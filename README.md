# 8_support_agent: Customer Support Automation Agent

Autonomous Tier-1 customer support automation agent with deterministic statutory business rules, ReAct FSM execution loop, and Model Context Protocol (MCP) tool runtime.

## Architectural Overview

The agent enforces a strict 4-layer decoupled architecture:
1. **Presentation Layer (`src/api/`, `src/cli.py`):** FastAPI REST endpoints (`/health`, `/agent/process`) and Typer/Rich CLI interface.
2. **Core Domain & Agent Layer (`src/agent/`, `src/domain/`, `src/models/`, `src/security/`):** ReAct FSM state machine ($N_{max}=3$), 14-day statutory cooling-off calculator, express delivery delay voucher engine, input XML encapsulation (`<user_email>`), and customer PII access guard.
3. **Infrastructure & Tool Runtime (`src/tools/`, `src/clients/`, `src/observability/`):** MCP tool interface and registry, ERP mock client with Tenacity exponential retry, structlog JSON logging, and FinOps cost estimation.
4. **Data & Persistence Layer (`src/persistence/`, `data/`):** Session state, SHA-256 idempotency cache (Redis / in-memory), and audit log trail repository (PostgreSQL / JSON Lines).

## Quick Start

### Installation & Environment Setup
```bash
make install
```

### Static Analysis & Type Checking
```bash
make lint       # Ruff linter and formatter checks
make typecheck  # Mypy strict mode analysis
```

### Automated Testing
```bash
make test       # Pytest execution
```

### Service Execution
```bash
make run-cli    # CLI help and interactive runner
make run-api    # Launch FastAPI server on port 8000
make dev        # Launch FastAPI in development reload mode
```

### Containerization
```bash
make docker-build  # Multi-stage non-root container (< 250MB)
make docker-up     # Full stack (API + Redis + PostgreSQL)
make docker-down   # Stop containers
```
