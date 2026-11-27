"""LLM provider layer.

All agents use ONE provider/model chosen in ``.env``:

    LLM_PROVIDER = openrouter | gemini | nvidia
    MODEL        = model id for that provider (optional; sensible default)

and the matching key: OPENROUTER_API_KEY, GEMINI_API_KEY (or GOOGLE_API_KEY),
NVIDIA_API_KEY. All three speak the OpenAI-compatible chat API.

API keys are only ever read from the environment - never hard-code them.
"""
from __future__ import annotations

import copy
import json
import os

from dotenv import load_dotenv

load_dotenv()

SUPPORTED_PROVIDERS = ("openrouter", "gemini", "nvidia")

_DEFAULT_MODELS = {
    "openrouter": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "gemini": "gemini-3.8-flash",
    "nvidia": "openai/gpt-oss-20b",
}
_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}
_KEY_VARS = {
    "openrouter": ("OPENROUTER_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "nvidia": ("NVIDIA_API_KEY",),
}


def get_provider() -> str:
    provider = os.getenv("LLM_PROVIDER", "openrouter").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            f"Choose one of: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    return provider


def get_api_key() -> str:
    provider = get_provider()
    for var in _KEY_VARS[provider]:
        value = (os.getenv(var) or "").strip()
        if value:
            return value
    raise ValueError(
        f"{_KEY_VARS[provider][0]} is missing (needed for LLM_PROVIDER={provider})."
    )


def get_model(agent: str | None = None) -> str:
    """Return one model id shared by every agent in the application."""
    provider = get_provider()
    model = os.getenv("MODEL", "").strip() or _DEFAULT_MODELS[provider]
    return model


def _int_setting(name: str, default: int, minimum: int = 1) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return parsed


def get_context_char_limit() -> int:
    """Repository context budget, configurable without changing code."""
    return _int_setting("LLM_MAX_CONTEXT_CHARS", 120_000)


def get_file_char_limit() -> int:
    return _int_setting("LLM_MAX_FILE_CHARS", 20_000)


def get_output_token_limit(default: int = 8_000, agent: str | None = None) -> int:
    if agent:
        specific = os.getenv(f"LLM_MAX_OUTPUT_TOKENS_{agent.upper()}", "").strip()
        if specific:
            return _int_setting(f"LLM_MAX_OUTPUT_TOKENS_{agent.upper()}", default)
    return _int_setting("LLM_MAX_OUTPUT_TOKENS", default)


def _client_timeout() -> int:
    return _int_setting("LLM_TIMEOUT_SECONDS", 120)


def _client_retries() -> int:
    return _int_setting("LLM_CLIENT_RETRIES", 2, minimum=0)


# ----------------------------------------------------------------------------
# OpenRouter adapter
# ----------------------------------------------------------------------------
def clean_json_text(text: str) -> str:
    """Strip markdown fences / chatter so json.loads() can parse the reply."""
    text = (text or "").strip()
    # Reasoning models may prefix <think>...</think>; braces inside it would
    # otherwise confuse the JSON extraction below.
    if "</think>" in text:
        text = text.split("</think>", 1)[1].strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()
    if text and text[0] not in "{[":
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return text


class _Completions:
    """OpenAI-compatible calls with prompt-based JSON instructions.

    Not every hosted model supports response_format, so the JSON schema is put
    in the system prompt instead of being sent as an API parameter.
    """

    def __init__(self, client, provider: str):
        self._client = client
        self._provider = provider

    def create(self, **kwargs):
        kwargs.pop("reasoning_effort", None)
        wanted = kwargs.get("response_format")
        if wanted and wanted.get("type") == "json_schema":
            kwargs = self._with_json_schema_instruction(kwargs)
        else:
            kwargs.pop("response_format", None)
        response = self._client.chat.completions.create(**kwargs)
        self._clean(response)
        return response

    @staticmethod
    def _with_json_schema_instruction(kwargs: dict) -> dict:
        shaped = copy.deepcopy(kwargs)
        schema = (shaped.pop("response_format").get("json_schema") or {}).get("schema", {})
        instruction = (
            "\n\nReply with ONLY valid JSON matching this schema. Do not include "
            "markdown, explanations, or reasoning outside the JSON object.\n"
            + json.dumps(schema, separators=(",", ":"))
        )
        messages = shaped.get("messages", [])
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = f"{messages[0]['content']}{instruction}"
        else:
            messages.insert(0, {"role": "system", "content": instruction.strip()})
        return shaped

    @staticmethod
    def _clean(response) -> None:
        for choice in getattr(response, "choices", []) or []:
            message = getattr(choice, "message", None)
            if message is None:
                continue
            if not message.content:
                # Some reasoning models put the answer in a reasoning field.
                fallback = (
                    getattr(message, "reasoning", None)
                    or getattr(message, "reasoning_content", None)
                )
                if isinstance(fallback, str) and "{" in fallback:
                    message.content = fallback
            if message.content:
                message.content = clean_json_text(message.content)


class _Chat:
    def __init__(self, client, provider: str):
        self.completions = _Completions(client, provider)


class _CompatClient:
    def __init__(self, client, provider: str):
        self.chat = _Chat(client, provider)


def get_llm_client():
    """Return the configured chat client."""
    provider = get_provider()
    from openai import OpenAI
    client = OpenAI(
        api_key=get_api_key(),
        base_url=os.getenv("LLM_BASE_URL", "").strip() or _BASE_URLS[provider],
        max_retries=_client_retries(),
        timeout=_client_timeout(),
    )
    return _CompatClient(client, provider)