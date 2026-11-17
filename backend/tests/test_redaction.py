import json
import logging

from undm.logging_setup import JsonFormatter
from undm.security.redaction import REDACTED, redact, redact_text


def test_redact_keys_and_nested():
    out = redact({"username": "admin", "password": "x", "nested": [{"api_key": "k"}]})
    assert out == {"username": "admin", "password": REDACTED, "nested": [{"api_key": REDACTED}]}


def test_redact_cli_fragments():
    text = "username admin secret 5 $1$abc\nset password ENC Zm9v\nsnmp-server community public RO"
    out = redact_text(text)
    assert "$1$abc" not in out and "Zm9v" not in out and "public" not in out
    assert "username admin" in out


def test_log_formatter_redacts():
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "login password hunter2", None, None)
    rec.ctx = {"token": "abc"}
    line = json.loads(JsonFormatter().format(rec))
    assert "hunter2" not in line["msg"] and line["ctx"]["token"] == REDACTED
