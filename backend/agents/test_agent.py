import re

from backend.graph.state import AgentState
from backend.tools.test_runner import run_tests

MAX_OUTPUT_LENGTH = 20_000
_FAILURE_LINE = re.compile(r"^(?:FAILED|ERROR)\s+(?!collecting\b)([^\s]+)", re.MULTILINE)
_COLLECTION_ERROR = re.compile(r"ERROR collecting\s+([^\s]+)")


def trim_output(output: str) -> str:
    if not output:
        return ""
    if len(output) <= MAX_OUTPUT_LENGTH:
        return output
    return output[:MAX_OUTPUT_LENGTH] + "\n\n[OUTPUT TRUNCATED]"


def extract_failed_tests(*outputs: str) -> list[str]:
    """Extract pytest node IDs from the short test summary and collection errors."""
    failed = []
    for output in outputs:
        for match in (*_FAILURE_LINE.findall(output or ""), *_COLLECTION_ERROR.findall(output or "")):
            target = match.rstrip(":,")
            if target and target not in failed:
                failed.append(target)
    return failed


def is_execution_error(result: dict) -> bool:
    if result.get("return_code", -1) == -1:
        return True
    output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    return any(marker in output for marker in (
        "no module named pytest",
        "no module named 'pytest'",
        "no module named \"pytest\"",
        "unable to start pytest",
        "docker is not installed",
        "unsupported execution mode",
    ))


def normalize_result(result: dict, phase: str) -> dict:
    result = dict(result)
    result["stdout"] = trim_output(result.get("stdout", ""))
    result["stderr"] = trim_output(result.get("stderr", ""))
    result["test_phase"] = phase
    result["failed_tests"] = extract_failed_tests(result["stdout"], result["stderr"])
    result["failure_kind"] = "none" if result.get("success") else ("execution_error" if is_execution_error(result) else "test_failure")
    return result


def run_test_agent(state: AgentState) -> AgentState:
    """Run failed tests first after a repair, then the complete regression suite."""
    repository_path = state.get("repository_path")
    if not repository_path:
        message = "Test Agent: No repository path provided."
        return {
            **state,
            "test_results": {"success": False, "return_code": -1, "stdout": "", "stderr": message, "failure_kind": "execution_error"},
            "errors": [*state.get("errors", []), message],
            "current_step": "testing_failed",
        }

    try:
        retry_count = state.get("debug_retry_count", 0)
        previous_failures = state.get("last_failed_tests", [])

        if retry_count > 0 and previous_failures:
            targeted = normalize_result(run_tests(repository_path, test_targets=previous_failures), "targeted_repair")
            if not targeted["success"]:
                if not targeted["failed_tests"]:
                    targeted["failed_tests"] = list(previous_failures)
                return {
                    **state,
                    "test_results": targeted,
                    "last_failed_tests": targeted["failed_tests"],
                    "current_step": "testing_failed",
                }

            regression = normalize_result(run_tests(repository_path), "full_regression")
            regression["targeted_test_results"] = {
                "success": targeted["success"],
                "return_code": targeted.get("return_code"),
                "failed_tests": targeted.get("failed_tests", []),
                "duration_seconds": targeted.get("duration_seconds", 0),
                "command": targeted.get("command", []),
            }
            regression["targeted_command"] = targeted.get("command", [])
            regression["stdout"] = trim_output(
                "=== TARGETED REPAIR TESTS ===\n"
                + targeted.get("stdout", "")
                + "\n=== FULL REGRESSION SUITE ===\n"
                + regression.get("stdout", "")
            )
            regression["stderr"] = trim_output(
                "=== TARGETED REPAIR TEST STDERR ===\n"
                + targeted.get("stderr", "")
                + "\n=== FULL REGRESSION SUITE STDERR ===\n"
                + regression.get("stderr", "")
            )
            regression["test_phase"] = "full_regression"
            regression["failure_kind"] = "none" if regression.get("success") else ("execution_error" if is_execution_error(regression) else "test_failure")
            regression["failed_tests"] = extract_failed_tests(regression["stdout"], regression["stderr"])
            return {
                **state,
                "test_results": regression,
                "last_failed_tests": regression["failed_tests"],
                "current_step": "testing_complete" if regression["success"] else "testing_failed",
            }

        result = normalize_result(run_tests(repository_path), "initial_full_suite")
        return {
            **state,
            "test_results": result,
            "last_failed_tests": result["failed_tests"],
            "current_step": "testing_complete" if result["success"] else "testing_failed",
        }
    except Exception as exc:
        message = f"Test Agent error: {exc}"
        return {
            **state,
            "test_results": {"success": False, "return_code": -1, "stdout": "", "stderr": str(exc), "failure_kind": "execution_error"},
            "errors": [*state.get("errors", []), message],
            "current_step": "testing_failed",
        }
