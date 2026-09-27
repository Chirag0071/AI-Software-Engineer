"""
GitHub integration utilities.

This module provides the foundation for creating branches,
committing changes, pushing branches, and creating pull
requests.

GitHub operations are intentionally kept separate from the
LangGraph workflow so they can be tested independently.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


@dataclass
class GitHubConfig:
    """
    GitHub configuration loaded from environment variables.
    """

    token: str
    owner: str
    repo: str


class GitHubClient:
    """
    Client for Git and GitHub operations.

    The local repository is modified through Git commands.
    GitHub-specific Pull Request creation is handled through
    the GitHub REST API in a later step.

    This class does not automatically execute any operation
    when it is instantiated.
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

        token = os.getenv(
            "GITHUB_TOKEN",
            "",
        ).strip()

        owner = os.getenv(
            "GITHUB_OWNER",
            "",
        ).strip()

        repo = os.getenv(
            "GITHUB_REPO",
            "",
        ).strip()

        return GitHubConfig(
            token=token,
            owner=owner,
            repo=repo,
        )

    def validate_config(self) -> None:
        """
        Validate required GitHub configuration.

        Raises:
            ValueError: If required configuration is missing.
        """

        missing = []

        if not self.config.token:
            missing.append("GITHUB_TOKEN")

        if not self.config.owner:
            missing.append("GITHUB_OWNER")

        if not self.config.repo:
            missing.append("GITHUB_REPO")

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

        Args:
            *args: Git command arguments.

        Returns:
            Standard output from Git.

        Raises:
            RuntimeError: If Git exits with a non-zero status.
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

        Args:
            branch_name: Name of the new branch.

        Returns:
            Created branch name.
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
        Otherwise all tracked/untracked changes are staged.
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
        Commit staged changes.

        Returns:
            Commit SHA.
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

        The repository's existing Git credential configuration
        is used for authentication. The GitHub token is not
        inserted into the remote URL.
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
        Create a new branch and return its name.
        """

        return self.create_branch(
            branch_name
        )


__all__ = [
    "GitHubConfig",
    "GitHubClient",
]