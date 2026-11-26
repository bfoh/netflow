"""Loading the Nokia 7705 SAR-Hmc's configuration file over its console as a plan (D-116), on
the simulated console.

Synthetic values only: a made-up system, file and password. The simulated unit accepts any
configuration line (SYNTHETIC); these tests prove UNDM's handling, not a real modem's."""

import keyring
import pytest
from api_helpers import make_client
from memory_keyring import MemoryKeyring
from test_sar_first_access import FAST, PASSWORD, SIM_MODEM, add, go

from undm.drivers.base import ApplyMode, Credentials, DeviceTarget
from undm.drivers.nokia import sar_files
from undm.drivers.nokia.sar_console import NokiaSarConsole
from undm.provisioning.console import port_lock
from undm.provisioning.simulated_sar import SimulatedSarConsole
from undm.services import provisioning as prov

NAME = "LTEmodemABCB007-Zone041"
FILE = ("# TiMOS-B-20.5.R1 both/sar Nokia 7705 SAR (example)\r\n# Generated (example)\r\n\r\n"
        "exit all\r\nconfigure\r\n#--------------------------------------------------\r\n"
        'echo "System Configuration"\r\n#--------------------------------------------------\r\n'
        f'    system\r\n        name "{NAME}"\r\n        security\r\n'
        '            user "admin"\r\n                password "${admin_password}"\r\n'
        "            exit\r\n        exit\r\n    exit\r\n"
        '    router\r\n        interface "pdn-loopback"\r\n            address 130.41.1.221/32\r\n'
        "        exit\r\n    exit\r\nexit all\r\n\r\n"
        "config system security snmp community example r version both\r\n"
        "config system snmp no shutdown\r\n\r\nadmin save\r\n\r\n# Finished (example)\r\n")


@pytest.fixture
def modem(monkeypatch):
    sim = SimulatedSarConsole.ready(PASSWORD)
    opened = []

    def open_console(port, speed):
        opened.append((port, speed))
        return sim
    monkeypatch.setattr(NokiaSarConsole, "open_console", staticmethod(open_console))
    monkeypatch.setattr(NokiaSarConsole, "wake_timeout", 1.0)
    monkeypatch.setattr(NokiaSarConsole, "line_timeout", 1.0)
    monkeypatch.setattr(NokiaSarConsole, "settle_time", 0.0)
    sim.opened = opened
    return sim


def driver(password=PASSWORD, port="COM9"):
    return NokiaSarConsole(DeviceTarget("d1", "", console_port=port),
                           Credentials("admin", password))


def test_the_file_is_read_as_the_team_writes_it():
    plan = sar_files.plan_load(FILE)
    assert plan.system_name == NAME and plan.password_slot and plan.markers == []
    assert plan.skipped == {"comment": 5, "blank": 5, "echo": 1, "save": 1}
    sent = [line.strip() for _, line in plan.lines]
    assert sent[:2] == ["exit all", "configure"] and sent[-1] == "config system snmp no shutdown"
    assert not any(s.startswith(("#", "echo", "admin save")) for s in sent)
    report = NokiaSarConsole.inspect_config_file(FILE)
    assert report is not None and report.apply_mode is ApplyMode.MERGE and not report.problems
    assert report.facts == {"lines to send": str(len(plan.lines)), "system name": NAME}
    assert any("from the modem's login" in n for n in report.notes)
    unready = NokiaSarConsole.inspect_config_file(FILE.replace("Zone041", "Zone${zone3}"))
    assert unready is not None and "${zone3}" in unready.problems[0]
    assert NokiaSarConsole.inspect_config_file("hostname x\n") is None


def test_the_load_logs_in_sends_line_by_line_saves_and_proves_it(modem):
    d = driver()
    assert d.connect().ok and modem.opened == [("COM9", 115200)]
    assert d.check_before_apply(FILE, ApplyMode.MERGE) is None
    before = d.backup_configuration()
    assert before.ok and "configure" in before.data.text
    result = d.apply_configuration(d.prepare_for_device(FILE, {}), ApplyMode.MERGE)
    assert result.ok, result.message
    assert "not sent: 5 comment, 1 echo, 1 'admin save'" in result.data["notes"][0]
    assert modem.unsaved and modem.file_password == PASSWORD  # nothing saved yet
    assert d.save_configuration().ok and not modem.unsaved
    verified = d.verify_configuration(FILE, ApplyMode.MERGE)
    assert verified.ok and NAME in verified.message
    running = d.get_running_configuration()
    assert running.ok and f'name "{NAME}"' in running.data
    assert set(d.expected_lines(FILE)) <= d.present_lines(running.data)
    transcript = d._session.transcript_text
    d.disconnect()
    # The password reached the modem, never the transcript (both directions are masked).
    assert f'password "{PASSWORD}"' in modem.commands_received
    assert PASSWORD not in transcript and "********" in transcript
    assert "echo" not in " ".join(modem.commands_received)
    assert modem.commands_received[-1] == "logout"
    assert port_lock("COM9").acquire(blocking=False)  # released
    port_lock("COM9").release()


def test_a_refused_line_stops_the_load_unsaved_with_the_modems_words(modem):
    modem.fail_on = {'address 130.41.1.221/32'}
    d = driver()
    result = d.apply_configuration(d.prepare_for_device(FILE, {}), ApplyMode.MERGE)
    assert not result.ok
    assert result.message.startswith("File line 19 'address 130.41.1.221/32': the modem "
                                     "answered 'MINOR: CLI Simulated refusal")
    assert "Nothing was saved" in result.message and "admin save" not in modem.commands_received
    assert "switched off and on, the modem starts with its saved" in d.manual_recovery()
    assert PASSWORD not in result.message + str(result.diagnostics)
    after = modem.commands_received.index("address 130.41.1.221/32")
    assert modem.commands_received[after + 1:] == []  # nothing sent after the refused line
    d.disconnect()


def test_what_is_refused_before_anything_is_sent(modem):
    d = driver()
    assert "merge" in d.check_before_apply(FILE, ApplyMode.REPLACE).message
    assert "not a configuration file" in d.check_before_apply("hostname x\n",
                                                              ApplyMode.MERGE).message
    assert "${zone}" in d.check_before_apply(FILE + "x ${zone}\n", ApplyMode.MERGE).message
    written = FILE.replace("${admin_password}", "Another-Example-9")
    assert "not the password of the modem's login" in d.check_before_apply(
        written, ApplyMode.MERGE).message
    assert d.check_before_apply(FILE.replace("${admin_password}", PASSWORD),
                                ApplyMode.MERGE) is None
    spaced = driver(password="two words").check_before_apply(FILE, ApplyMode.MERGE)
    assert "must not contain spaces" in spaced.message
    assert modem.commands_received == []  # none of these opened the console


def test_the_console_login_cases(modem, monkeypatch):
    no_port = NokiaSarConsole(DeviceTarget("d1", ""), Credentials("admin", PASSWORD)).connect()
    assert not no_port.ok and "Console setup saves it" in no_port.message
    refused = driver(password="Wrong-Example-1").connect()
    assert not refused.ok and refused.diagnostics.get("login_refused")
    with port_lock("COM9"):
        busy = driver().connect()
    assert not busy.ok and "in use by another console session" in busy.message
    # Someone is still logged in on the console: UNDM logs out and in with its own login.
    modem._state = "cli"
    d = driver()
    assert d.connect().ok and [c for c in modem.commands_received if c][:1] == ["logout"]
    d.disconnect()
    silent = SimulatedSarConsole.ready(PASSWORD, silent=True)
    monkeypatch.setattr(NokiaSarConsole, "open_console", staticmethod(lambda port, speed: silent))
    quiet = driver().connect()
    assert not quiet.ok and "No login prompt from the modem on COM9" in quiet.message


def test_first_access_then_its_file_as_a_plan(monkeypatch):
    """The wizard's path on a real (here simulated) modem: Console setup saves the port, then a
    staging plan loads the file over it, with approval and the real-device switch."""
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    sim = SimulatedSarConsole()

    def open_serial(port, baud):
        sim.power_cycle()
        return sim
    monkeypatch.setattr(prov, "open_serial", open_serial)
    monkeypatch.setattr(prov.sros_sar, "Timing", lambda **kw: FAST)
    monkeypatch.setattr(NokiaSarConsole, "open_console", staticmethod(lambda port, speed: sim))
    monkeypatch.setattr(NokiaSarConsole, "wake_timeout", 1.0)
    monkeypatch.setattr(NokiaSarConsole, "settle_time", 0.0)
    client, _ = make_client(enable_real_device_writes=True)
    try:
        with client:
            did = add(client, dict(SIM_MODEM, name="bench-modem", driver_id="console.nokia.sar",
                                   environment="lab"))
            assert go(client, did, name="bench-modem", serial_port="COM7").json()["status"] \
                == "bootstrapped"
            device = client.get(f"/api/devices/{did}").json()
            assert device["console_port"] == "COM7"
            version = client.post(f"/api/devices/{did}/configs/import", json={
                "filename": "LTEModemz41.txt", "text": FILE}).json()
            pid = device["project_id"]
            r = client.post(f"/api/projects/{pid}/device-staging", json={
                "device_id": did, "steps": [{"kind": "configuration",
                                             "version_id": version["id"]}]})
            assert r.status_code == 201, r.text
            assert r.json()["steps"][0]["apply_mode"] == "merge"
            sid = r.json()["staging_id"]
            assert client.post(f"/api/staging-plans/{sid}/approve").status_code == 200
            out = client.post(f"/api/staging-plans/{sid}/execute?background=false").json()
            step = out["steps"][0]
            events = " | ".join(e["message"] for e in step["events"])
            assert step["state"] == "succeeded", events
            assert "configuration line(s) sent over the console" in events
            assert "system name " + NAME in events
            assert sim.system_name == NAME and not sim.unsaved
            assert PASSWORD not in repr(out) + client.get("/api/audit").text
    finally:
        keyring.set_keyring(previous)
        prov.reset_simulation()


def test_a_console_only_device_without_its_port_is_told_where_to_set_it(monkeypatch):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    client, _ = make_client(enable_real_device_writes=True)
    try:
        with client:
            did = add(client, dict(SIM_MODEM, name="bench-modem", driver_id="console.nokia.sar",
                                   environment="lab"))
            r = client.post(f"/api/devices/{did}/operations/check_reachability")
            assert r.status_code == 400 and "which serial port" in r.json()["error"]
            bad = client.patch(f"/api/devices/{did}", json={"console_port": "COM9; rm"})
            assert bad.status_code == 422
            ok = client.patch(f"/api/devices/{did}", json={"console_port": "COM9"})
            assert ok.status_code == 200 and ok.json()["console_port"] == "COM9"
    finally:
        keyring.set_keyring(previous)
