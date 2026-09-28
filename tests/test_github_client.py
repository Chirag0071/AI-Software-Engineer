from unittest.mock import patch

import pytest

from backend.github.client import (
    GitHubClient,
    GitHubConfig,
    PullRequestResult,
)


def create_client():
    config = GitHubConfig(
        token="test-token",
        owner="test-owner",
        repo="test-repo",
        base_branch="main",
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

    assert "Git command failed" in str(
        exc.value
    )

    assert "fatal: test error" in str(
        exc.value
    )


def test_pull_request_result():
    result = PullRequestResult(
        number=42,
        url="https://github.com/test-owner/test-repo/pull/42",
        title="Add feature",
        branch="ai-engineer/add-feature",
        base_branch="main",
    )

    assert result.number == 42
    assert result.title == "Add feature"
    assert result.branch == (
        "ai-engineer/add-feature"
    )
    assert result.base_branch == "main"


def test_pull_request_requires_branch():
    client = create_client()

    with pytest.raises(ValueError):
        client.create_pull_request(
            branch_name="",
            title="Test PR",
        )


def test_pull_request_requires_title():
    client = create_client()

    with pytest.raises(ValueError):
        client.create_pull_request(
            branch_name="test-branch",
            title="",
        )


@patch(
    "backend.github.client.urlopen"
)
def test_create_pull_request(
    mock_urlopen,
):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def read(self):
            return (
                b'{"number": 42, '
                b'"html_url": '
                b'"https://github.com/test-owner/'
                b'test-repo/pull/42"}'
            )

    mock_urlopen.return_value = (
        FakeResponse()
    )

    client = create_client()

    result = client.create_pull_request(
        branch_name="ai-engineer/test-feature",
        title="Add test feature",
        body="Automated Pull Request.",
    )

    assert result.number == 42

    assert result.url == (
        "https://github.com/test-owner/"
        "test-repo/pull/42"
    )

    assert result.branch == (
        "ai-engineer/test-feature"
    )

    assert result.base_branch == "main"

    mock_urlopen.assert_called_once()


@patch(
    "backend.github.client.urlopen"
)
def test_github_request_does_not_expose_token(
    mock_urlopen,
):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def read(self):
            return (
                b'{"number": 1, '
                b'"html_url": '
                b'"https://github.com/test-owner/'
                b'test-repo/pull/1"}'
            )

    mock_urlopen.return_value = (
        FakeResponse()
    )

    client = GitHubClient(
        repository_path=".",
        config=GitHubConfig(
            token="SECRET_TEST_TOKEN",
            owner="test-owner",
            repo="test-repo",
            base_branch="main",
        ),
    )

    client.create_pull_request(
        branch_name="test-branch",
        title="Test PR",
    )

    request = (
        mock_urlopen.call_args.args[0]
    )

    assert (
        request.headers.get(
            "Authorization"
        )
        == "Bearer SECRET_TEST_TOKEN"
    )