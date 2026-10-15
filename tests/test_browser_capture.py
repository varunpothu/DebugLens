import pytest

from app.browser.capture import UnsafeTargetError, _assert_public_dns_resolution, validate_target_url


def test_dns_preflight_rejects_private_resolutions(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.browser.capture.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("192.168.1.10", 0))],
    )
    with pytest.raises(UnsafeTargetError, match="private or non-global"):
        _assert_public_dns_resolution("demo.example.org")


def test_dns_preflight_accepts_public_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.browser.capture.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("8.8.8.8", 0))],
    )
    _assert_public_dns_resolution("demo.example.org")


def test_dns_preflight_rejects_unresolvable_hostname(monkeypatch) -> None:
    def fail_resolution(*args, **kwargs):
        raise OSError("DNS unavailable")

    monkeypatch.setattr("app.browser.capture.socket.getaddrinfo", fail_resolution)
    with pytest.raises(UnsafeTargetError, match="could not be resolved"):
        _assert_public_dns_resolution("demo.example.org")


def test_allowlisted_hostname_is_accepted() -> None:
    assert validate_target_url("https://demo.example.org/page", {"demo.example.org"}) == "demo.example.org"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://192.168.1.1/",
        "https://user:password@demo.example.org/",
        "https://demo.example.org:8443/",
        "http://demo.example.org:8080/",
        "https://demo.example.org:invalid/",
        "https://unapproved.example.net/",
    ],
)
def test_unsafe_targets_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeTargetError):
        validate_target_url(url, {"demo.example.org"})


def test_allowlist_is_exact_not_suffix_based() -> None:
    with pytest.raises(UnsafeTargetError):
        validate_target_url("https://demo.example.org.attacker.net/", {"demo.example.org"})
