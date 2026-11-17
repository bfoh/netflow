"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

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
    provider: str = "env"
    locator: str = Field(min_length=1, max_length=200)


class CredentialRefOut(ORM):
    id: str
    name: str
    provider: str
    locator: str


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


class ConfigVersionFull(ConfigVersionOut):
    text: str


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


class DeploymentTargetOut(ORM):
    device_id: str
    position: int
    config_version_id: str
    backup_version_id: str | None
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
