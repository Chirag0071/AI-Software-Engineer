from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


TEST_TIMEOUT_SECONDS = int(
    os.getenv(
        "TEST_TIMEOUT_SECONDS",
        "120",
    )
)

DOCKER_IMAGE = os.getenv(
    "SANDBOX_DOCKER_IMAGE",
    "ai-software-engineer-sandbox:latest",
)


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
        "duration_seconds": round(
            duration,
            3,
        ),
        "sandbox": sandbox,
    }


def run_tests(
    repository_path: str,
    sandbox: str | None = None,
) -> dict:

    root = Path(
        repository_path
    ).resolve()

    if not root.exists() or not root.is_dir():
        return build_result(
            False,
            -1,
            stderr=(
                f"Invalid repository path: "
                f"{repository_path}"
            ),
        )

    mode = (
        sandbox
        or os.getenv(
            "EXECUTION_MODE",
            "local",
        )
    ).lower()

    if (
        mode == "docker"
        and shutil.which("docker")
    ):
        return run_docker(root)

    return run_local(root)


def run_local(
    root: Path,
) -> dict:

    environment = os.environ.copy()

    environment[
        "PYTHONDONTWRITEBYTECODE"
    ] = "1"

    environment[
        "PYTHONPATH"
    ] = str(root)

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
    ]

    started = time.perf_counter()

    try:
        result = subprocess.run(
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_SECONDS,
            check=False,
        )

        return build_result(
            result.returncode == 0,
            result.returncode,
            result.stdout,
            result.stderr,
            command,
            time.perf_counter() - started,
            "local",
        )

    except subprocess.TimeoutExpired:
        return build_result(
            False,
            -1,
            stderr=(
                "Test execution timed out after "
                f"{TEST_TIMEOUT_SECONDS} seconds."
            ),
            command=command,
            duration=(
                time.perf_counter()
                - started
            ),
            sandbox="local",
        )


def run_docker(
    root: Path,
) -> dict:

    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cpus",
        os.getenv(
            "SANDBOX_CPUS",
            "1",
        ),
        "--memory",
        os.getenv(
            "SANDBOX_MEMORY",
            "512m",
        ),
        "--pids-limit",
        os.getenv(
            "SANDBOX_PIDS",
            "128",
        ),
        "-v",
        f"{root}:/workspace:rw",
        "-w",
        "/workspace",
        DOCKER_IMAGE,
        "python",
        "-m",
        "pytest",
        "-q",
    ]

    started = time.perf_counter()

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_SECONDS + 30,
            check=False,
        )

        return build_result(
            result.returncode == 0,
            result.returncode,
            result.stdout,
            result.stderr,
            command,
            time.perf_counter() - started,
            "docker",
        )

    except subprocess.TimeoutExpired:
        return build_result(
            False,
            -1,
            stderr="Docker test execution timed out.",
            command=command,
            duration=(
                time.perf_counter()
                - started
            ),
            sandbox="docker",
        )