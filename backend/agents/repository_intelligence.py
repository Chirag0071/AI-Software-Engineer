from __future__ import annotations

import json
import time
from pathlib import Path

from backend.graph.state import AgentState
from backend.llm import get_groq_client, get_model
from backend.tools.filesystem import read_file


MAX_FILE_SIZE = 10_000
MAX_TOTAL_CONTEXT = 30_000
MAX_LLM_RETRIES = 2
RATE_LIMIT_WAIT_SECONDS = 15

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}

BLOCKED_FILES = {
    ".env",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".go",
    ".rs",
    ".php",
    ".rb",
    ".cs",
    ".html",
    ".css",
    ".sql",
}

CONFIG_FILES = {
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".gitignore",
}

REPOSITORY_INTELLIGENCE_SYSTEM_PROMPT = """
You are the Repository Intelligence Agent in an autonomous software engineering system.

Your job is to understand an existing software repository before implementation planning.

Return ONLY valid JSON matching the provided schema.

Analyze the repository evidence provided to you.

Identify:

1. Project type.
2. Main programming languages.
3. Frameworks and important libraries.
4. Entry points.
5. Source files.
6. Test files.
7. Configuration files.
8. Important architecture components.
9. Relationships between important files.
10. Relevant files for the user's requirement.
11. A concise architecture summary.
12. Useful implementation context for the Planner.

Rules:

- Use only evidence from the repository.
- Do not invent files.
- Do not invent frameworks.
- Do not invent architecture.
- Do not suggest code changes.
- Do not implement anything.
- Do not modify files.
- Never include .env as a relevant file.
- Do not include .git, .venv, __pycache__, node_modules or test caches.
- Keep descriptions concise.
- Relevant files must come from the provided repository file list.
"""


def normalize_path(path: str) -> str:
    if not isinstance(path, str):
        raise ValueError("Repository path must be a string.")

    path = path.strip().replace("\\", "/")

    while "//" in path:
        path = path.replace("//", "/")

    if path.startswith("./"):
        path = path[2:]

    if not path:
        raise ValueError("Repository path cannot be empty.")

    return path


def is_safe_path(path: str) -> bool:
    try:
        path = normalize_path(path)
    except ValueError:
        return False

    path_object = Path(path)

    if path_object.is_absolute():
        return False

    if ".." in path_object.parts:
        return False

    if any(
        part in IGNORED_DIRECTORIES
        for part in path_object.parts
    ):
        return False

    if path_object.name in BLOCKED_FILES:
        return False

    return True


def is_test_file(path: str) -> bool:
    name = Path(path).name.lower()

    return (
        name.startswith("test_")
        or "_test." in name
        or ".test." in name
        or ".spec." in name
    )


def is_source_file(path: str) -> bool:
    return Path(path).suffix.lower() in SOURCE_EXTENSIONS


def is_config_file(path: str) -> bool:
    name = Path(path).name.lower()

    return (
        name in CONFIG_FILES
        or name.endswith(".ini")
        or name.endswith(".cfg")
        or name.endswith(".yaml")
        or name.endswith(".yml")
        or name.endswith(".toml")
        or name.endswith(".json")
    )


def classify_files(files: list[str]) -> dict:
    source_files = []
    test_files = []
    config_files = []
    documentation_files = []
    other_files = []

    for path in files:
        normalized = normalize_path(path)

        if not is_safe_path(normalized):
            continue

        name = Path(normalized).name.lower()

        if is_test_file(normalized):
            test_files.append(normalized)
        elif is_source_file(normalized):
            source_files.append(normalized)
        elif is_config_file(normalized):
            config_files.append(normalized)
        elif (
            name.endswith(".md")
            or name.endswith(".rst")
            or name.endswith(".txt")
        ):
            documentation_files.append(normalized)
        else:
            other_files.append(normalized)

    return {
        "source_files": sorted(set(source_files)),
        "test_files": sorted(set(test_files)),
        "config_files": sorted(set(config_files)),
        "documentation_files": sorted(
            set(documentation_files)
        ),
        "other_files": sorted(set(other_files)),
    }


def read_repository_context(
    state: AgentState,
    files: list[str],
) -> list[dict]:
    repository_path = state.get(
        "repository_path"
    )

    if not repository_path:
        raise ValueError(
            "Repository path is missing."
        )

    context = []
    total_size = 0

    for relative_path in files:
        if total_size >= MAX_TOTAL_CONTEXT:
            break

        try:
            content = read_file(
                repository_path,
                relative_path,
            )
        except Exception:
            continue

        if len(content) > MAX_FILE_SIZE:
            content = (
                content[:MAX_FILE_SIZE]
                + "\n[FILE CONTEXT TRUNCATED]"
            )

        remaining = (
            MAX_TOTAL_CONTEXT - total_size
        )

        if len(content) > remaining:
            content = (
                content[:remaining]
                + "\n[CONTEXT TRUNCATED]"
            )

        context.append(
            {
                "path": relative_path,
                "content": content,
            }
        )

        total_size += len(content)

    return context


def build_repository_snapshot(
    state: AgentState,
) -> tuple[list[str], dict, list[dict]]:
    relevant_files = []

    for path in state.get(
        "relevant_files",
        [],
    ):
        try:
            normalized = normalize_path(path)
        except ValueError:
            continue

        if is_safe_path(normalized):
            relevant_files.append(normalized)

    relevant_files = sorted(
        set(relevant_files)
    )

    classifications = classify_files(
        relevant_files
    )

    priority_files = []

    priority_files.extend(
        classifications["source_files"]
    )

    priority_files.extend(
        classifications["test_files"]
    )

    priority_files.extend(
        classifications["config_files"]
    )

    priority_files.extend(
        classifications["documentation_files"]
    )

    context = read_repository_context(
        state,
        priority_files,
    )

    return (
        relevant_files,
        classifications,
        context,
    )


def build_intelligence_prompt(
    state: AgentState,
    classifications: dict,
    context: list[dict],
) -> str:
    file_context = []

    for item in context:
        file_context.append(
            f"""
FILE: {item["path"]}

{item["content"]}

END FILE: {item["path"]}
"""
        )

    return f"""
USER REQUIREMENT
================

{state.get("user_request", "")}

REPOSITORY SUMMARY
==================

{state.get("repository_summary", "")}

FILE CLASSIFICATION
===================

{json.dumps(classifications, indent=2)}

REPOSITORY CONTENT
==================

{"".join(file_context)}

TASK
====

Analyze the repository and produce structured intelligence.

Focus on information that the Planner needs to safely implement
the user's requirement.

Identify the most relevant existing files for the requirement.

Do not propose implementation changes.
Do not write code.
Do not invent missing components.
"""


def build_intelligence_schema() -> dict:
    return {
        "name": "repository_intelligence",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "project_type": {
                    "type": "string",
                },
                "languages": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "frameworks": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "libraries": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "entry_points": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "source_files": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "test_files": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "configuration_files": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "architecture_components": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                            },
                            "description": {
                                "type": "string",
                            },
                            "files": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                },
                            },
                        },
                        "required": [
                            "name",
                            "description",
                            "files",
                        ],
                        "additionalProperties": False,
                    },
                },
                "file_relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                            },
                            "target": {
                                "type": "string",
                            },
                            "relationship": {
                                "type": "string",
                            },
                        },
                        "required": [
                            "source",
                            "target",
                            "relationship",
                        ],
                        "additionalProperties": False,
                    },
                },
                "relevant_files": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "architecture_summary": {
                    "type": "string",
                },
                "implementation_context": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
            },
            "required": [
                "project_type",
                "languages",
                "frameworks",
                "libraries",
                "entry_points",
                "source_files",
                "test_files",
                "configuration_files",
                "architecture_components",
                "file_relationships",
                "relevant_files",
                "architecture_summary",
                "implementation_context",
            ],
            "additionalProperties": False,
        },
    }


def call_intelligence_llm(
    prompt: str,
) -> dict:
    client = get_groq_client()

    response = client.chat.completions.create(
        model=get_model(),
        messages=[
            {
                "role": "system",
                "content": (
                    REPOSITORY_INTELLIGENCE_SYSTEM_PROMPT
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
        reasoning_effort="low",
        max_tokens=10_000,
        response_format={
            "type": "json_schema",
            "json_schema": build_intelligence_schema(),
        },
    )

    if not response.choices:
        raise ValueError(
            "Repository Intelligence received no response."
        )

    content = (
        response.choices[0]
        .message
        .content
    )

    if not content:
        raise ValueError(
            "Repository Intelligence received an empty response."
        )

    result = json.loads(content)

    if not isinstance(result, dict):
        raise ValueError(
            "Repository Intelligence response must be an object."
        )

    return result


def is_rate_limit_error(
    error: Exception,
) -> bool:
    message = str(error).lower()

    return any(
        value in message
        for value in (
            "rate limit",
            "rate_limit",
            "too many requests",
            "429",
            "tokens per minute",
            "tpm",
        )
    )


def validate_intelligence(
    data: dict,
    available_files: set[str],
) -> dict:
    if not isinstance(data, dict):
        raise ValueError(
            "Repository Intelligence response must be an object."
        )

    list_fields = (
        "languages",
        "frameworks",
        "libraries",
        "entry_points",
        "source_files",
        "test_files",
        "configuration_files",
        "relevant_files",
        "implementation_context",
    )

    for field in list_fields:
        if not isinstance(
            data.get(field),
            list,
        ):
            raise ValueError(
                f"Repository Intelligence field "
                f"{field} must be a list."
            )

    architecture_summary = data.get(
        "architecture_summary"
    )

    if not isinstance(
        architecture_summary,
        str,
    ) or not architecture_summary.strip():
        raise ValueError(
            "Repository Intelligence did not provide "
            "an architecture summary."
        )

    validated_relevant_files = []

    for path in data.get(
        "relevant_files",
        [],
    ):
        normalized = normalize_path(path)

        if not is_safe_path(normalized):
            raise ValueError(
                f"Unsafe relevant file: {normalized}"
            )

        if normalized not in available_files:
            raise ValueError(
                "Repository Intelligence identified a "
                f"non-existing file: {normalized}"
            )

        if normalized not in validated_relevant_files:
            validated_relevant_files.append(
                normalized
            )

    if not validated_relevant_files:
        raise ValueError(
            "Repository Intelligence did not identify "
            "any relevant files."
        )

    for field in (
        "source_files",
        "test_files",
        "configuration_files",
        "entry_points",
    ):
        validated = []

        for path in data.get(field, []):
            try:
                normalized = normalize_path(path)
            except ValueError:
                continue

            if (
                normalized in available_files
                and normalized not in validated
            ):
                validated.append(normalized)

        data[field] = validated

    validated_components = []

    for component in data.get(
        "architecture_components",
        [],
    ):
        if not isinstance(
            component,
            dict,
        ):
            continue

        files = []

        for path in component.get(
            "files",
            [],
        ):
            try:
                normalized = normalize_path(path)
            except ValueError:
                continue

            if (
                normalized in available_files
                and normalized not in files
            ):
                files.append(normalized)

        validated_components.append(
            {
                "name": str(
                    component.get(
                        "name",
                        "",
                    )
                ),
                "description": str(
                    component.get(
                        "description",
                        "",
                    )
                ),
                "files": files,
            }
        )

    data["architecture_components"] = (
        validated_components
    )

    validated_relationships = []

    for relationship in data.get(
        "file_relationships",
        [],
    ):
        if not isinstance(
            relationship,
            dict,
        ):
            continue

        source = normalize_path(
            relationship.get(
                "source",
                "",
            )
        )

        target = normalize_path(
            relationship.get(
                "target",
                "",
            )
        )

        if (
            source not in available_files
            or target not in available_files
        ):
            continue

        validated_relationships.append(
            {
                "source": source,
                "target": target,
                "relationship": str(
                    relationship.get(
                        "relationship",
                        "",
                    )
                ),
            }
        )

    data["file_relationships"] = (
        validated_relationships
    )

    data["relevant_files"] = (
        validated_relevant_files
    )

    return data


def repository_intelligence(
    state: AgentState,
) -> AgentState:
    if not state.get(
        "repository_path"
    ):
        return {
            **state,
            "current_step": (
                "repository_intelligence_failed"
            ),
            "errors": [
                *state.get(
                    "errors",
                    [],
                ),
                (
                    "Repository Intelligence: "
                    "repository path is missing."
                ),
            ],
        }

    try:
        (
            available_files,
            classifications,
            context,
        ) = build_repository_snapshot(
            state
        )

        if not available_files:
            raise ValueError(
                "Repository contains no analyzable files."
            )

        prompt = build_intelligence_prompt(
            state,
            classifications,
            context,
        )

        last_error = None

        for attempt in range(
            1,
            MAX_LLM_RETRIES + 1,
        ):
            try:
                response = call_intelligence_llm(
                    prompt
                )

                intelligence = validate_intelligence(
                    response,
                    set(available_files),
                )

                architecture = {
                    "project_type": intelligence[
                        "project_type"
                    ],
                    "languages": intelligence[
                        "languages"
                    ],
                    "frameworks": intelligence[
                        "frameworks"
                    ],
                    "libraries": intelligence[
                        "libraries"
                    ],
                    "entry_points": intelligence[
                        "entry_points"
                    ],
                    "source_files": intelligence[
                        "source_files"
                    ],
                    "test_files": intelligence[
                        "test_files"
                    ],
                    "configuration_files": intelligence[
                        "configuration_files"
                    ],
                    "architecture_components": (
                        intelligence[
                            "architecture_components"
                        ]
                    ),
                    "file_relationships": intelligence[
                        "file_relationships"
                    ],
                }

                retrieved_context = [
                    {
                        "path": item["path"],
                        "content": item["content"],
                    }
                    for item in context
                    if item["path"]
                    in intelligence["relevant_files"]
                ]

                return {
                    **state,
                    "repository_files": [
                        {
                            "path": item["path"],
                            "content": item["content"],
                        }
                        for item in context
                    ],
                    "repository_architecture": architecture,
                    "architecture_summary": (
                        intelligence[
                            "architecture_summary"
                        ]
                    ),
                    "retrieved_context": (
                        retrieved_context
                    ),
                    "relevant_files": (
                        intelligence[
                            "relevant_files"
                        ]
                    ),
                    "current_step": (
                        "repository_intelligence_complete"
                    ),
                }

            except Exception as exc:
                last_error = exc

                if attempt >= MAX_LLM_RETRIES:
                    break

                if is_rate_limit_error(exc):
                    time.sleep(
                        RATE_LIMIT_WAIT_SECONDS
                        * attempt
                    )
                else:
                    time.sleep(2)

        raise RuntimeError(
            "Repository Intelligence failed: "
            f"{last_error}"
        )

    except Exception as exc:
        return {
            **state,
            "current_step": (
                "repository_intelligence_failed"
            ),
            "errors": [
                *state.get(
                    "errors",
                    [],
                ),
                str(exc),
            ],
        }