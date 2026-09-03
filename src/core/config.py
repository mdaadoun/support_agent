"""Centralized, type-safe application settings for 8_support_agent."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration schema backed by pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Runtime Environment
    support_agent_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    # LLM Settings
    llm_provider: str = Field(default="openai")
    llm_model: str = Field(default="gpt-4o-mini")
    openai_api_key: str = Field(default="")
    llm_temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    llm_max_retries: int = Field(default=3, ge=1, le=10)

    # Agent Guardrails
    agent_max_iterations: int = Field(default=3, ge=1, le=5)
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)

    # Persistence & Caching
    redis_url: str = Field(default="redis://localhost:6379/0")
    postgres_dsn: str = Field(
        default="postgresql://support_user:support_pass@localhost:5432/support_agent_db"
    )
    cache_ttl_seconds: int = Field(default=900, ge=60)

    # Mock ERP File Path
    erp_data_path: Path = Field(default=Path("data/mock_orders.json"))

    # Resilience & Retries
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_min_wait_seconds: float = Field(default=1.0, ge=0.1)
    retry_max_wait_seconds: float = Field(default=10.0, ge=1.0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve cached singleton settings instance."""
    return Settings()
