from sqlalchemy import select

from undm.db.models import Base, Device
from undm.db.session import make_engine, make_session_factory
from undm.seed import seed


def test_seed_is_idempotent_and_synthetic():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    pid = seed(factory)
    assert seed(factory) == pid
    with factory() as s:
        devices = s.scalars(select(Device)).all()
    assert {d.manufacturer for d in devices} == {"Aruba", "Fortinet"}
    assert all(d.environment == "simulated" for d in devices)
