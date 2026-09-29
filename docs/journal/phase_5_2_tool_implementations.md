# Session 5.2: Tool Implementations
**Date:** 2026-09-28

*Implemented production domain tool adapters in `src/tools/order_status.py`, `src/tools/refund_calculator.py`, and `src/tools/delay_calculator.py`. These tools connect the Model Context Protocol (MCP) runtime with the Mock ERP store, enforce strict customer PII cross-authorization, and bridge deterministic business rules for statutory 14-day cooling-off calculations and express delay vouchers.*

---

### 1. 🎓 Concepts Introduced
- **In-Tool PII Cross-Authorization:** Immediate fail-closed customer verification (`AccessControlGuard.verify_order_record_access`) within `OrderStatusTool` preventing unauthorized exposure of order records even if misrouted by an upstream agent.
- **Client Dependency Injection:** Optional constructor injection (`MockERPClient | None = None`) enabling test harnesses to simulate network dropouts, timeouts, and circuit breaker activations without patching global runtime singletons.
- **Deterministic Business Logic Bridging:** Routing `RefundCalculatorTool` and `DelayCalculatorTool` directly to pure Python domain calculations (`calculate_statutory_withdrawal`, `calculate_shipping_delay`), enforcing zero LLM financial authority.
- **Automated Output Serialization:** Leveraging `BaseTool.execute` to automatically serialize typed Pydantic models (`OrderDetailsResult`, `RefundEligibilityResult`) into JSON-compatible dictionaries inside `ToolExecutionResult.data`.
- **Statutory Cooling-Off Evaluation:** Complete end-to-end tool qualification asserting 14-day EU statutory return limits, expired return refusals, and unconfirmed delivery handling.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Direct Integration of PII Cross-Authorization inside OrderStatusTool
- **Option 1:** Rely entirely on pre-extraction checks before invoking the tool.
- **Option 2 (Selected):** Perform authorization check inside `OrderStatusTool._run` after fetching the order record.
- **Rationale:** The pre-extraction layer can only extract strings; the actual ownership association between sender and order record exists solely within the ERP database. Verifying identity at the tool boundary guarantees defense-in-depth and completely prevents PII leakage to the agent loop.

#### Decision: Client Dependency Injection in OrderStatusTool
- **Option 1:** Hardcode direct calls to a global `MockERPClient()` singleton.
- **Option 2 (Selected):** Allow optional injection `__init__(self, erp_client: MockERPClient | None = None)`.
- **Rationale:** Dependency injection decouples the tool from the underlying storage mechanism, permitting integration test suites to simulate transient outages, circuit breakers, and custom datasets without mutating global state.

#### Decision: Direct Domain Rule Delegation for Refund & Delay Calculators
- **Option 1:** Allow the LLM to inspect raw dates and compute refund eligibility or delays in prompts.
- **Option 2 (Selected):** Route all calculations directly to pure mathematical functions in `src/domain/business_rules.py`.
- **Rationale:** Eliminates prompt injection vectors and hallucinated numbers. 100% of calendar day offsets, refundable item totals, and express compensation vouchers originate from deterministic Python functions.

#### Decision: Returning Domain Models from `_run()`
- **Option 1:** Force tools to manually construct dictionaries via `model.model_dump()`.
- **Option 2 (Selected):** Return typed Pydantic instances (`OrderDetailsResult`, `RefundEligibilityResult`) and let `BaseTool.execute` normalize them.
- **Rationale:** Preserves end-to-end static type safety (`mypy --strict`) and clean function signatures while delegating serialization to the base class template method.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/tools/order_status.py
class OrderStatusTool(BaseTool):
    name: str = "get_order_details"
    description: str = (
        "Retrieve order details, delivery dates, carrier info, and item totals. "
        "Requires order_id and verified customer_email."
    )
    args_schema: type[OrderStatusArgs] = OrderStatusArgs

    def __init__(self, erp_client: MockERPClient | None = None) -> None:
        self.erp_client = erp_client or MockERPClient()

    async def _run(self, **kwargs: Any) -> OrderDetailsResult:
        order_id: str = kwargs["order_id"]
        customer_email: str = kwargs["customer_email"]

        order_record = await self.erp_client.get_order_by_id_async(order_id)
        AccessControlGuard.verify_order_record_access(
            sender_email=customer_email,
            order_record=order_record,
        )

        return OrderDetailsResult(
            order_id=order_record["order_id"],
            status=OrderStatusEnum(order_record["status"]),
            carrier=order_record["carrier"],
            tracking_number=order_record.get("tracking_number"),
            ordered_at=order_record["ordered_at"],
            shipped_at=order_record.get("shipped_at"),
            estimated_delivery=order_record["estimated_delivery"],
            actual_delivery=order_record.get("actual_delivery"),
            items_total_ttc_cents=order_record["items_total_ttc_cents"],
            shipping_fee_ttc_cents=order_record["shipping_fee_ttc_cents"],
            is_express=order_record["is_express"],
        )
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **`OrderStatusTool` (`src/tools/order_status.py`)**: Implemented complete order lookup with asynchronous ERP client retrieval and PII cross-authorization.
2. [x] **`RefundCalculatorTool` (`src/tools/refund_calculator.py`)**: Connected to pure deterministic business rules for cooling-off evaluation and voucher computation.
3. [x] **`DelayCalculatorTool` (`src/tools/delay_calculator.py`)**: Connected to shipping delay calculation and express voucher policy.
4. [x] **`OrderStatusArgs`, `RefundCalculatorArgs`, `DelayCalculatorArgs`**: Enforced `BaseDTO` immutability (`frozen=True, extra="forbid"`).
5. [x] **Comprehensive Test Suite (`tests/unit/test_tools.py`)**: 14 unit test suites verifying nominal execution, PII security denials, order-not-found error shielding, circuit breaker trip containment, and argument validation.
6. [x] **Quality Gates Verified**: `make lint`, `make typecheck` (Mypy strict), and `make test` (197 tests passing 100%).
