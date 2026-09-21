from fastapi import FastAPI
from pydantic import BaseModel

from backend.graph.workflow import build_workflow


app = FastAPI(
    title="AI Software Engineer",
    version="0.1.0",
    description="Multi-Agent AI Software Engineering System",
)


workflow = build_workflow()


class TaskRequest(BaseModel):
    requirement: str
    repository_path: str


@app.get("/")
def root():
    return {
        "project": "Multi-Agent AI Software Engineering System",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "workflow": "ready",
    }


@app.post("/run")
def run_agent(
    request: TaskRequest,
):
    """
    Execute the autonomous software engineering workflow.

    Repository Analyst
            ↓
    Repository Intelligence
            ↓
    Planner
            ↓
          Coder
            ↓
      Coding Success?
        ↙          ↘
      YES          NO
       ↓            ↓
    Test Agent      END
       ↓
    Tests Passed?
      ↙       ↘
    YES        NO
     ↓          ↓
    END      Debugger
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

        # Only a successful test run means the
        # complete workflow succeeded.
        if (
            current_step == "testing_complete"
            and tests_passed
        ):
            status = "completed"
        else:
            status = "failed"

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
            "status": status,

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
            "errors": [
                f"Workflow error: {exc}"
            ],
        }
