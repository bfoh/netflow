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


class ProjectOut(ORM):
    id: str
    name: str
    description: str
    site: str
    purpose: str
    created_at: datetime
    updated_at: datetime


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


class ConfigFileReportOut(ORM):
    """What an imported file is, worked out offline (never contains secret values)."""

    file_type: str
    summary: str
    apply_mode: str | None
    facts: dict[str, str]
    notes: list[str]
    problems: list[str]
    blocked_reason: str


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


class ConfigImportIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    text: str


class DeploymentTargetOut(ORM):
    device_id: str
    position: int
    config_version_id: str | None
    backup_version_id: str | None
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
    apply_mode: str
    created_by: str
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    targets: list[DeploymentTargetOut]
    events: list[DeploymentEventOut]


class DeploymentSummary(ORM):
    id: str
    project_id: str
    kind: str
    state: str
    dry_run: bool
    apply_mode: str
    created_by: str
    approved_by: str | None
    created_at: datetime


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
    integrity_verified: bool
    compatible_models: list[str]
    min_from_version: str | None
    release_notes: str
    status: str
    approved_by: str | None
    approved_at: datetime | None
    created_by: str
    created_at: datetime


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


class ConsoleBootstrapOut(BaseModel):
    status: str
    message: str
    commands_sent: list[str]
    findings: list[str]
    verified: bool
    saved: bool
    transcript: str
    sanitized_transcript: str
    network_reachable: bool | None
    network_hint: str
