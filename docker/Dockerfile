# Multi-stage non-root Dockerfile (< 250MB, UID 10001)
# Stage 1: Build & dependency resolution stage
FROM python:3.11-slim AS builder

WORKDIR /build

# Install poetry build tool
RUN pip install --no-cache-dir poetry==1.8.2

# Copy dependency specifications
COPY pyproject.toml README.md ./

# Install only production dependencies into system site-packages
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root --only main

# Stage 2: Minimal non-root production runtime stage
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

# Copy installed Python packages and binaries from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source code and seed data
COPY src/ ./src/
COPY data/ ./data/

# Set non-root ownership on application directory
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER 10001

EXPOSE 8000

# Healthcheck configuration
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').close()" || exit 1

# Production ASGI server launch
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
