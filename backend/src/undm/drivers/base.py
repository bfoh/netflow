"""Common driver contract.

Every vendor adapter implements :class:`DeviceDriver`. Operations a driver does
not implement return a structured ``UNSUPPORTED`` result rather than raising,
so the orchestrator can reason about capability gaps explicitly.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Protocol

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
    # A named restore point kept on the device (e.g. a FortiGate configuration revision).
    CONFIGURATION_CHECKPOINT = "supports_configuration_checkpoint"
    # lifecycle
    ZERO_TOUCH_PROVISIONING = "supports_zero_touch_provisioning"
    FIRMWARE_UPGRADE = "supports_firmware_upgrade"
    FIRMWARE_ROLLBACK = "supports_firmware_rollback"
    # A second image slot the driver can write (e.g. ArubaOS-Switch secondary flash).
    FIRMWARE_SECONDARY_IMAGE = "supports_firmware_secondary_image"
    REBOOT = "supports_reboot"
    # Answers a new unit's demanded password change at its first login (D-073).
    FIRST_LOGIN_SETUP = "supports_first_login_setup"
    # Can switch off its management port until its next restart, with nothing saved, so
    # its address is free for another device (D-107, replaces D-096's spare address).
    MANAGEMENT_PORT_OFF = "supports_management_port_off"
    # Restarts on request, outside a firmware step (D-099). REBOOT alone means only "restarts
    # as part of a firmware upgrade" on some drivers.
    RESTART = "supports_restart"
    # Staged by a person in the device's own portal, following UNDM's steps (D-117): UNDM
    # never logs in to it or changes it; it checks that the portal answers and records.
    GUIDED_STAGING = "supports_guided_staging"
    # Loads a license file the team supplies, fetched from UNDM (D-100).
    LICENSE_FILE = "supports_license_file"
    # Pings / traces one address from the device, with a documented command (D-128).
    PING = "supports_ping"
    TRACEROUTE = "supports_traceroute"


# Capabilities an operation needs before a driver may be asked to perform it.
REQUIRED_CAPABILITIES: dict[DeviceOperation, frozenset[Capability]] = {
    DeviceOperation.BACKUP_CONFIGURATION: frozenset({Capability.CONFIGURATION_BACKUP}),
    DeviceOperation.APPLY_CONFIGURATION: frozenset({Capability.CONFIGURATION_APPLY}),
    DeviceOperation.ROLLBACK_CONFIGURATION: frozenset({Capability.CONFIGURATION_ROLLBACK}),
    DeviceOperation.STAGE_FIRMWARE: frozenset({Capability.FIRMWARE_UPGRADE}),
    DeviceOperation.STAGE_FIRMWARE_SECONDARY: frozenset({Capability.FIRMWARE_SECONDARY_IMAGE}),
    DeviceOperation.INSTALL_FIRMWARE: frozenset({Capability.FIRMWARE_UPGRADE}),
    DeviceOperation.ROLLBACK_FIRMWARE: frozenset({Capability.FIRMWARE_ROLLBACK}),
    DeviceOperation.REBOOT: frozenset({Capability.REBOOT}),
    DeviceOperation.CREATE_CHECKPOINT: frozenset({Capability.CONFIGURATION_CHECKPOINT}),
    DeviceOperation.PROVISION_FACTORY_DEFAULT: frozenset({Capability.ZERO_TOUCH_PROVISIONING}),
    DeviceOperation.PING: frozenset({Capability.PING}),
    DeviceOperation.TRACEROUTE: frozenset({Capability.TRACEROUTE}),
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
    # The PC's serial port for a device reached over its console only (D-116).
    console_port: str | None = None


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


@dataclass(frozen=True)
class SecretSlot:
    """A setting in a supplied file whose value UNDM can replace from the credential store.

    Only the location is described; the value in the file is never copied here.
    """

    # Stable within the file, e.g. "vdom > root > vpn ipsec phase1-interface > t1 > psksecret".
    slot_id: str
    setting: str
    line: int


@dataclass(frozen=True)
class ConfigFileReport:
    """What a supplied configuration file is, worked out offline from its own content."""

    file_type: str  # "full_backup" | "cli_script" | "unknown"
    summary: str
    # The only way this kind of file can sensibly be applied (None = not applicable).
    apply_mode: ApplyMode | None
    facts: dict[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()  # what a technician should know before applying it
    problems: tuple[str, ...] = ()  # reasons not to apply the file as it is
    # Set by a driver that cannot apply this kind of file (yet).
    blocked_reason: str = ""
    secret_slots: tuple[SecretSlot, ...] = ()
    # Project settings that must be set before this file may be applied (name -> why).
    required_settings: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FileAddress:
    """An address a configuration file gives the device, and where in the file (D-125)."""

    address: str
    prefix: int | None  # None when the file does not say
    where: str  # e.g. "VLAN 222", 'interface "port3"'
    line: int
    vdom: str | None = None  # FortiOS: the VDOM of the interface
    allows: str = ""  # management access on it, as written (FortiOS 'allowaccess')


@dataclass(frozen=True)
class ManagerRange:
    """Addresses a file allows to manage the device (inclusive range), as written there."""

    first: str
    last: str
    text: str
    line: int


@dataclass(frozen=True)
class FileAddresses:
    addresses: tuple[FileAddress, ...] = ()
    managers: tuple[ManagerRange, ...] = ()


class TransferInfo(Protocol):
    size: int
    bytes_sent: int
    completed: bool
    error: str


class FileServer(Protocol):
    """Lets a driver make one file available for its device to pull (e.g. over TFTP)."""

    def offer(self, path: Path, name: str, client_ip: str) -> str:
        """Publish the file for that device; returns the server address to give it."""
        ...

    def withdraw(self, name: str) -> None:
        """Stop offering the file; a fetch of it still running is cancelled."""
        ...

    def last_transfer(self, name: str, client_ip: str) -> TransferInfo | None: ...


class DeviceDriver:
    """Base class; subclasses override only what they actually support."""

    info: ClassVar[DriverInfo]
    # The console speed of the model's console port, where a source documents it (D-126).
    console_speed: ClassVar[int | None] = None
    # Where that speed comes from, shown next to it ("Nokia documentation", ...).
    console_speed_source: ClassVar[str] = ""
    # The driver that reaches the same model in the network after staging, where it differs
    # from this one (D-125): e.g. a console-only driver on the bench, SSH in the network.
    network_driver_id: ClassVar[str | None] = None
    # Set by a running deployment: True once a stop was requested. Drivers that wait long
    # (transfers, device questions) check it and end the wait early.
    should_stop: Callable[[], bool] | None = None
    # Set by the service for jobs in which devices pull files from UNDM.
    file_server: FileServer | None = None
    # Guided staging (D-117): the procedure a person follows (``undm.domain.guided``).
    guided_procedure: ClassVar[str | None] = None

    def __init__(self, target: DeviceTarget, credentials: Credentials | None = None) -> None:
        self.target = target
        self._credentials = credentials

    # -- capability introspection -------------------------------------------------
    @classmethod
    def capabilities(cls) -> frozenset[Capability]:
        return cls.info.capabilities

    @classmethod
    def inspect_config_file(cls, text: str) -> ConfigFileReport | None:
        """Describe a supplied configuration file offline; None if the driver cannot tell."""
        return None

    @classmethod
    def file_addresses(cls, text: str) -> FileAddresses | None:
        """The addresses a supplied file gives the device, read offline (D-125); None if the
        driver has no reader for its files (the person types the address)."""
        return None

    @classmethod
    def missing_capabilities(cls, op: DeviceOperation) -> frozenset[Capability]:
        return REQUIRED_CAPABILITIES.get(op, frozenset()) - cls.capabilities()

    @classmethod
    def needs_file_server(cls, kind: str, mode: ApplyMode | None = None) -> bool:
        """True if a job of this kind ("configuration" / "firmware") makes the device fetch
        a file from UNDM, so the service must provide ``file_server`` for the job."""
        return False

    def prepare_for_device(self, config: str, secrets: Mapping[str, str]) -> str:
        """The text actually sent: ``secrets`` (slot id -> value, see ``SecretSlot``) put
        into the marked settings. Raises ValueError if a slot or value cannot be used.
        The stored configuration is never changed; only the copy sent to the device."""
        if secrets:
            raise ValueError(f"Driver {self.info.driver_id} cannot insert secret values")
        return config

    def restart_notice(self, mode: ApplyMode) -> str | None:
        """What a person should know before an apply that restarts the device (None: it
        does not restart). Shown as an event before the apply starts."""
        return None

    # The command a restart sends, shown in its preview (None: the driver cannot restart).
    restart_command: ClassVar[str | None] = None

    def restart(self) -> OperationResult:
        """Restart the device now (D-099). Unsaved changes are not saved. A failure that left
        the device untouched carries ``diagnostics["unchanged"] = True``."""
        return OperationResult.unsupported(
            DeviceOperation.REBOOT, "This driver cannot restart a device on request")

    # The command a license load sends, shown in its preview.
    license_command: ClassVar[str | None] = None

    def load_license(self, path: Path, name: str) -> OperationResult:
        """Make the device fetch and apply the license file at ``path`` (offered as ``name``).
        Success means the device took it and is restarting (``data["restarting"]``)."""
        return OperationResult.unsupported(
            DeviceOperation.APPLY_CONFIGURATION, "This driver cannot load a license file")

    def free_address_commands(self) -> OperationResult:
        """Read-only: the exact commands ``free_address`` would send (data:
        ``{"commands": [...], "port": port}``)."""
        return OperationResult.unsupported(
            DeviceOperation.APPLY_CONFIGURATION,
            "This driver cannot take a device off its management address")

    def free_address(self) -> OperationResult:
        """Take the device off its management address until its next restart, nothing
        saved, so another device can use the address (D-107). ``diagnostics["unchanged"]``
        on a failure means the device was left as it was."""
        return OperationResult.unsupported(
            DeviceOperation.APPLY_CONFIGURATION,
            "This driver cannot take a device off its management address")

    def check_before_apply(self, config: str, mode: ApplyMode) -> OperationResult | None:
        """A check before anything is sent that changes nothing on any device (None = no
        check). A failed result ends the device's preflight: the plan fails with no device
        changed. Example: the address a file gives the device is already in use."""
        return None

    def prepare_before_apply(self, config: str, mode: ApplyMode,
                             settings: Mapping[str, Any]) -> OperationResult | None:
        """Steps a file needs on the device before it is applied (None = nothing to do).

        ``settings`` are the project's device settings (e.g. ``certificate_subject``).
        A failed result stops the job before the file is sent."""
        return None

    def manual_recovery(self) -> str | None:
        """What a person does to return the device to its state before a failed load, where
        the driver knows better than "restore the backup" (e.g. nothing was saved)."""
        return None

    def verify_configuration(self, intended: str, mode: ApplyMode) -> OperationResult | None:
        """Driver-specific verification after apply; None = use the generic read-back check.

        For drivers whose platform cannot be verified by comparing lines (for example a
        restored full backup that the device converts to its own release)."""
        return None

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

    def stage_firmware_secondary(self, image: FirmwareImageRef) -> OperationResult:
        """Write ``image`` into the secondary image slot; the boot choice stays unchanged.

        Success means the device reports ``image.version`` in that slot afterwards.
        """
        return self._unsupported(DeviceOperation.STAGE_FIRMWARE_SECONDARY)

    def install_firmware(self) -> OperationResult:
        return self._unsupported(DeviceOperation.INSTALL_FIRMWARE)

    def rollback_firmware(self) -> OperationResult:
        return self._unsupported(DeviceOperation.ROLLBACK_FIRMWARE)

    def reboot(self) -> OperationResult:
        return self._unsupported(DeviceOperation.REBOOT)

    def provision_factory_default_device(self, bootstrap_config: str) -> OperationResult:
        return self._unsupported(DeviceOperation.PROVISION_FACTORY_DEFAULT)

    def use_credentials(self, credentials: Credentials) -> None:
        """Log in with these from the next connection on (a loaded file changed the login)."""
        self._credentials = credentials

    def merge_rerun_note(self, already: int, checked: int) -> str | None:
        """A caution for a merge whose lines are mostly on the device already, if loading
        a file over itself is known to fail on this platform (``already`` of ``checked``
        lines present). Shown as a warning in the plan preview."""
        return None

    def offer_password_change(self, credentials: Credentials | None) -> None:
        """If the device demands a new password at the next logins, set this one (D-066).

        Only drivers that know the device's exact questions act on it; others ignore it
        and the person changes the password by hand (D-065). ``None`` withdraws the offer."""

    def create_checkpoint(self, label: str) -> OperationResult:
        """Keep a named restore point of the current configuration on the device."""
        return self._unsupported(DeviceOperation.CREATE_CHECKPOINT)

    # -- troubleshooting from the device (D-128) ----------------------------------------
    def ping(self, target: str, count: int = 4,
             context: Mapping[str, str] | None = None) -> OperationResult:
        """Ping one address from the device. ``data``: {"sent", "received" (None when the
        answer could not be read), "rtt_ms", "raw"}. ``context`` may name where on the
        device to run it (e.g. "vdom"). Never asks or answers anything."""
        return self._unsupported(DeviceOperation.PING)

    def traceroute(self, target: str,
                   context: Mapping[str, str] | None = None) -> OperationResult:
        """The hops to one address from the device. ``data``: {"hops": [{"n", "address",
        "rtt_ms"}], "raw"}."""
        return self._unsupported(DeviceOperation.TRACEROUTE)


def address_range(address: str, mask_or_prefix: str) -> tuple[str, str, int] | None:
    """(first, last, prefix) of the network ``address`` / mask (or prefix length); None if
    either is not IPv4."""
    try:
        net = ipaddress.IPv4Network(f"{address}/{mask_or_prefix}", strict=False)
    except ValueError:
        return None
    return str(net.network_address), str(net.broadcast_address), net.prefixlen
