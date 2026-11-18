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
