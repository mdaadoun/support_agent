"""Unit tests verifying service main runner entrypoint."""

from unittest.mock import patch

import main as main_mod
from fastapi import FastAPI

from core.config import get_settings


def test_main_exports_app_and_factory() -> None:
    """Verify main exports app instance and create_app factory."""
    assert isinstance(main_mod.app, FastAPI)
    assert callable(main_mod.create_app)
    assert "app" in main_mod.__all__
    assert "create_app" in main_mod.__all__


def test_main_run_invokes_uvicorn() -> None:
    """Verify executing main runner invokes uvicorn.run with configured parameters."""
    with patch("uvicorn.run") as mock_run:
        settings = get_settings()
        mock_run(
            "src.main:app",
            host=settings.api_host,
            port=settings.api_port,
            reload=settings.support_agent_env == "development",
        )
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == "src.main:app"
        assert kwargs["host"] == settings.api_host
        assert kwargs["port"] == settings.api_port
