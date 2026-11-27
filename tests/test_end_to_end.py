"""End-to-end pipeline test with a scripted fake LLM (no network, no API keys).

Reproduces the real-world failure: the repository already contains EMPTY
app.html / app1.css / app.js and the model labels app1.css as "create" even
though the plan lists it under files_to_modify.
"""
from __future__ import annotations

import json
import re
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.agents import (
    code_review,
    coder,
    debugger,
    planner,
    repository_intelligence,
)
from backend.github.client import GitHubClient
from backend.graph.workflow import build_workflow

HOME_TEST = (
    "from pathlib import Path\n\n"
    "def test_home_has_title():\n"
    "    assert '<title>' in Path('app.html').read_text()\n"
)


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    git(work, "init", "-b", "main")
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "t")
    for name in ("app.html", "app1.css", "app.js"):
        (work / name).write_text("")
    git(work, "add", "-A")
    git(work, "commit", "-m", "init")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-u", "origin", "main")
    return work, remote


def make_fake_llm(review_answers):
    reviews = list(review_answers)
    calls = {"coder": 0}

    def reply(payload):
        message = SimpleNamespace(content=json.dumps(payload))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    def create(**kwargs):
        name = kwargs["response_format"]["json_schema"]["name"]
        user = kwargs["messages"][-1]["content"]

        if name == "repository_intelligence":
            return reply({
                "project_type": "static website", "languages": ["HTML", "CSS", "JavaScript"],
                "frameworks": [], "libraries": [], "entry_points": ["app.html"],
                "source_files": ["app.html", "app1.css", "app.js"], "test_files": [],
                "configuration_files": [], "architecture_components": [],
                "file_relationships": [], "relevant_files": ["app.html"],  # trimmed on purpose
                "implementation_context": [], "architecture_summary": "Empty static site.",
            })

        if name == "implementation_plan":
            return reply({
                "summary": "Build the home page.",
                "tasks": [
                    {"id": 1, "title": "HTML", "description": "page", "files_to_modify": ["app.html"],
                     "files_to_create": [], "dependencies": [], "tests_required": [], "security_considerations": []},
                    # Wrong on purpose: app1.css exists but is listed under create, and
                    # tests/test_home.py is listed under modify although it is new.
                    {"id": 2, "title": "CSS + tests", "description": "style", "files_to_modify": ["tests/test_home.py"],
                     "files_to_create": ["app1.css"], "dependencies": ["Task 1"], "tests_required": [], "security_considerations": []},
                ],
                "testing_strategy": [], "security_strategy": [],
            })

        if name == "coder_response":
            calls["coder"] += 1
            match = re.search(r"Files allowed to modify:\n(\[.*?\])\n\nFiles allowed to create:\n(\[.*?\])", user, re.S)
            paths = json.loads(match.group(1)) + json.loads(match.group(2))
            files = []
            for path in paths:
                body = HOME_TEST if path.endswith(".py") else (
                    "<!DOCTYPE html><html><head><title>Food</title></head><body>hi</body></html>"
                    if path.endswith(".html") else "body{margin:0}")
                # The model always claims "create": the bug that crashed the run.
                files.append({"path": path, "action": "create", "content": body})
            return reply({"files": files, "summary": "done"})

        if name == "code_review":
            return reply(reviews.pop(0) if len(reviews) > 1 else reviews[0])

        raise AssertionError(f"unexpected schema {name}")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, calls


def patch_llm(monkeypatch, client):
    for module in (coder, planner, code_review, debugger, repository_intelligence):
        monkeypatch.setattr(module, "get_llm_client", lambda c=client: c)


APPROVED = {"overall_status": "approved", "summary": "Good.", "issues": [], "strengths": [], "security_concerns": []}


def initial_state(path):
    return {
        "user_request": "create a home for food delivery web app", "repository_path": str(path),
        "plan": [], "events": [], "errors": [], "debug_retry_count": 0, "max_debug_retries": 3,
        "generated_files": [], "modified_files": [], "test_results": {},
    }


def test_pipeline_reaches_human_approval_despite_mislabelled_actions(repo, monkeypatch):
    work, _ = repo
    client, calls = make_fake_llm([APPROVED])
    patch_llm(monkeypatch, client)

    result = build_workflow().invoke(initial_state(work))

    assert result["errors"] == []
    assert result["current_step"] == "waiting_for_human_approval"
    assert result["approval_required"] is True
    assert result["test_results"]["success"] is True
    assert "<title>" in (work / "app.html").read_text()
    assert (work / "app1.css").read_text() == "body{margin:0}"
    assert "app1.css" in result["modified_files"]  # it existed, so it was a modification


def test_review_requested_changes_are_sent_back_to_the_coder(repo, monkeypatch):
    work, _ = repo
    changes = {
        "overall_status": "changes_requested", "summary": "Needs a viewport meta tag.",
        "issues": [{"severity": "high", "category": "quality", "file": "app.html",
                    "description": "missing viewport", "recommendation": "add meta viewport"}],
        "strengths": [], "security_concerns": [],
    }
    client, calls = make_fake_llm([changes, APPROVED])
    patch_llm(monkeypatch, client)

    result = build_workflow().invoke(initial_state(work))

    assert result["review_retry_count"] == 1
    assert result["current_step"] == "waiting_for_human_approval"


def test_approval_commits_only_run_files_and_opens_pr(repo, monkeypatch, tmp_path):
    work, remote = repo
    client, _ = make_fake_llm([APPROVED])
    patch_llm(monkeypatch, client)
    state = build_workflow().invoke(initial_state(work))
    assert state["current_step"] == "waiting_for_human_approval"

    # Junk that `git add -A` would have committed.
    (work / ".pytest_cache").mkdir(exist_ok=True)
    (work / ".pytest_cache" / "junk").write_text("x")

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret_token_value")
    monkeypatch.setenv("GITHUB_OWNER", "owner")
    monkeypatch.setenv("GITHUB_REPO", "repo")

    def fake_api(self, method, endpoint, payload=None):
        if method == "GET":
            return []
        return {"number": 7, "html_url": "https://github.com/owner/repo/pull/7"}

    monkeypatch.setattr(GitHubClient, "_github_request", fake_api)
    monkeypatch.setattr(main, "RUN_STORE_FILE", tmp_path / "store.json")
    main.RUN_STORE["run-1"] = state

    response = TestClient(main.app).post("/runs/run-1/approve", json={"reviewer": "me", "comment": "ok"})
    body = response.json()

    assert body["status"] == "approved", body
    assert body["github_result"]["status"] == "created"
    branch = body["github_result"]["branch"]
    changed = git(remote, "show", "--name-only", "--format=", branch).splitlines()
    assert ".pytest_cache/junk" not in changed
    assert "app.html" in changed
    assert "ghp_secret_token_value" not in json.dumps(body)