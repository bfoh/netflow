"""ArubaOS-Switch firmware steps against a fake switch that really downloads over TFTP.

The switch's wording is synthetic (see fake_aos_switch.py). These tests prove the
driver's decisions - what it answers, what it refuses to answer, and what evidence
it requires before reporting success - not compatibility with hardware.
"""

import hashlib
from dataclasses import dataclass

import pytest
from fake_aos_switch import FakeArubaSwitch, fake_image
from fake_netmiko import Scenario, factory_for

from undm.drivers.base import Credentials, DeviceTarget, FirmwareImageRef, ResultStatus
from undm.drivers.ssh.base import SshCliDriver
from undm.drivers.ssh.platforms import ArubaOSSwitchSsh
from undm.transfer.hub import TransferHub

TARGET = "WC.16.10.0025"


@dataclass
class Rig:
    driver: ArubaOSSwitchSsh
    switch: FakeArubaSwitch
    image: FirmwareImageRef
    scenario: Scenario


@pytest.fixture
def rig(monkeypatch, tmp_path):
    hub = TransferHub("127.0.0.1", 0)
    switch = FakeArubaSwitch(tftp_port=lambda: hub.port)
    sc = Scenario(prompt="lab-2930f#", device=switch)
    monkeypatch.setattr(SshCliDriver, "connection_factory", staticmethod(factory_for(sc)))
    monkeypatch.setattr(SshCliDriver, "poll_interval", 0.01)
    monkeypatch.setattr(ArubaOSSwitchSsh, "question_timeout", 0.3)
    monkeypatch.setattr(ArubaOSSwitchSsh, "reboot_quiet_timeout", 0.3)
    path = tmp_path / "WC_16_10_0025.swi"
    data = fake_image(TARGET)
    path.write_bytes(data)
    image = FirmwareImageRef(TARGET, path.name, hashlib.sha256(data).hexdigest(), len(data),
                             str(path))
    with hub.session() as files:
        driver = ArubaOSSwitchSsh(DeviceTarget("d1", "127.0.0.1", None),
                                  Credentials("manager", ""))
        driver.file_server = files
        assert driver.connect().ok
        yield Rig(driver, switch, image, sc)
    assert not hub.running  # the server stops with the job


def test_firmware_information_reads_running_and_flash(rig):
    info = rig.driver.get_firmware_information()
    assert info.ok
    assert info.data["running"] == "WC.16.10.0012"
    assert info.data["primary"] == "WC.16.10.0012"
    assert info.data["secondary"] == "WC.16.09.0004"
    assert info.data["default_boot"] == "Primary"


def test_stage_transfers_image_and_checks_flash(rig):
    r = rig.driver.stage_firmware(rig.image)
    assert r.ok, (r.message, r.data)
    assert r.data == {"primary": TARGET, "bytes": rig.image.size_bytes}
    assert rig.switch.primary == TARGET and rig.switch.running == "WC.16.10.0012"
    assert rig.switch.commands.count("copy tftp flash 127.0.0.1 WC_16_10_0025.swi primary") == 1
    assert rig.switch.keys == ["y"]


def test_stage_without_file_server_fails_before_touching_the_switch(rig):
    rig.driver.file_server = None
    r = rig.driver.stage_firmware(rig.image)
    assert r.status is ResultStatus.FAILED and "file server" in r.message
    assert not any(c.startswith("copy") for c in rig.switch.commands)


def test_unknown_question_is_not_answered(rig):
    rig.switch.copy_question = "Erase ALL images and reformat flash? Type CONFIRM: "
    r = rig.driver.stage_firmware(rig.image)
    assert r.status is ResultStatus.FAILED
    assert "did not request the image" in r.message and "no output for" in r.message
    assert "Type CONFIRM" in r.diagnostics["device_output"]  # the technician sees the question
    assert rig.switch.keys == []  # nothing was answered
    assert rig.switch.primary == "WC.16.10.0012"


def test_interrupted_transfer_is_reported_and_not_treated_as_staged(rig):
    rig.switch.truncate_download = True
    r = rig.driver.stage_firmware(rig.image)
    assert r.status is ResultStatus.FAILED
    assert "Transfer incomplete" in r.message and "not restarted" in r.message


def test_flash_must_show_the_expected_version(rig):
    rig.switch.skip_flash_write = True  # file fetched, but flash still holds the old image
    r = rig.driver.stage_firmware(rig.image)
    assert r.status is ResultStatus.FAILED
    assert "primary = WC.16.10.0012 instead of WC.16.10.0025" in r.message
    assert "Primary Image" in r.diagnostics["show_flash"]["show flash"]


def test_only_this_switch_may_fetch_the_image(rig, tmp_path):
    import tftpy
    files = rig.driver.file_server
    files.offer(tmp_path / "WC_16_10_0025.swi", "other.swi", "192.0.2.77")
    with pytest.raises(tftpy.TftpException):
        tftpy.TftpClient("127.0.0.1", files.port, {}).download(
            "other.swi", str(tmp_path / "stolen.bin"), timeout=1)
    assert not (tmp_path / "stolen.bin").exists() or \
        (tmp_path / "stolen.bin").stat().st_size == 0


def test_reboot_confirms_and_treats_closed_session_as_started(rig):
    assert rig.driver.stage_firmware(rig.image).ok
    r = rig.driver.reboot()
    assert r.ok and "closed the session" in r.message
    assert rig.switch.restarts == 1 and rig.switch.running == TARGET
    assert rig.driver._conn is None


def test_reboot_does_not_save_unsaved_changes(rig):
    rig.switch.unsaved_changes = True
    assert rig.driver.reboot().ok
    assert rig.switch.keys == ["n", "y"] and rig.switch.saved_on_reboot is False


def test_reboot_with_silent_session_is_started_only_after_confirmation(rig):
    rig.switch.reboot_mode = "silent"
    r = rig.driver.reboot()
    assert r.ok and "no further output" in r.message and rig.switch.restarts == 1


def test_reboot_refused_is_a_failure(rig):
    rig.switch.reboot_mode = "refuse"
    r = rig.driver.reboot()
    assert r.status is ResultStatus.FAILED and "returned to its prompt" in r.message
    assert rig.switch.restarts == 0


def test_reboot_unknown_question_confirms_nothing(rig, monkeypatch):
    def odd(text):
        rig.switch._out += "Device is in a stack. Reboot ALL members <yes/no>: "
        rig.switch._pending = "boot"
    monkeypatch.setattr(rig.switch, "_ask", lambda handler, question: odd(question))
    r = rig.driver.reboot()
    assert r.status is ResultStatus.FAILED and "nothing was confirmed" in r.message
    assert rig.switch.keys == [] and rig.switch.restarts == 0
