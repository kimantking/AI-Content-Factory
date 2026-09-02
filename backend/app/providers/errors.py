from __future__ import annotations


class ProviderError(Exception):
    """Base class. error_type must be one of the retry taxonomy values."""

    error_type = "PROVIDER_ERROR"

    def __init__(self, message: str, error_type: str | None = None):
        super().__init__(message)
        if error_type:
            self.error_type = error_type


class TimeoutError_(ProviderError):
    error_type = "TIMEOUT"


class RateLimitError(ProviderError):
    error_type = "RATE_LIMIT"


class AuthError(ProviderError):
    error_type = "AUTH_ERROR"


class InvalidOutputError(ProviderError):
    error_type = "INVALID_OUTPUT"


class InsufficientResearchError(ProviderError):
    error_type = "INSUFFICIENT_RESEARCH"


# Errors that must NOT be retried (retry would be meaningless).
NON_RETRYABLE = {"AUTH_ERROR", "BUDGET_EXCEEDED"}

RETRY_TAXONOMY = {
    "TIMEOUT",
    "RATE_LIMIT",
    "AUTH_ERROR",
    "BUDGET_EXCEEDED",
    "INVALID_OUTPUT",
    "PROVIDER_ERROR",
    "INSUFFICIENT_RESEARCH",
}
