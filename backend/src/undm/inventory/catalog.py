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
                      "On bench units (experimental): console bootstrap 2026-11-19, firmware "
                      "(approved downgrade, secondary flash) 2026-11-19/23, complete-file "
                      "load 2026-11-23, erase of a preconfigured unit 2026-11-23."),
    DeviceModel("blackbox-lig1014a", "Black Box", "Industrial managed switch", "LIG1014A",
                DeviceCategory.SWITCH, "Black Box managed switch",
                ("mock.blackbox.switch", "ssh.blackbox.lig1014a"),
                SupportLevel.LAB_READ_ONLY,
                notes="Read-only checks passed 2026-11-24 on a factory-default LIG1014A "
                      "v00.01.00: connect, facts (MAC address as identity), backup. "
                      "Loading the team's complete file (TFTP into the startup configuration, "
                      "'reload cold') passed once on hardware 2026-11-24. Firmware upgrade by "
                      "TFTP (v00.01.00 -> v00.01.01) passed once on hardware 2026-11-24."),
    DeviceModel("blackbox-le2700a", "Black Box", "LE2700 series", "LE2700A",
                DeviceCategory.SWITCH, "Black Box managed switch", ("mock.blackbox.switch",),
                SupportLevel.SIMULATED_ONLY,
                notes="Staging target in some systems. Configuration files are XML exports "
                      "(a different format from the LIG1014A), recognised offline; no "
                      "real-device driver yet."),
    DeviceModel("fortinet-fg-60f", "Fortinet", "FortiGate", "FortiGate-60F",
                DeviceCategory.FIREWALL, "FortiOS", _FORTIOS, SupportLevel.SIMULATED_ONLY),
    DeviceModel("fortinet-fg-100f", "Fortinet", "FortiGate", "FortiGate-100F",
                DeviceCategory.FIREWALL, "FortiOS", _FORTIOS, SupportLevel.SIMULATED_ONLY),
    DeviceModel("fortinet-fg-101f", "Fortinet", "FortiGate", "FortiGate-101F",
                DeviceCategory.FIREWALL, "FortiOS", _FORTIOS, SupportLevel.LAB_READ_ONLY,
                notes="Staging target. Supplied files are recognised offline (full backup vs "
                      "CLI script). On a bench unit 2026-11-24 (experimental): connect and "
                      "facts, base restore and site script end to end; the unit installed "
                      "7.6.5 by UNDM's firmware procedure (reported failed by an UNDM fault, "
                      "fixed, not yet re-run). First login: fake device only."),
    DeviceModel("nokia-7705-sar-hmc", "Nokia", "7705 SAR", "7705 SAR-Hmc",
                DeviceCategory.ROUTER, "SR OS (7705 SAR)",
                ("mock.nokia.sar", "console.nokia.sar"), SupportLevel.SIMULATED_ONLY,
                notes="Staging target (a system's LTE modem). Reached over its console cable "
                      "only. First access (one start without its configuration and "
                      "auto-discovery, then the admin password, boot options and save) "
                      "follows the team's console recording and Nokia's public guides; "
                      "passed once on hardware 2026-11-26 on a factory unit with TiMOS "
                      "20.5.R1 (experimental). Its configuration file is loaded by a plan over "
                      "its console port, line by line (experimental, not yet run on "
                      "hardware, D-116)."),
    DeviceModel("cisco-c9300", "Cisco", "Catalyst 9300", "C9300-24T", DeviceCategory.SWITCH,
                "IOS-XE", ("mock.cisco.iosxe", "ssh.cisco.iosxe"), SupportLevel.SIMULATED_ONLY),
    DeviceModel("cisco-isr4331", "Cisco", "ISR 4000", "ISR4331", DeviceCategory.ROUTER,
                "IOS-XE", ("mock.cisco.iosxe", "ssh.cisco.iosxe"), SupportLevel.SIMULATED_ONLY),
)


def get_model(model_id: str) -> DeviceModel | None:
    return next((m for m in CATALOG if m.model_id == model_id), None)
