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

        role = user.get("role")

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
# Workflow
# ---------------------------------------------------------------------------

workflow = build_workflow()


class TaskRequest(BaseModel):
    requirement: str
    repository_path: str


# ---------------------------------------------------------------------------
# Basic routes
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "project": (
            "Multi-Agent AI Software "
            "Engineering System"
        ),
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return health_check()


# ---------------------------------------------------------------------------
# Autonomous software-engineering workflow
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
                       ↓
                  Repair Coder
                       ↓
                  Test Agent
    """

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

        review_status = result.get(
            "review_status"
        )

        review_results = result.get(
            "review_results",
            {},
        )

        # Support both workflow versions:
        #
        # 1. Existing workflow:
        #       testing_complete
        #
        # 2. Workflow with Code Review:
        #       code_review_complete
        #
        # This prevents the API from breaking if the
        # review stage is temporarily disabled.
        if (
            current_step == "testing_complete"
            and tests_passed
        ):
            response_status = "completed"

        elif (
            current_step == "code_review_complete"
            and tests_passed
            and review_status != "changes_requested"
        ):
            response_status = "completed"

        else:
            response_status = "failed"

        files_analyzed = [
            file_data["path"]
            for file_data in result.get(
                "repository_files",
                [],
            )
            if (
                isinstance(file_data, dict)
                and "path" in file_data
            )
        ]

        return {
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

            "errors": result.get(
                "errors",
                [],
            ),
        }

    except Exception as exc:
        return {
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

            "errors": [
                f"Workflow error: {exc}"
            ],
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

    For the current development stage, the Google exchange is
    simulated so that authentication and RBAC can be tested
    without requiring real Google credentials.
    """

    # The code is intentionally accepted but not exchanged
    # with Google yet. Real Google OAuth integration can replace
    # this section later.

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
    Example protected endpoint requiring the admin role.
    """

    return {
        "message": (
            f"Hello, {user.get('email')}. "
            "You have access to protected resources."
        )
    }
