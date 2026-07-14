from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_prefix="MYCRM_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MyCRM API"
    app_version: str = "0.1.0"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "postgresql+asyncpg://mycrm:change-me@localhost:5432/mycrm"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
