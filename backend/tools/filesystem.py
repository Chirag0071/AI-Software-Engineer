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


def get_safe_path(
    repository_path: str,
    relative_path: str,
) -> Path:

    root = Path(
        repository_path
    ).resolve()

    file_path = (
        root / relative_path
    ).resolve()

    try:
        file_path.relative_to(root)

    except ValueError:
        raise ValueError(
            f"File is outside repository: "
            f"{relative_path}"
        )

    relative = file_path.relative_to(
        root
    )

    if any(
        part in IGNORED_DIRECTORIES
        for part in relative.parts
    ):
        raise ValueError(
            f"Access to this path is not allowed: "
            f"{relative_path}"
        )

    if relative.name in BLOCKED_FILES:
        raise ValueError(
            f"Access to this file is not allowed: "
            f"{relative_path}"
        )

    return file_path


def read_file(
    repository_path: str,
    relative_path: str,
) -> str:

    file_path = get_safe_path(
        repository_path,
        relative_path,
    )

    if not file_path.exists():
        raise FileNotFoundError(
            f"File does not exist: "
            f"{relative_path}"
        )

    if not file_path.is_file():
        raise ValueError(
            f"Path is not a file: "
            f"{relative_path}"
        )

    try:
        return file_path.read_text(
            encoding="utf-8"
        )

    except UnicodeDecodeError:
        return file_path.read_text(
            encoding="utf-8",
            errors="replace",
        )


def write_file(
    repository_path: str,
    relative_path: str,
    content: str,
) -> str:

    file_path = get_safe_path(
        repository_path,
        relative_path,
    )

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path.write_text(
        content,
        encoding="utf-8",
    )

    return relative_path