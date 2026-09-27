import os
import subprocess
import sys
from pathlib import Path


TEST_TIMEOUT_SECONDS = 120


def run_tests(
    repository_path: str,
) -> dict:
    """
    Run the repository test suite safely.

    Tests are executed using the same Python interpreter
    that is running the AI Software Engineer backend.
    """

    root = Path(
        repository_path
    ).resolve()

    if not root.exists():

        return {
            "success": False,
            "return_code": -1,
            "stdout": "",
            "stderr": (
                f"Repository does not exist: "
                f"{repository_path}"
            ),
        }

    if not root.is_dir():

        return {
            "success": False,
            "return_code": -1,
            "stdout": "",
            "stderr": (
                f"Repository path is not a directory: "
                f"{repository_path}"
            ),
        }

    environment = os.environ.copy()

    # Prevent Python from loading stale .pyc files.
    environment[
        "PYTHONDONTWRITEBYTECODE"
    ] = "1"

    # Make the repository itself importable.
    environment[
        "PYTHONPATH"
    ] = str(root)

    try:

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_SECONDS,
        )

        return {
            "success": result.returncode == 0,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    except subprocess.TimeoutExpired as exc:

        stdout = ""

        stderr = (
            "Test execution timed out after "
            f"{TEST_TIMEOUT_SECONDS} seconds."
        )

        if exc.stdout:

            stdout = str(
                exc.stdout
            )

        if exc.stderr:

            stderr += (
                "\n\nPartial stderr:\n"
                + str(exc.stderr)
            )

        return {
            "success": False,
            "return_code": -1,
            "stdout": stdout,
            "stderr": stderr,
        }

    except KeyboardInterrupt:

        return {
            "success": False,
            "return_code": -2,
            "stdout": "",
            "stderr": (
                "Test execution was interrupted."
            ),
        }

    except Exception as exc:

        return {
            "success": False,
            "return_code": -1,
            "stdout": "",
            "stderr": str(exc),
        }