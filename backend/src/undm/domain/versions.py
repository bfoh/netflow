"""Firmware version comparison.

Vendors format versions differently (``17.09.04a``, ``FL.10.13.1000``,
``v7.2.8,build1639``). Comparison uses the sequence of numbers in the string.
When either side has no numbers the result is ``None`` (unknown), and callers
must treat that as "cannot verify", never as "equal".
"""

import re

_NUM = re.compile(r"\d+")


def numeric_key(version: str) -> tuple[int, ...] | None:
    nums = tuple(int(n) for n in _NUM.findall(version))
    return nums or None


def compare(a: str, b: str) -> int | None:
    """-1 if a < b, 0 if equal, 1 if a > b, None if not comparable."""
    ka, kb = numeric_key(a), numeric_key(b)
    if ka is None or kb is None:
        return None
    width = max(len(ka), len(kb))
    pa, pb = ka + (0,) * (width - len(ka)), kb + (0,) * (width - len(kb))
    return (pa > pb) - (pa < pb)
