# Session 8.1: FastAPI REST Ingress
**Date:** 2026-10-22

*Implemented Step 8.1: FastAPI REST Ingress establishing a hardened, production-grade presentation boundary for the Customer Support Automation Agent. Created `AgentService` in `src/api/service.py` to orchestrate multi-tenancy validation, pre-extraction intent parsing, ReAct reasoning loop execution, session persistence, and audit logging while maintaining strict Clean Architecture layer isolation. Configured type-safe dependency injection providers in `src/api/dependencies.py` for API key authentication (`verify_api_key`), tenant scoping (`get_tenant_id`), session caching (`get_session_store`), audit logging (`get_audit_repository`), and reasoning engine assembly (`get_agent_service`). Engineered dual-tier error shielding in `src/api/middleware.py` with custom exception handlers and an outermost ASGI `ErrorHandlingMiddleware` mapping domain exceptions (`SecurityAccessError`, `SessionNotFoundError`, `BusinessRuleViolationError`, `OrderNotFoundError`, etc.) to HTTP status codes with zero raw stack trace leakage. Implemented REST route handlers in `src/api/routes.py` for `GET /health` (`HealthResponse` with `frozen=True, extra="forbid"`), `POST /agent/process` (`AgentFinalResponse`), and `GET /agent/sessions/{session_id}` (`AgentSessionSnapshot`). Updated `src/api/app.py` with CORS, error middleware, lifespan logging, and settings dependency overrides. Created `APIAuthenticationError` in `src/core/exceptions.py` and `api_key` in `src/core/config.py`. Verified with 17 new unit tests in `tests/unit/test_api_ingress.py` and `tests/unit/test_api_middleware.py`, full test suite pass (353 passed, 100% success), and `mypy --strict` compliance across 102 source files.*

---

### 1. 🎓 Concepts Introduced
- **Clean Architecture Presentation Boundary**: Decoupling the HTTP transport layer (`routes.py`) from domain reasoning and persistence by routing requests through an application coordinator (`AgentService`), preventing presentation logic from directly querying databases or driving multi-turn LLM loops.
- **Dual-Tier Exception Shielding**: Multi-layered defense-in-depth error handling combining framework-level exception handlers (for route and validation exceptions) with an outermost ASGI middleware (`ErrorHandlingMiddleware`) to guarantee zero raw runtime crashes or internal traceback leakage.
- **Tenant Boundary Partitioning**: Enforcing strict multi-tenancy at API ingress via the `X-Tenant-ID` header, guarded by strict regex boundary validation (`^[a-zA-Z0-9_\-]+$`) before scoping data store keys (`session:{tenant_id}:{session_id}`).
- **Multi-Scheme API Key Shielding**: Authentication provider supporting both custom header (`X-API-Key`) and standard bearer tokens (`Authorization: Bearer <key>`) with fail-closed security when configured, while allowing graceful unauthenticated access in default development/test environments.
- **FastAPI Inversion of Control & Dependency Injection**: Modular dependency graph (`api.dependencies`) allowing clean overrides during automated testing via `app.dependency_overrides` without patching global state or mocking low-level HTTP clients.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Decoupled Application Service (`AgentService`) vs. Direct Route Handler Orchestration
- **Option 1:** Orchestrating pre-extraction, ReAct loop execution, Redis session caching, and PostgreSQL audit logging directly inside `routes.py` endpoint functions.
- **Option 2 (Selected):** Introducing `AgentService` in `src/api/service.py` as a dedicated Application Service, while route handlers focus solely on HTTP serialization, status codes, and dependency resolution.
- **Rationale:** Strictly complies with Pax Universal Engineering Guardrails and Clean Architecture layer isolation. Direct DB or reasoning calls from the Presentation layer are prohibited. `AgentService` provides a reusable orchestration interface that will also power the Rich CLI runner in Step 8.2.

#### Decision: Dual-Tier Error Shielding vs. Single Framework Exception Handler
- **Option 1:** Relying exclusively on FastAPI's `@app.exception_handler` decorators.
- **Option 2 (Selected):** Combining FastAPI exception handlers for domain and Pydantic validation errors with an outermost ASGI `ErrorHandlingMiddleware`.
- **Rationale:** Framework exception handlers only catch exceptions within Starlette's route execution context. Exceptions triggered within middleware or before route dispatch can escape and emit raw 500 HTML tracebacks. An outer ASGI middleware ensures 100% exception shielding ("Zero Naked Crash").

#### Decision: Boundary Regex Validation on Partition Keys vs. Raw Parameter Acceptance
- **Option 1:** Passing incoming `session_id` and `tenant_id` strings directly to persistence stores.
- **Option 2 (Selected):** Enforcing strict pre-execution regex checks (`^[a-zA-Z0-9_\-]+$`) in `AgentService`, rejecting invalid identifiers with `BusinessRuleViolationError` (HTTP 422).
- **Rationale:** Protects Redis and persistent stores against directory traversal, Redis delimiter injection (`session:tenant:id:malicious`), and database injection attacks, upholding Zero Trust I/O principles.

---

### 3. 🛠️ Implementation & Code
*Application service orchestration and dependency injection setup.*

```python
# src/api/service.py
class AgentService:
    """Application service coordinating agent execution, persistence, and audit logging."""

    def __init__(
        self,
        engine: ReActLoopEngine | None = None,
        session_store: SessionStateStore | None = None,
        audit_repo: AuditLogRepository | None = None,
    ) -> None:
        self.engine = engine or ReActLoopEngine()
        self.session_store = session_store or SessionStateStore()
        self.audit_repo = audit_repo or AuditLogRepository()

    async def process_email(
        self,
        message: InboundEmailMessage,
        tenant_id: str,
        session_id: str | None = None,
    ) -> AgentFinalResponse:
        self.validate_tenant_id(tenant_id)
        sid = session_id or f"SESS-{uuid.uuid4().hex[:8].upper()}"
        session = create_session(sid, message, tenant_id=tenant_id)
        session.extracted_demand = classify_inbound_demand(message)

        response = await self.engine.run(session)
        self.session_store.save(session)
        self.audit_repo.save_response(
            response=response,
            tenant_id=tenant_id,
            message_id=message.message_id,
            customer_email=str(message.sender_email),
        )
        return response
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **FastAPI REST Ingress Routes**: Implemented `POST /agent/process`, `GET /health`, and `GET /agent/sessions/{session_id}` in `src/api/routes.py`.
2. [x] **Application Service Layer**: Built `AgentService` in `src/api/service.py` managing multi-tenancy, execution, and persistence.
3. [x] **Dependency Injection Providers**: Created `src/api/dependencies.py` for API key authentication, tenant resolution, and singleton store injection.
4. [x] **Error Handling Middleware**: Created `src/api/middleware.py` mapping domain errors to HTTP status codes with ASGI fallback shielding.
5. [x] **Security & Authentication**: Implemented API key header validation (`X-API-Key`, `Bearer`) and domain error `APIAuthenticationError`.
6. [x] **Comprehensive Test Suite**: Added 17 unit tests in `tests/unit/test_api_ingress.py` and `tests/unit/test_api_middleware.py`.
7. [x] **Strict Verification**: Passed `make lint`, `make typecheck` (`mypy --strict`, 102 files), and `make test` (353 passed).
