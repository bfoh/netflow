from fastapi.testclient import TestClient

from undm.api.app import create_app
from undm.config import Settings
from undm.db.models import Base
from undm.db.session import make_engine, make_session_factory


def make_client(**settings_kw):
    # In-memory by default; tests with background runs pass a file database, because one
    # shared in-memory connection must not be used by two threads at once.
    database_url = settings_kw.pop("database_url", "sqlite://")
    settings = Settings(database_url=database_url, log_level="WARNING", **settings_kw)
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    app = create_app(settings=settings, session_factory=factory)
    return TestClient(app), factory


SWITCH = {
    "name": "sw1", "manufacturer": "Aruba", "category": "switch", "role": "access-switch",
    "driver_id": "mock.aruba.aoscx", "management_address": "10.255.0.11",
    "model": "6300M", "os_family": "AOS-CX",
}
FIREWALL = {
    "name": "fw1", "manufacturer": "Fortinet", "category": "firewall", "role": "edge-firewall",
    "driver_id": "mock.fortinet.fortios", "management_address": "10.255.0.1",
}
SWITCH_INTENT = {
    "hostname": "sw1",
    "vlans": [{"vlan_id": 99, "name": "mgmt"}],
    "interfaces": [{"interface": "vlan99", "address": "10.255.0.11/24"}],
    "static_routes": [{"prefix": "0.0.0.0/0", "next_hop": "10.255.0.1"}],
}
FIREWALL_INTENT = {
    "hostname": "fw1",
    "interfaces": [{"interface": "internal1", "address": "10.255.0.1/24"}],
}
