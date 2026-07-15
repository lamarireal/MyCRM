import pytest
from pydantic import ValidationError

from mycrm.core.config import Settings


def test_render_database_url_is_normalized_for_asyncpg() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:password@database.internal/mycrm",
    )

    assert settings.database_url == "postgresql+asyncpg://user:password@database.internal/mycrm"


def test_production_rejects_fallback_configuration() -> None:
    with pytest.raises(ValidationError, match="Unsafe production configuration"):
        Settings(_env_file=None, app_env="production")


def test_production_accepts_explicit_secure_configuration() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql://mycrm:strong-password@database.internal/mycrm",
        secret_key="a-secure-random-value-with-more-than-32-characters",
        cors_origins=["https://crm.example.com"],
        allowed_hosts=["api.crm.example.com"],
    )

    assert settings.is_production
