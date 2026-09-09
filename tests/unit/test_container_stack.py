"""Unit tests validating Step 1.4 container stack skeleton and manifests."""

from pathlib import Path

import yaml  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = PROJECT_ROOT / "docker" / "docker-compose.yml"
DOCKERFILE_PATH = PROJECT_ROOT / "docker" / "Dockerfile"


def test_docker_compose_file_exists_and_parses() -> None:
    """Validate docker-compose.yml exists and contains valid YAML."""
    assert COMPOSE_PATH.is_file(), "docker/docker-compose.yml must exist"
    content = COMPOSE_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    assert isinstance(data, dict), "docker-compose.yml must parse to a dictionary"
    assert "services" in data, "Compose file must declare 'services'"


def test_docker_compose_services_declared() -> None:
    """Validate api, redis 7, and postgres 15 services in docker-compose.yml."""
    data = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    services = data["services"]

    # 1. API service definition
    assert "api" in services, "Service 'api' must be declared"
    api = services["api"]
    assert api["build"]["context"] == ".."
    assert api["build"]["dockerfile"] == "docker/Dockerfile"
    assert "8000:8000" in api["ports"]
    assert api.get("restart") == "unless-stopped"

    # 2. Redis 7 Alpine service definition
    assert "redis" in services, "Service 'redis' must be declared"
    redis = services["redis"]
    assert redis["image"] == "redis:7-alpine"
    assert "6379:6379" in redis["ports"]
    assert redis.get("restart") == "unless-stopped"

    # 3. PostgreSQL 15 Alpine service definition
    assert "postgres" in services, "Service 'postgres' must be declared"
    postgres = services["postgres"]
    assert postgres["image"] == "postgres:15-alpine"
    assert "5432:5432" in postgres["ports"]
    assert postgres.get("restart") == "unless-stopped"


def test_docker_compose_healthchecks_and_dependencies() -> None:
    """Validate healthchecks for database backends and dependency wiring on api."""
    data = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    services = data["services"]

    # Redis healthcheck
    redis_hc = services["redis"].get("healthcheck", {})
    assert "test" in redis_hc
    assert "redis-cli" in str(redis_hc["test"])

    # PostgreSQL healthcheck
    postgres_hc = services["postgres"].get("healthcheck", {})
    assert "test" in postgres_hc
    assert "pg_isready" in str(postgres_hc["test"])

    # API dependency on healthy backends
    api_deps = services["api"].get("depends_on", {})
    assert "redis" in api_deps
    assert api_deps["redis"].get("condition") == "service_healthy"
    assert "postgres" in api_deps
    assert api_deps["postgres"].get("condition") == "service_healthy"


def test_docker_compose_volumes_and_networks() -> None:
    """Validate persistent volume and isolated bridge network declarations."""
    data = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))

    # Named volume for postgres persistence
    assert "volumes" in data
    assert "postgres_data" in data["volumes"]

    pg_volumes = data["services"]["postgres"].get("volumes", [])
    assert any("postgres_data" in str(v) for v in pg_volumes)

    # Isolated bridge network
    assert "networks" in data
    assert "support_network" in data["networks"]
    for svc_name in ("api", "redis", "postgres"):
        svc_networks = data["services"][svc_name].get("networks", [])
        assert "support_network" in svc_networks


def test_docker_compose_environment_configuration() -> None:
    """Validate required production environment variables on api container."""
    data = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    env_vars = data["services"]["api"].get("environment", [])
    env_dict: dict[str, str] = {}
    for entry in env_vars:
        if "=" in entry:
            k, v = entry.split("=", 1)
            env_dict[k] = v

    assert env_dict.get("SUPPORT_AGENT_ENV") == "production"
    assert env_dict.get("LOG_LEVEL") == "INFO"
    assert "redis:6379" in env_dict.get("REDIS_URL", "")
    assert "postgres:5432" in env_dict.get("POSTGRES_DSN", "")
    assert "DEFAULT_TENANT_ID" in env_dict


def test_dockerfile_multi_stage_and_security_hardening() -> None:
    """Validate Dockerfile adheres to multi-stage non-root architecture (<250MB, UID 10001)."""
    assert DOCKERFILE_PATH.is_file(), "docker/Dockerfile must exist"
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")

    # Multi-stage build
    assert "FROM python:3.11-slim AS builder" in content
    assert "FROM python:3.11-slim AS runtime" in content

    # Non-root user with UID 10001
    assert "10001" in content
    assert "appuser" in content
    assert "USER 10001" in content

    # File ownership and port exposure
    assert "chown -R appuser:appgroup /app" in content
    assert "EXPOSE 8000" in content

    # Healthcheck and ASGI entrypoint
    assert "HEALTHCHECK" in content
    assert "/health" in content
    assert "uvicorn" in content
