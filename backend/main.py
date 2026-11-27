from __future__ import annotations

import base64
import hmac
import os
import re
import shutil
import subprocess
import tempfile
import threading

from fastapi import Request
from fastapi.responses import JSONResponse

_GITHUB_URL = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+?(\.git)?/?$")
_OPEN_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}


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
    description="Multi-Agent AI Software Engineering System",
)

workflow = build_workflow()


# ---------------------------------------------------------------------------
# Persistent run storage
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_STORE_FILE = PROJECT_ROOT / "run_store.json"


def load_run_store() -> dict[str, AgentState]:
    """
    Load persisted run states from disk.

    If the file does not exist or contains invalid JSON,
    return an empty store.
    """
    if not RUN_STORE_FILE.exists():
        return {}

    try:
        raw_data = RUN_STORE_FILE.read_text(encoding="utf-8")

        if not raw_data.strip():
            return {}

        data = json.loads(raw_data)

        if not isinstance(data, dict):
            return {}

        return data

    except (OSError, json.JSONDecodeError):
        return {}


_STORE_LOCK = threading.RLock()


def save_run_store() -> None:
    """
    Persist all current run states to disk.

    Guarded by a lock: the background run thread and the request
    handlers all save, and they must not interleave writes to the
    same temporary file or iterate the dict while it changes.
    """
    with _STORE_LOCK:
        temporary_file = RUN_STORE_FILE.with_suffix(".tmp")

        try:
            temporary_file.write_text(
                json.dumps(
                    dict(RUN_STORE),
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                ),
                encoding="utf-8",
            )

            temporary_file.replace(RUN_STORE_FILE)

        except OSError as exc:
            raise RuntimeError(
                f"Unable to persist run store: {exc}"
            ) from exc


# Steps that mean "a worker was in the middle of this run". After a
# server restart no worker exists any more, so such runs are marked failed
# instead of showing "running" forever.
_IN_FLIGHT_STEPS = {
    "starting",
    "repository_analysis_complete",
    "repository_intelligence_complete",
    "planning_complete",
    "coding_complete",
    "testing_complete",
    "debugging_complete",
    "debug_retry",
    "review_retry",
}


def _mark_interrupted(store: dict) -> dict:
    for state in store.values():
        if (
            isinstance(state, dict)
            and state.get("current_step") in _IN_FLIGHT_STEPS
        ):
            state["current_step"] = "workflow_failed"
            state["errors"] = [
                *state.get("errors", []),
                "Run was interrupted by a server restart. Start a new run.",
            ]
    return store


RUN_STORE: dict[str, AgentState] = _mark_interrupted(load_run_store())


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
    Decode and validate the JWT access token.
    """
    try:
        payload = verify_token(token)
        return payload

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_role(required_role: str):
    """
    Create a dependency that requires a specific role.
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
        description="Natural-language software requirement.",
    )

    repository_path: str = Field(
        ...,
        min_length=1,
        description="Local path of the repository to modify.",
    )

    max_debug_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of debugging retries.",
    )


class ApprovalRequest(BaseModel):
    """Human approval request."""

    reviewer: str = ""
    comment: str = ""


class RejectionRequest(BaseModel):
    """Human rejection request."""

    reviewer: str = ""
    comment: str = ""


# ---------------------------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "project": "Multi-Agent AI Software Engineering System",
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
        "message": "Redirect to Google OAuth endpoint.",
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
def google_callback(code: str):
    if not code.strip():
        raise HTTPException(
            status_code=400,
            detail="Authorization code is required.",
        )

    user_info = {
        "sub": "google-oauth-user-123",
        "email": "user@example.com",
        "role": "admin",
    }

    token = create_access_token(user_info)

    return {
        "access_token": token,
        "token_type": "bearer",
    }


@app.get("/protected")
def protected_route(
    user: dict = Depends(require_role("admin")),
):
    return {
        "message": (
            f"Hello, {user.get('email')}. "
            "You have access to protected resources."
        ),
        "user": user,
    }


# ---------------------------------------------------------------------------
# Autonomous engineering workflow
# ---------------------------------------------------------------------------

@app.post("/run")
def run_agent(request: TaskRequest):
    """
    Start the autonomous software engineering workflow.

    Request body:
    {
        "requirement": "...",
        "repository_path": "...",
        "max_debug_retries": 3
    }
    """
    requirement = request.requirement.strip()
    repository_path = request.repository_path.strip()

    if not requirement:
        raise HTTPException(
            status_code=400,
            detail="Requirement is required.",
        )

    if not repository_path:
        raise HTTPException(
            status_code=400,
            detail="Repository path is required.",
        )

    run_id = str(uuid4())

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
        "max_debug_retries": request.max_debug_retries,

        "review_results": {},

        "approval_result": {},
        "approval_required": False,

        "github_result": {},

        "errors": [],
        "final_response": "",
    }

    try:
        result = workflow.invoke(initial_state)

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

        if current_step == "waiting_for_human_approval":
            response_status = "waiting_for_approval"

        elif (
            current_step == "testing_complete"
            and tests_passed
            and not review_results
        ):
            response_status = "testing_complete"

        elif (
            current_step == "code_review_complete"
            and tests_passed
            and review_status == "approved"
        ):
            response_status = "review_approved"

        elif current_step in {
            "completed",
            "github_pr_created",
            "github_pr_already_exists",
        }:
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
                isinstance(file_data, dict)
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

            "approval_required": approval_required,

            "approval_result": approval_result,

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
            "current_step": "workflow_failed",
            "errors": [f"Workflow error: {exc}"],
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

            "github_result": {},

            "errors": [f"Workflow error: {exc}"],
        }


# ---------------------------------------------------------------------------
# Run status
# ---------------------------------------------------------------------------

@app.get("/runs/{run_id}")
def get_run(run_id: str):
    """
    Retrieve the persisted status of a run.
    """
    state = RUN_STORE.get(run_id)

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
    state = RUN_STORE.get(run_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Run not found.",
        )

    # "github_pr_failed" is allowed so a transient GitHub/network/token
    # problem can be fixed and the approval retried.
    if state.get("current_step") not in {
        "waiting_for_human_approval",
        "github_pr_failed",
    }:
        raise HTTPException(
            status_code=409,
            detail="Run is not waiting for human approval.",
        )

    reviewer = request.reviewer.strip()
    comment = request.comment.strip()

    state["approval_required"] = False

    state["approval_result"] = {
        "approved": True,
        "reviewer": reviewer,
        "comment": comment,
    }

    state["current_step"] = "human_approval_approved"

    try:
        github_client = GitHubClient(
            state["repository_path"]
        )

        pr_service = PullRequestService(github_client)

        github_result = pr_service.create_pr_from_approved_state(
            state=state,
            run_id=run_id,
            reviewer=reviewer,
            comment=comment,
        )

        state["github_result"] = github_result

        github_status = github_result.get("status")

        # PR successfully created
        if github_status == "created":
            state["current_step"] = "github_pr_created"

        # PR already existed
        elif github_status == "already_exists":
            state["current_step"] = "github_pr_already_exists"

        # GitHub operation failed
        else:
            state["current_step"] = "github_pr_failed"

    except Exception as exc:
        state["github_result"] = {
            "status": "failed",
            "branch": "",
            "commit_sha": "",
            "pr_number": 0,
            "pr_url": "",
            "error": str(exc),
        }

        state["current_step"] = "github_pr_failed"

    RUN_STORE[run_id] = state

    # Persist approval and GitHub result.
    save_run_store()

    github_status = state.get(
        "github_result",
        {},
    ).get("status")

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
    state = RUN_STORE.get(run_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Run not found.",
        )

    if state.get("current_step") != "waiting_for_human_approval":
        raise HTTPException(
            status_code=409,
            detail="Run is not waiting for human approval.",
        )

    reviewer = request.reviewer.strip()
    comment = request.comment.strip()

    state["approval_required"] = False

    state["approval_result"] = {
        "approved": False,
        "reviewer": reviewer,
        "comment": comment,
    }

    state["current_step"] = "human_approval_rejected"

    RUN_STORE[run_id] = state

    # Persist rejection.
    save_run_store()

    return {
        "run_id": run_id,
        "status": "rejected",
        "step": "human_approval_rejected",
        "approval_result": state["approval_result"],
    }


__all__ = [
    "app",
    "RUN_STORE",
    "RUN_STORE_FILE",
    "health_check",
    "get_current_user",
    "require_role",
]

# ---------------------------------------------------------------------------
# Live (background) runs - used by the Streamlit dashboard
# ---------------------------------------------------------------------------

import threading

RUNNING_RUNS: set[str] = set()


def _initial_state(requirement: str, repository_path: str, retries: int) -> AgentState:
    return {
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
        "max_debug_retries": retries,
        "review_results": {},
        "approval_result": {},
        "approval_required": False,
        "github_result": {},
        "errors": [],
        "events": [],
        "final_response": "",
    }


def _execute_run(run_id: str) -> None:
    try:
        for snapshot in workflow.stream(RUN_STORE[run_id], stream_mode="values"):
            RUN_STORE[run_id] = snapshot
            try:
                save_run_store()  # progress survives a restart
            except Exception:
                pass
    except Exception as exc:
        state = dict(RUN_STORE.get(run_id, {}))
        state["current_step"] = "workflow_failed"
        state["errors"] = [*state.get("errors", []), f"Workflow error: {exc}"]
        RUN_STORE[run_id] = state
    finally:
        RUNNING_RUNS.discard(run_id)
        try:
            save_run_store()
        except Exception:
            pass


@app.post("/run/start")
def start_run(request: TaskRequest):
    """Start a run in the background and return its id immediately."""
    requirement = request.requirement.strip()
    repository_value = request.repository_path.strip()

    if not requirement or not repository_value:
        raise HTTPException(
            status_code=400,
            detail="Requirement and repository path are required.",
        )

    run_id = str(uuid4())
    repository = _resolve_repository(repository_value, run_id)

    if not Path(repository).is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Repository path does not exist on the server: {repository}",
        )

    RUN_STORE[run_id] = _initial_state(
        requirement,
        repository,
        request.max_debug_retries,
    )
    RUNNING_RUNS.add(run_id)
    threading.Thread(target=_execute_run, args=(run_id,), daemon=True).start()
    return {"run_id": run_id, "status": "running"}


@app.get("/runs")
def list_runs():
    return [
        {
            "run_id": rid,
            "requirement": st.get("user_request", ""),
            "step": st.get("current_step", "unknown"),
            "running": rid in RUNNING_RUNS,
        }
        for rid, st in reversed(list(RUN_STORE.items()))
    ]


@app.get("/runs/{run_id}/full")
def get_run_full(run_id: str):
    """Full state of a run (file contents omitted) for the dashboard."""
    state = RUN_STORE.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    slim = {k: v for k, v in state.items() if k != "repository_files"}
    slim["files_analyzed"] = [
        f["path"] for f in state.get("repository_files", []) if isinstance(f, dict) and "path" in f
    ]
    return {"run_id": run_id, "running": run_id in RUNNING_RUNS, "state": slim}


# ---------------------------------------------------------------------------
# Deployment helpers: API key, GitHub URL cloning, diff endpoint
# ---------------------------------------------------------------------------

@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """If APP_API_KEY is set, every non-public endpoint needs header X-API-Key."""
    # .strip(): a trailing space/newline pasted into a dashboard field is the
    # most common reason for a "valid" key being rejected.
    expected = os.getenv("APP_API_KEY", "").strip()
    if expected and request.url.path not in _OPEN_PATHS:
        supplied = request.headers.get("x-api-key", "").strip()
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            reason = "missing" if not supplied else "does not match the backend's APP_API_KEY"
            return JSONResponse({"detail": f"Invalid or missing API key ({reason})."}, status_code=401)
    return await call_next(request)


def _resolve_repository(value: str, run_id: str) -> str:
    """Return a local path. A https://github.com/owner/repo URL is cloned first."""
    if not value.startswith("https://"):
        return value
    if not _GITHUB_URL.match(value):
        raise HTTPException(status_code=400, detail="Only https://github.com/<owner>/<repo> URLs are supported.")
    target = Path(tempfile.gettempdir()) / "ai-swe-workspaces" / run_id
    target.parent.mkdir(parents=True, exist_ok=True)

    token = os.getenv("GITHUB_TOKEN", "").strip()
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    # 1) anonymous (works for public repos, and is not broken by a bad token)
    # 2) with the token as a one-off header (needed for private repos)
    attempts: list[list[str]] = [["git", "clone", "--", value, str(target)]]
    if token:
        raw = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        attempts.append(
            ["git", "-c", f"http.extraheader=AUTHORIZATION: basic {raw}",
             "clone", "--", value, str(target)]
        )

    detail = ""
    for command in attempts:
        try:
            subprocess.run(
                command, check=True, capture_output=True, text=True,
                timeout=180, env=environment,
            )
            return str(target)
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr or str(exc)
            if token:
                detail = detail.replace(token, "***")
            shutil.rmtree(target, ignore_errors=True)  # clean partial clone
        except subprocess.TimeoutExpired:
            shutil.rmtree(target, ignore_errors=True)
            raise HTTPException(status_code=400, detail="Could not clone repository: timed out.")

    hint = (
        " (If the repo is private, check that GITHUB_TOKEN is valid and has access.)"
        if token else
        " (If the repo is private, set GITHUB_TOKEN.)"
    )
    raise HTTPException(status_code=400, detail=f"Could not clone repository: {detail.strip()}{hint}")


@app.get("/runs/{run_id}/diff")
def get_run_diff(run_id: str):
    """Unified diff of the run's changes (tracked edits plus new files)."""
    state = RUN_STORE.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    repo = state.get("repository_path", "")
    files = list(
        dict.fromkeys(
            [*state.get("generated_files", []), *state.get("modified_files", [])]
        )
    )
    if not repo or not files:
        return {"diff": "", "error": ""}
    try:
        # -N marks brand-new files as "intent to add" so they appear in the
        # diff. Limited to this run's files (not .pytest_cache and friends).
        subprocess.run(["git", "-C", repo, "add", "-N", "--", *files], capture_output=True, timeout=20)
        out = subprocess.run(["git", "-C", repo, "diff", "HEAD", "--", *files], capture_output=True, text=True, timeout=20)
        return {"diff": out.stdout, "error": out.stderr}
    except Exception as exc:  # noqa: BLE001
        return {"diff": "", "error": str(exc)}