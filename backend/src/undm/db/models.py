"""Database models.

Declared (user-entered) device attributes are kept separate from values
observed on the device (``observed_facts``), per the inventory requirements.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    site: Mapped[str] = mapped_column(String(200), default="")
    purpose: Mapped[str] = mapped_column(String(200), default="")

    devices: Mapped[list[Device]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    credential_refs: Mapped[list[CredentialRef]] = relationship(cascade="all, delete-orphan")


class CredentialRef(TimestampMixin, Base):
    """A pointer to a secret held elsewhere. Never contains the secret."""

    __tablename__ = "credential_refs"
    __table_args__ = (UniqueConstraint("project_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
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
    # observed attributes (retrieved from the device)
    observed_facts: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    facts_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_connection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_backup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_deployment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DeploymentRecord(TimestampMixin, Base):
    __tablename__ = "deployments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(30), index=True)
    dry_run: Mapped[bool] = mapped_column(default=False)
    apply_mode: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[str] = mapped_column(String(120))
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    config_version_id: Mapped[str] = mapped_column(ForeignKey("config_versions.id"))
    backup_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("config_versions.id"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(40))
    diff: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")


class DeploymentEventRecord(Base):
    __tablename__ = "deployment_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    stage: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    outcome: Mapped[str] = mapped_column(String(30))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
