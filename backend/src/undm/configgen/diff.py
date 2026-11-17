"""Configuration comparison."""

import difflib
from dataclasses import dataclass


def normalize(text: str) -> list[str]:
    return [ln.rstrip() for ln in text.splitlines() if ln.strip()]


@dataclass(frozen=True)
class ConfigDiff:
    unified: str
    added: int
    removed: int

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def diff_configs(current: str, intended: str, label: str = "device") -> ConfigDiff:
    lines = list(
        difflib.unified_diff(
            normalize(current), normalize(intended),
            fromfile=f"{label} (current)", tofile=f"{label} (intended)", lineterm="",
        )
    )
    added = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))
    return ConfigDiff("\n".join(lines), added, removed)


def missing_lines(running: str, intended: str) -> list[str]:
    """Intended lines that are absent from the running configuration."""
    present = set(normalize(running))
    return [ln for ln in normalize(intended) if ln not in present]
