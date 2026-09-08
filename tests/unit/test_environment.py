"""Unit tests asserting Step 1.1 dependency and environment configuration."""

import tomllib
from pathlib import Path

from core.exceptions import (
    AppBaseError,
    ConfigurationError,
    OrderNotFoundError,
    SecurityAccessError,
    SupportAgentBaseError,
    ToolExecutionError,
)


def test_pyproject_toml_configuration() -> None:
    """Validate pyproject.toml contains required Python version and tools config."""
    project_root = Path(__file__).resolve().parents[2]
    pyproject_path = project_root / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml must exist at project root"

    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    # 1. Python >= 3.11 constraint
    poetry_deps = data["tool"]["poetry"]["dependencies"]
    python_constraint = poetry_deps.get("python", "")
    assert "^3.11" in python_constraint or ">=3.11" in python_constraint

    # 2. Ruff linter & formatter rules (E, F, B, SIM, I)
    ruff_lint = data["tool"]["ruff"]["lint"]
    selected_rules = set(ruff_lint.get("select", []))
    for expected_rule in ("E", "F", "B", "SIM", "I"):
        assert (
            expected_rule in selected_rules
        ), f"Rule '{expected_rule}' must be configured in ruff select"

    # 3. Mypy strict mode
    mypy_config = data["tool"]["mypy"]
    assert mypy_config.get("strict") is True, "Mypy strict mode must be enabled"


def test_makefile_contains_required_targets() -> None:
    """Validate Makefile contains all required shortcuts from Step 1.1."""
    project_root = Path(__file__).resolve().parents[2]
    makefile_path = project_root / "Makefile"
    assert makefile_path.exists(), "Makefile must exist at project root"

    content = makefile_path.read_text(encoding="utf-8")
    required_targets = [
        "lint:",
        "typecheck:",
        "test:",
        "format:",
        "run-cli:",
        "run-api:",
    ]
    for target in required_targets:
        assert target in content, f"Makefile must declare target '{target}'"


def test_exception_hierarchy_and_app_base_error() -> None:
    """Validate exception taxonomy conforms to AppBaseError shielding rules."""
    assert issubclass(AppBaseError, Exception)
    assert AppBaseError is SupportAgentBaseError

    # Sub-exceptions must inherit from AppBaseError
    for exc_cls in (
        ConfigurationError,
        SecurityAccessError,
        ToolExecutionError,
        OrderNotFoundError,
    ):
        assert issubclass(
            exc_cls, AppBaseError
        ), f"{exc_cls.__name__} must inherit from AppBaseError"

    err = ConfigurationError("Config failed")
    assert err.error_code == "CONFIGURATION_ERROR"
    assert "Config failed" in str(err)
