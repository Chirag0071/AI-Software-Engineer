import json
import time

from backend.graph.state import AgentState
from backend.agents.planner_models import ImplementationPlan
from backend.llm import get_llm


PLANNER_SYSTEM_PROMPT = """
You are a software engineering planning agent.

Convert the user's software requirement into a practical
implementation plan based on the repository information.

Return ONLY a JSON object.

The JSON must contain:
- summary
- tasks
- testing_strategy
- security_strategy

Each task must contain:
- id
- title
- description
- files_to_modify
- files_to_create
- dependencies
- tests_required
- security_considerations

Rules:
- Task IDs start at 1.
- Task IDs must be sequential.
- Dependencies must reference earlier task IDs.
- Do not write implementation code.
- Do not invent existing files.
- Do not invent unnecessary libraries.
- Never include .env.
- Keep the plan concise and practical.
- Return valid JSON only.
"""


MAX_PLANNER_CONTEXT = 20_000
MAX_RETRIES = 2


def build_repository_context(
    repository_files: list,
) -> str:
    """
    Build a small repository context for the Planner.
    """

    context_parts = []
    current_size = 0

    # Give source files priority.
    priority_extensions = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
    }

    prioritized = []
    normal = []

    for file_data in repository_files:

        if not isinstance(
            file_data,
            dict,
        ):
            continue

        path = file_data.get(
            "path",
            "",
        )

        if not path:
            continue

        if path.lower() == ".env":
            continue

        extension = ""

        if "." in path:
            extension = (
                "."
                + path.rsplit(
                    ".",
                    1
                )[1].lower()
            )

        if extension in priority_extensions:
            prioritized.append(
                file_data
            )
        else:
            normal.append(
                file_data
            )

    ordered_files = (
        prioritized + normal
    )

    for file_data in ordered_files:

        path = file_data.get(
            "path",
            "",
        )

        content = file_data.get(
            "content",
            "",
        )

        # Keep individual files small.
        if len(content) > 8_000:
            content = (
                content[:8_000]
                + "\n[FILE TRUNCATED]"
            )

        file_text = (
            f"FILE: {path}\n"
            f"{content}\n\n"
        )

        if (
            current_size
            + len(file_text)
            > MAX_PLANNER_CONTEXT
        ):
            break

        context_parts.append(
            file_text
        )

        current_size += len(
            file_text
        )

    if not context_parts:

        return (
            "No repository source files "
            "are available."
        )

    return "".join(
        context_parts
    )


def clean_response(
    content,
) -> str:
    """
    Convert the LangChain response into
    a clean JSON string.
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

    # Remove markdown fences if the model
    # accidentally adds them.
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
            :-len("```")
        ]

    return content.strip()


def validate_plan(
    plan: ImplementationPlan,
) -> None:
    """
    Validate the generated implementation plan.
    """

    if not plan.tasks:

        raise ValueError(
            "Planner returned no tasks."
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
            (
                "Task IDs must be sequential "
                "starting from 1."
            )
        )

    valid_ids = {
        str(task_id)
        for task_id in task_ids
    }

    for task in plan.tasks:

        for dependency in (
            task.dependencies
        ):

            if dependency not in valid_ids:

                raise ValueError(
                    (
                        f"Task {task.id} has "
                        f"invalid dependency "
                        f"{dependency}."
                    )
                )

            if int(dependency) >= task.id:

                raise ValueError(
                    (
                        f"Task {task.id} depends "
                        f"on task {dependency}. "
                        "Dependencies must reference "
                        "earlier tasks."
                    )
                )

        if ".env" in task.files_to_modify:

            raise ValueError(
                "Planner cannot modify .env."
            )

        if ".env" in task.files_to_create:

            raise ValueError(
                "Planner cannot create .env."
            )


def generate_plan(
    llm,
    prompt: str,
):
    """
    Ask Groq for a plan.

    Retries once if Groq returns an empty
    or invalid response.
    """

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
                    "Groq returned an empty response."
                )

            raw_plan = json.loads(
                content
            )

            validated_plan = (
                ImplementationPlan.model_validate(
                    raw_plan
                )
            )

            validate_plan(
                validated_plan
            )

            return validated_plan

        except Exception as exc:

            last_error = exc

            if attempt < MAX_RETRIES - 1:

                time.sleep(1)

                # Retry with an even shorter
                # instruction.
                prompt = f"""
{PLANNER_SYSTEM_PROMPT}

USER REQUIREMENT:
{prompt.split("USER REQUIREMENT:", 1)[-1]}

IMPORTANT:
Return a small JSON implementation plan.
Use as few tasks as reasonably necessary.
Return JSON immediately.
"""

    raise last_error


def planner_agent(
    state: AgentState,
) -> AgentState:
    """
    Planner Agent.

    Converts the user requirement and repository
    context into a validated implementation plan.
    """

    request = state.get(
        "user_request",
        "",
    ).strip()

    if not request:

        return {
            **state,
            "plan": [],
            "plan_summary": None,
            "errors": [
                "No user requirement was provided."
            ],
            "current_step": (
                "planning_failed"
            ),
        }

    try:

        llm = get_llm()

        repository_summary = state.get(
            "repository_summary",
            "Repository information unavailable.",
        )

        repository_files = state.get(
            "repository_files",
            [],
        )

        repository_context = (
            build_repository_context(
                repository_files
            )
        )

        prompt = f"""
{PLANNER_SYSTEM_PROMPT}

USER REQUIREMENT:
{request}

REPOSITORY SUMMARY:
{repository_summary}

REPOSITORY CONTEXT:
{repository_context}

Create the implementation plan.

Make the plan concise.

Return ONLY JSON.
"""

        validated_plan = generate_plan(
            llm,
            prompt,
        )

        plan = [
            task.model_dump()
            for task in validated_plan.tasks
        ]

        return {
            **state,
            "plan": plan,
            "plan_summary": (
                validated_plan.summary
            ),
            "current_step": (
                "planning_complete"
            ),
            "errors": [],
        }

    except Exception as exc:

        return {
            **state,
            "plan": [],
            "plan_summary": None,
            "errors": [
                f"Planner error: {exc}"
            ],
            "current_step": (
                "planning_failed"
            ),
        }