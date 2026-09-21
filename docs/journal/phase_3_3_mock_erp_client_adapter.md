# Session 3.3: Mock ERP Client Adapter with Retry & Error Mapping
**Date:** 2026-09-18

*Implemented the production-grade `MockERPClient` adapter in `src/clients/erp_client.py` loading `data/mock_orders.json` with Tenacity exponential retries (`max_attempts=2`) for network simulation, synchronous and asynchronous retrieval methods, fail-fast order lookup validation, and comprehensive exception shielding mapping missing orders to `OrderNotFoundError`, corrupt storage to `ConfigurationError`, and network failure exhaustion to `CircuitBreakerError`.*

---

### 1. 🎓 Concepts Introduced
- **Mock ERP Client Adapter:** Infrastructure client module (`src/clients/erp_client.py`) simulating enterprise resource planning (ERP) logistics queries against local JSON storage (`data/mock_orders.json`) with retry resilience.
- **Transient Error Discrimination:** Inspection technique (`is_retryable_exception`) identifying recoverable I/O faults (timeouts, connection resets) while bypassing permanent domain errors (e.g. `OrderNotFoundError`).
- **CircuitBreakerError Chaining:** Architecture error shielding pattern where persistent upstream failure causes (`ConnectionError`, `TimeoutError`) are chained to `CircuitBreakerError` via `from exc` to preserve debugging context without leaking naked exceptions.
- **Network Failure Simulation Hook:** Internal client mechanism (`simulate_transient_network_failure`) allowing test harnesses to inject controllable network interruptions to verify retry recovery and circuit breaker tripping.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Direct-Fetch Worker Isolation within Retry Policy
- **Option 1:** Wrap entire file loading directly inside `get_order_by_id` without worker separation.
- **Option 2 (Selected):** Decouple `_fetch_order_direct` from `_read_orders_raw` and invoke via `retry_sync_call` / `retry_async_call`.
- **Rationale:** Isolating the fetch operation within Tenacity retry blocks ensures retries apply specifically to transient I/O and network simulation faults without retrying permanent business errors like `OrderNotFoundError`.

#### Decision: Fail-Fast OrderNotFoundError vs Retry Delay
- **Option 1:** Retry all exceptions including missing order IDs.
- **Option 2 (Selected):** Filter out non-transient domain errors in retry predicate so `OrderNotFoundError` immediately raises without delay.
- **Rationale:** A non-existent order ID in an ERP database is a deterministic domain state, not a transient network failure. Retrying missing order IDs degrades agent latency and wastes system resources.

#### Decision: Complete Exception Shielding ("Zero Naked Crash")
- **Option 1:** Allow raw `OSError`, `ConnectionError`, or `json.JSONDecodeError` to propagate.
- **Option 2 (Selected):** Map missing orders to `OrderNotFoundError`, storage corruption to `ConfigurationError`, and network failure exhaustion to `CircuitBreakerError` with cause chaining.
- **Rationale:** Upholds the Pax Universal Engineering Guardrail requiring zero raw third-party or OS exceptions across layer boundaries, ensuring predictable error recovery for the ReAct loop and FSM controller.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/clients/erp_client.py
from pathlib import Path
from typing import Any
from core.config import get_settings
from core.exceptions import CircuitBreakerError, ConfigurationError, OrderNotFoundError
from core.retry import retry_async_call, retry_sync_call

class MockERPClient:
    def __init__(self, data_path: Path | None = None, max_attempts: int = 2) -> None:
        settings = get_settings()
        self.data_path = data_path or settings.erp_data_path
        self.max_attempts = max_attempts
        self._transient_failures_remaining: int = 0

    def simulate_transient_network_failure(self, failure_count: int = 1) -> None:
        self._transient_failures_remaining = max(0, failure_count)

    def get_order_by_id(self, order_id: str) -> dict[str, Any]:
        try:
            return retry_sync_call(
                self._fetch_order_direct,
                order_id,
                max_attempts=self.max_attempts,
            )
        except (ConnectionError, TimeoutError) as exc:
            raise CircuitBreakerError(
                f"Upstream ERP service temporarily unavailable for order '{order_id}': {exc}"
            ) from exc

    async def get_order_by_id_async(self, order_id: str) -> dict[str, Any]:
        async def _async_fetch() -> dict[str, Any]:
            return self._fetch_order_direct(order_id)
        try:
            return await retry_async_call(_async_fetch, max_attempts=self.max_attempts)
        except (ConnectionError, TimeoutError) as exc:
            raise CircuitBreakerError(
                f"Upstream ERP service temporarily unavailable for order '{order_id}': {exc}"
            ) from exc
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **MockERPClient Adapter Implemented (`src/clients/erp_client.py`)** supporting JSON querying, sync/async lookups, and network simulation.
2. [x] **Tenacity Retry Decorator Configuration** with `max_attempts=2` and transient error discrimination.
3. [x] **Exception Shielding & Mapping** routing missing orders to `OrderNotFoundError`, corruption to `ConfigurationError`, and exhaustion to `CircuitBreakerError`.
4. [x] **Comprehensive Integration Test Suite (`tests/integration/test_erp_client.py`)** asserting nominal lookups, fail-fast 404s, retry recoveries, and circuit breaker tripping.
5. [x] **Static Verification & CI Gates**: `make lint`, `make typecheck` (Mypy strict), and `make test` passing 100%.
