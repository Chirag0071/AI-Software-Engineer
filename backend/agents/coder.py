import json
import time

from backend.graph.state import AgentState
from backend.llm import get_llm
from backend.tools.filesystem import (
    read_file,
    write_file,
)


CODER_SYSTEM_PROMPT = """
You are the Coder Agent in an autonomous software engineering system.

Your job is to implement ONE approved task from an implementation plan.

Return ONLY valid JSON.

Required JSON format:

{
  "files": [
    {
      "path": "relative/path",
      "action": "create",
      "content": "complete file content"
    }
  ],
  "summary": "short summary"
}

Rules:

1. Implement ONLY the assigned task.
2. Create ONLY files listed in files_to_create.
3. Modify ONLY files listed in files_to_modify.
4. For "create", return the COMPLETE file.
5. For "modify", return the COMPLETE resulting file.
6. Do not return patches.
7. Do not use markdown.
8. Do not use code fences.
9. Never modify .env.
10. Never expose secrets.
11. Preserve the existing architecture.
12. Do not invent unnecessary dependencies.
13. If no file needs to be changed, return an empty files array.
14. Return valid JSON only.
"""


MAX_FILE_CONTEXT = 12_000
MAX_TOTAL_CONTEXT = 20_000
MAX_RETRIES = 2


def clean_response(content) -> str:
    """
    Convert the LLM response into a clean JSON string.
    """

    if content is None:
        return ""

    if isinstance(content, list):

        parts = []

        for item in content:

            if isinstance(item, dict):

                parts.append(
                    item.get(
                        "text",
                        ""
                    )
                )

            else:

                parts.append(
                    str(item)
                )

        content = "".join(parts)

    content = str(
        content
    ).strip()

    if not content:
        return ""

    if content.startswith("```json"):

        content = content[
            len("```json"):
        ]

    elif content.startswith("```"):

        content = content[
            len("```"):
        ]

    if content.endswith("```"):

        content = content[
            :-len("```")
        ]

    return content.strip()


def read_task_context(
    repository_path: str,
    task: dict,
) -> str:
    """
    Read only files that the current task
    is allowed to modify.
    """

    files_to_modify = task.get(
        "files_to_modify",
        [],
    )

    if not files_to_modify:

        return (
            "No existing files need to be read."
        )

    context_parts = []
    total_size = 0

    for relative_path in files_to_modify:

        if relative_path == ".env":
            continue

        try:

            content = read_file(
                repository_path,
                relative_path,
            )

            if len(content) > MAX_FILE_CONTEXT:

                content = (
                    content[:MAX_FILE_CONTEXT]
                    + "\n[FILE TRUNCATED]"
                )

            file_text = (
                f"===== FILE: {relative_path} =====\n\n"
                f"{content}"
            )

            if (
                total_size
                + len(file_text)
                > MAX_TOTAL_CONTEXT
            ):
                break

            context_parts.append(
                file_text
            )

            total_size += len(
                file_text
            )

        except FileNotFoundError:

            # The file might have been created
            # by an earlier task.
            continue

    if not context_parts:

        return (
            "No existing file contents are available."
        )

    return "\n\n".join(
        context_parts
    )


def validate_generated_files(
    generated_files: list,
    task: dict,
) -> None:
    """
    Validate the Coder response before writing
    anything to the repository.
    """

    if not isinstance(
        generated_files,
        list,
    ):

        raise ValueError(
            "Coder returned an invalid files list."
        )

    allowed_create = set(
        task.get(
            "files_to_create",
            [],
        )
    )

    allowed_modify = set(
        task.get(
            "files_to_modify",
            [],
        )
    )

    for file_data in generated_files:

        if not isinstance(
            file_data,
            dict,
        ):

            raise ValueError(
                "Invalid generated file object."
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

        if not path:

            raise ValueError(
                "Generated file has no path."
            )

        if path == ".env":

            raise ValueError(
                "Coder cannot modify .env."
            )

        if action not in {
            "create",
            "modify",
        }:

            raise ValueError(
                f"Invalid file action: {action}"
            )

        if not isinstance(
            content,
            str,
        ):

            raise ValueError(
                f"Invalid content for {path}"
            )

        if action == "create":

            if path not in allowed_create:

                raise ValueError(
                    (
                        f"Coder attempted to create "
                        f"unauthorized file: {path}"
                    )
                )

        if action == "modify":

            if path not in allowed_modify:

                raise ValueError(
                    (
                        f"Coder attempted to modify "
                        f"unauthorized file: {path}"
                    )
                )


def execute_task(
    repository_path: str,
    task: dict,
) -> tuple[list[str], list[str]]:
    """
    Execute one implementation task.
    """

    task_context = read_task_context(
        repository_path,
        task,
    )

    files_to_create = task.get(
        "files_to_create",
        [],
    )

    files_to_modify = task.get(
        "files_to_modify",
        [],
    )

    tests_required = task.get(
        "tests_required",
        [],
    )

    security_considerations = task.get(
        "security_considerations",
        [],
    )

    prompt = f"""
{CODER_SYSTEM_PROMPT}

TASK ID:
{task.get("id")}

TASK TITLE:
{task.get("title")}

TASK DESCRIPTION:
{task.get("description")}

FILES TO CREATE:
{json.dumps(
    files_to_create,
    indent=2
)}

FILES TO MODIFY:
{json.dumps(
    files_to_modify,
    indent=2
)}

TESTS REQUIRED:
{json.dumps(
    tests_required,
    indent=2
)}

SECURITY CONSIDERATIONS:
{json.dumps(
    security_considerations,
    indent=2
)}

CURRENT FILE CONTENT:

{task_context}

IMPLEMENT THE TASK NOW.

Return ONLY the JSON object.
Do not include explanations.
"""

    llm = get_llm()

    last_error = None

    for attempt in range(
        MAX_RETRIES
    ):

        try:

            response = llm.invoke(
                prompt
            )

            content = clean_response(
                response.content
            )

            if not content:

                raise ValueError(
                    "Coder returned an empty response."
                )

            result = json.loads(
                content
            )

            if not isinstance(
                result,
                dict,
            ):

                raise ValueError(
                    "Coder response must be a JSON object."
                )

            generated_files = result.get(
                "files",
                []
            )

            validate_generated_files(
                generated_files,
                task,
            )

            generated_paths = []
            modified_paths = []

            # Only write files after the complete
            # response has passed validation.
            for file_data in generated_files:

                path = file_data[
                    "path"
                ]

                action = file_data[
                    "action"
                ]

                content = file_data[
                    "content"
                ]

                write_file(
                    repository_path,
                    path,
                    content,
                )

                if action == "create":

                    if path not in generated_paths:

                        generated_paths.append(
                            path
                        )

                else:

                    if path not in modified_paths:

                        modified_paths.append(
                            path
                        )

            return (
                generated_paths,
                modified_paths,
            )

        except Exception as exc:

            last_error = exc

            if attempt < MAX_RETRIES - 1:

                time.sleep(1)

                # Smaller retry prompt.
                prompt = f"""
{CODER_SYSTEM_PROMPT}

TASK:
{task.get("title")}

DESCRIPTION:
{task.get("description")}

FILES TO CREATE:
{json.dumps(files_to_create)}

FILES TO MODIFY:
{json.dumps(files_to_modify)}

Return a valid JSON object now.

The "files" array must contain complete
file contents for files that need to change.

Return ONLY JSON.
"""

    raise last_error


def dependencies_completed(
    task: dict,
    completed_tasks: set,
) -> bool:
    """
    Check whether all dependencies of a task
    have completed.
    """

    dependencies = task.get(
        "dependencies",
        []
    )

    completed = {
        str(task_id)
        for task_id in completed_tasks
    }

    return all(
        str(dependency) in completed
        for dependency in dependencies
    )


def coder_agent(
    state: AgentState,
) -> AgentState:
    """
    Execute all planned tasks sequentially.
    """

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
                    []
                ),
                "No implementation plan available.",
            ],
            "current_step": "coding_failed",
        }

    repository_path = state.get(
        "repository_path"
    )

    if not repository_path:

        return {
            **state,
            "errors": [
                *state.get(
                    "errors",
                    []
                ),
                "No repository path provided.",
            ],
            "current_step": "coding_failed",
        }

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

    completed_tasks = set()

    errors = list(
        state.get(
            "errors",
            []
        )
    )

    try:

        for task in plan:

            task_id = task.get(
                "id"
            )

            if task_id is None:

                raise ValueError(
                    "Task has no ID."
                )

            # Verify dependencies.
            if not dependencies_completed(
                task,
                completed_tasks,
            ):

                raise ValueError(
                    (
                        f"Task {task_id} has "
                        "unfinished dependencies."
                    )
                )

            state = {
                **state,
                "current_task_id": task_id,
                "current_step": (
                    f"coding_task_{task_id}"
                ),
            }

            task_generated, task_modified = (
                execute_task(
                    repository_path,
                    task,
                )
            )

            for path in task_generated:

                if path not in generated_files:

                    generated_files.append(
                        path
                    )

            for path in task_modified:

                if path not in modified_files:

                    modified_files.append(
                        path
                    )

            completed_tasks.add(
                task_id
            )

        return {
            **state,
            "generated_files": generated_files,
            "modified_files": modified_files,
            "current_task_id": None,
            "current_step": "coding_complete",
            "errors": errors,
        }

    except Exception as exc:

        errors.append(
            f"Coder error: {exc}"
        )

        return {
            **state,
            "generated_files": generated_files,
            "modified_files": modified_files,
            "current_task_id": (
                state.get(
                    "current_task_id"
                )
            ),
            "errors": errors,
            "current_step": "coding_failed",
        }