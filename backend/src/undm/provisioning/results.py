"""Result of a console setup procedure, whatever the device family."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class BootstrapStatus(StrEnum):
    BOOTSTRAPPED = "bootstrapped"
    ALREADY_CONFIGURED = "already_configured"
    REFUSED = "refused"
    FAILED = "failed"


@dataclass
class BootstrapResult:
    status: BootstrapStatus
    message: str
    commands_sent: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    verified: bool = False
    saved: bool = False
    transcript: str = ""
    credentials_set: bool = False  # a new switch's first-login credentials were set
    erased: str = ""  # hostname of the configuration that was erased first, if any
    # The approved login was refused and the switch was reached with the login it has now
    # (e.g. its password survived the erase): that login stays the switch's (D-102).
    kept_current_login: bool = False
    # The switch asked for no password and none was set: it has no manager password.
    no_password: bool = False
    # The switch had no manager password; UNDM set the device's login (verified).
    password_set: bool = False
    # What the device said about itself (name, type, version), where the procedure reads it.
    facts: dict[str, str] = field(default_factory=dict)
