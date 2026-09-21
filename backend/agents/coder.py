import json
import time

from backend.graph.state import AgentState
from backend.llm import get_llm
from backend.tools.filesystem import read_file, write_file


MAX_FILE_CONTEXT = 4000
MAX_TOTAL_CONTEXT = 7000

MAX_CODER_RETRIES = 2
RATE_LIMIT_WAIT_SECONDS = 20


CODER_SYSTEM_PROMPT = """
You are the Coder Agent in an autonomous software engineering system.

Implement the assigned software engineering task inside the existing repository.

Your response MUST follow the provided structured JSON schema.

Rules:

1. Return only the structured JSON object.
2. Never use Markdown code fences.
3. Return COMPLETE file contents.
4. Never return partial code.
5. Only modify files explicitly allowed by the current task.
6. Never modify .env.
7. Never expose secrets or API keys.
8. Preserve the existing project architecture.
9. Reuse existing modules whenever possible.
10. Do not rename files.
11. Do not invent files.
12. Do not modify unrelated files.
13. Ensure imports are correct.
14. Ensure generated Python is syntactically valid.
15. Implement only the current task.
"""


def build_file_context(
    task: dict,
    repository_files: list[dict],
) -> str:
    """
    Build a compact repository context.

    Files directly involved in the current task
    are placed first.
    """

    allowed_files = set()

    for path in task.get(
        "files_to_modify",
        [],
    ):
        allowed_files.add(
            path.replace("\\", "/")
        )

    for path in task.get(
        "files_to_create",
        [],
    ):
        allowed_files.add(
            path.replace("\\", "/")
        )

    prioritized = []
    remaining = []

    for file_data in repository_files:

        path = file_data.get(
            "path",
            "",
        ).replace("\\", "/")

        if path in allowed_files:
            prioritized.append(
                file_data
            )
        else:
            remaining.append(
                file_data
            )

    ordered_files = (
        prioritized
        + remaining
    )

    sections = []
    total_size = 0

    for file_data in ordered_files:

        path = file_data.get(
            "path",
            "",
        )

        content = file_data.get(
            "content",
            "",
        )

        if not path:
            continue

        if total_size >= MAX_TOTAL_CONTEXT:
            break

        if len(content) > MAX_FILE_CONTEXT:
            content = (
                content[:MAX_FILE_CONTEXT]
                + "\n[FILE TRUNCATED]"
            )

        remaining_size = (
            MAX_TOTAL_CONTEXT
            - total_size
        )

        if len(content) > remaining_size:
            content = (
                content[:remaining_size]
                + "\n[CONTEXT TRUNCATED]"
            )

        sections.append(
            f"""
FILE: {path}

{content}
"""
        )

        total_size += len(content)

    return "\n".join(
        sections
    )


def build_coder_prompt(
    state: AgentState,
    task: dict,
    repair_mode: bool = False,
) -> str:
    """
    Build the Coder prompt.
    """

    repository_files = state.get(
        "repository_files",
        [],
    )

    mode = (
        "REPAIR MODE"
        if repair_mode
        else "NORMAL IMPLEMENTATION MODE"
    )

    debugger_section = ""

    if repair_mode:

        debugger = state.get(
            "debugger_result",
            {},
        )

        debugger_section = f"""
DEBUGGER RESULT
===============

Diagnosis:
{debugger.get("diagnosis", "")}

Errors:
{json.dumps(
    debugger.get("errors", []),
    indent=2,
)}

Files to fix:
{json.dumps(
    debugger.get("files_to_fix", []),
    indent=2,
)}

Fix instructions:
{json.dumps(
    debugger.get("fix_instructions", []),
    indent=2,
)}

Severity:
{debugger.get("severity", "")}
"""

    context = build_file_context(
        task,
        repository_files,
    )

    return f"""
CODER MODE
==========

{mode}

USER REQUIREMENT
================

{state.get("user_request", "")}

CURRENT TASK
============

Task ID:
{task.get("id")}

Title:
{task.get("title")}

Description:
{task.get("description", "")}

Files to modify:
{json.dumps(
    task.get("files_to_modify", []),
    indent=2,
)}

Files to create:
{json.dumps(
    task.get("files_to_create", []),
    indent=2,
)}

Dependencies:
{json.dumps(
    task.get("dependencies", []),
    indent=2,
)}

{debugger_section}

EXISTING FILE CONTEXT
=====================

{context}

IMPLEMENTATION REQUIREMENTS
===========================

1. Implement ONLY the current task.

2. Modify ONLY files listed in files_to_modify.

3. Create ONLY files listed in files_to_create.

4. For every modified file, return its COMPLETE file content.

5. For every created file, return its COMPLETE file content.

6. Do not modify unrelated files.

7. Do not modify .env.

8. Do not expose secrets.

9. Preserve the existing architecture.

10. Make all imports valid.

11. Make all Python syntax valid.

12. Return every required file in the structured response.
"""


def build_coder_schema() -> dict:
    """
    Build the JSON schema used by the Coder.

    Groq/LangChain function-based structured output
    requires a top-level title.
    """

    return {
        "title": "CoderResponse",
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                        },
                        "action": {
                            "type": "string",
                            "enum": [
                                "create",
                                "modify",
                            ],
                        },
                        "content": {
                            "type": "string",
                        },
                    },
                    "required": [
                        "path",
                        "action",
                        "content",
                    ],
                    "additionalProperties": False,
                },
            },
            "summary": {
                "type": "string",
            },
        },
        "required": [
            "files",
            "summary",
        ],
        "additionalProperties": False,
    }


def is_rate_limit_error(
    error: Exception,
) -> bool:
    """
    Detect Groq rate-limit errors.
    """

    message = str(error).lower()

    keywords = [
        "rate limit",
        "rate_limit",
        "too many requests",
        "tokens per minute",
        "tpm",
        "429",
    ]

    return any(
        keyword in message
        for keyword in keywords
    )


def validate_coder_response(
    data: dict,
    task: dict,
) -> list[dict]:
    """
    Validate the structured Coder response
    against the current task permissions.
    """

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Coder response must be a JSON object."
        )

    files = data.get(
        "files"
    )

    if not isinstance(
        files,
        list,
    ):
        raise ValueError(
            "Coder response must contain a files array."
        )

    allowed_modify = {
        path.replace("\\", "/")
        for path in task.get(
            "files_to_modify",
            [],
        )
    }

    allowed_create = {
        path.replace("\\", "/")
        for path in task.get(
            "files_to_create",
            [],
        )
    }

    validated = []
    seen_paths = set()

    for file_data in files:

        if not isinstance(
            file_data,
            dict,
        ):
            raise ValueError(
                "Each generated file must be an object."
            )

        path = str(
            file_data.get(
                "path",
                "",
            )
        ).replace("\\", "/")

        action = file_data.get(
            "action"
        )

        content = file_data.get(
            "content"
        )

        if not path:
            raise ValueError(
                "Coder returned a file without a path."
            )

        if path == ".env":
            raise ValueError(
                "Coder cannot modify .env."
            )

        if path in seen_paths:
            raise ValueError(
                f"Coder returned the same file twice: {path}"
            )

        seen_paths.add(path)

        if action not in {
            "create",
            "modify",
        }:
            raise ValueError(
                f"Invalid action for {path}: {action}"
            )

        if action == "modify":

            if path not in allowed_modify:
                raise ValueError(
                    f"Unauthorized modification: {path}"
                )

        if action == "create":

            if path not in allowed_create:
                raise ValueError(
                    f"Unauthorized file creation: {path}"
                )

        if not isinstance(
            content,
            str,
        ):
            raise ValueError(
                f"Content for {path} must be a string."
            )

        if not content.strip():
            raise ValueError(
                f"Coder returned empty content for {path}."
            )

        validated.append(
            {
                "path": path,
                "action": action,
                "content": content,
            }
        )

    if not validated:
        raise ValueError(
            "Coder returned no files."
        )

    return validated


def call_coder_llm(
    prompt: str,
) -> dict:
    """
    Call Groq using structured JSON output.
    """

    llm = get_llm()

    schema = build_coder_schema()

    structured_llm = llm.with_structured_output(
        schema,
        method="json_schema",
    )

    response = structured_llm.invoke(
        [
            (
                "system",
                CODER_SYSTEM_PROMPT,
            ),
            (
                "human",
                prompt,
            ),
        ]
    )

    if response is None:
        raise ValueError(
            "Coder returned no structured response."
        )

    if isinstance(
        response,
        dict,
    ):
        return response

    if hasattr(
        response,
        "content",
    ):

        content = response.content

        if isinstance(
            content,
            dict,
        ):
            return content

        if isinstance(
            content,
            str,
        ):

            content = content.strip()

            if not content:
                raise ValueError(
                    "Coder returned an empty response."
                )

            try:

                parsed = json.loads(
                    content
                )

                if not isinstance(
                    parsed,
                    dict,
                ):
                    raise ValueError(
                        "Structured response is not an object."
                    )

                return parsed

            except json.JSONDecodeError as exc:

                raise ValueError(
                    f"Coder returned invalid JSON: {exc}"
                ) from exc

    raise ValueError(
        "Coder returned an unsupported structured response."
    )


def execute_task(
    state: AgentState,
    task: dict,
    repair_mode: bool = False,
):
    """
    Execute one Coder task.

    All files are validated before any file is written.
    """

    prompt = build_coder_prompt(
        state,
        task,
        repair_mode=repair_mode,
    )

    last_error = None

    for attempt in range(
        1,
        MAX_CODER_RETRIES + 1,
    ):

        try:

            response_data = call_coder_llm(
                prompt
            )

            generated_files = (
                validate_coder_response(
                    response_data,
                    task,
                )
            )

            repository_path = state.get(
                "repository_path"
            )

            if not repository_path:
                raise ValueError(
                    "Repository path is missing."
                )

            generated = []
            modified = []

            # -------------------------------------------------
            # VALIDATION PHASE
            # -------------------------------------------------

            for file_data in generated_files:

                path = file_data["path"]
                action = file_data["action"]

                if action == "modify":

                    read_file(
                        repository_path,
                        path,
                    )

                generated.append(
                    path
                )

                if action == "modify":
                    modified.append(
                        path
                    )

            # -------------------------------------------------
            # WRITE PHASE
            # -------------------------------------------------

            for file_data in generated_files:

                write_file(
                    repository_path,
                    file_data["path"],
                    file_data["content"],
                )

            return (
                generated,
                modified,
            )

        except Exception as exc:

            last_error = exc

            if attempt >= MAX_CODER_RETRIES:
                break

            if is_rate_limit_error(exc):

                wait_time = (
                    RATE_LIMIT_WAIT_SECONDS
                    * attempt
                )

                time.sleep(
                    wait_time
                )

            else:

                time.sleep(2)

    raise RuntimeError(
        f"Coder failed on task {task.get('id')}: "
        f"{last_error}"
    )


def coder_agent(
    state: AgentState,
) -> AgentState:
    """
    Execute planned tasks or repair failed code.
    """

    plan = state.get(
        "plan",
        [],
    )

    if not plan:

        return {
            **state,
            "generated_files": [],
            "modified_files": [],
            "errors": [
                *state.get("errors", []),
                "Coder Agent: No implementation plan was provided.",
            ],
            "current_step": "coding_failed",
        }

    repository_path = state.get(
        "repository_path"
    )

    if not repository_path:

        return {
            **state,
            "generated_files": [],
            "modified_files": [],
            "errors": [
                *state.get("errors", []),
                "Coder Agent: Repository path is missing.",
            ],
            "current_step": "coding_failed",
        }

    generated_files = list(
        state.get(
            "generated_files",
            [],
        )
    )

    modified_files = list(
        state.get(
            "modified_files",
            [],
        )
    )

    debugger_result = state.get(
        "debugger_result",
        {},
    )

    # ---------------------------------------------------------
    # REPAIR MODE
    # ---------------------------------------------------------

    if debugger_result:

        files_to_fix = debugger_result.get(
            "files_to_fix",
            [],
        )

        if not files_to_fix:

            return {
                **state,
                "errors": [
                    *state.get("errors", []),
                    "Coder Agent: Debugger did not identify files to fix.",
                ],
                "current_step": "coding_failed",
            }

        repair_task = {
            "id": state.get(
                "current_task_id",
                0,
            ),
            "title": "Repair failed implementation",
            "description": (
                "Repair the implementation using "
                "the Debugger Agent analysis."
            ),
            "files_to_modify": files_to_fix,
            "files_to_create": [],
            "dependencies": [],
        }

        try:

            generated, modified = execute_task(
                state,
                repair_task,
                repair_mode=True,
            )

            for path in generated:

                if path not in generated_files:
                    generated_files.append(
                        path
                    )

            for path in modified:

                if path not in modified_files:
                    modified_files.append(
                        path
                    )

            return {
                **state,
                "generated_files": generated_files,
                "modified_files": modified_files,
                "debugger_result": {},
                "current_step": "coding_complete",
            }

        except Exception as exc:

            return {
                **state,
                "generated_files": generated_files,
                "modified_files": modified_files,
                "errors": [
                    *state.get("errors", []),
                    f"Coder repair failed: {exc}",
                ],
                "current_step": "coding_failed",
            }

    # ---------------------------------------------------------
    # NORMAL IMPLEMENTATION MODE
    # ---------------------------------------------------------

    try:

        for task in plan:

            task_id = task.get(
                "id"
            )

            task_state = {
                **state,
                "current_task_id": task_id,
            }

            generated, modified = execute_task(
                task_state,
                task,
                repair_mode=False,
            )

            for path in generated:

                if path not in generated_files:
                    generated_files.append(
                        path
                    )

            for path in modified:

                if path not in modified_files:
                    modified_files.append(
                        path
                    )

        return {
            **state,
            "generated_files": generated_files,
            "modified_files": modified_files,
            "current_step": "coding_complete",
        }

    except Exception as exc:

        return {
            **state,
            "generated_files": generated_files,
            "modified_files": modified_files,
            "errors": [
                *state.get("errors", []),
                f"Coder failed: {exc}",
            ],
            "current_step": "coding_failed",
        }