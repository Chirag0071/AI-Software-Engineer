import json
import time
from pathlib import Path

from backend.graph.state import AgentState
from backend.llm import get_groq_client, get_model
from backend.tools.filesystem import read_file, write_file


MAX_FILE_SIZE = 20_000
MAX_TOTAL_CONTEXT = 30_000
MAX_LLM_RETRIES = 3
RATE_LIMIT_WAIT_SECONDS = 10


CODER_SYSTEM_PROMPT = """
You are the Coder Agent in an autonomous software engineering system.

Implement ONLY the current task.

Return ONLY valid JSON using this structure:

{
    "files": [
        {
            "path": "relative/path.py",
            "action": "create",
            "content": "complete file content"
        }
    ],
    "summary": "short implementation summary"
}

Rules:

1. Modify only files listed in files_to_modify.
2. Create only files listed in files_to_create.
3. Files in READ-ONLY CONTEXT may be read but must NEVER be returned.
4. Never modify .env.
5. Never modify .git, .venv, __pycache__, node_modules or .pytest_cache.
6. Use relative paths only.
7. Never use ".." in paths.
8. Return complete file contents.
9. Do not return Markdown.
10. Do not return partial code.
11. Do not add unrelated changes.
12. Preserve existing functionality.
13. Do not expose secrets.
14. If repairing an existing file, use action "modify".
15. Follow the implementation plan exactly.
"""


def normalize_path(path: str) -> str:
    if not isinstance(path, str):
        raise ValueError("File path must be a string.")

    path = path.strip().replace("\\", "/")

    while "//" in path:
        path = path.replace("//", "/")

    if path.startswith("./"):
        path = path[2:]

    if not path:
        raise ValueError("File path cannot be empty.")

    return path


def is_safe_relative_path(path: str) -> bool:
    try:
        path = normalize_path(path)
    except ValueError:
        return False

    p = Path(path)

    if p.is_absolute():
        return False

    if ".." in p.parts:
        return False

    blocked = {
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
    }

    if any(part in blocked for part in p.parts):
        return False

    if p.name == ".env":
        return False

    return True


def build_authorized_paths(task: dict) -> tuple[set[str], set[str]]:
    modify = {
        normalize_path(path)
        for path in task.get("files_to_modify", [])
    }

    create = {
        normalize_path(path)
        for path in task.get("files_to_create", [])
    }

    for path in modify | create:
        if not is_safe_relative_path(path):
            raise ValueError(
                f"Unsafe authorized file path: {path}"
            )

    return modify, create


def build_file_context(
    repository_files: list[dict],
    task: dict,
    repository_path: str = "",
    read_only_paths: set[str] | None = None,
) -> str:
    """
    Give the Coder writable context only for authorized files.
    Dependency files may be supplied as read-only context.
    """

    modify_paths, create_paths = build_authorized_paths(task)
    read_only_paths = {
        normalize_path(path)
        for path in (read_only_paths or set())
        if is_safe_relative_path(path)
    }

    writable_paths = modify_paths | create_paths

    if not writable_paths:
        raise ValueError(
            "Current task does not authorize any files."
        )

    snapshot = {}

    for file_data in repository_files:
        if not isinstance(file_data, dict):
            continue

        path = file_data.get("path", "")
        if not path:
            continue

        try:
            path = normalize_path(path)
        except ValueError:
            continue

        if not is_safe_relative_path(path):
            continue

        snapshot[path] = str(
            file_data.get("content", "")
        )

    sections = []
    total = 0
    context_paths = list(writable_paths) + [
        path
        for path in read_only_paths
        if path not in writable_paths
    ]

    for path in context_paths:
        if total >= MAX_TOTAL_CONTEXT:
            break

        is_read_only = (
            path in read_only_paths
            and path not in writable_paths
        )

        if path in create_paths and path not in snapshot:
            content = "[NEW FILE - DOES NOT EXIST]"
        elif repository_path:
            try:
                content = read_file(
                    repository_path,
                    path,
                )
            except FileNotFoundError:
                content = "[FILE DOES NOT EXIST]"
            except Exception as exc:
                content = f"[FILE READ ERROR: {exc}]"
        elif path in snapshot:
            content = snapshot[path]
        else:
            content = "[FILE DOES NOT EXIST]"

        if len(content) > MAX_FILE_SIZE:
            content = (
                content[:MAX_FILE_SIZE]
                + "\n[FILE CONTEXT TRUNCATED]"
            )

        remaining = MAX_TOTAL_CONTEXT - total
        if len(content) > remaining:
            content = (
                content[:remaining]
                + "\n[CONTEXT TRUNCATED]"
            )

        label = "READ-ONLY FILE" if is_read_only else "AUTHORIZED FILE"
        sections.append(
            f"{label}: {path}\n"
            f"{content}\n"
            f"END FILE: {path}"
        )
        total += len(content)

    return "\n\n".join(sections)


def build_read_only_dependency_paths(
    state: AgentState,
    task: dict,
) -> set[str]:
    """Resolve earlier task files as read-only context."""
    dependencies = {
        str(item)
        for item in task.get("dependencies", [])
    }

    if not dependencies:
        return set()

    paths = set()

    for previous_task in state.get("plan", []):
        if str(previous_task.get("id")) not in dependencies:
            continue

        for path in (
            previous_task.get("files_to_modify", [])
            + previous_task.get("files_to_create", [])
        ):
            path = normalize_path(path)
            if is_safe_relative_path(path):
                paths.add(path)

    return paths


def build_plan_context(state: AgentState) -> str:
    plan = state.get("plan", [])

    if not plan:
        return "No implementation plan."

    sections = []

    for task in plan:
        sections.append(
            json.dumps(
                {
                    "id": task.get("id"),
                    "title": task.get("title"),
                    "description": task.get("description"),
                    "files_to_modify": task.get(
                        "files_to_modify",
                        [],
                    ),
                    "files_to_create": task.get(
                        "files_to_create",
                        [],
                    ),
                    "dependencies": task.get(
                        "dependencies",
                        [],
                    ),
                    "tests_required": task.get(
                        "tests_required",
                        [],
                    ),
                },
                indent=2,
            )
        )

    return "\n\n".join(sections)


def build_coder_prompt(
    state: AgentState,
    task: dict,
    repair_mode: bool = False,
) -> str:

    read_only_paths = build_read_only_dependency_paths(
        state,
        task,
    )

    context = build_file_context(
        state.get("repository_files", []),
        task,
        state.get("repository_path", ""),
        read_only_paths,
    )

    debugger = state.get(
        "debugger_result",
        {},
    )

    repair_context = ""

    if repair_mode:
        repair_context = f"""
DEBUGGER ANALYSIS

Diagnosis:
{debugger.get("diagnosis", "")}

Errors:
{json.dumps(debugger.get("errors", []), indent=2)}

Files to fix:
{json.dumps(debugger.get("files_to_fix", []), indent=2)}

Instructions:
{json.dumps(debugger.get("fix_instructions", []), indent=2)}
"""

    return f"""
CURRENT TASK

ID:
{task.get("id")}

Title:
{task.get("title", "")}

Description:
{task.get("description", "")}

Files allowed to modify:
{json.dumps(task.get("files_to_modify", []), indent=2)}

Files allowed to create:
{json.dumps(task.get("files_to_create", []), indent=2)}

Read-only dependency files:
{json.dumps(sorted(read_only_paths), indent=2)}

USER REQUIREMENT

{state.get("user_request", "")}

IMPLEMENTATION PLAN

{build_plan_context(state)}

{repair_context}

AUTHORIZED FILE CONTENT

{context}

IMPORTANT:

The authorization lists above are the final authority.

You may read READ-ONLY FILE content for understanding,
but you MUST NOT return those files.

Return complete content only for files that the current
task is authorized to modify or create.
"""


def build_coder_schema() -> dict:
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


def call_coder_llm(prompt: str) -> dict:
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
        max_tokens=20_000,
        response_format={
            "type": "json_schema",
            "json_schema": build_coder_schema(),
        },
    )

    if not response.choices:
        raise ValueError(
            "Coder received no LLM response."
        )

    content = response.choices[0].message.content

    if not content:
        raise ValueError(
            "Coder received an empty LLM response."
        )

    data = json.loads(content)

    if not isinstance(data, dict):
        raise ValueError(
            "Coder response must be a JSON object."
        )

    return data


def validate_coder_response(
    data: dict,
    task: dict,
) -> list[dict]:

    if not isinstance(data, dict):
        raise ValueError(
            "Coder response must be an object."
        )

    files = data.get("files")

    if not isinstance(files, list) or not files:
        raise ValueError(
            "Coder returned no files."
        )

    allowed_modify, allowed_create = (
        build_authorized_paths(task)
    )

    allowed = allowed_modify | allowed_create

    validated = []
    seen = set()

    for item in files:
        if not isinstance(item, dict):
            raise ValueError(
                "Invalid coder file object."
            )

        path = normalize_path(
            item.get("path", "")
        )

        action = item.get("action")
        content = item.get("content")

        if path in seen:
            raise ValueError(
                f"Duplicate file returned: {path}"
            )

        seen.add(path)

        if path not in allowed:
            raise ValueError(
                f"Coder attempted to modify "
                f"an unauthorized file: {path}"
            )

        if action == "modify" and path not in allowed_modify:
            raise ValueError(
                f"File is not authorized for modification: {path}"
            )

        if action == "create" and path not in allowed_create:
            raise ValueError(
                f"File is not authorized for creation: {path}"
            )

        if not isinstance(content, str) or not content.strip():
            raise ValueError(
                f"Empty content returned for: {path}"
            )

        validated.append(
            {
                "path": path,
                "action": action,
                "content": content,
            }
        )

    return validated


def execute_task(
    state: AgentState,
    task: dict,
    repair_mode: bool = False,
):
    prompt = build_coder_prompt(
        state,
        task,
        repair_mode,
    )

    last_error = None

    for attempt in range(
        1,
        MAX_LLM_RETRIES + 1,
    ):
        try:
            response = call_coder_llm(
                prompt
            )

            files = validate_coder_response(
                response,
                task,
            )

            repository_path = state.get(
                "repository_path"
            )

            if not repository_path:
                raise ValueError(
                    "Repository path is missing."
                )

            for file_data in files:
                path = file_data["path"]

                if file_data["action"] == "modify":
                    if not Path(
                        repository_path,
                        path,
                    ).exists():
                        raise ValueError(
                            f"File does not exist: {path}"
                        )

            for file_data in files:
                write_file(
                    repository_path,
                    file_data["path"],
                    file_data["content"],
                )

            generated = [
                item["path"]
                for item in files
            ]

            modified = [
                item["path"]
                for item in files
                if item["action"] == "modify"
            ]

            return generated, modified

        except Exception as exc:
            last_error = exc

            if attempt == MAX_LLM_RETRIES:
                break

            message = str(exc).lower()

            if any(
                word in message
                for word in (
                    "rate limit",
                    "too many requests",
                    "429",
                    "tokens per minute",
                )
            ):
                time.sleep(
                    RATE_LIMIT_WAIT_SECONDS * attempt
                )
            else:
                time.sleep(2)

    raise RuntimeError(
        f"Coder failed on task {task.get('id')}: "
        f"{last_error}"
    )


def coder_agent(state: AgentState) -> AgentState:
    plan = state.get("plan", [])

    if not plan:
        return {
            **state,
            "current_step": "coding_failed",
            "errors": [
                *state.get("errors", []),
                "Coder: implementation plan is empty.",
            ],
        }

    if not state.get("repository_path"):
        return {
            **state,
            "current_step": "coding_failed",
            "errors": [
                *state.get("errors", []),
                "Coder: repository path is missing.",
            ],
        }

    generated_files = list(
        state.get("generated_files", [])
    )

    modified_files = list(
        state.get("modified_files", [])
    )

    debugger = state.get(
        "debugger_result",
        {},
    )

    try:
        if debugger:
            files_to_fix = [
                normalize_path(path)
                for path in debugger.get(
                    "files_to_fix",
                    [],
                )
            ]

            if not files_to_fix:
                raise ValueError(
                    "Debugger did not identify files to fix."
                )

            repair_task = {
                "id": state.get(
                    "current_task_id",
                    0,
                ),
                "title": "Repair failed implementation",
                "description": (
                    "Repair the files identified by "
                    "the debugger."
                ),
                "files_to_modify": files_to_fix,
                "files_to_create": [],
            }

            generated, modified = execute_task(
                state,
                repair_task,
                repair_mode=True,
            )

            generated_files.extend(
                path
                for path in generated
                if path not in generated_files
            )

            modified_files.extend(
                path
                for path in modified
                if path not in modified_files
            )

            return {
                **state,
                "generated_files": generated_files,
                "modified_files": modified_files,
                "debugger_result": {},
                "current_step": "coding_complete",
            }

        for task in plan:
            task_state = {
                **state,
                "current_task_id": task.get("id"),
            }

            generated, modified = execute_task(
                task_state,
                task,
            )

            generated_files.extend(
                path
                for path in generated
                if path not in generated_files
            )

            modified_files.extend(
                path
                for path in modified
                if path not in modified_files
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
            "current_step": "coding_failed",
            "errors": [
                *state.get("errors", []),
                f"Coder failed: {exc}",
            ],
        }