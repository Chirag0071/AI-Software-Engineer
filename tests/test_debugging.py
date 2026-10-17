from pathlib import Path

import pytest

from backend.agents import test_agent
from backend.tools import test_runner


def _result(success, stdout="", stderr="", return_code=0, command=None):
    return {
        "success": success,
        "return_code": return_code,
        "stdout": stdout,
        "stderr": stderr,
        "command": command or ["python", "-m", "pytest", "-q"],
        "duration_seconds": 0.01,
        "sandbox": "local",
    }


def test_extract_failed_pytest_node_ids():
    output = """
================ short test summary info ================
FAILED tests/test_math.py::test_divide - AssertionError
ERROR tests/test_api.py - ImportError
================ 1 failed, 1 error ======================
"""
    assert test_agent.extract_failed_tests(output) == [
        "tests/test_math.py::test_divide",
        "tests/test_api.py",
    ]


def test_collection_error_extracts_file_not_word_collecting():
    output = "ERROR collecting tests/test_api.py - ImportError"
    assert test_agent.extract_failed_tests(output) == ["tests/test_api.py"]


def test_repair_runs_targeted_failing_test_first(monkeypatch):
    calls = []

    def fake_run_tests(repository_path, test_targets=None):
        calls.append(test_targets)
        return _result(
            False,
            stdout="FAILED tests/test_math.py::test_divide - AssertionError",
            return_code=1,
        )

    monkeypatch.setattr(test_agent, "run_tests", fake_run_tests)
    state = {
        "repository_path": ".",
        "debug_retry_count": 1,
        "last_failed_tests": ["tests/test_math.py::test_divide"],
    }

    result = test_agent.run_test_agent(state)

    assert calls == [["tests/test_math.py::test_divide"]]
    assert result["current_step"] == "testing_failed"
    assert result["test_results"]["test_phase"] == "targeted_repair"
    assert result["last_failed_tests"] == ["tests/test_math.py::test_divide"]


def test_successful_targeted_test_is_followed_by_full_regression_suite(monkeypatch):
    calls = []

    def fake_run_tests(repository_path, test_targets=None):
        calls.append(test_targets)
        if test_targets:
            return _result(True, stdout="1 passed in 0.01s", command=["pytest", *test_targets])
        return _result(
            False,
            stdout="FAILED tests/test_other.py::test_regression - AssertionError",
            return_code=1,
        )

    monkeypatch.setattr(test_agent, "run_tests", fake_run_tests)
    state = {
        "repository_path": ".",
        "debug_retry_count": 1,
        "last_failed_tests": ["tests/test_math.py::test_divide"],
    }

    result = test_agent.run_test_agent(state)

    assert calls == [
        ["tests/test_math.py::test_divide"],
        None,
    ]
    assert result["current_step"] == "testing_failed"
    assert result["test_results"]["test_phase"] == "full_regression"
    assert result["test_results"]["targeted_test_results"]["success"] is True
    assert result["last_failed_tests"] == ["tests/test_other.py::test_regression"]


def test_first_run_runs_full_suite_and_records_failure(monkeypatch):
    calls = []

    def fake_run_tests(repository_path, test_targets=None):
        calls.append(test_targets)
        return _result(
            False,
            stdout="FAILED tests/test_math.py::test_divide - AssertionError",
            return_code=1,
        )

    monkeypatch.setattr(test_agent, "run_tests", fake_run_tests)
    result = test_agent.run_test_agent({"repository_path": ".", "debug_retry_count": 0})

    assert calls == [None]
    assert result["test_results"]["test_phase"] == "initial_full_suite"
    assert result["last_failed_tests"] == ["tests/test_math.py::test_divide"]


def test_test_runner_rejects_path_escape(tmp_path):
    outside = tmp_path.parent / "outside_test.py"
    outside.write_text("def test_ok(): pass", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsafe pytest target|outside the repository"):
        test_runner.validate_test_targets(tmp_path, ["../outside_test.py::test_ok"])


def test_test_runner_executes_selected_node_id(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_math.py").write_text(
        "def test_addition():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )

    result = test_runner.run_tests(
        str(tmp_path),
        sandbox="local",
        test_targets=["tests/test_math.py::test_addition"],
    )

    assert result["success"] is True, result
    assert "test_addition" in result["command"][-1]


def test_docker_mode_does_not_silently_fall_back_to_local(tmp_path, monkeypatch):
    monkeypatch.setattr(test_runner.shutil, "which", lambda _: None)

    result = test_runner.run_tests(str(tmp_path), sandbox="docker")

    assert result["success"] is False
    assert result["sandbox"] == "docker"
    assert "Docker mode requested" in result["stderr"]
