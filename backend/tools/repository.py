from pathlib import Path


IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
}


def scan_repository(repository_path: str) -> list[str]:
    """
    Scan a repository and return relevant source files.
    """

    root = Path(repository_path)

    if not root.exists():
        raise FileNotFoundError(
            f"Repository does not exist: {repository_path}"
        )

    files = []

    for path in root.rglob("*"):

        if not path.is_file():
            continue

        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue

        files.append(str(path.relative_to(root)))

    return sorted(files)