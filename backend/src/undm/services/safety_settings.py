"""Safety switches a person may change from Settings → Safety (D-082).

The switches start OFF (``undm.config.Settings`` defaults, rule 1) and are changed only by an
explicit, audited request. A change is kept in ``settings.json`` in the data folder, so it
lasts across restarts of this copy of UNDM and belongs to this copy only.

A switch given in the start-up settings (an ``UNDM_*`` environment variable or the ``.env``
file) wins and cannot be changed here: it is reported as locked.

Production switches are not offered: UNDM changes production devices only when its start-up
settings say so.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from undm.config import Settings

log = logging.getLogger("undm")

FILE_NAME = "settings.json"

# Switch -> what it means, in the words of the Settings page.
SWITCHES: dict[str, str] = {
    "enable_real_device_writes": "Approved plans may change real devices",
    "enable_real_device_firmware": "Approved firmware plans may upgrade real devices",
    "firmware_require_separate_approver": "A firmware plan needs a second person to approve it",
}


class SafetySettingsError(ValueError):
    """A request to change a switch that cannot be changed here."""


def _path(settings: Settings) -> Path:
    return Path(settings.data_dir) / FILE_NAME


def locked(settings: Settings) -> set[str]:
    """Switches fixed by the start-up settings (environment or ``.env``)."""
    return {name for name in SWITCHES if name in settings.model_fields_set}


def stored(settings: Settings) -> dict[str, bool]:
    """Switch values kept in the data folder. A damaged file counts as empty (all defaults)."""
    path = _path(settings)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log.warning("ignoring unreadable safety settings",
                    extra={"ctx": {"file": str(path), "error": str(e)}})
        return {}
    switches = raw.get("switches", {}) if isinstance(raw, dict) else {}
    if not isinstance(switches, dict):
        return {}
    return {k: v for k, v in switches.items() if k in SWITCHES and isinstance(v, bool)}


def effective(settings: Settings) -> Settings:
    """The settings in force now: start-up settings, then the stored switches not locked."""
    fixed = locked(settings)
    update = {k: v for k, v in stored(settings).items() if k not in fixed}
    return settings.model_copy(update=update) if update else settings


def change(settings: Settings, changes: dict[str, bool]) -> dict[str, tuple[bool, bool]]:
    """Store new switch values; returns ``{switch: (before, after)}`` for those that changed."""
    unknown = set(changes) - set(SWITCHES)
    if unknown:
        raise SafetySettingsError(
            f"not a switch that can be changed here: {', '.join(sorted(unknown))}")
    fixed = locked(settings) & set(changes)
    if fixed:
        raise SafetySettingsError(
            "set in the start-up settings (.env or environment), change it there: "
            + ", ".join(sorted(fixed)))
    now = effective(settings)
    done = {k: (bool(getattr(now, k)), v) for k, v in changes.items() if bool(getattr(now, k)) != v}
    if not done:
        return {}
    kept = stored(settings)
    kept.update({k: after for k, (_before, after) in done.items()})
    path = _path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write a temporary file and rename it, so a crash never leaves half a file.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"switches": kept}, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return done
