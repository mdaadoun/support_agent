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

### Exception Shielding & Safe Error Propagation Flow (`src/core/exceptions.py`)
```text
Upstream Failure (HTTP/DB/FSM) ──► Exception Boundary Shield (try/except) ──► Wrap into AppBaseError Subclass ──► FSM Controller Transition (REQUIRES_HUMAN) ──► Structured JSON Log & Clean API Egress
```
1. An upstream infrastructure operation (e.g. ERP HTTP call, Redis session lookup) encounters a failure.
2. The infrastructure adapter catches the raw third-party exception (e.g., `ConnectionError`, `HTTPStatusError`) at the module boundary.
3. The adapter maps and raises a domain-specific subclass of `AppBaseError` (e.g., `CircuitBreakerError`, `OrderNotFoundError`) with cause chaining (`from exc`) and typed metadata attributes.
4. The agent FSM controller catches `AppBaseError` at the orchestration boundary, preventing unhandled crashes.
5. The FSM transitions to `REQUIRES_HUMAN` or `FAILED`, emitting a structured `AgentFinalResponse` and logging structured JSON events without exposing raw internal stack traces.

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

### BaseDTO & Domain Enums Boundary Ingress Flow (`src/models/base.py` & `src/models/enums.py`)
```text
Raw Inbound Data / Tool Output Dict
            │
            ▼
Pydantic V2 Validation (BaseDTO)
            │
            ▼
Type Coercion & Enum Checking (StrEnum)
            │
            ▼
Immutable DTO (frozen=True, extra="forbid")
            │
            ▼
Domain Business Rules & ReAct Agent Loop
```
External inputs (inbound email payloads, ERP responses, tool results) arrive as untrusted dictionaries or raw JSON strings. Deserialization into models subclassing `BaseDTO` triggers Pydantic V2 Rust core validation. Fields typed with `OrderStatusEnum`, `IntentEnum`, `RefundReasonCode`, or `ResolutionStatusEnum` strictly validate string values against declared enum members, rejecting invalid states with `ValidationError`. Disallowed extra attributes immediately trigger `ValidationError` due to `extra="forbid"`. The resulting immutable, hashable DTO instances flow safely into pure domain business logic and agent state machines with zero risk of mutation or contract drift.

### Inbound Email Ingestion & Pre-Extraction Flow (`src/models/email.py` & `src/models/extraction.py`)
```text
Raw Inbound Payload
        │
        ▼
InboundEmailMessage (EmailStr, min_length)
        │
        ▼
Input Sanitizer & Pre-Extractor
        │
        ▼
ExtractedDemand (^CMD-[0-9]{5,8}$, IntentEnum, tuple sub_queries)
        │
        ▼
PII Access Guard & FSM Controller
```
1. External email payloads enter through presentation ingress (FastAPI or CLI) and are parsed into `InboundEmailMessage`, which validates message ID, sender email syntax, and non-empty content constraints.
2. The sanitized email body passes to the Pre-Extraction engine to detect customer intent and regex order IDs.
3. The result is instantiated as `ExtractedDemand`, enforcing valid `IntentEnum` values, regex compliance (`^CMD-[0-9]{5,8}$`), and immutable `tuple[str, ...]` sub-queries.
4. The validated `ExtractedDemand` is forwarded to the PII Access Controller and FSM Controller to guide tool execution or human escalation without risk of payload tampering.

### ReAct Tool Invocation, Shielded Execution & Audit Tracing Flow (`src/models/tools.py`)
```text
Agent Loop (Tool Call)
        │
        ▼
Tool Registry (Schema Validation)
        │
        ▼
Concrete Tool Adapter (OrderStatus / Refund / Delay)
        │
        ▼
Domain Rules / Mock ERP Client
        │
        ▼
ToolExecutionResult (success=bool, data/error)
        │
        ▼
ToolCallTrace (id, name, args, result, timestamp, duration_ms)
        │
        ▼
Agent State Observation & Audit Log Persistence
```
1. The ReAct agent loop or FSM decides to invoke a tool with structured arguments.
2. The Tool Registry validates arguments against the tool's `args_schema`.
3. The concrete tool adapter executes the underlying domain logic or client query within an exception-shielded try/except block.
4. Output is packaged into an immutable `ToolExecutionResult`, indicating success with data or failure with machine-readable error codes.
5. The execution wrapper measures elapsed execution time and instantiates a `ToolCallTrace` capturing call ID, name, arguments, result, timestamp, and non-negative `duration_ms`.
6. The `ToolCallTrace` is appended to the agent's audit state and fed back into the ReAct loop as an environment observation.

### Certified Final Response Egress Flow (`src/models/response.py`)
```text
Agent Decision / Escalation ──► Cross-Field Validation (mode="after") ──► Invariant Checks (FinOps, Score, Limits) ──► AgentFinalResponse (frozen=True) ──► API / CLI Egress
```
1. Upon reaching a terminal state (`RESOLVED_AUTOMATICALLY` or `REQUIRES_HUMAN_REVIEW`), the agent packages execution data into `AgentFinalResponse`.
2. Model validators enforce cross-field invariants, guaranteeing that a non-empty `human_escalation_reason` is supplied whenever human review is indicated.
3. Field boundaries enforce a confidence score in $[0.0, 1.0]$, non-negative token counts and financial costs, non-negative execution latency, and technical summaries $\le 250$ characters.
4. The resulting certified DTO is serialized for API egress and persisted to audit repositories with zero risk of subsequent mutation.

### Deterministic Statutory Withdrawal & Cooling-Off Calculation Flow (`src/domain/business_rules.py`)
```text
Inbound Tool Invocation (calculate_refund_eligibility)
        │
        ▼
Input Boundary Validation (shipping_fee >= 0, item_prices >= 0)
        │
        ▼
Undelivered Short-Circuit (delivery_date is None? ──► NOT_DELIVERED_YET)
        │
        ▼
UTC Date Normalization (_to_utc_date)
        │
        ▼
Exact Calendar Day Computation (diff_days = (req_date - del_date).days)
        │
        ├── diff_days < 0 ──────────────► NOT_DELIVERED_YET (Premature request)
        ├── 0 <= diff_days <= 14 ───────► WITHIN_LEGAL_TIMEFRAME (Eligible, refund = sum(items))
        └── diff_days > 14 ─────────────► TIMEFRAME_EXCEEDED (Ineligible, refund = 0)
        │
        ▼
RefundEligibilityResult (frozen=True, extra="forbid")
```
1. Inbound refund requests pass delivery timestamp, customer inquiry timestamp, item price list, and shipping fees to `calculate_statutory_withdrawal`.
2. Boundary assertions validate that monetary amounts are strictly non-negative; any negative financial figure or invalid date type raises `BusinessRuleViolationError`.
3. If `delivery_date` is `None`, the function immediately short-circuits to return `RefundReasonCode.NOT_DELIVERED_YET` with zero refundable amount.
4. Datetimes are normalized to UTC calendar dates via `_to_utc_date`, eliminating timezone offset drift and hour-of-day bias.
5. Exact calendar day difference (`(req_date - del_date).days`) is computed:
   - If inquiry precedes delivery (`diff_days < 0`), returns `NOT_DELIVERED_YET`.
   - If within the 14-day statutory cooling-off window (`0 <= diff_days <= 14`), sets `is_eligible_for_return=True`, calculates refundable item total as sum of prices, and assigns `WITHIN_LEGAL_TIMEFRAME`.
   - If exceeding 14 calendar days (`diff_days > 14`), marks request as ineligible with `TIMEFRAME_EXCEEDED` and zero refundable items total.
6. Results are emitted as an immutable `RefundEligibilityResult` DTO, strictly separating deterministic domain arithmetic from LLM generation.

### Shipping Delay Drift & Express Compensation Voucher Flow (`src/domain/business_rules.py`)
```text
Inbound Delay Query (calculate_delivery_delay)
        │
        ▼
Date Type Validation & UTC Normalization (_to_utc_date)
        │
        ▼
Calendar Drift Computation: diff = (ref_date - est_date).days
        │
        ▼
DeliveryDelayResult(delay_days = max(0, diff), is_delayed = delay_days > 0)
        │
        ▼
Express Policy Evaluation (is_express AND delay_days > 5 ?)
        ├── TRUE  ──► 100% Shipping Fee Voucher (voucher_cents = shipping_fee_cents)
        └── FALSE ──► Zero Voucher (voucher_cents = 0)
```
1. `calculate_shipping_delay` receives `estimated_delivery_date` and `reference_date`.
2. Both dates are validated as `datetime` instances and normalized to UTC calendar dates via `_to_utc_date`.
3. Elapsed calendar difference `(ref_date - est_date).days` is calculated; if non-positive (on-time or early), `delay_days` is clamped to `0` and `is_delayed` is `False`.
4. Output is returned as an immutable `DeliveryDelayResult` DTO.
5. If express compensation is evaluated (`calculate_express_compensation`), non-negative assertions guard `delay_days` and `shipping_fee_cents`.
6. Under commercial policy, if `is_express` is True and `delay_days > 5`, a 100% shipping fee voucher is granted; otherwise 0 is returned.

### Mock ERP Client Data Ingestion & Retry Shielding Flow (`src/clients/erp_client.py`)
```text
Inbound Order Query (get_order_by_id / get_order_by_id_async)
        │
        ▼
Tenacity Retry Policy (max_attempts = 2, exponential backoff + jitter)
        │
        ▼
Internal Worker (_fetch_order_direct)
        │
        ├── Transient Failure Injected? ──► Raise ConnectionError ──► Tenacity Retry (Attempt 2)
        │                                                                  │
        │                                                   Exhausted? ────┴──► CircuitBreakerError
        ▼
Read & Validate Storage (_read_orders_raw: data/mock_orders.json)
        │
        ├── Corrupt JSON / Missing File ──────────────────────────────────────► ConfigurationError
        │
        ▼
Order ID Lookup
        │
        ├── Missing in Map? ──► OrderNotFoundError (Fail-Fast, Zero Retry)
        └── Found in Map   ──► Return Order Record Dictionary
```
1. Inbound requests query order metadata via `get_order_by_id` or `get_order_by_id_async`.
2. The lookup delegates to internal worker `_fetch_order_direct` wrapped inside a Tenacity retry orchestrator with `max_attempts=2`.
3. If transient network errors occur (`ConnectionError`, `TimeoutError`), Tenacity catches them and retries with random exponential backoff; if retries are exhausted, the failure is caught and re-raised as a `CircuitBreakerError` preserving root cause context (`from exc`).
4. File reading validates storage existence and parses JSON; any `OSError` or `json.JSONDecodeError` is caught and wrapped into `ConfigurationError`.
5. If the queried `order_id` is missing from the indexed order map, `OrderNotFoundError` is raised immediately; because it represents a permanent domain state rather than transient fault, `is_retryable_exception` bypasses retries to fail fast without latency.
6. Successfully located order payloads return raw dictionary records conforming to ERP schema contracts.



