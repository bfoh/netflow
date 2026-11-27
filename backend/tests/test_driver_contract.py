"""Contract tests every registered driver must pass."""

import pytest

from undm.domain.operations import DeviceOperation
from undm.drivers.base import (
    REQUIRED_CAPABILITIES,
    ApplyMode,
    Capability,
    ConfigurationBackup,
    DeviceTarget,
    FirmwareImageRef,
    ResultStatus,
)
from undm.drivers.registry import DriverRegistry, UnknownDriverError, default_registry

REGISTRY = default_registry()
ALL_DRIVER_IDS = [d.driver_id for d in REGISTRY.list()]
# Behavioural contract against the simulated lab; SSH drivers: tests/test_ssh_drivers.py.
DRIVER_IDS = [d.driver_id for d in REGISTRY.list() if d.simulated]


def make(driver_id, addr="192.0.2.10"):
    return REGISTRY.create(driver_id, DeviceTarget("dev-1", addr))


def call(driver, op):
    backup = ConfigurationBackup("dev-1", "", "ckpt-x")
    return {
        DeviceOperation.BACKUP_CONFIGURATION: driver.backup_configuration,
        DeviceOperation.APPLY_CONFIGURATION:
            lambda: driver.apply_configuration("hostname x\n", ApplyMode.MERGE),
        DeviceOperation.ROLLBACK_CONFIGURATION: lambda: driver.rollback_configuration(backup),
        DeviceOperation.STAGE_FIRMWARE: lambda: driver.stage_firmware(
            FirmwareImageRef("1.2.3", "img.bin", "0" * 64, 1, "/nonexistent")),
        DeviceOperation.STAGE_FIRMWARE_SECONDARY: lambda: driver.stage_firmware_secondary(
            FirmwareImageRef("1.2.3", "img.bin", "0" * 64, 1, "/nonexistent")),
        DeviceOperation.INSTALL_FIRMWARE: driver.install_firmware,
        DeviceOperation.ROLLBACK_FIRMWARE: driver.rollback_firmware,
        DeviceOperation.REBOOT: driver.reboot,
        DeviceOperation.PROVISION_FACTORY_DEFAULT:
            lambda: driver.provision_factory_default_device("hostname x\n"),
        DeviceOperation.CREATE_CHECKPOINT: lambda: driver.create_checkpoint("x"),
        DeviceOperation.PING: lambda: driver.ping("192.0.2.10", 2),
        DeviceOperation.TRACEROUTE: lambda: driver.traceroute("192.0.2.10"),
    }[op]()


@pytest.mark.parametrize("driver_id", ALL_DRIVER_IDS)
def test_info_is_complete(driver_id):
    info = REGISTRY.get(driver_id).info
    assert info.vendor and info.platform and info.os_family and info.capabilities


@pytest.mark.parametrize("driver_id", DRIVER_IDS)
@pytest.mark.parametrize("op", sorted(REQUIRED_CAPABILITIES))
def test_missing_capability_yields_structured_unsupported(driver_id, op):
    d = make(driver_id)
    assert d.connect().ok
    result = call(d, op)
    if d.missing_capabilities(op):
        assert result.status is ResultStatus.UNSUPPORTED
    else:
        assert result.status is not ResultStatus.UNSUPPORTED


@pytest.mark.parametrize("driver_id", DRIVER_IDS)
def test_operations_fail_cleanly_when_not_connected(driver_id):
    d = make(driver_id)
    r = d.get_running_configuration()
    assert r.status is ResultStatus.FAILED and "Not connected" in r.message


@pytest.mark.parametrize("driver_id", DRIVER_IDS)
def test_apply_then_read_back(driver_id):
    d = make(driver_id)
    d.connect()
    if Capability.GUIDED_STAGING in d.capabilities():
        # Staged by a person in its own portal (D-117): UNDM never changes it.
        assert d.apply_configuration("hostname abc\n", ApplyMode.MERGE).status \
            is ResultStatus.UNSUPPORTED
        return
    assert d.apply_configuration("hostname abc\n", ApplyMode.MERGE).ok
    assert "hostname abc" in d.get_running_configuration().data
    assert d.get_device_facts().data.hostname == "abc"


def test_registry_rejects_duplicates_and_unknown():
    reg = DriverRegistry()
    cls = REGISTRY.get(DRIVER_IDS[0])
    reg.register(cls)
    with pytest.raises(ValueError):
        reg.register(cls)
    with pytest.raises(UnknownDriverError):
        reg.get("nope")
