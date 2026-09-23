import json
import time

from backend.graph.state import AgentState
from backend.llm import (
    get_groq_client,
    get_model,
)
from backend.tools.filesystem import (
    read_file,
    write_file,
)


MAX_FILE_CONTEXT = 8000
MAX_TOTAL_CONTEXT = 20000

MAX_CODER_RETRIES = 2
RATE_LIMIT_WAIT_SECONDS = 20


CODER_SYSTEM_PROMPT = """
You are the Coder Agent in an autonomous software engineering system.

Implement the assigned software engineering task inside the existing repository.

You MUST return a response matching the provided JSON schema.

Rules:

1. Implement ONLY the current task.
2. Return complete file contents.
3. Never return partial code.
4. Modify ONLY files explicitly listed in files_to_modify.
5. Create ONLY files explicitly listed in files_to_create.
6. Never modify .env.
7. Never expose secrets or API keys.
8. Preserve the existing project architecture.
9. Reuse existing modules whenever possible.
10. Do not rename files.
11. Do not invent files.
12. Do not modify unrelated files.
13. Ensure imports are correct.
14. Ensure Python syntax is valid.
15. Do not return Markdown.
16. Every modified file must contain its complete new content.
17. Every created file must contain its complete content.
18. If a dependency is required, modify requirements.txt only when
    requirements.txt is explicitly authorized by the current task.
19. Do not silently add dependencies without updating an authorized
    dependency file.
"""


def normalize_path(path: str) -> str:
    return str(path).replace("\\", "/")


def build_file_context(
    state: AgentState,
    task: dict,
) -> str:
    """
    Build context from the CURRENT repository state.

    This deliberately reads authorized files directly from disk.
    This prevents later tasks and repair tasks from receiving stale
    repository content.
    """

    repository_path = state.get(
        "repository_path"
    )

    if not repository_path:
        raise ValueError(
            "Repository path is missing."
        )

    allowed_paths = []

    for path in task.get(
        "files_to_modify",
        [],
    ):
        normalized = normalize_path(path)

        if normalized not in allowed_paths:
            allowed_paths.append(normalized)

    for path in task.get(
        "files_to_create",
        [],
    ):
        normalized = normalize_path(path)

        if normalized not in allowed_paths:
            allowed_paths.append(normalized)

    # Also include important files from the original repository context.
    for file_data in state.get(
        "repository_files",
        [],
    ):
        path = normalize_path(
            file_data.get("path", "")
        )

        if (
            path
            and path not in allowed_paths
        ):
            allowed_paths.append(path)

    sections = []
    total_size = 0

    for relative_path in allowed_paths:

        if relative_path == ".env":
            continue

        if total_size >= MAX_TOTAL_CONTEXT:
            break

        # -----------------------------------------------------
        # Files that are supposed to be created do not exist yet.
        # -----------------------------------------------------

        is_create_target = (
            relative_path
            in {
                normalize_path(path)
                for path in task.get(
                    "files_to_create",
                    [],
                )
            }
        )

        if is_create_target:

            sections.append(
                f"""
FILE: {relative_path}

[NEW FILE - DOES NOT EXIST YET]
"""
            )

            continue

        # -----------------------------------------------------
        # Read the ACTUAL current file.
        # -----------------------------------------------------

        try:
            content = read_file(
                repository_path,
                relative_path,
            )

        except FileNotFoundError:
            content = (
                "[FILE DOES NOT CURRENTLY EXIST]"
            )

        except Exception as exc:
            content = (
                f"[FILE COULD NOT BE READ: {exc}]"
            )

        if len(content) > MAX_FILE_CONTEXT:
            content = (
                content[:MAX_FILE_CONTEXT]
                + "\n\n[FILE CONTEXT TRUNCATED]"
            )

        remaining = (
            MAX_TOTAL_CONTEXT
            - total_size
        )

        if len(content) > remaining:
            content = (
                content[:remaining]
                + "\n\n[CONTEXT TRUNCATED]"
            )

        sections.append(
            f"""
FILE: {relative_path}

{content}
"""
        )

        total_size += len(content)

    return "\n".join(sections)


def build_coder_prompt(
    state: AgentState,
    task: dict,
    repair_mode: bool = False,
) -> str:

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
DEBUGGER ANALYSIS
=================

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
        state,
        task,
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
{task.get("title", "")}

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

CURRENT REPOSITORY FILE CONTENT
===============================

{context}

IMPLEMENTATION REQUIREMENTS
===========================

1. Implement ONLY this task.
2. Modify ONLY authorized files.
3. Create ONLY authorized files.
4. Return COMPLETE contents for every changed file.
5. Do not return unchanged files unless required by the task.
6. Do not modify .env.
7. Do not expose secrets.
8. Preserve the architecture.
9. Keep imports valid.
10. Keep Python syntax valid.
"""


def build_coder_schema() -> dict:
    """
    Native Groq strict JSON schema.

    All fields are required because Groq strict structured
    output requires complete schemas.
    """

    return {
        "name": "coder_response",
        "strict": True,
        "schema": {
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
        },
    }


def is_rate_limit_error(
    error: Exception,
) -> bool:

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
        normalize_path(path)
        for path in task.get(
            "files_to_modify",
            [],
        )
    }

    allowed_create = {
        normalize_path(path)
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

        path = normalize_path(
            file_data.get(
                "path",
                "",
            )
        )

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

        if action == "modify" and path not in allowed_modify:
            raise ValueError(
                f"Unauthorized modification: {path}"
            )

        if action == "create" and path not in allowed_create:
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

    # Verify that every authorized target was returned.
    expected = (
        allowed_modify
        | allowed_create
    )

    returned = {
        item["path"]
        for item in validated
    }

    missing = expected - returned

    if missing:
        raise ValueError(
            "Coder did not return all authorized files: "
            f"{sorted(missing)}"
        )

    return validated


def call_coder_llm(
    prompt: str,
) -> dict:

    client = get_groq_client()

    response = client.chat.completions.create(
        model=get_model(),
        messages=[
            {
                "role": "system",
                "content": CODER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
        reasoning_effort="low",
        max_tokens=20000,
        response_format={
            "type": "json_schema",
            "json_schema": build_coder_schema(),
        },
    )

    if not response.choices:
        raise ValueError(
            "Groq returned no choices."
        )

    message = response.choices[0].message

    content = message.content

    if not content:
        raise ValueError(
            "Groq Coder returned an empty response."
        )

    try:
        data = json.loads(
            content
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Groq Coder returned invalid JSON: {exc}"
        ) from exc

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Groq Coder response is not a JSON object."
        )

    return data


def execute_task(
    state: AgentState,
    task: dict,
    repair_mode: bool = False,
):
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

            # Validate ALL files before writing ANY file.
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

            # Write only after complete validation.
            for file_data in generated_files:

                write_file(
                    repository_path,
                    file_data["path"],
                    file_data["content"],
                )

            return generated, modified

        except Exception as exc:

            last_error = exc

            if attempt >= MAX_CODER_RETRIES:
                break

            if is_rate_limit_error(exc):
                time.sleep(
                    RATE_LIMIT_WAIT_SECONDS
                    * attempt
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

    if not state.get("repository_path"):
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

        files_to_fix = [
            normalize_path(path)
            for path in debugger_result.get(
                "files_to_fix",
                [],
            )
        ]

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
                "Repair the implementation using the "
                "Debugger Agent analysis."
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
                    generated_files.append(path)

            for path in modified:
                if path not in modified_files:
                    modified_files.append(path)

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
                    generated_files.append(path)

            for path in modified:
                if path not in modified_files:
                    modified_files.append(path)

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