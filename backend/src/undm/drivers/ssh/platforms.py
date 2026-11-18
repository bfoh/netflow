"""Platform specifics for the SSH drivers. EXPERIMENTAL — see drivers/ssh/base.py."""

from __future__ import annotations

from undm.domain.operations import DeviceOperation
from undm.drivers.base import DeviceFacts, DriverInfo, DriverMaturity, OperationResult
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


SSH_DRIVERS: tuple[type[SshCliDriver], ...] = (ArubaAOSCXSsh, CiscoIOSXESsh, FortiOSSsh)
