"""Small process-local rate limiter for local development and single-process deployments.

This is a defence-in-depth guardrail, not a distributed limiter. Public or multi-worker
deployments must also enforce limits at a trusted gateway and configure trusted proxy handling.
"""
from __future__ import annotations

from math import ceil
from threading import Lock
from time import monotonic


class InMemoryRateLimiter:
    """Thread-safe fixed-window limiter with bounded client-state memory."""

    def __init__(
        self,
        max_requests: int = 120,
        window_seconds: int = 60,
        max_clients: int = 10_000,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be at least 1")
        if max_clients < 1:
            raise ValueError("max_clients must be at least 1")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._lock = Lock()
        self._windows: dict[str, tuple[float, int]] = {}

    def check(self, client_key: str, *, now: float | None = None) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds); retry is zero when allowed.

        The optional clock makes tests deterministic. Client state is capped to prevent
        unbounded memory growth from requests carrying many different client addresses.
        """
        current = monotonic() if now is None else now
        key = client_key[:128] or "unknown"
        with self._lock:
            current_window = self._windows.get(key)
            if current_window is not None:
                started_at, count = current_window
                elapsed = current - started_at
                if elapsed >= self.window_seconds or elapsed < 0:
                    current_window = None
                elif count >= self.max_requests:
                    retry_after = max(1, ceil(self.window_seconds - elapsed))
                    return False, retry_after

            if current_window is None:
                if len(self._windows) >= self.max_clients:
                    # Evict the oldest window deterministically; state remains bounded.
                    oldest_key = min(self._windows, key=lambda item: self._windows[item][0])
                    del self._windows[oldest_key]
                self._windows[key] = (current, 1)
            else:
                self._windows[key] = (current_window[0], current_window[1] + 1)
            return True, 0

    def clear(self) -> None:
        """Clear counters, primarily for deterministic tests and controlled resets."""
        with self._lock:
            self._windows.clear()
