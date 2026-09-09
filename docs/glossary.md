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
