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

---

## ⚖️ 9. Deterministic Domain Rules & Statutory Consumer Rights

### Statutory Withdrawal Right (14-Day Rule)
Legal cooling-off right established under EU Directive 2011/83/EU entitling consumers to withdraw from a distance sales contract within 14 calendar days of acquiring physical possession of goods.

### Exact Calendar Day Computation
Deterministic date arithmetic computing elapsed full days between UTC-normalized calendar dates (`(date2 - date1).days`) rather than 24-hour seconds intervals or floating-point timestamps.

### Zero LLM Financial Authority
Architectural principle prohibiting large language models from deciding financial amounts, approving refunds, or generating vouchers without backing deterministic tool execution payloads.

### RefundReasonCode.NOT_DELIVERED_YET
Machine-readable domain classification indicating an order is either not yet delivered (`delivery_date` is `None`) or the inquiry was filed prior to confirmed delivery.

### BusinessRuleViolationError
Domain exception subclassing `AppBaseError` raised when domain invariants or boundary constraints (e.g. non-negative monetary figures, strict datetime types) are breached.

### Shipping Delay Drift
The non-negative count of calendar days elapsed between a carrier's promised estimated delivery date and the reference or actual delivery date.

### Express Compensation Voucher
Commercial goodwill voucher credit equal to 100% of the customer's shipping fee, granted automatically when an express shipment is delayed by more than 5 calendar days.

### Commercial Policy Threshold (delay_days > 5)
Deterministic business rule boundary establishing that only express shipment delays strictly exceeding 5 full calendar days qualify for shipping fee reimbursement vouchers.

### RefundReasonCode.EXPRESS_DELAY_COMPENSATED
Machine-readable domain classification indicating that while an order's statutory return window has expired or is undelivered, the customer qualifies for an express shipping delay compensation voucher.

---

## 🔌 10. ERP Integration & Resilient Adapters

### Mock ERP Client Adapter
Infrastructure client module (`src/clients/erp_client.py`) simulating enterprise resource planning (ERP) logistics queries against local JSON storage (`data/mock_orders.json`) with retry resilience.

### Transient Error Discrimination
Inspection technique (`is_retryable_exception`) identifying recoverable I/O faults (timeouts, connection resets) while bypassing permanent domain errors (e.g. `OrderNotFoundError`).

### CircuitBreakerError Chaining
Architecture error shielding pattern where persistent upstream failure causes (`ConnectionError`, `TimeoutError`) are chained to `CircuitBreakerError` via `from exc` to preserve debugging context without leaking naked exceptions.

### Network Failure Simulation Hook
Internal client mechanism (`simulate_transient_network_failure`) allowing test harnesses to inject controllable network interruptions to verify retry recovery and circuit breaker tripping.

---

## 🛡️ 11. Security, Input Sanitization & XML Delimitation

### XML Boundary Delimitation
A defensive prompt containment technique that wraps untrusted user input within well-defined XML tags (`<user_email>...</user_email>`) in all LLM system and agent prompts, establishing an explicit structural boundary between trusted system instructions and untrusted external data.

### Control Character Scrubbing
The systematic removal of non-printable ASCII control codes (C0/C1) and Unicode format characters (such as zero-width spaces and bidirectional overrides) from untrusted inputs to prevent visual deception, terminal escape injection, and regex evasion.

### Nested Tag Spoofing
An adversarial prompt injection vector where an attacker crafts nested, partial, or malformed XML tags (e.g., `</user_email>` or `<system>`) inside the user input to escape designated data boundaries and inject rogue operational instructions into the model context.

### Trojan Source / Bidi Overrides
Unicode control characters (such as U+202E Right-to-Left Override) that manipulate the visual rendering order of text without altering the logical byte sequence, used by attackers to disguise malicious payloads as benign phrases.

### Fixed-Point Tag Sanitization
The iterative application of tag removal rules until the payload reaches a steady state where no further prohibited delimiters exist, defeating recursive evasion techniques.

### Passive Input Framing
A core architectural constraint instructing the LLM that content inside specified XML tags must be treated strictly as passive semantic information rather than executable commands or operational authority.

### Regex Entity Extraction
Deterministic pre-LLM parsing technique using regular expressions to extract structured business entities (order identifiers, email addresses) from unstructured text with zero latency and zero hallucination risk.

### Lookaround Boundary Guard
Regular expression technique using negative lookbehind (`(?<!...)`) and lookahead (`(?!...)`) assertions to prevent accidental partial matches inside longer tokens or hyphenated compound words.

### Canonical Entity Normalization
The transformation of extracted entity representations into a standard canonical form (e.g. uppercase order codes, lowercase RFC email addresses) at the ingestion boundary.

### ExtractedEntities DTO
An immutable Pydantic transfer object holding parsed order identifiers and customer email addresses, maintaining both primary single-value fields and complete tuple collections.

### Strict Format Verification Predicate
Boolean validator function (`is_valid_order_id`, `is_valid_email`) asserting that an entire candidate string strictly matches a domain specification from start to end (`^...$`).

### PII Access Control Guard
A defensive security boundary module enforcing strict cross-authorization by verifying that the authenticated sender's identity matches the customer record associated with a queried entity.

### Fail-Closed Metadata Containment
A security design principle ensuring that when an authorization check fails, the system terminates access immediately and withholds all entity metadata, customer identities, or state details from the response.

### Cross-Authorization Verification
The validation that an authenticated user possesses explicit ownership or authorized access rights to an individual entity (e.g. order) rather than merely possessing a valid user account.

### Tool Execution Shielding
An architectural pattern where security violations or execution failures within tools return a structured, machine-readable result payload (`ToolExecutionResult(success=False, error_code=...)`) rather than crashing the calling agent loop with an unhandled exception.

### Opaque Security Error
A sanitized error response that communicates access rejection without revealing internal system state, owner identities, or whether a queried entity even exists.

### Pre-Flight Intent Classification
Deterministic parsing and categorization of inbound customer communications prior to invoking LLM reasoning loops or external tool interfaces.

### Missing Information Short-Circuiting
A defensive pattern classifying an inquiry as `INFORMATION_MISSING` when required identifiers (such as `order_id`) are absent, halting tool execution immediately.

### Hostile Legal Threat Escort
Security guard mechanism flagging litigation threats, legal notices, and aggressive hostility (`is_legal_threat_or_aggressive=True`) to route inquiries directly to human counsel without tool calls.

### Intent Family Grouping
The architectural organization of granular intents into domain clusters (Logistics, Refunds, Documentation) to evaluate query complexity and discern true `MIXED_QUERY` occurrences.

### Sub-Query Decomposition
The process of splitting multi-intent inquiries into isolated, ordered sub-queries preserved in an immutable tuple for structured downstream resolution.

### Zero-Tool Pre-Extraction Gate
A security and performance guardrail preventing unserviceable, out-of-scope, or incomplete customer inquiries from executing downstream backend or agent tools.



