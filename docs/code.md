# Codebase Structure & Educational Deep-Dive

> **Overview:** Educational reference guide for the `8_support_agent` architecture, directory layout, module contracts, and execution pipelines.

---

## 🛠️ 1. Directory Structure: `src/`

- **`cli.py`:** Presentation entrypoint powered by Typer and Rich. Exposes operational inspection and execution commands (`info`, `check-order`, `run`).
- **`api/`:** REST Ingress layer built on FastAPI (`app.py`, `routes.py`). Exposes endpoints (`/agent/process`, `/health`) with dependency injection and middleware.
- **`core/`:** Foundation services and boundary protection:
  - **`config.py`:** Centralized settings management backed by `pydantic-settings` (`Settings`).
  - **`exceptions.py`:** Standardized domain exception hierarchy rooted in `AppBaseError` (`SupportAgentBaseError`).
  - **`retry.py`:** Tenacity-decorated retry policies with exponential backoff and jitter.
- **`models/`:** Strictly typed, immutable Pydantic V2 DTOs (`frozen=True, extra="forbid"`):
  - **`base.py`:** `BaseDTO` enforcing immutability and zero payload field drift.
  - **`enums.py`:** Domain enumerations (`OrderStatusEnum`, `IntentEnum`, `RefundReasonCode`).
  - **`email.py`:** `InboundEmailMessage` with email syntax validation.
  - **`extraction.py`:** `ExtractedDemand` entity with regex order validation.
  - **`tools.py`:** Standardized execution payloads (`OrderDetailsResult`, `ToolExecutionResult`).
  - **`response.py`:** Certified agent response contract (`AgentFinalResponse`).
- **`domain/`:** Pure deterministic business rules:
  - **`business_rules.py`:** 14-day statutory cooling-off arithmetic and delivery delay voucher computation (zero LLM financial authority).
- **`agent/`:** Autonomous orchestration engine:
  - **`controller.py`:** Finite State Machine (FSM) enforcing valid lifecycle transitions.
  - **`loop.py`:** ReAct decision-action loop capped at 3 iterations.
  - **`prompts.py`:** XML boundary encapsulation and prompt boundary definitions.
  - **`state.py`:** Session state and trajectory models.
- **`security/`:** Defense-in-depth and isolation:
  - **`sanitizer.py`:** `<user_email>` XML delimiter tagging and prompt injection detection.
  - **`access_control.py`:** Cross-authorization email matching to prevent PII leakage.
- **`tools/`:** MCP-compliant tool runtime:
  - **`base.py`:** `ToolInterface` protocol with exception shielding wrapper.
  - **`registry.py`:** Tool catalog, schema validator, and MCP specification exporter.
  - **`order_status.py` / `refund_calculator.py` / `delay_calculator.py`:** Concrete domain tools.
- **`clients/`:** Upstream client adapters:
  - **`erp_client.py`:** Mock ERP store accessor with Tenacity retry policies.
  - **`llm_client.py`:** LiteLLM / AsyncOpenAI client with structured output validation.
- **`persistence/`:** State and audit logging:
  - **`cache.py`:** Redis idempotency key caching (SHA-256) and TTL management.
  - **`repository.py`:** PostgreSQL audit log repository with JSON Lines fallback.
- **`observability/`:** Telemetry and metrics:
  - **`logger.py`:** Structured JSON logging via `structlog`.
  - **`cost_tracker.py`:** FinOps token usage counter and USD cost estimator.
  - **`tracer.py`:** OpenTelemetry / Langfuse instrumentation spans.

---

## 📦 2. Manifest, Tooling & Automation

- **`pyproject.toml`:** Declares Poetry project metadata, runtime dependencies (`fastapi`, `pydantic-settings`, `typer`, `rich`, `structlog`, `tenacity`), and strict tool configurations (`ruff`, `mypy`).
- **`Makefile`:** Standardized developer command shortcuts routing to virtualenv binaries:
  - `make lint`: Executes Ruff static analysis (`ruff check .`) and formatting checks (`ruff format --check .`).
  - `make typecheck`: Runs Mypy in strict mode across `src/` and `tests/`.
  - `make test`: Runs Pytest test suite with coverage tracking.
  - `make format`: Automatically fixes lint issues and formats code.
  - `make run-cli`: Launches the Typer/Rich CLI interface.
  - `make run-api`: Starts the FastAPI server via Uvicorn.
- **`ruff.toml`:** Dedicated Ruff configuration enforcing rule sets `E`, `F`, `B`, `SIM`, `I` with Python 3.11 target.
- **`docker/`:** Container orchestration manifests (`Dockerfile`, `docker-compose.yml`) defining isolated runtime environments.

---

## 🔄 3. Key Function & Data Flow Summary

### Developer Workflow Dispatch (`Makefile`)
```text
Makefile Target ──► .venv/bin/ Tool ──► Source Code (src/, tests/) ──► Quality Report
```
The `Makefile` inspects `.venv/bin` and exports `PYTHONPATH=src:.` ensuring consistent command execution across both local environments and CI pipelines.

### Exception Shielding Flow (`src/core/exceptions.py`)
```text
Third-Party Exception (e.g., HTTPError)
            │
            ▼
Catch & Shield at Infrastructure Boundary
            │
            ▼
Wrap into AppBaseError derivative (e.g., OrderNotFoundError)
            │
            ▼
FSM Controller / API Layer (Safe Handling & Error Code Dispatch)
```
All system exceptions derive from `AppBaseError` (aliasing `SupportAgentBaseError`). Upstream library exceptions never cross layer boundaries unwrapped, ensuring the "Zero Naked Crash" guarantee.

### Centralized Settings Resolution Flow (`src/core/config.py`)
```text
Environment (.env / OS ENV)
            │
            ▼
Settings Schema Validation (pydantic-settings BaseSettings)
            │
            ▼
Immutability & Boundary Enforcement (frozen=True)
            │
            ▼
get_settings() [LRU Cache Singleton] ──► Presentation, Agent, Tool, and Persistence Layers
```
The centralized configuration pipeline parses runtime environment variables, enforces immutable type safety via `SettingsConfigDict(frozen=True)`, and caches the singleton `Settings` instance for $O(1)$ amortized access across all modules.

### Mock ERP Seed Data Flow (`src/clients/erp_client.py` & `data/mock_orders.json`)
```text
data/mock_orders.json (Multi-tenant Seed Data with tenant_id)
            │
            ▼
MockERPClient._read_orders_raw()
            │
            ▼
Tenacity Retry Wrapper (2 attempts with exponential backoff)
            │
            ▼
Order Lookup by ID (CMD-XXXXX) ──[Not Found]──► OrderNotFoundError (AppBaseError)
            │
            ▼ [Found]
Raw Order Dictionary ──► Domain Rules & Tool Execution Adapters
```
The mock ERP store decouples agent development from live backend dependencies. Orders are loaded and validated against the schema, with automated retries and exception shielding translating missing records into domain-level `OrderNotFoundError`.

### Container Stack Lifecycle & Orchestration Flow (`docker/`)
```text
docker compose up
        │
        ├──► Redis Container (redis:7-alpine) ──► Healthcheck: redis-cli ping
        │                                                │
        ├──► Postgres Container (postgres:15-alpine) ──► Healthcheck: pg_isready
        │                                                │
        ▼                                                ▼
Backend Health Verified (condition: service_healthy) ◄───┘
        │
        ▼
FastAPI API Container (UID 10001, port 8000, multi-stage runtime)
        │
        ├──► Isolated Bridge: support_network
        └──► Persistent Volume: postgres_data
```
The container orchestration architecture guarantees deterministic system startup: the FastAPI API service remains held until Redis and PostgreSQL healthchecks pass, preventing transient socket initialization failures.
