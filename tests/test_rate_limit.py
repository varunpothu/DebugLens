from app.rate_limit import InMemoryRateLimiter


def test_allows_requests_until_window_limit() -> None:
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=10)
    assert limiter.check("client-a", now=100.0) == (True, 0)
    assert limiter.check("client-a", now=101.0) == (True, 0)
    assert limiter.check("client-a", now=102.0) == (False, 8)


def test_window_resets_after_expiry() -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=10)
    assert limiter.check("client-a", now=100.0) == (True, 0)
    assert limiter.check("client-a", now=109.0) == (False, 1)
    assert limiter.check("client-a", now=110.0) == (True, 0)


def test_clients_have_independent_windows() -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=10)
    assert limiter.check("client-a", now=100.0) == (True, 0)
    assert limiter.check("client-b", now=100.0) == (True, 0)
    assert limiter.check("client-a", now=101.0) == (False, 9)


def test_client_state_is_bounded() -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=10, max_clients=2)
    assert limiter.check("client-a", now=100.0) == (True, 0)
    assert limiter.check("client-b", now=101.0) == (True, 0)
    assert limiter.check("client-c", now=102.0) == (True, 0)
    assert len(limiter._windows) == 2


def test_rejects_invalid_configuration() -> None:
    import pytest

    with pytest.raises(ValueError):
        InMemoryRateLimiter(max_requests=0)
    with pytest.raises(ValueError):
        InMemoryRateLimiter(window_seconds=0)
