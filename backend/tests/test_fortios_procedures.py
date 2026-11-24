"""FortiOS procedures against a fake FortiGate that really fetches files over TFTP.

The FortiGate's wording is synthetic (see fake_fortigate.py). These tests prove the
driver's decisions - what it answers, what stops it, what evidence it needs and what
it never reveals - not compatibility with hardware.
"""

import hashlib
from dataclasses import dataclass

import pytest
from fake_fortigate import FakeFortiGate, fake_image
from fake_netmiko import Scenario, factory_for
from test_fortios_files import BACKUP, SCRIPT

from undm.drivers.base import ApplyMode, Credentials, DeviceTarget, FirmwareImageRef, ResultStatus
from undm.drivers.fortinet.fortios_ssh import FortiOSSsh
from undm.drivers.ssh.base import SshCliDriver
from undm.transfer.hub import TransferHub

SLOT = "vdom > root > vpn ipsec phase1-interface > example-tunnel > psksecret"
PSK = "Example-Only-Psk-77"


@dataclass
class Rig:
    driver: FortiOSSsh
    fg: FakeFortiGate


def tune(monkeypatch):
    monkeypatch.setattr(SshCliDriver, "poll_interval", 0.005)
    monkeypatch.setattr(FortiOSSsh, "script_poll_interval", 0.001)
    monkeypatch.setattr(FortiOSSsh, "question_timeout", 0.3)
    monkeypatch.setattr(FortiOSSsh, "statement_timeout", 0.5)
    monkeypatch.setattr(FortiOSSsh, "transfer_timeout", 1.5)
    monkeypatch.setattr(FortiOSSsh, "restart_probe_interval", 0.0)


@pytest.fixture
def rig(monkeypatch):
    tune(monkeypatch)
    hub = TransferHub("127.0.0.1", 0)
    fg = FakeFortiGate(tftp_port=lambda: hub.port, password="Example-Only-1")
    sc = Scenario(device=fg)
    monkeypatch.setattr(SshCliDriver, "connection_factory", staticmethod(factory_for(sc)))
    with hub.session() as files:
        d = FortiOSSsh(DeviceTarget("d1", "127.0.0.1", None),
                       Credentials("admin", "Example-Only-1"))
        d.file_server = files
        assert d.connect().ok
        yield Rig(d, fg)
    assert not hub.running


def image(tmp_path, version="7.6.5"):
    data = fake_image(version)
    path = tmp_path / "FGT_101F-v7.6.5-FORTINET.out"
    path.write_bytes(data)
    return FirmwareImageRef(version, path.name, hashlib.sha256(data).hexdigest(), len(data),
                            str(path))


# -- firmware ------------------------------------------------------------------------

def test_firmware_version_is_read_from_status(rig):
    info = rig.driver.get_firmware_information()
    assert info.ok and info.data["running"] == "v7.2.7" and info.data["build"] == "1577"


def test_firmware_is_fetched_confirmed_and_the_unit_restarts(rig, tmp_path):
    r = rig.driver.stage_firmware(image(tmp_path))
    assert r.ok, (r.message, r.diagnostics)
    assert rig.fg.keys == ["y"] and rig.fg.restarts == 1 and rig.fg.version == "v7.6.5"
    assert rig.driver.install_firmware().ok and rig.driver.reboot().ok
    assert rig.driver.reboot().status is ResultStatus.FAILED  # only one restart was started


def test_progress_marks_while_fetching_are_not_the_prompt(rig, tmp_path):
    """Bench, 101F v7.2.6 (2026-11-24): UNDM took the first line of '#' progress marks
    for the prompt and reported "Transfer incomplete (5581824 of 101271832 bytes)"."""
    rig.fg.progress_marks, rig.fg.fetch_delay = True, 0.002
    r = rig.driver.stage_firmware(image(tmp_path))
    assert r.ok, (r.message, r.diagnostics)
    assert rig.fg.restarts == 1 and rig.fg.version == "v7.6.5"
    assert rig.fg.blocks_received >= 20  # at least one line of '#' marks was printed


def test_a_fetch_still_running_when_undm_stops_waiting_is_cancelled(rig, tmp_path):
    """A step UNDM reports as failed must not complete later: the file is withdrawn and
    the unit's fetch is cut off, so it cannot install the image afterwards."""
    rig.fg.progress_marks, rig.fg.fetch_delay = True, 0.01
    rig.driver.should_stop = lambda: rig.fg.blocks_received >= 40
    img = image(tmp_path)
    r = rig.driver.stage_firmware(img)
    assert r.status is ResultStatus.FAILED and "Transfer incomplete" in r.message
    assert "cannot finish fetching it later" in r.message
    assert rig.fg.fetch_done.wait(10)
    assert rig.fg.fetch_failed and rig.fg.restarts == 0 and rig.fg.version == "v7.2.7"
    record = rig.driver.file_server.last_transfer(img.filename, "127.0.0.1")
    assert not record.completed and record.error.startswith("cancelled by UNDM")


def test_rejected_image_is_a_failure_with_the_units_answer(rig, tmp_path):
    rig.fg.image_rejected = True
    r = rig.driver.stage_firmware(image(tmp_path))
    assert r.status is ResultStatus.FAILED and "did not accept it" in r.message
    assert "Image check failed" in r.diagnostics["device_output"]
    assert rig.fg.restarts == 0


def test_an_unexpected_question_is_never_answered(rig, tmp_path):
    img = image(tmp_path)
    rig.fg.question_on[f"execute restore image tftp {img.filename} 127.0.0.1"] = (
        "Image signature could not be verified. Continue? (y/n)")
    r = rig.driver.stage_firmware(img)
    assert r.status is ResultStatus.FAILED and "did not request the image" in r.message
    assert rig.fg.keys == [] and rig.fg.restarts == 0
    assert "signature" in r.diagnostics["device_output"]


def test_a_unit_that_goes_silent_is_not_reported_as_restarting(rig, tmp_path, monkeypatch):
    from undm.drivers.ssh import base as ssh_base
    monkeypatch.setattr(ssh_base, "tcp_port_open", lambda host, port, timeout=3.0: True)
    rig.fg.restart_mode = "silent"
    r = rig.driver.stage_firmware(image(tmp_path))
    assert r.status is ResultStatus.FAILED and "neither restarted" in r.message


def test_a_unit_restarting_without_closing_the_session_is_noticed(rig, tmp_path, monkeypatch):
    """Lesson from the 2930F bench (D-054): the session can stay open and silent while the
    unit restarts. Its SSH port then stops answering, which UNDM checks."""
    from undm.drivers.ssh import base as ssh_base
    monkeypatch.setattr(ssh_base, "tcp_port_open",
                        lambda host, port, timeout=3.0: rig.fg.restarts == 0)
    rig.fg.restart_mode = "silent"
    r = rig.driver.stage_firmware(image(tmp_path))
    assert r.ok, (r.message, r.diagnostics)
    assert "is restarting (its SSH port stopped answering)" in r.message


# -- full backup restore ----------------------------------------------------------------

def test_full_backup_is_restored_by_tftp_and_checked_by_facts(rig):
    r = rig.driver.apply_configuration(BACKUP, ApplyMode.REPLACE)
    assert r.ok and r.data == {"restarting": True}, r.message
    assert rig.fg.vdoms and rig.fg.hostname == "lab-fw-base" and rig.fg.keys == ["y"]
    assert rig.fg.fetched and rig.fg.fetched[0].startswith("undm-")  # not the original name
    assert not rig.driver.connect().ok  # still restarting
    assert rig.driver.connect().ok
    v = rig.driver.verify_configuration(BACKUP, ApplyMode.REPLACE)
    assert v.ok and "VDOMs multiple" in v.message


def test_base_restore_prompt_then_restart_is_waited_for(rig, monkeypatch):
    """Bench, 101F v7.6.5 (2026-11-24): after "File check OK." the unit showed its prompt;
    UNDM reported "did not accept it" within 3 s. The prompt after a clean check now means
    waiting for the restart."""
    from undm.drivers.ssh import base as ssh_base
    monkeypatch.setattr(ssh_base, "tcp_port_open", lambda host, port, timeout=3.0: True)
    rig.fg.restart_mode = "prompt_then_close"
    r = rig.driver.apply_configuration(BACKUP, ApplyMode.REPLACE)
    assert r.ok and r.data == {"restarting": True}, (r.message, r.diagnostics)
    assert "returned to its prompt, then closed the session to restart" in r.message
    assert rig.fg.restarts == 1 and rig.fg.hostname == "lab-fw-base"


def test_prompt_then_ssh_port_down_is_a_restart(rig, monkeypatch):
    from undm.drivers.ssh import base as ssh_base
    monkeypatch.setattr(ssh_base, "tcp_port_open", lambda host, port, timeout=3.0: False)
    rig.fg.restart_mode = "prompt_only"
    r = rig.driver.apply_configuration(BACKUP, ApplyMode.REPLACE)
    assert r.ok and "then restarted (its SSH port stopped answering)" in r.message


def test_prompt_without_a_restart_is_reported_after_the_grace(rig, monkeypatch):
    from undm.drivers.ssh import base as ssh_base
    monkeypatch.setattr(ssh_base, "tcp_port_open", lambda host, port, timeout=3.0: True)
    monkeypatch.setattr(FortiOSSsh, "restart_grace", 0.3)
    rig.fg.restart_mode = "prompt_only"
    r = rig.driver.apply_configuration(BACKUP, ApplyMode.REPLACE)
    assert r.status is ResultStatus.FAILED and "did not restart within 0 s" in r.message
    assert "File check OK." in r.diagnostics["device_output"]


def test_backup_from_another_model_is_refused(rig):
    rig.fg.model = "FortiGate-60F"
    r = rig.driver.apply_configuration(BACKUP, ApplyMode.REPLACE)
    assert r.status is ResultStatus.FAILED and "FG101F" in r.message and "60F" in r.message
    assert rig.fg.fetched == []


def test_files_cannot_be_applied_the_wrong_way(rig):
    before = list(rig.fg.applied)
    merge = rig.driver.apply_configuration(BACKUP, ApplyMode.MERGE)
    assert "never line by line" in merge.message
    replace = rig.driver.apply_configuration(SCRIPT, ApplyMode.REPLACE)
    assert "full FortiOS backup" in replace.message
    assert rig.fg.applied == before and rig.fg.fetched == []


def test_restore_without_file_server_touches_nothing(rig):
    rig.driver.file_server = None
    r = rig.driver.apply_configuration(BACKUP, ApplyMode.REPLACE)
    assert r.status is ResultStatus.FAILED and "file server" in r.message
    assert not any(c.startswith("execute") for c in rig.fg.commands)


# -- CLI script -----------------------------------------------------------------------

def multi_vdom(rig):
    rig.fg.vdoms = True


def test_script_runs_statement_by_statement_through_a_hostname_change(rig):
    multi_vdom(rig)
    rig.fg.info_replies["edit root"] = "current vf=root:0"  # synthetic informational reply
    r = rig.driver.apply_configuration(SCRIPT, ApplyMode.MERGE)
    assert r.ok, (r.message, r.diagnostics)
    assert r.data["statements"] == 35 and rig.fg.hostname == "lab-fw-site"
    warnings = r.data["warnings"]
    assert any("'end'" in w and "expected" in w for w in warnings)  # the leading bare end
    assert any("current vf=root:0" in w for w in warnings)  # reported, did not stop the run
    assert "set psksecret example-only-not-a-secret" in rig.fg.applied  # placeholder as written
    v = rig.driver.verify_configuration(SCRIPT, ApplyMode.MERGE)
    assert v.ok and "hostname lab-fw-site" in v.message and "appear in 'show'" in v.message


def test_script_stops_at_the_first_rejected_line(rig):
    multi_vdom(rig)
    rig.fg.bad_statements.add('set ip 203.0.113.1 255.255.255.0')
    r = rig.driver.apply_configuration(SCRIPT, ApplyMode.MERGE)
    assert r.status is ResultStatus.FAILED
    assert "rejected line 20" in r.message and "Return code -61" in r.message
    assert "the rest were not sent" in r.message
    assert not any("example-tunnel" in a for a in rig.fg.applied)


def test_script_stops_at_a_question(rig):
    multi_vdom(rig)
    rig.fg.question_on["set admin-scp enable"] = "This change needs a restart. Continue? (y/n)"
    r = rig.driver.apply_configuration(SCRIPT, ApplyMode.MERGE)
    assert r.status is ResultStatus.FAILED and "No prompt after line 9" in r.message
    assert rig.fg.keys == []


def test_secret_is_sent_but_never_shown(rig):
    multi_vdom(rig)
    rig.fg.bad_statements.add(f'set psksecret "{PSK}"')  # make it fail on the secret line
    text = rig.driver.prepare_for_device(SCRIPT, {SLOT: PSK})
    assert f'set psksecret "{PSK}"' in text and SCRIPT.count("example-only-not-a-secret") == 1
    r = rig.driver.apply_configuration(text, ApplyMode.MERGE)
    assert r.status is ResultStatus.FAILED and "rejected line 29" in r.message
    everything = r.message + repr(r.diagnostics) + repr(r.data)
    assert PSK not in everything
    assert "set psksecret ***REDACTED***" in everything  # shown masked, never as typed


def test_secret_values_that_cannot_be_typed_safely_are_refused(rig):
    for bad, why in (('ab"c', "cannot type safely"), ("what?", "CLI help"), ("", "empty")):
        with pytest.raises(ValueError, match=why):
            rig.driver.prepare_for_device(SCRIPT, {SLOT: bad})
    with pytest.raises(ValueError, match="no secret setting"):
        rig.driver.prepare_for_device(SCRIPT, {"vdom > root > nope": PSK})
    with pytest.raises(ValueError, match="only be inserted into a CLI script"):
        rig.driver.prepare_for_device(BACKUP, {SLOT: PSK})


def test_secret_settings_are_not_expected_in_the_read_back(rig):
    assert not any("psksecret" in ln for ln in rig.driver.expected_lines(SCRIPT))


# -- revisions ------------------------------------------------------------------------

def test_revision_is_saved_in_global_context_and_confirmed(rig):
    multi_vdom(rig)
    r = rig.driver.create_checkpoint("base-example")
    assert r.ok and rig.fg.revisions == ["base-example"]
    i = rig.fg.commands.index('execute backup config flash "base-example"')
    assert rig.fg.commands[i - 1] == "config global"
    assert rig.fg.commands[i + 1:i + 3] == ["execute revision list config", "end"]


def test_revision_not_confirmed_is_reported(rig):
    rig.fg.revisions_supported = False
    r = rig.driver.create_checkpoint("site-x")
    assert r.status is ResultStatus.FAILED and "refused" in r.message


def test_login_without_a_prompt_says_what_the_unit_showed(monkeypatch):
    """Bench 2026-11-23: Test connection on a new FortiGate ended with Netmiko's 'Pattern not
    detected: to accept|[#$]'. UNDM now shows what the unit printed instead of a prompt.
    The text below is SYNTHETIC, not a capture of a FortiGate."""
    from netmiko.exceptions import ReadTimeout

    def factory(**kwargs):
        kwargs["session_log"].write(
            b"[synthetic] Please change the admin password.\nNew Password: ")
        raise ReadTimeout("Pattern not detected: 'to accept|[#$]' in output.")
    monkeypatch.setattr(SshCliDriver, "connection_factory", staticmethod(factory))
    d = FortiOSSsh(DeviceTarget("d1", "192.0.2.99", None), Credentials("admin", "x"))
    r = d.connect()
    assert r.status is ResultStatus.FAILED
    assert r.message.startswith("Logged in, but the device did not show its command prompt")
    assert "New Password:" in r.message
    assert "A FortiGate asks for a new admin password at the first login" in r.message
    assert r.diagnostics["login_accepted"] is True


# -- base restore through the API: the unit demands a new password afterwards ----------
APPROVED, BASE_PW = "Example-Only-Approved-1", "Example-Only-Base-1"


@pytest.fixture
def api(monkeypatch, tmp_path):
    import keyring
    from api_helpers import make_client
    from memory_keyring import MemoryKeyring

    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    tune(monkeypatch)
    client, _ = make_client(data_dir=str(tmp_path), tftp_host="127.0.0.1", tftp_port=0,
                            firmware_reboot_wait_seconds=0, firmware_reboot_wait_attempts=4,
                            enable_real_device_writes=True)
    with client:
        hub = client.app.state.transfer_hub
        fg = FakeFortiGate(tftp_port=lambda: hub.port, password=APPROVED)
        monkeypatch.setattr(SshCliDriver, "connection_factory",
                            staticmethod(factory_for(Scenario(device=fg))))
        pid = client.post("/api/projects", json={"name": "FortiGate"}).json()["id"]
        refs = {}
        for name, pw in (("approved", APPROVED), ("base", BASE_PW)):
            refs[name] = client.post(f"/api/projects/{pid}/credential-refs",
                                     json={"name": name}).json()["id"]
            client.put(f"/api/credential-refs/{refs[name]}/secret",
                       json={"username": "admin", "password": pw})
        did = client.post(f"/api/projects/{pid}/devices", json={
            "name": "lab-fw", "manufacturer": "Fortinet", "category": "firewall",
            "model": "FortiGate-101F", "os_family": "FortiOS",
            "driver_id": "ssh.fortinet.fortios", "environment": "lab",
            "management_address": "127.0.0.1", "credential_ref_id": refs["approved"]}).json()
        assert "id" in did, did
        yield client, pid, did["id"], fg, refs
    keyring.set_keyring(previous)


def _restore_base(client, pid, did, after=None):
    v = client.post(f"/api/devices/{did}/configs/import",
                    json={"filename": "base.conf", "text": BACKUP}).json()
    assert v["inspection"]["apply_mode"] == "replace", v
    body = {"device_ids": [did], "apply_mode": "replace", "config_versions": {did: v["id"]}}
    if after:
        body["credentials_after"] = {did: after}
    dep = client.post(f"/api/projects/{pid}/deployments", json=body).json()
    assert dep["state"] == "awaiting_approval", dep
    client.post(f"/api/deployments/{dep['id']}/approve")
    out = client.post(f"/api/deployments/{dep['id']}/execute").json()
    return out, " | ".join(e["message"] for e in out["events"])


def test_api_password_set_by_hand_after_the_base_restore_is_waited_for(api):
    """Bench 2026-11-24 (product owner): the base file sets another admin password; logging
    in with it, the unit demands a new one (password policy), and the team sets the approved
    password again. UNDM logs in with the base password (accepted, no prompt), says what to
    do, and continues with the approved login once a person has set it (D-065)."""
    client, pid, did, fg, refs = api
    fg.restore_sets_password, fg.restore_forces_password_change = BASE_PW, True
    fg.hand_change_after, fg.hand_password = 2, APPROVED
    out, events = _restore_base(client, pid, did, after=refs["base"])
    assert out["state"] == "succeeded", events
    assert "If it asks for a new password, set the device's approved password" in events
    assert "refused now; trying the device's previous login" in events
    assert "logged in with the device's previous login" in events
    device = client.get(f"/api/devices/{did}").json()
    assert device["credential_ref_id"] == refs["approved"]  # not the base file's login
    assert fg.hostname == "lab-fw-base" and fg.vdoms
    assert APPROVED not in repr(out) and BASE_PW not in repr(out)


def test_api_nobody_sets_the_password_the_run_says_why(api):
    client, pid, did, fg, refs = api
    fg.restore_sets_password, fg.restore_forces_password_change = BASE_PW, True
    out, events = _restore_base(client, pid, did, after=refs["base"])
    assert out["state"] == "recovery_required", events
    assert "no login reached its prompt" in out["targets"][0]["message"]
    assert client.get(f"/api/devices/{did}").json()["credential_ref_id"] == refs["approved"]


def test_api_demanded_password_change_is_answered_with_the_approved_login(api):
    """Bench 2026-11-24 (SSH CLI capture by the product owner): after the base restore the
    unit asks "You are forced to change your password. Old password:", shows its policy,
    then "New Password:" and "Confirm Password:". With the base file's password as login
    after loading, UNDM answers with that (old) and the device's approved login (new),
    logs in again to prove it, and the device keeps its approved login (D-066)."""
    client, pid, did, fg, refs = api
    fg.restore_sets_password, fg.restore_forces_password_change = BASE_PW, True
    fg.change_dialogue = True
    out, events = _restore_base(client, pid, did, after=refs["base"])
    assert out["state"] == "succeeded", events
    assert "UNDM answered its questions and set the password" in events
    assert "logged in again with the device's login" in events
    assert fg.password == APPROVED and not fg.must_change_password
    assert fg.keys[-3:] == [BASE_PW, APPROVED, APPROVED]  # old, new, confirm: once each
    assert client.get(f"/api/devices/{did}").json()["credential_ref_id"] == refs["approved"]
    audit = client.get("/api/audit?limit=50").json()
    assert any(a["action"] == "device.password_set" for a in audit)
    assert APPROVED not in repr(out) + repr(audit) and BASE_PW not in repr(out) + repr(audit)


def test_a_refused_new_password_is_not_offered_twice(rig):
    """The unit asks again when it does not accept the new password (synthetic reply):
    UNDM stops instead of guessing, and never shows a password."""
    rig.fg.must_change_password = rig.fg.change_dialogue = True
    rig.driver.offer_password_change(Credentials("admin", "short"))
    r = rig.driver.connect()
    assert r.status is ResultStatus.FAILED and r.diagnostics["login_accepted"] is True
    assert "asked again for its new password" in r.message
    assert "short" not in r.message and "Example-Only-1" not in r.message
    assert rig.fg.password == "Example-Only-1" and rig.fg.keys.count("short") == 2


def test_an_unknown_question_at_login_is_not_answered(rig, monkeypatch):
    monkeypatch.setattr(FortiOSSsh, "login_dialogue_timeout", 0.2)
    rig.fg.must_change_password = rig.fg.change_dialogue = True
    rig.fg.password = "Example-Only-1"
    # A different first question than the one seen on the bench.
    monkeypatch.setattr(type(rig.fg), "accept_connection", _asks_something_else)
    rig.driver.offer_password_change(Credentials("admin", "Example-Only-Approved-1"))
    r = rig.driver.connect()
    assert r.status is ResultStatus.FAILED and "does not answer at login" in r.message
    assert rig.fg.keys == []


def _asks_something_else(self, password=None):
    self._closed, self._closing, self._pending = False, False, "unknown"
    self.awaiting_login_answers = True
    self._out = "\r\n[synthetic] Please accept the disclaimer (yes/no): "


def test_ordinary_login_with_the_offer_changes_nothing(rig):
    rig.driver.offer_password_change(Credentials("admin", "Example-Only-Approved-1"))
    r = rig.driver.connect()
    assert r.ok and not r.data and rig.fg.password == "Example-Only-1" and rig.fg.keys == []


def test_a_missed_prompt_after_the_change_still_switches_to_the_new_login(rig, monkeypatch):
    """Bench 2026-11-24 (v39): the unit accepted UNDM's answers, then Netmiko missed the
    prompt UNDM had already read. If that happens, the driver still knows the device now has
    the new password."""
    monkeypatch.setattr(SshCliDriver, "_hand_back", staticmethod(lambda conn, text: None))
    rig.fg.must_change_password = rig.fg.change_dialogue = True
    rig.driver.offer_password_change(Credentials("admin", "Example-Only-Approved-1"))
    r = rig.driver.connect()
    assert not r.ok and r.diagnostics["password_changed"] is True, r.message
    assert "after UNDM set the new password it demanded" in r.message
    assert "Example-Only-Approved-1" not in r.message
    assert rig.fg.password == "Example-Only-Approved-1"
    assert rig.driver.connect().ok  # the next login uses the new password
