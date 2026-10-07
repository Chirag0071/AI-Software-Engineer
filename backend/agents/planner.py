from __future__ import annotations

import json
import time

from backend.agents.planner_models import ImplementationPlan
from backend.graph.state import AgentState
from backend.llm import get_groq_client, get_model


PLANNER_SYSTEM_PROMPT = """
You are the Planner Agent in an autonomous software engineering system.

Your job is to convert the user's software requirement into a practical,
ordered implementation plan for the EXISTING repository.

You are given repository intelligence, repository files, architecture,
and source context.

Return ONLY valid JSON matching the provided JSON schema.

IMPORTANT:

- The tasks array MUST contain at least one task.
- Never return an empty task list.
- Do not return Markdown.
- Do not return explanations outside the schema.
- Do not write implementation code.
- Use only files that actually exist in the repository.
- Create a file only when it does not already exist.
- Do not invent files.
- Do not rename files.
- Do not include .env.
- Do not include secrets or API keys.

FILE RULES:

1. Existing files that must change belong in files_to_modify.
2. New files belong in files_to_create.
3. Never put an existing file in files_to_create.
4. Never put a file in both files_to_modify and files_to_create.
5. Every file mentioned in a task must be explicitly listed.
6. Reuse existing authentication modules.
7. If backend/main.py exists, use backend/main.py for application endpoints.
8. If backend/auth/jwt.py exists, reuse it.
9. If backend/auth/dependencies.py exists, reuse it.
10. Do not create duplicate authentication modules.

TASK RULES:

1. Task IDs start at 1.
2. Task IDs must be sequential.
3. Dependencies must reference earlier task IDs only.
4. Split the requirement into practical implementation tasks.
5. A requirement that changes behavior MUST contain implementation and test work.
6. Include tests when behavior changes.
7. Include security considerations for security-sensitive changes.
8. Keep tasks concise and implementation-focused.
9. Do not duplicate the same modification across unrelated tasks.
10. Do not create the same file in multiple tasks.
11. Every task must perform meaningful work.
12. If the requirement is small, one task is acceptable.
13. Never return zero tasks.

DEPENDENCY RULE:

Dependencies must contain task IDs as strings.

Example:

["1", "2"]

Never use integer dependency IDs.

FINAL CHECK:

Before returning the plan, verify:

- tasks contains at least one task
- task IDs start at 1
- task IDs are sequential
- dependencies reference only earlier tasks
- existing files are only in files_to_modify
- new files are only in files_to_create
- no file is both modified and created
- tests are included for behavior changes
"""


MAX_PLANNER_CONTEXT = 12000
MAX_RETRIES = 2


def normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def build_repository_context(
    state: AgentState,
) -> str:
    """
    Build compact but structured repository context
    for the Planner.
    """

    sections = []

    repository_summary = state.get(
        "repository_summary",
        "",
    )

    architecture_summary = state.get(
        "architecture_summary",
        "",
    )

    architecture = state.get(
        "repository_architecture",
        {},
    )

    relevant_files = state.get(
        "relevant_files",
        [],
    )

    repository_files = state.get(
        "repository_files",
        [],
    )

    if repository_summary:
        sections.append(
            f"""
REPOSITORY SUMMARY
==================

{repository_summary}
"""
        )

    if architecture:
        sections.append(
            f"""
STRUCTURED REPOSITORY INTELLIGENCE
===================================

{json.dumps(architecture, indent=2)}
"""
        )

    if architecture_summary:
        sections.append(
            f"""
ARCHITECTURE SUMMARY
====================

{architecture_summary}
"""
        )

    if relevant_files:
        normalized_files = sorted(
            {
                normalize_path(path)
                for path in relevant_files
            }
        )

        sections.append(
            """
REPOSITORY FILE LIST
====================

"""
            + "\n".join(
                f"- {path}"
                for path in normalized_files
            )
        )

    if repository_files:
        file_sections = []
        total_size = 0

        for file_data in repository_files:
            if not isinstance(
                file_data,
                dict,
            ):
                continue

            path = normalize_path(
                file_data.get(
                    "path",
                    "",
                )
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

END FILE: {path}
"""
            )

            total_size += len(content)

        if file_sections:
            sections.append(
                """
EXISTING SOURCE CONTEXT
=======================

"""
                + "\n".join(file_sections)
            )

    return "\n".join(sections)


def build_planner_schema() -> dict:
    """
    Strict JSON schema for native structured Planner output.
    """

    return {
        "name": "implementation_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                },
                "tasks": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "integer",
                            },
                            "title": {
                                "type": "string",
                            },
                            "description": {
                                "type": "string",
                            },
                            "files_to_modify": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                },
                            },
                            "files_to_create": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                },
                            },
                            "dependencies": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                },
                            },
                            "tests_required": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                },
                            },
                            "security_considerations": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                },
                            },
                        },
                        "required": [
                            "id",
                            "title",
                            "description",
                            "files_to_modify",
                            "files_to_create",
                            "dependencies",
                            "tests_required",
                            "security_considerations",
                        ],
                        "additionalProperties": False,
                    },
                },
                "testing_strategy": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "security_strategy": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
            },
            "required": [
                "summary",
                "tasks",
                "testing_strategy",
                "security_strategy",
            ],
            "additionalProperties": False,
        },
    }


def validate_file_consistency(
    plan: ImplementationPlan,
    relevant_files: list[str],
) -> None:
    """
    Validate that the Planner did not invent files,
    duplicate files, or create existing files.
    """

    existing_files = {
        normalize_path(path)
        for path in relevant_files
    }

    created_files = set()
    previous_task_ids = set()

    for task in plan.tasks:
        task_id = task.id

        if task_id in previous_task_ids:
            raise ValueError(
                f"Duplicate task ID: {task_id}"
            )

        expected_next_id = len(
            previous_task_ids
        ) + 1

        if task_id != expected_next_id:
            raise ValueError(
                "Task IDs must be sequential "
                "starting from 1."
            )

        previous_task_ids.add(task_id)

        modify_files = {
            normalize_path(path)
            for path in task.files_to_modify
        }

        create_files = {
            normalize_path(path)
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
                    "Planner attempted to modify a "
                    f"file that does not exist: {path}"
                )

        for path in create_files:
            if path in existing_files:
                raise ValueError(
                    "Planner attempted to create a "
                    f"file that already exists: {path}"
                )

            if path in created_files:
                raise ValueError(
                    "Planner attempted to create the "
                    f"same file more than once: {path}"
                )

            created_files.add(path)

        for dependency in task.dependencies:
            if not isinstance(
                dependency,
                str,
            ):
                raise ValueError(
                    f"Task {task_id} has a non-string "
                    "dependency."
                )

            dependency_id = int(dependency)

            if dependency_id >= task_id:
                raise ValueError(
                    f"Task {task_id} has invalid dependency "
                    f"'{dependency}'. Dependencies must "
                    "reference earlier task IDs."
                )

            if dependency_id not in previous_task_ids:
                raise ValueError(
                    f"Task {task_id} has invalid dependency "
                    f"'{dependency}'."
                )


def validate_plan(
    plan_data: dict,
) -> ImplementationPlan:
    """
    Validate the structured Planner response
    using the project's Pydantic models.
    """

    if not isinstance(
        plan_data,
        dict,
    ):
        raise ValueError(
            "Planner response must be a JSON object."
        )

    plan = ImplementationPlan.model_validate(
        plan_data
    )

    if not plan.tasks:
        raise ValueError(
            "Planner returned an empty task list."
        )

    task_ids = [
        task.id
        for task in plan.tasks
    ]

    expected_ids = list(
        range(
            1,
            len(task_ids) + 1,
        )
    )

    if task_ids != expected_ids:
        raise ValueError(
            "Task IDs must be sequential starting from 1."
        )

    return plan


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

CREATE THE IMPLEMENTATION PLAN NOW.

The requirement requires actual repository work.

You MUST return at least one task.

If the requirement is a small change, create one focused
implementation task containing the required source and test
changes.

Before returning the structured response, verify:

1. tasks contains at least one task.
2. Existing files are only placed in files_to_modify.
3. New files are only placed in files_to_create.
4. No existing file is listed in files_to_create.
5. No file is both modified and created.
6. backend/main.py is used when application endpoints change.
7. Existing backend/auth modules are reused.
8. No .env file is included.
9. Dependencies are strings referring to earlier task IDs.
10. Task IDs start at 1 and are sequential.
11. Tests are included when behavior changes.
12. Security considerations are included where appropriate.
13. Every referenced file exists in the repository.
"""

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):
        try:
            client = get_groq_client()

            response = client.chat.completions.create(
                model=get_model(),
                messages=[
                    {
                        "role": "system",
                        "content": PLANNER_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0,
                reasoning_effort="low",
                max_tokens=12000,
                response_format={
                    "type": "json_schema",
                    "json_schema": build_planner_schema(),
                },
            )

            if not response.choices:
                raise ValueError(
                    "Planner received no response choices from Groq."
                )

            content = (
                response.choices[0]
                .message
                .content
            )

            if not content:
                raise ValueError(
                    "Planner returned an empty response."
                )

            plan_data = json.loads(
                content
            )

            plan = validate_plan(
                plan_data
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

            time.sleep(
                2 * attempt
            )

            prompt = f"""
The previous planning attempt failed validation.

You MUST return a complete implementation plan.

The tasks array MUST contain at least ONE task.

USER SOFTWARE REQUIREMENT
=========================

{user_request}

REPOSITORY INFORMATION
======================

{repository_context}

STRICT REQUIREMENTS:

- Return at least one task.
- Use only files from the repository.
- Existing files belong in files_to_modify.
- New files belong in files_to_create.
- Never create an existing file.
- Never modify a nonexistent file.
- Never include .env.
- Use backend/main.py when application endpoints change.
- Reuse existing backend/auth modules.
- Task IDs start at 1.
- Dependencies are strings.
- Dependencies refer only to earlier task IDs.
- Include tests for behavior changes.
- Include security considerations where appropriate.
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
                *state.get(
                    "errors",
                    [],
                ),
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
