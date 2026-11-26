import re
from ipaddress import IPv4Interface

import pytest

from undm.drivers.base import Credentials
from undm.provisioning.aos_switch import (
    ArubaOSSwitchConsole,
    BootstrapParams,
    BootstrapStatus,
    bootstrap,
    is_configured,
    parse_vlans,
    site_config_findings,
)
from undm.provisioning.console import ConsoleSession, clean
from undm.provisioning.simulated import SimulatedArubaConsole

PARAMS = BootstrapParams(222, "OOBM_VLAN", "2", IPv4Interface("192.168.1.1/24"))


def run(sim, params=PARAMS, creds=None, **kw):
    session = ConsoleSession(sim, read_timeout=0.3, settle_time=0)
    console = ArubaOSSwitchConsole(session, creds, wake_delay=0, login_timeout=0.3)
    return bootstrap(console, params, **kw)


def test_commands_match_the_manual_procedure():
    assert PARAMS.commands() == [
        "configure", "vlan 222", 'name "OOBM_VLAN"', "untagged 2",
        "ip address 192.168.1.1 255.255.255.0", "exit", "write memory"]
    port3 = BootstrapParams(222, "OOBM_VLAN", "3", IPv4Interface("192.168.1.1/24"))
    assert "untagged 3" in port3.commands()


@pytest.mark.parametrize("kw", [
    {"vlan_id": 1}, {"vlan_id": 5000}, {"vlan_name": 'x" ; reload'}, {"untagged_port": "2;reload"},
    {"address": IPv4Interface("192.168.1.0/24")}, {"address": IPv4Interface("192.168.1.1/32")},
])
def test_parameters_are_validated(kw):
    base = {"vlan_id": 222, "vlan_name": "OOBM_VLAN", "untagged_port": "2",
            "address": IPv4Interface("192.168.1.1/24")}
    with pytest.raises(ValueError):
        BootstrapParams(**{**base, **kw})


def test_factory_default_switch_is_bootstrapped_and_saved():
    sim = SimulatedArubaConsole()
    r = run(sim)
    assert r.status is BootstrapStatus.BOOTSTRAPPED and r.verified and r.saved, r.message
    assert sim.vlans[222] == {"name": "OOBM_VLAN", "untagged": {"2"},
                              "ip": "192.168.1.1 255.255.255.0"}
    assert "2" not in sim.vlans[1]["untagged"]
    assert sim.saved_config is not None and "vlan 222" in sim.saved_config
    assert r.commands_sent == PARAMS.commands()
    assert "Press any key to continue" in r.transcript and "<<< vlan 222" in r.transcript


def test_second_run_changes_nothing():
    sim = SimulatedArubaConsole()
    run(sim)
    before = list(sim.commands_received)
    sim2_state = sim.render()
    sim._state, sim._enters = "asleep", 0  # a new console session on the same switch
    r = run(sim)
    assert r.status is BootstrapStatus.ALREADY_CONFIGURED and r.commands_sent == []
    assert sim.render() == sim2_state
    new = sim.commands_received[len(before):]
    assert not any(c.startswith(("configure", "vlan", "untagged", "write")) for c in new)


def test_switch_with_site_configuration_is_refused_unless_allowed():
    sim = SimulatedArubaConsole(extra_config=[
        "ip authorized-managers 192.0.2.10 255.255.255.255 access manager",
        "ip route 0.0.0.0 0.0.0.0 192.0.2.1"])
    r = run(sim)
    assert r.status is BootstrapStatus.REFUSED and r.commands_sent == []
    assert any("authorized-managers" in f for f in r.findings)
    assert 222 not in sim.vlans and sim.saved_config is None
    sim._state, sim._enters = "asleep", 0
    assert run(sim, allow_configured=True).status is BootstrapStatus.BOOTSTRAPPED


def test_switch_with_password_is_not_factory_default():
    sim = SimulatedArubaConsole(username="manager", password="Example-Only-1")
    r = run(sim)
    assert r.status is BootstrapStatus.FAILED and "not in factory-default state" in r.message
    assert 222 not in sim.vlans
    sim = SimulatedArubaConsole(username="manager", password="Example-Only-1")
    r = run(sim, creds=Credentials("manager", "Example-Only-1"))
    assert r.status is BootstrapStatus.BOOTSTRAPPED
    assert "Example-Only-1" not in r.transcript


def test_operator_level_console_is_elevated():
    r = run(SimulatedArubaConsole(operator_level=True))
    assert r.status is BootstrapStatus.BOOTSTRAPPED and "<<< enable" in r.transcript


def test_rejected_command_stops_without_saving():
    sim = SimulatedArubaConsole(fail_on={"untagged 2"})
    r = run(sim)
    assert r.status is BootstrapStatus.FAILED and "rejected 'untagged 2'" in r.message
    assert sim.saved_config is None and not r.saved
    assert r.commands_sent == ["configure", "vlan 222", 'name "OOBM_VLAN"', "untagged 2"]


def test_address_in_the_network_of_a_dhcp_lease_is_explained():
    """Bench 2026-11-25: VLAN 1 held a DHCP address in the bench network, so the switch
    refused the OOBM address. UNDM stops at once, quotes the switch, and says what to do."""
    sim = SimulatedArubaConsole(dhcp_lease="192.168.1.120/24")
    r = run(sim)
    assert r.status is BootstrapStatus.FAILED and not r.saved and sim.saved_config is None
    assert "rejected 'ip address 192.168.1.1 255.255.255.0'" in r.message
    assert "overlapping network" in r.message  # the switch's own words
    # The switch's own 'show ip' names the holder (read-only), not a guess.
    assert '"DEFAULT_VLAN | DHCP/Bootp 192.168.1.120 255.255.255.0"' in r.message
    assert "DHCP server" in r.message and "unplug" in r.message and "plug port 2" in r.message
    assert "write memory" not in r.commands_sent and "<<< exit" not in r.transcript
    assert "<<< show ip" in r.transcript


def test_dhcp_lease_in_another_network_does_not_matter():
    r = run(SimulatedArubaConsole(dhcp_lease="10.0.0.5/24"))
    assert r.status is BootstrapStatus.BOOTSTRAPPED


def test_port_the_switch_does_not_have_is_refused_before_any_change():
    """Bench 2026-11-25: port 83 typed for a 52-port switch. UNDM checks the port against the
    switch's own configuration (VLAN 1 lists 1-52) and sends nothing."""
    sim = SimulatedArubaConsole(first_login_setup=True)
    r = run(sim, BootstrapParams(222, "OOBM_VLAN", "83", IPv4Interface("192.168.1.1/24")),
            creds=Credentials("manager", "x-approved-1"))
    assert r.status is BootstrapStatus.REFUSED and not r.saved
    assert "no port 83" in r.message and "ports 1-52" in r.message
    assert "Nothing was changed. The switch was new" in r.message and ".." not in r.message
    assert "configure" not in sim.commands_received and sim.saved_config is None


def test_quote_of_a_rejected_command_has_no_prompt_and_no_double_period():
    sim = SimulatedArubaConsole(first_login_setup=True, fail_on={"untagged 2"})
    r = run(sim, creds=Credentials("manager", "x-approved-1"))
    assert r.status is BootstrapStatus.FAILED
    assert '"Invalid input: untagged"' in r.message
    assert "(vlan-222)#" not in r.message and ".." not in r.message


def test_silently_ignored_command_is_caught_by_read_back():
    sim = SimulatedArubaConsole(silently_ignore={"ip address 192.168.1.1 255.255.255.0"})
    r = run(sim)
    assert r.status is BootstrapStatus.FAILED and "read back" in r.message
    assert sim.saved_config is None


def test_dead_console_times_out_cleanly():
    r = run(SimulatedArubaConsole(silent=True))
    assert r.status is BootstrapStatus.FAILED and "No expected prompt" in r.message


def test_parsing_helpers():
    cfg = ('hostname "x"\nvlan 1\n   name "DEFAULT_VLAN"\n   untagged 1,3-52\n'
           "   ip address dhcp-bootp\n   exit\nvlan 222\n   name \"OOBM_VLAN\"\n   untagged 2\n"
           "   ip address 192.168.1.1 255.255.255.0\n   exit\n")
    assert set(parse_vlans(cfg)) == {1, 222}
    assert is_configured(cfg, PARAMS)
    assert not is_configured(cfg, BootstrapParams(222, "OOBM_VLAN", "3",
                                                  IPv4Interface("192.168.1.1/24")))
    assert site_config_findings(cfg, PARAMS) == []
    assert clean("\x1b[24;1H\x1b[?25hsw# \r\n") == "sw# \n"


# -- new switches: mandatory manager credentials at first login --------------------------
# Seen on a real new 2930F (product owner, 2026-11-19): "Configure the manager credentials :",
# "Username:", "Password:", "Re-enter the new password:".

APPROVED = Credentials("manager", "Example-Only-Approved-1")


def test_new_switch_gets_the_attached_login_then_is_bootstrapped():
    sim = SimulatedArubaConsole(first_login_setup=True)
    r = run(sim, creds=APPROVED)
    assert r.status is BootstrapStatus.BOOTSTRAPPED, (r.message, r.transcript)
    assert r.credentials_set and "manager credentials were set" in r.message
    assert (sim.username, sim.password) == ("manager", "Example-Only-Approved-1")
    assert "Example-Only-Approved-1" not in r.transcript
    assert r.transcript.count("(new password: not shown)") == 2


def test_new_switch_without_an_attached_login_is_left_untouched():
    for creds in (None, Credentials("manager", "")):  # none, or the factory login
        sim = SimulatedArubaConsole(first_login_setup=True)
        r = run(sim, creds=creds)
        assert r.status is BootstrapStatus.FAILED
        assert "requires its manager credentials" in r.message and "Nothing was sent" in r.message
        assert sim.username is None and sim.commands_received == []


def test_rejected_password_stops_without_retrying():
    sim = SimulatedArubaConsole(first_login_setup=True, min_password_length=40)
    r = run(sim, creds=APPROVED)
    assert r.status is BootstrapStatus.FAILED and "asked for the username again" in r.message
    assert sim.username is None and sim.commands_received == []
    assert "Example-Only-Approved-1" not in r.transcript


def test_old_style_factory_default_switch_does_not_need_a_login():
    r = run(SimulatedArubaConsole(), creds=None)
    assert r.status is BootstrapStatus.BOOTSTRAPPED and not r.credentials_set


def test_unexpected_password_question_is_not_answered():
    sim = SimulatedArubaConsole(first_login_setup=True,
                                setup_password_prompt="Enter the old password: ")
    r = run(sim, creds=APPROVED)
    assert r.status is BootstrapStatus.FAILED and "did not expect" in r.message
    assert "(new password: not shown)" not in r.transcript and sim.username is None


def test_questions_in_another_order_are_not_answered():
    sim = SimulatedArubaConsole(first_login_setup=True,
                                setup_password_prompt="Re-enter the new password: ")
    r = run(sim, creds=APPROVED)
    assert r.status is BootstrapStatus.FAILED and "did not expect" in r.message
    assert sim.username is None


def test_console_left_at_a_password_prompt_starts_over():
    """Seen on the bench: the wake-up key answered a pending password prompt."""
    sim = SimulatedArubaConsole(first_login_setup=True, left_at_password_prompt=True)
    r = run(sim, creds=APPROVED)
    assert r.status is BootstrapStatus.BOOTSTRAPPED, (r.message, r.transcript)
    assert "Session Terminated" in r.transcript and r.credentials_set
    assert (sim.username, sim.password) == ("manager", "Example-Only-Approved-1")


def test_prompts_placed_with_cursor_codes_are_recognised():
    """Second bench run: the 'Password:' prompt did not start on a new line."""
    sim = SimulatedArubaConsole(first_login_setup=True, cursor_codes=True)
    r = run(sim, creds=APPROVED)
    assert r.status is BootstrapStatus.BOOTSTRAPPED, (r.message, r.transcript)
    assert r.credentials_set and r.transcript.count("(new password: not shown)") == 2


def test_unexpected_question_is_quoted_in_the_message():
    sim = SimulatedArubaConsole(first_login_setup=True,
                                setup_password_prompt="Enter the old password: ")
    r = run(sim, creds=APPROVED)
    assert "'Enter the old password:'" in r.message


class _Chunks:
    """A transport returning fixed chunks, to cut escape codes like a serial port does."""

    def __init__(self, *chunks: bytes) -> None:
        self.chunks = list(chunks)

    def read(self, size: int = 1) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""

    def write(self, data: bytes) -> int:
        return len(data)

    def close(self) -> None:
        pass


def test_escape_code_cut_by_a_read_is_still_removed():
    """Bench transcript: 'ESC' ended one read, '[24;18HPassword:' started the next."""
    session = ConsoleSession(_Chunks(b"manager\r\n\x1b", b"[24;18HPassword: "),
                             read_timeout=0.5, settle_time=0)
    idx, text = session.read_until_any([re.compile(r"(?:^|\n)Password\s*:\s*$")])
    assert idx == 0 and text == "manager\nPassword: "


def test_line_codes_become_line_breaks():
    assert clean("a\x1bEb") == "a\nb"
    assert clean("a\x1b[2Lb") == "a\n\nb"
    assert clean("x\x1b[24;1H\x1b[2Kbench#") == "xbench#"


def test_whole_bootstrap_with_cursor_codes_and_tiny_reads():
    sim = SimulatedArubaConsole(first_login_setup=True, cursor_codes=True, max_read=5)
    r = run(sim, creds=APPROVED)
    assert r.status is BootstrapStatus.BOOTSTRAPPED, (r.message, r.transcript)
    assert "\x1b" not in r.transcript and "[24;" not in r.transcript


# -- preconfigured switches: erase first (product owner, 2026-11-23) ------------------------
from undm.provisioning.aos_switch import EraseRequest  # noqa: E402

PRECONFIGURED = Credentials("manager", "preconfigured-test-pw")
NEW_LOGIN = Credentials("manager", "approved-test-pw")


def preconfigured(**kw):
    """As on the bench: operator prompt without login, 'enable' needs the manager login."""
    return SimulatedArubaConsole(hostname="lab-bhdmz-sw01", username="manager",
                                 password="preconfigured-test-pw", operator_level=True,
                                 enable_login=True, first_login_setup=False,
                                 extra_config=["ip route 0.0.0.0 0.0.0.0 192.0.2.254"], **kw)


def test_preconfigured_switch_fails_without_erase_as_on_the_bench():
    sim = preconfigured()
    r = run(sim, creds=NEW_LOGIN)
    assert r.status is BootstrapStatus.FAILED
    assert "Could not enter manager (enable) level" in r.message
    assert "Unable to verify password" in r.transcript
    assert not r.erased and sim.vlans.keys() == {1}


def test_preconfigured_switch_is_erased_then_bootstrapped_with_the_approved_login():
    sim = preconfigured()
    r = run(sim, creds=NEW_LOGIN,
            erase=EraseRequest(PRECONFIGURED, "lab-bhdmz-sw01", restart_timeout=2,
                               down_delay=0, poll=0.2))
    assert r.status is BootstrapStatus.BOOTSTRAPPED, (r.message, r.transcript)
    assert r.erased == "lab-bhdmz-sw01" and sim.erased == 1
    assert r.message.startswith("Erased the configuration of 'lab-bhdmz-sw01' first.")
    assert r.credentials_set and (sim.username, sim.password) == ("manager", "approved-test-pw")
    assert r.commands_sent[0] == "erase startup-config" and r.saved and r.verified
    assert "preconfigured-test-pw" not in r.transcript and "approved-test-pw" not in r.transcript


def test_erase_needs_the_typed_hostname_to_match_the_switch():
    sim = preconfigured()
    r = run(sim, creds=NEW_LOGIN, erase=EraseRequest(PRECONFIGURED, "other-switch"))
    assert r.status is BootstrapStatus.FAILED
    assert "is 'lab-bhdmz-sw01', not 'other-switch'" in r.message
    assert "erase startup-config" not in sim.commands_received and not getattr(sim, "erased", 0)


def test_erase_with_a_wrong_current_login_erases_nothing():
    sim = preconfigured()
    r = run(sim, creds=NEW_LOGIN,
            erase=EraseRequest(Credentials("manager", "wrong"), "lab-bhdmz-sw01"))
    assert r.status is BootstrapStatus.FAILED
    assert "Could not log in with the switch's current login" in r.message
    assert "Nothing was erased" in r.message and not getattr(sim, "erased", 0)


def test_erase_on_a_factory_default_switch_erases_nothing():
    sim = SimulatedArubaConsole()
    r = run(sim, creds=NEW_LOGIN,
            erase=EraseRequest(Credentials("manager", ""), "Aruba-2930F-48G-4SFP"))
    assert r.status is BootstrapStatus.BOOTSTRAPPED, r.message
    assert not r.erased and "erase startup-config" not in sim.commands_received


def test_unknown_question_after_erase_is_not_answered(monkeypatch):
    sim = preconfigured()
    original = sim._run

    def run_cmd(cmd):
        if cmd == "erase startup-config":
            sim._state = "erase_confirm"
            return "Type ERASE to wipe all files: "
        return original(cmd)
    monkeypatch.setattr(sim, "_run", run_cmd)
    r = run(sim, creds=NEW_LOGIN, erase=EraseRequest(PRECONFIGURED, "lab-bhdmz-sw01"))
    assert r.status is BootstrapStatus.FAILED
    assert "asked something UNDM does not answer" in r.message
    assert not getattr(sim, "erased", 0)


def test_typed_hostname_is_compared_without_regard_to_case():
    sim = preconfigured()
    r = run(sim, creds=NEW_LOGIN,
            erase=EraseRequest(PRECONFIGURED, "LAB-BHDMZ-SW01", restart_timeout=2,
                               down_delay=0, poll=0.2))
    assert r.status is BootstrapStatus.BOOTSTRAPPED, r.message
    assert r.erased == "lab-bhdmz-sw01"


def test_erased_switch_that_never_answers_is_reported_clearly():
    sim = preconfigured()
    original = sim._factory_reset

    def reset_then_go_silent():
        original()
        sim.silent = True  # e.g. the console cable was pulled during the restart
    sim._factory_reset = reset_then_go_silent
    r = run(sim, creds=NEW_LOGIN, erase=EraseRequest(PRECONFIGURED, "lab-bhdmz-sw01",
                                                     restart_timeout=0.6, down_delay=0, poll=0.2))
    assert r.status is BootstrapStatus.FAILED
    assert "was erased but did not answer on the console" in r.message
    assert "run the bootstrap again without erasing" in r.message
    assert r.erased == "lab-bhdmz-sw01"  # the result says that the erase happened


def test_erased_unit_waiting_for_speed_sense_gets_two_enters_and_is_flagged_without_password():
    """Bench 2026-11-23 (BH-DMZ, WC.16.10.0025): after the erase the console printed
    'Waiting for Speed Sense.  Press <Enter> twice to continue.' and then asked for no
    manager credentials, so the switch had no manager password."""
    sim = preconfigured(speed_sense_after_erase=True, setup_after_erase=False)
    r = run(sim, creds=NEW_LOGIN, erase=EraseRequest(PRECONFIGURED, "lab-bhdmz-sw01",
                                                     restart_timeout=3, down_delay=0, poll=1))
    assert r.status is BootstrapStatus.BOOTSTRAPPED, (r.message, r.transcript)
    assert "Waiting for Speed Sense" in r.transcript
    # It asked for no manager credentials, so UNDM set the approved password itself.
    assert r.password_set and not r.no_password and not r.credentials_set
    assert (sim.username, sim.password) == ("manager", "approved-test-pw")
    assert "it was set to the device's attached login and saved" in r.message
    assert r.commands_sent[-1] == "password manager"
    assert "approved-test-pw" not in r.transcript


def test_switch_without_password_gets_the_attached_login_with_the_bench_prompts():
    sim = SimulatedArubaConsole()
    r = run(sim, creds=NEW_LOGIN)
    assert r.status is BootstrapStatus.BOOTSTRAPPED and r.password_set and r.saved
    assert sim.password == "approved-test-pw" and sim.saved_config is not None
    assert "password manager" in sim.saved_config  # saved together with the VLAN
    assert "New password for manager:" in r.transcript and "approved-test-pw" not in r.transcript
    sim._state, sim._enters = "asleep", 0  # a new console session, as the service starts
    again = run(sim, creds=NEW_LOGIN)  # now it asks for the password: nothing more to do
    assert again.status is BootstrapStatus.ALREADY_CONFIGURED and not again.password_set


def test_password_is_not_set_for_another_user_name():
    sim = SimulatedArubaConsole()
    r = run(sim, creds=Credentials("admin", "approved-test-pw"))
    assert r.status is BootstrapStatus.BOOTSTRAPPED and not r.password_set and r.no_password
    assert sim.password is None


def test_no_password_flag_only_when_the_switch_asked_for_none():
    assert run(SimulatedArubaConsole()).no_password  # factory default, no password
    new = run(SimulatedArubaConsole(first_login_setup=True), creds=NEW_LOGIN)
    assert new.credentials_set and not new.no_password
    with_pw = run(SimulatedArubaConsole(username="manager", password="approved-test-pw"),
                  creds=NEW_LOGIN)
    assert with_pw.status is BootstrapStatus.BOOTSTRAPPED and not with_pw.no_password
