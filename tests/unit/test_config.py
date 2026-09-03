"""Tests verifying centralized settings and configuration boundaries."""

from core.config import Settings, get_settings


def test_settings_defaults() -> None:
    """Validate default settings parameters."""
    settings = Settings()
    assert settings.agent_max_iterations == 3
    assert settings.confidence_threshold == 0.85
    assert settings.cache_ttl_seconds == 900
    assert settings.llm_model == "gpt-4o-mini"


def test_get_settings_cached_instance() -> None:
    """Validate get_settings returns singleton cached instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
