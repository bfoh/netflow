"""Device operations and their impact classification.

Informed by the TNDM reference workflow (see
docs/reference-analysis/tndm-screenshot-catalog.md, SC-03/SC-04), where
disruptive actions are hidden behind an explicit "enable impacting actions"
switch. UNDM makes impact a property of every operation so that the API, the
orchestrator and the UI apply the same rule.
"""

from enum import StrEnum


class Impact(StrEnum):
    READ_ONLY = "read_only"  # cannot change device state
    IMPACTING = "impacting"  # changes configuration, firmware, credentials or availability


class DeviceOperation(StrEnum):
    GET_FACTS = "get_facts"
    CHECK_REACHABILITY = "check_reachability"
    GET_RUNNING_CONFIGURATION = "get_running_configuration"
    BACKUP_CONFIGURATION = "backup_configuration"
    GET_FIRMWARE_INFORMATION = "get_firmware_information"
    APPLY_CONFIGURATION = "apply_configuration"
    SAVE_CONFIGURATION = "save_configuration"
    ROLLBACK_CONFIGURATION = "rollback_configuration"
    STAGE_FIRMWARE = "stage_firmware"
    INSTALL_FIRMWARE = "install_firmware"
    ROLLBACK_FIRMWARE = "rollback_firmware"
    REBOOT = "reboot"
    PROVISION_FACTORY_DEFAULT = "provision_factory_default"
    SET_CREDENTIALS = "set_credentials"
    CREATE_CHECKPOINT = "create_checkpoint"


IMPACT: dict[DeviceOperation, Impact] = {
    DeviceOperation.GET_FACTS: Impact.READ_ONLY,
    DeviceOperation.CHECK_REACHABILITY: Impact.READ_ONLY,
    DeviceOperation.GET_RUNNING_CONFIGURATION: Impact.READ_ONLY,
    DeviceOperation.BACKUP_CONFIGURATION: Impact.READ_ONLY,
    DeviceOperation.GET_FIRMWARE_INFORMATION: Impact.READ_ONLY,
    DeviceOperation.APPLY_CONFIGURATION: Impact.IMPACTING,
    DeviceOperation.SAVE_CONFIGURATION: Impact.IMPACTING,
    DeviceOperation.ROLLBACK_CONFIGURATION: Impact.IMPACTING,
    DeviceOperation.STAGE_FIRMWARE: Impact.IMPACTING,
    DeviceOperation.INSTALL_FIRMWARE: Impact.IMPACTING,
    DeviceOperation.ROLLBACK_FIRMWARE: Impact.IMPACTING,
    DeviceOperation.REBOOT: Impact.IMPACTING,
    DeviceOperation.PROVISION_FACTORY_DEFAULT: Impact.IMPACTING,
    DeviceOperation.SET_CREDENTIALS: Impact.IMPACTING,
    DeviceOperation.CREATE_CHECKPOINT: Impact.IMPACTING,
}


def impact_of(operation: DeviceOperation) -> Impact:
    return IMPACT[operation]


def is_impacting(operation: DeviceOperation) -> bool:
    return IMPACT[operation] is Impact.IMPACTING
