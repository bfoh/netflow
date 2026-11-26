"""First access to a factory Nokia 7705 SAR-Hmc over its console cable (D-112).

A factory unit does not accept the default login: its boot options start auto-discovery
and its configuration file, and Nokia's guide says some variants carry a unique factory
password. The product owner's team therefore starts the unit once without its
configuration and without auto-discovery, logs in with the default login, sets the admin
password and saves the boot options and configuration.

Every question answered and every command sent below comes from the product owner's
console recording of that procedure (2026-11-26, a 7705 SAR-Hmc on TiMOS 20.5.R1), with
two additions that Nokia documents publicly (7705 SAR Basic System Configuration Guide,
"CLI usage"): ``environment no more`` (paging off for this session only) and the pager
text "Press any key to continue (Q to quit)". Message families ``MINOR:``, ``MAJOR:``,
``CRITICAL:`` and ``Error:`` are Nokia's documented formats; the recording shows ``MINOR:``.

EXPERIMENTAL: built from one recording. The first bench run (2026-11-26) showed the start
of a real unit and how its 3-second question is printed (counting down); the steps after the
question have not yet run on hardware. It answers only the listed questions, in the listed
order: anything else ends the procedure with the unit's own text (D-031), and the boot
options file is never written from the boot menu.

Questions are found anywhere in the unit's output (``ConsoleSession.wait_for``), not only at
its very end: the first bench run printed the 3-second question but UNDM, waiting for the
output to end with it, never answered (D-112).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from undm.drivers.base import Credentials
from undm.provisioning.console import ConsoleError, ConsoleSession, ConsoleTimeoutError
from undm.provisioning.results import BootstrapResult, BootstrapStatus

MODEL = "7705 SAR-Hmc"
FAMILY = "Nokia 7705 SAR"  # in the boot loader's and the image's banner
CONSOLE_SPEED = 115200  # the factory boot options' console-speed (recording; Nokia's default)

# Nokia's documented default login ("The default login is admin. The default password is
# admin."), which the unit accepts once it starts without its configuration file
# (recording; confirmed by the product owner 2026-11-26). A public default, not a secret.
FACTORY_USER = "admin"
FACTORY_PASSWORD = "admin"  # noqa: S105 - the vendor's documented factory default

# -- what the console shows (recording; bench 2026-11-26) ------------------------------
# Questions: matched wherever they appear (each sentence occurs once per question).
HIT_KEY = re.compile(r"Hit a key within \d+ seconds? to change boot par(?:ameter|m)s\.\.\.")
HIT_KEY_START = "Hit a key within"  # to tell "not recognised" from "not shown"
TYPE_SROS = re.compile(
    r'Type "sros" and hit ENTER within \d+ seconds? to begin changing parameters:')
PRESS_ENTER = re.compile(r"Press ENTER to begin, or 'flash' to enter firmware update\.\.\.")
IMAGE_URL = re.compile(r"Software Image URL:")
CONFIG_URL = re.compile(r"Config File URL:")
FIPS = re.compile(r"press ENTER to keep existing fips configuration")
AUTO_DISCOVERY = re.compile(r"Would you like to keep auto-discovery enabled\? \(yes/no\)")
OVERWRITE_BOF = re.compile(r"Do you want to overwrite \S+ with the new settings\? \(yes/no\):")
LOGIN_SEEN = re.compile(r"(?:^|\n)Login:")
PASSWORD_SEEN = re.compile(r"(?:^|\n)Password:")
# After an answer: the end of the output (the next question or the prompt).
LOGIN = re.compile(r"(?:^|\n)Login:\s*$")
PASSWORD = re.compile(r"(?:^|\n)Password:\s*$")
# "*A:name#" (the asterisk: unsaved changes), also inside a context ("A:name>config#").
PROMPT = re.compile(r"(?:^|\n)\*?[AB]:[^\s#$>]+(?:>[^\s#$]+)*[#$]\s*$")
PAGER = re.compile(r"Press any key to continue \(Q to quit\)\s*$")
ERROR = re.compile(r"^(?:(?:MINOR|MAJOR|CRITICAL): .*|Error: .*)$", re.M)
TOO_SIMPLE = re.compile(r"does not meet the system requirement", re.I)
_BOF_LINE = re.compile(r"^[ \t]{2,}([a-z][a-z0-9-]*)[ \t]+(\S.*?)[ \t]*$", re.M)
_FACT = re.compile(r"^([A-Z][A-Za-z/ ]+?)\s*:\s?(.*?)\s*$", re.M)
# The password is typed on a command line: nothing that could end or split the line.
_SAFE_PASSWORD = re.compile(r"^[!#-&(-~]+$")  # printable ASCII without space, " and '

CONFIG_FILE = "cf3:\\config.cfg"


@dataclass(frozen=True)
class _Answer:
    key: str  # a short name, for diagnostics
    question: re.Pattern[str]
    answer: str
    asked: str  # the question in words, for messages
    shown: str  # the answer in words, for the preview
    needs: str = ""  # text the unit must have shown with the question

    def echo(self) -> re.Pattern[str]:
        """The typed answer shown back by the unit: right after the question (a plain
        echo) or in its redrawn line (``…parameters: sros``, bench 2026-11-26)."""
        return re.compile(r"(?:\A[ \t]*|" + self.question.pattern + r"[ \t]*)"
                          + re.escape(self.answer) + r"(?!\S)")


# The boot menu, in the order of the recording.
BOOT_MENU: tuple[_Answer, ...] = (
    _Answer("sros", TYPE_SROS, "sros", 'to type "sros"', "sros (it counts down from 30 seconds)"),
    _Answer("begin", PRESS_ENTER, "", "to press ENTER to begin", "Enter (begin)"),
    _Answer("image", IMAGE_URL, "", "for the software image", "Enter (keep the software image)"),
    _Answer("config", CONFIG_URL, "none", "for the configuration file",
            "none (start without its file)", needs="the word 'none' for no Config URL"),
    _Answer("fips", FIPS, "", "about fips-140-2", "Enter (keep the fips setting)"),
    _Answer("auto_discovery", AUTO_DISCOVERY, "no", "about auto-discovery",
            "no (auto-discovery off)"),
    _Answer("overwrite", OVERWRITE_BOF, "no", "to overwrite the boot options file",
            "no (the boot options file is not written here)"),
)

COMMANDS: tuple[str, ...] = (
    "environment no more",
    "admin save config.cfg",
    "exec cf3:/config.cfg",
    'configure system security user "admin" password ********',
    f"bof primary-config {CONFIG_FILE}",
    "show bof",
    "bof persist on",
    "show bof",
    "bof save",
    "admin save",
    "show system information",
)


# The key at "Hit a key within 3 seconds": Enter, as the team presses (product owner,
# 2026-11-26).
KEY = "\r"


def preview_steps() -> list[str]:
    """What UNDM types, in order (the password is never shown)."""
    return (["(you switch the modem off and on)", "Enter, within 3 seconds of its question"]
            + [f"{a.shown}" for a in BOOT_MENU]
            + [f"Login: {FACTORY_USER} (the factory login)"] + list(COMMANDS))


@dataclass(frozen=True)
class Timing:
    # From Run to the 3-second question: the person switches the unit off and on, and the
    # unit takes about 2.5 minutes to reach the question (bench 2026-11-26).
    power_on: float = 600.0
    # Each boot-menu question; longer than the sros question's 30-second countdown, whose
    # line is redrawn every second while UNDM waits.
    menu: float = 40.0
    key_gap: float = 0.15  # between typed characters in the boot menu, as a person types
    echo: float = 5.0  # for the unit to show a typed answer before UNDM presses Enter
    boot: float = 420.0  # from the last answer to "Login:"
    command: float = 40.0


class _Stop(Exception):
    def __init__(self, status: BootstrapStatus, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def password_problem(credentials: Credentials | None) -> str | None:
    """Why this login cannot be set on the modem, if it cannot."""
    if credentials is None or not credentials.password:
        return ("Choose this device's login first (Stage a system, step 1): its password "
                "becomes the modem's admin password.")
    if credentials.username != FACTORY_USER:
        return (f"The modem's administrator is '{FACTORY_USER}': choose a login with that "
                f"user name (this one has '{credentials.username}').")
    if not _SAFE_PASSWORD.match(credentials.password):
        return ("UNDM types the password on the modem's command line: it must not contain "
                "spaces, quotation marks or characters outside plain ASCII.")
    return None


def parse_bof(text: str) -> dict[str, list[str]]:
    """Boot options as listed at power-on or by ``show bof``: name -> values."""
    out: dict[str, list[str]] = {}
    for m in _BOF_LINE.finditer(text):
        out.setdefault(m.group(1), []).append(m.group(2))
    return out


def parse_system_information(text: str) -> dict[str, str]:
    wanted = {"System Name": "name", "System Type": "type", "System Version": "version",
              "Changes Since Last Save": "unsaved_changes", "Last Saved Config": "saved_config"}
    out: dict[str, str] = {}
    for m in _FACT.finditer(text):
        key = wanted.get(m.group(1).strip())
        if key and key not in out:
            out[key] = m.group(2)
    return out


_PROMPT_NAME = re.compile(r"(?:^|\n)\*?[AB]:([^\s#$>]+)")


def prompt_names(text: str) -> list[str]:
    """The unit names its prompts show (a factory unit is named after its serial number)."""
    return sorted({m.group(1) for m in _PROMPT_NAME.finditer(text)})


def _last_line(text: str) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return lines[-1][-160:] if lines else "(nothing)"


# Stages of a first access, for progress reports while it runs.
STAGES = ("listening", "question_answered", "boot_menu", "starting", "logged_in", "commands",
          "saved", "finished")


def _counts(session: ConsoleSession) -> str:
    return ", ".join(f"{k} ×{n}" for k, n in session.ignored.most_common()) or "none"


class SarConsole:
    def __init__(self, session: ConsoleSession, timing: Timing | None = None,
                 on_stage: Callable[[str], None] | None = None) -> None:
        self.s = session
        self.t = timing or Timing()
        self.sent: list[str] = []
        self.on_stage = on_stage

    def stage(self, name: str) -> None:
        if self.on_stage is not None:
            self.on_stage(name)

    def command(self, cmd: str, timeout: float | None = None) -> str:
        """Send one command and return what the unit printed up to its next prompt."""
        self.s.write_line(cmd)
        self.sent.append(self.s.mask(cmd))
        out = ""
        while True:
            idx, text = self.s.read_until_any([PROMPT, PAGER], timeout or self.t.command)
            out += text
            if idx == 0:
                return out
            self.s.write_key(" ")

    def must(self, cmd: str, what: str, expect: tuple[str, ...] = (),
             saved_so_far: str = "Nothing was saved.") -> str:
        """A command that must be accepted: no error line, and the listed words shown."""
        out = self.command(cmd)
        refused = ERROR.search(out)
        if refused:
            raise _Stop(BootstrapStatus.FAILED,
                        f"{what}: the modem answered '{refused.group(0)[:200]}'. {saved_so_far}")
        missing = [w for w in expect if w not in out]
        if missing:
            raise _Stop(BootstrapStatus.FAILED,
                        f"{what}: the modem did not confirm it (no '{missing[0]}' in its "
                        f"answer; last line '{_last_line(out)}'). {saved_so_far}")
        return out

    def login(self, user: str, password: str, timeout: float) -> bool:
        """Answer "Login:" and "Password:"; False when the unit asks for the login again."""
        self.s.write_line(user)
        self.s.wait_for([PASSWORD_SEEN], timeout)
        self.s.write_secret(password)
        idx, _ = self.s.read_until_any([PROMPT, LOGIN, PASSWORD], timeout)
        return idx == 0


def first_access(session: ConsoleSession, new: Credentials | None,
                 timing: Timing | None = None,
                 on_stage: Callable[[str], None] | None = None) -> BootstrapResult:
    """Run the first access. ``new`` is the device's login: its password becomes admin's."""
    console = SarConsole(session, timing, on_stage)
    t = console.t
    findings: list[str] = []
    facts: dict[str, str] = {}
    diagnostics: dict[str, str] = {}
    state = {"saved": False, "verified": False, "password_set": False}

    def result(status: BootstrapStatus, message: str) -> BootstrapResult:
        diagnostics["received_bytes"] = str(session.received)
        diagnostics["control_characters_ignored"] = _counts(session)
        if status in (BootstrapStatus.FAILED, BootstrapStatus.REFUSED) and session.received:
            diagnostics["last_received"] = session.raw_tail(400)
        return BootstrapResult(
            status=status, message=message, commands_sent=list(console.sent),
            findings=findings, verified=state["verified"], saved=state["saved"],
            transcript=session.transcript_text, password_set=state["password_set"],
            facts=facts, diagnostics=diagnostics)

    problem = password_problem(new)
    if problem or new is None:
        return result(BootstrapStatus.REFUSED, f"{problem} Nothing was sent to the modem.")
    session.secrets.append(new.password)

    try:
        # 1. Power-on: the boot loader lists its boot options, then asks for a key. Found as
        # soon as the sentence arrives; the key goes at once (the unit waits 3 seconds).
        console.stage("listening")
        minutes = (f"{t.power_on / 60:.0f} minutes" if t.power_on >= 120
                   else f"{t.power_on:g} seconds")
        try:
            idx, text = session.wait_for([HIT_KEY, LOGIN_SEEN], t.power_on)
        except ConsoleTimeoutError:
            if not session.received:
                raise _Stop(BootstrapStatus.FAILED,
                            f"Nothing arrived from the console in {minutes}. Check the "
                            "console cable, the COM port and the speed "
                            f"({CONSOLE_SPEED}), and switch the modem off and on after "
                            "pressing Run. Nothing was changed.") from None
            raise _Stop(BootstrapStatus.FAILED,
                        "The modem's start-up text arrived, but "
                        + ("UNDM did not recognise its 3-second question"
                           if HIT_KEY_START in session.transcript_text else
                           "its 3-second question did not appear")
                        + f" in {minutes}. No key was sent and nothing was changed. "
                        "Please send the transcript with its technical details.") from None
        diagnostics["at_question"] = session.raw_tail(300)
        if idx == 1:
            raise _Stop(BootstrapStatus.FAILED,
                        "The modem reached its login without UNDM seeing its 3-second "
                        "question: it was probably already starting when UNDM began "
                        "listening. Nothing was changed. Press Run first, then switch the "
                        "modem off and on.")
        if FAMILY not in text:
            raise _Stop(BootstrapStatus.REFUSED,
                        f"The device starting on this console did not name itself '{FAMILY}'. "
                        "No key was sent; it starts normally. Nothing was changed.")
        if "Contents of Boot Options File" not in text:
            raise _Stop(BootstrapStatus.FAILED,
                        "UNDM did not see the modem's boot options before its 3-second "
                        "question, so it sent no key. Switch the modem off and on again "
                        "after pressing Run. Nothing was changed.")
        bof = parse_bof(text.split("Contents of Boot Options File", 1)[1])
        findings.append("Boot options at power-on: " + ", ".join(
            f"{k} {' / '.join(v)}" for k, v in bof.items()))
        if "auto-discover" not in bof:
            return _already_done(console, new, result, facts, state)

        # 2. The boot menu: only the recorded questions, in the recorded order.
        session.write_key(KEY, "(Enter)")
        console.sent.append("Enter (at its 3-second question)")
        console.stage("question_answered")
        answered: list[_Answer] = []
        for step in BOOT_MENU:
            text = _next_question(console, step, answered)
            diagnostics[f"at_{step.key}"] = session.raw_tail(200)
            if step.needs and step.needs not in text:
                raise _Stop(BootstrapStatus.FAILED,
                            f"The modem's question {step.asked} did not offer '{step.needs}'. "
                            "UNDM answered nothing more; the boot options file was not "
                            "written. Switch the modem off and on to start again.")
            if step.question is OVERWRITE_BOF:
                planned = parse_bof(text.split("New Settings", 1)[-1])
                if "primary-config" in planned or "auto-discover" in planned:
                    findings.append("The boot menu's new settings still list: " + ", ".join(
                        k for k in ("primary-config", "auto-discover") if k in planned))
            _answer(console, step)
            answered.append(step)
            console.sent.append(step.shown)
            console.stage("boot_menu")

        # 3. It starts without its configuration: the factory login works now.
        console.stage("starting")
        try:
            session.wait_for([LOGIN_SEEN], t.boot)
        except ConsoleTimeoutError:
            raise _Stop(BootstrapStatus.FAILED,
                        "The modem did not reach its login after the boot menu. The boot "
                        "options file was not written: switch it off and on to return to "
                        "its factory start.") from None
        if not console.login(FACTORY_USER, FACTORY_PASSWORD, t.command):
            raise _Stop(BootstrapStatus.FAILED,
                        f"The modem refused the factory login ({FACTORY_USER}) although it "
                        "started without its configuration. Nothing was changed; switch it "
                        "off and on to return to its factory start.")
        console.sent.append(f"Login: {FACTORY_USER} (the factory login)")
        console.stage("logged_in")

        # 4. The command line, as recorded. Paging off for this session first (documented).
        console.stage("commands")
        if ERROR.search(console.command("environment no more")):
            findings.append("'environment no more' was not accepted: long answers are paged "
                            "and UNDM presses a key at each page.")
        console.must("admin save config.cfg", "Saving the starting configuration")
        console.must("exec cf3:/config.cfg", "Reading that configuration back in",
                     expect=("Executed",),
                     saved_so_far="The boot options were not saved: switch the modem off "
                                  "and on, then run again.")
        out = console.command(f'configure system security user "{FACTORY_USER}" password '
                              f"{new.password}")
        refused = ERROR.search(out)
        if refused:
            why = (" Choose a login with a longer, less simple password, then run again."
                   if TOO_SIMPLE.search(out) else "")
            raise _Stop(BootstrapStatus.FAILED,
                        f"The modem refused the new admin password: "
                        f"'{refused.group(0)[:200]}'.{why} The boot options were not saved: "
                        "switch the modem off and on first.")
        state["password_set"] = True
        later = ("The boot options were not saved: switch the modem off and on, then run "
                 "again.")
        console.must(f"bof primary-config {CONFIG_FILE}", "Setting the configuration file",
                     saved_so_far=later)
        shown = parse_bof(console.must("show bof", "Reading the boot options back",
                                       saved_so_far=later))
        wrong = []
        if [v.replace("/", "\\") for v in shown.get("primary-config", [])] != [CONFIG_FILE]:
            wrong.append(f"primary-config is {shown.get('primary-config') or 'not set'}")
        if "auto-discover" in shown:
            wrong.append("auto-discovery is still listed")
        if not wrong:
            console.must("bof persist on", "Turning persist on", saved_so_far=later)
            shown = parse_bof(console.must("show bof", "Reading the boot options back",
                                           saved_so_far=later))
            if shown.get("persist") != ["on"]:
                wrong.append(f"persist is {shown.get('persist') or 'not shown'}")
        if wrong:
            raise _Stop(BootstrapStatus.FAILED,
                        "The boot options do not read back as intended (" + "; ".join(wrong)
                        + "). " + later)
        console.must("bof save", "Saving the boot options", expect=("OK", "Completed."),
                     saved_so_far="The boot options may not be saved: check with 'show bof' "
                                  "on the console.")
        console.must("admin save", "Saving the configuration",
                     expect=("Saving configuration", "OK", "Completed."),
                     saved_so_far="The boot options are saved; the configuration (with the "
                                  "new password) may not be: type 'admin save' on the console.")
        state["saved"] = True
        console.stage("saved")

        # 5. What the unit says about itself.
        facts.update(parse_system_information(console.command("show system information")))
        if facts.get("type") and facts["type"] != MODEL:
            findings.append(f"The unit calls itself '{facts['type']}'; this procedure was "
                            f"recorded on a {MODEL}.")
        state["verified"] = facts.get("unsaved_changes", "").lower() == "no"
        if not state["verified"]:
            findings.append("The unit did not confirm 'Changes Since Last Save: No'.")
        name = facts.get("name") or "the modem"
        console.stage("finished")
        return result(
            BootstrapStatus.BOOTSTRAPPED,
            f"First access done on {name}"
            + (f" ({facts['type']}, {facts.get('version', '?')})" if facts.get("type") else "")
            + ": it started once without its configuration and auto-discovery, admin has "
              "this device's password, and the boot options and configuration are saved. "
              "The console is still logged in as admin.")
    except _Stop as stop:
        return result(stop.status, stop.message)
    except ConsoleTimeoutError as e:
        return result(BootstrapStatus.FAILED,
                      f"The modem stopped answering: {session.mask(str(e))} "
                      + ("The boot options and configuration were saved before that."
                         if state["saved"] else
                         "Nothing was saved to the boot options: switch the modem off and "
                         "on, then run again."))
    except ConsoleError as e:
        return result(BootstrapStatus.FAILED, session.mask(str(e)))


_RESTART = ("The boot options file was not written; switch the modem off and on to start "
            "again.")


def _next_question(console: SarConsole, step: _Answer, answered: list[_Answer]) -> str:
    """Wait for the boot menu's next question, ``step``, and return the text up to it.

    The unit redraws a question's whole line on every key and each second of its countdown
    (``\\r`` + the question + the field, bench 2026-11-26). A question already answered
    that shows up again on the same line is such a redraw and is ignored. After a line
    break it is the question asked again (the answer was not taken): the run stops, and
    nothing is answered twice. Any other question out of order stops the run (D-031)."""
    s, t = console.s, console.t
    questions = [a.question for a in BOOT_MENU]
    deadline = time.monotonic() + t.menu
    seen = ""
    redraws = 0
    while True:
        try:
            idx, text = s.wait_for([*questions, LOGIN_SEEN], max(deadline - time.monotonic(), 0))
        except ConsoleTimeoutError:
            last = _last_line(s.transcript[-1] if s.transcript else "")
            hint = ("it is probably starting normally (the key came too late)"
                    if step is BOOT_MENU[0] else
                    f"it kept redrawing its previous question ({redraws} times)" if redraws else
                    "it showed something UNDM has no answer for")
            raise _Stop(BootstrapStatus.FAILED,
                        f"The modem did not ask {step.asked}: {hint}. Its last words: "
                        f"'{last}'. {_RESTART}") from None
        seen += text
        if idx >= len(questions):
            raise _Stop(BootstrapStatus.FAILED,
                        f"The modem started normally instead of asking {step.asked} "
                        "(it is at its login). The boot options file was not written; "
                        "nothing was changed. Switch it off and on and run again.")
        if questions[idx] is step.question:
            return seen
        before = next((a for a in answered if a.question is questions[idx]), None)
        if before is not None and "\n" not in text:
            redraws += 1  # its line redrawn: not a new question
            continue
        if before is not None:
            raise _Stop(BootstrapStatus.FAILED,
                        f"The modem asked again {before.asked} ('{_last_line(text)}'): it did "
                        "not take UNDM's answer. UNDM answered nothing twice. " + _RESTART)
        raise _Stop(BootstrapStatus.FAILED,
                    f"The modem asked '{_last_line(text)}' where UNDM expected it to ask "
                    f"{step.asked}. UNDM answered nothing more. " + _RESTART)


def _answer(console: SarConsole, step: _Answer) -> None:
    """Answer a boot-menu question: Enter alone, or the answer typed one key at a time,
    then Enter only once the unit shows the answer (its line redrawn, or a plain echo)."""
    s, t = console.s, console.t
    if step.answer:
        s.type_slowly(step.answer, t.key_gap)
        try:
            s.wait_for([step.echo()], t.echo)
        except ConsoleTimeoutError:
            raise _Stop(BootstrapStatus.FAILED,
                        f"UNDM typed '{step.answer}' when the modem asked {step.asked}, but "
                        "the modem did not show it, so UNDM did not press Enter. "
                        + _RESTART) from None
    s.write_key(KEY, "(Enter)")


def _already_done(console: SarConsole, new: Credentials,
                  result: Callable[[BootstrapStatus, str], BootstrapResult],
                  facts: dict[str, str], state: dict[str, bool]) -> BootstrapResult:
    """No auto-discovery in the boot options: not a factory unit. Change nothing; see
    whether it already has this device's login."""
    s, t = console.s, console.t
    try:
        s.wait_for([LOGIN_SEEN], t.boot)
    except ConsoleTimeoutError:
        raise _Stop(BootstrapStatus.REFUSED,
                    "This modem's boot options have no auto-discovery, so it is not in its "
                    "factory state; UNDM sent no key and it did not reach its login. "
                    "Nothing was changed.") from None
    if not console.login(new.username, new.password, t.command):
        raise _Stop(BootstrapStatus.REFUSED,
                    "This modem's boot options have no auto-discovery, so it is not in its "
                    "factory state, and it refuses this device's login. UNDM changed "
                    "nothing. If it was set up with another password, choose that login.")
    console.command("environment no more")
    facts.update(parse_system_information(console.command("show system information")))
    state["verified"] = True
    return result(BootstrapStatus.ALREADY_CONFIGURED,
                  f"{facts.get('name') or 'This modem'} has already had its first access: "
                  "its boot options have no auto-discovery and it accepts this device's "
                  "login. Nothing was changed.")
