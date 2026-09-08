# Implementation Roadmap: Customer Support Automation Agent

**Project:** `8_support_agent` (`projects/8_/`)  
**Status:** Active Planning | **Version:** 1.0.0  
**Target:** Production-Grade Autonomous Tier-1 Support Agent with Deterministic Business Rules

---

## 📊 Phase Overview

```text
[Phase 1] Setup & Baseline Infra ──► [Phase 2] Domain Schemas & Exceptions ──► [Phase 3] Deterministic Business Rules
                                                                                              │
[Phase 6] ReAct Loop & FSM Controller ◄── [Phase 5] Tool Runtime & MCP ◄── [Phase 4] Security & Pre-Extraction
      │
      ▼
[Phase 7] Persistence & FinOps Telemetry ──► [Phase 8] Ingress (FastAPI & CLI), Test Suite (TC-01..TC-12) & Docker
```

---

## Phase 1: Baseline Architecture & Project Infrastructure

**Entry Criteria:** Clean repository directory (`projects/8_/`).  
**Dependencies:** None.  
**Deliverables:** Poetry configuration, Ruff, Mypy strict setup, Pydantic settings, directory layout, Docker skeleton.

- [x] **Step 1.1: Dependency & Environment Configuration:**
  - Initialize Poetry project with Python `>= 3.11` constraints (`pyproject.toml`).
  - Configure Ruff linter/formatter rules (E, F, B, SIM, I) and Mypy strict mode (`strict = true`).
  - Create `Makefile` with shortcuts: `lint`, `typecheck`, `test`, `format`, `run-cli`, `run-api`.
- [ ] **Step 1.2: Centralized Settings Configuration:**
  - Implement `src/core/config.py` using `pydantic-settings` (`BaseSettings`).
  - Define environment variables with defaults: LLM model, API keys, Redis URL, PostgreSQL DSN, max iterations (default 3), confidence threshold (0.85).
- [ ] **Step 1.3: Package Skeleton & Mock ERP Seed Data:**
  - Create modular directory tree (`src/api`, `src/agent`, `src/domain`, `src/models`, `src/security`, `src/tools`, `src/clients`, `src/persistence`, `src/observability`, `tests/`).
  - Populate `data/mock_orders.json` with representative order scenarios (delivered, delayed, cancelled, returned).
- [ ] **Step 1.4: Container Stack Skeleton:**
  - Create `docker/docker-compose.yml` specifying FastAPI service, Redis 7 Alpine, and PostgreSQL 15 Alpine.

**Verification Checkpoint:**  
`make lint && make typecheck` passes with zero warnings or errors.

---

## Phase 2: Domain Schemas, Type Contracts & Exception Shielding

**Entry Criteria:** Phase 1 complete and verified.  
**Dependencies:** Phase 1.  
**Deliverables:** Pydantic V2 immutable DTOs (`frozen=True`), domain enums, standardized exception hierarchy.

- [ ] **Step 2.1: Business Enums & Base Model:**
  - Define `BaseDTO` with `frozen=True` and `extra="forbid"` (`src/models/base.py`).
  - Define enums: `OrderStatusEnum`, `IntentEnum`, `RefundReasonCode`, `ResolutionStatusEnum` (`src/models/enums.py`).
- [ ] **Step 2.2: Ingestion & Extraction Schemas:**
  - Implement `InboundEmailMessage` with email syntax validation (`src/models/email.py`).
  - Implement `ExtractedDemand` with regex pattern validation for `CMD-[0-9]{5,8}` (`src/models/extraction.py`).
- [ ] **Step 2.3: Tool Execution & Trace Schemas:**
  - Implement `OrderDetailsResult`, `RefundEligibilityResult`, `DeliveryDelayResult` (`src/models/tools.py`).
  - Implement `ToolExecutionResult` and `ToolCallTrace` for deterministic tool reporting (`src/models/tools.py`).
- [ ] **Step 2.4: Final Certified Response Schema:**
  - Implement `AgentFinalResponse` ensuring mandatory FinOps, latency, and escalation metadata (`src/models/response.py`).
- [ ] **Step 2.5: Standardized Exception Shielding Hierarchy:**
  - Create `SupportAgentBaseError` in `src/core/exceptions.py`.
  - Implement domain sub-exceptions: `SecurityAccessError`, `ToolExecutionError`, `FSMStateError`, `CircuitBreakerError`, `ConfigurationError`.

**Verification Checkpoint:**  
Unit tests in `tests/unit/test_schemas.py` confirm model immutability, extra field rejection, and schema validation.

---

## Phase 3: Deterministic Domain Business Rules & ERP Client

**Entry Criteria:** Phase 2 schemas and exceptions implemented.  
**Dependencies:** Phase 2.  
**Deliverables:** Pure Python deterministic arithmetic engine, mock ERP client with retry and error mapping.

- [ ] **Step 3.1: Statutory Withdrawal Business Logic (14-Day Rule):**
  - Implement pure function `calculate_statutory_withdrawal(delivery_date, request_date, item_prices_cents, shipping_fee_cents)` in `src/domain/business_rules.py`.
  - Enforce exact calendar day computation (`(request_date - delivery_date).days <= 14`).
- [ ] **Step 3.2: Shipping Delay & Express Compensation Logic:**
  - Implement pure function `calculate_shipping_delay(estimated_delivery_date, reference_date)` in `src/domain/business_rules.py`.
  - Implement `calculate_express_compensation(delay_days, is_express, shipping_fee_cents)` granting 100% shipping fee voucher if `is_express` and `delay_days > 5`.
- [ ] **Step 3.3: Mock ERP Client Adapter:**
  - Implement `src/clients/erp_client.py` loading and querying `data/mock_orders.json`.
  - Decorate lookups with Tenacity exponential retry (max 2 attempts) for network simulation.
  - Map missing orders cleanly to `OrderNotFoundError` without raising raw filesystem or HTTP exceptions.

**Verification Checkpoint:**  
`pytest tests/unit/test_business_rules.py` validates 100% deterministic accuracy on cooling-off calculations and delay vouchers.

---

## Phase 4: Security Guardrails, PII Isolation & Pre-Extraction Engine

**Entry Criteria:** Phase 3 business rules complete.  
**Dependencies:** Phase 2, Phase 3.  
**Deliverables:** Input sanitizer, prompt injection filter, PII access controller, pre-flight demand extractor.

- [ ] **Step 4.1: Input Sanitizer & XML Boundary Delimitation:**
  - Implement `src/security/sanitizer.py` wrapping raw inbound email text in `<user_email>...</user_email>`.
  - Scrub control characters and sanitize nested tag spoofing attempts.
- [ ] **Step 4.2: Regex Entity Extraction:**
  - Implement deterministic regex matcher for order numbers (`CMD-[0-9]{5,8}`) and customer email addresses (`src/security/sanitizer.py`).
- [ ] **Step 4.3: PII Access Control Guard:**
  - Implement `src/security/access_control.py` verifying `sender_email == order.customer_email`.
  - Return `SECURITY_UNAUTHORIZED_ACCESS` on mismatch and block data leakage.
- [ ] **Step 4.4: Pre-Extraction Intent Classifier:**
  - Implement pre-flight extractor identifying `INFORMATION_MISSING` (no order ID when required), `OUT_OF_SCOPE`, or aggressive legal litigation threats prior to tool dispatch.

**Verification Checkpoint:**  
`pytest tests/unit/test_sanitizer.py` passes injection neutralization tests; PII mismatch triggers rejection without metadata leakage.

---

## Phase 5: Tool Interface, Registry & MCP Compatibility Runtime

**Entry Criteria:** Phase 3 domain logic and Phase 4 security guards implemented.  
**Dependencies:** Phase 3, Phase 4.  
**Deliverables:** MCP-compatible `ToolInterface`, dynamic tool registry, tool adapters with exception shielding, Redis idempotency caching.

- [ ] **Step 5.1: Tool Protocol & Abstract Base:**
  - Define `ToolInterface` protocol in `src/tools/base.py` declaring `name`, `description`, `args_schema`, and `execute()`.
  - Implement execution wrapper shielding raw exceptions and returning `ToolExecutionResult`.
- [ ] **Step 5.2: Tool Implementations:**
  - Implement `OrderStatusTool` (`get_order_details`) in `src/tools/order_status.py`.
  - Implement `RefundCalculatorTool` (`calculate_refund_eligibility`) in `src/tools/refund_calculator.py`.
  - Implement `DelayCalculatorTool` (`calculate_delivery_delay`) in `src/tools/delay_calculator.py`.
- [ ] **Step 5.3: Tool Registry & Schema Exporter:**
  - Implement `src/tools/registry.py` for tool discovery, validation against Pydantic models, and MCP tool specification export.
- [ ] **Step 5.4: Tool Execution Idempotency Caching:**
  - Implement idempotency hashing: `SHA256(session_id + tool_name + sorted_args)` stored in Redis (15-minute TTL) to prevent duplicate execution during active sessions.

**Verification Checkpoint:**  
`pytest tests/integration/test_tools_runtime.py` verifies all tools validate arguments, shield errors, and return cached results on duplicate calls.

---

## Phase 6: ReAct Agent Loop & Finite State Machine (FSM) Controller

**Entry Criteria:** Phase 5 tool runtime operational.  
**Dependencies:** Phases 2, 4, 5.  
**Deliverables:** FSM lifecycle controller, ReAct execution loop, recursion throttler ($N_{\max} = 3$), LLM client integration.

- [ ] **Step 6.1: FSM State Machine Controller:**
  - Implement `src/agent/controller.py` enforcing transitions: `RECEIVED` ──► `ANALYZING` ──► `EXECUTING_TOOL` ──► `OBSERVING` ──► `GENERATING_RESPONSE` ──► `COMPLETED` / `REQUIRES_HUMAN` / `FAILED`.
- [ ] **Step 6.2: System Prompt & Boundary Templates:**
  - Author strict system prompts in `src/agent/prompts.py` enforcing zero LLM financial authority and passive parsing of `<user_email>`.
- [ ] **Step 6.3: LLM Inference Client Wrapper:**
  - Implement `src/clients/llm_client.py` wrapping LiteLLM / AsyncOpenAI with `temperature <= 0.2`, structured output tool calling, and Tenacity retries.
- [ ] **Step 6.4: ReAct Execution Loop Engine:**
  - Implement `src/agent/loop.py` orchestrating multi-step decision-action-observation cycles.
  - Enforce hard recursion ceiling at **3 tool iterations** with automatic escalation to `REQUIRES_HUMAN` upon limit reach.
- [ ] **Step 6.5: Zero LLM Authority Validation Guard:**
  - Validate that final email responses containing monetary figures or approval statements strictly match certified tool outputs.

**Verification Checkpoint:**  
Agent loop successfully runs multi-turn tool calling, halts at 3 iterations, and produces validated `AgentFinalResponse`.

---

## Phase 7: Persistence, Audit Trail & FinOps Telemetry

**Entry Criteria:** Agent loop functional.  
**Dependencies:** Phase 6.  
**Deliverables:** PostgreSQL audit log repository, JSON Lines fallback, `structlog` logging, FinOps cost estimation, OpenTelemetry tracer.

- [ ] **Step 7.1: Redis Cache & Session State Store:**
  - Implement `src/persistence/cache.py` managing session states and idempotency keys with TTL expiry.
- [ ] **Step 7.2: Audit Log Repository:**
  - Implement `src/persistence/repository.py` for PostgreSQL `agent_audit_logs` storage with JSONB trace payloads.
  - Implement local fallback appending to `traces.jsonl` when PostgreSQL is unavailable.
- [ ] **Step 7.3: Structured JSON Logging:**
  - Configure `structlog` in `src/observability/logger.py` for structured JSON output to stdout.
- [ ] **Step 7.4: FinOps Token & Cost Calculator:**
  - Implement `src/observability/cost_tracker.py` computing token usage via `tiktoken` and estimating exact USD costs ($C_{\text{LLM\_in}} + C_{\text{LLM\_out}}$).
- [ ] **Step 7.5: OpenTelemetry / Langfuse Tracing Adapter:**
  - Implement `src/observability/tracer.py` emitting OpenInference traces for tool invocations, latencies, and agent spans.

**Verification Checkpoint:**  
`pytest tests/integration/test_persistence.py` confirms state persistence, FinOps metrics calculation, and audit log generation.

---

## Phase 8: Ingress Interfaces (FastAPI & CLI), Test Matrix (TC-01..TC-12) & Hardened Release

**Entry Criteria:** Phases 1 through 7 complete.  
**Dependencies:** All previous phases.  
**Deliverables:** FastAPI REST API, Rich CLI runner, full qualification suite (TC-01 to TC-12), production Docker container.

- [ ] **Step 8.1: FastAPI REST Ingress:**
  - Implement `POST /agent/process`, `GET /health`, and `GET /agent/sessions/{session_id}` in `src/api/routes.py`.
  - Add API key authentication, CORS, error handling middleware, and dependency injection in `src/api/app.py`.
- [ ] **Step 8.2: Rich Terminal CLI Runner:**
  - Implement `src/cli.py` using Typer and Rich to process email files or interactive queries with formatted trace tables.
- [ ] **Step 8.3: Comprehensive Test Matrix Qualification (TC-01 to TC-12):**
  - Implement `tests/agent/test_scenarios.py` validating all 12 core test scenarios:
    - `TC-01`: Nominal delivered order query (1 tool call).
    - `TC-02`: Chained delivery delay slip computation.
    - `TC-03`: Eligible 14-day statutory return.
    - `TC-04`: Expired return request (>14 days) polite refusal.
    - `TC-05`: Missing order ID pre-extraction clarification.
    - `TC-06`: Unknown order ID (404) graceful response.
    - `TC-07`: PII email mismatch containment and human escalation.
    - `TC-08`: Indirect prompt injection attack neutralization.
    - `TC-09`: Upstream ERP outage with retry and circuit breaker fallback.
    - `TC-10`: Loop limit exceeded (3 iterations) graceful termination.
    - `TC-11`: Out-of-scope / hostile legal threat escalation.
    - `TC-12`: Schema deserialization validation failure handling.
- [ ] **Step 8.4: Multi-Stage Production Dockerfile:**
  - Create multi-stage `Dockerfile` with non-root user (`UID 10001`), optimized wheel caching, and final image size `< 250MB`.
- [ ] **Step 8.5: Quality Gate Verification & Documentation:**
  - Verify `mypy --strict` passes across all files.
  - Verify test suite passes with `pytest --cov=src --cov-fail-under=80`.
  - Produce operational `README.md` with usage instructions.

**Verification Checkpoint:**  
All 12 test scenarios pass; test coverage $\ge 80\%$; Docker container builds and boots healthy via `docker compose up`.
