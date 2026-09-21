from pathlib import Path


IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
}

BLOCKED_FILES = {
    ".env",
}


def scan_repository(
    repository_path: str,
) -> list[str]:

    root = Path(
        repository_path
    )

    if not root.exists():

        raise FileNotFoundError(
            f"Repository does not exist: "
            f"{repository_path}"
        )

    files = []

    for path in root.rglob("*"):

        if not path.is_file():
            continue

        if any(
            part in IGNORED_DIRECTORIES
            for part in path.parts
        ):
            continue

        if path.name in BLOCKED_FILES:
            continue

        files.append(
            str(
                path.relative_to(root)
            )
        )

    return sorted(files)