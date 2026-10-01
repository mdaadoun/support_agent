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
  - **`extraction.py`:** `ExtractedDemand` and `ExtractedEntities` entities with regex validation and boundary schemas.
  - **`tools.py`:** Standardized execution payloads (`OrderDetailsResult`, `ToolExecutionResult`).
  - **`response.py`:** Certified agent response contract (`AgentFinalResponse`).
- **`domain/`:** Pure deterministic business rules:
  - **`business_rules.py`:** 14-day statutory cooling-off arithmetic and delivery delay voucher computation (zero LLM financial authority).
  - **`controller.py`:** Finite State Machine (FSM) controller (`AgentFSMController`) enforcing valid lifecycle transitions, absorbing terminal states, and audit tracking.
  - **`loop.py`:** ReAct decision-action loop capped at 3 iterations.
  - **`prompts.py`:** XML boundary encapsulation and prompt boundary definitions.
  - **`state.py`:** Session state container (`AgentSessionState`), lifecycle state enum (`AgentLifecycleState`), and immutable audit DTO (`StateTransition`).
- **`security/`:** Defense-in-depth and isolation:
  - **`sanitizer.py`:** Defensive input sanitization: non-printable control character scrubbing, bidi/format override removal, bounded iterative tag spoofing neutralization (`[TAG_REMOVED]`), `<user_email>` XML boundary encapsulation, regex entity extraction (`extract_order_id`, `extract_email`), and prompt injection detection.
  - **`access_control.py`:** PII access control and cross-authorization guard (`AccessControlGuard`): canonical email normalization, boolean authorization checks, fail-closed access assertions, polymorphic record inspection, and tool exception shielding.
- **`tools/`:** MCP-compliant tool runtime:
  - **`base.py`:** `ToolInterface` protocol, `BaseTool` abstract base class, `execute_shielded` exception-shielding engine, and `@shield_tool_execution` decorator.
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

### Input Sanitization & XML Boundary Delimitation Flow (`src/security/sanitizer.py`)
```text
Raw Inbound Email Payload (wrap_user_email_payload)
        │
        ▼
Type Validation (isinstance(raw_text, str) ?)
        ├── FALSE ──► Raise BusinessRuleViolationError (INVALID_PAYLOAD_TYPE)
        └── TRUE
        │
        ▼
Control Character Scrubbing (scrub_control_characters)
        │ ── Strips C0 controls (0x00-0x08, 0x0b, 0x0c, 0x0e-0x1f)
        │ ── Strips DEL and C1 controls (0x7f-0x9f)
        │ ── Strips Unicode bidi overrides & zero-width chars (U+200B-U+200F, U+202A-U+202E, U+2066-U+2069, U+FEFF)
        │ ── Preserves standard formatting whitespace (\t, \n, \r)
        │
        ▼
Fixed-Point Tag Sanitization (sanitize_tag_spoofing: max 5 iterations)
        │ ── Match USER_EMAIL_TAG_PATTERN (< /? user_email ... >) ─────────► Replace with [TAG_REMOVED]
        │ ── Match SPOOFED_TAG_PATTERN (< /? (system|instructions|...) >) ──► Replace with [TAG_REMOVED]
        │ ── Reapply until convergence (defeats recursive nesting <<user_email>/user_email>)
        │
        ▼
Boundary Delimitation Envelope
        │
        ▼
Return Formatted Payload: "<user_email>\n{sanitized}\n</user_email>"
```
1. `wrap_user_email_payload` accepts raw inbound customer email text and validates that the payload is a valid string. Non-string inputs immediately raise `BusinessRuleViolationError` with code `INVALID_PAYLOAD_TYPE`.
2. `scrub_control_characters` purges non-printable C0 and C1 control codes, as well as Unicode bidirectional override and zero-width characters (e.g. U+202E, U+200B, U+FEFF), neutralizing visual spoofing and regex evasion techniques while preserving legitimate formatting whitespace (`\t`, `\n`, `\r`).
3. `sanitize_tag_spoofing` executes a bounded iterative loop (up to 5 passes) that substitutes all variants of `<user_email>` boundary tags (opening, closing, self-closing, attributes) and spoofed system/instruction delimiters (`<system>`, `<instructions>`, `<developer>`, `<admin>`, etc.) with `[TAG_REMOVED]`. Iterating until fixed-point convergence neutralizes recursive evasion payloads such as `<<user_email>/user_email>`.
4. The sanitized content is wrapped securely in `<user_email>\n{sanitized}\n</user_email>` before transmission to downstream prompt managers and extraction engines.

### Deterministic Regex Entity Extraction Flow (`src/security/sanitizer.py`)
```text
Inbound Text Payload (extract_entities)
        │
        ├── Type Validation: isinstance(raw_text, str) ──► FALSE ──► Raise BusinessRuleViolationError
        └── TRUE
        │
        ├──► Order Extraction Branch:
        │       │
        │       ▼
        │    Pattern Search: ORDER_ID_PATTERN ((?<![A-Za-z0-9])CMD-[0-9]{5,8}(?![A-Za-z0-9-]))
        │       │
        │       ▼
        │    Uppercase Normalization & Order-Preserving Set Deduplication
        │       │
        │       ▼
        │    Primary Order ID: orders[0] (or None) | All Order IDs: tuple(orders)
        │
        └──► Email Extraction Branch:
                │
                ▼
             Pattern Search: EMAIL_PATTERN (\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b)
                │
                ▼
             Lowercase Canonicalization & Order-Preserving Set Deduplication
                │
                ▼
             Primary Customer Email: emails[0] (or None) | All Emails: tuple(emails)
        │
        ▼
Assemble Immutable DTO: ExtractedEntities(order_id, all_order_ids, customer_email, all_emails)
        │
        ▼
Forward to Pre-Extraction Classifier & PII Access Controller
```
1. `extract_entities` receives raw inbound customer text and performs fail-fast type verification, raising `BusinessRuleViolationError` with code `INVALID_PAYLOAD_TYPE` on non-string inputs.
2. In the order extraction branch, `ORDER_ID_PATTERN` executes with negative lookaround boundaries `(?<![A-Za-z0-9])` and `(?![A-Za-z0-9-])`. This eliminates false-positive sub-matches on longer numbers (e.g. 9 digits) or hyphenated suffixes (`CMD-10045-A`) while allowing punctuation and bracket delimiters. All extracted order codes are normalized to uppercase (`.upper()`) and deduplicated while preserving first-appearance order.
3. In the email extraction branch, `EMAIL_PATTERN` matches RFC 5322-compliant addresses including plus-addressing tags (`user+tag@domain.com`). Extracted addresses are normalized to lowercase (`.lower()`) and deduplicated to guarantee consistent downstream identity comparisons.
4. Results are assembled into an immutable `ExtractedEntities` DTO (`frozen=True, extra="forbid"`), validating `order_id` against `^CMD-[0-9]{5,8}$` and email syntax via Pydantic `EmailStr`.
5. The validated DTO is forwarded to pre-extraction intent classifiers and PII access guards, providing zero-latency deterministic entity resolution prior to LLM reasoning loops.

### PII Access Control & Cross-Authorization Flow (`src/security/access_control.py`)
```text
Inbound Query (sender_email, order_id)
        │
        ▼
Fetch Target Order Record (data/mock_orders.json / erp_client)
        │
        ▼
Access Verification (AccessControlGuard.verify_order_access / shield_unauthorized_access)
        │
        ├── Syntax & Type Normalization (normalize_email)
        │       ├── Invalid Type / Non-String ──► Raise BusinessRuleViolationError (INVALID_PAYLOAD_TYPE)
        │       └── Malformed Syntax ──────────► Raise BusinessRuleViolationError (INVALID_EMAIL_SYNTAX)
        │
        ├── Identity Comparison: normalized_sender == normalized_owner ?
        │
        ├── TRUE (Authorized)
        │       └── Proceed with Order Details Dispatch (OrderStatusTool / FSM)
        │
        └── FALSE (Unauthorized Mismatch)
                │
                ├── Structured Logging: logger.warning("security_access_denied", sender, owner)
                │
                ├── Direct Domain Call:
                │       └── Fail Closed ──► Raise SecurityAccessError ("SECURITY_UNAUTHORIZED_ACCESS")
                │                           (Opaque message: Zero order/owner metadata leaked)
                │
                └── Tool Ingress Wrapper (shield_unauthorized_access):
                        └── Return ToolExecutionResult(success=False, error_code="SECURITY_UNAUTHORIZED_ACCESS")
                                │
                                ▼
                        FSM Transition: ANALYZING ──► REQUIRES_HUMAN (Ticket routed to agent queue)
```
1. Inbound customer operations query order metadata supplying an authenticated `sender_email` and an `order_id`. The order record is retrieved from the ERP data layer.
2. `AccessControlGuard` validates and normalizes both email addresses via `normalize_email`, stripping whitespace, lowercasing, and verifying RFC email syntax. Non-string inputs or empty strings raise `BusinessRuleViolationError` (`INVALID_PAYLOAD_TYPE`), while malformed emails raise `INVALID_EMAIL_SYNTAX`.
3. If normalized emails match (`normalized_sender == normalized_owner`), access is granted and execution proceeds to domain tool dispatch.
4. If an email mismatch is detected, the guard immediately fails closed. A security event is logged internally with structured diagnostic metadata (`sender_email`, `order_owner`).
5. For direct service invocations, `verify_order_access` raises `SecurityAccessError` with standard code `SECURITY_UNAUTHORIZED_ACCESS`. The exception message is strictly sanitized and opaque, withholding the customer's registered email address and order status to block enumeration and harvesting attacks.
6. For tool runtimes, `shield_unauthorized_access` intercepts the violation and returns a certified `ToolExecutionResult(success=False, error_code="SECURITY_UNAUTHORIZED_ACCESS")`, enabling the ReAct loop and FSM controller to route the session gracefully to human escalation (`REQUIRES_HUMAN`) without runtime crash or data leakage.

### Deterministic Pre-Extraction Intent Classification & Threat Guard (`src/security/pre_extraction.py`)
```text
Inbound Message Payload (InboundEmailMessage / raw_text + sender_email)
        │
        ├── Payload & Type Verification: InboundEmailMessage / isinstance(text, str)
        ├── Sender Email Canonicalization: AccessControlGuard.normalize_email(sender_email)
        └── Text Normalization: scrub_control_characters(subject + "\n" + text)
        │
        ├── Entity Extraction:
        │       ├── order_id: extract_order_id(full_text)
        │       └── all_order_ids: extract_all_order_ids(full_text)
        │
        ├── Security Threat Evaluation: detect_legal_threat_or_hostility(full_text)
        │       │
        │       └── TRUE (TC-11: Legal notice, attorney, court, fraud, profanity)
        │               │
        │               ▼
        │            Return ExtractedDemand:
        │              • intent = IntentEnum.OUT_OF_SCOPE
        │              • is_legal_threat_or_aggressive = True
        │              • order_id = order_id (preserved for legal context)
        │              (Direct escalation to human legal counsel; 0 tool calls)
        │
        └── FALSE (Non-hostile)
                │
                ├── Intent Detection & Family Grouping:
                │       ├── Logistics: ORDER_STATUS, DELIVERY_DELAY
                │       ├── Financial: REFUND_REQUEST
                │       └── Documentation: ORDER_INFORMATION
                │
                ├── Classification Logic:
                │       ├── Active Families > 1 OR len(all_order_ids) > 1 ──► candidate = MIXED_QUERY
                │       │                                                       sub_queries = extract_sub_queries(...)
                │       ├── Single Intent Matched ──────────────────────────► candidate = intents[0]
                │       ├── Multiple in Same Family ────────────────────────► candidate = DELIVERY_DELAY / ORDER_STATUS
                │       └── Out of Scope / Unrelated ───────────────────────► candidate = OUT_OF_SCOPE
                │
                ├── Missing Information Gate (TC-05):
                │       ├── candidate in {ORDER_STATUS, DELIVERY_DELAY, REFUND_REQUEST, ORDER_INFORMATION, MIXED_QUERY}
                │       │   AND order_id is None
                │       │   │
                │       │   ▼
                │       │   intent = IntentEnum.INFORMATION_MISSING (0 tool calls; ask customer for ID)
                │       │
                │       └── Otherwise ──► intent = candidate
                │
                ▼
        Return Immutable ExtractedDemand(intent, order_id, customer_email, is_legal_threat, sub_queries)
```
1. `PreExtractionClassifier.classify` ingests either an `InboundEmailMessage` or raw text via `classify_text`. Senders' email addresses are canonicalized through `AccessControlGuard.normalize_email` and text is scrubbed of non-printable control characters via `scrub_control_characters`.
2. Deterministic entity extraction scans the concatenated subject and body for order identifiers using `extract_order_id` and `extract_all_order_ids`.
3. Hostile threats, attorney representation, small claims notices, fraud allegations, and aggressive profanity are screened using `LEGAL_THREAT_PATTERN`. If detected, the classifier returns an `ExtractedDemand` with `intent = IntentEnum.OUT_OF_SCOPE` and `is_legal_threat_or_aggressive = True` (satisfying TC-11). This forces 0 tool calls and immediately routes the inquiry to the human legal team.
4. For non-hostile inquiries, intents are grouped into functional families (Logistics, Refunds, Documentation). Requests spanning multiple distinct families or referencing multiple order IDs are classified as `IntentEnum.MIXED_QUERY`, and decomposed into clauses via `extract_sub_queries`.
5. Crucially, any inquiry requiring an order record (`ORDER_STATUS`, `DELIVERY_DELAY`, `REFUND_REQUEST`, `ORDER_INFORMATION`, `MIXED_QUERY`) that lacks a valid `order_id` is short-circuited to `IntentEnum.INFORMATION_MISSING` (satisfying TC-05). This halts downstream tool invocations before entering the LLM loop and prompts the user for clarification.

### Tool Protocol, Abstract Base & Shielded Execution Runtime (`src/tools/base.py`)
```text
Tool Invocation: BaseTool.execute(**kwargs) / @shield_tool_execution
        │
        ▼
execute_shielded(func, tool_name, args_schema, **kwargs)
        │
        ├── Step 1: Input Schema Validation
        │       ├── args_schema is not None ──► validated = args_schema.model_validate(kwargs)
        │       │                               call_kwargs = validated.model_dump()
        │       │                               (Enforces frozen=True, extra="forbid", and default values)
        │       │
        │       └── ValidationError caught ──► Return ToolExecutionResult(
        │                                         success=False,
        │                                         tool_name=tool_name,
        │                                         error_code="INVALID_ARGUMENTS",
        │                                         error_message=str(val_err)
        │                                      )
        │
        ├── Step 2: Core Logic Dispatch
        │       └── res = func(**call_kwargs) (supports coroutines & synchronous callables)
        │
        ├── Step 3: Payload Normalization
        │       ├── ToolExecutionResult ──► Pass through unchanged
        │       ├── BaseModel / BaseDTO ──► Return ToolExecutionResult(success=True, data=res.model_dump())
        │       ├── dict                ──► Return ToolExecutionResult(success=True, data=dict)
        │       ├── None                ──► Return ToolExecutionResult(success=True, data=None)
        │       └── primitive / list    ──► Return ToolExecutionResult(success=True, data={"result": res})
        │
        └── Step 4: Absolute Exception Shielding ("Zero Naked Crash")
                ├── SupportAgentBaseError caught ──► Return ToolExecutionResult(
                │                                       success=False,
                │                                       tool_name=tool_name,
                │                                       error_code=err.error_code,
                │                                       error_message=err.message
                │                                    )
                │
                └── Generic Exception caught    ──► Structured JSON Log (logger.error)
                                                    Return ToolExecutionResult(
                                                       success=False,
                                                       tool_name=tool_name,
                                                       error_code="TOOL_EXECUTION_ERROR",
                                                       error_message="Unhandled tool failure: ..."
                                                    )
```
1. `BaseTool.execute` acts as the Template Method entrypoint delegating to `execute_shielded`, passing `self._run`, `self.name`, `self.args_schema`, and raw `kwargs`.
2. `execute_shielded` deserializes and schema-validates `kwargs` via `args_schema.model_validate(kwargs)`. Any schema violation or prohibited extra attribute raises Pydantic's `ValidationError`, which is intercepted and mapped to `ToolExecutionResult(success=False, error_code="INVALID_ARGUMENTS")`.
3. Validated arguments are unpacked via `**validated.model_dump()` into `func`, populating model default values and keeping domain code clean of manual deserialization logic. Both coroutine functions and sync callables are transparently supported.
4. If execution succeeds, return values are normalized into `ToolExecutionResult`: Pydantic models are converted via `.model_dump()`, dictionaries are stored in `data`, and empty results return `data=None`.
5. If a domain exception inheriting from `SupportAgentBaseError` (`AppBaseError`) occurs (e.g. `OrderNotFoundError`, `SecurityAccessError`, `BusinessRuleViolationError`), the exact domain `error_code` and message are shielded into `ToolExecutionResult`. Any unexpected third-party runtime failure is logged via `structlog` and shielded into `error_code="TOOL_EXECUTION_ERROR"`. Raw exceptions never escape to crash the ReAct loop.
6. The `@shield_tool_execution` decorator inspects `self` or function attributes to dynamically resolve `tool_name` and `args_schema`, providing identical shielding capabilities for standalone functions and methods.
7. `BaseTool.get_mcp_spec` dynamically generates Model Context Protocol (MCP) tool catalog entries containing the tool's name, description, and JSON Schema parameters directly from Pydantic models.

### Concrete Domain Tool Implementations (`src/tools/order_status.py`, `refund_calculator.py`, `delay_calculator.py`)
```text
1. Order Status Tool (OrderStatusTool):
   Inbound Tool Call (order_id, customer_email)
           │
           ▼
   BaseTool.execute() ──► OrderStatusArgs.model_validate(kwargs)
           │
           ▼
   OrderStatusTool._run(order_id, customer_email)
           │
           ├── erp_client.get_order_by_id_async(order_id)
           │       └── OrderNotFoundError ──► Shielded: ToolExecutionResult(error_code="ORDER_NOT_FOUND")
           │       └── CircuitBreakerError ──► Shielded: ToolExecutionResult(error_code="CIRCUIT_BREAKER_TRIPPED")
           │
           ├── AccessControlGuard.verify_order_record_access(customer_email, order_record)
           │       └── SecurityAccessError ──► Shielded: ToolExecutionResult(error_code="SECURITY_UNAUTHORIZED_ACCESS")
           │
           └── Return OrderDetailsResult(...) ──► Normalized to ToolExecutionResult(success=True, data=...)

2. Refund Calculator Tool (RefundCalculatorTool):
   Inbound Tool Call (delivery_date, request_date, item_prices_cents, shipping_fee_cents, is_express, delay_days)
           │
           ▼
   BaseTool.execute() ──► RefundCalculatorArgs.model_validate(kwargs)
           │
           ▼
   RefundCalculatorTool._run(...)
           │
           ├── Pure Function: calculate_statutory_withdrawal(...)
           │       ├── Check 14-day calendar window: (request_date - delivery_date).days <= 14
           │       └── Express delay compensation: delay_days > 5 & is_express ──► 100% shipping fee voucher
           │
           └── Return RefundEligibilityResult(...) ──► Normalized to ToolExecutionResult(success=True, data=...)

3. Delay Calculator Tool (DelayCalculatorTool):
   Inbound Tool Call (estimated_delivery_date, reference_date, is_express, shipping_fee_cents)
           │
           ▼
   BaseTool.execute() ──► DelayCalculatorArgs.model_validate(kwargs)
           │
           ▼
   DelayCalculatorTool._run(...)
           │
           ├── Pure Function: calculate_shipping_delay(estimated_delivery_date, reference_date)
           └── Pure Function: calculate_express_compensation(delay_days, is_express, shipping_fee_cents)
           │
           └── Return {"delay_days": ..., "is_delayed": ..., "voucher_compensation_cents": ...}
```
1. `OrderStatusTool._run` coordinates asynchronous ERP order queries and PII access control. When invoked with `order_id` and `customer_email`, it fetches the record via `self.erp_client.get_order_by_id_async(order_id)`. Missing orders raise `OrderNotFoundError` which is shielded by `BaseTool` into `error_code="ORDER_NOT_FOUND"`. Upstream ERP dropouts raise `CircuitBreakerError` after retry exhaustion, shielded into `error_code="CIRCUIT_BREAKER_TRIPPED"`.
2. Cross-authorization is verified via `AccessControlGuard.verify_order_record_access(sender_email=customer_email, order_record=order_record)`. If the email fails to match, a `SecurityAccessError` is raised and shielded into `error_code="SECURITY_UNAUTHORIZED_ACCESS"`, failing closed and withholding internal order data.
3. Upon successful authorization, `OrderStatusTool` constructs and returns an immutable `OrderDetailsResult` domain DTO, which `BaseTool.execute` automatically converts into a dictionary payload for `ToolExecutionResult.data`.
4. `RefundCalculatorTool._run` implements statutory cooling-off evaluations under EU Directive 2011/83/EU. It invokes `calculate_statutory_withdrawal` to determine whether the customer's request falls within the 14-day calendar window, returning an immutable `RefundEligibilityResult` with refundable item totals and reason codes (`WITHIN_LEGAL_TIMEFRAME`, `TIMEFRAME_EXCEEDED`, or `NOT_DELIVERED_YET`).
5. `DelayCalculatorTool._run` measures delivery drift in calendar days via `calculate_shipping_delay` and computes commercial express vouchers via `calculate_express_compensation`. Express deliveries delayed by more than 5 calendar days receive a 100% shipping fee compensation voucher.

### Tool Registry & Dynamic Schema Exporters (`src/tools/registry.py`)
```text
Agent Orchestrator / ReAct FSM Loop
        │
        ├── Discovery & Specification:
        │       ├── registry.get_mcp_specs() ──► [{"name", "description", "parameters": json_schema}, ...]
        │       └── registry.get_openai_tools() ──► [{"type": "function", "function": {...}}, ...]
        │
        ├── Pre-Flight Argument Validation:
        │       └── registry.validate_tool_arguments(tool_name, **kwargs)
        │               ├── Unknown Tool ────────► Raise ToolExecutionError ("Tool not registered")
        │               ├── Invalid Schema ──────► Raise ValidationError (Pydantic failure)
        │               └── Valid Model ─────────► Return Validated Pydantic DTO (for cache key hashing)
        │
        └── Shielded Execution Dispatch:
                └── registry.execute(tool_name, **kwargs)
                        │
                        ├── Tool Lookup Check (has_tool)
                        │       └── FALSE ──► Return ToolExecutionResult(success=False, error_code="TOOL_NOT_FOUND")
                        │
                        ├── Dispatch to tool.execute(**kwargs)
                        │       ├── Domain Error (SupportAgentBaseError)
                        │       │       └── Shielded: ToolExecutionResult(success=False, error_code=err.error_code)
                        │       │
                        │       ├── Unexpected Fault (Exception)
                        │       │       └── Logged & Shielded: ToolExecutionResult(success=False, error_code="UNHANDLED_TOOL_FAULT")
                        │       │
                        │       └── Success
                        │               └── Return ToolExecutionResult(success=True, data=..., metrics=...)
```
1. `ToolRegistry` acts as the single-point catalog and dispatch coordinator for all agent tools. It implements Python collection protocols (`__contains__`, `__len__`), allowing clean `if "get_order_details" in registry:` inspection.
2. Dynamic registration via `register(tool)` enforces contract boundary checks at initialization: incoming tools must conform to `@runtime_checkable` `ToolInterface`, have non-empty names, and provide an `args_schema` that is a subclass of Pydantic `BaseModel`. Violations immediately raise `BusinessRuleViolationError` with specific error codes (`INVALID_TOOL_PROTOCOL` or `INVALID_TOOL_METADATA`).
3. Schema export methods (`get_mcp_specs()`, `get_mcp_spec()`, and `get_openai_tools()`) generate standardized Model Context Protocol (MCP) and OpenAI Function Calling definitions dynamically from each tool's Pydantic `model_json_schema()`, eliminating schema duplication and drift.
4. `validate_tool_arguments(tool_name, **kwargs)` performs pre-flight validation against the registered tool's Pydantic schema without executing the tool. This decouples validation from execution, enabling upstream layers (such as the idempotency cache) to validate parameters and construct deterministic cache keys before invoking backend services.
5. `execute(tool_name, **kwargs)` provides full exception shielding. Invocations of unregistered tools return `error_code="TOOL_NOT_FOUND"`, domain exceptions return their respective domain error code, and unexpected runtime exceptions are logged via structured logging and returned with `error_code="UNHANDLED_TOOL_FAULT"`, safeguarding the ReAct loop from crashing.
6. The `create_default_registry(erp_client)` factory assembles the standard operational tool suite (`OrderStatusTool`, `RefundCalculatorTool`, `DelayCalculatorTool`), accepting an optional `MockERPClient` dependency injection for test and production environments.

### Tool Execution Idempotency Caching Flow (`src/persistence/cache.py`, `src/tools/registry.py`)
```text
Inbound Tool Execution Request (tool_name, session_id, **kwargs)
        │
        ▼
ToolRegistry.execute(tool_name, session_id, **kwargs)
        │
        ├── 1. Registry Tool Lookup: has_tool(tool_name)?
        │       └── FALSE ──► Return ToolExecutionResult(error_code="TOOL_NOT_FOUND")
        │
        ├── 2. Cache Key Derivation: session_id provided & cache active?
        │       ├── NO ──► Skip caching, proceed to direct execution
        │       └── YES
        │           │
        │           ▼
        │       IdempotencyCache.compute_key(session_id, tool_name, kwargs)
        │           │ ── Normalize primitives & ISO-8601 datetimes (_json_serializer)
        │           │ ── Canonical JSON serialization: json.dumps(kwargs, sort_keys=True)
        │           │ ── Derive SHA-256 Digest: SHA256(f"{session_id}:{tool_name}:{normalized_args}")
        │           │
        │           ▼
        │       IdempotencyCache.get_result_async(cache_key)
        │           │
        │           ├── Try Primary Redis Store (L2):
        │           │       └── GET idempotency:<hash> (timeout 0.2s)
        │           │               ├── HIT ──► ToolExecutionResult.model_validate_json(payload)
        │           │               └── Connection Error ──► Log warning & Fallback
        │           │
        │           └── Check Local Memory Store (L1 Fallback):
        │                   └── entry = _in_memory_store[hash]
        │                           ├── Active (now <= expires_at) ──► Return deserialized result
        │                           └── Stale (now > expires_at) ──► Evict key & Return None
        │
        ├── 3. Cache HIT:
        │       └── Return cached ToolExecutionResult instantly (Zero ERP/LLM I/O)
        │
        └── 4. Cache MISS:
                │
                ▼
            tool.execute(**kwargs) ──► Shielded execution
                │
                ├── Execution Succeeded (result.success is True)?
                │       ├── YES ──► IdempotencyCache.set_result_async(cache_key, result)
                │       │             ├── Redis: SET idempotency:<hash> payload EX 900 NX
                │       │             └── Memory: _in_memory_store[hash] = (payload, now + 900)
                │       └── NO  ──► Skip caching (allows immediate retries for transient faults)
                │
                ▼
            Return ToolExecutionResult
```
1. `IdempotencyCache.compute_key` enforces deterministic argument hashing by running `json.dumps(arguments, sort_keys=True, default=_json_serializer)`. Datetimes, dates, and nested Pydantic models are normalized to ISO-8601 strings and JSON dictionaries, preventing serialization failures and ensuring dictionary key order independence.
2. The derived SHA-256 hash digest binds three critical dimensions: `session_id` (guaranteeing tenant and conversational isolation), `tool_name` (scoping by operation), and normalized arguments.
3. Two-tier caching provides resilience: `IdempotencyCache` lazily probes the configured Redis cluster at `settings.redis_url` with strict 0.2s connection and socket timeouts. If Redis is down, unreachable, or in local/test mode, the cache falls back seamlessly to an in-memory dictionary (`_in_memory_store`) without raising exceptions.
4. Active TTL management enforces 15-minute expiration (900 seconds). In Redis, this is implemented using native `EX 900` flags with `NX=True` (set-if-not-exists) for distributed atomicity. In the in-memory fallback, each item is stored as a `(payload, expires_at_timestamp)` tuple; expired items are pruned lazily on access.
5. `ToolRegistry.execute` intercepts execution requests when an optional `session_id` is supplied. It checks the cache before calling `tool.execute()`. On cache hits, it immediately returns the cached `ToolExecutionResult`, saving external API calls, latency, and FinOps token costs.
6. Caching is strictly confined to successful outcomes (`result.success is True`). Transient network errors, rate limits, or authorization rejections are never cached, enabling callers to retry without waiting for TTL expiration.

---

### Finite State Machine (FSM) Lifecycle Controller & Session Transition Flow (`src/agent/controller.py`, `src/agent/state.py`)

```text
[ Inbound Email Message ]
        │
        ▼
   create_session(session_id, inbound_message)
        │ ── Initial State: AgentLifecycleState.RECEIVED
        │ ── State History: [], Tool Traces: []
        │
        ▼
AgentFSMController.transition(session, ANALYZING)
        │ ── Assert target in VALID_TRANSITIONS[RECEIVED]
        │ ── Append StateTransition(from=RECEIVED, to=ANALYZING)
        │
        ├── [ Pre-Extraction / Security Guard ]
        │       ├── Injection / Threat / Out-of-Scope ──► AgentFSMController.transition_to_human(session, reason)
        │       │                                               └── State: REQUIRES_HUMAN (Terminal)
        │       └── Valid Inbound Demand ──► AgentFSMController.transition(session, EXECUTING_TOOL)
        │
        ├── [ Tool Execution Dispatch ]
        │       │
        │       ▼
        │   AgentFSMController.transition(session, OBSERVING)
        │       │
        │       ├── Additional Tool Required & Iteration < 3:
        │       │       └── AgentFSMController.transition(session, EXECUTING_TOOL)  [Multi-Turn ReAct Loop]
        │       │
        │       ├── Loop Ceiling Reached (Iteration >= 3) or Unrecoverable Fault:
        │       │       └── AgentFSMController.transition_to_human(session, "LOOP_LIMIT_EXCEEDED") [Terminal]
        │       │
        │       └── Sufficient Context Collected:
        │               └── AgentFSMController.transition(session, GENERATING_RESPONSE)
        │
        └── [ Response Validation & Delivery ]
                ├── FinalResponse Schema Passes ──► AgentFSMController.transition(session, COMPLETED) [Terminal]
                └── Validation Failure / Hallucination ──► AgentFSMController.transition_to_human(session, reason) [Terminal]
```

1. **Session Lifecycle Initialization:** An incoming customer email is wrapped into `AgentSessionState` via `create_session(session_id, inbound_message)`. The session initializes strictly in `AgentLifecycleState.RECEIVED` with empty `tool_traces` and an empty `state_history` audit collection.
2. **Deterministic State Machine Enforcement:** Every state change must flow through `AgentFSMController.transition(session, new_state, reason=...)`. The controller consults the centralized `VALID_TRANSITIONS` table (`dict[AgentLifecycleState, frozenset[AgentLifecycleState]]`). Any unauthorized transition attempt immediately logs an error and raises `FSMStateError` (`error_code="FSM_STATE_INVALID"`).
3. **Immutable Forensic Audit Trail:** Each successful transition instantiates an immutable `StateTransition` Pydantic V2 DTO (`frozen=True, extra="forbid"`), stamping the `from_state`, `to_state`, UTC `timestamp`, and diagnostic `reason` into `session.state_history`. This enables post-hoc debugging, telemetry tracing, and audit qualification.
4. **Fail-Closed Security & Escalation Shortcuts:** When anomalies (such as prompt injections, hostile legal threats, or PII mismatches) are detected, callers invoke `AgentFSMController.transition_to_human(session, reason)`. This automatically attaches the `escalation_reason` to the session and advances the state to `REQUIRES_HUMAN`.
5. **Multi-Turn Loop Re-Entrance:** The transition graph explicitly permits looping from `OBSERVING` back to `EXECUTING_TOOL`, facilitating autonomous multi-turn ReAct tool execution while bounding recursion through iteration checks.
6. **Absorbing Terminal State Isolation:** Terminal states (`COMPLETED`, `REQUIRES_HUMAN`, `FAILED`) map to empty transition sets (`frozenset()`). Once a session reaches a terminal state, any further transition is rejected with `FSMStateError`, eliminating zombie background executions.

---

### System Prompt Engineering, Boundary Enforcement & Observation Formatting (`src/agent/prompts.py`)

```text
[ Raw Inbound Email ]
        │
        ▼
wrap_user_email_payload() ──► Sanitization: strips nested XML tags, normalizes whitespace
        │
        ▼
format_user_prompt()      ──► Envelopes input into passive <user_email> ... </user_email>
        │
        ▼
PromptManager.build_initial_agent_prompt()
        │
        ├── Prefixes with <metadata> (Detected Intent, Extracted Order ID)
        └── Instructs ReAct loop to initiate reasoning
        │
        ▼
[ Multi-Turn ReAct Cycle ]
        │
        ├── Tool Execution Completed ──► ToolExecutionResult / ToolExecutionTrace
        │                                         │
        │                                         ▼
        │                         format_tool_trace_observation()
        │                                         │
        │                                         ▼
        │                         <tool_observation tool="..." success="..." error_code="...">
        │                             {"output": ..., "status": ...}
        │                         </tool_observation>
        │
        ▼
PromptManager.build_react_history_prompt()
        │
        └── Chronologically aggregates initial prompt and all <tool_observation> blocks
        │
        ▼
PromptManager.build_final_response_prompt()
        │
        └── Pairs <user_email> with verified tool observations and instructions to synthesize
            a grounded customer response with ZERO uncertified financial commitments
```

1. **Passive Input Parsing (`<user_email>` Framing):** User inquiries are processed through `format_user_prompt(email_body)`, which sanitizes control characters, strips nested or forged XML boundary tags using `wrap_user_email_payload`, and envelopes the body within `<user_email>...</user_email>`. System prompt instructions inform the LLM that content within this tag is passive customer data and must never be interpreted as operational directives or policy changes.
2. **Zero Financial Authority Invariant:** Hardened system prompts (`AGENT_SYSTEM_PROMPT` and `RESPONSE_SYNTHESIS_SYSTEM_PROMPT`) explicitly forbid the model from computing, promising, negotiating, or volunteering any financial amounts, refunds, discounts, or vouchers. Any financial compensation must be generated exclusively by deterministic backend tools (`calculate_refund_eligibility`, `calculate_delivery_delay`) and echoed verbatim.
3. **Structured Tool Observation Framing:** Observations returned from backend tools are wrapped into structured `<tool_observation>` blocks via `format_observation` and `format_tool_trace_observation`. XML attributes (`tool`, `success`, `error_code`) and indented JSON payloads provide deterministic syntactic separation between LLM reasoning thoughts, user input, and trusted backend tool data.
4. **Centralized PromptManager Facade:** The `PromptManager` class decouples prompt formatting from the execution loop. It exposes static factory methods (`build_initial_agent_prompt`, `build_react_history_prompt`, `build_final_response_prompt`) that standardize metadata injection, chronological observation history compilation, and response synthesis instructions across the application.

---

### LLM Inference Client Wrapper, Resilient Retries & Tool Calling (`src/clients/llm_client.py`, `src/clients/llm_retry.py`, `src/clients/llm_parser.py`)

```text
[ LLM Request: messages, tools, response_schema ]
        │
        ▼
LLMClient.generate_with_tools() / generate_structured()
        │
        ├── 1. Temperature Validation: enforce 0.0 <= temperature <= 0.2
        ├── 2. Parameter Assembly: model, messages, tools, tool_choice
        │
        ▼
execute_with_retry() ──► Tenacity AsyncRetrying loop
        │
        ├── Attempt API call (AsyncOpenAI client)
        │       │
        │       ├── Transient Error (429 RateLimit, 5xx ServerError, Timeout, Connection)?
        │       │       └── Exponential Backoff with Jitter (up to max_retries) ──► Re-attempt
        │       │
        │       └── Fatal Error (401 Auth, 400 Bad Request, exhausted retries)?
        │               └── Shield into AppBaseError (LLMAuthenticationError, LLMInferenceError)
        │
        ▼
[ Raw ChatCompletion / ParsedChatCompletion Response ]
        │
        ├── parse_tool_calls(message.tool_calls)
        │       └── Validates and parses JSON argument strings into tuple[LLMToolCall, ...]
        │
        ├── parse_usage_metrics(response.usage, cost_tracker)
        │       └── Computes prompt/completion token sums and real-time USD cost
        │
        ▼
[ LLMResponse DTO ] (immutable, typed, certified)
```

1. **Deterministic Sampling Ceiling ($T \le 0.2$):** `LLMClient` guarantees reproducible outputs by strictly bounding temperature. At initialization, if a temperature is passed, it validates `0.0 <= temperature <= 0.2` (raising `BusinessRuleViolationError` on violations); otherwise, it clamps the default setting to $\le 0.2$.
2. **Selective Tenacity Retrying:** The execution pipeline delegates all network I/O to `execute_with_retry` backed by `AsyncRetrying`. It selectively retries ephemeral errors (`RateLimitError`, `APIConnectionError`, `APITimeoutError`, `InternalServerError`) using exponential backoff with jitter (`retry_min_wait` to `retry_max_wait`). Fatal client errors (`AuthenticationError`, `BadRequestError`) fail fast without retry waste.
3. **Structured Response Parsing:** For schema-constrained outputs (`generate_structured`), the client leverages `beta.chat.completions.parse` with automated fallback to `chat.completions.create(response_format={"type": "json_object"})` followed by `model_validate_json`. Validation failures or model refusals immediately raise `LLMResponseValidationError`.
4. **Tool Calling & Argument Normalization:** When invoking tools via `generate_with_tools`, raw JSON arguments returned from the provider are safely decoded and wrapped into immutable `LLMToolCall` DTOs (`BaseDTO` derivatives). Malformed JSON payloads are trapped at the boundary with diagnostic errors.
5. **Real-Time Token Telemetry:** Every tool generation automatically runs through `parse_usage_metrics`, computing token usage and estimating USD cost via `FinOpsCostTracker`, packing these metrics directly into the returned `LLMResponse.usage` object.

---

### ReAct Execution Loop Engine & Bounded Autonomous Reasoning (`src/agent/loop.py`, `src/agent/protocols.py`, `src/agent/response_builder.py`)

```text
[ Inbound Session: CustomerInboundPayload ]
        │
        ▼
ReActLoopEngine.run()
        │
        ├── Transition FSM: RECEIVED ──► ANALYZING
        │
        ├── Pre-Flight Security & Scope Check (extracted_demand)
        │       │
        │       └── Threat/Hostile/Out-of-Scope? ──► YES ──► build_escalated_response()
        │                                                     │
        │                                                     ▼
        │                                            Transition: REQUIRES_HUMAN
        ▼
[ Multi-Turn ReAct Cycle (iteration = 0 .. max_iterations - 1) ]
        │
        ├── Check Recursion Ceiling: iteration >= 3?
        │       └── YES ──► build_escalated_response(LOOP_LIMIT_EXCEEDED) ──► REQUIRES_HUMAN
        │
        ├── Compile Messages (PromptManager.build_react_history_prompt)
        ├── Export Tool Schemas (tool_registry.get_mcp_schemas)
        │
        ▼
LLMClient.generate_with_tools()
        │
        ├── Model Decides: Tool Call Requested?
        │       │
        │       ├── YES:
        │       │     ├── Transition FSM: ANALYZING ──► EXECUTING_TOOL
        │       │     ├── Dispatch tool via tool_registry.execute_shielded()
        │       │     ├── Record ToolExecutionTrace (id, tool, args, result)
        │       │     └── Transition FSM: EXECUTING_TOOL ──► OBSERVING
        │       │             └── Transition FSM: OBSERVING ──► ANALYZING (Next Turn)
        │       │
        │       └── NO (Reasoning complete):
        │             └── Break Multi-Turn Loop ──► Proceed to Synthesis
        ▼
Transition FSM: ANALYZING ──► GENERATING_RESPONSE
        │
        ▼
synthesize_certified_response()
        │
        ├── Compile synthesis prompt (PromptManager.build_final_response_prompt)
        ├── LLMClient.generate_structured(ResponseSynthesisOutput)
        │
        ▼
[ Confidence Evaluation & Final Resolution ]
        │
        ├── Confidence Score >= 0.85?
        │       │
        │       ├── YES ──► RESOLVED_AUTOMATICALLY
        │       │             └── Transition FSM: GENERATING_RESPONSE ──► COMPLETED
        │       │
        │       └── NO  ──► REQUIRES_HUMAN_REVIEW (LOW_CONFIDENCE)
        │                     └── Transition FSM: GENERATING_RESPONSE ──► REQUIRES_HUMAN
        ▼
[ Return AgentFinalResponse ]
```

1. **Hexagonal Layer Decoupling via Structural Protocols:** `src/agent/protocols.py` defines `LLMClientProtocol` and `ToolRegistryProtocol` using `@runtime_checkable` Python `typing.Protocol`. The core agent domain never imports concrete infrastructure clients (`LLMClient`, `ToolRegistry`), preserving strict layer isolation and allowing full mockability in tests.
2. **Deterministic Pre-Flight Fast-Path Escalation:** Before committing LLM tokens or executing tools, the engine inspects the pre-extracted demand. Hostile litigation threats, aggressive language, or out-of-scope queries immediately bypass the ReAct loop and trigger `build_escalated_response`, routing straight to `AgentLifecycleState.REQUIRES_HUMAN`.
3. **Hard Recursion Ceiling Throttler ($N_{\max} = 3$):** To prevent runaway loops, infinite circular reasoning, and token exhaustion, the multi-turn loop strictly caps iterations at 3. Reaching this boundary triggers deterministic escalation with reason `LOOP_LIMIT_EXCEEDED` and transitions the FSM to `REQUIRES_HUMAN`.
4. **FSM State Machine Lifecycle Governance:** Every phase transition (`RECEIVED -> ANALYZING -> EXECUTING_TOOL -> OBSERVING -> GENERATING_RESPONSE -> COMPLETED / REQUIRES_HUMAN`) is governed and recorded by `AgentStateController`, maintaining an immutable audit log of lifecycle states with diagnostic transition reasons.
5. **Two-Tier Confidence Guard & Response Synthesis:** Customer responses are synthesized via `ResponseSynthesisOutput` enforcing structured validation. If the model's reported confidence falls below 0.85, the engine overrides the status to `REQUIRES_HUMAN_REVIEW` and routes the session to human queues, preventing ungrounded or low-confidence resolutions from reaching the customer.

---

### Zero LLM Authority Validation Guard & Output Certification (`src/agent/validator.py`, `src/agent/validator_rules.py`)

```text
[ Synthesized Response / AgentFinalResponse candidate ]
        │
        ▼
ZeroLLMAuthorityGuard.validate()
        │
        ├── 1. extract_monetary_amounts(subject + body)
        │       └── Parse (€, $, £, EUR, USD, cents) ──► Convert to integer cents
        │
        ├── 2. extract_certified_amounts(session.tool_traces)
        │       └── Extract deterministic cents from successful tool payloads
        │       │
        │       └── Uncertified monetary amount detected?
        │               └── YES ──► Flag Violation: "Uncertified monetary figure"
        │
        ├── 3. detect_approval_claims(subject + body)
        │       ├── Negation-Aware Filtering (skip "cannot be approved", "not eligible")
        │       ├── Affirmative Refund Claim? ──► check_refund_tool_authorization()
        │       │       └── Unbacked? ──► Flag Violation: "Unauthorized refund approval"
        │       └── Affirmative Voucher Claim? ──► check_voucher_tool_authorization()
        │               └── Unbacked? ──► Flag Violation: "Unauthorized voucher approval"
        │
        ├── 4. Operational Mutation Check (MUTATION_RE)
        │       └── Claims order cancellation or address modification? ──► Flag Violation
        │
        ├── 5. Security Access Check
        │       └── SECURITY_UNAUTHORIZED_ACCESS in traces with RESOLVED_AUTOMATICALLY?
        │               └── Flag Violation: "Security access violation"
        ▼
[ AuthorityValidationResult(is_valid, violations) ]
        │
        ├── is_valid == True:
        │       └── Return unchanged certified response ──► FSM: COMPLETED
        │
        └── is_valid == False:
                ├── guard_response() overrides status_resolution ──► REQUIRES_HUMAN_REVIEW
                ├── Populates human_escalation_reason with violation diagnostics
                ├── Neutralizes email_response_body ──► Standard human handoff message
                └── Transition FSM: GENERATING_RESPONSE ──► REQUIRES_HUMAN
```

1. **Separation of Privileges & Zero Financial Authority:** The language model is completely stripped of autonomous authority to authorize refunds, approve discount vouchers, or mutate orders. All financial values and legal entitlements must originate from pure, certified Python calculations (`src/domain/business_rules.py`) executed via backend tools.
2. **Canonical Integer Cents Normalization:** Currency figures cited in customer emails or generated responses are parsed across multi-currency symbols (`€`, `$`, `£`) and units (`EUR`, `USD`, `cents`) into exact integer cents (`_parse_to_cents`). This eliminates floating-point representation artifacts and enables exact set membership checks against certified tool traces.
3. **Negation-Aware Approval Clause Parsing:** The guard parses text on clause and sentence boundaries, checking for explicit negation tokens (`cannot`, `not`, `unable`, `refused`, `ineligible`). This allows the agent to safely convey statutory refusals (e.g. 14-day expired return refusals) without triggering false-positive escalations, while strictly intercepting unbacked affirmative approvals.
4. **Defense-in-Depth Pipeline Integration:** Output validation operates as a dual gate: first within `synthesize_certified_response` in `src/agent/response_builder.py` prior to response packaging, and second via `guard_response` inside `ReActLoopEngine.run` before FSM state finalization.
5. **Fail-Closed Response Neutralization:** If an authority breach is detected (e.g., prompted by an indirect prompt injection like TC-08), `guard_response` immediately overrides `status_resolution` to `REQUIRES_HUMAN_REVIEW`, populates `human_escalation_reason`, and replaces the uncertified email body with a neutral human handoff message, guaranteeing that no unauthorized commitments reach the customer.









