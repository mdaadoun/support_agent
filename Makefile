# ==============================================================================
# Makefile — Customer Support Automation Agent (8_support_agent)
# ==============================================================================

.DEFAULT_GOAL := help

.PHONY: help install clean lint format typecheck test run-cli run-api dev docker-build docker-up docker-down

BIN := $(shell if [ -d ".venv/bin" ]; then echo ".venv/bin/"; else echo ""; fi)
POETRY := $(shell command -v poetry 2> /dev/null)
export PYTHONPATH := src:.


help:
	@echo "======================================================================"
	@echo "   8_support_agent — Customer Support Automation Agent"
	@echo "======================================================================"
	@echo "  make install      - Install dependencies & pre-commit hooks."
	@echo "  make clean        - Purge cache & temporary artifacts."
	@echo "  make lint         - Run Ruff static analysis & format checks."
	@echo "  make typecheck    - Run Mypy strict type analysis."
	@echo "  make format       - Auto-format source code with Ruff."
	@echo "  make test         - Run full pytest test suite."
	@echo "  make run-cli      - Run Typer/Rich CLI interface."
	@echo "  make run-api      - Run FastAPI server via Uvicorn."
	@echo "  make dev          - Start FastAPI dev server with auto-reload."
	@echo "  make docker-build - Build production Docker container."
	@echo "  make docker-up    - Start full stack (API + Redis + PostgreSQL)."
	@echo "  make docker-down  - Stop full stack containers."
	@echo "======================================================================"

install:
	@if [ -d ".venv/bin" ]; then $(BIN)pip install -e .; elif [ -n "$(POETRY)" ]; then poetry install; else pip install -e .; fi

clean:
	@echo "Cleaning cache directories and temporary files..."
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

lint:
	@echo "--- [1/2] Static analysis (Ruff) ---"
	@$(BIN)ruff check .
	@echo "--- [2/2] Code formatting check (Ruff Format) ---"
	@$(BIN)ruff format --check .

typecheck:
	@echo "--- Strict type check (Mypy) ---"
	@$(BIN)mypy src/ tests/

format:
	@echo "--- Auto-formatting source code (Ruff) ---"
	@$(BIN)ruff format .
	@$(BIN)ruff check --fix .

test:
	@$(BIN)pytest

run-cli:
	@$(BIN)python -m src.cli --help

run-api:
	@$(BIN)uvicorn src.api.app:app --host 0.0.0.0 --port 8000

dev:
	@$(BIN)uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

docker-build:
	docker build -f docker/Dockerfile -t support-agent:latest .

docker-up:
	docker compose -f docker/docker-compose.yml up -d

docker-down:
	docker compose -f docker/docker-compose.yml down
