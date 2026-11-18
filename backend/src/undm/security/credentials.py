"""Credential references and the stores that hold the actual secrets.

UNDM's database only ever holds a *reference* (provider + locator). Secrets
live in one of these stores and are read at the moment a driver connects:

- ``keyring``: the operating system's credential store via the ``keyring``
  library (Windows Credential Manager, macOS Keychain, Linux Secret Service).
  Secrets are written through the API and can never be read back through it.
- ``env``: read-only, from ``UNDM_CRED_<LOCATOR>_USERNAME`` / ``_PASSWORD``
  environment variables of the backend process.
"""

from __future__ import annotations

import json
import os
import re

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from undm.drivers.base import Credentials

KEYRING_SERVICE = "UNDM"
PROVIDERS = ("keyring", "env")


class CredentialResolutionError(LookupError):
    pass


class CredentialStoreError(RuntimeError):
    pass


def _env_name(locator: str, part: str) -> str:
    return f"UNDM_CRED_{re.sub(r'[^A-Za-z0-9]', '_', locator).upper()}_{part}"


def _keyring_get(locator: str) -> Credentials | None:
    try:
        raw = keyring.get_password(KEYRING_SERVICE, locator)
    except KeyringError as e:
        raise CredentialStoreError(f"OS credential store unavailable: {e}") from e
    if raw is None:
        return None
    data = json.loads(raw)
    return Credentials(data["username"], data["password"])


def resolve(provider: str, locator: str) -> Credentials:
    if provider == "env":
        user = os.environ.get(_env_name(locator, "USERNAME"))
        pw = os.environ.get(_env_name(locator, "PASSWORD"))
        if not user or pw is None:
            raise CredentialResolutionError(
                f"Credential {locator!r} not set ({_env_name(locator, 'USERNAME')}/PASSWORD)"
            )
        return Credentials(user, pw)
    if provider == "keyring":
        try:
            creds = _keyring_get(locator)
        except CredentialStoreError as e:
            raise CredentialResolutionError(str(e)) from e
        if creds is None:
            raise CredentialResolutionError("No username/password stored for this credential yet")
        return creds
    raise CredentialResolutionError(f"Unknown credential provider {provider!r}")


def has_secret(provider: str, locator: str) -> bool | None:
    """True/False if known; None if the store cannot be queried."""
    try:
        resolve(provider, locator)
        return True
    except CredentialResolutionError:
        if provider == "keyring":
            try:
                return _keyring_get(locator) is not None
            except CredentialStoreError:
                return None
        return False


def store_secret(provider: str, locator: str, username: str, password: str) -> None:
    if provider != "keyring":
        raise CredentialStoreError(
            f"Provider {provider!r} is read-only; set its environment variables instead")
    try:
        keyring.set_password(KEYRING_SERVICE, locator,
                             json.dumps({"username": username, "password": password}))
    except KeyringError as e:
        raise CredentialStoreError(
            "No OS credential store is available on this machine. Use the 'env' provider, "
            f"or install a keyring backend ({e})") from e


def delete_secret(provider: str, locator: str) -> None:
    if provider != "keyring":
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, locator)
    except PasswordDeleteError:
        pass  # nothing stored
    except KeyringError as e:
        raise CredentialStoreError(f"OS credential store unavailable: {e}") from e
