"""Database models.

Declared (user-entered) device attributes are kept separate from values
observed on the device (``observed_facts``), per the inventory requirements.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    false,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UtcDateTime(TypeDecorator[datetime]):
    """Timestamp stored and returned in UTC, always with its time zone.

    SQLite keeps no zone and returns naive values; without this the API sent times
    without a zone and browsers showed them as local time (an hour off in CET).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=_now, onupdate=_now
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    site: Mapped[str] = mapped_column(String(200), default="")
    purpose: Mapped[str] = mapped_column(String(200), default="")
    # Subject for self-signed HTTPS certificates created on the project's devices before a
    # file that needs one is loaded (organisation details; kept only in this database).
    certificate_subject: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    devices: Mapped[list[Device]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    credential_refs: Mapped[list[CredentialRef]] = relationship(cascade="all, delete-orphan")


class CredentialRef(TimestampMixin, Base):
    """A pointer to a secret held elsewhere. Never contains the secret."""

    __tablename__ = "credential_refs"
    __table_args__ = (UniqueConstraint("project_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # None: shared by all systems (D-105).
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(40), default="env")
    locator: Mapped[str] = mapped_column(String(200))


class Device(TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("project_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    # declared attributes
    manufacturer: Mapped[str] = mapped_column(String(80))
    product_family: Mapped[str] = mapped_column(String(80), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    hardware_revision: Mapped[str] = mapped_column(String(40), default="")
    category: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(80), default="")
    os_family: Mapped[str] = mapped_column(String(80), default="")
    firmware_version: Mapped[str] = mapped_column(String(80), default="")
    management_address: Mapped[str] = mapped_column(String(255), default="")
    management_protocol: Mapped[str] = mapped_column(String(20), default="ssh")
    management_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    management_vrf: Mapped[str] = mapped_column(String(80), default="")
    site: Mapped[str] = mapped_column(String(200), default="")
    rack_location: Mapped[str] = mapped_column(String(200), default="")
    driver_id: Mapped[str] = mapped_column(String(120))
    credential_ref_id: Mapped[str | None] = mapped_column(
        ForeignKey("credential_refs.id", ondelete="SET NULL"), nullable=True
    )
    environment: Mapped[str] = mapped_column(String(20), default="simulated")
    provisioning_status: Mapped[str] = mapped_column(String(30), default="planned")
    deployment_status: Mapped[str] = mapped_column(String(30), default="never_deployed")
    notes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[Any]] = mapped_column(default=list)
    intent: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    # Console bootstrap settings for this device (management VLAN, port, address).
    bootstrap_profile: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    # observed attributes (retrieved from the device)
    observed_facts: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    facts_retrieved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    last_connection_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    last_backup_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    last_deployment_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    # Set while a deployment is changing this device; prevents concurrent conflicting changes.
    locked_by_deployment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    project: Mapped[Project] = relationship(back_populates="devices")
    credential_ref: Mapped[CredentialRef | None] = relationship()


class ConfigVersion(Base):
    __tablename__ = "config_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # generated | backup
    text: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(String(40), default="")
    template_version: Mapped[str] = mapped_column(String(20), default="")
    verification: Mapped[str] = mapped_column(String(60), default="")
    reference: Mapped[str] = mapped_column(String(200), default="")  # driver backup handle
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now)


class FirmwareImage(Base):
    """An image file in the UNDM firmware repository (stored on disk, not in the DB)."""

    __tablename__ = "firmware_images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vendor: Mapped[str] = mapped_column(String(80))
    platform: Mapped[str] = mapped_column(String(40), index=True)  # driver platform key
    version: Mapped[str] = mapped_column(String(80))
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    vendor_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Vendors such as Fortinet publish SHA-512 (and MD5, not accepted) instead of SHA-256.
    vendor_sha512: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Approved although no vendor checksum could be matched: the approver's written reason.
    unverified_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    integrity_verified: Mapped[bool] = mapped_column(default=False)
    storage_path: Mapped[str] = mapped_column(String(500))
    compatible_models: Mapped[list[Any]] = mapped_column(default=list)
    min_from_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    release_notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="uploaded")  # uploaded/approved/retired
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now)


class DeploymentRecord(TimestampMixin, Base):
    __tablename__ = "deployments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="configuration",
                                      server_default="configuration")
    firmware_image_id: Mapped[str | None] = mapped_column(
        ForeignKey("firmware_images.id", name="fk_deployments_firmware_image_id"), nullable=True
    )
    window_start: Mapped[datetime | None] = mapped_column(UtcDateTime())
    window_end: Mapped[datetime | None] = mapped_column(UtcDateTime())
    state: Mapped[str] = mapped_column(String(30), index=True)
    dry_run: Mapped[bool] = mapped_column(default=False)
    # Firmware plans: install the approved image even where the device runs a newer one.
    allow_downgrade: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Firmware plans: also write the image into the secondary image slot.
    also_secondary: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Staging plans (D-071): the steps of one plan share staging_id and run in staging_step
    # order (1: base file, replace; 2: site file, merge); a step runs only after the one
    # before it succeeded.
    staging_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    staging_step: Mapped[int | None] = mapped_column(nullable=True)
    apply_mode: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[str] = mapped_column(String(120))
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())

    targets: Mapped[list[DeploymentTargetRecord]] = relationship(
        cascade="all, delete-orphan", order_by="DeploymentTargetRecord.position"
    )
    events: Mapped[list[DeploymentEventRecord]] = relationship(
        cascade="all, delete-orphan", order_by="DeploymentEventRecord.seq"
    )


class DeploymentTargetRecord(Base):
    __tablename__ = "deployment_targets"
    __table_args__ = (UniqueConstraint("deployment_id", "device_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    config_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("config_versions.id"), nullable=True
    )
    from_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    to_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    backup_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("config_versions.id"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(40))
    diff: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")
    # Secret slot id -> credential reference id, for settings of a supplied file whose
    # value comes from the credential store at execution. References only, never values.
    secret_refs: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    # Credential valid once this configuration is applied (the file changes the login).
    credential_after_ref_id: Mapped[str | None] = mapped_column(
        ForeignKey("credential_refs.id", ondelete="SET NULL",
                   name="fk_deployment_targets_credential_after_ref_id"), nullable=True
    )
    # The running configuration read back from the device once it was verified.
    after_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("config_versions.id", ondelete="SET NULL",
                   name="fk_deployment_targets_after_version_id"), nullable=True
    )


class DeploymentEventRecord(Base):
    __tablename__ = "deployment_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime())
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    stage: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now, index=True)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    outcome: Mapped[str] = mapped_column(String(30))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)


class TopologyLink(Base):
    """A designed link between two device interfaces (design intent, not proof of cabling)."""

    __tablename__ = "topology_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    a_device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    a_interface: Mapped[str] = mapped_column(String(64))
    b_device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    b_interface: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(20), default="routed")  # access/trunk/routed
    vlans: Mapped[list[Any]] = mapped_column(default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now)


class TopologyPosition(Base):
    """Where a device is drawn on the topology canvas. Layout only."""

    __tablename__ = "topology_positions"
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    x: Mapped[float] = mapped_column(default=0.0)
    y: Mapped[float] = mapped_column(default=0.0)


class AppSetting(Base):
    """A setting for all systems (D-105), e.g. default logins per role. JSON value."""

    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now, onupdate=_now)
