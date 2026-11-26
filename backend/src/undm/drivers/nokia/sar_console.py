"""Nokia 7705 SAR-Hmc: reached over its console cable only. EXPERIMENTAL.

The unit has no management address from the factory, and the team stages it entirely over
the console. For now UNDM's only procedure for it is the first access
(``undm.provisioning.sros_sar``, D-112), run from Console setup. Every operation of the
driver contract is therefore unsupported here; loading its configuration over the console
as a plan is the next step and is not built yet.
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


class NokiaSarConsole(DeviceDriver):
    info: ClassVar[DriverInfo] = DriverInfo(
        driver_id="console.nokia.sar",
        vendor="Nokia",
        platform="sros_sar",
        os_family="SR OS (7705 SAR)",
        description="Nokia 7705 SAR-Hmc over its console cable (experimental): first access "
                    "only for now",
        simulated=False,
        capabilities=frozenset({Capability.SERIAL_CONSOLE}),
        maturity=DriverMaturity.EXPERIMENTAL,
        transport="console",
        notes=(
            "Console cable only: the unit has no management address from the factory.",
            "First access (Console setup) follows the team's console recording of "
            "2026-11-26 on TiMOS 20.5.R1; not yet run by UNDM on hardware.",
            "No network test, backup or configuration load yet.",
        ),
    )

    def connect(self) -> OperationResult:
        return OperationResult.unsupported(
            DeviceOperation.CHECK_REACHABILITY,
            "This device is reached over its console cable only: use Console setup. UNDM "
            "has no network test for it.")


CONSOLE_DRIVERS: tuple[type[DeviceDriver], ...] = (NokiaSarConsole,)
