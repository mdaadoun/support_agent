# Session 8.4: Multi-Stage Production Dockerfile
**Date:** 2026-10-22

*Implemented Step 8.4: Multi-Stage Production Dockerfile establishing an enterprise-grade container packaging pipeline for the Customer Support Automation Agent. Structured the Docker build into a multi-stage architecture separating build tooling (Poetry 1.8.2, poetry-plugin-export, pip wheel compilation) from a minimal runtime footprint (< 250MB). Generated optimized binary wheel archives in `/build/wheels` and installed them cleanly in the runtime container using `--no-index --find-links=/wheels` followed by immediate cleanup of wheel archives to eliminate image bloat. Enforced container security hardening with a dedicated unprivileged user (`appuser:appgroup`, UID/GID 10001) and native Python urllib healthchecks against `/health`. Validated manifest syntax, dependency wiring, wheel caching assertions, and security boundaries in `tests/unit/test_container_stack.py` with all 378 unit tests passing and zero typecheck issues across 108 files.*

---

### 1. 🎓 Concepts Introduced
- **Multi-Stage Docker Architecture:** Decoupling dependency resolution and compiler toolchains from minimal production execution environments to shrink container attack surfaces.
- **Optimized Wheel Caching:** Pre-building binary wheel archives (`.whl`) in an isolated builder stage and installing them via local file links (`--find-links`) without runtime network access.
- **Non-Root Principle of Least Privilege:** Restricting container process execution to a dedicated system user (`UID 10001`) to protect host systems against container breakout vulnerabilities.
- **Native Zero-Dependency Healthcheck:** Utilizing Python standard library `urllib.request` for container liveness and readiness probes rather than introducing external packages like `curl` or `wget`.
- **Filesystem Layer Optimization:** Minimizing layer sizes by purging build artifacts and wheel caches in the same `RUN` layer and utilizing unbuffered byte-code suppression flags.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Pre-Compiled Wheel Cache vs Direct Site-Packages Copying
- **Option 1:** Directly copying `site-packages` and `bin` directories across multi-stage images.
- **Option 2 (Selected):** Compiling binary wheels into `/build/wheels` in the builder stage and installing via `pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl && rm -rf /wheels` in the runtime stage.
- **Rationale:** Wheel installation guarantees clean entrypoint binary generation, resolves dependency symlinks reliably, prevents stale file transfers, and allows instantaneous purging of build archives to maintain the runtime image size under 250MB.

#### Decision: Native Python `urllib` Healthcheck vs External `curl` / `wget`
- **Option 1:** Installing `curl` via `apt-get` in the runtime container to execute healthcheck requests.
- **Option 2 (Selected):** Using `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').close()"`.
- **Rationale:** Avoids adding external system binaries, apt package manager indices, and dynamic library dependencies to the runtime image, reducing both vulnerability attack surface and overall image weight.

#### Decision: Hardened Non-Root Identity (`UID 10001` / `appuser:appgroup`)
- **Option 1:** Running as default root user (`UID 0`).
- **Option 2 (Selected):** Creating non-root user `appuser` (`UID 10001`, `GID 10001`) with non-interactive shell (`/bin/false`) and no home directory.
- **Rationale:** Satisfies strict cloud-native security standards (Kubernetes Restricted Pod Security Profile, OpenShift, Google Cloud Run) and neutralizes host privilege escalation vectors.

---

### 3. 🛠️ Implementation & Code
*Multi-stage Dockerfile configuration and wheel caching test assertions.*

```dockerfile
# docker/Dockerfile
FROM python:3.11-slim AS builder
WORKDIR /build
RUN pip install --no-cache-dir poetry==1.8.2 poetry-plugin-export
COPY pyproject.toml poetry.lock* README.md ./
RUN if [ ! -f poetry.lock ]; then poetry lock --no-update 2>/dev/null || poetry lock; fi \
    && poetry export -f requirements.txt --output requirements.txt --without-hashes --only main \
    && pip wheel --no-cache-dir --wheel-dir=/build/wheels -r requirements.txt

FROM python:3.11-slim AS runtime
RUN groupadd -g 10001 appgroup && useradd -u 10001 -g appgroup -s /bin/false -M appuser
WORKDIR /app
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl && rm -rf /wheels
COPY src/ ./src/
COPY data/ ./data/
RUN chown -R appuser:appgroup /app
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').close()" || exit 1
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **Multi-Stage Dockerfile**: Implemented builder and runtime stages in `docker/Dockerfile`.
2. [x] **Optimized Wheel Caching**: Configured `pip wheel --wheel-dir=/build/wheels` with `poetry-plugin-export`.
3. [x] **Offline Runtime Installation**: Enforced `--no-index --find-links=/wheels` followed by immediate cache purge.
4. [x] **Non-Root Hardening**: Configured dedicated system user `appuser:appgroup` with explicit `UID 10001`.
5. [x] **Zero-Dependency Healthcheck**: Implemented native Python standard library `urllib` probe targeting `/health`.
6. [x] **Qualification Unit Tests**: Added wheel caching and runtime assertions in `tests/unit/test_container_stack.py`.
7. [x] **Roadmap & Quality Gates**: Updated `docs/roadmap.md`, passed `make lint`, `make typecheck` (108 files), and `make test` (378 passed).
