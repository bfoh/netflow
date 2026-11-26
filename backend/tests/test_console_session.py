"""The console session (provisioning/console.py): questions found at once, control characters
dropped and counted, raw characters kept for diagnostics (D-112, bench 2026-11-26)."""

import contextlib
import re
import time
from collections import Counter

from undm.provisioning.console import ConsoleSession, ConsoleTimeoutError, clean, visible


class Script:
    """Returns the given chunks one per read, then nothing (or ``forever`` on every read)."""

    def __init__(self, chunks, forever=b""):
        self.chunks = list(chunks)
        self.forever = forever

    def read(self, size=1):
        return self.chunks.pop(0) if self.chunks else self.forever

    def write(self, data):
        return len(data)

    def close(self):
        pass


Q = re.compile(r"Question one\?")
R = re.compile(r"Question two\?")


def test_wait_for_finds_a_question_mid_output_and_returns_at_once():
    s = ConsoleSession(Script([b"start\r\nQuestion two? and Question one?\b\b more text"]))
    t0 = time.monotonic()
    idx, text = s.wait_for([Q, R], timeout=2)
    assert time.monotonic() - t0 < 0.5
    # The earliest match wins, whatever the order of the patterns; the rest stays unread.
    assert idx == 1 and text.endswith("Question two?")
    idx, text = s.wait_for([Q, R], timeout=2)
    assert idx == 0 and text == " and Question one?"
    assert s.wait_for([re.compile("more text")], timeout=1)[1] == " more text"


def test_wait_for_times_out_with_the_output_in_the_transcript():
    s = ConsoleSession(Script([b"nothing asked here"]))
    try:
        s.wait_for([Q], timeout=0.2)
    except ConsoleTimeoutError as e:
        assert "nothing asked here" in str(e)
    else:
        raise AssertionError("expected a timeout")
    assert "nothing asked here" in s.transcript_text


def test_control_characters_are_dropped_counted_and_kept_raw():
    counts: Counter[str] = Counter()
    assert clean("a\r\nb\rc\b\b\x00\x07d\te\x1bf", counts) == "a\nbcd\tef"
    assert dict(counts) == {"\\r": 1, "\\b": 2, "\\x00": 1, "\\x07": 1, "\\e": 1}
    assert visible("ok\r\n\b\x00") == "ok\\r\n\\b\\x00"
    s = ConsoleSession(Script([b"Password: Example-Secret-1\b\b\r\n"]))
    s.secrets.append("Example-Secret-1")
    s.wait_for([re.compile("Password:")], timeout=1)
    s._fill()  # noqa: SLF001 - nothing more arrives
    assert s.raw_tail() == "Password: ********\\b\\b\\r\n" and s.received == 30
    assert s.ignored["\\b"] == 2 and "Example-Secret-1" not in s.transcript_text


def test_a_device_that_keeps_sending_cannot_hold_a_prompt_past_the_deadline():
    # A matched prompt waits for the output to pause; output that never pauses used to keep
    # it waiting for ever. Control characters alone no longer count as output at all.
    nul = ConsoleSession(Script([b"host# "], forever=b"\x00"), settle_time=0.15)
    t0 = time.monotonic()
    assert nul.read_until_any([re.compile(r"host# $")], timeout=3)[0] == 0
    assert time.monotonic() - t0 < 1
    dots = ConsoleSession(Script([b"host# "], forever=b"."), settle_time=0.15)
    t0 = time.monotonic()
    with contextlib.suppress(ConsoleTimeoutError):
        dots.read_until_any([re.compile(r"host# ")], timeout=0.5)
    assert time.monotonic() - t0 < 1.5  # ends at the deadline either way
