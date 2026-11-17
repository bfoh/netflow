"""Consistency rules between a device's driver and its environment."""

from undm.domain.enums import DeviceEnvironment
from undm.drivers.registry import DriverRegistry


def environment_problem(driver_id: str, environment: str, registry: DriverRegistry) -> str | None:
    simulated_driver = registry.get(driver_id).info.simulated
    if simulated_driver and environment != DeviceEnvironment.SIMULATED.value:
        return (f"Driver {driver_id} is a simulation; the device environment must be "
                "'simulated' so it is never mistaken for real equipment")
    if not simulated_driver and environment == DeviceEnvironment.SIMULATED.value:
        return f"Driver {driver_id} talks to real equipment; environment cannot be 'simulated'"
    return None
