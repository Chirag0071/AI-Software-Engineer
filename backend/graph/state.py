from typing import TypedDict


class PlanTask(TypedDict, total=False):
    id: int
    title: str
    description: str
    files_to_modify: list[str]
    files_to_create: list[str]
    dependencies: list[str]
    tests_required: list[str]
    security_considerations: list[str]


class AgentState(TypedDict, total=False):
    # User input
    user_request: str
    repository_path: str

    # Repository analysis
    repository_summary: str
    relevant_files: list[str]

    # Planning
    plan: list[PlanTask]
    plan_summary: str

    # Execution
    current_task_id: int
    current_step: str

    # Future agents
    generated_files: list[str]
    modified_files: list[str]
    test_results: dict
    review_results: dict

    # Error handling
    errors: list[str]

    # Final response
    final_response: str