from backend.graph.state import AgentState
from backend.tools.repository import scan_repository


def repository_analyst(
    state: AgentState,
) -> AgentState:

    repository_path = state.get(
        "repository_path"
    )

    if not repository_path:
        return {
            **state,
            "repository_summary": (
                "No repository was provided."
            ),
            "relevant_files": [],
            "current_step": (
                "repository_analysis_complete"
            ),
        }

    try:

        files = scan_repository(
            repository_path
        )

        summary = (
            f"Repository contains "
            f"{len(files)} relevant files."
        )

        return {
            **state,
            "repository_summary": summary,
            "relevant_files": files,
            "current_step": (
                "repository_analysis_complete"
            ),
        }

    except Exception as exc:

        return {
            **state,
            "repository_summary": (
                "Repository analysis failed."
            ),
            "relevant_files": [],
            "errors": [
                str(exc)
            ],
            "current_step": (
                "repository_analysis_failed"
            ),
        }