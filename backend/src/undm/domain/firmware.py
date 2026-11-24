"""Offline firmware compatibility rules (no device contact)."""

from __future__ import annotations

from dataclasses import dataclass

from undm.domain.validation import Severity, ValidationIssue


@dataclass(frozen=True)
class ImageRules:
    platform: str
    version: str
    compatible_models: tuple[str, ...]
    approved: bool
    integrity_verified: bool
    retired: bool
    # Set when the image was approved without a matching vendor checksum (D-062).
    unverified_reason: str | None = None


def compatibility_issues(
    rules: ImageRules, *, device_models: tuple[str, ...], driver_platform: str,
    driver_can_upgrade: bool, driver_id: str,
) -> list[ValidationIssue]:
    """Problems that prevent using this image on this device. Empty list = compatible.

    ``device_models`` holds every model string known for the device (declared and,
    if retrieved, observed). A match on any of them (case-insensitive) is accepted.
    """
    issues: list[ValidationIssue] = []

    def err(code: str, msg: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, code, msg))

    if rules.retired:
        err("image_retired", "image is retired")
    elif not rules.approved:
        err("image_not_approved", "image has not been approved for use")
    if not rules.integrity_verified and rules.unverified_reason:
        issues.append(ValidationIssue(
            Severity.WARNING, "integrity_not_verified",
            "image approved WITHOUT the vendor's checksum; reason given: "
            f"{rules.unverified_reason}"))
    elif not rules.integrity_verified:
        err("integrity_not_verified",
            "image checksum has not been verified against the vendor's published "
            "SHA-256 or SHA-512")
    if rules.platform != driver_platform:
        err("platform_mismatch",
            f"image is for platform {rules.platform!r}, device driver is {driver_platform!r}")
    if not rules.compatible_models:
        err("no_compatibility_list", "image lists no compatible models")
    else:
        known = {m.strip().lower() for m in device_models if m and m.strip()}
        allowed = {m.strip().lower() for m in rules.compatible_models}
        if not known & allowed:
            err("model_not_compatible",
                f"device model {', '.join(sorted(known)) or 'unknown'} is not in the image's "
                f"compatibility list ({', '.join(rules.compatible_models)})")
    if not driver_can_upgrade:
        err("driver_cannot_upgrade",
            f"driver {driver_id} has no firmware upgrade procedure (not implemented for real "
            "devices until validated per model on lab equipment)")
    return issues
