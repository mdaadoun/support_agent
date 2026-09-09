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

---

### Q4: Why is strict layer isolation (domain never importing infrastructure) essential in an AI agent architecture?
**Answer:**
In agentic systems, infrastructure components (LLM clients, tool wrappers, vector databases, HTTP ERP APIs) are prone to frequent API updates, transient outages, and vendor changes. If core domain rules (such as 14-day cooling-off calculations or order state machines) directly imported infrastructure modules, any external change would ripple into business logic, making unit testing fragile and requiring external mocks for pure math operations. Isolating the domain keeps business logic pure, deterministic, and 100% testable in isolation.

---

### Q5: How does pre-populating mock ERP seed data with explicit scenario states (delayed, returned, cancelled) protect the ReAct agent qualification pipeline?
**Answer:**
Autonomous agents require rigorous qualification across both nominal paths (on-time delivery) and edge cases (lost packages, express delays, return window expirations). Pre-populating deterministic order records with known timestamps and item details allows test fixtures to assert exact deterministic tool outputs, verifying that the ReAct loop and FSM controller transition to expected states without stochastic variability.

---

### Q6: Why enforce a 250 LOC limit per file, and how is it tested automatically?
**Answer:**
A hard 250 LOC limit prevents bloated "God objects" and encourages single-responsibility modules, improving readability, maintainability, and code review efficiency. It is automatically tested via unit tests (`test_file_loc_limits_guardrail`) that traverse all repository Python source files and assert line count boundaries, failing CI if any file grows beyond the modular threshold.

---

### Q7: Why should configuration models in an autonomous agent architecture be frozen (`frozen=True`) rather than mutable?
**Answer:**
In asynchronous, multi-step agentic systems (such as ReAct loops with concurrent tool dispatches), configuration instances are shared across multiple concurrent tasks, coroutines, and workers. Making settings mutable introduces race conditions, unexpected side-effects, and potential prompt/credential injection vectors if any component inadvertently alters a parameter (like `agent_max_iterations` or `llm_temperature`). Freezing the model via `SettingsConfigDict(frozen=True)` ensures deterministic, tamper-proof execution throughout the application lifecycle.

---

### Q8: Why is a multi-stage Docker build critical for deploying Python AI agent services to production?
**Answer:**
Python applications often require build tools (Poetry, compilers, header files) to resolve and compile dependencies during installation. Leaving these packaging utilities in the production runtime image balloons image size and introduces critical attack vectors. A multi-stage build compiles dependencies in a builder stage and copies only the resulting site-packages and app source into a clean `python:3.11-slim` runtime image, maintaining a compact footprint (`< 250MB`) and hardened attack surface.

---

### Q9: Why enforce execution under a dedicated non-root UID (10001) inside the container?
**Answer:**
By default, containers execute as the root user (`UID 0`). In the event of an application exploit or container escape, an attacker would immediately gain root privileges on the container and potentially the host kernel. Creating an unprivileged user (`UID 10001`) and declaring `USER 10001` enforces defense-in-depth and the principle of least privilege, strictly confining compromised processes to unprivileged access.

---

### Q10: How does `condition: service_healthy` in Docker Compose prevent startup race conditions in distributed agent pipelines?
**Answer:**
Standard `depends_on` only waits until the dependency container process launches, which occurs well before the database engine binds sockets and accepts network connections. Using `condition: service_healthy` coupled with active healthcheck probes (such as `pg_isready` or `redis-cli ping`) ensures that the FastAPI application container is held back until PostgreSQL and Redis have verified internal operational readiness, eliminating transient startup connection failures.
