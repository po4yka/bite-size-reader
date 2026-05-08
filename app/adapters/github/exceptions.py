"""GitHub API exception hierarchy."""

from __future__ import annotations


class GitHubError(Exception):
    """Base GitHub error."""


class GitHubAuthError(GitHubError):
    """401 Unauthorized: token revoked, expired, or insufficient scope."""


class GitHubNotFoundError(GitHubError):
    """404 Not Found: repo doesn't exist or token can't see it."""


class GitHubRateLimitError(GitHubError):
    """403 with X-RateLimit-Remaining: 0 — rate limit exceeded."""

    def __init__(self, reset_epoch: int, message: str = "GitHub rate limit exceeded") -> None:
        super().__init__(message)
        self.reset_epoch = reset_epoch


class GitHubServerError(GitHubError):
    """5xx after retries exhausted."""


class GitHubIntegrationRequiredError(GitHubError):
    """Raised when a GitHub operation needs an active integration but none exists."""


class InvalidGitHubTokenError(GitHubError):
    """The token failed validation against GitHub /user."""
