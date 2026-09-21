from pathlib import Path

from backend.graph.state import AgentState
from backend.tools.filesystem import read_file


MAX_FILE_SIZE = 20_000
MAX_TOTAL_CONTEXT = 30_000


def detect_architecture(
    repository_path: str,
    relevant_files: list[str],
) -> dict:
    """
    Detect the basic architecture of the repository
    without using an additional LLM call.
    """

    normalized_files = {
        path.replace("\\", "/")
        for path in relevant_files
    }

    architecture = {
        "framework": "unknown",
        "entry_point": None,
        "authentication": [],
        "llm": [],
        "agents": [],
        "workflow": [],
        "tools": [],
        "tests": [],
        "important_files": [],
    }

    # ---------------------------------------------------------
    # Detect application entry point
    # ---------------------------------------------------------

    entry_candidates = [
        "backend/main.py",
        "backend/app.py",
        "main.py",
        "app.py",
    ]

    for candidate in entry_candidates:
        if candidate in normalized_files:
            architecture["entry_point"] = candidate
            break

    # ---------------------------------------------------------
    # Categorize repository files
    # ---------------------------------------------------------

    for path in sorted(normalized_files):

        lower_path = path.lower()

        # Authentication
        if (
            "/auth/" in lower_path
            or lower_path.startswith("auth/")
        ):
            architecture["authentication"].append(path)

        # LLM
        if (
            lower_path.endswith("llm.py")
            or "/llm/" in lower_path
        ):
            architecture["llm"].append(path)

        # Agents
        if "/agents/" in lower_path:
            architecture["agents"].append(path)

        # Graph / workflow
        if (
            "/graph/" in lower_path
            or lower_path.endswith("workflow.py")
        ):
            architecture["workflow"].append(path)

        # Tools
        if "/tools/" in lower_path:
            architecture["tools"].append(path)

        # Tests
        if (
            lower_path.startswith("tests/")
            or "/tests/" in lower_path
            or lower_path.startswith("test_")
            or "/test_" in lower_path
            or lower_path.endswith("_test.py")
        ):
            architecture["tests"].append(path)

    # ---------------------------------------------------------
    # Detect framework from source files
    # ---------------------------------------------------------

    files_to_check = []

    if architecture["entry_point"]:
        files_to_check.append(
            architecture["entry_point"]
        )

    files_to_check.extend(
        architecture["agents"][:5]
    )

    for relative_path in files_to_check:

        try:
            content = read_file(
                repository_path,
                relative_path,
            )

            if (
                "from fastapi import" in content
                or "import fastapi" in content
                or "FastAPI(" in content
            ):
                architecture["framework"] = "FastAPI"
                break

        except Exception:
            continue

    # ---------------------------------------------------------
    # Identify important architectural files
    # ---------------------------------------------------------

    preferred_files = [
        architecture["entry_point"],
        "backend/llm.py",
        "backend/graph/workflow.py",
        "backend/graph/state.py",
        "backend/auth/jwt.py",
    ]

    for path in preferred_files:

        if (
            path
            and path in normalized_files
            and path not in architecture["important_files"]
        ):
            architecture["important_files"].append(path)

    return architecture


def build_architecture_summary(
    architecture: dict,
) -> str:
    """
    Convert detected architecture into concise,
    planner-readable text.
    """

    lines = [
        "REPOSITORY ARCHITECTURE",
        "========================",
        "",
        f"Framework: {architecture['framework']}",
        f"Entry point: {architecture['entry_point']}",
        "",
        "Authentication:",
    ]

    if architecture["authentication"]:
        lines.extend(
            f"- {path}"
            for path in architecture["authentication"]
        )
    else:
        lines.append("- None detected")

    lines.extend(
        [
            "",
            "LLM:",
        ]
    )

    if architecture["llm"]:
        lines.extend(
            f"- {path}"
            for path in architecture["llm"]
        )
    else:
        lines.append("- None detected")

    lines.extend(
        [
            "",
            "Agents:",
        ]
    )

    if architecture["agents"]:
        lines.extend(
            f"- {path}"
            for path in architecture["agents"]
        )
    else:
        lines.append("- None detected")

    lines.extend(
        [
            "",
            "Workflow:",
        ]
    )

    if architecture["workflow"]:
        lines.extend(
            f"- {path}"
            for path in architecture["workflow"]
        )
    else:
        lines.append("- None detected")

    lines.extend(
        [
            "",
            "Tools:",
        ]
    )

    if architecture["tools"]:
        lines.extend(
            f"- {path}"
            for path in architecture["tools"]
        )
    else:
        lines.append("- None detected")

    lines.extend(
        [
            "",
            "Tests:",
        ]
    )

    if architecture["tests"]:
        lines.extend(
            f"- {path}"
            for path in architecture["tests"]
        )
    else:
        lines.append("- None detected")

    lines.extend(
        [
            "",
            "Important files:",
        ]
    )

    if architecture["important_files"]:
        lines.extend(
            f"- {path}"
            for path in architecture["important_files"]
        )
    else:
        lines.append("- None detected")

    return "\n".join(lines)


def repository_intelligence(
    state: AgentState,
) -> AgentState:
    """
    Analyze repository structure and collect relevant
    source context for the Planner.
    """

    repository_path = state.get(
        "repository_path"
    )

    if not repository_path:
        return {
            **state,
            "repository_files": [],
            "repository_architecture": {},
            "architecture_summary": "",
            "errors": [
                *state.get("errors", []),
                "No repository path was provided.",
            ],
            "current_step": "repository_intelligence_failed",
        }

    relevant_files = state.get(
        "relevant_files",
        [],
    )

    errors = list(
        state.get("errors", [])
    )

    # ---------------------------------------------------------
    # Detect repository architecture
    # ---------------------------------------------------------

    architecture = detect_architecture(
        repository_path,
        relevant_files,
    )

    architecture_summary = build_architecture_summary(
        architecture
    )

    # ---------------------------------------------------------
    # Prioritize important files
    # ---------------------------------------------------------

    normalized_relevant = [
        path.replace("\\", "/")
        for path in relevant_files
    ]

    prioritized_files = []

    for path in architecture["important_files"]:

        if path in normalized_relevant:
            prioritized_files.append(path)

    for path in normalized_relevant:

        if path not in prioritized_files:
            prioritized_files.append(path)

    # ---------------------------------------------------------
    # Read repository context
    # ---------------------------------------------------------

    repository_files = []
    total_context_size = 0

    for relative_path in prioritized_files:

        if relative_path == ".env":
            continue

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

            total_context_size += len(content)

        except Exception as exc:

            errors.append(
                f"{relative_path}: {exc}"
            )

    return {
        **state,
        "repository_files": repository_files,
        "repository_architecture": architecture,
        "architecture_summary": architecture_summary,
        "errors": errors,
        "current_step": "repository_intelligence_complete",
    }