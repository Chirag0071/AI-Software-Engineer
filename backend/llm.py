"""LLM provider layer.

Supported providers (set LLM_PROVIDER in .env):

* ``groq``        - GROQ_API_KEY,       default model ``openai/gpt-oss-20b``
* ``gemini``      - GEMINI_API_KEY (Google AI Studio key; GOOGLE_API_KEY also accepted),
                    default model ``gemini-2.5-flash``
* ``openrouter``  - OPENROUTER_API_KEY, MODEL is required (pick a model id from
                    openrouter.ai/models; ids ending in ``:free`` use the free tier)

Gemini and OpenRouter are reached through their OpenAI-compatible endpoints, so every
agent keeps calling ``get_groq_client().chat.completions.create(...)`` unchanged.

Per-agent models: set MODEL_CODER, MODEL_DEBUGGER, MODEL_PLANNER, MODEL_REVIEWER or
MODEL_INTELLIGENCE to override MODEL for one agent (e.g. a stronger model for the Coder
and Debugger, a cheaper one elsewhere).

API keys are only ever read from the environment - never hard-code them.
"""
from __future__ import annotations

import copy
import json
import os

from dotenv import load_dotenv
from groq import Groq
from langchain_groq import ChatGroq

load_dotenv()

SUPPORTED_PROVIDERS = ("groq", "gemini", "openrouter")

_DEFAULT_MODELS = {
    "groq": "openai/gpt-oss-20b",
    "gemini": "gemini-2.5-flash",
    "openrouter": "",  # must be chosen explicitly
}
_BASE_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openrouter": "https://openrouter.ai/api/v1",
}
_KEY_VARS = {
    "groq": ("GROQ_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY",),
}


def get_provider() -> str:
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            f"Choose one of: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    return provider


def get_api_key() -> str:
    provider = get_provider()
    for var in _KEY_VARS[provider]:
        value = os.getenv(var)
        if value:
            return value
    raise ValueError(f"{_KEY_VARS[provider][0]} is missing from .env")


def get_model(agent: str | None = None) -> str:
    """Model id for an agent: MODEL_<AGENT> > MODEL > provider default."""
    provider = get_provider()
    if agent:
        specific = os.getenv(f"MODEL_{agent.upper()}", "").strip()
        if specific:
            return specific
    model = os.getenv("MODEL", "").strip() or _DEFAULT_MODELS[provider]
    if not model:
        raise ValueError(
            f"MODEL is required when LLM_PROVIDER={provider}. "
            "Pick a model id from openrouter.ai/models (ids ending in ':free' are free)."
        )
    return model


def get_llm():
    """LangChain Groq client (Groq only)."""
    if get_provider() != "groq":
        raise ValueError("get_llm() is only available for LLM_PROVIDER=groq")
    return ChatGroq(model=get_model(), api_key=get_api_key(), temperature=0, max_retries=3)


# ----------------------------------------------------------------------------
# OpenAI-compatible adapter (Gemini / OpenRouter)
# ----------------------------------------------------------------------------
def clean_json_text(text: str) -> str:
    """Strip markdown fences / chatter so json.loads() can parse the reply."""
    text = (text or "").strip()
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


def _is_format_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    return status in (400, 422)


class _Completions:
    """Same call shape as ``Groq().chat.completions`` with structured-output fallbacks."""

    # strict JSON schema -> plain JSON mode -> prompt-only. The first that works is cached.
    _STRATEGIES = ("json_schema", "json_object", "prompt_only")
    _working: dict[tuple[str, str], str] = {}

    def __init__(self, client, provider: str):
        self._client = client
        self._provider = provider

    def create(self, **kwargs):
        if self._provider == "openrouter":
            kwargs.pop("reasoning_effort", None)  # not an OpenRouter chat parameter
        wanted = kwargs.get("response_format")
        if not wanted or wanted.get("type") != "json_schema":
            return self._client.chat.completions.create(**kwargs)

        cache_key = (self._provider, str(kwargs.get("model")))
        strategies = list(self._STRATEGIES)
        known = self._working.get(cache_key)
        if known:
            strategies = strategies[strategies.index(known):]

        last_exc: Exception | None = None
        for strategy in strategies:
            try:
                response = self._client.chat.completions.create(**self._shape(kwargs, strategy))
            except Exception as exc:  # noqa: BLE001
                if _is_format_error(exc) and strategy != strategies[-1]:
                    last_exc = exc
                    continue
                raise
            self._working[cache_key] = strategy
            self._clean(response)
            return response
        raise last_exc  # pragma: no cover

    @staticmethod
    def _shape(kwargs: dict, strategy: str) -> dict:
        if strategy == "json_schema":
            return kwargs
        shaped = copy.deepcopy(kwargs)
        schema = (shaped.pop("response_format").get("json_schema") or {}).get("schema", {})
        if strategy == "json_object":
            shaped["response_format"] = {"type": "json_object"}
        instruction = (
            "\n\nReply with ONLY one JSON object (no markdown, no commentary) that "
            "conforms to this JSON schema:\n" + json.dumps(schema)
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
            if message is not None and message.content:
                message.content = clean_json_text(message.content)


class _Chat:
    def __init__(self, client, provider: str):
        self.completions = _Completions(client, provider)


class _CompatClient:
    def __init__(self, client, provider: str):
        self.chat = _Chat(client, provider)


def get_groq_client():
    """Provider-aware client exposing ``.chat.completions.create(...)``.

    (Name kept for backwards compatibility with the agents.)
    """
    provider = get_provider()
    if provider == "groq":
        return Groq(api_key=get_api_key())

    from openai import OpenAI  # imported lazily so Groq-only setups don't need it

    client = OpenAI(
        api_key=get_api_key(),
        base_url=_BASE_URLS[provider],
        max_retries=2,
        timeout=120,
    )
    return _CompatClient(client, provider)


get_llm_client = get_groq_client
