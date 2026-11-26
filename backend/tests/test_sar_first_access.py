"""First access to a Nokia 7705 SAR-Hmc over its console (D-112), on the simulated console.

Synthetic values only: a made-up system name and password. The normal path of the simulated
console follows the product owner's recording; these tests prove UNDM's handling of it, not
the behaviour of a real modem."""

import time

import keyring
import pytest
from api_helpers import make_client
from memory_keyring import MemoryKeyring

from undm.drivers.base import Credentials
from undm.provisioning import sros_sar as sar
from undm.provisioning.console import ConsoleSession
from undm.provisioning.results import BootstrapStatus
from undm.provisioning.simulated_sar import SimulatedSarConsole
from undm.services import provisioning as prov

PASSWORD = "Example-Only-Pass-77"  # noqa: S105 - a made-up test value
FAST = sar.Timing(power_on=1, menu=1, boot=1, command=1, key_gap=0, echo=1)


def run(sim, password=PASSWORD, user="admin"):
    sim.key_window = 0.0  # no waiting in tests: the session reads without pauses
    sim.power_cycle()
    session = ConsoleSession(sim, read_timeout=1, settle_time=0)
    return sar.first_access(session, Credentials(user, password), FAST)


def test_first_access_follows_the_recording_and_never_shows_the_password():
    sim = SimulatedSarConsole()
    r = run(sim)
    assert r.status is BootstrapStatus.BOOTSTRAPPED and r.saved and r.verified and r.password_set
    # The boot menu: the recorded answers, in the recorded order; the boot options file is
    # written once, by 'bof save', never from the boot menu.
    assert r.commands_sent[:9] == [
        "Enter (at its 3-second question)", "sros (it counts down from 30 seconds)",
        "Enter (begin)", "Enter (keep the software image)",
        "none (start without its file)", "Enter (keep the fips setting)",
        "no (auto-discovery off)", "no (the boot options file is not written here)",
        "Login: admin (the factory login)"]
    assert sim.commands_received == [
        "environment no more", "admin save config.cfg", "exec cf3:/config.cfg",
        f'configure system security user "admin" password {PASSWORD}',
        "bof primary-config cf3:\\config.cfg", "show bof", "bof persist on", "show bof",
        "bof save", "admin save", "show system information", "logout"]
    assert sim.bof_writes == 1 and sim.keys == ["\r"]  # Enter, as the team presses
    assert sim.bof == {"primary-image": ["cf3:/TiMOS-SR-20.5.R1"], "wait": ["3"],
                       "persist": ["on"], "console-speed": ["115200"],
                       "primary-config": ["cf3:\\config.cfg"]}
    assert sim.file_password == PASSWORD and not sim.unsaved
    assert r.facts["type"] == "7705 SAR-Hmc" and r.facts["name"] == "NS00SIM0001"
    # The modem echoes the command line: the password is masked in both directions.
    assert PASSWORD not in r.transcript and PASSWORD not in "".join(r.commands_sent)
    assert 'password ********' in r.transcript and PASSWORD not in r.message
    assert "auto-discover private.nokia.nsp.primary.nms" in r.findings[0]


def test_a_second_run_changes_nothing():
    sim = SimulatedSarConsole()
    run(sim)
    again = run(sim)
    assert again.status is BootstrapStatus.ALREADY_CONFIGURED and sim.bof_writes == 1
    assert sim.keys == ["\r"] and "Nothing was changed" in again.message  # no key this time
    assert not any(c.startswith("Enter") for c in again.commands_sent)
    # Not a factory unit and another password: refused, nothing sent but the login.
    other = run(sim, password="Another-Pass-88")
    assert other.status is BootstrapStatus.REFUSED
    assert "refuses this device's login" in other.message
    assert sim.bof_writes == 1 and sim.file_password == PASSWORD


@pytest.mark.parametrize(("kw", "words"), [
    ({"silent": True}, "Nothing arrived from the console"),
    ({"key_ignored": True}, "started normally instead of asking to type"),
    ({"extra_question": "Enter the BOF password:"}, "Enter the BOF password:"),
    ({"fail_on": {"admin save config.cfg"}}, "Saving the starting configuration"),
    ({"fail_on": {"bof save"}}, "Saving the boot options"),
])
def test_anything_unexpected_ends_the_run_with_the_modems_words(kw, words):
    sim = SimulatedSarConsole(**kw)
    r = run(sim)
    assert r.status is BootstrapStatus.FAILED and words in r.message and not r.saved
    # The boot menu never writes the boot options file, and a refused 'bof save' wrote none.
    assert sim.bof_writes == 0 and "auto-discover" in sim.bof
    assert PASSWORD not in r.transcript


def test_a_refused_password_stops_before_the_boot_options_are_saved():
    sim = SimulatedSarConsole()
    r = run(sim, password="short")
    assert r.status is BootstrapStatus.FAILED and "is too simple" in r.message
    assert "less simple password" in r.message and sim.bof_writes == 0
    assert "bof save" not in sim.commands_received and "short" not in r.transcript


def test_logins_that_cannot_be_typed_are_refused_before_anything_is_sent():
    for user, password, words in [("admin", "", "Choose this device's login"),
                                  ("operator", PASSWORD, "administrator is 'admin'"),
                                  ("admin", 'has "quotes"', "must not contain"),
                                  ("admin", "has space", "must not contain")]:
        sim = SimulatedSarConsole()
        r = run(sim, password=password, user=user)
        assert r.status is BootstrapStatus.REFUSED and words in r.message
        assert sim.commands_received == [] and sim._state == "hit_key"  # noqa: SLF001


def test_a_listening_start_too_late_and_a_pager_are_handled():
    # Started listening after the 3-second question: the modem is at its login.
    sim = SimulatedSarConsole(key_window=0.0)
    sim.power_cycle()
    sim.read(8192)  # the start and the question pass before UNDM listens
    session = ConsoleSession(sim, read_timeout=1, settle_time=0)
    late = sar.first_access(session, Credentials("admin", PASSWORD), FAST)
    assert late.status is BootstrapStatus.FAILED
    assert "reached its login without UNDM seeing its 3-second question" in late.message
    assert sim.keys == [] and sim.bof_writes == 0
    # 'environment no more' refused: answers are paged and UNDM presses a key per page.
    sim = SimulatedSarConsole(no_paging_command=False)
    r = run(sim)
    assert r.status is BootstrapStatus.BOOTSTRAPPED and r.facts["unsaved_changes"] == "No"
    assert any("paged" in f for f in r.findings)


def test_the_patterns_match_the_recorded_wording():
    assert sar.HIT_KEY.search("Hit a key within 3 seconds to change boot parameters...")
    # As printed on the bench, counting down, with whatever follows each sentence.
    assert sar.HIT_KEY.search("Hit a key within 1 second to change boot parameters...\b\b\b")
    assert sar.HIT_KEY.search("Hit a key within 3 seconds to change boot parms...")  # Nokia guide
    assert sar.PROMPT.search("\n*A:NS00SIM0001# ") and sar.PROMPT.search("\nA:NS00SIM0001# ")
    assert sar.PROMPT.search("\n*A:lab-modem>config>system# ")
    assert not sar.PROMPT.search("\nLogin: ")
    assert sar.ERROR.search("x\nMINOR: SYSTEM #1372 The user password does not meet\n")
    assert sar.ERROR.search("Error: Bad command.") and not sar.ERROR.search("Completed.")
    bof = sar.parse_bof("    primary-config   cf3:/config.cfg\n    persist          off\n"
                        "    auto-discover    a.example\n    auto-discover    b.example\n")
    assert bof == {"primary-config": ["cf3:/config.cfg"], "persist": ["off"],
                   "auto-discover": ["a.example", "b.example"]}
    assert sar.preview_steps()[-1] == "show system information"
    assert sar.preview_steps()[1].startswith("Enter")
    assert sar.prompt_names("x\n*A:NS00SIM0001# show bof\nA:NS00SIM0001# ") == ["NS00SIM0001"]
    assert not any(PASSWORD in s for s in sar.preview_steps())


# -- through the API -------------------------------------------------------------------
SIM_MODEM = {"name": "lab-modem", "manufacturer": "Nokia", "category": "router",
             "model": "7705 SAR-Hmc", "os_family": "SR OS (7705 SAR)",
             "driver_id": "mock.nokia.sar"}


@pytest.fixture
def client():
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    prov.reset_simulation()
    c, _ = make_client()
    with c:
        yield c
    keyring.set_keyring(previous)
    prov.reset_simulation()


def add(client, body, user="admin", password=PASSWORD):
    pid = client.post("/api/projects", json={"name": "Staging " + body["name"]}).json()["id"]
    if password is not None:
        ref = client.post(f"/api/projects/{pid}/credential-refs", json={"name": "approved"}).json()
        client.put(f"/api/credential-refs/{ref['id']}/secret",
                   json={"username": user, "password": password})
        body = dict(body, credential_ref_id=ref["id"])
    r = client.post(f"/api/projects/{pid}/devices", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def go(client, did, name="lab-modem", **over):
    return client.post(f"/api/devices/{did}/provisioning/console-bootstrap", json={
        "serial_port": "SIMULATED", "baudrate": 115200, "confirm_device_name": name, **over})


def test_api_preview_run_rerun_and_audit(client):
    did = add(client, SIM_MODEM)
    pre = client.post(f"/api/devices/{did}/provisioning/console-bootstrap/preview", json={}).json()
    assert pre["supported"] and pre["procedure"] == "first_access"
    assert "sros (it counts down from 30 seconds)" in pre["commands"]
    assert "bof save" in pre["commands"]
    assert not any(PASSWORD in line for line in pre["commands"] + pre["notes"])
    assert go(client, did, name="other").status_code == 409
    r = go(client, did)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "bootstrapped" and out["saved"] and out["password_set"]
    assert out["facts"]["type"] == "7705 SAR-Hmc" and "configuration" in out["network_hint"]
    assert PASSWORD not in r.text
    # The unit's own name (its serial number from the factory) is masked in the shared text.
    assert "NS00SIM0001" not in out["sanitized_transcript"]
    assert client.get(f"/api/devices/{did}").json()["provisioning_status"] == "bootstrapped"
    assert go(client, did).json()["status"] == "already_configured"
    entry = client.get("/api/audit", params={"target_id": did}).json()[0]
    assert entry["action"] == "provisioning.console_bootstrap"
    assert entry["details"]["procedure"] == "sros_sar_first_access"
    assert "transcript" not in entry["details"] and PASSWORD not in str(entry)
    # The modem has no network address: tests say so instead of failing oddly.
    test = client.post(f"/api/devices/{did}/operations/check_reachability")
    assert "console cable only" in test.text
    ident = client.post(f"/api/devices/{did}/provisioning/console-identify",
                        json={"serial_port": "SIMULATED"})
    assert ident.status_code == 400


def test_api_needs_a_usable_login_before_anything_is_sent(client):
    no_login = add(client, SIM_MODEM, password=None)
    r = go(client, no_login)
    assert r.status_code == 409 and "Choose this device's login first" in r.json()["error"]
    other_user = add(client, dict(SIM_MODEM, name="lab-modem-2"), user="manager")
    r = go(client, other_user, name="lab-modem-2")
    assert r.status_code == 409 and "administrator is 'admin'" in r.json()["error"]
    assert prov._simulated_sar == {}  # noqa: SLF001 - no console was opened


def test_api_real_modem_needs_the_write_switch_and_a_real_port(client, monkeypatch):
    opened = []
    monkeypatch.setattr(prov, "open_serial", lambda port, baud: opened.append((port, baud)))
    did = add(client, dict(SIM_MODEM, name="bench-modem", driver_id="console.nokia.sar",
                           environment="lab"))
    r = go(client, did, name="bench-modem", serial_port="COM7")
    assert r.status_code == 403 and "Real-device changes are off" in r.json()["error"]
    assert go(client, did, name="bench-modem").status_code == 400  # SIMULATED refused
    assert opened == []


def test_api_real_modem_runs_at_115200_with_the_switch_on(monkeypatch):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    sim = SimulatedSarConsole()
    opened = []

    def open_serial(port, baud):
        opened.append((port, baud))
        sim.power_cycle()  # "the person switches it off and on" once UNDM listens
        return sim
    monkeypatch.setattr(prov, "open_serial", open_serial)
    monkeypatch.setattr(prov.sros_sar, "Timing", lambda: FAST)
    client, _ = make_client(enable_real_device_writes=True)
    try:
        with client:
            did = add(client, dict(SIM_MODEM, name="bench-modem", driver_id="console.nokia.sar",
                                   environment="lab"))
            r = go(client, did, name="bench-modem", serial_port="COM7")
            assert r.status_code == 200 and r.json()["status"] == "bootstrapped", r.text
            assert opened == [("COM7", 115200)] and sim.closed
    finally:
        keyring.set_keyring(previous)


def test_finish_staging_counts_a_console_only_device_after_its_first_access(client):
    did = add(client, SIM_MODEM)
    pid = client.get(f"/api/devices/{did}").json()["project_id"]
    r = client.post(f"/api/projects/{pid}/finish", json={"device_ids": [did]})
    assert r.status_code == 409 and "has not had its console setup" in r.json()["error"]
    assert go(client, did).json()["status"] == "bootstrapped"
    r = client.post(f"/api/projects/{pid}/finish", json={"device_ids": [did]})
    assert r.status_code == 200 and r.json()["staged_at"]



# -- the first bench run (2026-11-26): the question was printed but never answered -------
class TimedFeed:
    """Bytes that arrive at given times, read like a serial port (each read waits a little
    for data). For testing UNDM's real session settings, not a model of the modem."""

    def __init__(self, events, read_wait=0.05):
        self.events = sorted(events)
        self.read_wait = read_wait
        self.start = time.monotonic()
        self.written = []

    def read(self, size=1):
        end = time.monotonic() + self.read_wait
        while True:
            now = time.monotonic() - self.start
            ready = [e for e in self.events if e[0] <= now]
            if ready:
                self.events = [e for e in self.events if e[0] > now]
                return b"".join(e[1] for e in ready)
            if time.monotonic() >= end:
                return b""
            time.sleep(0.005)

    def write(self, data):
        self.written.append((time.monotonic() - self.start, data))
        return len(data)

    def close(self):
        pass


START = (b"TiMOS-L-20.5.R1 boot/sar Nokia 7705 SAR Copyright (c) 2000-2020 Nokia.\r\n"
         b"Contents of Boot Options File on cf3:\r\n    primary-image    cf3:/x\r\n"
         b"    auto-discover    a.example\r\n\r\n")


def sentence(n, tail=b"   "):
    unit = b"second" if n == 1 else b"seconds"
    return b"Hit a key within %d %s to change boot parameters..." % (n, unit) + tail


@pytest.mark.parametrize("form", ["spaces", "backspaces", "busy line"])
def test_the_question_is_answered_at_once_with_the_real_session_settings(form):
    tail = b"\b\b\b" if form == "backspaces" else b"   "
    events = [(0.0, START + sentence(3, tail)), (1.0, b"\r" + sentence(2, tail)),
              (2.0, b"\r" + sentence(1, tail)), (3.0, b"\r\n\r\nPrimary image location: x\r\n")]
    if form == "busy line":
        events += [(0.02 * i, b"\x00") for i in range(1, 150)]
    feed = TimedFeed(events)
    session = ConsoleSession(feed)  # settle 0.15 s, as in UNDM
    session.secrets.append(PASSWORD)
    r = sar.first_access(session, Credentials("admin", PASSWORD),
                         sar.Timing(power_on=5, menu=0.3, boot=0.3, command=0.3))
    # Enter went within half a second of the first sentence (the unit waits 3 seconds).
    assert feed.written and feed.written[0][1] == b"\r" and feed.written[0][0] < 0.5
    assert r.diagnostics["at_question"].rstrip().endswith(
        "parameters...\\b\\b\\b" if form == "backspaces" else "parameters...")
    if form == "backspaces":
        assert r.diagnostics["control_characters_ignored"].startswith("\\b ×3")


def test_text_without_a_known_question_is_reported_as_such():
    start = START + b"Hit a key within 3 seconds to stop the countdown"  # not the known form
    feed = TimedFeed([(0.0, start)])
    r = sar.first_access(ConsoleSession(feed), Credentials("admin", PASSWORD),
                         sar.Timing(power_on=0.5))
    assert r.status is BootstrapStatus.FAILED and feed.written == []
    assert "start-up text arrived, but UNDM did not recognise its 3-second question" in r.message
    assert "nothing was changed" in r.message and "technical details" in r.message
    assert "stop the countdown" in r.diagnostics["last_received"]
    feed = TimedFeed([(0.0, b"U-Boot\r\nStarting kernel ...\r\n")])
    r = sar.first_access(ConsoleSession(feed), Credentials("admin", PASSWORD),
                         sar.Timing(power_on=0.5))
    assert "its 3-second question did not appear" in r.message and feed.written == []


def test_bench_forms_on_the_simulated_modem_complete_with_real_settings():
    for kw in ({"question_tail": "\b\b\b"}, {"trickle": True}):
        sim = SimulatedSarConsole(key_window=3.0, **kw)
        sim.power_cycle()
        r = sar.first_access(ConsoleSession(sim), Credentials("admin", PASSWORD),
                             sar.Timing(power_on=5, menu=2, boot=2, command=2))
        assert r.status is BootstrapStatus.BOOTSTRAPPED, (kw, r.message)
        assert sim.keys == ["\r"] and sim.bof_writes == 1


def test_stages_are_reported_in_order():
    seen = []
    sim = SimulatedSarConsole(key_window=0.0)
    sim.power_cycle()
    sar.first_access(ConsoleSession(sim, read_timeout=1, settle_time=0),
                     Credentials("admin", PASSWORD), FAST, on_stage=seen.append)
    assert [s for s in sar.STAGES if s in seen] == list(dict.fromkeys(seen))
    assert seen[0] == "listening" and seen[-1] == "finished"



def test_api_progress_and_masked_diagnostics(client):
    did = add(client, SIM_MODEM)
    idle = client.get(f"/api/devices/{did}/provisioning/console-progress").json()
    assert idle == {"running": False, "stage": None, "seconds": 0, "received": 0,
                    "last_line": ""}
    out = go(client, did).json()
    done = client.get(f"/api/devices/{did}/provisioning/console-progress").json()
    assert done["running"] is False and done["stage"] == "finished" and done["received"] > 0
    assert "NS00SIM0001" not in done["last_line"]  # the unit's name is masked
    diag = out["diagnostics"]
    assert "Hit a key within 3 seconds" in diag["at_question"]
    assert "--- Technical details (UNDM) ---" in out["sanitized_transcript"]
    assert PASSWORD not in str(out) and PASSWORD not in str(done)
    entry = client.get("/api/audit", params={"target_id": did}).json()[0]
    assert "at_question" in entry["details"]["diagnostics"]
    assert client.get("/api/devices/nope/provisioning/console-progress").status_code == 404


def test_shared_text_masks_uuids():
    from undm.security.sanitize import sanitize
    text = "UUID 01234567-89AB-4DEC-A75A-0123456789AB, again 01234567-89ab-4dec-a75a-0123456789ab"
    assert sanitize(text) == "UUID <uuid-1>, again <uuid-1>"



# -- the second bench run (2026-11-26, v85): the sros field is redrawn on every key -------
# The raw characters the modem sent, from the run's technical details (Nokia's own texts and
# default boot options only).
BENCH_SROS = ("\r\rHit a key within 3 seconds to change boot parameters...   \b\b\b\r\r\n"
              '\rType "sros" and hit ENTER within 30 seconds to begin changing parameters:'
              "      \b\b\b\b\b"
              '\rType "sros" and hit ENTER within 30 seconds to begin changing parameters: s'
              "     \b\b\b\b\b")


def test_the_bench_field_redraw_is_one_question_and_shows_the_typed_answer():
    from undm.provisioning.console import clean
    text = clean(BENCH_SROS)
    assert len(sar.TYPE_SROS.findall(text)) == 2 and "\n" not in text.split("parameters:", 1)[1]
    step = sar.BOOT_MENU[0]
    assert not step.echo().search(text)  # only "s" so far: Enter must wait
    assert step.echo().search(text + '\rType "sros" and hit ENTER within 29 seconds to begin '
                                      "changing parameters: sros     ")
    plain = sar.BOOT_MENU[3]  # the configuration file: a plain echo
    assert plain.echo().search(" none") and not plain.echo().search(" non")


def run_real(sim, **timing):
    """The first access with UNDM's real session settings and typing speed."""
    sim.power_cycle()
    t = {"power_on": 5, "menu": 3, "boot": 3, "command": 3, "echo": 2, **timing}
    return sar.first_access(ConsoleSession(sim), Credentials("admin", PASSWORD),
                            sar.Timing(**t))


def test_the_redrawn_field_is_typed_into_and_enter_waits_for_the_answer():
    sim = SimulatedSarConsole(key_window=3.0, sros_tick=0.05)  # a fast countdown: many redraws
    r = run_real(sim)
    assert r.status is BootstrapStatus.BOOTSTRAPPED, r.message
    assert sim.keys == ["\r"] and sim.bof_writes == 1 and "auto-discover" not in sim.bof
    assert "<<< sros" in r.transcript and "at_sros" in r.diagnostics
    assert "at_overwrite" in r.diagnostics


def test_asked_again_on_a_new_line_stops_without_answering_twice():
    sim = SimulatedSarConsole(key_window=3.0, reask=True)
    r = run_real(sim)
    assert r.status is BootstrapStatus.FAILED and "asked again to type" in r.message
    assert r.transcript.count("<<< sros") == 1 and sim.bof_writes == 0
    assert "switch the modem off and on" in r.message


def test_no_echo_means_no_enter():
    sim = SimulatedSarConsole(key_window=3.0, no_echo=True)
    r = run_real(sim)
    assert r.status is BootstrapStatus.FAILED and "did not show it" in r.message
    assert "did not press Enter" in r.message and sim.bof_writes == 0
    assert "primary-config" in sim.bof  # nothing was written


# -- the third bench run (2026-11-26, v86): the first access worked on hardware ----------
def test_logout_at_the_end_shows_the_login_prompt():
    sim = SimulatedSarConsole()
    r = run(sim)
    assert r.status is BootstrapStatus.BOOTSTRAPPED and "UNDM logged out" in r.message
    assert sim.commands_received[-1] == "logout" and r.commands_sent[-1] == "logout"
    assert sim._state == "login"  # noqa: SLF001 - the console is back at its login
    again = run(sim)  # the "already done" path logs out too
    assert again.status is BootstrapStatus.ALREADY_CONFIGURED
    assert sim.commands_received[-1] == "logout" and not again.findings[1:]


def test_no_login_prompt_after_logout_is_only_a_finding():
    sim = SimulatedSarConsole(fail_on={"logout"})  # answered with an error, no prompt
    r = run(sim)
    assert r.status is BootstrapStatus.BOOTSTRAPPED and r.saved
    assert "could not confirm it logged out" in r.message
    assert any("log out on the console by hand" in f for f in r.findings)


def test_admin_save_must_confirm():
    sim = SimulatedSarConsole(fail_on={"admin save config.cfg"})
    r = run(sim)
    assert r.status is BootstrapStatus.FAILED and "Saving the starting configuration" in r.message
    assert sim.bof_writes == 0


def test_shared_text_masks_engine_ids_and_keeps_the_password_marker_readable():
    from undm.security.sanitize import sanitize
    text = ("SNMP Engine ID         : 0000197f0000aabbccddeeff\n<<< (password: not shown)\n"
            "<<< (new password: not shown)\n")
    out = sanitize(text)
    assert "aabbccddeeff" not in out and "SNMP Engine ID         : <engine-1>" in out
    assert "<<< (password: not shown)" in out and "<<< (new password: not shown)" in out
