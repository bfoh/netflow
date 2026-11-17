"""Credential references.

UNDM stores *references* to credentials, never the secrets. The first
provider reads them from environment variables at the moment of use:

    UNDM_CRED_<LOCATOR>_USERNAME / UNDM_CRED_<LOCATOR>_PASSWORD

An OS keyring or vault provider will be added later behind the same interface.
"""

from __future__ import annotations

import os
import re

from undm.drivers.base import Credentials


class CredentialResolutionError(LookupError):
    pass


def _env_name(locator: str, part: str) -> str:
    return f"UNDM_CRED_{re.sub(r'[^A-Za-z0-9]', '_', locator).upper()}_{part}"


def resolve(provider: str, locator: str) -> Credentials:
    if provider != "env":
        raise CredentialResolutionError(f"Unknown credential provider {provider!r}")
    user = os.environ.get(_env_name(locator, "USERNAME"))
    pw = os.environ.get(_env_name(locator, "PASSWORD"))
    if not user or pw is None:
        raise CredentialResolutionError(
            f"Credential {locator!r} not set ({_env_name(locator, 'USERNAME')}/PASSWORD)"
        )
    return Credentials(user, pw)
