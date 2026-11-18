"""Simulated drivers for the three initial target families.

IMPORTANT: the capability profiles below describe *simulations*. They are
chosen to exercise different orchestration paths (e.g. one profile without
configuration rollback) and are NOT claims about what the real products or a
specific firmware release support. Real adapters declare capabilities only
after verification against vendor documentation and lab equipment.
"""

from __future__ import annotations

import hashlib
from typing import ClassVar

from undm.domain.operations import DeviceOperation
from undm.drivers.base import (
    ApplyMode,
    Capability,
    ConfigurationBackup,
    DeviceDriver,
    DeviceFacts,
    DriverInfo,
    FirmwareImageRef,
    OperationResult,
)
from undm.drivers.mock.lab import SimulatedDevice, default_lab

Op = DeviceOperation
C = Capability


def _lines(text: str) -> list[str]:
    return [ln.rstrip() for ln in text.splitlines() if ln.strip()]


class MockDriver(DeviceDriver):
    model: ClassVar[str] = "SIM"
    initial_os_version: ClassVar[str] = "0.0.0"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._dev: SimulatedDevice | None = None

    # -- helpers ------------------------------------------------------------------
    def _device(self, op: DeviceOperation) -> SimulatedDevice | OperationResult:
        if self._dev is None:
            return OperationResult.failed(op, "Not connected")
        if not self._dev.reachable:
            return OperationResult.failed(op, f"{self.target.management_address} unreachable")
        if op in self._dev.fail_on:
            return OperationResult.failed(op, f"Simulated failure injected for {op.value}")
        return self._dev

    def _require(self, op: DeviceOperation) -> OperationResult | None:
        missing = self.missing_capabilities(op)
        return self._unsupported(op) if missing else None

    # -- session --------------------------------------------------------------------
    def connect(self) -> OperationResult:
        op = Op.CHECK_REACHABILITY
        dev = default_lab().get_or_create(
            self.target.management_address, self.info.vendor, self.model, self.initial_os_version
        )
        if dev is None:
            return OperationResult.failed(op, "No simulated device at this address")
        if not dev.reachable:
            return OperationResult.failed(op, f"{dev.address} unreachable (simulated)")
        self._dev = dev
        return OperationResult.success(op, message="connected (simulated)")

    def disconnect(self) -> None:
        self._dev = None

    # -- read-only ------------------------------------------------------------------
    def get_device_facts(self) -> OperationResult:
        dev = self._device(Op.GET_FACTS)
        if isinstance(dev, OperationResult):
            return dev
        facts = DeviceFacts(
            hostname=dev.hostname,
            vendor=dev.vendor,
            model=dev.model,
            os_version=dev.os_version,
            serial_number=dev.serial_number,
            extra={"factory_default": dev.factory_default, "simulated": True},
        )
        return OperationResult.success(Op.GET_FACTS, facts)

    def get_running_configuration(self) -> OperationResult:
        dev = self._device(Op.GET_RUNNING_CONFIGURATION)
        if isinstance(dev, OperationResult):
            return dev
        return OperationResult.success(Op.GET_RUNNING_CONFIGURATION, dev.running_config)

    def backup_configuration(self) -> OperationResult:
        op = Op.BACKUP_CONFIGURATION
        if r := self._require(op):
            return r
        dev = self._device(op)
        if isinstance(dev, OperationResult):
            return dev
        ref = "ckpt-" + hashlib.sha256(dev.running_config.encode()).hexdigest()[:12]
        dev.checkpoints[ref] = dev.running_config
        return OperationResult.success(
            op, ConfigurationBackup(self.target.device_id, dev.running_config, ref)
        )

    def get_firmware_information(self) -> OperationResult:
        dev = self._device(Op.GET_FIRMWARE_INFORMATION)
        if isinstance(dev, OperationResult):
            return dev
        return OperationResult.success(
            Op.GET_FIRMWARE_INFORMATION,
            {"running": dev.os_version, "staged": dev.staged_firmware,
             "previous": dev.previous_os_version},
        )

    # -- impacting ------------------------------------------------------------------
    def apply_configuration(self, config: str, mode: ApplyMode) -> OperationResult:
        op = Op.APPLY_CONFIGURATION
        if r := self._require(op):
            return r
        if mode is ApplyMode.REPLACE and C.CONFIGURATION_REPLACE not in self.capabilities():
            return OperationResult.unsupported(op, "Replace mode is not supported by this driver")
        dev = self._device(op)
        if isinstance(dev, OperationResult):
            return dev
        new_lines = [ln for ln in _lines(config) if ln.strip() not in dev.ignored_lines]
        if mode is ApplyMode.REPLACE:
            dev.running_config = "\n".join(new_lines) + "\n"
        else:
            existing = _lines(dev.running_config)
            merged = existing + [ln for ln in new_lines if ln not in existing]
            dev.running_config = "\n".join(merged) + "\n"
        for ln in new_lines:
            if ln.startswith("hostname "):
                dev.hostname = ln.split(None, 1)[1].strip()
        dev.factory_default = False
        return OperationResult.success(op, message=f"applied ({mode.value}, simulated)")

    def save_configuration(self) -> OperationResult:
        dev = self._device(Op.SAVE_CONFIGURATION)
        if isinstance(dev, OperationResult):
            return dev
        dev.startup_config = dev.running_config
        return OperationResult.success(Op.SAVE_CONFIGURATION)

    def rollback_configuration(self, backup: ConfigurationBackup) -> OperationResult:
        op = Op.ROLLBACK_CONFIGURATION
        if r := self._require(op):
            return r
        dev = self._device(op)
        if isinstance(dev, OperationResult):
            return dev
        if backup.reference not in dev.checkpoints:
            return OperationResult.failed(op, f"Checkpoint {backup.reference} not found on device")
        dev.running_config = dev.checkpoints[backup.reference]
        return OperationResult.success(op, message=f"rolled back to {backup.reference}")

    def stage_firmware(self, image: FirmwareImageRef) -> OperationResult:
        op = Op.STAGE_FIRMWARE
        if r := self._require(op):
            return r
        dev = self._device(op)
        if isinstance(dev, OperationResult):
            return dev
        dev.staged_firmware = image.version
        return OperationResult.success(op, {"staged": image.version, "sha256": image.sha256})

    def install_firmware(self) -> OperationResult:
        op = Op.INSTALL_FIRMWARE
        if r := self._require(op):
            return r
        dev = self._device(op)
        if isinstance(dev, OperationResult):
            return dev
        if not dev.staged_firmware:
            return OperationResult.failed(op, "No firmware image staged")
        dev.previous_os_version, dev.os_version = dev.os_version, dev.staged_firmware
        dev.staged_firmware = None
        return OperationResult.success(op, {"running": dev.os_version})

    def rollback_firmware(self) -> OperationResult:
        op = Op.ROLLBACK_FIRMWARE
        if r := self._require(op):
            return r
        dev = self._device(op)
        if isinstance(dev, OperationResult):
            return dev
        if not dev.previous_os_version:
            return OperationResult.failed(op, "No previous firmware recorded")
        dev.os_version, dev.previous_os_version = dev.previous_os_version, None
        return OperationResult.success(op, {"running": dev.os_version})

    def reboot(self) -> OperationResult:
        op = Op.REBOOT
        if r := self._require(op):
            return r
        dev = self._device(op)
        if isinstance(dev, OperationResult):
            return dev
        dev.running_config = dev.startup_config
        if dev.unreachable_after_reboot:
            dev.reachable = False  # simulates a device that does not come back
        self._dev = None  # a reboot drops the session; callers must reconnect
        return OperationResult.success(op, message="rebooted (simulated)")

    def provision_factory_default_device(self, bootstrap_config: str) -> OperationResult:
        op = Op.PROVISION_FACTORY_DEFAULT
        if r := self._require(op):
            return r
        dev = self._device(op)
        if isinstance(dev, OperationResult):
            return dev
        if not dev.factory_default:
            return OperationResult.failed(op, "Device is not in factory-default state")
        result = self.apply_configuration(bootstrap_config, ApplyMode.MERGE)
        if not result.ok:
            return result
        dev.startup_config = dev.running_config
        return OperationResult.success(op, message="bootstrapped (simulated)")


_COMMON = frozenset(
    {C.SSH, C.CONFIGURATION_BACKUP, C.CONFIGURATION_APPLY, C.FIRMWARE_UPGRADE, C.REBOOT}
)


class MockFortiGateDriver(MockDriver):
    model = "SIM-FGT"
    initial_os_version = "sim-7.0.0"
    info = DriverInfo(
        driver_id="mock.fortinet.fortios",
        vendor="Fortinet",
        platform="fortios",
        os_family="FortiOS",
        description="Simulated FortiGate (no rollback capability in this simulation profile)",
        simulated=True,
        capabilities=_COMMON | {C.REST_API, C.ZERO_TOUCH_PROVISIONING},
    )


class MockArubaAOSCXDriver(MockDriver):
    model = "SIM-CX"
    initial_os_version = "sim-10.0.0"
    info = DriverInfo(
        driver_id="mock.aruba.aoscx",
        vendor="Aruba",
        platform="aoscx",
        os_family="AOS-CX",
        description="Simulated AOS-CX switch",
        simulated=True,
        capabilities=_COMMON
        | {C.REST_API, C.CONFIGURATION_ROLLBACK, C.CONFIGURATION_REPLACE,
           C.FIRMWARE_ROLLBACK, C.ZERO_TOUCH_PROVISIONING},
    )


class MockCiscoIOSXEDriver(MockDriver):
    model = "SIM-IOSXE"
    initial_os_version = "sim-17.0.0"
    info = DriverInfo(
        driver_id="mock.cisco.iosxe",
        vendor="Cisco",
        platform="iosxe",
        os_family="IOS-XE",
        description="Simulated IOS-XE router/switch",
        simulated=True,
        capabilities=_COMMON
        | {C.NETCONF, C.CONFIGURATION_ROLLBACK, C.CONFIGURATION_REPLACE, C.SERIAL_CONSOLE},
    )


class MockArubaOSSwitchDriver(MockDriver):
    model = "SIM-2930F"
    initial_os_version = "WC.16.10.0010"
    info = DriverInfo(
        driver_id="mock.aruba.aos_switch",
        vendor="Aruba",
        platform="aos_switch",
        os_family="ArubaOS-Switch",
        description="Simulated ArubaOS-Switch (e.g. 2930F); dual image banks simulated as "
                    "firmware rollback, no configuration rollback",
        simulated=True,
        capabilities=_COMMON | {C.FIRMWARE_ROLLBACK},
    )


MOCK_DRIVERS: tuple[type[MockDriver], ...] = (
    MockArubaOSSwitchDriver,
    MockFortiGateDriver,
    MockArubaAOSCXDriver,
    MockCiscoIOSXEDriver,
)
