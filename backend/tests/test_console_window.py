"""A console window for every real device (D-126, amends D-118): the port and speed are
chosen in order, saved, audited; UNDM types nothing. No program is started in tests."""

import pytest
from api_helpers import make_client

from undm.api.routers import devices as router
from undm.provisioning.console import port_lock
from undm.services import devices as devsvc


@pytest.fixture
def env(monkeypatch):
    started: list[list[str]] = []
    monkeypatch.setattr(devsvc, "launch_console", started.append)
    monkeypatch.setattr(devsvc, "_putty", lambda: None)
    monkeypatch.setattr(router, "_from_this_pc", lambda request: True)
    c, _ = make_client()
    with c:
        yield c, started


def add(c, **body):
    pid = c.post("/api/projects", json={"name": f"Practice {body['name']}"}).json()["id"]
    r = c.post(f"/api/projects/{pid}/devices", json={
        "manufacturer": "x", "category": "switch", "environment": "lab",
        "management_address": "192.168.1.1", **body})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.parametrize(("driver", "speed", "source"), [
    ("ssh.aruba.aos_switch", 9600, "team"),
    ("ssh.fortinet.fortios", 9600, "Fortinet"),
    ("ssh.blackbox.lig1014a", 115200, "Black Box"),
    ("console.nokia.sar", 115200, "Nokia"),
])
def test_each_model_opens_at_its_documented_speed(env, driver, speed, source):
    c, started = env
    did = add(c, name=driver, driver_id=driver)
    settings = c.get(f"/api/devices/{did}/console-settings").json()
    assert settings["console_speed"] == speed and source in settings["source"]
    assert settings["console_port"] is None
    r = c.post(f"/api/devices/{did}/open-console")
    assert r.status_code == 409 and "COM port" in r.json()["error"]
    out = c.post(f"/api/devices/{did}/open-console", json={"console_port": "COM4"}).json()
    assert out["console_speed"] == speed and started[-1][-2:] == ["COM4", str(speed)]
    device = c.get(f"/api/devices/{did}").json()
    assert device["console_port"] == "COM4" and device["console_speed"] is None  # its model's
    saved = [a for a in c.get("/api/audit").json() if a["action"] == "device.console_port_set"]
    assert saved and saved[0]["details"]["console_port"] == "COM4"


def test_a_model_without_a_documented_speed_asks_for_one_and_keeps_it(env):
    c, started = env
    did = add(c, name="iosxe", driver_id="ssh.cisco.iosxe")
    assert c.get(f"/api/devices/{did}/console-settings").json()["console_speed"] is None
    r = c.post(f"/api/devices/{did}/open-console", json={"console_port": "COM5"})
    assert r.status_code == 409 and "console speed" in r.json()["error"]
    out = c.post(f"/api/devices/{did}/open-console",
                 json={"console_port": "COM5", "console_speed": 19200}).json()
    assert out["console_speed"] == 19200 and started[-1][-2:] == ["COM5", "19200"]
    assert c.get(f"/api/devices/{did}").json()["console_speed"] == 19200
    again = c.get(f"/api/devices/{did}/console-settings").json()
    assert (again["console_port"], again["console_speed"], again["source"]) == (
        "COM5", 19200, "saved for this device")


def test_putty_gets_the_port_and_speed_and_nothing_else(env, monkeypatch):
    c, started = env
    monkeypatch.setattr(devsvc, "_putty", lambda: r"C:\PuTTY\putty.exe")
    did = add(c, name="sw", driver_id="ssh.aruba.aos_switch", console_port="COM3")
    out = c.post(f"/api/devices/{did}/open-console").json()
    assert out["program"] == "putty"
    assert started[-1] == [r"C:\PuTTY\putty.exe", "-serial", "COM3", "-sercfg", "9600,8,n,1,N"]


def test_refusals(env):
    c, started = env
    sim = add(c, name="sim", driver_id="mock.aruba.aos_switch", environment="simulated")
    assert c.post(f"/api/devices/{sim}/open-console").status_code == 409
    did = add(c, name="sw2", driver_id="ssh.aruba.aos_switch")
    for port in ("SIMULATED", "-oProxyCommand"):
        r = c.post(f"/api/devices/{did}/open-console", json={"console_port": port})
        assert r.status_code in (409, 422), port
    assert c.post(f"/api/devices/{did}/open-console",
                  json={"console_port": "COM3", "console_speed": 12345}).status_code == 422
    with port_lock("COM3"):
        r = c.post(f"/api/devices/{did}/open-console", json={"console_port": "COM3"})
    assert r.status_code == 409 and "UNDM is using COM3" in r.json()["error"]
    assert started == []


def test_reading_the_settings_writes_nothing(env):
    c, _ = env
    did = add(c, name="fw", driver_id="ssh.fortinet.fortios")
    before = len(c.get("/api/audit").json())
    c.get(f"/api/devices/{did}/console-settings")
    assert len(c.get("/api/audit").json()) == before


def test_the_speed_can_be_set_on_the_device(env):
    c, _ = env
    did = add(c, name="bb", driver_id="ssh.blackbox.lig1014a")
    assert c.patch(f"/api/devices/{did}", json={"console_speed": 9600}).json()["console_speed"] \
        == 9600
    assert c.patch(f"/api/devices/{did}", json={"console_speed": 1234}).status_code == 422
