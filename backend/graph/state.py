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


class RepositoryFile(TypedDict):

    path: str
    content: str


class TestResults(TypedDict, total=False):

    success: bool
    return_code: int
    stdout: str
    stderr: str


class DebuggerResult(TypedDict, total=False):

    diagnosis: str
    errors: list[str]
    files_to_fix: list[str]
    fix_instructions: list[str]
    severity: str


class AgentState(TypedDict, total=False):

    # User input
    user_request: str
    repository_path: str

    # Repository analysis
    repository_summary: str
    relevant_files: list[str]
    repository_files: list[RepositoryFile]

    # Planning
    plan: list[PlanTask]
    plan_summary: str

    # Execution
    current_task_id: int
    current_step: str

    # Coder
    generated_files: list[str]
    modified_files: list[str]

    # Testing
    test_results: TestResults

    # Debugging
    debugger_result: DebuggerResult

    # Future agents
    review_results: dict

    # Error handling
    errors: list[str]

    # Final response
    final_response: str