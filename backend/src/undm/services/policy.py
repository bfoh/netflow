"""Safety policy for real-device access, derived from settings.

Simulated devices are never restricted. For real devices:

- lab: read-only operations and dry runs allowed; configuration changes only
  if ``enable_real_device_writes``.
- firmware on real devices additionally needs ``enable_real_device_firmware``.
- production: read-only only if ``allow_production_read_only``; changes only if
  writes are enabled AND ``allow_production_deployments``.
"""

from __future__ import annotations

from dataclasses import dataclass

from undm.config import Settings
from undm.domain.enums import DeviceEnvironment


@dataclass(frozen=True)
class Policy:
    enable_real_device_writes: bool = False
    enable_real_device_firmware: bool = False
    allow_production_read_only: bool = False
    allow_production_deployments: bool = False
    require_separate_approver: bool = False

    @classmethod
    def from_settings(cls, s: Settings) -> Policy:
        return cls(
            enable_real_device_writes=s.enable_real_device_writes,
            enable_real_device_firmware=s.enable_real_device_firmware,
            allow_production_read_only=s.allow_production_read_only,
            allow_production_deployments=s.allow_production_deployments,
            require_separate_approver=s.require_separate_approver,
        )

    def read_problem(self, name: str, environment: str, simulated: bool) -> str | None:
        if simulated:
            return None
        production = environment == DeviceEnvironment.PRODUCTION.value
        if production and not self.allow_production_read_only:
            return (f"{name} is a production device; connecting to production devices is disabled "
                    "(UNDM_ALLOW_PRODUCTION_READ_ONLY=false)")
        return None

    def write_problem(self, name: str, environment: str, simulated: bool) -> str | None:
        if simulated:
            return None
        if environment == DeviceEnvironment.PRODUCTION.value and not (
            self.allow_production_deployments and self.enable_real_device_writes
        ):
            return (f"{name} is a production device; production deployments are disabled by "
                    "policy (UNDM_ALLOW_PRODUCTION_DEPLOYMENTS)")
        if not self.enable_real_device_writes:
            return (f"{name} is a real device; configuration changes to real devices are disabled "
                    "(set UNDM_ENABLE_REAL_DEVICE_WRITES=true to allow changes to lab devices). "
                    "Dry runs are allowed.")
        return None

    def firmware_problem(self, name: str, environment: str, simulated: bool) -> str | None:
        """Firmware on a real device needs the write switch and the firmware switch."""
        if simulated:
            return None
        problem = self.write_problem(name, environment, simulated)
        if problem:
            return problem
        if not self.enable_real_device_firmware:
            return (f"{name} is a real device; firmware changes to real devices are disabled "
                    "(set UNDM_ENABLE_REAL_DEVICE_FIRMWARE=true to allow them on lab devices). "
                    "Dry runs are allowed.")
        return None
