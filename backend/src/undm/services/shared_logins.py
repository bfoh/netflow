"""Bring the systems' own logins into the logins for all systems (D-115).

Product owner, 2026-11-26: every system of the project uses the same logins, so the logins
made per system before D-105 should be available to all systems, under clear names.

- Logins with the same user name and password are one login: the oldest is kept (or the
  login for all systems that already has them), the others' devices and plans move to it and
  they are removed, with their stored password.
- Each new login for all systems gets a suggested name from what uses it: the devices'
  manufacturer and model, then its user name ("Aruba 2930F – manager"), or "tunnel key" for
  the pre-shared key of a site file. The person can change every name before confirming.
- A login nothing uses keeps its name. Logins without a stored password are never merged.

Passwords are compared here, in memory, and never returned, logged or audited.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from undm.db.models import (
    CredentialRef,
    DeploymentRecord,
    DeploymentTargetRecord,
    Device,
    Project,
)
from undm.domain.lifecycle import TRANSIENT_STATES
from undm.security import credentials as creds
from undm.services import app_settings, audit
from undm.services.errors import ConflictError, ServiceError

NAME_MAX = 120


@dataclass
class Member:
    id: str
    name: str
    system: str
    devices: int


@dataclass
class Group:
    """One login for all systems, made from one or more systems' logins."""

    id: str  # the login kept
    name: str  # suggested; for an existing login for all systems, its name
    existing: bool = False  # joins a login that is already for all systems
    members: list[Member] = field(default_factory=list)
    devices: int = 0


def _secret(ref: CredentialRef) -> tuple[str, str] | None:
    try:
        c = creds.resolve(ref.provider, ref.locator)
    except (creds.CredentialResolutionError, creds.CredentialStoreError):
        return None  # no password stored: kept apart, never guessed
    return c.username, c.password


def _label(device: Device) -> str:
    words = f"{device.manufacturer} {device.model}".split() or [device.category]
    return " ".join(dict.fromkeys(words))


def _uses(session: Session, ids: set[str]) -> tuple[list[str], set[str], bool]:
    """Device labels, kinds of use (login / after / secret) and whether a secret is a PSK."""
    labels: set[str] = set()
    kinds: set[str] = set()
    psk = False
    for d in session.scalars(select(Device).where(Device.credential_ref_id.in_(ids))):
        labels.add(_label(d))
        kinds.add("login")
    for t in session.scalars(select(DeploymentTargetRecord)):
        slots = [k for k, v in (t.secret_refs or {}).items() if v in ids]
        after = t.credential_after_ref_id in ids
        if not slots and not after:
            continue
        device = session.get(Device, t.device_id)
        if device is not None:
            labels.add(_label(device))
        if after:
            kinds.add("after")
        if slots:
            kinds.add("secret")
            psk = psk or any(k.rstrip().endswith("psksecret") for k in slots)
    return sorted(labels), kinds, psk


def _suggest(session: Session, group: Group, secret: tuple[str, str] | None) -> str:
    labels, kinds, psk = _uses(session, {m.id for m in group.members})
    if not labels:
        return group.members[0].name
    subject = labels[0] if len(labels) == 1 else (
        " and ".join(labels) if len(labels) == 2 else "All devices")
    if kinds == {"secret"}:
        return f"{subject} – {'tunnel key' if psk else 'file secret'}"
    name = f"{subject} – {secret[0] if secret else group.members[0].name}"
    return name + (" (no password)" if secret is not None and secret[1] == "" else "")


def _unique(groups: list[Group], taken: set[str]) -> None:
    new = [g for g in groups if not g.existing]
    clash = Counter(g.name.casefold() for g in new)
    used = {t.casefold() for t in taken}
    for g in new:
        if clash[g.name.casefold()] > 1 or g.name.casefold() in used:
            first = g.members[0]
            g.name = f"{g.name} ({first.system if g.name == first.name else first.name})"
        base, n = g.name[:NAME_MAX], 2
        g.name = base
        while g.name.casefold() in used:
            suffix = f" {n}"
            g.name, n = base[:NAME_MAX - len(suffix)] + suffix, n + 1
        used.add(g.name.casefold())


def plan(session: Session) -> list[Group]:
    """What bringing the systems' logins in would do, oldest systems' logins first."""
    shared = app_settings.shared_logins(session)
    by_secret: dict[tuple[str, str], Group] = {}
    for s in shared:
        secret = _secret(s)
        if secret is not None:
            by_secret.setdefault(secret, Group(s.id, s.name, existing=True))
    rows = session.execute(
        select(CredentialRef, Project.name)
        .join(Project, CredentialRef.project_id == Project.id)
        .order_by(Project.created_at, Project.name, CredentialRef.created_at,
                  CredentialRef.name)).all()
    out: list[Group] = []
    secrets: dict[str, tuple[str, str] | None] = {}
    for ref, system in rows:
        secret = _secret(ref)
        used = len(session.scalars(select(Device.id).where(
            Device.credential_ref_id == ref.id)).all())
        group = by_secret.get(secret) if secret is not None else None
        if group is None:
            group = Group(ref.id, ref.name)
            secrets[ref.id] = secret
            if secret is not None:
                by_secret[secret] = group
        if not group.members:
            out.append(group)
        group.members.append(Member(ref.id, ref.name, system, used))
        group.devices += used
    for g in out:
        if not g.existing:
            g.name = _suggest(session, g, secrets.get(g.id))
    _unique(out, {s.name for s in shared})
    return out


def _repoint(session: Session, old: str, new: str) -> None:
    for device in session.scalars(select(Device).where(Device.credential_ref_id == old)):
        device.credential_ref_id = new
    for target in session.scalars(select(DeploymentTargetRecord)):
        if target.credential_after_ref_id == old:
            target.credential_after_ref_id = new
        if target.secret_refs and old in target.secret_refs.values():
            target.secret_refs = {k: new if v == old else v
                                  for k, v in target.secret_refs.items()}


def share_all(session: Session, actor: str,
              names: dict[str, str] | None = None) -> tuple[list[Group], dict[str, str]]:
    """Make every system's login a login for all systems, under the names given (by the id
    of the login kept) or suggested. Returns the groups and, for the logins that became
    one, old id -> the id that replaces it."""
    running = session.scalars(select(DeploymentRecord.id).where(
        DeploymentRecord.state.in_([s.value for s in TRANSIENT_STATES]))).first()
    if running is not None:
        raise ConflictError("A plan is running: bring the logins in once it has finished")
    groups = plan(session)
    taken = {s.name.casefold() for s in app_settings.shared_logins(session)}
    for g in groups:
        if g.existing:
            continue
        name = " ".join((names or {}).get(g.id, g.name).split())
        if not name or len(name) > NAME_MAX:
            raise ServiceError(f"Give each login a name of 1 to {NAME_MAX} characters")
        if name.casefold() in taken:
            raise ConflictError(f"Two logins for all systems would be called '{name}'")
        taken.add(name.casefold())
        g.name = name
    replaced: dict[str, str] = {}
    kept_secrets: list[str] = []
    for g in groups:
        keep = session.get(CredentialRef, g.id)
        assert keep is not None
        if not g.existing:
            keep.project_id, keep.name = None, g.name
        for m in g.members:
            if m.id == g.id:
                continue
            ref = session.get(CredentialRef, m.id)
            assert ref is not None
            _repoint(session, ref.id, keep.id)
            replaced[ref.id] = keep.id
            if ref.provider == "keyring" and ref.locator != keep.locator:
                try:
                    creds.delete_secret(ref.provider, ref.locator)
                except creds.CredentialStoreError:
                    kept_secrets.append(ref.name)
            session.delete(ref)
    session.flush()
    audit.record(session, actor, "credential_ref.share_all", "credential_ref", "all", details={
        "logins": [{"name": g.name, "joined": g.existing,
                    "from": [f"{m.name} ({m.system})" for m in g.members]} for g in groups],
        "stored_logins_not_removed": kept_secrets,
    })
    return groups, replaced
