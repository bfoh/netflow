"""Platform specifics for the SSH drivers. EXPERIMENTAL — see drivers/ssh/base.py."""

from __future__ import annotations

import contextlib
import hashlib
import ipaddress
import os
import re
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar

from undm.domain.operations import DeviceOperation
from undm.domain.versions import compare
from undm.drivers.aruba.config_files import (
    address_after_loading,
    inspect_aos_switch_file,
    where_after_loading,
)
from undm.drivers.aruba.config_files import parse as parse_aos_switch_file
from undm.drivers.base import (
    ApplyMode,
    Capability,
    ConfigFileReport,
    DeviceFacts,
    DriverInfo,
    DriverMaturity,
    FirmwareImageRef,
    OperationResult,
)
from undm.drivers.blackbox.lig1014a_ssh import BlackBoxLig1014aSsh
from undm.drivers.fortinet.fortios_ssh import FortiOSSsh
from undm.drivers.ssh import base as ssh_base
from undm.drivers.ssh.base import SSH_CAPABILITIES, SshCliDriver
from undm.security.redaction import redact_text


class ArubaAOSCXSsh(SshCliDriver):
    netmiko_device_type = "aruba_aoscx"
    facts_commands = ("show version", "show system")
    running_config_command = "show running-config"
    info = DriverInfo(
        driver_id="ssh.aruba.aoscx",
        vendor="Aruba",
        platform="aoscx",
        os_family="AOS-CX",
        description="AOS-CX over SSH CLI (Netmiko 'aruba_aoscx'). Experimental, not lab-validated.",
        simulated=False,
        capabilities=SSH_CAPABILITIES,
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="ssh",
        notes=(
            "Session runs 'no page' (session only).",
            "Save uses 'copy running-config startup-config'.",
            "No automatic rollback: failures end in manual recovery from the stored backup.",
        ),
    )

    def parse_facts(self, outputs: dict[str, str], prompt: str) -> DeviceFacts:
        text = "\n".join(outputs.values())
        return DeviceFacts(
            hostname=self._search(r"^\s*Hostname\s*:\s*(\S+)", text) or prompt.rstrip("#> "),
            vendor="Aruba",
            model=self._search(r"^\s*Product Name\s*:\s*(.+)$", text) or "unknown",
            os_version=self._search(r"^\s*Version\s*:\s*(\S+)", text) or "unknown",
            serial_number=self._search(
                r"^\s*(?:Chassis Serial Nbr|Serial Number)\s*:\s*(\S+)", text),
        )


class CiscoIOSXESsh(SshCliDriver):
    netmiko_device_type = "cisco_xe"
    facts_commands = ("show version",)
    running_config_command = "show running-config"
    skip_line_patterns = (r"^\s*!", r"^Building configuration", r"^Current configuration",
                          r"^\s*end\s*$")
    info = DriverInfo(
        driver_id="ssh.cisco.iosxe",
        vendor="Cisco",
        platform="iosxe",
        os_family="IOS-XE",
        description="IOS-XE over SSH CLI (Netmiko 'cisco_xe'). Experimental, not lab-validated.",
        simulated=False,
        capabilities=SSH_CAPABILITIES,
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="ssh",
        notes=(
            "Session runs 'terminal length 0' (session only).",
            "Save uses 'write mem'.",
            "Requires privileged EXEC (level 15) login; enable-secret prompts are not handled.",
            "No automatic rollback: failures end in manual recovery from the stored backup.",
        ),
    )

    def parse_facts(self, outputs: dict[str, str], prompt: str) -> DeviceFacts:
        text = outputs.get("show version", "")
        return DeviceFacts(
            hostname=self._search(r"^(\S+) uptime is", text) or prompt.rstrip("#> "),
            vendor="Cisco",
            model=self._search(r"^\s*Model [Nn]umber\s*:\s*(\S+)", text)
            or self._search(r"^cisco (\S+) .*processor", text) or "unknown",
            os_version=self._search(r"Cisco IOS XE Software, Version (\S+)", text)
            or self._search(r"Version (\S+),", text) or "unknown",
            serial_number=self._search(r"Processor board ID (\S+)", text),
        )


def _transferring(record: object) -> bool:
    """True while a recorded TFTP transfer is still in progress."""
    return record is not None and not getattr(record, "completed", False) \
        and not getattr(record, "error", "")


class ArubaOSSwitchSsh(SshCliDriver):
    """ArubaOS-Switch (formerly ProCurve), e.g. Aruba 2930F.

    Netmiko 'aruba_osswitch' (HPProcurveSSH) session behaviour, checked in its source:
    passes the 'Press any key to continue' banner, runs 'enable', then 'terminal width 511'
    and 'no page' for the session; on logout it answers 'no' to the save prompt.
    """

    netmiko_device_type = "aruba_osswitch"
    facts_commands = ("show system", "show modules")
    parser_validated_on = ("2930F-48G-4SFP (JL260A) WC.16.10.0025",
                           "2930F-48G-4SFP (JL260A) WC.16.11.0001")
    running_config_command = "show running-config"
    skip_line_patterns = (r"^\s*;", r"^Running configuration:")
    error_pattern = SshCliDriver.error_pattern + r"|Incomplete input|Ambiguous input"
    info = DriverInfo(
        driver_id="ssh.aruba.aos_switch",
        vendor="Aruba",
        platform="aos_switch",
        os_family="ArubaOS-Switch",
        description="ArubaOS-Switch (e.g. 2930F) over SSH CLI (Netmiko 'aruba_osswitch'). "
                    "Experimental, not lab-validated.",
        simulated=False,
        capabilities=SSH_CAPABILITIES | {Capability.TEMPORARY_ADDRESS,
                                         Capability.FIRMWARE_UPGRADE, Capability.REBOOT,
                                         Capability.CONFIGURATION_REPLACE,
                                         Capability.FIRMWARE_SECONDARY_IMAGE},
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="ssh",
        notes=(
            "Needs a manager-level login (the session runs 'enable'); if the switch asks for "
            "an enable password, the login password is sent.",
            "Session runs 'terminal width 511' and 'no page' (session only).",
            "On logout Netmiko answers 'no' to the save prompt; saving uses 'write memory' "
            "only as part of a deployment.",
            "No automatic rollback: failures end in manual recovery from the stored backup.",
            "Firmware: the switch pulls the image from UNDM by TFTP into the primary flash, "
            "then reboots into it ('boot system flash primary'); no automatic firmware "
            "rollback. Run once on hardware (approved downgrade on a spare 2930F).",
            "Optional per plan: after the primary is verified, the same image is copied into "
            "the secondary flash ('copy tftp flash ... secondary'); the switch keeps booting "
            "from primary. Run once on hardware (spare 2930F).",
            "Complete configuration files (replace mode): the switch pulls the file by TFTP "
            "into its startup configuration ('copy tftp startup-config ... unix') and restarts; "
            "UNDM follows an address change made by the file, checks the serial number after "
            "the restart, and never saves the old running configuration over the new file. "
            "Not yet run on hardware.",
        ),
    )

    def _connect_kwargs(self) -> dict[str, object]:
        assert self._credentials is not None
        return {"secret": self._credentials.password}

    @classmethod
    def needs_file_server(cls, kind: str, mode: ApplyMode | None = None) -> bool:
        # The switch pulls the image, or a complete configuration file, by TFTP.
        return kind == "firmware" or (kind == "configuration" and mode is ApplyMode.REPLACE)

    @classmethod
    def inspect_config_file(cls, text: str) -> ConfigFileReport | None:
        return inspect_aos_switch_file(text)

    # -- HTTPS certificate before a file that needs one (EXPERIMENTAL) --------------------
    # The team's commands and the switch's questions (screenshots, 2026-11-19):
    #   configure
    #   crypto pki identity-profile <profile> subject   -> six questions, answered below
    #   crypto pki enroll-self-signed certificate-name <name>
    #       (silent, or 'Certificate "<name>" already exists.')
    #   web-management ssl
    # then the configuration is saved ('write memory').
    _SUBJECT_QUESTIONS: ClassVar[tuple[tuple[str, str], ...]] = (
        (r"Enter Common Name\(CN\)\s*:", "common_name"),
        (r"Enter Org Unit\(OU\)\s*:", "org_unit"),
        (r"Enter Org Name\(O\)\s*:", "org_name"),
        (r"Enter Locality\(L\)\s*:", "locality"),
        (r"Enter State\(ST\)\s*:", "state"),
        (r"Enter Country\(C\)\s*:", "country"),
    )

    # -- temporary address (EXPERIMENTAL, D-096; not yet run on hardware) -------------------
    # The team's own console commands (staging use case): 'vlan <id>' / 'ip address <a> <m>'.
    # 'no ip address <a> <m>' removes one address; whether a second 'ip address' adds to or
    # replaces the first is not verified (Q-45): both are handled. Never 'write memory'.
    @staticmethod
    def _vlan_addresses(running: str) -> dict[int, list[tuple[str, str]]]:
        found: dict[int, list[tuple[str, str]]] = {}
        vid: int | None = None
        for raw in running.splitlines():
            line = raw.strip()
            if m := re.match(r"^vlan (\d+)$", line):
                vid = int(m.group(1))
            elif line == "exit":
                vid = None
            elif vid is not None and (m := re.match(r"^ip address (\S+) (\S+)$", line)):
                found.setdefault(vid, []).append((m.group(1), m.group(2)))
        return found

    def _temporary_plan(self, spare: str) -> tuple[OperationResult | None, int, str, str]:
        op = DeviceOperation.APPLY_CONFIGURATION
        if r := self._need(op):
            return r, 0, "", ""
        current = self.target.management_address
        running = self.get_running_configuration()
        if not running.ok:
            return OperationResult.failed(op, running.message), 0, "", ""
        for vid, addresses in self._vlan_addresses(str(running.data)).items():
            for address, mask in addresses:
                if address != current:
                    continue
                try:
                    net = ipaddress.ip_network(f"{address}/{mask}", strict=False)
                    ok = ipaddress.ip_address(spare) in net and spare != address
                except ValueError:
                    ok = False
                if not ok:
                    return OperationResult.failed(
                        op, f"{spare} is not another address of the network of {address} "
                            f"({mask})"), 0, "", ""
                return None, vid, address, mask
        return OperationResult.failed(
            op, f"The running configuration shows no VLAN with the address {current}; "
                "nothing was changed"), 0, "", ""

    def temporary_address_commands(self, spare: str) -> OperationResult:
        problem, vid, address, mask = self._temporary_plan(spare)
        if problem is not None:
            return problem
        return OperationResult.success(
            DeviceOperation.APPLY_CONFIGURATION,
            {"vlan": vid, "previous": address,
             "commands": [f"vlan {vid}", f"ip address {spare} {mask}",
                          f"no ip address {address} {mask}"]},
            f"VLAN {vid}: add {spare}, then remove {address}; nothing is saved")

    def _config_lines(self, lines: list[str]) -> str | None:
        """Send configuration lines; the reason if the switch rejected one, None if sent
        (a session that drops while sending is not a rejection: the caller reads back)."""
        from netmiko.exceptions import ConfigInvalidException
        try:
            self._conn.send_config_set(lines, error_pattern=self.error_pattern,
                                       read_timeout=self.read_timeout)
        except ConfigInvalidException as e:
            return redact_text(str(e))[-300:]
        except Exception:  # noqa: BLE001 - e.g. the session ended with the address
            return None
        return None

    def set_temporary_address(self, spare: str) -> OperationResult:
        op = DeviceOperation.APPLY_CONFIGURATION
        problem, vid, old, mask = self._temporary_plan(spare)
        if problem is not None:
            return problem
        port = self.target.port or 22
        if ssh_base.tcp_port_open(spare, port):
            return OperationResult.failed(
                op, f"Another device already answers at {spare}; nothing was changed")
        facts = self.get_device_facts()
        serial = facts.data.serial_number if facts.ok else None
        notes: list[str] = []
        rejected = self._config_lines([f"vlan {vid}", f"ip address {spare} {mask}"])
        if rejected:
            return OperationResult.failed(
                op, f"The switch rejected 'ip address {spare} {mask}' in VLAN {vid}; its own "
                    "address was not removed", {"device_output": rejected})
        # From here on the switch is reached at the spare address.
        self.disconnect()
        home = self.target
        self.target = replace(self.target, management_address=spare)
        back = self.connect()
        if not back.ok:
            self.target = home
            return OperationResult.failed(
                op, f"The switch took the command but does not answer at {spare} "
                    f"({back.message}). Nothing was saved: restarting the switch returns it "
                    "to its saved configuration.")
        again = self.get_device_facts()
        if serial and again.ok and again.data.serial_number != serial:
            self.target = home
            return OperationResult.failed(
                op, f"A different device answers at {spare} (serial "
                    f"{again.data.serial_number}); stopped. Nothing was saved.")
        running = self.get_running_configuration()
        listed = self._vlan_addresses(str(running.data)).get(vid, []) if running.ok else []
        if (old, mask) in listed:
            notes.append(f"the switch kept {old} next to {spare}; UNDM removed it")
            rejected = self._config_lines([f"vlan {vid}", f"no ip address {old} {mask}"])
            if rejected:
                return OperationResult.failed(
                    op, f"The switch now also answers at {spare}, but rejected 'no ip address "
                        f"{old} {mask}': {old} is still in use by it. Nothing was saved.",
                    {"device_output": rejected})
            running = self.get_running_configuration()
            listed = self._vlan_addresses(str(running.data)).get(vid, []) if running.ok else []
        else:
            notes.append(f"the switch replaced {old} by {spare}")
        if (spare, mask) not in listed or (old, mask) in listed:
            return OperationResult.failed(
                op, f"After the commands the running configuration does not show VLAN {vid} "
                    f"with {spare} only. Nothing was saved: restarting the switch returns it "
                    "to its saved configuration.")
        if ssh_base.tcp_port_open(old, port):
            return OperationResult.failed(
                op, f"The switch moved to {spare}, but something still answers at {old}. "
                    "Nothing was saved.")
        return OperationResult.success(
            op, {"address": spare, "previous": old, "vlan": vid, "notes": notes},
            f"running at {spare} (VLAN {vid}) until its next restart; {old} is free; nothing "
            "was saved, so it returns to its saved configuration at the next power-on")

    def check_before_apply(self, config: str, mode: ApplyMode) -> OperationResult | None:
        """Both switch roles of a system end at the same OOBM address (D-091): if the file
        moves this switch to an address where another device already answers, loading it
        would leave two devices on one address. Stop before anything is sent."""
        if mode is not ApplyMode.REPLACE:
            return None
        current = self.target.management_address
        after = address_after_loading(config, current)
        if after is None or after == current:
            return None
        if not ssh_base.tcp_port_open(after, self.target.port or 22):
            return None
        return OperationResult.failed(
            DeviceOperation.APPLY_CONFIGURATION,
            f"Another device already answers at {after}, the address this file gives the "
            "switch (on the bench: probably the other 2930F). Unplug it from the bench "
            "network, then make a new plan for this switch. Nothing was changed.")

    def prepare_before_apply(self, config: str, mode: ApplyMode,
                             settings: Mapping[str, Any]) -> OperationResult | None:
        if mode is not ApplyMode.REPLACE:
            return None
        statements = {ln.strip() for ln in config.splitlines()}
        if not {"web-management ssl", "no web-management"} <= statements:
            return None  # the file does not make the web interface HTTPS-only
        op = DeviceOperation.APPLY_CONFIGURATION
        subject = settings.get("certificate_subject")
        if not subject:
            return OperationResult.success(
                op, {"warnings": [
                    "The file makes the web interface HTTPS-only, but this project has no "
                    "certificate subject (Project settings), so UNDM did not create a "
                    "certificate. Create it by hand before loading if the switch has none."]},
                "no HTTPS certificate created (no certificate subject set)")
        if r := self._need(op):
            return r
        name = str(subject.get("certificate_name") or "certificate")
        profile = str(subject.get("profile_name") or "Profile")
        answers = [(q, str(subject.get(key) or "")) for q, key in self._SUBJECT_QUESTIONS]
        steps = [("configure", []),
                 (f"crypto pki identity-profile {profile} subject", answers),
                 (f"crypto pki enroll-self-signed certificate-name {name}", []),
                 ("web-management ssl", []),
                 ("end", []),
                 ("write memory", [])]
        outputs = []
        existed = False
        for command, questions in steps:
            talk = self._dialogue(command, questions, timeout=120, idle_timeout=30)
            outputs.append(talk.output)
            diagnostics: dict[str, object] = {"device_output": talk.tail}
            if talk.ended != "prompt":
                return OperationResult.failed(
                    op, f"Certificate step: no prompt after '{command}' ({talk.detail}). The "
                        "switch may be asking something UNDM does not answer; its text is "
                        "below. The file was not sent.", diagnostics)
            if questions and len(talk.replies) != len(questions):
                return OperationResult.failed(
                    op, f"Certificate step: the switch asked {len(talk.replies)} of the "
                        f"{len(questions)} expected subject questions; stopped before sending "
                        "the file.", diagnostics)
            if re.search(r"already exists", talk.output, re.I):
                existed = True
            elif re.search(self.error_pattern, talk.output):
                return OperationResult.failed(
                    op, f"Certificate step: the switch rejected '{command}' (below). The file "
                        "was not sent.", diagnostics)
        return OperationResult.success(
            op, {"certificate": name, "existed": existed},
            f"HTTPS certificate '{name}' "
            + ("already existed" if existed else "created (self-signed)")
            + "; web management set to SSL and saved")

    # -- complete configuration file (EXPERIMENTAL) ---------------------------------------
    #   copy tftp startup-config <server> <file> unix   (from the manual of a sibling model)
    # then the switch restarts into the new startup configuration (by itself, or after
    # 'boot system flash primary', where any "save current configuration" question is
    # answered "n" so the file just loaded is not overwritten).
    def apply_configuration(self, config: str, mode: ApplyMode) -> OperationResult:
        if mode is not ApplyMode.REPLACE:
            return super().apply_configuration(config, mode)
        op = DeviceOperation.APPLY_CONFIGURATION
        if r := self._need(op):
            return r
        report = inspect_aos_switch_file(config)
        if report.file_type != "full_config":
            return OperationResult.failed(
                op, "Replace mode needs a complete ArubaOS-Switch configuration file")
        facts = self.get_device_facts()
        wanted = report.facts.get("product_number")
        have = facts.data.extra.get("product_number") if facts.ok else None
        if wanted and have and wanted.upper() != str(have).upper():
            return OperationResult.failed(
                op, f"The file was written for a {wanted}; this switch is a {have}. Loading "
                    "it here is refused.")
        files = self.file_server
        if files is None:
            return OperationResult.failed(op, "No file server is available for this job")
        client = self.target.management_address
        after = address_after_loading(config, client)
        name = f"undm-{hashlib.sha256(config.encode()).hexdigest()[:10]}.cfg"
        fd, tmp = tempfile.mkstemp(prefix="undm-config-", suffix=".cfg")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(config)
            server_ip = files.offer(Path(tmp), name, client)
            # A save question is answered "n" first: "y" would write the old running
            # configuration over the file just fetched (D-041). Other y/n questions: "y".
            talk = self._dialogue(
                f"copy tftp startup-config {server_ip} {name} unix",
                [(self._SAVE_QUESTION, "n"), (self._YES_NO, "y")],
                restarting=self._RESTARTING,
                timeout=self.transfer_timeout, idle_timeout=self.question_timeout,
                # Silence is expected only while the file is still being transferred. Once it
                # is complete, a switch that restarts may leave the session open but silent
                # (bench 2026-11-23): that silence ends the wait after question_timeout.
                patient=lambda _out: _transferring(files.last_transfer(name, client)))
            transfer = self._settled_transfer(name)
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
        diagnostics: dict[str, object] = {"device_output": talk.tail}
        answered = ", ".join(f'"{r}"' for r in talk.replies) or "nothing"
        notes = [f"switch output during the load (UNDM answered {answered}): "
                 + (talk.tail[-500:].replace("\r", "").strip() or "(none)")]
        if transfer is None:
            return OperationResult.failed(
                op, "The switch did not request the file from UNDM's TFTP server "
                    f"({talk.detail or 'it returned to the prompt'}). Its output is below.",
                diagnostics)
        if not transfer.completed:
            return OperationResult.failed(
                op, f"Transfer incomplete ({transfer.bytes_sent} of {transfer.size} bytes). "
                    "The switch was not restarted.", diagnostics)
        if talk.ended == "timeout" and re.search(r"[?:]\s*$", talk.unanswered):
            return OperationResult.failed(
                op, f"The switch fetched the file but did not finish ({talk.detail}); it may "
                    "be waiting for an answer UNDM does not give. Check it on the console.",
                diagnostics)
        how = "and restarted by itself"
        if talk.ended == "restarting":
            self.disconnect()
            how = "and is restarting (\"Rebooting switch\")"
        if talk.ended == "timeout":
            # Quiet after the complete transfer, no question, no prompt: restarting. The wait
            # for the switch and the checks after it (serial, hostname, lines) prove it.
            self.disconnect()
            how = "and is restarting (the session went quiet)"
        if talk.ended == "prompt":
            if re.search(self.error_pattern, talk.output):
                return OperationResult.failed(
                    op, "The switch fetched the file but reported an error (below). It was "
                        "not restarted.", diagnostics)
            # Independent evidence before restarting (D-031): the startup configuration
            # must now be the file. ('show config' shows the startup configuration.)
            wanted = parse_aos_switch_file(config).hostname
            if wanted:
                try:
                    startup = self._send("show config")
                except Exception as e:  # noqa: BLE001
                    return self._fail(op, e)
                if f'hostname "{wanted}"' not in startup:
                    return OperationResult.failed(
                        op, "The switch fetched the file and returned to its prompt, but its "
                            f"startup configuration does not contain it (no hostname "
                            f"\"{wanted}\" in 'show config'). It was not restarted; its "
                            "output is below.", diagnostics)
            how = "; UNDM restarted it"
            restart = self.reboot()  # answers "n" to any save question
            if not restart.ok:
                return OperationResult.failed(
                    op, f"The file is in the startup configuration, but the restart failed: "
                        f"{restart.message}", {**diagnostics, **restart.diagnostics})
        else:
            self._conn = None  # the switch closed the session to restart
        moved = ""
        if after and after != client:
            self.target = replace(self.target, management_address=after)
        where = where_after_loading(config, client)
        if where:
            # The file may put management on another port than the bootstrap did: say where
            # this PC must be connected while UNDM waits (bench 2026-11-23).
            moved = (f"; after the restart it answers at {where}, so this PC must be "
                     "connected there")
        return OperationResult.success(
            op, {"restarting": True, "address_after": after or client, "notes": notes},
            f"the switch fetched the file ({transfer.bytes_sent} bytes) into its startup "
            f"configuration {how}{moved}")

    def restart_notice(self, mode: ApplyMode) -> str | None:
        if mode is not ApplyMode.REPLACE:
            return None
        return ("loading the file: the switch fetches it from this PC and restarts with it. "
                "Expect 1-2 minutes without answers (bench: about 1 minute). Keep the switch "
                "powered and connected; UNDM continues by itself")

    def verify_configuration(self, intended: str, mode: ApplyMode) -> OperationResult | None:
        if mode is not ApplyMode.REPLACE:
            return None  # merge: the generic line check
        op = DeviceOperation.GET_FACTS
        facts = self.get_device_facts()
        if not facts.ok:
            return OperationResult.failed(op, f"Could not read the switch: {facts.message}")
        wanted = parse_aos_switch_file(intended).hostname
        if wanted and facts.data.hostname != wanted:
            return OperationResult.failed(
                op, f"After loading, the hostname is {facts.data.hostname}; the file sets "
                    f"{wanted}. The switch is not running the file: it may have refused it "
                    "while starting. Its console shows the reason during the start, and its "
                    "log afterwards ('show logging')")
        running = self.get_running_configuration()
        if not running.ok:
            return OperationResult.success(
                op, message=f"back after loading: hostname {facts.data.hostname}; read-back "
                            f"not available ({running.message})")
        expected = [ln for ln in self.expected_lines(intended) if not ln.startswith(";")]
        present = self.present_lines(str(running.data))
        missing = [ln for ln in expected if ln not in present]
        warnings = []
        if missing:
            # One line per distinct text, with a count: "no lacp" appears once per port.
            counts = Counter(missing)
            shown = [f"{ln} (x{n})" if n > 1 else ln for ln, n in counts.items()]
            warnings.append(
                f"{len(missing)} line(s) of the file are not shown in the running "
                "configuration (often settings the switch does not list because they are "
                "its defaults); review: " + "; ".join(shown[:20])
                + (f"; and {len(shown) - 20} more" if len(shown) > 20 else ""))
        return OperationResult.success(
            op, {"warnings": warnings},
            f"back after loading: hostname {facts.data.hostname}; "
            f"{len(expected) - len(missing)} of {len(expected)} lines of the file appear in "
            "the running configuration")

    def parse_facts(self, outputs: dict[str, str], prompt: str) -> DeviceFacts:
        # Layout verified against a real 2930F-48G-4SFP on WC.16.10.0025 (2026-11-19):
        # "show system" is two-column; "show modules" has
        # "Chassis: <model>  <product number>   Serial Number: <serial>".
        system = outputs.get("show system", "")
        modules = outputs.get("show modules", "")
        chassis = re.search(r"Chassis:\s*(\S+)(?:[ \t]+(?!Serial)(\S+))?", modules)
        return DeviceFacts(
            hostname=self._search(r"System Name\s*:\s*(\S+)", system) or prompt.rstrip("#> "),
            vendor="Aruba",
            model=chassis.group(1) if chassis else "unknown",
            os_version=self._search(r"Software revision\s*:\s*(\S+)", system) or "unknown",
            serial_number=self._search(r"Serial Number\s*:\s*(\S+)", system),
            extra={
                "product_number": chassis.group(2) if chassis and chassis.group(2) else None,
                "rom_version": self._search(r"ROM Version\s*:\s*(\S+)", system),
            },
        )


    # -- firmware (EXPERIMENTAL) ------------------------------------------------------
    # Commands as described in public write-ups of the ArubaOS-Switch CLI; the exact
    # wording of the switch's questions is NOT verified on hardware:
    #   copy tftp flash <server> <file> primary   -> image into the primary flash bank
    #   show flash                                -> version now held in primary
    #   boot system flash primary                 -> restart into it
    # The procedure only continues when UNDM's own TFTP server saw the switch fetch the
    # whole file AND "show flash" shows the expected version. An unknown question is
    # never answered; it ends the step with the switch's text.
    _YES_NO = r"\[y/n\]\??|\(y/n\)\??"
    # Printed by a 2930F on WC.16.10.0025 after taking a file (bench, 2026-11-23).
    _RESTARTING = r"Rebooting switch"
    _SAVE_QUESTION = r"save[^\n]*(?:\[y/n[^\]]*\]|\(y/n\))\??"
    transfer_timeout: ClassVar[float] = 2400.0   # whole copy, including the flash write
    question_timeout: ClassVar[float] = 60.0     # silence before the transfer starts
    reboot_quiet_timeout: ClassVar[float] = 20.0  # silence after the reboot is confirmed

    def get_firmware_information(self) -> OperationResult:
        op = DeviceOperation.GET_FIRMWARE_INFORMATION
        if r := self._need(op):
            return r
        try:
            system = self._send("show system")
            flash = self._send("show flash")
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        running = self._search(r"Software revision\s*:\s*(\S+)", system)
        if not running:
            return OperationResult.failed(op, "Could not read the running software revision")
        return OperationResult.success(op, {
            "running": running,
            "primary": self._search(r"Primary Image\s*:\s*\d+\s+\S+\s+(\S+)", flash),
            "secondary": self._search(r"Secondary Image\s*:\s*\d+\s+\S+\s+(\S+)", flash),
            "default_boot": self._search(r"Default Boot(?: Image)?\s*:\s*(\S+)", flash),
            "raw": {"show flash": flash[:2000]},
        })

    def stage_firmware(self, image: FirmwareImageRef) -> OperationResult:
        return self._copy_image(image, "primary", DeviceOperation.STAGE_FIRMWARE)

    def stage_firmware_secondary(self, image: FirmwareImageRef) -> OperationResult:
        # Same documented command as for primary, with the other image slot; the boot
        # choice (primary) is not changed. Run only after the primary is verified.
        return self._copy_image(image, "secondary", DeviceOperation.STAGE_FIRMWARE_SECONDARY)

    def _copy_image(self, image: FirmwareImageRef, slot: str,
                    op: DeviceOperation) -> OperationResult:
        if r := self._need(op):
            return r
        files = self.file_server
        if files is None:
            return OperationResult.failed(op, "No file server is available for this job")
        name = re.sub(r"[^A-Za-z0-9._-]", "_", image.filename)
        client = self.target.management_address
        try:
            server_ip = files.offer(Path(image.local_path), name, client)
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        before = files.last_transfer(name, client)  # e.g. the primary copy of the same file
        talk = self._dialogue(
            f"copy tftp flash {server_ip} {name} {slot}", [(self._YES_NO, "y")],
            timeout=self.transfer_timeout, idle_timeout=self.question_timeout,
            # Once the switch has asked for the file, silence is normal: it validates the
            # image and writes it to flash before the prompt returns.
            patient=lambda _output: files.last_transfer(name, client) not in (None, before))
        diagnostics: dict[str, object] = {"device_output": talk.tail}
        transfer = self._settled_transfer(name, since=before)
        if transfer is None:
            return OperationResult.failed(
                op, "The switch did not request the image from UNDM's TFTP server "
                    f"({talk.detail or 'it returned to the prompt'}). Check the switch output "
                    "below, this PC's firewall (inbound UDP 69) and the cabling/addresses.",
                diagnostics)
        if not transfer.completed:
            return OperationResult.failed(
                op, f"Transfer incomplete ({transfer.bytes_sent} of {transfer.size} bytes"
                    f"{': ' + transfer.error if transfer.error else ''}). The switch was not "
                    f"restarted; check 'show flash' ({slot} image) before doing anything else.",
                diagnostics)
        if talk.ended != "prompt":
            return OperationResult.failed(
                op, "The image was transferred, but the switch did not return to its prompt "
                    f"({talk.detail}). It may still be writing to flash: do not power it off; "
                    "check 'show flash' on the console.", diagnostics)
        info = self.get_firmware_information()
        found = str(info.data.get(slot) or "") if info.ok else ""
        if not found or compare(found, image.version) != 0:
            return OperationResult.failed(
                op, f"The image was transferred, but 'show flash' reports {slot} = "
                    f"{found or 'unknown'} instead of {image.version}. The switch was not "
                    "restarted.",
                {**diagnostics, "show_flash": info.data.get("raw") if info.ok else info.message})
        return OperationResult.success(
            op, {slot: found, "bytes": transfer.bytes_sent},
            f"{found} is in the {slot} flash ({transfer.bytes_sent} bytes transferred)")

    def install_firmware(self) -> OperationResult:
        return OperationResult.success(
            DeviceOperation.INSTALL_FIRMWARE,
            message="nothing to do: the image is activated by restarting into primary")

    def reboot(self) -> OperationResult:
        op = DeviceOperation.REBOOT
        if r := self._need(op):
            return r
        # Unsaved changes are not saved by a firmware job: answer "n" to a save question.
        talk = self._dialogue(
            "boot system flash primary", [(self._SAVE_QUESTION, "n"), (self._YES_NO, "y")],
            timeout=90, idle_timeout=self.reboot_quiet_timeout)
        diagnostics: dict[str, object] = {"device_output": talk.tail}
        if talk.ended == "prompt":
            self.disconnect()
            return OperationResult.failed(
                op, "The switch returned to its prompt instead of restarting", diagnostics)
        confirmed = "y" in talk.replies
        if talk.ended == "timeout" and not confirmed:
            self.disconnect()
            return OperationResult.failed(
                op, "The switch did not ask the expected question; nothing was confirmed "
                    f"({talk.detail})", diagnostics)
        self._conn = None  # the session is gone or about to go; do not reuse it
        how = "the switch closed the session" if talk.ended == "closed" else "no further output"
        return OperationResult.success(
            op, message=f"restart into the primary image started ({how})")


SSH_DRIVERS: tuple[type[SshCliDriver], ...] = (
    ArubaAOSCXSsh, ArubaOSSwitchSsh, BlackBoxLig1014aSsh, CiscoIOSXESsh, FortiOSSsh,
)
