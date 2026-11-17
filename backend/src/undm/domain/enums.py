"""Vendor-neutral enumerations shared across subsystems."""

from enum import StrEnum


class DeviceCategory(StrEnum):
    SWITCH = "switch"
    ROUTER = "router"
    FIREWALL = "firewall"
    SERVER = "server"
    WIRELESS_CONTROLLER = "wireless_controller"
    ACCESS_POINT = "access_point"
    OTHER = "other"


class ManagementProtocol(StrEnum):
    SSH = "ssh"
    TELNET = "telnet"
    HTTPS_API = "https_api"
    NETCONF = "netconf"
    GNMI = "gnmi"
    SERIAL = "serial"


class ProvisioningStatus(StrEnum):
    """Where a device is in its onboarding life."""

    PLANNED = "planned"  # exists only in the design
    FACTORY_DEFAULT = "factory_default"  # known to be unconfigured
    BOOTSTRAPPED = "bootstrapped"  # reachable with minimal management config
    MANAGED = "managed"  # operational configuration deployed and verified
    DECOMMISSIONED = "decommissioned"


class DeviceDeploymentStatus(StrEnum):
    NEVER_DEPLOYED = "never_deployed"
    IN_SYNC = "in_sync"
    DRIFTED = "drifted"
    DEPLOYMENT_FAILED = "deployment_failed"
    UNKNOWN = "unknown"


class DeviceEnvironment(StrEnum):
    """Where a device lives. Shown prominently in the UI (directive 18)."""

    SIMULATED = "simulated"  # exists only in the UNDM simulation lab
    LAB = "lab"  # real hardware in an approved, isolated laboratory
    PRODUCTION = "production"  # real hardware carrying live traffic
