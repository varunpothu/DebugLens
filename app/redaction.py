"""Conservative text redaction before external vision-provider calls.

This is defence-in-depth for text fields, not a guarantee that screenshots, source code,
DOM captures, or arbitrary encoded data contain no sensitive information.
"""
from __future__ import annotations

import re

_REPLACEMENT = "[REDACTED]"
_LABELED_SECRET = re.compile(
    r"""(?ix)(\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization)\b\s*["']?\s*[:=]\s*["']?)([^\s,"'\x60}]+)"""
)
_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b[A-CEGHJ-PR-TW-Z]{2}\d{6}[A-D]\b", re.IGNORECASE),
    re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
)


def redact_sensitive_text(value: str | None) -> str | None:
    """Mask common credential and personal-data patterns in free text.

    Returns None unchanged. This deterministic helper does not log or retain the original.
    It is a defence-in-depth measure, not a DLP guarantee.
    """
    if value is None:
        return None
    # Remove the complete bearer credential before processing labelled keys.
    redacted = _PATTERNS[0].sub(_REPLACEMENT, value)
    redacted = _LABELED_SECRET.sub(
        lambda match: match.group(1) + _REPLACEMENT,
        redacted,
    )
    for pattern in _PATTERNS[1:]:
        redacted = pattern.sub(_REPLACEMENT, redacted)
    return redacted
