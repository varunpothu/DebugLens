from app.redaction import redact_sensitive_text


def test_redacts_email_and_personal_identifiers() -> None:
    source = "Contact alex@example.com; reference NI AB123456C."
    result = redact_sensitive_text(source)
    assert result is not None
    assert "alex@example.com" not in result
    assert "AB123456C" not in result
    assert result.count("[REDACTED]") == 2


def test_redacts_labeled_secrets_and_bearer_tokens() -> None:
    source = 'password="correct-horse", api_key: sk-example-secret Authorization: Bearer abcdefghijklmnop'
    result = redact_sensitive_text(source)
    assert result is not None
    assert "correct-horse" not in result
    assert "sk-example-secret" not in result
    assert "abcdefghijklmnop" not in result
    assert "[REDACTED]" in result


def test_redacts_cloud_and_source_control_tokens() -> None:
    source = "AWS=AKIA1234567890ABCDEF ghp_abcdefghijklmnopqrstuvwxyz123456"
    result = redact_sensitive_text(source)
    assert result is not None
    assert "AKIA1234567890ABCDEF" not in result
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in result


def test_redacts_payment_card_shaped_numbers_but_preserves_viewport() -> None:
    source = "Viewport 390x844, card 4111 1111 1111 1111"
    result = redact_sensitive_text(source)
    assert result is not None
    assert "390x844" in result
    assert "4111 1111 1111 1111" not in result


def test_none_and_empty_values_are_preserved() -> None:
    assert redact_sensitive_text(None) is None
    assert redact_sensitive_text("") == ""


def test_redacts_private_key_block() -> None:
    source = "key=-----BEGIN PRIVATE KEY-----\nvery-secret\n-----END PRIVATE KEY-----"
    result = redact_sensitive_text(source)
    assert result is not None
    assert "very-secret" not in result
    assert "BEGIN PRIVATE KEY" not in result
