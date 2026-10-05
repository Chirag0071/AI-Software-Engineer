"""
FastAPI entry point for the Multi-Agent AI Software Engineer.

Provides:
- Health check
- Autonomous software engineering workflow
- Google OAuth development endpoints
- JWT authentication
- Admin protected endpoint
- Persistent run status storage
- Human approval/rejection
- GitHub Pull Request creation after approval
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

from backend.auth.jwt import (
    create_access_token,
    verify_token,
)
from backend.github.client import GitHubClient
from backend.github.pr_service import PullRequestService
from backend.graph.state import AgentState
from backend.graph.workflow import build_workflow
from backend.utils.health import health_check


app = FastAPI(
    title="AI Software Engineer",
    version="1.0.0",
    description=(
        "Multi-Agent AI Software Engineering System"
    ),
)

workflow = build_workflow()


# ---------------------------------------------------------------------------
# Persistent run storage
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RUN_STORE_FILE = (
    PROJECT_ROOT / "run_store.json"
)


def load_run_store() -> dict[str, AgentState]:
    """
    Load persisted run states from disk.

    If the file does not exist or contains invalid JSON,
    return an empty store.
    """

    if not RUN_STORE_FILE.exists():
        return {}

    try:
        raw_data = RUN_STORE_FILE.read_text(
            encoding="utf-8"
        )

        if not raw_data.strip():
            return {}

        data = json.loads(
            raw_data
        )

        if not isinstance(
            data,
            dict,
        ):
            return {}

        return data

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {}


def save_run_store() -> None:
    """
    Persist all current run states to disk.

    A temporary file is used so that an interrupted
    write does not normally destroy the existing store.
    """

    temporary_file = RUN_STORE_FILE.with_suffix(
        ".tmp"
    )

    try:
        temporary_file.write_text(
            json.dumps(
                RUN_STORE,
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )

        temporary_file.replace(
            RUN_STORE_FILE
        )

    except OSError as exc:
        raise RuntimeError(
            f"Unable to persist run store: {exc}"
        ) from exc


RUN_STORE: dict[str, AgentState] = (
    load_run_store()
)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/google/login"
)


def get_current_user(
    token: str = Depends(
        oauth2_scheme
    ),
) -> dict:
    """
    Decode and validate the JWT access token.
    """

    try:
        payload = verify_token(
            token
        )

        return payload

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Could not validate credentials"
            ),
            headers={
                "WWW-Authenticate": "Bearer"
            },
        ) from exc


def require_role(
    required_role: str,
):
    """
    Create a dependency that requires a specific role.
    """

    def role_checker(
        user: dict = Depends(
            get_current_user
        ),
    ) -> dict:
        role = user.get(
            "role"
        )

        if role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Operation requires role "
                    f"'{required_role}'."
                ),
            )

        return user

    return role_checker


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class TaskRequest(BaseModel):
    """
    Request body for starting an autonomous
    software engineering task.
    """

    requirement: str = Field(
        ...,
        min_length=1,
        description=(
            "Natural-language software requirement."
        ),
    )

    repository_path: str = Field(
        ...,
        min_length=1,
        description=(
            "Local path of the repository to modify."
        ),
    )


class ApprovalRequest(BaseModel):
    """
    Human approval request.
    """

    reviewer: str = ""

    comment: str = ""


class RejectionRequest(BaseModel):
    """
    Human rejection request.
    """

    reviewer: str = ""

    comment: str = ""


# ---------------------------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------------------------


@app.get("/")
def root():
    return {
        "project": (
            "Multi-Agent AI Software "
            "Engineering System"
        ),
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health")
def health():
    return health_check()


# ---------------------------------------------------------------------------
# Google OAuth development endpoints
# ---------------------------------------------------------------------------


@app.get("/auth/google/login")
def google_login():
    return {
        "message": (
            "Redirect to Google OAuth endpoint."
        ),
        "auth_url": (
            "https://accounts.google.com/"
            "o/oauth2/v2/auth"
            "?client_id=YOUR_CLIENT_ID"
            "&redirect_uri=YOUR_REDIRECT_URI"
            "&response_type=code"
            "&scope=openid%20email"
        ),
    }


@app.get("/auth/google/callback")
def google_callback(
    code: str,
):
    if not code.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Authorization code is required."
            ),
        )

    user_info = {
        "sub": "google-oauth-user-123",
        "email": "user@example.com",
        "role": "admin",
    }

    token = create_access_token(
        user_info
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }


@app.get("/protected")
def protected_route(
    user: dict = Depends(
        require_role("admin")
    ),
):
    return {
        "message": (
            f"Hello, {user.get('email')}. "
            "You have access to protected "
            "resources."
        ),
        "user": user,
    }


# ---------------------------------------------------------------------------
# Autonomous engineering workflow
# ---------------------------------------------------------------------------


@app.post("/run")
def run_agent(
    request: TaskRequest,
):
    """
    Start the autonomous software engineering workflow.

    Request:

    {
        "requirement": "...",
        "repository_path": "..."
    }
    """

    requirement = request.requirement.strip()

    repository_path = (
        request.repository_path.strip()
    )

    if not requirement:
        raise HTTPException(
            status_code=400,
            detail="Requirement is required.",
        )

    if not repository_path:
        raise HTTPException(
            status_code=400,
            detail=(
                "Repository path is required."
            ),
        )

    run_id = str(
        uuid4()
    )

    initial_state: AgentState = {
        "user_request": requirement,
        "repository_path": repository_path,

        "repository_summary": "",
        "relevant_files": [],
        "repository_files": [],

        "repository_architecture": {},
        "architecture_summary": "",

        "plan": [],
        "plan_summary": "",
        "current_task_id": 0,

        "current_step": "starting",

        "generated_files": [],
        "modified_files": [],

        "test_results": {},

        "debugger_result": {},
        "debug_retry_count": 0,

        "review_results": {},

        "approval_result": {},
        "approval_required": False,

        "github_result": {},

        "errors": [],
        "final_response": "",
    }

    try:
        result = workflow.invoke(
            initial_state
        )

        RUN_STORE[run_id] = result

        # Persist immediately so the run survives
        # a FastAPI restart.
        save_run_store()

        current_step = result.get(
            "current_step",
            "unknown",
        )

        test_results = result.get(
            "test_results",
            {},
        )

        tests_passed = test_results.get(
            "success",
            False,
        )

        review_results = result.get(
            "review_results",
            {},
        )

        review_status = review_results.get(
            "overall_status"
        )

        approval_required = result.get(
            "approval_required",
            False,
        )

        approval_result = result.get(
            "approval_result",
            {},
        )

        # ---------------------------------------------------------------
        # Determine API response status
        # ---------------------------------------------------------------

        if current_step == (
            "waiting_for_human_approval"
        ):
            response_status = (
                "waiting_for_approval"
            )

        elif (
            current_step == "testing_complete"
            and tests_passed
            and not review_results
        ):
            response_status = (
                "testing_complete"
            )

        elif (
            current_step
            == "code_review_complete"
            and tests_passed
            and review_status == "approved"
        ):
            response_status = (
                "review_approved"
            )

        elif current_step == "completed":
            response_status = "completed"

        elif current_step == (
            "github_pr_created"
        ):
            response_status = "completed"

        elif current_step == (
            "github_pr_already_exists"
        ):
            response_status = "completed"

        elif current_step in {
            "approval_blocked",
            "human_approval_rejected",
            "github_pr_failed",
            "code_review_failed",
            "code_review_skipped",
            "debugging_failed",
            "repository_analysis_failed",
            "repository_intelligence_failed",
            "planning_failed",
            "coding_failed",
            "testing_failed",
            "workflow_failed",
        }:
            response_status = "failed"

        else:
            response_status = "failed"

        # ---------------------------------------------------------------
        # Files analyzed
        # ---------------------------------------------------------------

        files_analyzed = [
            file_data["path"]
            for file_data in result.get(
                "repository_files",
                [],
            )
            if (
                isinstance(
                    file_data,
                    dict,
                )
                and "path" in file_data
            )
        ]

        return {
            "run_id": run_id,

            "status": response_status,

            "step": current_step,

            "plan_summary": result.get(
                "plan_summary"
            ),

            "plan": result.get(
                "plan",
                [],
            ),

            "repository_summary": result.get(
                "repository_summary"
            ),

            "architecture_summary": result.get(
                "architecture_summary"
            ),

            "relevant_files": result.get(
                "relevant_files",
                [],
            ),

            "files_analyzed": files_analyzed,

            "generated_files": result.get(
                "generated_files",
                [],
            ),

            "modified_files": result.get(
                "modified_files",
                [],
            ),

            "test_results": test_results,

            "debugger_result": result.get(
                "debugger_result",
                {},
            ),

            "debug_retry_count": result.get(
                "debug_retry_count",
                0,
            ),

            "review_results": review_results,

            "review_status": review_status,

            "approval_required": (
                approval_required
            ),

            "approval_result": (
                approval_result
            ),

            "github_result": result.get(
                "github_result",
                {},
            ),

            "errors": result.get(
                "errors",
                [],
            ),
        }

    except Exception as exc:
        failed_state: AgentState = {
            **initial_state,
            "current_step": (
                "workflow_failed"
            ),
            "errors": [
                f"Workflow error: {exc}"
            ],
        }

        RUN_STORE[run_id] = failed_state

        try:
            save_run_store()
        except Exception:
            pass

        return {
            "run_id": run_id,
            "status": "failed",
            "step": "workflow_failed",

            "plan_summary": None,
            "plan": [],

            "repository_summary": None,
            "architecture_summary": None,

            "relevant_files": [],
            "generated_files": [],
            "modified_files": [],

            "test_results": {},
            "debugger_result": {},
            "debug_retry_count": 0,

            "review_results": {},
            "review_status": None,

            "approval_required": False,
            "approval_result": {},

            "github_result": {},

            "errors": [
                f"Workflow error: {exc}"
            ],
        }


# ---------------------------------------------------------------------------
# Run status
# ---------------------------------------------------------------------------


@app.get("/runs/{run_id}")
def get_run(
    run_id: str,
):
    """
    Retrieve the persisted status of a run.
    """

    state = RUN_STORE.get(
        run_id
    )

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Run not found.",
        )

    return {
        "run_id": run_id,

        "step": state.get(
            "current_step",
            "unknown",
        ),

        "approval_required": state.get(
            "approval_required",
            False,
        ),

        "approval_result": state.get(
            "approval_result",
            {},
        ),

        "github_result": state.get(
            "github_result",
            {},
        ),

        "test_results": state.get(
            "test_results",
            {},
        ),

        "review_results": state.get(
            "review_results",
            {},
        ),

        "generated_files": state.get(
            "generated_files",
            [],
        ),

        "modified_files": state.get(
            "modified_files",
            [],
        ),

        "errors": state.get(
            "errors",
            [],
        ),
    }


# ---------------------------------------------------------------------------
# Human approval
# ---------------------------------------------------------------------------


@app.post("/runs/{run_id}/approve")
def approve_run(
    run_id: str,
    request: ApprovalRequest,
):
    """
    Approve a run and create the GitHub Pull Request.

    GitHub operations happen only after explicit approval.
    """

    state = RUN_STORE.get(
        run_id
    )

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Run not found.",
        )

    if state.get(
        "current_step"
    ) != "waiting_for_human_approval":
        raise HTTPException(
            status_code=409,
            detail=(
                "Run is not waiting for "
                "human approval."
            ),
        )

    reviewer = request.reviewer.strip()

    comment = request.comment.strip()

    state["approval_required"] = False

    state["approval_result"] = {
        "approved": True,
        "reviewer": reviewer,
        "comment": comment,
    }

    state["current_step"] = (
        "human_approval_approved"
    )

    try:
        github_client = GitHubClient(
            state["repository_path"]
        )

        pr_service = PullRequestService(
            github_client
        )

        github_result = (
            pr_service.create_pr_from_approved_state(
                state=state,
                run_id=run_id,
                reviewer=reviewer,
                comment=comment,
            )
        )

        state["github_result"] = (
            github_result
        )

        github_status = github_result.get(
            "status"
        )

        # ---------------------------------------------------------------
        # PR successfully created
        # ---------------------------------------------------------------

        if github_status == "created":
            state["current_step"] = (
                "github_pr_created"
            )

        # ---------------------------------------------------------------
        # PR already existed
        # ---------------------------------------------------------------

        elif github_status == "already_exists":
            state["current_step"] = (
                "github_pr_already_exists"
            )

        # ---------------------------------------------------------------
        # GitHub operation failed
        # ---------------------------------------------------------------

        else:
            state["current_step"] = (
                "github_pr_failed"
            )

    except Exception as exc:
        state["github_result"] = {
            "status": "failed",
            "branch": "",
            "commit_sha": "",
            "pr_number": 0,
            "pr_url": "",
            "error": str(exc),
        }

        state["current_step"] = (
            "github_pr_failed"
        )

    RUN_STORE[run_id] = state

    # Persist approval + GitHub result.
    save_run_store()

    github_status = (
        state.get(
            "github_result",
            {},
        ).get(
            "status"
        )
    )

    successful = github_status in {
        "created",
        "already_exists",
    }

    return {
        "run_id": run_id,

        "status": (
            "approved"
            if successful
            else "approval_complete"
        ),

        "step": state["current_step"],

        "approval_result": state.get(
            "approval_result",
            {},
        ),

        "github_result": state.get(
            "github_result",
            {},
        ),
    }


# ---------------------------------------------------------------------------
# Human rejection
# ---------------------------------------------------------------------------


@app.post("/runs/{run_id}/reject")
def reject_run(
    run_id: str,
    request: RejectionRequest,
):
    """
    Reject a run that is waiting for human approval.
    """

    state = RUN_STORE.get(
        run_id
    )

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Run not found.",
        )

    if state.get(
        "current_step"
    ) != "waiting_for_human_approval":
        raise HTTPException(
            status_code=409,
            detail=(
                "Run is not waiting for "
                "human approval."
            ),
        )

    reviewer = request.reviewer.strip()

    comment = request.comment.strip()

    state["approval_required"] = False

    state["approval_result"] = {
        "approved": False,
        "reviewer": reviewer,
        "comment": comment,
    }

    state["current_step"] = (
        "human_approval_rejected"
    )

    RUN_STORE[run_id] = state

    # Persist rejection.
    save_run_store()

    return {
        "run_id": run_id,

        "status": "rejected",

        "step": (
            "human_approval_rejected"
        ),

        "approval_result": (
            state["approval_result"]
        ),
    }


__all__ = [
    "app",
    "RUN_STORE",
    "RUN_STORE_FILE",
    "health_check",
    "get_current_user",
    "require_role",
]