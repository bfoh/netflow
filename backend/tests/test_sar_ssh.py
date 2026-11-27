"""The modem in the network, read over SSH (D-127). A fake Netmiko channel replays synthetic
SR OS text (fictional name, RFC 5737 address); no device is contacted."""

import pytest

from undm.domain.operations import DeviceOperation
from undm.drivers.base import ApplyMode, Capability, Credentials, DeviceTarget, ResultStatus
from undm.drivers.nokia.sar_console import NokiaSarConsole
from undm.drivers.nokia.sar_ssh import NokiaSarSsh
from undm.drivers.registry import default_registry

PROMPT = "\r\nA:abc-modem# "
SYSINFO = "\r\n".join([
    "", "=" * 40, "System Information", "=" * 40,
    "System Name            : abc-modem", "System Type            : 7705 SAR-Hmc",
    "System Version         : B-20.5.R1", "Last Saved Config      : cf3:\\config.cfg",
    "Changes Since Last Save: No", "=" * 40])
CONFIG = ("# TiMOS-B-20.5.R1\r\nexit all\r\nconfigure\r\n    system\r\n"
          "        name \"abc-modem\"\r\n    exit\r\nexit all\r\n")


class FakeChannel:
    """What Netmiko's generic (terminal server) session gives: a channel, nothing sent."""

    def __init__(self, *, prompt_at_login=True, answers=None):
        self.sent: list[str] = []
        self.out = ("Welcome\r\n" + PROMPT) if prompt_at_login else "Welcome\r\n"
        self.answers = answers or {
            "environment no more": "", "show system information": SYSINFO,
            "admin display-config": CONFIG}
        self.closed = False

    def write_channel(self, data):
        if not data.strip():  # Enter alone: the prompt again
            self.sent.append("")
            self.out += PROMPT
            return
        for line in data.replace("\r", "\n").split("\n"):
            if not line:
                continue
            self.sent.append(line)
            if line == "logout":
                continue
            self.out += line + "\r\n" + self.answers.get(line, "MINOR: CLI Command not allowed") \
                + PROMPT

    def read_channel(self):
        text, self.out = self.out, ""
        return text

    def disconnect(self):
        self.closed = True


@pytest.fixture
def channel(monkeypatch):
    holder = {}

    def factory(**kwargs):
        holder["kwargs"] = kwargs
        holder["conn"] = holder.get("make", FakeChannel)()
        return holder["conn"]

    monkeypatch.setattr(NokiaSarSsh, "connection_factory", staticmethod(factory))
    monkeypatch.setattr(NokiaSarSsh, "wake_timeout", 0.5)
    monkeypatch.setattr(NokiaSarSsh, "settle_time", 0.0)
    return holder


def driver():
    return NokiaSarSsh(DeviceTarget("m1", "198.51.100.31"),
                       Credentials("admin", "Example-Only-9"))


def test_it_reads_facts_with_the_documented_commands_only(channel):
    d = driver()
    assert d.connect().ok
    assert channel["kwargs"]["device_type"] == "generic"  # Netmiko sends nothing itself
    facts = d.get_device_facts()
    assert facts.ok and facts.data.hostname == "abc-modem"
    assert facts.data.model == "7705 SAR-Hmc" and facts.data.os_version == "B-20.5.R1"
    backup = d.backup_configuration()
    assert backup.ok and "configure" in backup.data.text
    d.disconnect()
    conn = channel["conn"]
    assert conn.sent == ["environment no more", "show system information",
                         "admin display-config", "logout"]
    assert conn.closed
    assert "Example-Only-9" not in repr(conn.sent)


def test_without_a_prompt_at_login_it_presses_enter_once(channel):
    channel["make"] = lambda: FakeChannel(prompt_at_login=False)
    d = driver()
    assert d.connect().ok
    assert channel["conn"].sent[:2] == ["", "environment no more"]


def test_nothing_is_changed_over_ssh(channel):
    d = driver()
    assert d.connect().ok
    assert d.apply_configuration(CONFIG, ApplyMode.MERGE).status is ResultStatus.UNSUPPORTED
    assert d.save_configuration().status is ResultStatus.UNSUPPORTED
    assert not d.check_before_apply(CONFIG, ApplyMode.MERGE).ok
    with pytest.raises(ValueError):
        d.prepare_for_device(CONFIG, {})
    assert d.missing_capabilities(DeviceOperation.APPLY_CONFIGURATION)
    assert channel["conn"].sent == ["environment no more"]


def test_a_refused_login_says_so(monkeypatch):
    from netmiko.exceptions import NetmikoAuthenticationException

    def refuse(**kwargs):
        raise NetmikoAuthenticationException("Authentication failed.")

    monkeypatch.setattr(NokiaSarSsh, "connection_factory", staticmethod(refuse))
    r = driver().connect()
    assert not r.ok and r.diagnostics.get("login_refused") and "refused the login" in r.message


def test_network_drivers_match_their_bench_driver():
    """Every declared network driver exists, is for the same platform, is just as
    simulated or real, reaches the device (SSH or a person's portal) and cannot change it."""
    registry = default_registry()
    declared = [(d.driver_id, registry.get(d.driver_id).network_driver_id)
                for d in registry.list() if registry.get(d.driver_id).network_driver_id]
    assert ("console.nokia.sar", "ssh.nokia.sar") in declared
    for bench, network in declared:
        b, n = registry.get(bench).info, registry.get(str(network)).info
        assert n.platform == b.platform and n.simulated == b.simulated
        assert Capability.SSH in n.capabilities or Capability.GUIDED_STAGING in n.capabilities
        assert Capability.CONFIGURATION_APPLY not in n.capabilities
        assert registry.get(str(network)).network_driver_id is None


def test_in_the_network_the_modem_gets_its_ssh_driver(tmp_path):
    import keyring
    from api_helpers import make_client
    from memory_keyring import MemoryKeyring

    from undm.db.models import Device
    from undm.services import devices as devsvc

    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    try:
        c, factory = make_client(data_dir=str(tmp_path))
        with c:
            pid = c.post("/api/projects", json={"name": "Practice B007"}).json()["id"]
            ref = c.post(f"/api/projects/{pid}/credential-refs", json={"name": "modem"}).json()
            c.put(f"/api/credential-refs/{ref['id']}/secret",
                  json={"username": "admin", "password": "Example-Only-9"})
            fw = c.post(f"/api/projects/{pid}/devices", json={
                "name": "abc-fw", "manufacturer": "Fortinet", "category": "firewall",
                "driver_id": "mock.fortinet.fortios", "management_address": "192.168.1.99"
            }).json()["id"]
            modem = c.post(f"/api/projects/{pid}/devices", json={
                "name": "abc-modem", "manufacturer": "Nokia", "category": "router",
                "driver_id": "console.nokia.sar", "environment": "lab", "console_port": "COM7",
                "credential_ref_id": ref["id"]}).json()["id"]
            with factory() as s:
                bench = devsvc.build_driver(s.get(Device, modem), default_registry())
            assert isinstance(bench, NokiaSarConsole) and not isinstance(bench, NokiaSarSsh)
            c.put(f"/api/devices/{fw}/network-address", json={"address": "198.51.100.1"})
            c.put(f"/api/devices/{modem}/network-address", json={"address": "198.51.100.31"})
            assert c.put(f"/api/projects/{pid}/reached-via",
                         json={"via": "network"}).status_code == 200
            out = c.get(f"/api/devices/{modem}").json()
            assert out["connection"]["driver_id"] == "ssh.nokia.sar"
            assert "supports_ssh" in out["connection"]["capabilities"]
            with factory() as s:
                net = devsvc.build_driver(s.get(Device, modem), default_registry())
            assert isinstance(net, NokiaSarSsh)
            assert net.target.management_address == "198.51.100.31"
    finally:
        keyring.set_keyring(previous)
