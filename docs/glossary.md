# Technical Glossary: Customer Support Automation Agent

> **Scope:** Domain terms, architectural patterns, LLM orchestration principles, and FinOps concepts for `8_support_agent`.

---

## 🛠️ 1. Software & Architecture Patterns

### Exception Shielding
Pattern that wraps third-party or infrastructure exceptions into standardized application domain exceptions (`AppBaseError` derivatives) to prevent leaking implementation details across layer boundaries.

### Layer Isolation
Architectural boundary enforcement ensuring presentation, domain, infrastructure, and data layers maintain strict unidirectional dependencies. Core domain logic cannot import infrastructure or persistence modules.

### Mypy Strict Mode
Static analysis mode enforcing full type annotations across all functions and variables, disallowing untyped definitions, checking untyped decorators, and preventing any dynamic type escapes (`Any`).

### Zero Naked Crash Policy
Architectural rule prohibiting raw third-party exceptions (`httpx.HTTPError`, `redis.RedisError`, `psycopg2.Error`) from escaping module boundaries without being caught and mapped to domain errors.

### Fail-Fast Boundary Validation
Validating input schemas and payload contracts at the ingress boundary using Pydantic V2 immutable DTOs (`frozen=True, extra="forbid"`) before passing data to domain workflows.

### Modular Package Tree
Hierarchical directory structure separating system responsibilities into dedicated packages (`api`, `agent`, `domain`, `models`, `security`, `tools`, `clients`, `persistence`, `observability`, `core`) with explicit module contracts and strict downward dependency flow.

### Layer Isolation Guardrail
Static and dynamic verification rule forbidding core domain modules from importing or depending on infrastructure, persistence, or presentation modules.

### Mock ERP Seed Store
Deterministic local data fixture providing representative transactional business entities (`data/mock_orders.json`) for testing external ERP adapter integrations without live backend dependencies.

### Multi-Tenancy Tagging
Mandatory inclusion of an explicit tenant identifier (`tenant_id`) on all persistent data entities to guarantee logical data isolation across organizations.

### BaseSettings
Pydantic Settings model base class that automatically parses, validates, and populates application configuration from environment variables, `.env` files, and explicit keyword arguments.

### Configuration Immutability
Architectural constraint designating configuration objects as frozen post-instantiation (`frozen=True`), preventing runtime mutations across concurrent tasks and preserving system consistency.

### Configuration Shielding
Boundary defense technique that intercepts upstream schema deserialization and validation failures (`pydantic.ValidationError`) and re-raises domain-specific `ConfigurationError` instances.

### Multi-Stage Docker Build
Container optimization technique that separates build-time dependencies (compilers, packaging managers) from the final minimal runtime image.

### Unprivileged Container Execution
Security practice of executing containerized processes under a dedicated non-root user (e.g. UID 10001) to restrict system privileges and protect host kernels.

### Service Healthcheck Probing
Automated runtime inspection commands (e.g., `redis-cli ping`, `pg_isready`) periodically executed by container runtimes to assess service viability and gate startup dependencies.

### Named Volume Persistence
Docker storage mechanism decoupled from container lifecycles that preserves stateful database data across container restarts and updates.

---

## 🤖 2. Artificial Intelligence & Agentic Concepts

### ReAct Loop Throttling
Autonomous reasoning-action cycle bounded by a strict iteration limit ($N_{max} = 3$) to prevent infinite looping, excessive token expenditure, and latency runaway.

### Model Context Protocol (MCP) Runtime
Standardized protocol interface exposing tools with machine-readable schemas, runtime argument validation, and consistent execution contracts.

### Zero LLM Financial Authority
Strict business constraint ensuring all monetary values, cooling-off return windows, and compensation vouchers are calculated by deterministic Python domain code rather than probabilistic model outputs.

### Delimiter Encapsulation
Enclosing raw customer inputs within explicit XML tags (`<user_email>...</user_email>`) to neutralize prompt injection attacks and clarify boundary instructions to the LLM.

---

## 💰 3. FinOps & Observability

### FinOps Telemetry
Continuous tracking of prompt tokens, completion tokens, execution duration, and estimated USD expenditure for every agent invocation.

### Idempotency Caching
Hashing tool execution contexts (`SHA-256(session_id + tool_name + sorted_args)`) in Redis with a 15-minute TTL to prevent redundant executions and optimize resource usage.

---

## 📋 4. Domain Contracts & Business Enums

### BaseDTO
Root immutable Pydantic V2 model enforcing `frozen=True` and `extra="forbid"`, guaranteeing zero runtime mutation, hashability, and strict contract adherence across boundaries.

### StrEnum
Python 3.11+ string-backed enumeration whose members inherit directly from `str`, providing seamless JSON serialization and strict static typing without manual `.value` indirection.

### OrderStatusEnum
Core domain enumeration capturing carrier and ERP shipment lifecycle states (PENDING, PROCESSING, SHIPPED, IN_TRANSIT, DELIVERED, DELAYED, CANCELLED, RETURNED, UNKNOWN).

### IntentEnum
Domain classification taxonomy for customer queries (ORDER_STATUS, DELIVERY_DELAY, REFUND_REQUEST, ORDER_INFORMATION, MIXED_QUERY, OUT_OF_SCOPE, INFORMATION_MISSING).

### RefundReasonCode
Machine-readable qualification codes explaining statutory cooling-off eligibility or express delay vouchers (WITHIN_LEGAL_TIMEFRAME, TIMEFRAME_EXCEEDED, NOT_DELIVERED_YET, EXPRESS_DELAY_COMPENSATED).

### ResolutionStatusEnum
Terminal operational classification for customer requests indicating automatic resolution or human escalation (RESOLVED_AUTOMATICALLY, REQUIRES_HUMAN_REVIEW).

---

## 📨 5. Ingestion & Extraction Schemas

### InboundEmailMessage
Boundary DTO encapsulating raw, validated incoming customer emails with RFC-compliant email syntax and non-empty content constraints.

### ExtractedDemand
Structured domain entity extracted from customer communications representing intent, order ID, verified customer email, legal threat flag, and sub-queries.

### EmailStr
Pydantic V2 specialized type providing RFC 5322 email syntax validation at ingress boundary deserialization.

### Order ID Regex
Anchored regular expression (`^CMD-[0-9]{5,8}$`) enforcing ERP-compliant order identifiers before tool dispatch.

### Deep Immutability
Architectural design ensuring that both the top-level model and all nested composite collections (such as tuples over lists) are immutable post-instantiation.

---

## 🔧 6. Tool Execution & Observability Schemas

### OrderDetailsResult
Normalized logistical and financial snapshot DTO returned by order query tools, encapsulating lifecycle statuses, carrier tracking, and cents-based monetary totals.

### RefundEligibilityResult
Deterministic output DTO of statutory return evaluation expressing eligibility, elapsed calendar days, refundable item totals, delay vouchers, and machine-readable reason code.

### DeliveryDelayResult
Logistical computation DTO quantifying delivery delay in calendar days and flagging delay status.

### ToolExecutionResult
Generic shielded result envelope returned by all MCP-compatible tools, providing standardized success status, payload data, and machine-readable error codes.

### ToolCallTrace
Immutable audit trail DTO recording a discrete tool invocation with unique call ID, input arguments, execution result, timestamp, and millisecond latency.

---

## 🛡️ 7. Exception Shielding & Error Taxonomy

### SupportAgentBaseError
Root domain exception class for the support agent system, establishing standardized message handling and machine-readable error_code taxonomy.

### AppBaseError
Universal engineering architecture alias for SupportAgentBaseError, providing cross-repo consistency with Pax engineering standards.

### SecurityAccessError
Domain exception raised when an operation violates security policy, PII ownership verification, or cross-tenant isolation boundaries.

### ToolExecutionError
Domain exception raised when an internal or external tool adapter fails during invocation, carrying the specific tool_name.

### FSMStateError
Domain exception raised when an invalid or forbidden state transition is requested in the agent lifecycle controller.

### CircuitBreakerError
Resilience domain exception raised when repeated upstream service failures trip the circuit breaker.

### OrderNotFoundError
Domain exception raised when an order lookup cannot locate a record in the ERP store, preserving the queried order_id.

---

## 🎯 8. Final Certified Response & Escalation Schemas

### AgentFinalResponse
Certified output DTO emitted upon session completion, encapsulating resolution status, customer email body, internal diagnostics, escalation reasoning, and FinOps telemetry.

### Cross-Field Model Validation
Post-validation technique (`@model_validator(mode="after")`) enforcing interdependent field constraints, such as requiring non-empty human escalation reasons when human review is indicated.

### Executive Diagnostic Summary
Bounded string representation (`max_length=250`) within the response contract providing condensed internal technical context for support supervisors and audit logs.

### Confidence Score Invariant
Strict floating-point constraint ($0.0 \le \text{confidence} \le 1.0$) evaluating agent decision certainty before finalizing automatic customer responses.
