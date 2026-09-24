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


class ReviewIssue(TypedDict, total=False):
    severity: str
    category: str
    file: str
    description: str
    recommendation: str


class ReviewResults(TypedDict, total=False):
    overall_status: str
    summary: str
    issues: list[ReviewIssue]
    strengths: list[str]
    security_concerns: list[str]


class ApprovalResult(TypedDict, total=False):
    approved: bool
    reviewer: str
    comment: str


class AgentState(TypedDict, total=False):
    user_request: str

    repository_path: str

    repository_summary: str
    relevant_files: list[str]

    repository_files: list[RepositoryFile]

    repository_architecture: dict
    architecture_summary: str

    plan: list[PlanTask]
    plan_summary: str

    current_task_id: int
    current_step: str

    generated_files: list[str]
    modified_files: list[str]

    test_results: TestResults

    debugger_result: DebuggerResult
    debug_retry_count: int

    review_results: ReviewResults

    approval_result: ApprovalResult
    approval_required: bool

    errors: list[str]

    final_response: str