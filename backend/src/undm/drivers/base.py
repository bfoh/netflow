"""Common driver contract.

Every vendor adapter implements :class:`DeviceDriver`. Operations a driver does
not implement return a structured ``UNSUPPORTED`` result rather than raising,
so the orchestrator can reason about capability gaps explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from undm.domain.operations import DeviceOperation


class Capability(StrEnum):
    # transport / management interfaces
    SSH = "supports_ssh"
    REST_API = "supports_rest_api"
    NETCONF = "supports_netconf"
    GNMI = "supports_gnmi"
    SERIAL_CONSOLE = "supports_serial_console"
    # configuration behaviour
    CONFIGURATION_BACKUP = "supports_configuration_backup"
    CONFIGURATION_APPLY = "supports_configuration_apply"
    CONFIGURATION_REPLACE = "supports_configuration_replace"
    CANDIDATE_CONFIGURATION = "supports_candidate_configuration"
    CONFIGURATION_ROLLBACK = "supports_configuration_rollback"
    # lifecycle
    ZERO_TOUCH_PROVISIONING = "supports_zero_touch_provisioning"
    FIRMWARE_UPGRADE = "supports_firmware_upgrade"
    FIRMWARE_ROLLBACK = "supports_firmware_rollback"
    REBOOT = "supports_reboot"


# Capabilities an operation needs before a driver may be asked to perform it.
REQUIRED_CAPABILITIES: dict[DeviceOperation, frozenset[Capability]] = {
    DeviceOperation.BACKUP_CONFIGURATION: frozenset({Capability.CONFIGURATION_BACKUP}),
    DeviceOperation.APPLY_CONFIGURATION: frozenset({Capability.CONFIGURATION_APPLY}),
    DeviceOperation.ROLLBACK_CONFIGURATION: frozenset({Capability.CONFIGURATION_ROLLBACK}),
    DeviceOperation.STAGE_FIRMWARE: frozenset({Capability.FIRMWARE_UPGRADE}),
    DeviceOperation.INSTALL_FIRMWARE: frozenset({Capability.FIRMWARE_UPGRADE}),
    DeviceOperation.ROLLBACK_FIRMWARE: frozenset({Capability.FIRMWARE_ROLLBACK}),
    DeviceOperation.REBOOT: frozenset({Capability.REBOOT}),
    DeviceOperation.PROVISION_FACTORY_DEFAULT: frozenset({Capability.ZERO_TOUCH_PROVISIONING}),
}


class ResultStatus(StrEnum):
    SUCCESS = "success"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass(frozen=True)
class OperationResult:
    operation: DeviceOperation
    status: ResultStatus
    message: str = ""
    data: Any = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status is ResultStatus.SUCCESS

    @classmethod
    def success(cls, op: DeviceOperation, data: Any = None, message: str = "") -> OperationResult:
        return cls(op, ResultStatus.SUCCESS, message, data)

    @classmethod
    def unsupported(cls, op: DeviceOperation, message: str = "") -> OperationResult:
        return cls(op, ResultStatus.UNSUPPORTED, message or f"{op.value} is not supported")

    @classmethod
    def failed(
        cls, op: DeviceOperation, message: str, diagnostics: dict[str, Any] | None = None
    ) -> OperationResult:
        return cls(op, ResultStatus.FAILED, message, None, diagnostics or {})


class ApplyMode(StrEnum):
    MERGE = "merge"  # add/modify lines; leave unrelated config in place
    REPLACE = "replace"  # make the running config equal to the supplied text


class DriverMaturity(StrEnum):
    SIMULATION = "simulation"  # talks only to the in-memory simulated lab
    EXPERIMENTAL = "experimental"  # real devices; not yet validated on lab equipment
    LAB_VALIDATED = "lab_validated"  # passed acceptance tests on named models/firmware


@dataclass(frozen=True)
class DriverInfo:
    driver_id: str
    vendor: str
    platform: str  # configuration-generation platform key, e.g. "iosxe"
    os_family: str
    description: str
    simulated: bool
    capabilities: frozenset[Capability]
    maturity: DriverMaturity = DriverMaturity.SIMULATION
    transport: str = "simulated"
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeviceTarget:
    """How to reach a device. Secrets are resolved separately and never stored here."""

    device_id: str
    management_address: str
    port: int | None = None


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class ConfigurationBackup:
    device_id: str
    text: str
    reference: str  # driver-specific handle usable for rollback (checkpoint name, file, ...)


@dataclass(frozen=True)
class FirmwareImageRef:
    """An approved image from the UNDM repository, as handed to a driver."""

    version: str
    filename: str
    sha256: str
    size_bytes: int
    local_path: str


@dataclass(frozen=True)
class DeviceFacts:
    hostname: str
    vendor: str
    model: str
    os_version: str
    serial_number: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class DeviceDriver:
    """Base class; subclasses override only what they actually support."""

    info: ClassVar[DriverInfo]

    def __init__(self, target: DeviceTarget, credentials: Credentials | None = None) -> None:
        self.target = target
        self._credentials = credentials

    # -- capability introspection -------------------------------------------------
    @classmethod
    def capabilities(cls) -> frozenset[Capability]:
        return cls.info.capabilities

    @classmethod
    def missing_capabilities(cls, op: DeviceOperation) -> frozenset[Capability]:
        return REQUIRED_CAPABILITIES.get(op, frozenset()) - cls.capabilities()

    # -- verification helpers ---------------------------------------------------------
    # The orchestrator decides "already applied" and "verified" by comparing these.
    # Real-device drivers override them to ignore indentation and lines a platform
    # does not display (defaults, block terminators).
    def expected_lines(self, config: str) -> list[str]:
        return [ln.rstrip() for ln in config.splitlines() if ln.strip()]

    def present_lines(self, running: str) -> set[str]:
        return {ln.rstrip() for ln in running.splitlines() if ln.strip()}

    def _unsupported(self, op: DeviceOperation) -> OperationResult:
        return OperationResult.unsupported(
            op, f"Driver {self.info.driver_id} does not support {op.value}"
        )

    # -- session ------------------------------------------------------------------
    def connect(self) -> OperationResult:
        return self._unsupported(DeviceOperation.CHECK_REACHABILITY)

    def disconnect(self) -> None:
        return None

    # -- read-only ------------------------------------------------------------------
    def get_device_facts(self) -> OperationResult:
        return self._unsupported(DeviceOperation.GET_FACTS)

    def get_running_configuration(self) -> OperationResult:
        return self._unsupported(DeviceOperation.GET_RUNNING_CONFIGURATION)

    def backup_configuration(self) -> OperationResult:
        return self._unsupported(DeviceOperation.BACKUP_CONFIGURATION)

    def get_firmware_information(self) -> OperationResult:
        return self._unsupported(DeviceOperation.GET_FIRMWARE_INFORMATION)

    # -- impacting ------------------------------------------------------------------
    def apply_configuration(self, config: str, mode: ApplyMode) -> OperationResult:
        return self._unsupported(DeviceOperation.APPLY_CONFIGURATION)

    def save_configuration(self) -> OperationResult:
        return self._unsupported(DeviceOperation.SAVE_CONFIGURATION)

    def rollback_configuration(self, backup: ConfigurationBackup) -> OperationResult:
        return self._unsupported(DeviceOperation.ROLLBACK_CONFIGURATION)

    def stage_firmware(self, image: FirmwareImageRef) -> OperationResult:
        return self._unsupported(DeviceOperation.STAGE_FIRMWARE)

    def install_firmware(self) -> OperationResult:
        return self._unsupported(DeviceOperation.INSTALL_FIRMWARE)

    def rollback_firmware(self) -> OperationResult:
        return self._unsupported(DeviceOperation.ROLLBACK_FIRMWARE)

    def reboot(self) -> OperationResult:
        return self._unsupported(DeviceOperation.REBOOT)

    def provision_factory_default_device(self, bootstrap_config: str) -> OperationResult:
        return self._unsupported(DeviceOperation.PROVISION_FACTORY_DEFAULT)
