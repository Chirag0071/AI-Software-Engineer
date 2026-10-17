from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

TEST_TIMEOUT_SECONDS = int(os.getenv("TEST_TIMEOUT_SECONDS", "120"))
DOCKER_IMAGE = os.getenv("SANDBOX_DOCKER_IMAGE", "ai-software-engineer-sandbox:latest")


def build_result(
    success: bool,
    return_code: int,
    stdout: str = "",
    stderr: str = "",
    command: list[str] | None = None,
    duration: float = 0.0,
    sandbox: str = "local",
) -> dict:
    return {
        "success": success,
        "return_code": return_code,
        "stdout": stdout,
        "stderr": stderr,
        "command": command or [],
        "duration_seconds": round(duration, 3),
        "sandbox": sandbox,
    }


def validate_test_targets(repository: Path, targets: list[str] | None) -> list[str]:
    """Accept only existing repository-local pytest paths/node IDs."""
    validated = []
    root = repository.resolve()

    for target in targets or []:
        if not isinstance(target, str) or not target.strip():
            continue
        target = target.strip().replace("\\", "/")
        file_part = target.split("::", 1)[0]
        candidate = Path(file_part)

        if candidate.is_absolute() or ".." in candidate.parts or target.startswith("-"):
            raise ValueError(f"Unsafe pytest target: {target}")

        resolved = (root / candidate).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Pytest target is outside the repository: {target}") from exc

        if not resolved.is_file():
            raise ValueError(f"Pytest target does not exist: {target}")
        if resolved.suffix != ".py":
            raise ValueError(f"Pytest target must refer to a Python test file: {target}")

        if target not in validated:
            validated.append(target)

    return validated


def run_tests(repository_path: str, sandbox: str | None = None, test_targets: list[str] | None = None) -> dict:
    root = Path(repository_path).resolve()
    if not root.exists() or not root.is_dir():
        return build_result(False, -1, stderr=f"Invalid repository path: {repository_path}")

    mode = (sandbox or os.getenv("EXECUTION_MODE", "local")).strip().lower()
    if mode not in {"local", "docker"}:
        return build_result(False, -1, stderr=f"Unsupported execution mode: {mode}")

    try:
        targets = validate_test_targets(root, test_targets)
    except ValueError as exc:
        return build_result(False, -1, stderr=str(exc), sandbox=mode)

    if mode == "docker":
        if not shutil.which("docker"):
            return build_result(False, -1, stderr="Docker mode requested, but Docker is not installed or not on PATH.", sandbox="docker")
        return run_docker(root, targets)

    return run_local(root, targets)


def run_local(root: Path, test_targets: list[str] | None = None) -> dict:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(root)
    command = [sys.executable, "-m", "pytest", "-q", *(test_targets or [])]
    started = time.perf_counter()

    try:
        result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True, timeout=TEST_TIMEOUT_SECONDS, check=False)
        return build_result(result.returncode == 0, result.returncode, result.stdout, result.stderr, command, time.perf_counter() - started, "local")
    except subprocess.TimeoutExpired:
        return build_result(False, -1, stderr=f"Test execution timed out after {TEST_TIMEOUT_SECONDS} seconds.", command=command, duration=time.perf_counter() - started, sandbox="local")
    except OSError as exc:
        return build_result(False, -1, stderr=f"Unable to start pytest: {exc}", command=command, duration=time.perf_counter() - started, sandbox="local")


def run_docker(root: Path, test_targets: list[str] | None = None) -> dict:
    command = [
        "docker", "run", "--rm", "--network", "none",
        "--cpus", os.getenv("SANDBOX_CPUS", "1"),
        "--memory", os.getenv("SANDBOX_MEMORY", "512m"),
        "--pids-limit", os.getenv("SANDBOX_PIDS", "128"),
        "-v", f"{root}:/workspace:rw", "-w", "/workspace",
        DOCKER_IMAGE, "python", "-m", "pytest", "-q", *(test_targets or []),
    ]
    started = time.perf_counter()

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=TEST_TIMEOUT_SECONDS + 30, check=False)
        return build_result(result.returncode == 0, result.returncode, result.stdout, result.stderr, command, time.perf_counter() - started, "docker")
    except subprocess.TimeoutExpired:
        return build_result(False, -1, stderr=f"Docker test execution timed out after {TEST_TIMEOUT_SECONDS + 30} seconds.", command=command, duration=time.perf_counter() - started, sandbox="docker")
    except OSError as exc:
        return build_result(False, -1, stderr=f"Unable to start Docker test runner: {exc}", command=command, duration=time.perf_counter() - started, sandbox="docker")
