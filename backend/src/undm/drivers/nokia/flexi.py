"""Nokia Flexi Multiradio 10 BBU (FSMF): staged by a person in its web portal (WebEM),
following UNDM's guided steps (D-113, D-117). EXPERIMENTAL.

UNDM changes nothing on the BBU: no documented interface for scripts is available to the
team, and nothing may be invented (CLAUDE.md rule 2). The driver checks, read-only, that
something answers on the portal's port (TCP 443) at the BBU's address on its LMP port; the
steps themselves are recorded by ``undm.services.guided``.

To find a documented way in (D-130), it can also say which management services the unit
offers: SSH (22), its portal (443) and NETCONF over SSH (830), reading only what each
presents by itself, and, with a login a person chooses, the NETCONF <hello> (the
capabilities and YANG modules it announces). Neither changes anything.
"""

from __future__ import annotations

from typing import ClassVar

from undm.domain.operations import DeviceOperation
from undm.drivers import discovery
from undm.drivers.base import (
    Capability,
    Credentials,
    DeviceDriver,
    DriverInfo,
    DriverMaturity,
    OperationResult,
)
from undm.drivers.ssh.base import tcp_port_open

PORTAL_PORT = 443


class NokiaFlexiGuided(DeviceDriver):
    info: ClassVar[DriverInfo] = DriverInfo(
        driver_id="guided.nokia.flexi",
        vendor="Nokia",
        platform="flexi_sbts",
        os_family="SBTS (Flexi Multiradio 10)",
        description="Nokia Flexi Multiradio 10 BBU (FSMF), staged by hand in its portal "
                    "with UNDM's guided steps (experimental)",
        simulated=False,
        capabilities=frozenset({Capability.GUIDED_STAGING, Capability.SERVICE_DISCOVERY}),
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="https (by hand)",
        notes=(
            "UNDM never logs in to the BBU: a person loads the software and the SCF in its "
            "portal (WebEM); UNDM hands out the files with their SHA-256 and records each "
            "step (D-117).",
            "Its checks are read-only: something answers on port 443 at its LMP address, and "
            "which management services it offers (SSH, its portal, NETCONF), with the NETCONF "
            "<hello> read only with a login chosen by a person (D-130).",
        ),
    )
    guided_procedure: ClassVar[str | None] = "flexi_bbu"
    check_timeout: ClassVar[float] = 3.0

    def connect(self) -> OperationResult:
        address = self.target.management_address
        port = self.target.port or PORTAL_PORT
        if tcp_port_open(address, port, self.check_timeout):
            return OperationResult.success(
                DeviceOperation.CHECK_REACHABILITY,
                message=f"its portal answers on {address}:{port} (nothing was logged in to)")
        return OperationResult.failed(
            DeviceOperation.CHECK_REACHABILITY,
            f"No answer on {address}:{port}. Check that the LMP cable is in, that the BBU has "
            "finished starting, and that this PC has an address in the same network on that "
            "adapter (the team uses 192.168.255.126/24).")

    def discover_services(self) -> OperationResult:
        address = self.target.management_address
        ports = discovery.probe(address, discovery.MANAGEMENT_SERVICES, self.check_timeout)
        return OperationResult.success(
            DeviceOperation.DISCOVER_SERVICES,
            {"address": address, "ports": [vars(p) for p in ports], "simulated": False},
            message=f"{sum(p.open for p in ports)} of {len(ports)} management ports answer")

    def netconf_hello(self, credentials: Credentials) -> OperationResult:
        address = self.target.management_address
        try:
            hello = discovery.netconf_hello(address, discovery.NETCONF.port,
                                            credentials.username, credentials.password)
        except discovery.DiscoveryError as e:
            return OperationResult.failed(DeviceOperation.NETCONF_HELLO, str(e))
        return OperationResult.success(
            DeviceOperation.NETCONF_HELLO, {**hello.to_dict(), "simulated": False},
            message=f"It announces {len(hello.capabilities)} capabilities and "
                    f"{len(hello.modules)} YANG modules")


GUIDED_DRIVERS: tuple[type[DeviceDriver], ...] = (NokiaFlexiGuided,)
