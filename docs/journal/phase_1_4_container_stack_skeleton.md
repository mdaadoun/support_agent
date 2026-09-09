# Session 1.4: Container Stack Skeleton
**Date:** 2026-09-09

*Engineered the containerized production stack skeleton comprising a multi-stage non-root Dockerfile (< 250MB, UID 10001) and Docker Compose orchestration wiring FastAPI, Redis 7 Alpine, and PostgreSQL 15 Alpine with healthchecks and volume persistence.*

---

### 1. 🎓 Concepts Introduced
- **Multi-Stage Docker Build:** Separating build tooling (Poetry, compiler wheels) from minimal slim runtime stage to minimize image surface area and attack vector.
- **Unprivileged Container Hardening:** Enforcing non-root container runtime using dedicated UID/GID 10001 (`appuser`/`appgroup`) satisfying principle of least privilege.
- **Healthcheck Dependency Orchestration:** Wiring `depends_on` with `condition: service_healthy` to ensure API only boots once Redis and PostgreSQL backends are fully operational.
- **Isolated Bridge Networking & Named Volumes:** Isolating inter-container communication on `support_network` and persisting database state in `postgres_data`.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Multi-Stage Non-Root Docker Image (UID 10001)
- **Option 1:** Single-stage root-privileged Python image with development dependencies bundled.
- **Option 2 (Selected):** Two-stage build discarding Poetry in final stage, running under UID 10001 (`< 250MB`).
- **Rationale:** Mitigates container breakout vulnerabilities, eliminates compiler tools from runtime attack surface, and reduces deployment footprint to under 250MB.

#### Decision: Healthcheck-Gated Service Dependencies
- **Option 1:** Simple `depends_on` list without healthchecks leading to startup race conditions.
- **Option 2 (Selected):** Comprehensive healthchecks (`redis-cli ping`, `pg_isready`) coupled with `condition: service_healthy`.
- **Rationale:** Prevents ASGI server crash loops on boot caused by upstream databases still initializing sockets.

---

### 3. 🛠️ Implementation & Code
*Implementation details, orchestration snippets, and validation commands.*

```yaml
# docker/docker-compose.yml
services:
  api:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: support_agent_api
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **Configured `docker/Dockerfile` with multi-stage build, non-root user (`appuser`, UID 10001), healthcheck on `/health`, and optimized layer caching.**
2. [x] **Configured `docker/docker-compose.yml` declaring `api`, `redis:7-alpine`, and `postgres:15-alpine` services on dedicated `support_network` bridge.**
3. [x] **Configured healthcheck probes and `service_healthy` dependencies for deterministic container initialization.**
4. [x] **Configured `postgres_data` named volume for durable database state persistence.**
5. [x] **Implemented comprehensive unit test suite in `tests/unit/test_container_stack.py` verifying compose syntax, service declarations, healthchecks, network/volume wiring, and Dockerfile security hardening.**
6. [x] **Verified clean pass on `make lint`, `make typecheck`, and `make test`.**
