from unittest.mock import patch

import pytest

from backend.github.client import (
    GitHubClient,
    GitHubConfig,
)


def create_client():
    config = GitHubConfig(
        token="test-token",
        owner="test-owner",
        repo="test-repo",
    )

    return GitHubClient(
        repository_path=".",
        config=config,
    )


def test_github_config_is_valid():
    client = create_client()

    client.validate_config()


def test_missing_github_token():
    config = GitHubConfig(
        token="",
        owner="test-owner",
        repo="test-repo",
    )

    client = GitHubClient(
        repository_path=".",
        config=config,
    )

    with pytest.raises(ValueError):
        client.validate_config()


def test_missing_github_owner():
    config = GitHubConfig(
        token="test-token",
        owner="",
        repo="test-repo",
    )

    client = GitHubClient(
        repository_path=".",
        config=config,
    )

    with pytest.raises(ValueError):
        client.validate_config()


def test_missing_github_repo():
    config = GitHubConfig(
        token="test-token",
        owner="test-owner",
        repo="",
    )

    client = GitHubClient(
        repository_path=".",
        config=config,
    )

    with pytest.raises(ValueError):
        client.validate_config()


def test_empty_branch_name_is_rejected():
    client = create_client()

    with pytest.raises(ValueError):
        client.create_branch("")


def test_branch_starting_with_dash_is_rejected():
    client = create_client()

    with pytest.raises(ValueError):
        client.create_branch("--bad-branch")


@patch(
    "backend.github.client.subprocess.run"
)
def test_current_branch(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "main\n"
    mock_run.return_value.stderr = ""

    client = create_client()

    branch = client.get_current_branch()

    assert branch == "main"

    mock_run.assert_called_once()


@patch(
    "backend.github.client.subprocess.run"
)
def test_git_command_failure(mock_run):
    mock_run.return_value.returncode = 1
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = "fatal: test error"

    client = create_client()

    with pytest.raises(RuntimeError) as exc:
        client.get_status()

    assert "Git command failed" in str(exc.value)
    assert "fatal: test error" in str(exc.value)