"""Process-local provider request budget.

This is a burst guardrail for one application process, not a distributed quota or billing cap.
"""
from __future__ import annotations

from app.rate_limit import InMemoryRateLimiter


class ProviderRateLimitError(RuntimeError):
    """Raised when a provider's local request budget is exhausted."""

    def __init__(self, provider: str, retry_after_seconds: int) -> None:
        self.provider = provider
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__(f"Provider '{provider}' is rate limited; retry after the current window.")


class ProviderCallBudget:
    """Apply a bounded fixed-window request budget independently to each provider."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60) -> None:
        self._limiter = InMemoryRateLimiter(
            max_requests=max_requests,
            window_seconds=window_seconds,
            max_clients=16,
        )

    def check(self, provider: str) -> None:
        """Allow a call or raise a provider-specific rate-limit error."""
        allowed, retry_after = self._limiter.check(provider)
        if not allowed:
            raise ProviderRateLimitError(provider, retry_after)

    def clear(self) -> None:
        """Reset local counters, primarily for tests and controlled local operations."""
        self._limiter.clear()
