"""Unit tests asserting Step 1.2 centralized settings and configuration boundaries."""

import pytest
from pytest import MonkeyPatch

from core.config import Settings, get_settings
from core.exceptions import AppBaseError, ConfigurationError


def test_settings_defaults() -> None:
    """Validate default settings parameters and initial boundaries."""
    settings = Settings()

    # Runtime Environment
    assert settings.support_agent_env == "development"
    assert settings.log_level == "INFO"
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8000

    # Multi-Tenancy Isolation
    assert settings.default_tenant_id == "default_tenant"

    # LLM Inference
    assert settings.llm_provider == "openai"
    assert settings.llm_model == "gpt-4o-mini"
    assert settings.openai_api_key == ""
    assert settings.llm_temperature == 0.1
    assert settings.llm_max_retries == 3

    # Agent Guardrails & Throttling
    assert settings.agent_max_iterations == 3
    assert settings.confidence_threshold == 0.85

    # Persistence & Caching
    assert settings.redis_url == "redis://localhost:6379/0"
    assert (
        settings.postgres_dsn
        == "postgresql://support_user:support_pass@localhost:5432/support_agent_db"
    )
    assert settings.cache_ttl_seconds == 900

    # Resilience & Retries
    assert settings.retry_max_attempts == 3
    assert settings.retry_min_wait_seconds == 1.0
    assert settings.retry_max_wait_seconds == 10.0


def test_get_settings_cached_singleton() -> None:
    """Validate get_settings returns cached singleton instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_settings_immutability_enforcement() -> None:
    """Validate Settings instance is frozen and mutation raises ConfigurationError."""
    settings = Settings()

    with pytest.raises(ConfigurationError) as exc_info:
        settings.api_port = 9000

    assert issubclass(ConfigurationError, AppBaseError)
    assert exc_info.value.error_code == "CONFIGURATION_ERROR"
    assert "Cannot modify immutable settings attribute 'api_port'" in str(
        exc_info.value
    )


def test_settings_load_factory_valid_overrides() -> None:
    """Validate Settings.load factory correctly overrides configuration."""
    settings = Settings.load(
        agent_max_iterations=4,
        confidence_threshold=0.90,
        support_agent_env="production",
        default_tenant_id="tenant_alpha",
    )
    assert settings.agent_max_iterations == 4
    assert settings.confidence_threshold == 0.90
    assert settings.support_agent_env == "production"
    assert settings.default_tenant_id == "tenant_alpha"
    assert settings.is_production is True
    assert settings.is_development is False


def test_settings_load_factory_invalid_shielding() -> None:
    """Validate Settings.load shields validation errors into ConfigurationError."""
    # Test iteration bounds (1 to 5)
    with pytest.raises(ConfigurationError) as exc_info:
        Settings.load(agent_max_iterations=10)
    assert exc_info.value.error_code == "CONFIGURATION_ERROR"

    # Test confidence threshold bounds (0.0 to 1.0)
    with pytest.raises(ConfigurationError) as exc_info:
        Settings.load(confidence_threshold=1.5)
    assert exc_info.value.error_code == "CONFIGURATION_ERROR"

    # Test port bounds (1 to 65535)
    with pytest.raises(ConfigurationError) as exc_info:
        Settings.load(api_port=99999)
    assert exc_info.value.error_code == "CONFIGURATION_ERROR"


def test_get_settings_exception_shielding(monkeypatch: MonkeyPatch) -> None:
    """Validate get_settings shields invalid environment variables into ConfigurationError."""
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "99")
    get_settings.cache_clear()

    try:
        with pytest.raises(ConfigurationError) as exc_info:
            get_settings()
        assert issubclass(ConfigurationError, AppBaseError)
        assert exc_info.value.error_code == "CONFIGURATION_ERROR"
        assert "Failed to load application configuration" in str(exc_info.value)
    finally:
        get_settings.cache_clear()


def test_environment_variable_overrides(monkeypatch: MonkeyPatch) -> None:
    """Validate environment variables are prioritized during settings resolution."""
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "4")
    monkeypatch.setenv("SUPPORT_AGENT_ENV", "production")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.llm_model == "gpt-4o"
        assert settings.agent_max_iterations == 4
        assert settings.is_production is True
        assert settings.is_development is False
    finally:
        get_settings.cache_clear()


def test_environment_helper_properties() -> None:
    """Validate environment classification helper flags."""
    dev_settings = Settings.load(support_agent_env="development")
    assert dev_settings.is_development is True
    assert dev_settings.is_production is False
    assert dev_settings.is_testing is False

    prod_settings = Settings.load(support_agent_env="production")
    assert prod_settings.is_development is False
    assert prod_settings.is_production is True
    assert prod_settings.is_testing is False

    test_settings = Settings.load(support_agent_env="test")
    assert test_settings.is_development is False
    assert test_settings.is_production is False
    assert test_settings.is_testing is True
