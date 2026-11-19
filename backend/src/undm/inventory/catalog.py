"""Device model registry.

A catalog of product models users can pick from when adding a network
element. ``support`` states what UNDM can actually do with the model today;
for most entries that is SIMULATED ONLY: the model can be designed and exercised
against a mock driver; an experimental SSH driver is listed second but has not been
validated on lab equipment. ``lab_read_only`` means read-only operations passed
acceptance on the model/firmware named in ``notes``. Listing a model is not a
compatibility claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from undm.domain.enums import DeviceCategory


class SupportLevel(StrEnum):
    SIMULATED_ONLY = "simulated_only"
    LAB_READ_ONLY = "lab_read_only"
    LAB_VALIDATED = "lab_validated"


@dataclass(frozen=True)
class DeviceModel:
    model_id: str
    manufacturer: str
    product_family: str
    model: str
    category: DeviceCategory
    os_family: str
    drivers: tuple[str, ...]
    support: SupportLevel
    notes: str = ""


_FORTIOS = ("mock.fortinet.fortios", "ssh.fortinet.fortios")

CATALOG: tuple[DeviceModel, ...] = (
    DeviceModel("aruba-cx-6300", "Aruba", "CX 6300", "6300M", DeviceCategory.SWITCH,
                "AOS-CX", ("mock.aruba.aoscx", "ssh.aruba.aoscx"), SupportLevel.SIMULATED_ONLY),
    DeviceModel("aruba-cx-6200", "Aruba", "CX 6200", "6200F", DeviceCategory.SWITCH,
                "AOS-CX", ("mock.aruba.aoscx", "ssh.aruba.aoscx"), SupportLevel.SIMULATED_ONLY),
    DeviceModel("aruba-2930f", "Aruba", "2930F", "2930F", DeviceCategory.SWITCH,
                "ArubaOS-Switch", ("mock.aruba.aos_switch", "ssh.aruba.aos_switch"),
                SupportLevel.LAB_READ_ONLY,
                notes="Runs ArubaOS-Switch (not AOS-CX). Read-only acceptance passed 2026-11-19 "
                      "on 2930F-48G-4SFP (JL260A) WC.16.10.0025: connect, facts, backup. "
                      "Configuration changes not yet validated."),
    DeviceModel("fortinet-fg-60f", "Fortinet", "FortiGate", "FortiGate-60F",
                DeviceCategory.FIREWALL, "FortiOS", _FORTIOS, SupportLevel.SIMULATED_ONLY),
    DeviceModel("fortinet-fg-100f", "Fortinet", "FortiGate", "FortiGate-100F",
                DeviceCategory.FIREWALL, "FortiOS", _FORTIOS, SupportLevel.SIMULATED_ONLY),
    DeviceModel("fortinet-fg-101f", "Fortinet", "FortiGate", "FortiGate-101F",
                DeviceCategory.FIREWALL, "FortiOS", _FORTIOS, SupportLevel.SIMULATED_ONLY,
                notes="Staging target. Supplied files are recognised offline (full backup vs "
                      "CLI script); restore, multi-VDOM scripts and firmware are not "
                      "implemented for real units yet."),
    DeviceModel("cisco-c9300", "Cisco", "Catalyst 9300", "C9300-24T", DeviceCategory.SWITCH,
                "IOS-XE", ("mock.cisco.iosxe", "ssh.cisco.iosxe"), SupportLevel.SIMULATED_ONLY),
    DeviceModel("cisco-isr4331", "Cisco", "ISR 4000", "ISR4331", DeviceCategory.ROUTER,
                "IOS-XE", ("mock.cisco.iosxe", "ssh.cisco.iosxe"), SupportLevel.SIMULATED_ONLY),
)


def get_model(model_id: str) -> DeviceModel | None:
    return next((m for m in CATALOG if m.model_id == model_id), None)
