import json
from types import SimpleNamespace

import httpx
import pytest
from openai import RateLimitError

from backend import llm


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in (
        "LLM_PROVIDER", "MODEL", "GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "MODEL_CODER",
        "MODEL_DEBUGGER", "LLM_MAX_CONTEXT_CHARS", "LLM_MAX_FILE_CHARS",
        "LLM_MAX_OUTPUT_TOKENS", "LLM_MAX_OUTPUT_TOKENS_INTELLIGENCE",
    ):
        monkeypatch.delenv(var, raising=False)


def test_app_uses_openrouter_nemotron_for_every_agent():
    expected = "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert llm.get_provider() == "openrouter"
    assert llm.get_model() == expected
    assert llm.get_model("coder") == expected
    assert llm.get_model("intelligence") == expected


def test_unknown_provider_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(ValueError, match="Unsupported"):
        llm.get_provider()


def test_missing_openrouter_key_message():
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        llm.get_api_key()


def test_only_openrouter_is_supported(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    with pytest.raises(ValueError, match="Choose one of: openrouter"):
        llm.get_provider()


def test_provider_request_settings_are_configurable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    assert llm.get_context_char_limit() == 120_000
    monkeypatch.setenv("LLM_MAX_CONTEXT_CHARS", "70000")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS_INTELLIGENCE", "16000")
    assert llm.get_context_char_limit() == 70_000
    assert llm.get_output_token_limit(12_000, agent="intelligence") == 16_000


def test_openrouter_api_key_alias(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")
    assert llm.get_api_key() == "router-key"


def test_single_model_is_used_even_if_agent_override_is_set(monkeypatch):
    monkeypatch.setenv("MODEL", "base-model")
    monkeypatch.setenv("MODEL_CODER", "strong-model")
    assert llm.get_model("coder") == "base-model"
    assert llm.get_model("debugger") == "base-model"
    assert llm.get_model() == "base-model"


def test_clean_json_text_strips_fences_and_chatter():
    assert json.loads(llm.clean_json_text('```json\n{"a": 1}\n```')) == {"a": 1}
    assert json.loads(llm.clean_json_text('Sure! Here it is: {"a": 2} thanks')) == {"a": 2}
    assert llm.clean_json_text('{"a": 3}') == '{"a": 3}'


def test_client_factory_uses_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    client = llm.get_llm_client()
    assert isinstance(client, llm._CompatClient)
    assert str(client.chat.completions._client.base_url) == "https://openrouter.ai/api/v1/"


def _response(text):
    msg = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeOpenAI:
    def __init__(self, reply='```json\n{"ok": true}\n```'):
        self.calls, self.reply = [], reply
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return _response(self.reply)


KW = dict(
    model="m",
    messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "u"}],
    reasoning_effort="low",
    response_format={"type": "json_schema", "json_schema": {"name": "n", "schema": {"type": "object"}}},
)


def test_schema_is_sent_as_prompt_instruction_and_output_cleaned():
    fake = FakeOpenAI()
    resp = llm._Completions(fake, "openrouter").create(**KW)
    assert len(fake.calls) == 1
    assert "reasoning_effort" not in fake.calls[0]
    assert "response_format" not in fake.calls[0]
    assert "JSON matching this schema" in fake.calls[0]["messages"][0]["content"]
    assert json.loads(resp.choices[0].message.content) == {"ok": True}


def test_non_format_errors_are_not_swallowed():
    req = httpx.Request("POST", "http://test")
    err = RateLimitError("429 rate limit", response=httpx.Response(429, request=req), body=None)

    class Boom:
        chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(err)))

    with pytest.raises(RateLimitError):
        llm._Completions(Boom(), "openrouter").create(**KW)
