import pytest

from app.browser.capture import UnsafeTargetError, validate_target_url


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
        "https://unapproved.example.net/",
    ],
)
def test_unsafe_targets_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeTargetError):
        validate_target_url(url, {"demo.example.org"})


def test_allowlist_is_exact_not_suffix_based() -> None:
    with pytest.raises(UnsafeTargetError):
        validate_target_url("https://demo.example.org.attacker.net/", {"demo.example.org"})
