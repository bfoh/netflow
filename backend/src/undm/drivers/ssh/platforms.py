"""Platform specifics for the SSH drivers. EXPERIMENTAL — see drivers/ssh/base.py."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

from undm.domain.operations import DeviceOperation
from undm.domain.versions import compare
from undm.drivers.base import (
    Capability,
    ConfigFileReport,
    DeviceFacts,
    DriverInfo,
    DriverMaturity,
    FirmwareImageRef,
    OperationResult,
)
from undm.drivers.fortinet.config_files import inspect_fortios_file
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


class FortiOSSsh(SshCliDriver):
    netmiko_device_type = "fortinet"
    facts_commands = ("get system status",)
    running_config_command = "show"
    info = DriverInfo(
        driver_id="ssh.fortinet.fortios",
        vendor="Fortinet",
        platform="fortios",
        os_family="FortiOS",
        description="FortiOS over SSH CLI (Netmiko 'fortinet'). Experimental, not lab-validated.",
        simulated=False,
        capabilities=SSH_CAPABILITIES,
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="ssh",
        notes=(
            "If console paging ('set output more') is on, Netmiko temporarily sets "
            "'config system console / set output standard' for the session and restores it on "
            "disconnect: a read-only session still makes this temporary change.",
            "Multi-VDOM devices are not supported yet.",
            "FortiOS commits each block on 'end'; saving relies on the default "
            "'cfg-save automatic' (not checked on the device).",
            "No automatic rollback: failures end in manual recovery from the stored backup.",
        ),
    )

    @classmethod
    def inspect_config_file(cls, text: str) -> ConfigFileReport | None:
        report = inspect_fortios_file(text)
        if report.file_type == "full_backup":
            return replace(report, blocked_reason=(
                "Restoring a full backup on a real FortiGate is not implemented yet. Sending "
                "it line by line would be wrong, so UNDM refuses to."))
        if report.file_type == "cli_script" and report.facts.get("vdom_mode") == "multi-vdom":
            return replace(report, blocked_reason=(
                "Running a multi-VDOM CLI script on a real FortiGate is not implemented yet "
                "(this driver cannot follow 'config global' / 'config vdom' or a hostname "
                "change during the run)."))
        return report

    def parse_facts(self, outputs: dict[str, str], prompt: str) -> DeviceFacts:
        text = outputs.get("get system status", "")
        version_line = self._search(r"^Version\s*:\s*(.+)$", text) or ""
        model, _, version = version_line.partition(" ")
        return DeviceFacts(
            hostname=self._search(r"^Hostname\s*:\s*(\S+)", text) or prompt.rstrip("#$ "),
            vendor="Fortinet",
            model=model or "unknown",
            os_version=version.split(",")[0] if version else "unknown",
            serial_number=self._search(r"^Serial-Number\s*:\s*(\S+)", text),
            extra={"vdom_mode": self._search(r"^Virtual domain configuration\s*:\s*(\S+)", text)},
        )

    def save_configuration(self) -> OperationResult:
        op = DeviceOperation.SAVE_CONFIGURATION
        if r := self._need(op):
            return r
        return OperationResult.success(
            op, message="FortiOS commits on 'end' (assumes default cfg-save automatic; "
                        "not checked)")


class ArubaOSSwitchSsh(SshCliDriver):
    """ArubaOS-Switch (formerly ProCurve), e.g. Aruba 2930F.

    Netmiko 'aruba_osswitch' (HPProcurveSSH) session behaviour, checked in its source:
    passes the 'Press any key to continue' banner, runs 'enable', then 'terminal width 511'
    and 'no page' for the session; on logout it answers 'no' to the save prompt.
    """

    netmiko_device_type = "aruba_osswitch"
    facts_commands = ("show system", "show modules")
    parser_validated_on = ("2930F-48G-4SFP (JL260A) WC.16.10.0025",)
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
        capabilities=SSH_CAPABILITIES | {Capability.FIRMWARE_UPGRADE, Capability.REBOOT},
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
            "then reboots into it ('boot system flash primary'). Not yet run on hardware; "
            "no automatic firmware rollback.",
        ),
    )

    def _connect_kwargs(self) -> dict[str, object]:
        assert self._credentials is not None
        return {"secret": self._credentials.password}

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
        op = DeviceOperation.STAGE_FIRMWARE
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
        talk = self._dialogue(
            f"copy tftp flash {server_ip} {name} primary", [(self._YES_NO, "y")],
            timeout=self.transfer_timeout, idle_timeout=self.question_timeout,
            # Once the switch has asked for the file, silence is normal: it validates the
            # image and writes it to flash before the prompt returns.
            patient=lambda: files.last_transfer(name, client) is not None)
        diagnostics: dict[str, object] = {"device_output": talk.tail}
        transfer = self._settled_transfer(name)
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
                    "restarted; check 'show flash' before doing anything else.", diagnostics)
        if talk.ended != "prompt":
            return OperationResult.failed(
                op, "The image was transferred, but the switch did not return to its prompt "
                    f"({talk.detail}). It may still be writing to flash: do not power it off; "
                    "check 'show flash' on the console.", diagnostics)
        info = self.get_firmware_information()
        primary = str(info.data.get("primary") or "") if info.ok else ""
        if not primary or compare(primary, image.version) != 0:
            return OperationResult.failed(
                op, "The image was transferred, but 'show flash' reports primary = "
                    f"{primary or 'unknown'} instead of {image.version}. The switch was not "
                    "restarted.",
                {**diagnostics, "show_flash": info.data.get("raw") if info.ok else info.message})
        return OperationResult.success(
            op, {"primary": primary, "bytes": transfer.bytes_sent},
            f"{primary} is in the primary flash ({transfer.bytes_sent} bytes transferred)")

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
