"""Device model registry.

A catalog of product models users can pick from when adding a network
element. ``support`` states what UNDM can actually do with the model today;
for every entry below that is SIMULATED ONLY: the model can be designed and
exercised against a mock driver, but no real-device driver exists or has been
validated. Listing a model is not a compatibility claim.
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


CATALOG: tuple[DeviceModel, ...] = (
    DeviceModel("aruba-cx-6300", "Aruba", "CX 6300", "6300M", DeviceCategory.SWITCH,
                "AOS-CX", ("mock.aruba.aoscx",), SupportLevel.SIMULATED_ONLY),
    DeviceModel("aruba-cx-6200", "Aruba", "CX 6200", "6200F", DeviceCategory.SWITCH,
                "AOS-CX", ("mock.aruba.aoscx",), SupportLevel.SIMULATED_ONLY),
    DeviceModel("fortinet-fg-60f", "Fortinet", "FortiGate", "FortiGate-60F",
                DeviceCategory.FIREWALL, "FortiOS", ("mock.fortinet.fortios",),
                SupportLevel.SIMULATED_ONLY),
    DeviceModel("fortinet-fg-100f", "Fortinet", "FortiGate", "FortiGate-100F",
                DeviceCategory.FIREWALL, "FortiOS", ("mock.fortinet.fortios",),
                SupportLevel.SIMULATED_ONLY),
    DeviceModel("cisco-c9300", "Cisco", "Catalyst 9300", "C9300-24T", DeviceCategory.SWITCH,
                "IOS-XE", ("mock.cisco.iosxe",), SupportLevel.SIMULATED_ONLY),
    DeviceModel("cisco-isr4331", "Cisco", "ISR 4000", "ISR4331", DeviceCategory.ROUTER,
                "IOS-XE", ("mock.cisco.iosxe",), SupportLevel.SIMULATED_ONLY),
)


def get_model(model_id: str) -> DeviceModel | None:
    return next((m for m in CATALOG if m.model_id == model_id), None)
