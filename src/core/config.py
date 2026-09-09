"""Centralized, type-safe application settings for 8_support_agent."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.exceptions import ConfigurationError


class Settings(BaseSettings):
    """Application configuration schema backed by pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    # Runtime Environment
    support_agent_env: str = Field(
        default="development",
        description="Runtime deployment environment (development, test, production)",
    )
    log_level: str = Field(
        default="INFO",
        description="Structured logging verbosity level",
    )
    api_host: str = Field(
        default="0.0.0.0",
        description="FastAPI ASGI server binding host",
    )
    api_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="FastAPI ASGI server listening port",
    )

    # Multi-Tenancy Isolation
    default_tenant_id: str = Field(
        default="default_tenant",
        description="Tenant identifier for multi-tenant data isolation",
    )

    # LLM Settings
    llm_provider: str = Field(
        default="openai",
        description="Upstream LLM API provider",
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="LLM model identifier for agent inference",
    )
    openai_api_key: str = Field(
        default="",
        description="API key for OpenAI / LLM provider authentication",
    )
    llm_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for deterministic generation",
    )
    llm_max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts on transient LLM failures",
    )

    # Agent Guardrails & Throttling
    agent_max_iterations: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Strict recursion ceiling for ReAct reasoning iterations",
    )
    confidence_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score required for autonomous resolution",
    )

    # Persistence & Caching
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for idempotency and session caching",
    )
    postgres_dsn: str = Field(
        default="postgresql://support_user:support_pass@localhost:5432/support_agent_db",
        description="PostgreSQL connection DSN for persistent audit trail",
    )
    cache_ttl_seconds: int = Field(
        default=900,
        ge=60,
        description="TTL duration in seconds for cached idempotency keys",
    )

    # Mock ERP File Path
    erp_data_path: Path = Field(
        default=Path("data/mock_orders.json"),
        description="Relative or absolute filesystem path to mock ERP database",
    )

    # Resilience & Retries
    retry_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Default maximum retry attempts for transient errors",
    )
    retry_min_wait_seconds: float = Field(
        default=1.0,
        ge=0.1,
        description="Minimum exponential backoff wait in seconds",
    )
    retry_max_wait_seconds: float = Field(
        default=10.0,
        ge=1.0,
        description="Maximum exponential backoff wait in seconds",
    )

    def __setattr__(self, name: str, value: object) -> None:
        """Shield immutability enforcement against raw third-party mutation errors."""
        try:
            super().__setattr__(name, value)
        except (ValidationError, TypeError) as exc:
            raise ConfigurationError(
                f"Cannot modify immutable settings attribute '{name}': {exc}"
            ) from exc

    @classmethod
    def load(cls, **values: object) -> "Settings":
        """Factory method creating Settings instance with exception shielding."""
        try:
            return cls(**values)  # type: ignore[arg-type]
        except (ValidationError, ValueError) as exc:
            raise ConfigurationError(
                f"Invalid application configuration: {exc}"
            ) from exc

    @property
    def is_production(self) -> bool:
        """Check whether the agent runs in production environment."""
        return self.support_agent_env.lower() in ("production", "prod")

    @property
    def is_development(self) -> bool:
        """Check whether the agent runs in development environment."""
        return self.support_agent_env.lower() in ("development", "dev")

    @property
    def is_testing(self) -> bool:
        """Check whether the agent runs in testing environment."""
        return self.support_agent_env.lower() in ("test", "testing")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve cached singleton settings instance with exception shielding."""
    try:
        return Settings()
    except (ValidationError, ValueError) as exc:
        raise ConfigurationError(
            f"Failed to load application configuration: {exc}"
        ) from exc
