import json

from backend.graph.state import AgentState
from backend.agents.planner_models import ImplementationPlan
from backend.llm import get_llm


PLANNER_SYSTEM_PROMPT = """
You are the Planner Agent in an autonomous software engineering system.

Your job is to convert a natural-language software requirement into a
precise implementation plan that another AI agent can execute.

You are NOT the coding agent.

IMPORTANT:
Return ONLY valid JSON.
Do not use markdown.
Do not include ```json.
Do not include explanations outside the JSON.

The JSON MUST have exactly this top-level structure:

{
  "summary": "short implementation summary",
  "tasks": [
    {
      "id": 1,
      "title": "short task title",
      "description": "detailed task description",
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

RULES:

1. Break the requirement into small, ordered technical tasks.
2. Analyze the supplied repository information.
3. Identify existing files that should be modified.
4. Identify new files that should be created.
5. Do not claim that a file exists unless it appears in the repository.
6. Use task IDs starting from 1.
7. Dependencies must contain task IDs as strings.
8. Include tests for relevant tasks.
9. Include security considerations when appropriate.
10. Do not write implementation code.
11. Do not invent unnecessary libraries.
12. Prefer the existing project architecture.
13. Make the plan practical for a Coder Agent to execute.
14. Return valid JSON only.
"""


def planner_agent(state: AgentState) -> AgentState:
    request = state.get("user_request", "").strip()

    if not request:
        return {
            **state,
            "plan": [],
            "errors": ["No user requirement was provided."],
            "current_step": "planning_failed",
        }

    try:
        llm = get_llm()

        repository_summary = state.get(
            "repository_summary",
            "Repository information is not available."
        )

        relevant_files = state.get("relevant_files", [])

        files_text = "\n".join(
            f"- {file}"
            for file in relevant_files
        )

        prompt = f"""
{PLANNER_SYSTEM_PROMPT}

USER REQUIREMENT:
{request}

REPOSITORY SUMMARY:
{repository_summary}

REPOSITORY FILES:
{files_text}

Create the implementation plan now.

Remember:
Return ONLY the JSON object.
"""

        response = llm.invoke(prompt)

        content = response.content

        if isinstance(content, list):
            content = "".join(
                item.get("text", "")
                if isinstance(item, dict)
                else str(item)
                for item in content
            )

        content = content.strip()

        # Remove accidental markdown fences if the model adds them.
        if content.startswith("```json"):
            content = content[7:]

        if content.startswith("```"):
            content = content[3:]

        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        raw_plan = json.loads(content)

        validated_plan = ImplementationPlan.model_validate(raw_plan)

        plan = [
            task.model_dump()
            for task in validated_plan.tasks
        ]

        return {
            **state,
            "plan": plan,
            "plan_summary": validated_plan.summary,
            "current_step": "planning_complete",
            "errors": [],
        }

    except json.JSONDecodeError as exc:
        return {
            **state,
            "plan": [],
            "plan_summary": None,
            "errors": [
                f"Planner returned invalid JSON: {exc}"
            ],
            "current_step": "planning_failed",
        }

    except Exception as exc:
        return {
            **state,
            "plan": [],
            "plan_summary": None,
            "errors": [str(exc)],
            "current_step": "planning_failed",
        }