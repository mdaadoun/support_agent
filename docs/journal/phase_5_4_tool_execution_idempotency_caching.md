# Session 5.4: Tool Execution Idempotency Caching
**Date:** 2026-09-28

*Implemented tool execution idempotency caching in `src/persistence/cache.py` and integrated it into `ToolRegistry.execute()` in `src/tools/registry.py`. Computed deterministic SHA-256 hash keys across `session_id`, `tool_name`, and sorted arguments with ISO 8601 datetime serialization. Implemented Redis storage with 15-minute TTL (`SET key payload EX 900 NX`), in-memory TTL eviction fallback, and `ToolExecutionResult` serialization. Added complete unit (`tests/unit/test_cache.py`) and runtime integration test suites (`tests/integration/test_tools_runtime.py`).*

---

### 1. 🎓 Concepts Introduced
- **Deterministic Idempotency Key Hashing:** Generating SHA-256 digests over `f"{session_id}:{tool_name}:{normalized_args}"` with key sorting and ISO 8601 datetime serialization to prevent duplicate tool execution across conversational turns.
- **Redis Backend with NX/EX Semantics:** Utilizing `SET key payload EX 900 NX` for distributed atomicity and 15-minute TTL expiration.
- **Two-Tier Cache Degradation:** Primary Redis store with automatic, transparent in-memory fallback upon network timeouts or connection drops ("Zero Naked Crash").
- **Active In-Memory TTL Eviction:** Associating timestamp expiration with in-memory entries and pruning stale items on access.
- **ToolExecutionResult JSON Serialization:** Preserving type-safe DTO structures across cache boundaries via `model_dump_json()` and `model_validate_json()`.
- **Registry-Level Transparent Interception:** Checking cache keys before dispatch and caching successful outputs directly in `ToolRegistry.execute()`.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Two-Tier Fault-Tolerant Cache Architecture (Redis + Memory Fallback)
- **Option 1:** Hard dependency on Redis requiring network connectivity and failing when Redis is unreachable.
- **Option 2 (Selected):** Two-tier cache attempting Redis operations with immediate, silent fallback to in-memory store on connection or timeout errors.
- **Rationale:** Guarantees Zero Naked Crash and uninterrupted service availability in local test environments, CI pipelines, and during transient infrastructure outages.

#### Decision: Deterministic JSON Argument Normalization with Custom Serializer
- **Option 1:** Standard `json.dumps` without type handling, crashing on datetime objects.
- **Option 2 (Selected):** `json.dumps` with `sort_keys=True` and a custom serializer converting datetimes to ISO 8601 strings and Pydantic models to JSON dicts.
- **Rationale:** Ensures identical hash keys regardless of argument dictionary key order and prevents serialization exceptions on date/datetime parameters used in domain tools.

#### Decision: Caching Confined to Successful Tool Executions
- **Option 1:** Caching all tool execution results including transient network or circuit breaker failures.
- **Option 2 (Selected):** Caching strictly when `result.success is True`.
- **Rationale:** Prevents caching transient infrastructure dropouts or authorization rejections, allowing immediate retries while eliminating duplicate expensive operations on successful calls.

#### Decision: Transparent Registry-Level Idempotency Interception
- **Option 1:** Requiring each tool subclass to manage its own caching logic inside `_run()`.
- **Option 2 (Selected):** Centralizing cache lookup and population inside `ToolRegistry.execute()` using optional `session_id`.
- **Rationale:** Preserves single-responsibility principle: tools remain pure business logic adapters, while caching, shielding, and metrics are handled at the catalog orchestration layer.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/persistence/cache.py
class IdempotencyCache:
    """Thread-safe idempotency caching backed by Redis with memory fallback."""

    @staticmethod
    def compute_key(session_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
        normalized_args = json.dumps(
            arguments, sort_keys=True, default=_json_serializer
        )
        raw_key = f"{session_id}:{tool_name}:{normalized_args}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        client = self._get_redis()
        if client is not None:
            try:
                val = client.get(f"idempotency:{key}")
                if val is not None:
                    return str(val)
            except Exception as exc:
                logger.warning("redis_get_error", key=key, error=str(exc))

        entry = self._in_memory_store.get(key)
        if entry is None:
            return None
        payload, expires_at = entry
        if time.time() > expires_at:
            self._in_memory_store.pop(key, None)
            return None
        return payload

    def set(self, key: str, payload: str, ttl_seconds: int | None = None) -> bool:
        ttl = ttl_seconds or self.ttl_seconds
        client = self._get_redis()
        if client is not None:
            try:
                client.set(f"idempotency:{key}", payload, ex=ttl, nx=True)
            except Exception as exc:
                logger.warning("redis_set_error", key=key, error=str(exc))

        self._in_memory_store[key] = (payload, time.time() + ttl)
        return True
```

```bash
# Verification commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **`IdempotencyCache` Backend (`src/persistence/cache.py`)**: Built SHA-256 key computation, Redis client with `NX`/`EX` options, in-memory TTL eviction, and `ToolExecutionResult` serialization.
2. [x] **Registry Caching Interception (`src/tools/registry.py`)**: Updated `ToolRegistry.execute()` to accept `session_id`, check cache before execution, and store successful outputs.
3. [x] **Output Serialization Alignment (`src/tools/base.py`)**: Standardized `raw_result.model_dump(mode="json")` in `execute_shielded` for consistency across direct and cached calls.
4. [x] **Unit Test Suite (`tests/unit/test_cache.py`)**: Implemented 7 tests verifying key determinism, in-memory TTL, Redis mock integration, and memory fallback.
5. [x] **Integration Test Suite (`tests/integration/test_tools_runtime.py`)**: Implemented 6 tests verifying all tools, argument validation, PII shielding, session isolation, and cache hit verification.
6. [x] **Quality Gates Verified**: `make lint` passed, `make typecheck` passed (strict across 68 files), `make test` passed (218 tests passing 100%).
