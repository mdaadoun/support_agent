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
