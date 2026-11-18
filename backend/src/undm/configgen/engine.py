"""Render device intent into platform configuration.

Each platform template declares the intent features it can express. Intent
that uses an unsupported feature is reported as a validation error instead of
being silently dropped.

Verification status of the bundled templates: syntax written from public
vendor documentation conventions and reviewed by hand; NOT yet verified on
lab equipment or pinned to specific firmware releases. Every generated config
carries this status so the UI and deployment approval can show it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from undm.domain.intent import DeviceIntent
from undm.domain.validation import Severity, ValidationIssue, has_errors, validate_intent

TEMPLATE_DIR = Path(__file__).parent / "templates"


class Feature(StrEnum):
    HOSTNAME = "hostname"
    VLANS = "vlans"
    PHYSICAL_INTERFACE_ADDRESS = "physical_interface_address"
    SVI_ADDRESS = "svi_address"
    INTERFACE_DESCRIPTION = "interface_description"
    STATIC_ROUTES = "static_routes"


class VerificationStatus(StrEnum):
    DOCS_REVIEWED = "docs_reviewed_not_lab_verified"
    LAB_VERIFIED = "lab_verified"


@dataclass(frozen=True)
class PlatformTemplate:
    platform: str
    template: str
    version: str
    features: frozenset[Feature]
    verification: VerificationStatus
    requires_route_egress_interface: bool = False


PLATFORMS: dict[str, PlatformTemplate] = {
    "iosxe": PlatformTemplate(
        "iosxe", "iosxe.j2", "0.1.0",
        frozenset(Feature), VerificationStatus.DOCS_REVIEWED,
    ),
    "aoscx": PlatformTemplate(
        "aoscx", "aoscx.j2", "0.1.0",
        frozenset({Feature.HOSTNAME, Feature.VLANS, Feature.SVI_ADDRESS,
                   Feature.INTERFACE_DESCRIPTION, Feature.STATIC_ROUTES}),
        VerificationStatus.DOCS_REVIEWED,
    ),
    # ArubaOS-Switch (formerly ProCurve), e.g. Aruba 2930F. Layer-3 addresses live in
    # VLAN contexts; there are no routed physical ports.
    "aos_switch": PlatformTemplate(
        "aos_switch", "aos_switch.j2", "0.1.0",
        frozenset({Feature.HOSTNAME, Feature.VLANS, Feature.SVI_ADDRESS, Feature.STATIC_ROUTES}),
        VerificationStatus.DOCS_REVIEWED,
    ),
    "fortios": PlatformTemplate(
        "fortios", "fortios.j2", "0.1.0",
        frozenset({Feature.HOSTNAME, Feature.PHYSICAL_INTERFACE_ADDRESS, Feature.STATIC_ROUTES}),
        VerificationStatus.DOCS_REVIEWED,
        requires_route_egress_interface=True,
    ),
}


def _iosxe_ifname(name: str) -> str:
    m = re.fullmatch(r"vlan(\d{1,4})", name, flags=re.IGNORECASE)
    return f"Vlan{m.group(1)}" if m else name


_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    autoescape=False,  # noqa: S701 - output is device CLI text, not HTML
)
_env.filters["iosxe_ifname"] = _iosxe_ifname


class UnknownPlatformError(KeyError):
    pass


@dataclass(frozen=True)
class GenerationResult:
    platform: str
    template_version: str
    verification: VerificationStatus
    issues: list[ValidationIssue] = field(default_factory=list)
    text: str | None = None

    @property
    def ok(self) -> bool:
        return self.text is not None

    @property
    def sha256(self) -> str | None:
        return hashlib.sha256(self.text.encode()).hexdigest() if self.text is not None else None


def required_features(intent: DeviceIntent) -> dict[Feature, str]:
    """Features the intent uses, mapped to the intent path that needs them."""
    used: dict[Feature, str] = {Feature.HOSTNAME: "hostname"}
    if intent.vlans:
        used[Feature.VLANS] = "vlans"
    for idx, i in enumerate(intent.interfaces):
        feat = Feature.SVI_ADDRESS if i.svi_vlan is not None else Feature.PHYSICAL_INTERFACE_ADDRESS
        used.setdefault(feat, f"interfaces[{idx}]")
        if i.description:
            used.setdefault(Feature.INTERFACE_DESCRIPTION, f"interfaces[{idx}].description")
    if intent.static_routes:
        used[Feature.STATIC_ROUTES] = "static_routes"
    return used


def check_platform_support(intent: DeviceIntent, platform: str) -> list[ValidationIssue]:
    tpl = PLATFORMS.get(platform)
    if tpl is None:
        raise UnknownPlatformError(platform)
    issues = [
        ValidationIssue(
            Severity.ERROR, "feature_not_supported_by_platform",
            f"{feature.value} is not supported by the {platform} template v{tpl.version}",
            path,
        )
        for feature, path in required_features(intent).items()
        if feature not in tpl.features
    ]
    if platform == "aos_switch" and intent.static_routes:
        issues.append(ValidationIssue(
            Severity.WARNING, "aos_switch_routes_need_ip_routing",
            "ArubaOS-Switch uses 'ip route' entries only when IP routing is enabled on the "
            "switch; this template does not enable it (a management-only default gateway is "
            "configured differently and is not modelled yet)",
            "static_routes",
        ))
    if platform == "fortios" and intent.static_routes:
        issues.append(ValidationIssue(
            Severity.WARNING, "fortios_static_route_ids_overwrite",
            f"FortiOS static routes are written as entries 1..{len(intent.static_routes)}; on a "
            "real device this overwrites existing routes with the same IDs",
            "static_routes",
        ))
    if tpl.requires_route_egress_interface:
        issues += [
            ValidationIssue(
                Severity.ERROR, "egress_interface_required",
                f"{platform} static routes require an egress interface",
                f"static_routes[{idx}].egress_interface",
            )
            for idx, r in enumerate(intent.static_routes)
            if not r.egress_interface
        ]
    return issues


def _vlan_context(intent: DeviceIntent) -> dict[str, object]:
    """VLAN-centric view used by templates that group settings per VLAN (ArubaOS-Switch)."""
    names = {v.vlan_id: v.name for v in intent.vlans if v.name}
    svis = {i.svi_vlan: i.address for i in intent.interfaces if i.svi_vlan is not None}
    ids = sorted({v.vlan_id for v in intent.vlans} | set(svis))
    return {"vlan_ids": ids, "vlan_names": names, "svi_addresses": svis}


def generate(intent: DeviceIntent, platform: str) -> GenerationResult:
    tpl = PLATFORMS.get(platform)
    if tpl is None:
        raise UnknownPlatformError(platform)
    issues = validate_intent(intent) + check_platform_support(intent, platform)
    if has_errors(issues):
        return GenerationResult(platform, tpl.version, tpl.verification, issues)
    text = _env.get_template(tpl.template).render(intent=intent, **_vlan_context(intent))
    return GenerationResult(platform, tpl.version, tpl.verification, issues, text)
