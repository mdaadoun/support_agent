# Technical Interview & Architecture FAQ: Customer Support Automation Agent

> **Overview:** Core architectural decisions, technical trade-offs, and design interview questions for `8_support_agent`.

---

### Q1: Why enforce `model_config = ConfigDict(frozen=True, extra="forbid")` across domain models rather than standard mutable dataclasses?
**Answer:**
Freezing models (`frozen=True`) guarantees immutability, preventing accidental state mutations across asynchronous agent and tool execution boundaries. Forbidding extra fields (`extra="forbid"`) eliminates silent schema drift, protects against unexpected parameter injection during deserialization, and forces strict contract adherence between system layers.

---

### Q2: What is the rationale behind strict exception shielding via `AppBaseError`?
**Answer:**
Allowing raw third-party library exceptions (such as `httpx.HTTPStatusError` or `redis.RedisError`) to escape infrastructure boundaries leaks underlying implementation details into agent domain logic and presentation layers. Wrapping all failures into domain-specific subclasses of `AppBaseError` (e.g., `OrderNotFoundError`, `ToolExecutionError`) enforces the "Zero Naked Crash" policy, normalizes machine-readable error codes for logging and telemetry, and guarantees predictable recovery pathways for the FSM lifecycle controller.

---

### Q3: How do Ruff rules (E, F, B, SIM, I) and Mypy strict mode complement Pydantic runtime validation?
**Answer:**
Ruff and Mypy operate statically at build time and in pre-commit hooks, verifying type soundness, syntax conformance, code complexity simplifications, and clean import ordering across the codebase. Pydantic validates runtime payloads at system boundaries when untrusted external inputs arrive. Together, they establish defense-in-depth: static checks prevent internal programming flaws from being deployed, while runtime schemas guarantee that external data adheres strictly to business contracts.
