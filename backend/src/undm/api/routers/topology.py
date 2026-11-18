from ipaddress import IPv4Interface
from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from undm.api.deps import ActorDep, SessionDep
from undm.api.routers.projects import get_project
from undm.api.schemas import ORM, IssueOut
from undm.db.models import Device, TopologyLink, TopologyPosition
from undm.domain.topology import LinkInfo, NodeInfo, validate_topology
from undm.services import audit
from undm.services.errors import ConflictError, NotFoundError, ServiceError

router = APIRouter(tags=["topology"])


class LinkIn(BaseModel):
    a_device_id: str
    a_interface: str = Field(min_length=1, max_length=64)
    b_device_id: str
    b_interface: str = Field(min_length=1, max_length=64)
    mode: Literal["access", "trunk", "routed"] = "routed"
    vlans: list[int] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def _check(self) -> "LinkIn":
        if any(not 1 <= v <= 4094 for v in self.vlans):
            raise ValueError("VLAN IDs must be 1-4094")
        if self.mode == "routed" and self.vlans:
            raise ValueError("routed links do not carry VLANs")
        return self


class LinkOut(ORM):
    id: str
    a_device_id: str
    a_interface: str
    b_device_id: str
    b_interface: str
    mode: str
    vlans: list[int]
    notes: str


class NodeOut(BaseModel):
    device_id: str
    name: str
    category: str
    manufacturer: str
    model: str
    environment: str
    x: float | None
    y: float | None


class TopologyOut(BaseModel):
    nodes: list[NodeOut]
    links: list[LinkOut]
    issues: list[IssueOut]


class PositionIn(BaseModel):
    x: float
    y: float


def _node_info(d: Device) -> NodeInfo:
    addresses: dict[str, IPv4Interface] = {}
    vlans: set[int] = set()
    intent = d.intent or {}
    for i in intent.get("interfaces") or []:
        try:
            addresses[str(i["interface"]).lower()] = IPv4Interface(i["address"])
        except (KeyError, ValueError):
            continue
    for v in intent.get("vlans") or []:
        if isinstance(v, dict) and isinstance(v.get("vlan_id"), int):
            vlans.add(v["vlan_id"])
    return NodeInfo(d.id, d.name, addresses, frozenset(vlans))


def _topology(session: SessionDep, project_id: str) -> TopologyOut:
    devices = list(session.scalars(
        select(Device).where(Device.project_id == project_id).order_by(Device.name)))
    links = list(session.scalars(
        select(TopologyLink).where(TopologyLink.project_id == project_id)
        .order_by(TopologyLink.created_at)))
    positions = {p.device_id: p for p in session.scalars(
        select(TopologyPosition).where(TopologyPosition.device_id.in_([d.id for d in devices])))}
    issues = validate_topology(
        [_node_info(d) for d in devices],
        [LinkInfo(ln.id, ln.a_device_id, ln.a_interface, ln.b_device_id, ln.b_interface,
                  ln.mode, tuple(ln.vlans)) for ln in links])
    return TopologyOut(
        nodes=[NodeOut(device_id=d.id, name=d.name, category=d.category,
                       manufacturer=d.manufacturer, model=d.model, environment=d.environment,
                       x=positions[d.id].x if d.id in positions else None,
                       y=positions[d.id].y if d.id in positions else None) for d in devices],
        links=[LinkOut.model_validate(ln) for ln in links],
        issues=[IssueOut(severity=i.severity.value, code=i.code, message=i.message, path=i.path)
                for i in issues],
    )


@router.get("/api/projects/{project_id}/topology", response_model=TopologyOut)
def read_topology(project_id: str, session: SessionDep) -> TopologyOut:
    get_project(session, project_id)
    return _topology(session, project_id)


def _check_devices(session: SessionDep, project_id: str, body: LinkIn) -> None:
    for did in (body.a_device_id, body.b_device_id):
        d = session.get(Device, did)
        if d is None or d.project_id != project_id:
            raise ServiceError("Both ends of a link must be devices in this project")
    if body.a_device_id == body.b_device_id:
        raise ServiceError("A link must connect two different devices")


@router.post("/api/projects/{project_id}/topology/links", response_model=LinkOut,
             status_code=status.HTTP_201_CREATED)
def create_link(project_id: str, body: LinkIn, session: SessionDep,
                actor: ActorDep) -> TopologyLink:
    get_project(session, project_id)
    _check_devices(session, project_id, body)
    link = TopologyLink(project_id=project_id, **body.model_dump())
    session.add(link)
    session.flush()
    audit.record(session, actor, "topology.link.create", "topology_link", link.id,
                 details={"a": f"{body.a_device_id}:{body.a_interface}",
                          "b": f"{body.b_device_id}:{body.b_interface}", "mode": body.mode})
    return link


def _get_link(session: SessionDep, link_id: str) -> TopologyLink:
    link = session.get(TopologyLink, link_id)
    if link is None:
        raise NotFoundError("Link not found")
    return link


@router.put("/api/topology/links/{link_id}", response_model=LinkOut)
def update_link(link_id: str, body: LinkIn, session: SessionDep, actor: ActorDep) -> TopologyLink:
    link = _get_link(session, link_id)
    _check_devices(session, link.project_id, body)
    for k, v in body.model_dump().items():
        setattr(link, k, v)
    audit.record(session, actor, "topology.link.update", "topology_link", link.id)
    return link


@router.delete("/api/topology/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_link(link_id: str, session: SessionDep, actor: ActorDep) -> None:
    link = _get_link(session, link_id)
    session.delete(link)
    audit.record(session, actor, "topology.link.delete", "topology_link", link_id)


@router.put("/api/projects/{project_id}/topology/positions", response_model=TopologyOut)
def save_positions(project_id: str, body: dict[str, PositionIn],
                   session: SessionDep) -> TopologyOut:
    """Layout only; not audited as a design change."""
    get_project(session, project_id)
    for device_id, pos in body.items():
        d = session.get(Device, device_id)
        if d is None or d.project_id != project_id:
            raise ConflictError(f"Device {device_id} is not in this project")
        existing = session.get(TopologyPosition, device_id)
        if existing is None:
            session.add(TopologyPosition(device_id=device_id, x=pos.x, y=pos.y))
        else:
            existing.x, existing.y = pos.x, pos.y
    session.flush()
    return _topology(session, project_id)
