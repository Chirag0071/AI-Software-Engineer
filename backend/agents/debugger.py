import json
import time

from backend.graph.state import AgentState
from backend.llm import get_groq_client, get_model


DEBUGGER_SYSTEM_PROMPT = """
You are the Debugger Agent in an autonomous software engineering system.

Your job is to analyze a failed test execution and identify the actual
root cause.

Return ONLY valid JSON.

Required JSON format:

{
    "diagnosis": "short explanation of the root cause",
    "errors": [
        "specific error supported by the test output"
    ],
    "files_to_fix": [
        "existing/relative/path.py"
    ],
    "fix_instructions": [
        "specific instruction for the Coder"
    ],
    "severity": "low"
}

Rules:

1. Analyze the ACTUAL test output.
2. Do not invent errors.
3. Do not invent repository files.
4. files_to_fix MUST contain only files listed in the repository file list.
5. Never use paths that are not present in the repository file list.
6. Never use src/... unless the repository actually contains that path.
7. Never target .env.
8. Never target .git.
9. Never target .venv.
10. Do not write implementation code.
11. Do not suggest unrelated architectural changes.
12. Keep the repair focused on the actual failure.
13. Severity must be one of:
    - low
    - medium
    - high
14. Return valid JSON only.
"""


MAX_TEST_OUTPUT = 8_000
MAX_RETRIES = 2


def clean_response(
    content,
) -> str:
    """
    Convert an LLM response into clean JSON text.
    """

    if content is None:

        return ""

    if isinstance(
        content,
        list,
    ):

        parts = []

        for item in content:

            if isinstance(
                item,
                dict,
            ):

                text = item.get(
                    "text",
                    "",
                )

                if text:

                    parts.append(
                        str(text)
                    )

            else:

                parts.append(
                    str(item)
                )

        content = "".join(
            parts
        )

    content = str(
        content
    ).strip()

    if content.startswith(
        "```json"
    ):

        content = content[
            len("```json"):
        ]

    elif content.startswith(
        "```"
    ):

        content = content[
            len("```"):
        ]

    if content.endswith(
        "```"
    ):

        content = content[
            :-3
        ]

    return content.strip()


def validate_debugger_result(
    result: dict,
    repository_files: list[str],
) -> None:
    """
    Validate the debugger response.

    The most important safety rule is that the Debugger can
    only target files that actually exist in the repository.
    """

    if not isinstance(
        result,
        dict,
    ):

        raise ValueError(
            "Debugger response must be a JSON object."
        )

    required_fields = {
        "diagnosis",
        "errors",
        "files_to_fix",
        "fix_instructions",
        "severity",
    }

    missing = (
        required_fields
        - set(result.keys())
    )

    if missing:

        raise ValueError(
            (
                "Debugger response is missing "
                f"fields: {sorted(missing)}"
            )
        )

    if result.get(
        "severity"
    ) not in {
        "low",
        "medium",
        "high",
    }:

        raise ValueError(
            "Invalid debugger severity."
        )

    repository_set = {
        path.replace("\\", "/")
        for path in repository_files
    }

    files_to_fix = result.get(
        "files_to_fix",
        []
    )

    if not isinstance(
        files_to_fix,
        list,
    ):

        raise ValueError(
            "files_to_fix must be a list."
        )

    for path in files_to_fix:

        if not isinstance(
            path,
            str,
        ):

            raise ValueError(
                "Debugger file paths must be strings."
            )

        normalized = path.replace(
            "\\",
            "/",
        ).strip()

        if normalized == ".env":

            raise ValueError(
                "Debugger cannot target .env."
            )

        if (
            normalized.startswith(
                ".git/"
            )
            or normalized.startswith(
                ".venv/"
            )
            or normalized.startswith(
                "__pycache__/"
            )
        ):

            raise ValueError(
                (
                    "Debugger cannot target "
                    f"blocked path: {normalized}"
                )
            )

        if normalized not in repository_set:

            raise ValueError(
                (
                    "Debugger targeted a file that does "
                    "not exist in the repository: "
                    f"{normalized}"
                )
            )


def build_debugger_prompt(
    state: AgentState,
    stdout: str,
    stderr: str,
) -> str:
    """
    Build a compact debugger prompt.

    Only repository paths are supplied here.
    Full repository source code is unnecessary for diagnosis.
    """

    repository_files = [
        str(path).replace(
            "\\",
            "/",
        )
        for path in state.get(
            "relevant_files",
            [],
        )
    ]

    return f"""
{DEBUGGER_SYSTEM_PROMPT}

USER REQUIREMENT:
{state.get("user_request", "")}

CURRENT STEP:
{state.get("current_step", "")}

TEST RETURN CODE:
{state.get("test_results", {}).get("return_code", -1)}

ACTUAL REPOSITORY FILES:
{json.dumps(repository_files)}

TEST STDOUT:
{stdout}

TEST STDERR:
{stderr}

Identify the root cause.

IMPORTANT:
files_to_fix MUST contain only paths from ACTUAL REPOSITORY FILES.

If no repository file can be safely identified as the cause,
return:

"files_to_fix": []

Return ONLY JSON.
"""


def call_debugger_llm(
    prompt: str,
) -> dict:
    """
    Call Groq with structured JSON output.
    """

    client = get_groq_client()
    model = get_model()

    schema = {
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
    }

    response = client.chat.completions.create(
        model=model,
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
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "debugger_output",
                "schema": schema,
                "strict": True,
            },
        },
    )

    if not response.choices:

        raise ValueError(
            "Debugger LLM returned no choices."
        )

    content = getattr(
        response.choices[0].message,
        "content",
        None,
    )

    content = clean_response(
        content
    )

    if not content:

        raise ValueError(
            "Debugger LLM returned an empty response."
        )

    return json.loads(
        content
    )


def debugger_agent(
    state: AgentState,
) -> AgentState:
    """
    Analyze failed tests and produce safe repair instructions.
    """

    test_results = state.get(
        "test_results",
        {},
    )

    if not test_results:

        return {
            **state,
            "debugger_result": {},
            "errors": [
                *state.get(
                    "errors",
                    [],
                ),
                "Debugger: No test results available.",
            ],
            "current_step": (
                "debugging_failed"
            ),
        }

    if test_results.get(
        "success",
        False,
    ):

        return {
            **state,
            "debugger_result": {
                "diagnosis": (
                    "Tests passed. Debugging is not required."
                ),
                "errors": [],
                "files_to_fix": [],
                "fix_instructions": [],
                "severity": "low",
            },
            "current_step": (
                "debugging_not_required"
            ),
        }

    stdout = str(
        test_results.get(
            "stdout",
            "",
        )
    )

    stderr = str(
        test_results.get(
            "stderr",
            "",
        )
    )

    if len(stdout) > MAX_TEST_OUTPUT:

        stdout = (
            stdout[:MAX_TEST_OUTPUT]
            + "\n[STDOUT TRUNCATED]"
        )

    if len(stderr) > MAX_TEST_OUTPUT:

        stderr = (
            stderr[:MAX_TEST_OUTPUT]
            + "\n[STDERR TRUNCATED]"
        )

    repository_files = state.get(
        "relevant_files",
        [],
    )

    prompt = build_debugger_prompt(
        state,
        stdout,
        stderr,
    )

    last_error = None

    for attempt in range(
        MAX_RETRIES
    ):

        try:

            result = call_debugger_llm(
                prompt
            )

            validate_debugger_result(
                result,
                repository_files,
            )

            return {
                **state,
                "debugger_result": result,
                "current_step": (
                    "debugging_complete"
                ),
            }

        except Exception as exc:

            last_error = exc

            if attempt < MAX_RETRIES - 1:

                time.sleep(1)

                prompt = build_debugger_prompt(
                    state,
                    stdout,
                    stderr,
                ) + f"""

PREVIOUS DEBUGGER ERROR:
{exc}

Correct the response.

Do not invent repository paths.

Return ONLY JSON.
"""

    return {
        **state,
        "debugger_result": {},
        "errors": [
            *state.get(
                "errors",
                [],
            ),
            f"Debugger error: {last_error}",
        ],
        "current_step": (
            "debugging_failed"
        ),
    }