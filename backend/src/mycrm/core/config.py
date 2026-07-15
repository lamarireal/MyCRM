from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
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
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "test"])
    enable_docs: bool = True
    secret_key: SecretStr = SecretStr("local-development-key-only")
    max_request_body_bytes: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    public_rate_limit_per_minute: int = Field(default=120, ge=1, le=10_000)
    demo_enabled: bool = False
    demo_read_only: bool = True
    demo_workspace_slug: str = "public-demo"
    registration_enabled: bool = False
    session_cookie_name: str = "mycrm_session"
    session_ttl_days: int = Field(default=14, ge=1, le=90)

    @field_validator("database_url", mode="before")
    @classmethod
    def use_async_postgresql_driver(cls, value: object) -> object:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if isinstance(value, str) and value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        return value

    @model_validator(mode="after")
    def validate_environment_safety(self) -> "Settings":
        if not self.is_production:
            return self

        errors: list[str] = []
        parsed_database_url = urlsplit(self.database_url)
        if not parsed_database_url.hostname or parsed_database_url.hostname in {
            "localhost",
            "127.0.0.1",
        }:
            errors.append("MYCRM_DATABASE_URL must point to a non-local production database")
        if "change-me" in self.database_url:
            errors.append("MYCRM_DATABASE_URL must not contain a fallback password")
        if len(self.secret_key.get_secret_value()) < 32:
            errors.append("MYCRM_SECRET_KEY must contain at least 32 characters")
        if not self.cors_origins or any(
            origin == "*" or not origin.startswith("https://") for origin in self.cors_origins
        ):
            errors.append("MYCRM_CORS_ORIGINS must contain only explicit HTTPS origins")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            errors.append("MYCRM_ALLOWED_HOSTS must contain explicit host names")

        if errors:
            raise ValueError("Unsafe production configuration: " + "; ".join(errors))
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
