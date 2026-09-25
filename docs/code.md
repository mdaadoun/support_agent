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
- **`agent/`:** Autonomous orchestration engine:
  - **`controller.py`:** Finite State Machine (FSM) enforcing valid lifecycle transitions.
  - **`loop.py`:** ReAct decision-action loop capped at 3 iterations.
  - **`prompts.py`:** XML boundary encapsulation and prompt boundary definitions.
  - **`state.py`:** Session state and trajectory models.
- **`security/`:** Defense-in-depth and isolation:
  - **`sanitizer.py`:** Defensive input sanitization: non-printable control character scrubbing, bidi/format override removal, bounded iterative tag spoofing neutralization (`[TAG_REMOVED]`), `<user_email>` XML boundary encapsulation, regex entity extraction (`extract_order_id`, `extract_email`), and prompt injection detection.
  - **`access_control.py`:** PII access control and cross-authorization guard (`AccessControlGuard`): canonical email normalization, boolean authorization checks, fail-closed access assertions, polymorphic record inspection, and tool exception shielding.
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

