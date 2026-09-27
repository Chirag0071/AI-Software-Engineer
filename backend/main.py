from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from backend.auth.jwt import (
    create_access_token,
    verify_token,
)
from backend.graph.workflow import build_workflow
from backend.utils.health import health_check


app = FastAPI(
    title="AI Software Engineer",
    version="0.1.0",
    description="Multi-Agent AI Software Engineering System",
)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/google/login"
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> dict:
    """
    Decode and validate the JWT supplied by the client.
    """

    try:
        payload = verify_token(token)

        return payload

    except Exception as exc:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        ) from exc


def require_role(
    required_role: str,
):
    """
    Create a dependency that requires a specific user role.
    """

    def role_checker(
        user: dict = Depends(get_current_user),
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
    Request body for starting a new autonomous
    software-engineering task.
    """

    requirement: str
    repository_path: str


class ApprovalRequest(BaseModel):
    """
    Request body for approving or rejecting a
    workflow waiting for human approval.
    """

    approved: bool

    comment: str = ""


# ---------------------------------------------------------------------------
# Temporary workflow storage
# ---------------------------------------------------------------------------

# This is intentionally an in-memory store for the current development
# version of the project.
#
# Later this should be replaced with PostgreSQL or another persistent
# workflow-state store so that approval requests survive server restarts.
pending_approvals: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    """
    Basic application information.
    """

    return {
        "project": "Multi-Agent AI Software Engineering System",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    """
    Health-check endpoint.
    """

    return health_check()


# ---------------------------------------------------------------------------
# Autonomous Software Engineering Workflow
# ---------------------------------------------------------------------------

@app.post("/run")
def run_agent(
    request: TaskRequest,
):
    """
    Execute the autonomous software-engineering workflow.

    Workflow:

        Repository Analyst
                ↓
        Repository Intelligence
                ↓
              Planner
                ↓
              Coder
                ↓
            Test Agent
                ↓
          Tests Passed?
             ↙      ↘
           YES      NO
            ↓        ↓
       Code Review  Debugger
            ↓        ↓
     Human Approval Repair Coder
            ↓        ↓
           END    Test Agent
    """

    if not request.requirement.strip():

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requirement cannot be empty.",
        )

    if not request.repository_path.strip():

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository path cannot be empty.",
        )

    initial_state = {
        "user_request": request.requirement,
        "repository_path": request.repository_path,
        "current_step": "starting",
        "errors": [],
        "debug_retry_count": 0,
        "generated_files": [],
        "modified_files": [],
    }

    try:

        workflow = build_workflow()

        result = workflow.invoke(
            initial_state
        )

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
        # Create a run ID when human approval is required
        # ---------------------------------------------------------------

        run_id = None

        if current_step == "waiting_for_human_approval":

            run_id = str(
                uuid4()
            )

            pending_approvals[run_id] = {
                **result,
                "run_id": run_id,
            }

            response_status = (
                "waiting_for_approval"
            )

        # ---------------------------------------------------------------
        # Completed state
        # ---------------------------------------------------------------

        elif (
            current_step == "completed"
            and tests_passed
            and review_status == "approved"
            and approval_result.get(
                "approved",
                False,
            )
        ):

            response_status = "completed"

        # ---------------------------------------------------------------
        # Code review approved
        # ---------------------------------------------------------------

        elif (
            current_step == "code_review_complete"
            and tests_passed
            and review_status == "approved"
        ):

            response_status = "review_approved"

        # ---------------------------------------------------------------
        # Testing completed but no review state
        # ---------------------------------------------------------------

        elif (
            current_step == "testing_complete"
            and tests_passed
            and not review_results
        ):

            response_status = "testing_complete"

        # ---------------------------------------------------------------
        # Known failure states
        # ---------------------------------------------------------------

        elif current_step in {
            "approval_blocked",
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

        # ---------------------------------------------------------------
        # Response
        # ---------------------------------------------------------------

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

            "approval_required": approval_required,

            "approval_result": approval_result,

            "errors": result.get(
                "errors",
                [],
            ),
        }

    except Exception as exc:

        return {
            "run_id": None,

            "status": "failed",

            "step": "workflow_failed",

            "plan_summary": None,

            "plan": [],

            "repository_summary": None,

            "architecture_summary": None,

            "relevant_files": [],

            "files_analyzed": [],

            "generated_files": [],

            "modified_files": [],

            "test_results": {},

            "debugger_result": {},

            "debug_retry_count": 0,

            "review_results": {},

            "review_status": None,

            "approval_required": False,

            "approval_result": {},

            "errors": [
                f"Workflow error: {exc}"
            ],
        }


# ---------------------------------------------------------------------------
# Human Approval
# ---------------------------------------------------------------------------

@app.post("/runs/{run_id}/approval")
def approve_run(
    run_id: str,
    request: ApprovalRequest,
    user: dict = Depends(
        require_role("admin")
    ),
):
    """
    Approve or reject a workflow waiting for human approval.

    Only an authenticated admin can make the approval decision.

    Current behavior:

        approved=True
            →
        workflow becomes ready for GitHub PR creation

        approved=False
            →
        workflow is rejected

    The actual GitHub PR agent will be connected in the next stage.
    """

    stored_state = pending_approvals.get(
        run_id
    )

    if stored_state is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Workflow run was not found or "
                "is no longer waiting for approval."
            ),
        )

    if stored_state.get(
        "current_step"
    ) != "waiting_for_human_approval":

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This workflow is not waiting "
                "for human approval."
            ),
        )

    reviewer = str(
        user.get(
            "email",
            user.get(
                "sub",
                "admin",
            ),
        )
    )

    comment = request.comment.strip()

    if request.approved:

        updated_state = {
            **stored_state,
            "approval_required": False,
            "approval_result": {
                "approved": True,
                "reviewer": reviewer,
                "comment": comment,
            },
            "current_step": (
                "approved_for_github_pr"
            ),
        }

        pending_approvals[
            run_id
        ] = updated_state

        return {
            "run_id": run_id,
            "status": "approved",
            "step": "approved_for_github_pr",
            "message": (
                "Human approval received. "
                "The workflow is ready for GitHub PR creation."
            ),
            "approval_result": updated_state[
                "approval_result"
            ],
        }

    updated_state = {
        **stored_state,
        "approval_required": False,
        "approval_result": {
            "approved": False,
            "reviewer": reviewer,
            "comment": comment,
        },
        "current_step": "approval_rejected",
    }

    pending_approvals[
        run_id
    ] = updated_state

    return {
        "run_id": run_id,
        "status": "rejected",
        "step": "approval_rejected",
        "message": (
            "Human approval was rejected. "
            "No GitHub PR should be created."
        ),
        "approval_result": updated_state[
            "approval_result"
        ],
    }


# ---------------------------------------------------------------------------
# View pending approval
# ---------------------------------------------------------------------------

@app.get("/runs/{run_id}/approval")
def get_pending_approval(
    run_id: str,
    user: dict = Depends(
        require_role("admin")
    ),
):
    """
    Return the current approval information for a workflow run.
    """

    _ = user

    stored_state = pending_approvals.get(
        run_id
    )

    if stored_state is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run was not found.",
        )

    return {
        "run_id": run_id,
        "step": stored_state.get(
            "current_step"
        ),
        "approval_required": stored_state.get(
            "approval_required",
            False,
        ),
        "approval_result": stored_state.get(
            "approval_result",
            {},
        ),
        "review_results": stored_state.get(
            "review_results",
            {},
        ),
        "test_results": stored_state.get(
            "test_results",
            {},
        ),
        "generated_files": stored_state.get(
            "generated_files",
            [],
        ),
        "modified_files": stored_state.get(
            "modified_files",
            [],
        ),
    }


# ---------------------------------------------------------------------------
# Google OAuth login
# ---------------------------------------------------------------------------

@app.get("/auth/google/login")
def google_login():
    """
    Start the Google OAuth flow.

    This project currently uses a placeholder authorization URL.
    Real Google credentials can be connected later.
    """

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


# ---------------------------------------------------------------------------
# Google OAuth callback
# ---------------------------------------------------------------------------

@app.get("/auth/google/callback")
def google_callback(
    code: str,
):
    """
    Handle the Google OAuth callback.

    Development version:
    Google exchange is simulated.
    """

    _ = code

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


# ---------------------------------------------------------------------------
# Protected admin route
# ---------------------------------------------------------------------------

@app.get("/protected")
def protected_route(
    user: dict = Depends(
        require_role("admin")
    ),
):
    """
    Example protected endpoint requiring admin role.
    """

    return {
        "message": (
            f"Hello, {user.get('email')}. "
            "You have access to protected resources."
        )
    }