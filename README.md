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

### Static Analysis & Quality Gates
```bash
make lint       # Ruff linter and formatter checks
make typecheck  # Mypy strict mode analysis (109 files)
make test       # Full pytest suite with >= 80% coverage check
```

### Service Execution

#### 1. FastAPI REST Ingress
```bash
make run-api    # Launch production Uvicorn server on port 8000
make dev        # Launch FastAPI in development reload mode
```

Query the API via `curl`:
```bash
# Healthcheck probe
curl http://localhost:8000/health

# Process customer support email
curl -X POST http://localhost:8000/agent/process \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: default" \
  -d '{
    "message_id": "MSG-001",
    "sender_email": "alice@example.com",
    "subject": "Status of CMD-10001",
    "body_text": "Hello, could you please give me an update on order CMD-10001?",
    "received_at": "2026-10-22T10:00:00Z"
  }'

# Inspect session snapshot
curl http://localhost:8000/agent/sessions/SESS-001 -H "X-Tenant-ID: default"
```

#### 2. Rich Terminal CLI Runner
```bash
# Interactive terminal wizard
make run-cli

# Process specific email payload file
.venv/bin/python -m src.cli run --file data/sample_emails/delivered_nominal.json

# Check order details in ERP
.venv/bin/python -m src.cli check-order CMD-10001
```

### Containerization & Docker Compose
```bash
make docker-build  # Multi-stage non-root container (< 250MB, UID 10001)
make docker-up     # Full stack (API + Redis 7 + PostgreSQL 15)
make docker-down   # Stop containers and purge networks
```

## Configuration Reference

Key environment variables configurable in `.env`:

| Variable | Default | Description |
|:---|:---|:---|
| `SUPPORT_AGENT_ENV` | `development` | Deployment environment (`development`, `staging`, `production`) |
| `OPENAI_API_KEY` | `""` | OpenAI API key for LLM client |
| `OPENAI_MODEL` | `gpt-4o-mini` | Target reasoning model |
| `API_PORT` | `8000` | Port for FastAPI ingress server |
| `API_KEY` | `None` | Optional shared secret for REST authentication |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL for session store and cache |
| `POSTGRES_DSN` | `postgresql://user:pass@localhost:5432/support_db` | PostgreSQL connection string for audit trail |
| `DEFAULT_TENANT_ID` | `default` | Default tenant identifier for multi-tenancy scoping |

