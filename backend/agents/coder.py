import json
import time
from pathlib import Path

from backend.graph.state import AgentState
from backend.llm import get_groq_client, get_model
from backend.tools.filesystem import (
    read_file,
    write_file,
)


MAX_FILE_SIZE = 20_000
MAX_TOTAL_CONTEXT = 30_000
MAX_LLM_RETRIES = 3


CODER_SYSTEM_PROMPT = """
You are the Coder Agent in an autonomous software engineering system.

Your job is to implement the requested software changes in an existing
repository.

You must return ONLY valid JSON.

You must never return Markdown.
You must never return explanations outside the JSON object.

The JSON must have exactly this structure:

{
    "files": [
        {
            "path": "relative/path/to/file.py",
            "action": "create",
            "content": "complete file content"
        }
    ],
    "summary": "short description of implemented changes"
}

Allowed actions:

1. "create"
   Use only when the file does not already exist.

2. "modify"
   Use only when the file already exists.

Rules:

1. Use relative paths only.
2. Never use absolute paths.
3. Never use ".." in paths.
4. Never modify or create ".env".
5. Never modify or create ".git" files.
6. Never modify or create files inside ".venv".
7. Never modify or create "__pycache__" files.
8. Preserve the existing project architecture unless the requirement
   explicitly requires an architectural change.
9. When modifying an existing file, return the COMPLETE updated file.
10. Do not return partial code.
11. Do not use placeholders such as:
       TODO
       ...
       <existing code>
       <rest of code>
12. Do not invent files unless they are required by the task.
13. Follow the implementation plan.
14. Follow the debugger instructions when operating in repair mode.
15. Keep changes focused on the requested requirement.
16. Do not expose secrets or API keys.
17. Never create a file named ".env".
18. Never delete files unless the task explicitly requires deletion.
19. Do not rename files unless the task explicitly requires a rename.
20. Preserve existing functionality that is unrelated to the requested change.

IMPORTANT:

If a debugger identifies an existing file as needing repair, that file
must be returned with action "modify", not "create".

The Coder must not create a duplicate file when the debugger is asking
for an existing file to be repaired.
"""


def normalize_path(path: str) -> str:
    """
    Normalize a repository-relative path.
    """

    if not isinstance(path, str):
        raise ValueError(
            "File path must be a string."
        )

    path = path.strip()

    if not path:
        raise ValueError(
            "File path cannot be empty."
        )

    path = path.replace("\\", "/")

    while "//" in path:
        path = path.replace("//", "/")

    if path.startswith("./"):
        path = path[2:]

    return path


def is_safe_relative_path(path: str) -> bool:
    """
    Check whether a path is safe to access inside the repository.
    """

    try:
        normalized = normalize_path(path)
    except Exception:
        return False

    path_object = Path(normalized)

    if path_object.is_absolute():
        return False

    if ".." in path_object.parts:
        return False

    blocked_parts = {
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
    }

    if any(
        part in blocked_parts
        for part in path_object.parts
    ):
        return False

    if path_object.name == ".env":
        return False

    return True


def path_exists(
    repository_path: str,
    relative_path: str,
) -> bool:
    """
    Check whether a repository-relative file exists.
    """

    try:
        normalized = normalize_path(
            relative_path
        )

        if not is_safe_relative_path(
            normalized
        ):
            return False

        root = Path(
            repository_path
        ).resolve()

        file_path = (
            root / normalized
        ).resolve()

        try:
            file_path.relative_to(root)
        except ValueError:
            return False

        return file_path.exists()

    except Exception:
        return False


def build_file_context(
    repository_files: list[dict],
) -> str:
    """
    Build repository context for the Coder.
    """

    if not repository_files:
        return (
            "No repository file contents were provided."
        )

    sections = []
    total_size = 0

    for file_data in repository_files:

        if not isinstance(
            file_data,
            dict,
        ):
            continue

        path = file_data.get(
            "path",
            ""
        )

        content = file_data.get(
            "content",
            ""
        )

        if not path:
            continue

        path = normalize_path(
            path
        )

        if not is_safe_relative_path(
            path
        ):
            continue

        content = str(
            content
        )

        if len(content) > MAX_FILE_SIZE:
            content = (
                content[:MAX_FILE_SIZE]
                + "\n\n[FILE TRUNCATED]"
            )

        remaining = (
            MAX_TOTAL_CONTEXT
            - total_size
        )

        if remaining <= 0:
            break

        if len(content) > remaining:
            content = (
                content[:remaining]
                + "\n\n[CONTEXT TRUNCATED]"
            )

        section = (
            f"\n===== FILE: {path} =====\n"
            f"{content}\n"
            f"===== END FILE: {path} =====\n"
        )

        sections.append(
            section
        )

        total_size += len(
            content
        )

    if not sections:
        return (
            "No safe repository files were available."
        )

    return "\n".join(
        sections
    )


def build_plan_context(
    state: AgentState,
) -> str:
    """
    Convert the implementation plan into
    readable context for the Coder.
    """

    plan = state.get(
        "plan",
        []
    )

    if not plan:
        return (
            "No implementation plan was provided."
        )

    sections = []

    for task in plan:

        if not isinstance(
            task,
            dict,
        ):
            continue

        task_id = task.get(
            "id",
            ""
        )

        title = task.get(
            "title",
            ""
        )

        description = task.get(
            "description",
            ""
        )

        files_to_modify = task.get(
            "files_to_modify",
            []
        )

        files_to_create = task.get(
            "files_to_create",
            []
        )

        dependencies = task.get(
            "dependencies",
            []
        )

        tests_required = task.get(
            "tests_required",
            []
        )

        security_considerations = task.get(
            "security_considerations",
            []
        )

        sections.append(
            f"""
TASK {task_id}
Title:
{title}

Description:
{description}

Files to modify:
{files_to_modify}

Files to create:
{files_to_create}

Dependencies:
{dependencies}

Tests required:
{tests_required}

Security considerations:
{security_considerations}
"""
        )

    return "\n".join(
        sections
    )


def build_repair_context(
    state: AgentState,
) -> str:
    """
    Build context specifically for a debugger repair cycle.
    """

    debugger_result = state.get(
        "debugger_result",
        {}
    )

    if not debugger_result:
        return (
            "No debugger result was provided."
        )

    diagnosis = debugger_result.get(
        "diagnosis",
        ""
    )

    errors = debugger_result.get(
        "errors",
        []
    )

    files_to_fix = debugger_result.get(
        "files_to_fix",
        []
    )

    fix_instructions = debugger_result.get(
        "fix_instructions",
        []
    )

    severity = debugger_result.get(
        "severity",
        ""
    )

    return f"""
DEBUGGER DIAGNOSIS:
{diagnosis}

DEBUGGER ERRORS:
{errors}

FILES TO FIX:
{files_to_fix}

FIX INSTRUCTIONS:
{fix_instructions}

SEVERITY:
{severity}

IMPORTANT REPAIR RULE:

Every file listed by the debugger must be checked against the
repository before choosing "create" or "modify".

If the file already exists, the action MUST be "modify".

Do not create a second copy of an existing file.
"""


def build_coder_prompt(
    state: AgentState,
    task: dict,
    repair_mode: bool = False,
) -> str:
    """
    Build the complete prompt sent to the Coder LLM.
    """

    repository_files = state.get(
        "repository_files",
        []
    )

    repository_summary = state.get(
        "repository_summary",
        ""
    )

    architecture_summary = state.get(
        "architecture_summary",
        ""
    )

    user_request = state.get(
        "user_request",
        ""
    )

    file_context = build_file_context(
        repository_files
    )

    plan_context = build_plan_context(
        state
    )

    repair_context = ""

    if repair_mode:
        repair_context = build_repair_context(
            state
        )

    task_description = task.get(
        "description",
        ""
    )

    task_title = task.get(
        "title",
        ""
    )

    files_to_modify = task.get(
        "files_to_modify",
        []
    )

    files_to_create = task.get(
        "files_to_create",
        []
    )

    return f"""
{CODER_SYSTEM_PROMPT}

==================================================
USER REQUIREMENT
==================================================

{user_request}

==================================================
REPOSITORY SUMMARY
==================================================

{repository_summary}

==================================================
REPOSITORY ARCHITECTURE
==================================================

{architecture_summary}

==================================================
IMPLEMENTATION PLAN
==================================================

{plan_context}

==================================================
CURRENT TASK
==================================================

Task title:
{task_title}

Task description:
{task_description}

Files expected to modify:
{files_to_modify}

Files expected to create:
{files_to_create}

==================================================
REPOSITORY FILE CONTENT
==================================================

{file_context}

==================================================
REPAIR MODE
==================================================

{repair_mode}

{repair_context}

==================================================
CODING REQUIREMENTS
==================================================

Implement the current task.

Return complete file contents.

For existing files:
- return action "modify"
- return the complete updated file

For genuinely new files:
- return action "create"

Do not return partial files.

Do not return Markdown.

Return ONLY valid JSON.
"""


def clean_response(
    content,
) -> str:
    """
    Clean an LLM response before JSON parsing.
    """

    if content is None:
        return ""

    if isinstance(
        content,
        list,
    ):

        parts = []

        for item in content:

            if isinstance(
                item,
                dict,
            ):

                text = item.get(
                    "text",
                    ""
                )

                if text:
                    parts.append(
                        str(text)
                    )

            else:

                parts.append(
                    str(item)
                )

        content = "".join(
            parts
        )

    content = str(
        content
    ).strip()

    if not content:
        return ""

    if content.startswith(
        "```json"
    ):

        content = content[
            len("```json"):
        ]

    elif content.startswith(
        "```"
    ):

        content = content[
            len("```"):
        ]

    if content.endswith(
        "```"
    ):

        content = content[
            :-3
        ]

    return content.strip()


def validate_coder_response(
    result: dict,
    repository_path: str,
    authorized_modify: set[str],
    authorized_create: set[str],
    repair_mode: bool,
) -> None:
    """
    Validate the Coder LLM response before writing anything.
    """

    if not isinstance(
        result,
        dict,
    ):
        raise ValueError(
            "Coder response must be a JSON object."
        )

    if "files" not in result:
        raise ValueError(
            "Coder response is missing 'files'."
        )

    if "summary" not in result:
        raise ValueError(
            "Coder response is missing 'summary'."
        )

    files = result.get(
        "files"
    )

    if not isinstance(
        files,
        list,
    ):
        raise ValueError(
            "Coder 'files' must be a list."
        )

    seen_paths = set()

    for file_data in files:

        if not isinstance(
            file_data,
            dict,
        ):
            raise ValueError(
                "Each Coder file entry must be an object."
            )

        path = file_data.get(
            "path"
        )

        action = file_data.get(
            "action"
        )

        content = file_data.get(
            "content"
        )

        if not isinstance(
            path,
            str,
        ):
            raise ValueError(
                "Coder file path must be a string."
            )

        if not isinstance(
            action,
            str,
        ):
            raise ValueError(
                f"Missing action for file: {path}"
            )

        if not isinstance(
            content,
            str,
        ):
            raise ValueError(
                f"Missing content for file: {path}"
            )

        normalized = normalize_path(
            path
        )

        if not is_safe_relative_path(
            normalized
        ):
            raise ValueError(
                f"Unsafe file path: {normalized}"
            )

        if normalized in seen_paths:
            raise ValueError(
                f"Duplicate file returned: {normalized}"
            )

        seen_paths.add(
            normalized
        )

        if action not in {
            "create",
            "modify",
        }:
            raise ValueError(
                (
                    f"Invalid action '{action}' "
                    f"for file: {normalized}"
                )
            )

        exists = path_exists(
            repository_path,
            normalized
        )

        if action == "modify" and not exists:
            raise ValueError(
                (
                    f"Coder attempted to modify a file "
                    f"that does not exist: {normalized}"
                )
            )

        if action == "create" and exists:
            raise ValueError(
                (
                    f"Coder attempted to create an existing "
                    f"file: {normalized}. Use 'modify'."
                )
            )

        if repair_mode:

            if action == "create":
                raise ValueError(
                    (
                        "Repair mode does not allow arbitrary "
                        f"file creation: {normalized}"
                    )
                )

            if (
                authorized_modify
                and normalized not in authorized_modify
            ):
                raise ValueError(
                    (
                        "Repair Coder attempted to modify "
                        f"an unauthorized file: {normalized}"
                    )
                )

        else:

            if action == "modify":

                if (
                    authorized_modify
                    and normalized not in authorized_modify
                ):
                    raise ValueError(
                        (
                            "Coder attempted to modify "
                            f"an unauthorized file: {normalized}"
                        )
                    )

            if action == "create":

                if (
                    authorized_create
                    and normalized not in authorized_create
                ):
                    raise ValueError(
                        (
                            "Coder attempted to create "
                            f"an unauthorized file: {normalized}"
                        )
                    )

        if normalized == ".env":
            raise ValueError(
                "Coder cannot modify .env."
            )

        if (
            "GROQ_API_KEY="
            in content
            or "OPENAI_API_KEY="
            in content
        ):
            raise ValueError(
                (
                    f"Possible API key detected in "
                    f"generated file: {normalized}"
                )
            )


def call_coder_llm(
    prompt: str,
) -> dict:
    """
    Call Groq using structured JSON output.
    """

    client = get_groq_client()
    model = get_model()

    schema = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string"
                        },
                        "action": {
                            "type": "string",
                            "enum": [
                                "create",
                                "modify",
                            ],
                        },
                        "content": {
                            "type": "string"
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
                "type": "string"
            },
        },
        "required": [
            "files",
            "summary",
        ],
        "additionalProperties": False,
    }

    response = client.chat.completions.create(
        model=model,
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
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "coder_output",
                "schema": schema,
                "strict": True,
            },
        },
    )

    if not response.choices:
        raise ValueError(
            "Coder LLM returned no choices."
        )

    message = response.choices[0].message

    content = getattr(
        message,
        "content",
        None,
    )

    content = clean_response(
        content
    )

    if not content:
        raise ValueError(
            "Coder LLM returned an empty response."
        )

    try:
        return json.loads(
            content
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Coder returned invalid JSON: {exc}"
        ) from exc


def execute_task(
    state: AgentState,
    task: dict,
    repair_mode: bool = False,
) -> AgentState:
    """
    Execute one coding task.
    """

    repository_path = state.get(
        "repository_path"
    )

    if not repository_path:
        return {
            **state,
            "errors": [
                *state.get(
                    "errors",
                    [],
                ),
                "Coder: No repository path provided.",
            ],
            "current_step": "coding_failed",
        }

    debugger_result = state.get(
        "debugger_result",
        {}
    )

    authorized_modify = set()
    authorized_create = set()

    if repair_mode:

        debugger_files = debugger_result.get(
            "files_to_fix",
            []
        )

        for path in debugger_files:

            try:
                normalized = normalize_path(
                    path
                )
            except Exception:
                continue

            if not is_safe_relative_path(
                normalized
            ):
                continue

            if path_exists(
                repository_path,
                normalized
            ):
                authorized_modify.add(
                    normalized
                )

    else:

        for path in task.get(
            "files_to_modify",
            []
        ):

            try:
                normalized = normalize_path(
                    path
                )
            except Exception:
                continue

            if not is_safe_relative_path(
                normalized
            ):
                continue

            if path_exists(
                repository_path,
                normalized
            ):
                authorized_modify.add(
                    normalized
                )

        for path in task.get(
            "files_to_create",
            []
        ):

            try:
                normalized = normalize_path(
                    path
                )
            except Exception:
                continue

            if not is_safe_relative_path(
                normalized
            ):
                continue

            if not path_exists(
                repository_path,
                normalized
            ):
                authorized_create.add(
                    normalized
                )

    prompt = build_coder_prompt(
        state,
        task,
        repair_mode=repair_mode,
    )

    last_error = None

    for attempt in range(
        MAX_LLM_RETRIES
    ):

        try:

            result = call_coder_llm(
                prompt
            )

            validate_coder_response(
                result=result,
                repository_path=repository_path,
                authorized_modify=authorized_modify,
                authorized_create=authorized_create,
                repair_mode=repair_mode,
            )

            generated_files = list(
                state.get(
                    "generated_files",
                    []
                )
            )

            modified_files = list(
                state.get(
                    "modified_files",
                    []
                )
            )

            for file_data in result.get(
                "files",
                []
            ):

                relative_path = normalize_path(
                    file_data["path"]
                )

                action = file_data["action"]
                content = file_data["content"]

                if action == "modify":

                    write_file(
                        repository_path,
                        relative_path,
                        content,
                    )

                    if (
                        relative_path
                        not in modified_files
                    ):
                        modified_files.append(
                            relative_path
                        )

                elif action == "create":

                    write_file(
                        repository_path,
                        relative_path,
                        content,
                    )

                    if (
                        relative_path
                        not in generated_files
                    ):
                        generated_files.append(
                            relative_path
                        )

            return {
                **state,
                "generated_files": generated_files,
                "modified_files": modified_files,
                "current_step": "coding_complete",
            }

        except Exception as exc:

            last_error = exc

            if attempt < MAX_LLM_RETRIES - 1:

                time.sleep(1)

                prompt = (
                    build_coder_prompt(
                        state,
                        task,
                        repair_mode=repair_mode,
                    )
                    + f"""

PREVIOUS CODER ERROR:
{exc}

Correct the response.

Remember:
- Existing files MUST use action "modify".
- New files MUST use action "create".
- Repair mode cannot create arbitrary files.
- Return complete file contents.
- Return ONLY valid JSON.
"""
                )

    raise RuntimeError(
        f"Coder failed on task {task.get('id', 'unknown')}: "
        f"{last_error}"
    )


def coder_agent(
    state: AgentState,
) -> AgentState:
    """
    Main Coder Agent.

    Normal mode:
        Implements the planned task.

    Repair mode:
        Uses Debugger output to repair failed code.
    """

    repair_mode = bool(
        state.get(
            "debugger_result"
        )
    ) and (
        state.get(
            "current_step"
        ) in {
            "debugging_complete",
            "debug_retry",
        }
    )

    try:

        if repair_mode:

            debugger_result = state.get(
                "debugger_result",
                {}
            )

            files_to_fix = debugger_result.get(
                "files_to_fix",
                []
            )

            if not files_to_fix:
                return {
                    **state,
                    "errors": [
                        *state.get(
                            "errors",
                            [],
                        ),
                        (
                            "Coder repair skipped: "
                            "Debugger did not identify files to fix."
                        ),
                    ],
                    "current_step": "coding_failed",
                }

            repair_task = {
                "id": 0,
                "title": "Repair failed implementation",
                "description": (
                    debugger_result.get(
                        "diagnosis",
                        "Repair the implementation based on test failures.",
                    )
                ),
                "files_to_modify": files_to_fix,
                "files_to_create": [],
                "dependencies": [],
                "tests_required": [],
                "security_considerations": [],
            }

            return execute_task(
                state,
                repair_task,
                repair_mode=True,
            )

        plan = state.get(
            "plan",
            []
        )

        if not plan:
            return {
                **state,
                "errors": [
                    *state.get(
                        "errors",
                        [],
                    ),
                    "Coder: No implementation plan available.",
                ],
                "current_step": "coding_failed",
            }

        current_task_id = state.get(
            "current_task_id"
        )

        task = None

        if current_task_id is not None:

            for planned_task in plan:

                if (
                    planned_task.get(
                        "id"
                    )
                    == current_task_id
                ):
                    task = planned_task
                    break

        if task is None:
            task = plan[0]

        return execute_task(
            state,
            task,
            repair_mode=False,
        )

    except Exception as exc:

        return {
            **state,
            "errors": [
                *state.get(
                    "errors",
                    [],
                ),
                f"Coder error: {exc}",
            ],
            "current_step": "coding_failed",
        }