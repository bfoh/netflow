"""Remove secrets from data before it reaches logs or the audit trail."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "***REDACTED***"
_SECRET_KEY = re.compile(
    r"(pass(word|wd|phrase)?|secret|token|api[_-]?key|private[_-]?key|community|psk)", re.I
)
# CLI fragments such as "password 0 foo", "set password ENC xyz", "secret 5 $1$..."
_SECRET_IN_TEXT = re.compile(
    r"(?P<kw>\b(?:password|passwd|secret|community|key-string|psksecret|passphrase)\b"
    r"(?:\s+(?:ENC|\d))?\s+)(?P<val>\S+)",
    re.I,
)


def redact_text(text: str) -> str:
    return _SECRET_IN_TEXT.sub(lambda m: m.group("kw") + REDACTED, text)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (REDACTED if isinstance(k, str) and _SECRET_KEY.search(k) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
