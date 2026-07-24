"""
Configuration management for FitGenie AI backend.

All configuration is loaded from environment variables (via python-dotenv
locally, or injected directly by the platform in production e.g. AWS App
Runner / Secrets Manager). Nothing sensitive is hardcoded.

Usage:
    from app.config import get_settings
    settings = get_settings()
"""

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings, sourced from environment vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App metadata ---
    app_name: str = Field(default="FitGenie AI Backend")
    app_env: str = Field(default="development")  # development | staging | production
    app_version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)

    # --- Server ---
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # --- CORS ---
    # Comma-separated list of allowed origins, e.g.
    # "http://localhost:5500,https://app.fitgenie.ai"
    allowed_origins: str = Field(default="http://localhost:5500")

    # --- Gemini (Google GenAI SDK) ---
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-3.5-flash")
    gemini_chat_model: str = Field(default="gemini-3.5-flash")
    gemini_temperature_plan: float = Field(default=0.4)
    gemini_temperature_chat: float = Field(default=0.6)
    gemini_max_tokens_plan: int = Field(default=4096)
    gemini_max_tokens_chat: int = Field(default=1024)
    gemini_request_timeout: int = Field(default=60)

    # --- Logging ---
    log_level: str = Field(default="INFO")

    @field_validator("gemini_api_key")
    @classmethod
    def warn_if_missing_key(cls, v: str) -> str:
        # We intentionally do not raise here so the app can still boot
        # (e.g. for /api/health checks in CI) — routers that need the key
        # will raise a clear, friendly error at request time instead.
        return v

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — env is read once per process."""
    return Settings()
