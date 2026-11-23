"""Platform specifics for the SSH drivers. EXPERIMENTAL — see drivers/ssh/base.py."""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar

from undm.domain.operations import DeviceOperation
from undm.domain.versions import compare
from undm.drivers.aruba.config_files import (
    address_after_loading,
    inspect_aos_switch_file,
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
from undm.drivers.fortinet.fortios_ssh import FortiOSSsh
from undm.drivers.ssh.base import SSH_CAPABILITIES, SshCliDriver


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
        capabilities=SSH_CAPABILITIES | {Capability.FIRMWARE_UPGRADE, Capability.REBOOT,
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
            "from primary. Secondary copy not yet run on hardware.",
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
            talk = self._dialogue(
                f"copy tftp startup-config {server_ip} {name} unix", [(self._YES_NO, "y")],
                timeout=self.transfer_timeout, idle_timeout=self.question_timeout,
                patient=lambda out: files.last_transfer(name, client) is not None
                and not re.search(r"\?\s*$", out))
            transfer = self._settled_transfer(name)
        except Exception as e:  # noqa: BLE001
            return self._fail(op, e)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
        diagnostics: dict[str, object] = {"device_output": talk.tail}
        if transfer is None:
            return OperationResult.failed(
                op, "The switch did not request the file from UNDM's TFTP server "
                    f"({talk.detail or 'it returned to the prompt'}). Its output is below.",
                diagnostics)
        if not transfer.completed:
            return OperationResult.failed(
                op, f"Transfer incomplete ({transfer.bytes_sent} of {transfer.size} bytes). "
                    "The switch was not restarted.", diagnostics)
        if talk.ended == "timeout":
            return OperationResult.failed(
                op, f"The switch fetched the file but did not finish ({talk.detail}); it may "
                    "be waiting for an answer UNDM does not give. Check it on the console.",
                diagnostics)
        if talk.ended == "prompt":
            if re.search(self.error_pattern, talk.output):
                return OperationResult.failed(
                    op, "The switch fetched the file but reported an error (below). It was "
                        "not restarted.", diagnostics)
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
            moved = f"; it will answer at {after} (address set by the file)"
        return OperationResult.success(
            op, {"restarting": True, "address_after": after or client},
            f"the switch fetched the file ({transfer.bytes_sent} bytes) into its startup "
            f"configuration and is restarting{moved}")

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
                    f"{wanted}")
        running = self.get_running_configuration()
        if not running.ok:
            return OperationResult.success(
                op, message=f"back after loading: hostname {facts.data.hostname}; read-back "
                            f"not available ({running.message})")
        expected = [ln for ln in self.expected_lines(intended) if not ln.startswith(";")]
        present = self.present_lines(str(running.data))
        missing = [ln for ln in expected if ln not in present]
        return OperationResult.success(
            op, {"warnings": [f"not shown in the running configuration: {ln}"
                              for ln in missing[:10]]},
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
    ArubaAOSCXSsh, ArubaOSSwitchSsh, CiscoIOSXESsh, FortiOSSsh,
)
