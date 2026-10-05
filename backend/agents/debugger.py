import json
import time

from backend.graph.state import AgentState
from backend.llm import get_groq_client, get_model
from backend.tools.filesystem import read_file


MAX_FILE_CONTEXT = 8000
MAX_TOTAL_CONTEXT = 24000
MAX_DEBUGGER_RETRIES = 2
RATE_LIMIT_WAIT_SECONDS = 20


DEBUGGER_SYSTEM_PROMPT = """
You are the Debugger Agent in an autonomous software engineering system.

Your job is to diagnose a failed test run and provide a precise repair plan.

You MUST return only valid JSON matching the provided schema.

Rules:

1. Diagnose the actual test failure.
2. Use the test output and repository files as evidence.
3. Never invent files.
4. files_to_fix must contain only existing repository files.
5. Do not suggest modifying .env.
6. Do not suggest modifying .git, .venv, __pycache__, node_modules,
   or .pytest_cache.
7. Do not write code.
8. Do not perform the repair.
9. Give concise, actionable fix instructions.
10. Distinguish the root cause from secondary errors.
11. If the failure is caused by a test, identify the test file.
12. If the failure is caused by implementation code, identify the implementation file.
13. If the failure is caused by configuration or dependency issues, identify the
    relevant existing file.
14. Do not create new files unless the existing repository clearly requires one.
15. Severity must be one of: low, medium, high, critical.
"""


def normalize_path(path: str) -> str:
    if not isinstance(path, str):
        raise ValueError("File path must be a string.")

    path = path.strip().replace("\\", "/")

    while "//" in path:
        path = path.replace("//", "/")

    if path.startswith("./"):
        path = path[2:]

    if not path:
        raise ValueError("File path cannot be empty.")

    return path


def is_safe_path(path: str) -> bool:
    try:
        path = normalize_path(path)
    except ValueError:
        return False

    if path.startswith("/"):
        return False

    parts = path.split("/")

    if ".." in parts:
        return False

    blocked = {
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
    }

    if any(part in blocked for part in parts):
        return False

    if parts[-1] == ".env":
        return False

    return True


def get_repository_files(
    state: AgentState,
) -> list[str]:
    files = []

    for path in state.get(
        "relevant_files",
        [],
    ):
        try:
            normalized = normalize_path(path)
        except ValueError:
            continue

        if is_safe_path(normalized):
            files.append(normalized)

    return sorted(set(files))


def build_repository_context(
    state: AgentState,
) -> str:
    repository_path = state.get(
        "repository_path"
    )

    if not repository_path:
        raise ValueError(
            "Repository path is missing."
        )

    files = get_repository_files(state)

    sections = []
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

        if len(content) > MAX_FILE_CONTEXT:
            content = (
                content[:MAX_FILE_CONTEXT]
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

        sections.append(
            f"FILE: {relative_path}\n"
            f"{content}\n"
            f"END FILE: {relative_path}"
        )

        total_size += len(content)

    return "\n\n".join(sections)


def build_debugger_prompt(
    state: AgentState,
) -> str:
    test_results = state.get(
        "test_results",
        {},
    )

    stdout = test_results.get(
        "stdout",
        "",
    )

    stderr = test_results.get(
        "stderr",
        "",
    )

    command = test_results.get(
        "command",
        [],
    )

    return f"""
DEBUGGING TASK
==============

User requirement:
{state.get("user_request", "")}

Current workflow step:
{state.get("current_step", "")}

Test command:
{json.dumps(command)}

Test return code:
{test_results.get("return_code")}

Tests successful:
{test_results.get("success")}

TEST STDOUT
===========

{stdout}

TEST STDERR
===========

{stderr}

REPOSITORY FILES
================

{build_repository_context(state)}

DEBUGGING REQUIREMENTS
======================

Determine:

1. The root cause.
2. The exact existing files that must be fixed.
3. The specific repair instructions.
4. The severity.

Do not write code.

Do not create files.

Only identify existing files that require modification.
"""


def build_debugger_schema() -> dict:
    return {
        "name": "debugger_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "diagnosis": {
                    "type": "string",
                },
                "errors": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "files_to_fix": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "fix_instructions": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "severity": {
                    "type": "string",
                    "enum": [
                        "low",
                        "medium",
                        "high",
                        "critical",
                    ],
                },
            },
            "required": [
                "diagnosis",
                "errors",
                "files_to_fix",
                "fix_instructions",
                "severity",
            ],
            "additionalProperties": False,
        },
    }


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
            "tokens per minute",
            "429",
            "tpm",
        )
    )


def call_debugger_llm(
    prompt: str,
) -> dict:
    client = get_groq_client()

    response = client.chat.completions.create(
        model=get_model(),
        messages=[
            {
                "role": "system",
                "content": DEBUGGER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
        reasoning_effort="low",
        max_tokens=8000,
        response_format={
            "type": "json_schema",
            "json_schema": build_debugger_schema(),
        },
    )

    if not response.choices:
        raise ValueError(
            "Debugger received no LLM response."
        )

    content = (
        response.choices[0]
        .message
        .content
    )

    if not content:
        raise ValueError(
            "Debugger received an empty response."
        )

    data = json.loads(content)

    if not isinstance(data, dict):
        raise ValueError(
            "Debugger response must be an object."
        )

    return data


def validate_debugger_response(
    data: dict,
    state: AgentState,
) -> dict:
    if not isinstance(data, dict):
        raise ValueError(
            "Debugger response must be an object."
        )

    diagnosis = data.get(
        "diagnosis",
        "",
    )

    errors = data.get(
        "errors",
        [],
    )

    files_to_fix = data.get(
        "files_to_fix",
        [],
    )

    fix_instructions = data.get(
        "fix_instructions",
        [],
    )

    severity = data.get(
        "severity",
        "",
    )

    if not isinstance(
        diagnosis,
        str,
    ) or not diagnosis.strip():
        raise ValueError(
            "Debugger did not provide a diagnosis."
        )

    if not isinstance(
        errors,
        list,
    ):
        raise ValueError(
            "Debugger errors must be a list."
        )

    if not isinstance(
        files_to_fix,
        list,
    ):
        raise ValueError(
            "Debugger files_to_fix must be a list."
        )

    if not isinstance(
        fix_instructions,
        list,
    ):
        raise ValueError(
            "Debugger fix_instructions must be a list."
        )

    allowed_files = set(
        get_repository_files(state)
    )

    validated_files = []

    for path in files_to_fix:
        normalized = normalize_path(path)

        if not is_safe_path(normalized):
            raise ValueError(
                f"Debugger returned unsafe file: {normalized}"
            )

        if normalized not in allowed_files:
            raise ValueError(
                "Debugger identified a file that does not "
                f"exist in the analyzed repository: {normalized}"
            )

        if normalized not in validated_files:
            validated_files.append(
                normalized
            )

    if not validated_files:
        raise ValueError(
            "Debugger did not identify an existing file to fix."
        )

    return {
        "diagnosis": diagnosis.strip(),
        "errors": [
            str(item)
            for item in errors
        ],
        "files_to_fix": validated_files,
        "fix_instructions": [
            str(item)
            for item in fix_instructions
        ],
        "severity": severity,
    }


def debugger_agent(
    state: AgentState,
) -> AgentState:
    test_results = state.get(
        "test_results",
        {},
    )

    if test_results.get(
        "success",
        False,
    ):
        return {
            **state,
            "debugger_result": {},
            "current_step": "debugging_skipped",
        }

    if not state.get(
        "repository_path"
    ):
        return {
            **state,
            "current_step": "debugging_failed",
            "errors": [
                *state.get(
                    "errors",
                    [],
                ),
                "Debugger: repository path is missing.",
            ],
        }

    if not test_results:
        return {
            **state,
            "current_step": "debugging_failed",
            "errors": [
                *state.get(
                    "errors",
                    [],
                ),
                "Debugger: test results are missing.",
            ],
        }

    prompt = build_debugger_prompt(
        state
    )

    last_error = None

    for attempt in range(
        1,
        MAX_DEBUGGER_RETRIES + 1,
    ):
        try:
            response = call_debugger_llm(
                prompt
            )

            result = validate_debugger_response(
                response,
                state,
            )

            return {
                **state,
                "debugger_result": result,
                "current_step": "debugging_complete",
            }

        except Exception as exc:
            last_error = exc

            if attempt >= MAX_DEBUGGER_RETRIES:
                break

            if is_rate_limit_error(exc):
                time.sleep(
                    RATE_LIMIT_WAIT_SECONDS
                    * attempt
                )
            else:
                time.sleep(2)

    return {
        **state,
        "current_step": "debugging_failed",
        "errors": [
            *state.get(
                "errors",
                [],
            ),
            f"Debugger failed: {last_error}",
        ],
    }