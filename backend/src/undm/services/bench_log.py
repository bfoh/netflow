"""A masked bench log of one system, to send instead of screenshots (D-090).

Everything UNDM recorded about the system's devices in a time window, as plain text:
the safety switches in force, each device as last read, each console setup, and each
plan with all of its events. Identifying values are masked with the diagnostics sanitizer
(``security/sanitize.py``): addresses, MACs, serials and names, plus the values UNDM knows
belong to this system (its name and site, device names, hostnames read from the devices or
written in the plans' files, login names, people's names) and double-quoted names in event
text (FortiOS objects such as tunnels or VIPs). Masking is best effort: the person reads the
text before sharing it. Nothing is sent anywhere by UNDM.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from undm import __version__
from undm.config import Settings
from undm.db.models import AuditEvent, ConfigVersion, DeploymentRecord, Device, Project
from undm.drivers.registry import DriverRegistry
from undm.security.sanitize import new_mapper, sanitize
from undm.services import audit
from undm.services.safety_settings import effective

_FILE_HOSTNAME = re.compile(r'^\s*(?:set\s+)?hostname\s+"?([^"\s]+)"?', re.M | re.I)
_QUOTED = re.compile(r'"([^"\n]{3,80})"')
# Revisions are named after the file (``services/deployments.py``): "revision 'name' saved".
_REVISION = re.compile(r"(revision ')([^'\n]{1,80})(')")


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _when(value: datetime | None) -> str:
    v = _utc(value)
    return v.strftime("%Y-%m-%d %H:%M:%S UTC") if v else "—"


def bench_log(session: Session, project: Project, registry: DriverRegistry, settings: Settings,
              actor: str, since: datetime | None) -> str:
    devices = list(session.scalars(select(Device).where(Device.project_id == project.id)
                                   .order_by(Device.name)))
    device_ids = {d.id for d in devices}
    plans = [p for p in session.scalars(
        select(DeploymentRecord).where(DeploymentRecord.project_id == project.id)
        .order_by(DeploymentRecord.created_at))
        if since is None or (_utc(p.created_at) or since) >= since]
    setups = [a for a in session.scalars(
        select(AuditEvent).where(AuditEvent.action.like("provisioning.console_bootstrap%"))
        .order_by(AuditEvent.timestamp))
        if a.target_id in device_ids and (since is None or (_utc(a.timestamp) or since) >= since)]

    # What belongs to this system and must not leave the bench in clear.
    known: list[tuple[str, str]] = [("system", project.name), ("site", project.site)]
    known += [("login", r.name) for r in project.credential_refs]
    for d in devices:
        facts = dict(d.observed_facts or {})
        extra = dict(facts.get("extra") or {})
        known += [("device", d.name), ("hostname", str(facts.get("hostname") or "")),
                  ("serial", str(facts.get("serial_number") or "")),
                  ("mac", str(extra.get("mac_address") or "")), ("site", d.site),
                  ("rack", d.rack_location)]
    version_ids = {t.config_version_id for p in plans for t in p.targets if t.config_version_id}
    for v in session.scalars(select(ConfigVersion).where(ConfigVersion.id.in_(version_ids))):
        known += [("hostname", m.group(1)) for m in _FILE_HOSTNAME.finditer(v.text)]
        # The file name, and the name without its extension that revisions carry (bench
        # 2026-11-25: a revision named after the site file showed the site code in clear).
        stem = PurePath(v.reference).stem if v.reference else ""
        known += [("file", v.reference), ("file", stem), ("file", stem[:60])]
    people = {p.created_by for p in plans} | {p.approved_by or "" for p in plans}
    people |= {a.actor for a in setups} | {actor}
    known += [("person", name) for name in people if name and name != "local-user"]
    for a in setups:
        for key in ("erased_hostname", "current_login", "credential"):
            known.append(("name", str(a.details.get(key) or "")))
    # A factory hostname is often just the model (e.g. "FortiGate-101F"): that says nothing
    # about the system and is kept, so the log still names the models.
    generic = {v.lower() for d in devices for v in (d.model, d.manufacturer, d.product_family) if v}
    known = [(kind, value) for kind, value in known if value and value.lower() not in generic]
    mapper = new_mapper()

    def s(text: object) -> str:
        out = sanitize(str(text), known, mapper)
        out = _REVISION.sub(lambda m: m.group(0) if m.group(2).startswith("<")
                            else f"{m.group(1)}{mapper('file', m.group(2))}{m.group(3)}", out)
        # FortiOS object names in quotes (tunnels, VIPs, VDOMs); placeholders stay as they are.
        return _QUOTED.sub(lambda m: m.group(0) if m.group(1).startswith("<")
                           else f'"{mapper("name", m.group(1))}"', out)

    name_of = {d.id: s(d.name) for d in devices}
    live = effective(settings)
    now = datetime.now(UTC)
    lines = [
        "UNDM bench log (masked)",
        f"UNDM {__version__} · made {_when(now)} · covers "
        + (f"since {_when(since)}" if since else "everything recorded"),
        f"system: {s(project.name)} · {len(devices)} devices · {len(plans)} plans · "
        f"{len(setups)} console setups",
        "safety switches: real-device changes "
        f"{'ON' if live.enable_real_device_writes else 'off'} · firmware changes "
        f"{'ON' if live.enable_real_device_firmware else 'off'} · second approver for firmware "
        f"{'on' if live.firmware_require_separate_approver else 'off'}",
        "",
        "== devices ==",
    ]
    for d in devices:
        info = registry.get(d.driver_id).info if d.driver_id in registry else None
        facts = dict(d.observed_facts or {})
        extra = dict(facts.pop("extra", None) or {})
        extra.pop("raw_output", None)
        lines.append(f"- {name_of[d.id]}: {d.manufacturer} {d.model} · {d.environment} · "
                     f"{d.driver_id}" + (f" ({info.maturity.value})" if info else "")
                     + f" · setup {d.provisioning_status} · status {d.deployment_status}")
        read: dict[str, Any] = {k: v for k, v in {**facts, **extra}.items()
                                if v not in (None, "") and not isinstance(v, dict | list)}
        if read:
            lines.append(f"  read {_when(d.facts_retrieved_at)}: "
                         + "; ".join(f"{k}={s(v)}" for k, v in read.items()))
    if setups:
        lines += ["", "== console setups =="]
        for a in setups:
            det = a.details
            lines.append(f"- {_when(a.timestamp)} {name_of.get(a.target_id, '?')}: {a.outcome}"
                         f" · erase {bool(det.get('erase_existing'))}"
                         f" · verified {det.get('verified')} · saved {det.get('saved')}")
            if det.get("message"):
                lines.append(f"  {s(det['message'])}")
            for f in det.get("findings") or []:
                lines.append(f"  finding: {s(f)}")
            if det.get("transcript_tail"):  # a failed setup keeps the console's last words
                lines.append("  console (last lines):")
                lines += [f"    {s(ln)}" for ln in str(det["transcript_tail"]).splitlines()]
    lines += ["", "== plans =="]
    for p in plans:
        flags = []
        if p.dry_run:
            flags.append("dry run")
        if p.staging_id:
            flags.append(f"staging {p.staging_id[:8]} step {p.staging_step}")
        lines += ["", f"--- {_when(p.created_at)} {p.kind} ({p.apply_mode}"
                  + (", " + ", ".join(flags) if flags else "") + f") → {p.state}"
                  + (f" · approved by {s(p.approved_by)}" if p.approved_by else "")]
        for t in p.targets:
            versions = (f" · {t.from_version or '?'} → {t.to_version}" if t.to_version else "")
            lines.append(f"  target {name_of.get(t.device_id, '?')}: {t.state}{versions}"
                         + (f" · {s(t.message)}" if t.message else ""))
        for e in p.events:
            who = f" {name_of.get(e.device_id, '?')}" if e.device_id else ""
            lines.append(f"  {_when(e.timestamp)[11:19]} {e.stage}{who} [{e.status}] "
                         f"{s(e.message)}")
    lines += ["", "Masking is automatic and best effort: read it before sharing."]
    audit.record(session, actor, "system.bench_log", "project", project.id,
                 details={"plans": len(plans), "console_setups": len(setups),
                          "since": since.isoformat() if since else None})
    return "\n".join(lines) + "\n"
