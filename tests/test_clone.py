import subprocess

import pytest
from fastapi import HTTPException

import backend.main as main


def _runner(fail_when_no_header=False, fail_always=False, calls=None):
    def run(command, **kwargs):
        calls.append(command)
        has_header = any("http.extraheader" in part for part in command)
        if fail_always or (fail_when_no_header and not has_header) or (not fail_when_no_header and has_header):
            raise subprocess.CalledProcessError(128, command, stderr="fatal: Authentication failed for ghp_tok")
        return subprocess.CompletedProcess(command, 0, "", "")
    return run


def test_public_repo_clones_even_with_a_bad_token(monkeypatch):
    calls = []
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_tok")
    # token header would be rejected; anonymous clone must be tried first
    monkeypatch.setattr(main.subprocess, "run", _runner(calls=calls))
    path = main._resolve_repository("https://github.com/o/r", "run-a")
    assert path.endswith("run-a")
    assert len(calls) == 1 and not any("extraheader" in p for p in calls[0])


def test_private_repo_falls_back_to_token(monkeypatch):
    calls = []
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_tok")
    monkeypatch.setattr(main.subprocess, "run", _runner(fail_when_no_header=True, calls=calls))
    main._resolve_repository("https://github.com/o/r", "run-b")
    assert len(calls) == 2


def test_clone_error_never_leaks_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_tok")
    monkeypatch.setattr(main.subprocess, "run", _runner(fail_always=True, calls=[]))
    with pytest.raises(HTTPException) as exc:
        main._resolve_repository("https://github.com/o/r", "run-c")
    assert "ghp_tok" not in exc.value.detail


def test_provider_selection(monkeypatch):
    from backend import llm

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", " k ")
    assert llm.get_model() == "gemini-3.8-flash"
    assert llm.get_api_key() == "k"
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("MODEL", "openai/gpt-oss-20b")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(ValueError):
        llm.get_api_key()