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


def test_a_unit_that_goes_silent_is_not_reported_as_restarting(rig, tmp_path):
    rig.fg.restart_mode = "silent"
    r = rig.driver.stage_firmware(image(tmp_path))
    assert r.status is ResultStatus.FAILED and "neither restarted" in r.message


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
