import json
import time

from backend.graph.state import AgentState
from backend.llm import get_llm


DEBUGGER_SYSTEM_PROMPT = """
You are the Debugger Agent in an autonomous software engineering system.

Analyze failed test results and determine the likely cause of the failure.

Return ONLY valid JSON.

Required JSON format:

{
  "diagnosis": "short explanation of the root cause",
  "errors": [
    "specific error or failure"
  ],
  "files_to_fix": [
    "relative/path.py"
  ],
  "fix_instructions": [
    "specific instruction for the Coder"
  ],
  "severity": "low"
}

Rules:
1. Analyze the actual test output.
2. Do not invent errors that are not supported by the output.
3. Identify files that likely need changes.
4. Give concrete instructions to the Coder.
5. Do not write implementation code.
6. Never include .env.
7. Severity must be one of:
   - low
   - medium
   - high
8. Return valid JSON only.
"""


MAX_TEST_OUTPUT = 15_000
MAX_RETRIES = 2


def clean_response(content) -> str:
    """
    Convert the LLM response into clean JSON.
    """

    if content is None:
        return ""

    if isinstance(content, list):

        parts = []

        for item in content:

            if isinstance(item, dict):

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

        content = "".join(parts)

    content = str(
        content
    ).strip()

    if not content:
        return ""

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
            :-len("```")
        ]

    return content.strip()


def validate_debugger_result(
    result: dict,
) -> None:
    """
    Validate the debugger JSON response.
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

    if result["severity"] not in {
        "low",
        "medium",
        "high",
    }:

        raise ValueError(
            "Invalid debugger severity."
        )

    if ".env" in result.get(
        "files_to_fix",
        [],
    ):

        raise ValueError(
            "Debugger cannot target .env."
        )


def debugger_agent(
    state: AgentState,
) -> AgentState:
    """
    Analyze failed tests and produce
    debugging instructions.
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
            "current_step": "debugging_failed",
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
            "current_step": "debugging_not_required",
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

    prompt = f"""
{DEBUGGER_SYSTEM_PROMPT}

USER REQUIREMENT:
{state.get("user_request", "")}

CURRENT STEP:
{state.get("current_step", "")}

TEST RETURN CODE:
{test_results.get("return_code", -1)}

TEST STDOUT:
{stdout}

TEST STDERR:
{stderr}

Analyze the failure.

Return ONLY JSON.
"""

    try:

        llm = get_llm()

        last_error = None

        for attempt in range(
            MAX_RETRIES
        ):

            try:

                response = llm.invoke(
                    prompt
                )

                content = clean_response(
                    response.content
                )

                if not content:

                    raise ValueError(
                        "Debugger returned an empty response."
                    )

                result = json.loads(
                    content
                )

                validate_debugger_result(
                    result
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

                    prompt = f"""
{DEBUGGER_SYSTEM_PROMPT}

TEST FAILURE:

{stdout}

{stderr}

Return a small valid JSON object.

Return ONLY JSON.
"""

        raise last_error

    except Exception as exc:

        return {
            **state,
            "debugger_result": {},
            "errors": [
                *state.get(
                    "errors",
                    [],
                ),
                f"Debugger error: {exc}",
            ],
            "current_step": "debugging_failed",
        }