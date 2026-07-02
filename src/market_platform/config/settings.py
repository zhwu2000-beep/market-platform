"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "prod"]
DataProviderName = Literal["polygon", "twelve_data"]


class Settings(BaseSettings):
    """Runtime configuration for the application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = "dev"
    log_level: str = "INFO"
    default_data_provider: DataProviderName = "polygon"

    polygon_api_key: str = ""
    twelve_data_api_key: str = ""

    request_timeout_seconds: int = Field(default=30, ge=1)
    cache_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
