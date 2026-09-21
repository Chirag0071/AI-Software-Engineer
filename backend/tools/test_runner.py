import subprocess
import sys
from pathlib import Path


def run_tests(
    repository_path: str,
) -> dict:

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

    try:

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=300,
        )

        return {
            "success": result.returncode == 0,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    except subprocess.TimeoutExpired:

        return {
            "success": False,
            "return_code": -1,
            "stdout": "",
            "stderr": (
                "Test execution timed out "
                "after 300 seconds."
            ),
        }

    except Exception as exc:

        return {
            "success": False,
            "return_code": -1,
            "stdout": "",
            "stderr": str(exc),
        }