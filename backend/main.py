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
    }


@app.post("/run")
def run_agent(request: TaskRequest):
    initial_state = {
        "user_request": request.requirement,
        "repository_path": request.repository_path,
        "current_step": "starting",
        "errors": [],
    }

    result = workflow.invoke(initial_state)

    return {
        "status": (
            "completed"
            if result.get("current_step") == "planning_complete"
            else "failed"
        ),
        "step": result.get("current_step"),
        "plan_summary": result.get("plan_summary"),
        "plan": result.get("plan", []),
        "repository_summary": result.get("repository_summary"),
        "relevant_files": result.get("relevant_files", []),
        "errors": result.get("errors", []),
    }