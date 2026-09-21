from backend.graph.state import AgentState
from backend.tools.filesystem import read_file


MAX_FILE_SIZE = 30_000
MAX_TOTAL_CONTEXT = 50_000


def repository_intelligence(
    state: AgentState,
) -> AgentState:

    repository_path = state.get(
        "repository_path"
    )

    if not repository_path:
        return {
            **state,
            "repository_files": [],
            "errors": [
                "No repository path was provided."
            ],
            "current_step": (
                "repository_intelligence_failed"
            ),
        }

    relevant_files = state.get(
        "relevant_files",
        [],
    )

    repository_files = []

    errors = list(
        state.get(
            "errors",
            [],
        )
    )

    total_context_size = 0

    for relative_path in relevant_files:

        # Never send secrets to the LLM.
        if relative_path.lower() == ".env":
            continue

        # Stop when the total repository
        # context becomes too large.
        if total_context_size >= MAX_TOTAL_CONTEXT:
            break

        try:

            content = read_file(
                repository_path,
                relative_path,
            )

            if len(content) > MAX_FILE_SIZE:

                content = (
                    content[:MAX_FILE_SIZE]
                    + "\n\n[FILE TRUNCATED]"
                )

            remaining_space = (
                MAX_TOTAL_CONTEXT
                - total_context_size
            )

            if len(content) > remaining_space:

                content = (
                    content[:remaining_space]
                    + "\n\n[FILE TRUNCATED]"
                )

            repository_files.append(
                {
                    "path": relative_path,
                    "content": content,
                }
            )

            total_context_size += len(
                content
            )

        except Exception as exc:

            errors.append(
                f"{relative_path}: {exc}"
            )

    return {
        **state,
        "repository_files": repository_files,
        "errors": errors,
        "current_step": (
            "repository_intelligence_complete"
        ),
    }