"""
Shared LangGraph state definitions.
"""

from typing import TypedDict


# ---------------------------------------------------------------------------
# Planner state
# ---------------------------------------------------------------------------

class PlanTask(TypedDict, total=False):
    id: int
    title: str
    description: str
    files_to_modify: list[str]
    files_to_create: list[str]
    dependencies: list[str]
    tests_required: list[str]
    security_considerations: list[str]


# ---------------------------------------------------------------------------
# Repository state
# ---------------------------------------------------------------------------

class RepositoryFile(TypedDict):
    path: str
    content: str


# ---------------------------------------------------------------------------
# Test state
# ---------------------------------------------------------------------------

class TestResults(TypedDict, total=False):
    success: bool
    return_code: int
    stdout: str
    stderr: str


# ---------------------------------------------------------------------------
# Debugger state
# ---------------------------------------------------------------------------

class DebuggerResult(TypedDict, total=False):
    diagnosis: str
    errors: list[str]
    files_to_fix: list[str]
    fix_instructions: list[str]
    severity: str


# ---------------------------------------------------------------------------
# Code review state
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Complete AgentState
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):

    # -----------------------------------------------------------------------
    # User request
    # -----------------------------------------------------------------------

    user_request: str
    repository_path: str

    # -----------------------------------------------------------------------
    # Repository analysis
    # -----------------------------------------------------------------------

    repository_summary: str
    relevant_files: list[str]
    repository_files: list[RepositoryFile]

    repository_architecture: dict
    architecture_summary: str

    # -----------------------------------------------------------------------
    # Planning
    # -----------------------------------------------------------------------

    plan: list[PlanTask]
    plan_summary: str

    # -----------------------------------------------------------------------
    # Current workflow state
    # -----------------------------------------------------------------------

    current_task_id: int
    current_step: str

    # -----------------------------------------------------------------------
    # Code generation
    # -----------------------------------------------------------------------

    generated_files: list[str]
    modified_files: list[str]

    # -----------------------------------------------------------------------
    # Testing
    # -----------------------------------------------------------------------

    test_results: TestResults

    # -----------------------------------------------------------------------
    # Debugging
    # -----------------------------------------------------------------------

    debugger_result: DebuggerResult
    debug_retry_count: int

    # -----------------------------------------------------------------------
    # Code review
    # -----------------------------------------------------------------------

    review_results: ReviewResults

    # -----------------------------------------------------------------------
    # Errors / final response
    # -----------------------------------------------------------------------

    errors: list[str]
    final_response: str
