"""Driver registry: maps driver identifiers to driver classes."""

from undm.drivers.base import Credentials, DeviceDriver, DeviceTarget, DriverInfo


class UnknownDriverError(KeyError):
    pass


class DriverRegistry:
    def __init__(self) -> None:
        self._drivers: dict[str, type[DeviceDriver]] = {}

    def register(self, driver_cls: type[DeviceDriver]) -> type[DeviceDriver]:
        driver_id = driver_cls.info.driver_id
        if driver_id in self._drivers:
            raise ValueError(f"Driver {driver_id} already registered")
        self._drivers[driver_id] = driver_cls
        return driver_cls

    def get(self, driver_id: str) -> type[DeviceDriver]:
        try:
            return self._drivers[driver_id]
        except KeyError:
            raise UnknownDriverError(driver_id) from None

    def create(
        self, driver_id: str, target: DeviceTarget, credentials: Credentials | None = None
    ) -> DeviceDriver:
        return self.get(driver_id)(target, credentials)

    def list(self) -> list[DriverInfo]:
        return [cls.info for cls in sorted(self._drivers.values(), key=lambda c: c.info.driver_id)]

    def __contains__(self, driver_id: object) -> bool:
        return driver_id in self._drivers


def default_registry() -> DriverRegistry:
    """Registry with all built-in drivers: simulations and experimental SSH drivers."""
    from undm.drivers.mock.drivers import MOCK_DRIVERS
    from undm.drivers.nokia.flexi import GUIDED_DRIVERS
    from undm.drivers.nokia.sar_console import CONSOLE_DRIVERS
    from undm.drivers.nokia.sar_ssh import NETWORK_DRIVERS
    from undm.drivers.ssh.platforms import SSH_DRIVERS

    registry = DriverRegistry()
    for cls in (*MOCK_DRIVERS, *SSH_DRIVERS, *CONSOLE_DRIVERS, *NETWORK_DRIVERS,
                *GUIDED_DRIVERS):
        registry.register(cls)
    return registry
