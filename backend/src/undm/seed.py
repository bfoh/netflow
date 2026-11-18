"""Create a demonstration project with synthetic, simulated devices.

    python -m undm.seed

All names and addresses are fictional (RFC 1918 / RFC 5737 ranges). Running it
again is harmless: an existing demo project is left untouched.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from undm.config import get_settings
from undm.db.models import Device, Project
from undm.db.session import make_engine, make_session_factory
from undm.domain.intent import DeviceIntent
from undm.services import audit

DEMO_PROJECT = "Demo Branch Site"


def _intent(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and store intent in the same complete form the API stores."""
    return DeviceIntent.model_validate(raw).model_dump(mode="json")


def seed(session_factory=None) -> str:  # type: ignore[no-untyped-def]
    factory = session_factory or make_session_factory(make_engine(get_settings().database_url))
    with factory() as s:
        existing = s.scalars(select(Project).where(Project.name == DEMO_PROJECT)).first()
        if existing:
            return existing.id
        p = Project(name=DEMO_PROJECT, description="Synthetic demonstration project",
                    site="Example Site A", purpose="Branch office LAN and internet edge")
        s.add(p)
        s.flush()
        switch = Device(
            project_id=p.id, name="branch-sw-01", manufacturer="Aruba",
            product_family="CX 6300", model="6300M", category="switch", role="access-switch",
            os_family="AOS-CX", management_address="10.255.0.11", management_protocol="ssh",
            site="Example Site A", rack_location="Rack 1 / U20",
            driver_id="mock.aruba.aoscx", environment="simulated", tags=["demo"],
            intent=_intent({
                "hostname": "branch-sw-01",
                "vlans": [{"vlan_id": 10, "name": "users"}, {"vlan_id": 20, "name": "voice"},
                          {"vlan_id": 99, "name": "mgmt"}],
                "interfaces": [{"interface": "vlan99", "address": "10.255.0.11/24",
                                "description": "management"}],
                "static_routes": [{"prefix": "0.0.0.0/0", "next_hop": "10.255.0.1"}],
            }),
        )
        firewall = Device(
            project_id=p.id, name="branch-fw-01", manufacturer="Fortinet",
            product_family="FortiGate", model="FortiGate-60F", category="firewall",
            role="edge-firewall", os_family="FortiOS", management_address="10.255.0.1",
            management_protocol="https_api", site="Example Site A", rack_location="Rack 1 / U22",
            driver_id="mock.fortinet.fortios", environment="simulated", tags=["demo"],
            intent=_intent({
                "hostname": "branch-fw-01",
                "interfaces": [
                    {"interface": "internal1", "address": "10.255.0.1/24"},
                    {"interface": "wan1", "address": "198.51.100.2/30"},
                ],
                "static_routes": [{"prefix": "0.0.0.0/0", "next_hop": "198.51.100.1",
                                   "egress_interface": "wan1"}],
            }),
        )
        s.add_all([switch, firewall])
        s.flush()
        audit.record(s, "seed", "project.seed", "project", p.id, details={"name": p.name})
        s.commit()
        return p.id


if __name__ == "__main__":
    print(seed())
