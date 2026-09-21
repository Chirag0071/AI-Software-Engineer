import json
import time

from backend.graph.state import AgentState
from backend.agents.planner_models import ImplementationPlan
from backend.llm import get_llm


PLANNER_SYSTEM_PROMPT = """
You are a software engineering planning agent.

Your job is to convert the user's software requirement into
a practical implementation plan for the EXISTING repository.

Return ONLY one valid JSON object.

Required structure:

{
  "summary": "string",
  "tasks": [
    {
      "id": 1,
      "title": "string",
      "description": "string",
      "files_to_modify": [],
      "files_to_create": [],
      "dependencies": [],
      "tests_required": [],
      "security_considerations": []
    }
  ],
  "testing_strategy": [],
  "security_strategy": []
}

IMPORTANT TYPE RULES:

- summary must be a string.
- tasks must be an array.
- testing_strategy must be an array of strings.
- security_strategy must be an array of strings.
- files_to_modify must be an array of strings.
- files_to_create must be an array of strings.
- dependencies must be an array of strings.
- tests_required must be an array of strings.
- security_considerations must be an array of strings.
- Dependency IDs must be strings such as ["1", "2"].
- Never return an integer inside dependencies.
- Never return null for an array field.

REPOSITORY RULES:

1. Inspect the repository architecture before creating tasks.
2. Use ONLY files that actually exist in the repository.
3. Use the detected entry point.
4. If the entry point is backend/main.py, use backend/main.py.
5. NEVER invent backend/app.py when backend/main.py exists.
6. Reuse existing directories and modules.
7. Create a file only when it does not already exist.
8. If backend/auth/ exists, use backend/auth/.
9. If backend/auth/jwt.py exists, modify it instead of creating another JWT module.
10. If backend/auth/dependencies.py exists, modify it instead of creating another authentication dependency module.
11. Do not create duplicate authentication modules.
12. Do not rename existing files.
13. Do not invent existing files.
14. Do not include .env.
15. Do not include secrets or API keys.
16. Do not modify unrelated files.

CRITICAL FILE CONSISTENCY RULE:

If a task description says that a file must be changed,
that file MUST appear in files_to_modify.

For example:

Correct:
{
  "description": "Modify backend/main.py to add an endpoint.",
  "files_to_modify": ["backend/main.py"]
}

Incorrect:
{
  "description": "Modify backend/main.py to add an endpoint.",
  "files_to_modify": []
}

If a task creates a file, it MUST appear in files_to_create.

If a task modifies an existing file, it MUST appear in files_to_modify.

Never describe changes to a file without listing that file.

TASK RULES:

1. Task IDs start at 1.
2. Task IDs must be sequential.
3. Dependencies must reference earlier task IDs.
4. Do not write implementation code.
5. Keep the plan concise.
6. Every file path must match the actual repository.
7. Do not create duplicate functionality.
8. Tests should be planned when behavior changes.
9. Security-sensitive functionality must include security considerations.
10. Split large implementation work into logical tasks.
11. A task may modify multiple related existing files.
12. Do not put the same newly created file in multiple tasks.
13. Do not put the same modification into multiple unrelated tasks.
14. Return valid JSON only.
"""


MAX_PLANNER_CONTEXT = 12000
MAX_RETRIES = 2


def clean_response(content) -> str:
    """Clean the raw LLM response."""

    if content is None:
        return ""

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)

            elif isinstance(item, dict):
                text = item.get("text")

                if text:
                    parts.append(str(text))

        content = "\n".join(parts)

    elif not isinstance(content, str):
        content = str(content)

    content = content.strip()

    if content.startswith("```"):
        lines = content.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        content = "\n".join(lines).strip()

    return content


def extract_json_object(content: str) -> str:
    """Extract JSON from the model response."""

    content = clean_response(content)

    if not content:
        return ""

    if content.startswith("{") and content.endswith("}"):
        return content

    start = content.find("{")
    end = content.rfind("}")

    if start != -1 and end != -1 and end > start:
        return content[start:end + 1]

    return content


def build_repository_context(
    state: AgentState,
) -> str:
    """Build repository context for the Planner."""

    architecture_summary = state.get(
        "architecture_summary",
        "",
    )

    repository_summary = state.get(
        "repository_summary",
        "",
    )

    relevant_files = state.get(
        "relevant_files",
        [],
    )

    repository_files = state.get(
        "repository_files",
        [],
    )

    sections = []

    if architecture_summary:
        sections.append(
            architecture_summary
        )

    if repository_summary:
        sections.append(
            f"""
REPOSITORY SUMMARY
==================

{repository_summary}
"""
        )

    if relevant_files:
        sections.append(
            """
REPOSITORY FILE LIST
====================

"""
            + "\n".join(
                f"- {path.replace(chr(92), '/')}"
                for path in relevant_files
            )
        )

    if repository_files:

        file_sections = []
        total_size = 0

        for file_data in repository_files:

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

            remaining = (
                MAX_PLANNER_CONTEXT
                - total_size
            )

            if remaining <= 0:
                break

            if len(content) > remaining:
                content = (
                    content[:remaining]
                    + "\n\n[PLANNER CONTEXT TRUNCATED]"
                )

            file_sections.append(
                f"""
FILE: {path}

{content}
"""
            )

            total_size += len(content)

        sections.append(
            """
EXISTING SOURCE CONTEXT
=======================

"""
            + "\n".join(file_sections)
        )

    return "\n".join(sections)


def validate_plan(
    plan_data: dict,
) -> ImplementationPlan:
    """Validate the Planner output."""

    if not isinstance(plan_data, dict):
        raise ValueError(
            "Planner response must be a JSON object."
        )

    plan = ImplementationPlan.model_validate(
        plan_data
    )

    return plan


def validate_file_consistency(
    plan: ImplementationPlan,
    relevant_files: list[str],
) -> None:
    """
    Make sure every file mentioned in a task description
    is actually listed in the corresponding file list.

    Also prevent duplicate file creation.
    """

    existing_files = {
        path.replace("\\", "/")
        for path in relevant_files
    }

    created_files = set()

    for task in plan.tasks:

        modify_files = {
            path.replace("\\", "/")
            for path in task.files_to_modify
        }

        create_files = {
            path.replace("\\", "/")
            for path in task.files_to_create
        }

        overlap = (
            modify_files
            & create_files
        )

        if overlap:
            raise ValueError(
                "A file cannot appear in both "
                "files_to_modify and files_to_create: "
                f"{sorted(overlap)}"
            )

        for path in modify_files:

            if path not in existing_files:
                raise ValueError(
                    f"Planner attempted to modify a file "
                    f"that does not exist: {path}"
                )

        for path in create_files:

            if path in existing_files:
                raise ValueError(
                    f"Planner attempted to create a file "
                    f"that already exists: {path}"
                )

            if path in created_files:
                raise ValueError(
                    f"Planner attempted to create the same "
                    f"file more than once: {path}"
                )

            created_files.add(path)


def generate_plan(
    user_request: str,
    repository_context: str,
    relevant_files: list[str],
) -> ImplementationPlan:

    prompt = f"""
USER SOFTWARE REQUIREMENT
=========================

{user_request}

REPOSITORY INFORMATION
======================

{repository_context}

Create a practical implementation plan.

Before returning the JSON, verify:

1. Every modified existing file is listed in files_to_modify.
2. Every new file is listed in files_to_create.
3. No existing file is listed in files_to_create.
4. No file is both modified and created.
5. backend/main.py is used when application endpoints must change.
6. Existing backend/auth modules are reused.
7. Do not invent files.
8. Return ONLY valid JSON.
"""

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            llm = get_llm()

            response = llm.invoke(
                [
                    (
                        "system",
                        PLANNER_SYSTEM_PROMPT,
                    ),
                    (
                        "human",
                        prompt,
                    ),
                ]
            )

            content = extract_json_object(
                response.content
            )

            if not content:
                raise ValueError(
                    "Planner returned an empty response."
                )

            data = json.loads(
                content
            )

            plan = validate_plan(
                data
            )

            validate_file_consistency(
                plan,
                relevant_files,
            )

            return plan

        except Exception as exc:

            last_error = exc

            if attempt >= MAX_RETRIES:
                break

            time.sleep(2)

            prompt = f"""
The previous Planner response was invalid.

Fix the problem and return ONLY valid JSON.

USER REQUIREMENT:
{user_request}

REPOSITORY:
{repository_context}

Remember:

- Every file described as modified must be in files_to_modify.
- Every new file must be in files_to_create.
- Existing files cannot be created.
- Do not invent files.
- Use backend/main.py as the application entry point.
- Reuse backend/auth/jwt.py.
- Reuse backend/auth/dependencies.py.
- Return valid JSON only.
"""

    raise RuntimeError(
        f"Planner failed after {MAX_RETRIES} attempts: "
        f"{last_error}"
    )


def planner_agent(
    state: AgentState,
) -> AgentState:

    user_request = state.get(
        "user_request"
    )

    if not user_request:
        return {
            **state,
            "plan": [],
            "plan_summary": "",
            "errors": [
                *state.get("errors", []),
                "Planner Agent: No user requirement provided.",
            ],
            "current_step": "planning_failed",
        }

    repository_context = build_repository_context(
        state
    )

    relevant_files = state.get(
        "relevant_files",
        [],
    )

    try:

        implementation_plan = generate_plan(
            user_request,
            repository_context,
            relevant_files,
        )

        plan_tasks = [
            task.model_dump()
            for task in implementation_plan.tasks
        ]

        return {
            **state,
            "plan": plan_tasks,
            "plan_summary": implementation_plan.summary,
            "current_step": "planning_complete",
        }

    except Exception as exc:

        return {
            **state,
            "plan": [],
            "plan_summary": "",
            "errors": [
                *state.get("errors", []),
                f"Planner Agent error: {exc}",
            ],
            "current_step": "planning_failed",
        }
