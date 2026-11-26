"""Nokia Flexi Multiradio 10 BBU (FSMF): staged by a person in its web portal (WebEM),
following UNDM's guided steps (D-113, D-117). EXPERIMENTAL.

UNDM does not log in to the BBU and changes nothing on it: no documented interface for
scripts is available to the team, and nothing may be invented (CLAUDE.md rule 2). The only
thing this driver does is a read-only check that something answers on the portal's port
(TCP 443) at the BBU's address on its LMP port; the steps themselves are recorded by
``undm.services.guided``.
"""

from __future__ import annotations

from typing import ClassVar

from undm.domain.operations import DeviceOperation
from undm.drivers.base import (
    Capability,
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
        capabilities=frozenset({Capability.GUIDED_STAGING}),
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="https (by hand)",
        notes=(
            "UNDM never logs in to the BBU: a person loads the software and the SCF in its "
            "portal (WebEM); UNDM hands out the files with their SHA-256 and records each "
            "step (D-117).",
            "Its only check is read-only: something answers on port 443 at its LMP address.",
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


GUIDED_DRIVERS: tuple[type[DeviceDriver], ...] = (NokiaFlexiGuided,)
