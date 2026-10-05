"""
GitHub integration utilities.

This module provides controlled Git and GitHub REST API
operations for the autonomous software engineering system.

GitHub operations are intentionally separated from the
LangGraph workflow so they can be tested independently.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


load_dotenv()


GITHUB_API_URL = "https://api.github.com"


@dataclass
class GitHubConfig:
    """
    GitHub configuration loaded from environment variables.
    """

    token: str
    owner: str
    repo: str
    base_branch: str = "main"


@dataclass
class PullRequestResult:
    """
    Information returned after creating or finding
    a GitHub Pull Request.
    """

    number: int
    url: str
    title: str
    branch: str
    base_branch: str


class GitHubClient:
    """
    Client for Git and GitHub REST API operations.

    This class does not automatically perform any GitHub
    operation when instantiated.
    """

    def __init__(
        self,
        repository_path: str,
        config: Optional[GitHubConfig] = None,
    ):
        self.repository_path = repository_path

        if config is None:
            config = self._load_config()

        self.config = config

    @staticmethod
    def _load_config() -> GitHubConfig:
        """
        Load GitHub configuration from environment variables.
        """

        return GitHubConfig(
            token=os.getenv(
                "GITHUB_TOKEN",
                "",
            ).strip(),
            owner=os.getenv(
                "GITHUB_OWNER",
                "",
            ).strip(),
            repo=os.getenv(
                "GITHUB_REPO",
                "",
            ).strip(),
            base_branch=os.getenv(
                "GITHUB_BASE_BRANCH",
                "main",
            ).strip()
            or "main",
        )

    def validate_config(self) -> None:
        """
        Validate required GitHub configuration.
        """

        missing = []

        if not self.config.token:
            missing.append("GITHUB_TOKEN")

        if not self.config.owner:
            missing.append("GITHUB_OWNER")

        if not self.config.repo:
            missing.append("GITHUB_REPO")

        if not self.config.base_branch:
            missing.append("GITHUB_BASE_BRANCH")

        if missing:
            raise ValueError(
                "Missing GitHub configuration: "
                + ", ".join(missing)
            )

    def _run_git(
        self,
        *args: str,
    ) -> str:
        """
        Execute a Git command inside the target repository.
        """

        command = [
            "git",
            *args,
        ]

        try:
            result = subprocess.run(
                command,
                cwd=self.repository_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        except FileNotFoundError as exc:
            raise RuntimeError(
                "Git executable was not found. "
                "Make sure Git is installed and available "
                "in PATH."
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip()

            raise RuntimeError(
                f"Git command failed: "
                f"{' '.join(command)}\n"
                f"{stderr}"
            )

        return result.stdout.strip()

    def get_current_branch(self) -> str:
        """
        Return the currently checked-out Git branch.
        """

        branch = self._run_git(
            "branch",
            "--show-current",
        )

        if not branch:
            raise RuntimeError(
                "Unable to determine the current Git branch."
            )

        return branch

    def get_status(self) -> str:
        """
        Return the repository's current Git status.
        """

        return self._run_git(
            "status",
            "--short",
        )

    def create_branch(
        self,
        branch_name: str,
    ) -> str:
        """
        Create and switch to a new branch.
        """

        branch_name = branch_name.strip()

        if not branch_name:
            raise ValueError(
                "Branch name cannot be empty."
            )

        if branch_name.startswith("-"):
            raise ValueError(
                "Invalid branch name."
            )

        self._run_git(
            "switch",
            "-c",
            branch_name,
        )

        return branch_name

    def stage_changes(
        self,
        files: Optional[list[str]] = None,
    ) -> None:
        """
        Stage repository changes.

        If files are supplied, only those files are staged.
        Otherwise all changes are staged.
        """

        if files:
            self._run_git(
                "add",
                "--",
                *files,
            )
        else:
            self._run_git(
                "add",
                "-A",
            )

    def commit_changes(
        self,
        message: str,
    ) -> str:
        """
        Commit staged changes and return the commit SHA.
        """

        message = message.strip()

        if not message:
            raise ValueError(
                "Commit message cannot be empty."
            )

        self._run_git(
            "commit",
            "-m",
            message,
        )

        return self._run_git(
            "rev-parse",
            "HEAD",
        )

    def push_branch(
        self,
        branch_name: Optional[str] = None,
    ) -> None:
        """
        Push the current branch to origin.

        Existing Git credential configuration is used for
        authentication. The GitHub token is never inserted
        into the Git remote URL.
        """

        if branch_name is None:
            branch_name = self.get_current_branch()

        branch_name = branch_name.strip()

        if not branch_name:
            raise ValueError(
                "Branch name cannot be empty."
            )

        self._run_git(
            "push",
            "-u",
            "origin",
            branch_name,
        )

    def prepare_branch(
        self,
        branch_name: str,
    ) -> str:
        """
        Create a new Git branch.
        """

        return self.create_branch(
            branch_name
        )

    def _github_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> Any:
        """
        Send an authenticated request to the GitHub REST API.

        The GitHub token is never included in logs or returned
        in exceptions.
        """

        self.validate_config()

        endpoint = endpoint.lstrip("/")

        url = (
            f"{GITHUB_API_URL}/{endpoint}"
        )

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": (
                f"Bearer {self.config.token}"
            ),
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Software-Engineer",
        }

        body = None

        if payload is not None:
            body = json.dumps(
                payload
            ).encode("utf-8")

            headers["Content-Type"] = (
                "application/json"
            )

        request = Request(
            url,
            data=body,
            headers=headers,
            method=method.upper(),
        )

        try:
            with urlopen(
                request,
                timeout=30,
            ) as response:

                response_body = response.read()

                if not response_body:
                    return {}

                return json.loads(
                    response_body.decode("utf-8")
                )

        except HTTPError as exc:
            response_body = ""

            try:
                response_body = (
                    exc.read()
                    .decode(
                        "utf-8",
                        errors="replace",
                    )
                )
            except Exception:
                pass

            raise RuntimeError(
                "GitHub API request failed: "
                f"HTTP {exc.code}. "
                f"{response_body[:1000]}"
            ) from exc

        except URLError as exc:
            raise RuntimeError(
                "Unable to connect to GitHub API."
            ) from exc

    def find_open_pull_request(
        self,
        branch_name: str,
        base_branch: Optional[str] = None,
    ) -> Optional[PullRequestResult]:
        """
        Find an existing open Pull Request for a branch.

        Returns None when no matching open Pull Request exists.
        """

        branch_name = branch_name.strip()

        if not branch_name:
            raise ValueError(
                "Branch name cannot be empty."
            )

        if base_branch is None:
            base_branch = self.config.base_branch

        base_branch = base_branch.strip()

        if not base_branch:
            raise ValueError(
                "Base branch cannot be empty."
            )

        result = self._github_request(
            "GET",
            (
                f"/repos/"
                f"{self.config.owner}/"
                f"{self.config.repo}/"
                "pulls"
                "?state=open"
            ),
        )

        if not isinstance(
            result,
            list,
        ):
            raise RuntimeError(
                "GitHub did not return a valid "
                "Pull Request list."
            )

        for item in result:
            if not isinstance(
                item,
                dict,
            ):
                continue

            head = item.get(
                "head",
                {},
            )

            base = item.get(
                "base",
                {},
            )

            if not isinstance(
                head,
                dict,
            ):
                continue

            if not isinstance(
                base,
                dict,
            ):
                continue

            head_ref = head.get(
                "ref"
            )

            base_ref = base.get(
                "ref"
            )

            if (
                head_ref != branch_name
                or base_ref != base_branch
            ):
                continue

            number = item.get(
                "number"
            )

            url = item.get(
                "html_url"
            )

            title = item.get(
                "title",
                "Existing Pull Request",
            )

            if not isinstance(
                number,
                int,
            ):
                continue

            if not isinstance(
                url,
                str,
            ) or not url:
                continue

            if not isinstance(
                title,
                str,
            ):
                title = "Existing Pull Request"

            return PullRequestResult(
                number=number,
                url=url,
                title=title,
                branch=branch_name,
                base_branch=base_branch,
            )

        return None

    def create_pull_request(
        self,
        branch_name: str,
        title: str,
        body: str = "",
        base_branch: Optional[str] = None,
    ) -> PullRequestResult:
        """
        Create a Pull Request on GitHub.

        Duplicate detection is handled by PullRequestService.
        This method performs only the actual PR creation request.

        Args:
            branch_name:
                Source branch containing the changes.

            title:
                Pull Request title.

            body:
                Pull Request description.

            base_branch:
                Target branch. Defaults to configured base branch.

        Returns:
            PullRequestResult containing PR number and URL.
        """

        branch_name = branch_name.strip()
        title = title.strip()
        body = body.strip()

        if not branch_name:
            raise ValueError(
                "Branch name cannot be empty."
            )

        if not title:
            raise ValueError(
                "Pull Request title cannot be empty."
            )

        if base_branch is None:
            base_branch = (
                self.config.base_branch
            )

        base_branch = base_branch.strip()

        if not base_branch:
            raise ValueError(
                "Base branch cannot be empty."
            )

        payload = {
            "title": title,
            "head": branch_name,
            "base": base_branch,
            "body": body,
        }

        result = self._github_request(
            "POST",
            (
                f"/repos/"
                f"{self.config.owner}/"
                f"{self.config.repo}/"
                "pulls"
            ),
            payload,
        )

        number = result.get(
            "number"
        )

        url = result.get(
            "html_url"
        )

        if not isinstance(
            number,
            int,
        ):
            raise RuntimeError(
                "GitHub did not return a valid "
                "Pull Request number."
            )

        if not isinstance(
            url,
            str,
        ) or not url:
            raise RuntimeError(
                "GitHub did not return a valid "
                "Pull Request URL."
            )

        return PullRequestResult(
            number=number,
            url=url,
            title=title,
            branch=branch_name,
            base_branch=base_branch,
        )

    def create_pull_request_from_changes(
        self,
        branch_name: str,
        commit_message: str,
        pr_title: str,
        pr_body: str = "",
        files: Optional[list[str]] = None,
    ) -> PullRequestResult:
        """
        Complete the GitHub operation:

        1. Create branch
        2. Stage changes
        3. Commit changes
        4. Push branch
        5. Create Pull Request
        """

        self.validate_config()

        self.create_branch(
            branch_name
        )

        self.stage_changes(
            files
        )

        status = self.get_status()

        if not status:
            raise RuntimeError(
                "No changes are available to commit."
            )

        self.commit_changes(
            commit_message
        )

        self.push_branch(
            branch_name
        )

        return self.create_pull_request(
            branch_name=branch_name,
            title=pr_title,
            body=pr_body,
        )


__all__ = [
    "GitHubConfig",
    "GitHubClient",
    "PullRequestResult",
]