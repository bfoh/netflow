"""In-memory simulated lab used by the mock drivers.

Simulated devices hold running/startup configuration, firmware state and
optional failure injection so deployment workflows can be exercised end to
end without real equipment.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from undm.domain.operations import DeviceOperation


@dataclass
class SimulatedDevice:
    address: str
    vendor: str
    model: str
    os_version: str
    serial_number: str
    hostname: str = "factory-default"
    running_config: str = ""
    startup_config: str = ""
    factory_default: bool = True
    reachable: bool = True
    staged_firmware: str | None = None
    secondary_firmware: str | None = None  # second image slot, where the model has one
    previous_os_version: str | None = None
    checkpoints: dict[str, str] = field(default_factory=dict)
    # Operations that will fail when attempted (failure injection for tests/demos).
    fail_on: set[DeviceOperation] = field(default_factory=set)
    # Lines that "silently" do not take effect on apply (simulates partial apply).
    ignored_lines: set[str] = field(default_factory=set)
    # Device does not come back after a reboot (simulates a failed boot).
    unreachable_after_reboot: bool = False


class SimulatedLab:
    def __init__(self, autocreate: bool = True) -> None:
        self._devices: dict[str, SimulatedDevice] = {}
        # UNDM's device id -> its simulated unit, so one unit answers at its bench address
        # and at its network address (D-125). SYNTHETIC: a real unit has one address at a
        # time; the lab keeps both so a practice system can move back and forth.
        self._by_device: dict[str, SimulatedDevice] = {}
        self._lock = threading.Lock()
        self.autocreate = autocreate

    def add(self, device: SimulatedDevice) -> SimulatedDevice:
        with self._lock:
            self._devices[device.address] = device
        return device

    def get(self, address: str) -> SimulatedDevice | None:
        with self._lock:
            return self._devices.get(address)

    def get_or_create(
        self, address: str, vendor: str, model: str, os_version: str,
        device_id: str | None = None,
    ) -> SimulatedDevice | None:
        """The unit at ``address``; else the unit UNDM's device ``device_id`` reached
        before (at its other address), which then also answers here; else a new one."""
        with self._lock:
            dev = self._devices.get(address)
            if dev is None and device_id and device_id in self._by_device:
                dev = self._by_device[device_id]
                self._devices[address] = dev
            if dev is None and self.autocreate:
                dev = SimulatedDevice(
                    address=address,
                    vendor=vendor,
                    model=model,
                    os_version=os_version,
                    serial_number=f"SIM-{abs(hash(address)) % 10**8:08d}",
                )
                self._devices[address] = dev
            if dev is not None and device_id:
                self._by_device[device_id] = dev
            return dev

    def clear(self) -> None:
        with self._lock:
            self._devices.clear()
            self._by_device.clear()


_default_lab = SimulatedLab()


def default_lab() -> SimulatedLab:
    return _default_lab
