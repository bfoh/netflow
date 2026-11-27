import pytest
from api_helpers import make_client

from undm.provisioning import console as console_mod
from undm.provisioning.simulated import SimulatedArubaConsole
from undm.services import provisioning as prov

PROFILE = {"vlan_id": 222, "vlan_name": "OOBM_VLAN", "untagged_port": "2",
           "address": "192.168.1.1/24"}
SIM_SWITCH = {"name": "dmz-sw", "manufacturer": "Aruba", "category": "switch", "model": "2930F",
              "os_family": "ArubaOS-Switch", "driver_id": "mock.aruba.aos_switch"}
REAL_SWITCH = dict(SIM_SWITCH, name="lab-sw", driver_id="ssh.aruba.aos_switch", environment="lab")


@pytest.fixture
def client():
    c, _ = make_client()
    with c:
        yield c


def add(client, body):
    pid = client.post("/api/projects", json={"name": "Staging " + body["name"]}).json()["id"]
    r = client.post(f"/api/projects/{pid}/devices", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def run(client, did, **over):
    body = {"serial_port": "SIMULATED", "profile": PROFILE, "confirm_device_name": "dmz-sw", **over}
    return client.post(f"/api/devices/{did}/provisioning/console-bootstrap", json=body)


def test_serial_ports_always_offer_the_simulated_console(client, monkeypatch):
    monkeypatch.setattr(prov, "list_serial_ports", lambda: [
        {"port": "COM7", "description": "USB Serial Port", "hardware_id": "USB VID:PID=0000:0000"}])
    ports = client.get("/api/provisioning/serial-ports").json()
    assert [p["port"] for p in ports] == ["SIMULATED", "COM7"]


def test_profile_is_stored_per_device_and_validated(client):
    did = add(client, dict(SIM_SWITCH, bootstrap_profile=PROFILE))
    assert client.get(f"/api/devices/{did}").json()["bootstrap_profile"] == PROFILE
    other = dict(PROFILE, untagged_port="3", address="192.168.1.2/24")
    assert client.patch(f"/api/devices/{did}", json={"bootstrap_profile": other}
                        ).json()["bootstrap_profile"]["address"] == "192.168.1.2/24"
    bad = client.patch(f"/api/devices/{did}", json={
        "bootstrap_profile": dict(PROFILE, untagged_port="2; reload")})
    assert bad.status_code == 422


def test_preview_lists_exact_commands_without_contacting_anything(client):
    did = add(client, SIM_SWITCH)
    r = client.post(f"/api/devices/{did}/provisioning/console-bootstrap/preview",
                    json={"profile": PROFILE}).json()
    assert r["supported"] and r["commands"] == [
        "configure", "vlan 222", 'name "OOBM_VLAN"', "untagged 2",
        "ip address 192.168.1.1 255.255.255.0", "exit", "write memory"]
    assert prov._simulated_consoles == {}


def test_simulated_bootstrap_end_to_end(client):
    did = add(client, SIM_SWITCH)
    out = run(client, did).json()
    assert out["status"] == "bootstrapped" and out["verified"] and out["saved"], out
    assert "<<< vlan 222" in out["transcript"]
    assert "192.168.1.1" not in out["sanitized_transcript"]
    d = client.get(f"/api/devices/{did}").json()
    assert d["provisioning_status"] == "bootstrapped"
    assert d["management_address"] == "192.168.1.1" and d["bootstrap_profile"] == PROFILE
    assert run(client, did).json()["status"] == "already_configured"
    entry = client.get("/api/audit", params={"target_id": did}).json()[0]
    assert entry["action"] == "provisioning.console_bootstrap"
    assert "transcript" not in entry["details"]


def test_confirmation_and_platform_rules(client):
    did = add(client, SIM_SWITCH)
    assert run(client, did, confirm_device_name="other").status_code == 409
    assert run(client, did, serial_port="COM3").status_code == 400  # simulated needs SIMULATED
    fw = add(client, {"name": "fw", "manufacturer": "Fortinet", "category": "firewall",
                      "driver_id": "mock.fortinet.fortios"})
    r = client.post(f"/api/devices/{fw}/provisioning/console-bootstrap",
                    json={"serial_port": "SIMULATED", "profile": PROFILE,
                          "confirm_device_name": "fw"})
    assert r.status_code == 400 and "No console bootstrap procedure" in r.json()["error"]
    pre = client.post(f"/api/devices/{fw}/provisioning/console-bootstrap/preview", json={}).json()
    assert pre["supported"] is False


def test_real_device_needs_write_switch_and_real_port(client, monkeypatch):
    did = add(client, REAL_SWITCH)
    opened = []
    monkeypatch.setattr(prov, "open_serial", lambda port, baud: opened.append(port))
    r = run(client, did, confirm_device_name="lab-sw", serial_port="COM7")
    assert r.status_code == 403 and "Real-device changes are off" in r.json()["error"]
    assert run(client, did, confirm_device_name="lab-sw").status_code == 400  # SIMULATED refused
    assert opened == []
    pre = client.post(f"/api/devices/{did}/provisioning/console-bootstrap/preview",
                      json={"profile": PROFILE}).json()
    assert any("Blocked at the moment" in n for n in pre["notes"])


def test_real_device_bootstrap_over_serial_when_writes_enabled(monkeypatch):
    sim = SimulatedArubaConsole()
    opened = []

    def fake_open(port, baud):
        opened.append((port, baud))
        return sim

    monkeypatch.setattr(prov, "open_serial", fake_open)
    monkeypatch.setattr(prov, "_tcp_reachable", lambda address, port=22, timeout=3.0: False)
    monkeypatch.setattr(prov.ConsoleSession, "settle_time", 0)
    monkeypatch.setattr(prov.aos_switch.time, "sleep", lambda s: None)
    client, _ = make_client(enable_real_device_writes=True)
    with client:
        did = add(client, REAL_SWITCH)
        out = run(client, did, confirm_device_name="lab-sw", serial_port="COM7",
                  baudrate=115200, profile=dict(PROFILE, untagged_port="3")).json()
    assert out["status"] == "bootstrapped", out
    assert opened == [("COM7", 115200)] and sim.closed
    assert sim.vlans[222]["untagged"] == {"3"}
    assert out["network_reachable"] is False and "port 3" in out["network_hint"]
    assert "192.168.1.51" in out["network_hint"] or "192.168.1.50" in out["network_hint"]
    # Bench cabling (D-091): the switch's port goes into the bench switch the PC is on.
    assert "Plug its port 3 into the bench switch the PC is on" in out["network_hint"]
    assert "then press Test (Stage a system, step 3)" in out["network_hint"]


def test_busy_com_port_gives_clear_error(monkeypatch):
    import serial

    def boom(**kwargs):
        raise serial.SerialException("could not open port 'COM7': PermissionError")

    monkeypatch.setattr(serial, "Serial", boom)
    with pytest.raises(console_mod.ConsoleError, match="Close any terminal program"):
        console_mod.open_serial("COM7")


def test_serial_parameters(monkeypatch):
    import serial
    seen = {}
    monkeypatch.setattr(serial, "Serial", lambda **kw: seen.update(kw) or object())
    console_mod.open_serial("COM4", 9600)
    assert (seen["port"], seen["baudrate"], seen["bytesize"], seen["parity"], seen["stopbits"]) \
        == ("COM4", 9600, 8, "N", 1)


def test_empty_factory_default_password_can_be_stored(client):
    import keyring
    from memory_keyring import MemoryKeyring
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    try:
        pid = client.post("/api/projects", json={"name": "Defaults"}).json()["id"]
        ref = client.post(f"/api/projects/{pid}/credential-refs",
                          json={"name": "aruba-factory"}).json()
        r = client.put(f"/api/credential-refs/{ref['id']}/secret",
                       json={"username": "manager", "password": ""})
        assert r.status_code == 200 and r.json()["has_secret"] is True
    finally:
        keyring.set_keyring(previous)


def test_default_console_speed_is_9600(monkeypatch):
    sim = SimulatedArubaConsole()
    opened = []
    monkeypatch.setattr(prov, "open_serial", lambda port, baud: opened.append(baud) or sim)
    monkeypatch.setattr(prov, "_tcp_reachable", lambda address, port=22, timeout=3.0: True)
    monkeypatch.setattr(prov.ConsoleSession, "settle_time", 0)
    monkeypatch.setattr(prov.aos_switch.time, "sleep", lambda s: None)
    client, _ = make_client(enable_real_device_writes=True)
    with client:
        did = add(client, REAL_SWITCH)
        out = client.post(f"/api/devices/{did}/provisioning/console-bootstrap", json={
            "serial_port": "COM3", "profile": PROFILE, "confirm_device_name": "lab-sw"}).json()
    assert out["status"] == "bootstrapped" and opened == [9600]
    assert out["network_reachable"] is True
    # Its console window opens with the port and speed that worked (D-126).
    with client:
        device = client.get(f"/api/devices/{did}").json()
    assert (device["console_port"], device["console_speed"]) == ("COM3", 9600)


def test_new_switch_first_login_sets_the_attached_login(monkeypatch):
    """New 2930F units ask 'Configure the manager credentials' first (seen 2026-11-19)."""
    import keyring
    from memory_keyring import MemoryKeyring

    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    sim = SimulatedArubaConsole(first_login_setup=True)
    monkeypatch.setattr(prov, "open_serial", lambda port, baud: sim)
    monkeypatch.setattr(prov, "_tcp_reachable", lambda address, port=22, timeout=3.0: True)
    monkeypatch.setattr(prov.ConsoleSession, "settle_time", 0)
    monkeypatch.setattr(prov.aos_switch.time, "sleep", lambda s: None)
    try:
        client, _ = make_client(enable_real_device_writes=True)
        with client:
            pid = client.post("/api/projects", json={"name": "New units"}).json()["id"]
            ref = client.post(f"/api/projects/{pid}/credential-refs",
                              json={"name": "approved login"}).json()
            client.put(f"/api/credential-refs/{ref['id']}/secret",
                       json={"username": "manager", "password": "Example-Only-Approved-1"})
            did = client.post(f"/api/projects/{pid}/devices", json=dict(
                REAL_SWITCH, credential_ref_id=ref["id"])).json()["id"]
            notes = client.post(f"/api/devices/{did}/provisioning/console-bootstrap/preview",
                                json={"profile": PROFILE}).json()["notes"]
            assert any("'approved login'" in n and "Configure the manager credentials" in n
                       for n in notes)
            out = run(client, did, confirm_device_name="lab-sw", serial_port="COM7").json()
            assert out["status"] == "bootstrapped", out["message"]
            assert out["credentials_set"] is True
            assert (sim.username, sim.password) == ("manager", "Example-Only-Approved-1")
            audit = client.get("/api/audit?limit=20").json()
            entry = next(a for a in audit if a["action"] == "provisioning.console_bootstrap")
            assert entry["details"]["first_login_credentials_set"] is True
            assert entry["details"]["credential"] == "approved login"
            assert "Example-Only-Approved-1" not in repr(out) + repr(audit)
    finally:
        keyring.set_keyring(previous)


def test_preconfigured_switch_is_erased_first_with_its_current_login(monkeypatch):
    """BH-DMZ units arrive preconfigured with a non-approved manager password (2026-11-23)."""
    import keyring
    from memory_keyring import MemoryKeyring

    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    sim = SimulatedArubaConsole(hostname="lab-bhdmz-sw01", username="manager",
                                password="Example-Only-Preconfigured", operator_level=True,
                                enable_login=True,
                                extra_config=["ip route 0.0.0.0 0.0.0.0 192.0.2.254"])
    monkeypatch.setattr(prov, "open_serial", lambda port, baud: sim)
    monkeypatch.setattr(prov, "_tcp_reachable", lambda address, port=22, timeout=3.0: True)
    monkeypatch.setattr(prov.ConsoleSession, "settle_time", 0)
    monkeypatch.setattr(prov.aos_switch.time, "sleep", lambda s: None)
    try:
        client, _ = make_client(enable_real_device_writes=True)
        with client:
            pid = client.post("/api/projects", json={"name": "BH-DMZ"}).json()["id"]

            def login(name, password):
                ref = client.post(f"/api/projects/{pid}/credential-refs",
                                  json={"name": name}).json()
                client.put(f"/api/credential-refs/{ref['id']}/secret",
                           json={"username": "manager", "password": password})
                return ref["id"]
            approved = login("approved login", "Example-Only-Approved-1")
            current = login("preconfigured login", "Example-Only-Preconfigured")
            did = client.post(f"/api/projects/{pid}/devices", json=dict(
                REAL_SWITCH, credential_ref_id=approved)).json()["id"]
            plain = run(client, did, confirm_device_name="lab-sw", serial_port="COM7").json()
            assert plain["status"] == "failed" and "enable" in plain["message"]
            # Read its name first, changing nothing (D-095): no typing of a hostname.
            before = list(sim.commands_received)
            seen = client.post(f"/api/devices/{did}/provisioning/console-identify", json={
                "serial_port": "COM7", "current_credential_ref_id": current}).json()
            assert seen["state"] == "configured" and seen["hostname"] == "lab-bhdmz-sw01"
            assert sim.hostname == "lab-bhdmz-sw01" and sim.password == "Example-Only-Preconfigured"
            sent = sim.commands_received[len(before):]
            assert not any(c.startswith(("erase", "write", "configure", "vlan")) for c in sent)
            # The device's own login must be the approved one: after the erase the switch is
            # set up as new with it. A login without a password is refused, nothing erased.
            refs = {r["name"]: r for r in client.get(f"/api/projects/{pid}/credential-refs").json()}
            assert refs["approved login"]["empty_password"] is False
            factory = login("factory login", "")
            listed = client.get(f"/api/projects/{pid}/credential-refs").json()
            assert listed[-1]["empty_password"] is True
            client.patch(f"/api/devices/{did}", json={"credential_ref_id": factory})
            sent_before = list(sim.commands_received)
            no_pw = run(client, did, confirm_device_name="lab-sw", serial_port="COM7",
                        erase_existing=True, current_credential_ref_id=current,
                        confirm_hostname="lab-bhdmz-sw01")
            assert no_pw.status_code == 409 and "Choose the approved login" in no_pw.json()["error"]
            assert "Nothing was erased" in no_pw.json()["error"]
            assert sim.commands_received == sent_before
            client.patch(f"/api/devices/{did}", json={"credential_ref_id": approved})
            missing = run(client, did, confirm_device_name="lab-sw", serial_port="COM7",
                          erase_existing=True)
            assert missing.status_code == 409 and "current login" in missing.json()["error"]
            out = run(client, did, confirm_device_name="lab-sw", serial_port="COM7",
                      erase_existing=True, current_credential_ref_id=current,
                      confirm_hostname="lab-bhdmz-sw01").json()
            assert out["status"] == "bootstrapped", (out["message"], out["transcript"])
            assert out["erased"] == "lab-bhdmz-sw01" and out["credentials_set"] is True
            assert (sim.username, sim.password) == ("manager", "Example-Only-Approved-1")
            audit = client.get("/api/audit?limit=20").json()
            entry = next(a for a in audit if a["action"] == "provisioning.console_bootstrap"
                         and a["details"]["erase_existing"])
            assert entry["details"]["erased_hostname"] == "lab-bhdmz-sw01"
            assert entry["details"]["current_login"] == "preconfigured login"
            shown = repr(out) + repr(audit)
            assert "Example-Only-Preconfigured" not in shown
            assert "Example-Only-Approved-1" not in shown
            # A failed setup keeps the console's last words for the bench log (2026-11-25: an
            # erase ended "Could not reach a command prompt" with nothing to show why).
            failed = [x for x in audit if x["action"] == "provisioning.console_bootstrap"
                      and "transcript_tail" in x["details"]]
            assert len(failed) == 1 and failed[0]["details"]["transcript_tail"].strip()
            log = client.get(f"/api/projects/{pid}/bench-log").text
            assert "console (last lines):" in log and "lab-bhdmz-sw01" not in log
            assert "Example-Only" not in log
    finally:
        keyring.set_keyring(previous)


# -- a switch whose password survives the erase (D-102, bench 2026-11-25) --------------------

def _two_logins(monkeypatch, sim):
    import keyring
    from memory_keyring import MemoryKeyring

    monkeypatch.setattr(prov, "open_serial", lambda port, baud: sim)
    monkeypatch.setattr(prov, "_tcp_reachable", lambda address, port=22, timeout=3.0: True)
    monkeypatch.setattr(prov.ConsoleSession, "settle_time", 0)
    monkeypatch.setattr(prov.aos_switch.time, "sleep", lambda s: None)
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    return previous


def test_after_an_erase_that_kept_the_password_the_approved_one_is_given(monkeypatch):
    import keyring

    sim = SimulatedArubaConsole(hostname="lab-bhdmz-sw02", username="manager",
                                password="Example-Only-Factory", operator_level=True,
                                enable_login=True, keep_passwords_on_erase=True,
                                extra_config=["ip route 0.0.0.0 0.0.0.0 192.0.2.254"])
    previous = _two_logins(monkeypatch, sim)
    try:
        client, _ = make_client(enable_real_device_writes=True)
        with client:
            pid = client.post("/api/projects", json={"name": "BH-DMZ"}).json()["id"]

            def login(name, password):
                ref = client.post(f"/api/projects/{pid}/credential-refs",
                                  json={"name": name}).json()
                client.put(f"/api/credential-refs/{ref['id']}/secret",
                           json={"username": "manager", "password": password})
                return ref["id"]
            approved = login("approved", "Example-Only-Approved-1")
            factory = login("factory", "Example-Only-Factory")
            did = client.post(f"/api/projects/{pid}/devices", json=dict(
                REAL_SWITCH, credential_ref_id=approved)).json()["id"]
            out = run(client, did, confirm_device_name="lab-sw", serial_port="COM7",
                      erase_existing=True, current_credential_ref_id=factory,
                      confirm_hostname="lab-bhdmz-sw02").json()
            assert out["status"] == "bootstrapped", (out["message"], out["transcript"])
            # The erase kept the old password (bench 2026-11-27); the team file does not set
            # one either, so the setup gives the switch the approved password itself.
            assert sim.erased == 1 and sim.password == "Example-Only-Approved-1"
            assert "Authentication failed" in out["transcript"]
            assert "trying the login it has now" in out["transcript"]
            assert "now has the approved login's password" in out["message"]
            assert "file sets the approved password" not in out["message"]
            assert "password manager" in out["commands_sent"]
            device = client.get(f"/api/devices/{did}").json()
            assert device["credential_ref_id"] == approved  # it answers to the approved now
            extra = (device["observed_facts"] or {}).get("extra") or {}
            assert not extra.get("login_after_loading_needed")
            assert "Example-Only" not in repr(out)
    finally:
        keyring.set_keyring(previous)


def test_without_erase_the_current_login_is_tried_when_enable_refuses_the_approved(monkeypatch):
    import keyring

    # The bench's second attempt: operator level without a password, manager with one.
    sim = SimulatedArubaConsole(username="manager", password="Example-Only-Factory",
                                operator_level=True, enable_login=True)
    previous = _two_logins(monkeypatch, sim)
    try:
        client, _ = make_client(enable_real_device_writes=True)
        with client:
            pid = client.post("/api/projects", json={"name": "Bench"}).json()["id"]
            refs = []
            for name, pw in (("approved", "Example-Only-Approved-1"),
                             ("factory", "Example-Only-Factory")):
                ref = client.post(f"/api/projects/{pid}/credential-refs",
                                  json={"name": name}).json()
                client.put(f"/api/credential-refs/{ref['id']}/secret",
                           json={"username": "manager", "password": pw})
                refs.append(ref["id"])
            did = client.post(f"/api/projects/{pid}/devices", json=dict(
                REAL_SWITCH, credential_ref_id=refs[0])).json()["id"]
            out = run(client, did, confirm_device_name="lab-sw", serial_port="COM7",
                      current_credential_ref_id=refs[1]).json()
            assert out["status"] == "bootstrapped", (out["message"], out["transcript"])
            assert "Unable to verify password" in out["transcript"]
            # It answered to its old password only: it now has the approved one.
            assert sim.password == "Example-Only-Approved-1"
            assert client.get(f"/api/devices/{did}").json()["credential_ref_id"] == refs[0]
    finally:
        keyring.set_keyring(previous)
