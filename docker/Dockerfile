# Multi-stage non-root Dockerfile (< 250MB, UID 10001)
# Stage 1: Build & dependency resolution stage with optimized wheel caching
FROM python:3.11-slim AS builder

WORKDIR /build

# Configure environment for deterministic dependency compilation
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install poetry build tool and export plugin
RUN pip install --no-cache-dir poetry==1.8.2 poetry-plugin-export

# Copy dependency specifications
COPY pyproject.toml poetry.lock* README.md ./

# Export locked production dependencies and compile wheels into /build/wheels
RUN if [ ! -f poetry.lock ]; then poetry lock --no-update 2>/dev/null || poetry lock; fi \
    && poetry export -f requirements.txt --output requirements.txt --without-hashes --only main \
    && pip wheel --no-cache-dir --wheel-dir=/build/wheels -r requirements.txt

# Stage 2: Minimal non-root production runtime stage (< 250MB)
FROM python:3.11-slim AS runtime

# Security hardening: Create dedicated non-root user and group with UID/GID 10001
RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -s /bin/false -M appuser

WORKDIR /app

# Environment variables for optimized container execution
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src:/app \
    PORT=8000 \
    HOST=0.0.0.0

# Copy pre-compiled binary wheels from builder stage
COPY --from=builder /build/wheels /wheels

# Install production wheels in runtime environment and purge wheel cache
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl \
    && rm -rf /wheels

# Copy application source code and seed data
COPY src/ ./src/
COPY data/ ./data/

# Set non-root ownership on application directory
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER 10001

EXPOSE 8000

# Healthcheck configuration using native Python urllib
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').close()" || exit 1

# Production ASGI server launch
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
