"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from ipaddress import IPv4Interface
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from undm.domain.enums import (
    DeviceCategory,
    DeviceEnvironment,
    ManagementProtocol,
    ProvisioningStatus,
)
from undm.domain.intent import DeviceIntent
from undm.drivers.base import ApplyMode


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DriverOut(BaseModel):
    driver_id: str
    vendor: str
    platform: str
    os_family: str
    description: str
    simulated: bool
    capabilities: list[str]
    maturity: str
    transport: str
    notes: list[str]


class PolicyOut(BaseModel):
    enable_real_device_writes: bool
    enable_real_device_firmware: bool
    allow_production_read_only: bool
    allow_production_deployments: bool
    require_separate_approver: bool
    firmware_require_separate_approver: bool = True
    # Switches fixed by the start-up settings (.env or environment): not changeable in the UI.
    locked: list[str] = []


class PolicyChange(BaseModel):
    """Switches to change from Settings → Safety; omitted ones stay as they are."""

    model_config = ConfigDict(extra="forbid")

    enable_real_device_writes: bool | None = None
    enable_real_device_firmware: bool | None = None
    firmware_require_separate_approver: bool | None = None


_CLI_TEXT = r'^[^"?\\\x00-\x1f\x7f]*$'  # typed into a switch CLI: no quotes, '?', '\\'


class CertificateSubject(BaseModel):
    """Answers to the switch's certificate questions (team practice on the 2930F)."""

    model_config = ConfigDict(extra="forbid")

    common_name: str = Field(min_length=1, max_length=64, pattern=_CLI_TEXT)
    org_unit: str = Field(default="", max_length=64, pattern=_CLI_TEXT)
    org_name: str = Field(default="", max_length=64, pattern=_CLI_TEXT)
    locality: str = Field(default="", max_length=64, pattern=_CLI_TEXT)
    state: str = Field(default="", max_length=64, pattern=_CLI_TEXT)
    country: str = Field(default="", pattern=r"^([A-Za-z]{2})?$")
    profile_name: str = Field(default="Profile", pattern=r"^[A-Za-z0-9_.-]{1,32}$")
    certificate_name: str = Field(default="certificate", pattern=r"^[A-Za-z0-9_.-]{1,32}$")


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    site: str = ""
    purpose: str = ""


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    site: str | None = None
    purpose: str | None = None
    certificate_subject: CertificateSubject | None = None  # explicit null clears it
    zone: int | None = Field(default=None, ge=1, le=128)  # explicit null clears it (D-111)


class ProjectOut(ORM):
    id: str
    name: str
    description: str
    site: str
    purpose: str
    certificate_subject: CertificateSubject | None = None
    staged_at: datetime | None = None  # staging of the system finished (D-108)
    staged_by: str = ""
    zone: int | None = None  # its files are generated for this zone (D-111)
    created_at: datetime
    updated_at: datetime


class LoginDefaults(BaseModel):
    """Default logins per device kind (ids of logins for all systems), D-105."""

    model_config = ConfigDict(extra="forbid")

    class Firewall(BaseModel):
        model_config = ConfigDict(extra="forbid")
        login: str | None = None
        login_after: str | None = None
        tunnel_key: str | None = None

    class BlackBox(BaseModel):
        model_config = ConfigDict(extra="forbid")
        login: str | None = None
        login_after: str | None = None

    class Aruba(BaseModel):
        model_config = ConfigDict(extra="forbid")
        login: str | None = None
        current: str | None = None

    firewall: Firewall = Field(default_factory=Firewall)
    blackbox: BlackBox = Field(default_factory=BlackBox)
    aruba: Aruba = Field(default_factory=Aruba)


class CertificateSetting(BaseModel):
    """The HTTPS certificate answers for all systems (null: none set)."""

    subject: CertificateSubject | None = None


class FinishStagingIn(BaseModel):
    """The devices the person staged (the wizard's roles): each must be finished."""

    device_ids: list[str] = Field(min_length=1, max_length=50)


class CredentialRefIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: Literal["keyring", "env"] = "keyring"
    # Required for "env"; generated automatically for "keyring".
    locator: str | None = Field(default=None, min_length=1, max_length=200)


class CredentialRefOut(ORM):
    id: str
    name: str
    provider: str
    locator: str
    has_secret: bool | None = None  # None: the credential store could not be queried
    empty_password: bool | None = None  # a login without a password (never the value)
    shared: bool = False  # a login for all systems (D-105)


class CredentialSecretIn(BaseModel):
    """Write-only. Never returned by any endpoint."""

    username: str = Field(min_length=1, max_length=120)
    # May be empty: factory-default devices often have no password.
    password: str = Field(max_length=512, repr=False)


class BootstrapProfile(BaseModel):
    """Console bootstrap settings: an out-of-band management VLAN on one port."""

    model_config = ConfigDict(extra="forbid")

    vlan_id: int = Field(ge=2, le=4094)
    vlan_name: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,32}$")
    untagged_port: str = Field(pattern=r"^[A-Za-z0-9/]{1,8}$")
    address: IPv4Interface  # e.g. "192.168.1.1/24"


class DeviceBase(BaseModel):
    manufacturer: str | None = None
    product_family: str | None = None
    model: str | None = None
    hardware_revision: str | None = None
    category: DeviceCategory | None = None
    role: str | None = None
    os_family: str | None = None
    firmware_version: str | None = None
    management_address: str | None = None
    management_protocol: ManagementProtocol | None = None
    management_port: int | None = Field(default=None, ge=1, le=65535)
    management_vrf: str | None = None
    site: str | None = None
    rack_location: str | None = None
    driver_id: str | None = None
    credential_ref_id: str | None = None
    environment: DeviceEnvironment | None = None
    provisioning_status: ProvisioningStatus | None = None
    notes: str | None = None
    tags: list[str] | None = None
    bootstrap_profile: BootstrapProfile | None = None


class DeviceIn(DeviceBase):
    name: str = Field(min_length=1, max_length=120)
    manufacturer: str
    category: DeviceCategory
    driver_id: str


class DevicePatch(DeviceBase):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class DeviceOut(ORM):
    id: str
    project_id: str
    name: str
    manufacturer: str
    product_family: str
    model: str
    hardware_revision: str
    category: str
    role: str
    os_family: str
    firmware_version: str
    management_address: str
    management_protocol: str
    management_port: int | None
    management_vrf: str
    site: str
    rack_location: str
    driver_id: str
    credential_ref_id: str | None
    environment: str
    provisioning_status: str
    deployment_status: str
    notes: str
    tags: list[str]
    intent: dict[str, Any] | None
    observed_facts: dict[str, Any] | None
    facts_retrieved_at: datetime | None
    last_connection_at: datetime | None
    last_backup_at: datetime | None
    last_deployment_at: datetime | None
    locked_by_deployment_id: str | None
    bootstrap_profile: dict[str, Any] | None
    capabilities: list[str] = []
    created_at: datetime
    updated_at: datetime


class DeviceModelOut(BaseModel):
    model_id: str
    manufacturer: str
    product_family: str
    model: str
    category: str
    os_family: str
    drivers: list[str]
    support: str
    notes: str


class IssueOut(BaseModel):
    severity: str
    code: str
    message: str
    path: str


class ConfigVersionOut(ORM):
    id: str
    device_id: str
    kind: str
    sha256: str
    platform: str
    template_version: str
    verification: str
    reference: str
    created_by: str
    created_at: datetime


class SecretSlotOut(ORM):
    slot_id: str
    setting: str
    line: int


class ConfigFileReportOut(ORM):
    """What an imported file is, worked out offline (never contains secret values)."""

    file_type: str
    summary: str
    apply_mode: str | None
    facts: dict[str, str]
    notes: list[str]
    problems: list[str]
    blocked_reason: str
    secret_slots: list[SecretSlotOut] = []


class ConfigVersionFull(ConfigVersionOut):
    text: str
    inspection: ConfigFileReportOut | None = None


class GenerateOut(BaseModel):
    ok: bool
    issues: list[IssueOut]
    version: ConfigVersionFull | None


class IntentIn(DeviceIntent):
    pass


class DeploymentIn(BaseModel):
    device_ids: list[str] = Field(min_length=1)
    dry_run: bool = False
    apply_mode: ApplyMode = ApplyMode.MERGE
    # Optional device_id -> config version id. Default: latest generated, else latest imported.
    config_versions: dict[str, str] | None = None
    # Optional device_id -> {secret slot id -> credential reference id}: values to put into
    # marked settings of a supplied file (e.g. a tunnel pre-shared key) when it is sent.
    secrets: dict[str, dict[str, str]] | None = None
    # Optional device_id -> credential reference id valid once the file is applied (for
    # files that change the login, e.g. the 2930F files set the approved password).
    credentials_after: dict[str, str] | None = None


class ConfigImportIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    text: str


class DeploymentTargetOut(ORM):
    device_id: str
    position: int
    config_version_id: str | None
    secret_refs: dict[str, str] | None = None
    credential_after_ref_id: str | None = None
    backup_version_id: str | None
    # Running configuration read back after verification (view or compare with the file).
    after_version_id: str | None = None
    from_version: str | None
    to_version: str | None
    state: str
    diff: str
    message: str


class DeploymentEventOut(ORM):
    seq: int
    timestamp: datetime
    device_id: str | None
    stage: str
    status: str
    message: str


class DeploymentOut(ORM):
    id: str
    project_id: str
    kind: str
    firmware_image_id: str | None
    window_start: datetime | None
    window_end: datetime | None
    state: str
    dry_run: bool
    allow_downgrade: bool = False
    also_secondary: bool = False
    apply_mode: str
    created_by: str
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    staging_id: str | None = None
    staging_step: int | None = None
    needs_attention: bool = False  # D-088, see DeploymentSummary
    attention_cleared: str | None = None
    targets: list[DeploymentTargetOut]
    events: list[DeploymentEventOut]


class StagingPlanIn(BaseModel):
    """One device: restore the base file (replace), then load the site file (merge)."""
    device_id: str
    base_version_id: str
    site_version_id: str
    # Login valid once the base file is applied (it sets its own admin password).
    credential_after_ref_id: str | None = None
    # Secret slot id of the site file -> credential reference id (e.g. the tunnel key).
    secrets: dict[str, str] | None = None
    # New unit: first set the device's login at its first login (D-073).
    first_login: bool = False


class FirstLoginIn(BaseModel):
    device_id: str


class StagingStepIn(BaseModel):
    """One step of a device's staging plan (D-085)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["first_login", "firmware", "configuration", "free_address", "license"]
    # free_address: another device of the system, taken off its address (D-107);
    # 'address' is ignored since D-107 (no spare address)
    other_device_id: str | None = None
    address: str | None = Field(default=None, max_length=64)
    # firmware
    image_id: str | None = None
    allow_downgrade: bool = False
    also_secondary: bool = False
    # configuration
    version_id: str | None = None
    apply_mode: Literal["merge", "replace"] | None = None  # None: as the file requires
    credential_after_ref_id: str | None = None
    secrets: dict[str, str] | None = None


class DeviceStagingIn(BaseModel):
    """Steps for one device, run in this order after one approval."""

    model_config = ConfigDict(extra="forbid")

    device_id: str
    steps: list[StagingStepIn] = Field(min_length=1, max_length=8)


class StagingApproveIn(BaseModel):
    """Maintenance window for the plan's firmware steps (none needed without firmware)."""

    window_start: datetime | None = None
    window_end: datetime | None = None


class SystemImportOut(BaseModel):
    project: ProjectOut
    summary: dict[str, Any]


class StagingIndexOut(BaseModel):
    staging_id: str
    device_id: str
    created_at: datetime
    kinds: list[str]
    states: list[str]


class StagingPlanOut(BaseModel):
    staging_id: str
    steps: list[DeploymentOut]


class DeploymentSummary(ORM):
    id: str
    project_id: str
    kind: str
    state: str
    dry_run: bool
    allow_downgrade: bool = False
    also_secondary: bool = False
    apply_mode: str
    created_by: str
    approved_by: str | None
    created_at: datetime
    staging_id: str | None = None
    staging_step: int | None = None
    # D-088: a plan that needs attention and still waits for a person; else why not.
    needs_attention: bool = False
    attention_cleared: str | None = None  # "checked" or "superseded:<plan id>"


class CheckedIn(BaseModel):
    """What a person checked on the device(s) of a plan that needs attention."""

    note: str = Field(min_length=1, max_length=500)


class AuditOut(ORM):
    id: str
    timestamp: datetime
    actor: str
    action: str
    target_type: str
    target_id: str
    outcome: str
    details: dict[str, Any]


class ConfigDiffOut(BaseModel):
    from_version_id: str
    to_version_id: str
    unified: str
    added: int
    removed: int
    changed: bool


class OperationOut(BaseModel):
    status: str
    message: str
    data: Any = None
    login_refused: bool = False  # the device refused the login (driver diagnostic)


class ApproveIn(BaseModel):
    """Firmware deployments require a maintenance window (UTC or with offset)."""

    window_start: datetime | None = None
    window_end: datetime | None = None


class FirmwareImageOut(ORM):
    id: str
    vendor: str
    platform: str
    version: str
    filename: str
    size_bytes: int
    sha256: str
    vendor_sha256: str | None
    vendor_sha512: str | None = None
    integrity_verified: bool
    unverified_reason: str | None = None
    compatible_models: list[str]
    min_from_version: str | None
    release_notes: str
    status: str
    approved_by: str | None
    approved_at: datetime | None
    created_by: str
    created_at: datetime


class ApproveImageIn(BaseModel):
    # Required only for an image without a matching vendor checksum (D-062).
    unverified_reason: str | None = Field(default=None, max_length=500)


class VendorChecksumIn(BaseModel):
    checksum: str = Field(min_length=32, max_length=200)


class CompatibilityIn(BaseModel):
    device_ids: list[str] = Field(min_length=1)


class CompatibilityOut(BaseModel):
    device_id: str
    device_name: str
    compatible: bool
    issues: list[IssueOut]


class FirmwareDeploymentIn(BaseModel):
    device_ids: list[str] = Field(min_length=1)
    image_id: str
    dry_run: bool = False
    # Install the approved image even where a device runs a newer version.
    allow_downgrade: bool = False
    # Also write the image into the secondary image slot once the primary is verified.
    also_secondary: bool = False


class DiagnosticsOut(BaseModel):
    text: str


class SerialPortOut(BaseModel):
    port: str
    description: str
    hardware_id: str = ""


class BootstrapPreviewIn(BaseModel):
    profile: BootstrapProfile | None = None  # default: the profile saved on the device


class BootstrapPreviewOut(BaseModel):
    supported: bool
    commands: list[str]
    notes: list[str]


class ConsoleBootstrapIn(BaseModel):
    serial_port: str = Field(min_length=1, max_length=64)
    # 9600 is what the product owner's team uses for factory-default 2930F consoles.
    baudrate: Literal[9600, 19200, 38400, 57600, 115200] = 9600
    profile: BootstrapProfile | None = None
    confirm_device_name: str
    allow_configured: bool = False
    # Preconfigured switch: erase its configuration first (D-057). Needs its current login
    # and its current hostname as typed by the technician.
    erase_existing: bool = False
    current_credential_ref_id: str | None = None
    confirm_hostname: str | None = Field(default=None, max_length=64)


class ConsoleIdentifyIn(BaseModel):
    serial_port: str = Field(min_length=1, max_length=64)
    baudrate: Literal[9600, 19200, 38400, 57600, 115200] = 9600
    current_credential_ref_id: str | None = None


class ConsoleIdentifyOut(BaseModel):
    # configured | factory_default | new | unknown
    state: str
    hostname: str
    message: str


class ConsoleBootstrapOut(BaseModel):
    status: str
    message: str
    commands_sent: list[str]
    findings: list[str]
    verified: bool
    saved: bool
    transcript: str
    sanitized_transcript: str
    credentials_set: bool = False  # a new switch's first-login credentials were set
    erased: str = ""  # hostname of the configuration erased first, if any
    no_password: bool = False  # the switch asked for no password: it has no manager password
    password_set: bool = False  # it had none; UNDM set the device's login (confirmed)
    network_reachable: bool | None
    network_hint: str


# -- team templates (D-111) -------------------------------------------------------------
class TemplateFileIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    text: str
    zone: int | None = Field(default=None, ge=1, le=128)


class TemplateImportIn(TemplateFileIn):
    role: Literal["fortigate_base", "fortigate_site", "bhdmz", "lte", "tetra"]
    verify: TemplateFileIn | None = None  # the same file for another zone


class TemplateOut(ORM):
    id: str
    role: str
    version: str
    filename: str
    reference_zone: int | None
    counts: dict[str, int]
    verified_zone: int | None
    line_ending: Literal["lf", "crlf"] = "lf"  # the team file's formatting, kept on download
    final_newline: bool = True
    created_by: str
    created_at: datetime
    older: int = 0


class TemplateImportOut(BaseModel):
    template: TemplateOut
    to_check: list[str] = []
    verified_bytes: bool | None = None  # the second zone's file also matched byte for byte


class TemplatePreviewOut(BaseModel):
    filename: str
    text: str


class GenerateFilesIn(BaseModel):
    """Which device of the system gets which template's file."""

    assignments: dict[Literal["fortigate_base", "fortigate_site", "bhdmz", "lte", "tetra"], str] \
        = Field(min_length=1)


class GeneratedFileOut(BaseModel):
    role: str
    device_id: str
    version_id: str
    filename: str
    template_version: str
    verified_zone: int | None


class ComparedFileOut(BaseModel):
    role: str
    device_id: str
    generated_name: str
    file_name: str | None
    same: bool
    lines: int
    differences: list[tuple[int, str, str]]

