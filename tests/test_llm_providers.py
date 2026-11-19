import json
from types import SimpleNamespace

import httpx
import pytest
from openai import BadRequestError, RateLimitError

from backend import llm


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in (
        "LLM_PROVIDER", "MODEL", "GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY", "MODEL_CODER", "MODEL_DEBUGGER",
    ):
        monkeypatch.delenv(var, raising=False)
    llm._Completions._working.clear()


def test_default_provider_is_groq():
    assert llm.get_provider() == "groq"
    assert llm.get_model() == "openai/gpt-oss-20b"


def test_unknown_provider_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(ValueError, match="Unsupported"):
        llm.get_provider()


def test_missing_key_message(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        llm.get_api_key()


def test_gemini_accepts_google_api_key_alias(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    assert llm.get_api_key() == "k"
    assert llm.get_model() == "gemini-2.5-flash"


def test_openrouter_requires_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    with pytest.raises(ValueError, match="MODEL is required"):
        llm.get_model()
    monkeypatch.setenv("MODEL", "vendor/some-model:free")
    assert llm.get_model() == "vendor/some-model:free"


def test_per_agent_model_override(monkeypatch):
    monkeypatch.setenv("MODEL", "base-model")
    monkeypatch.setenv("MODEL_CODER", "strong-model")
    assert llm.get_model("coder") == "strong-model"
    assert llm.get_model("debugger") == "base-model"
    assert llm.get_model() == "base-model"


def test_clean_json_text_strips_fences_and_chatter():
    assert json.loads(llm.clean_json_text('```json\n{"a": 1}\n```')) == {"a": 1}
    assert json.loads(llm.clean_json_text('Sure! Here it is: {"a": 2} thanks')) == {"a": 2}
    assert llm.clean_json_text('{"a": 3}') == '{"a": 3}'


def test_client_factory_uses_compat_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    client = llm.get_groq_client()
    assert isinstance(client, llm._CompatClient)


# ---- fallback behaviour -----------------------------------------------------
def _bad_request():
    req = httpx.Request("POST", "http://test")
    return BadRequestError("bad", response=httpx.Response(400, request=req), body=None)


def _response(text):
    msg = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeOpenAI:
    """Rejects the first `reject` formats, then answers."""

    def __init__(self, reject, reply='```json\n{"ok": true}\n```'):
        self.calls, self.reject, self.reply = [], reject, reply
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        if len(self.calls) <= self.reject:
            raise _bad_request()
        return _response(self.reply)


KW = dict(
    model="m",
    messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "u"}],
    reasoning_effort="low",
    response_format={"type": "json_schema", "json_schema": {"name": "n", "schema": {"type": "object"}}},
)


def test_schema_accepted_first_try_and_output_cleaned():
    fake = FakeOpenAI(reject=0)
    resp = llm._Completions(fake, "gemini").create(**KW)
    assert len(fake.calls) == 1
    assert fake.calls[0]["reasoning_effort"] == "low"  # kept for Gemini
    assert json.loads(resp.choices[0].message.content) == {"ok": True}


def test_openrouter_drops_reasoning_effort():
    fake = FakeOpenAI(reject=0)
    llm._Completions(fake, "openrouter").create(**KW)
    assert "reasoning_effort" not in fake.calls[0]


def test_falls_back_to_json_object_then_prompt_only():
    fake = FakeOpenAI(reject=2)
    resp = llm._Completions(fake, "openrouter").create(**KW)
    assert [c.get("response_format", {}).get("type") for c in fake.calls] == ["json_schema", "json_object", None]
    assert "JSON schema" in fake.calls[2]["messages"][0]["content"]
    assert json.loads(resp.choices[0].message.content) == {"ok": True}
    # original kwargs were not mutated
    assert KW["response_format"]["type"] == "json_schema"


def test_working_strategy_is_cached():
    fake = FakeOpenAI(reject=1)
    comp = llm._Completions(fake, "openrouter")
    comp.create(**KW)
    fake.calls.clear()
    fake.reject = 0
    comp.create(**KW)
    assert len(fake.calls) == 1 and fake.calls[0]["response_format"]["type"] == "json_object"


def test_non_format_errors_are_not_swallowed():
    req = httpx.Request("POST", "http://test")
    err = RateLimitError("429 rate limit", response=httpx.Response(429, request=req), body=None)

    class Boom:
        chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(err)))

    with pytest.raises(RateLimitError):
        llm._Completions(Boom(), "gemini").create(**KW)
