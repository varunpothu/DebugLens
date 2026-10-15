"""Typed configuration with safe local defaults."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DebugLens"
    app_env: str = "local"
    log_level: str = "INFO"
    analysis_provider: str = "mock"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    allowed_origins: str = "http://localhost:8501,http://127.0.0.1:8501"
    vision_api_key: str = ""
    vision_model: str = ""
    vision_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    vision_timeout_seconds: float = Field(default=45.0, ge=1.0, le=120.0)
    database_path: str = "./data/debuglens.db"
    api_access_token: str = ""
    browser_enabled: bool = False
    browser_allowed_hosts: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_browser_hosts(self) -> set[str]:
        return {host.strip().lower().rstrip(".") for host in self.browser_allowed_hosts.split(",") if host.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings; clear the cache in tests when changing environment."""
    return Settings()
