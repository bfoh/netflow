"""Application settings (environment variables prefixed UNDM_)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UNDM_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://undm:undm@localhost:5432/undm"
    # Require a different person to approve a live deployment than the one who created it.
    require_separate_approver: bool = False
    # Simulated lab creates a factory-default device on first contact with an address.
    simulation_autocreate: bool = True
    # Real-device safety switches (see undm.services.policy). All off by default.
    enable_real_device_writes: bool = False
    # Firmware on real devices needs this switch in addition to the write switch.
    enable_real_device_firmware: bool = False
    # Firmware plans need an approver other than the creator. A single technician staging
    # new devices on an isolated bench may turn this off.
    firmware_require_separate_approver: bool = True
    # After a firmware reboot: how often and how long to wait for a real device.
    firmware_reboot_wait_attempts: int = 30
    firmware_reboot_wait_seconds: float = 20.0
    # TFTP server used only while a job needs devices to pull files from this PC.
    tftp_host: str = "0.0.0.0"  # noqa: S104 - files are restricted per client address
    tftp_port: int = 69
    allow_production_read_only: bool = False
    allow_production_deployments: bool = False
    # Where uploaded firmware images are stored.
    data_dir: str = "./undm-data"
    max_firmware_bytes: int = 4 * 1024**3
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
