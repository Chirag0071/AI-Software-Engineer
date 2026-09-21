from backend.graph.state import AgentState
from backend.tools.test_runner import run_tests


MAX_OUTPUT_LENGTH = 20_000


def trim_output(output: str) -> str:
    """
    Prevent extremely large pytest output from entering
    the LangGraph state.
    """

    if not output:
        return ""

    if len(output) <= MAX_OUTPUT_LENGTH:
        return output

    return (
        output[:MAX_OUTPUT_LENGTH]
        + "\n\n[OUTPUT TRUNCATED]"
    )


def run_test_agent(
    state: AgentState,
) -> AgentState:
    """
    Test Agent.

    Runs the repository test suite and stores the
    result in AgentState.

    The function intentionally does not start with
    'test_' so pytest will not mistake this agent
    for a pytest test function.
    """

    repository_path = state.get(
        "repository_path"
    )

    if not repository_path:

        return {
            **state,
            "test_results": {
                "success": False,
                "return_code": -1,
                "stdout": "",
                "stderr": "No repository path provided.",
            },
            "errors": [
                *state.get("errors", []),
                "Test Agent: No repository path provided.",
            ],
            "current_step": "testing_failed",
        }

    try:

        result = run_tests(
            repository_path
        )

        result["stdout"] = trim_output(
            result.get("stdout", "")
        )

        result["stderr"] = trim_output(
            result.get("stderr", "")
        )

        if result.get("success", False):

            return {
                **state,
                "test_results": result,
                "current_step": "testing_complete",
            }

        return {
            **state,
            "test_results": result,
            "current_step": "testing_failed",
        }

    except Exception as exc:

        return {
            **state,
            "test_results": {
                "success": False,
                "return_code": -1,
                "stdout": "",
                "stderr": str(exc),
            },
            "errors": [
                *state.get("errors", []),
                f"Test Agent error: {exc}",
            ],
            "current_step": "testing_failed",
        }