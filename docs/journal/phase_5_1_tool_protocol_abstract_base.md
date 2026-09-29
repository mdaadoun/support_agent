# Session 5.1: Tool Protocol & Abstract Base
**Date:** 2026-09-28

*Implemented the core Tool Protocol (`ToolInterface`), Abstract Base Class (`BaseTool`), and execution shielding runtime (`execute_shielded`, `@shield_tool_execution`) in `src/tools/base.py` and exported through `src/tools/__init__.py`. This foundation guarantees MCP-compliant tool discovery, strict Pydantic argument validation, and absolute exception shielding ("Zero Naked Crash") across all customer support automation tools.*

---

### 1. 🎓 Concepts Introduced
- **`ToolInterface` Protocol:** Runtime-checkable Protocol declaring the structural contract (`name`, `description`, `args_schema`, `execute`) required for ReAct agent loop integration and Model Context Protocol (MCP) tool exposure.
- **`BaseTool` Abstract Base Class:** Template Method pattern implementation that standardizes cross-cutting concerns: argument deserialization, validation against Pydantic models, JSON Schema generation, and exception shielding while delegating core operational logic to `_run()`.
- **Absolute Exception Shielding ("Zero Naked Crash"):** Isolation boundary intercepting Pydantic validation errors, domain-specific `SupportAgentBaseError` instances, and unhandled runtime exceptions, converting them into structured `ToolExecutionResult` payloads without crashing calling threads.
- **Dynamic Metadata Binding Decorator (`@shield_tool_execution`):** Higher-order decorator dynamically inspecting bound instance attributes or function metadata to enforce schema validation and error containment on standalone functions or custom tool methods.
- **MCP Tool Specification Export (`get_mcp_spec`):** Automated extraction of tool name, human-readable description, and JSON Schema parameters directly from Pydantic argument models for LLM tool calling.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Decoupled ToolInterface Protocol and BaseTool ABC
- **Option 1:** Use only a single abstract class `BaseTool`.
- **Option 2 (Selected):** Decouple `ToolInterface` (a `@runtime_checkable` `Protocol`) from `BaseTool` (an `ABC` implementing `ToolInterface`).
- **Rationale:** Using a `Protocol` enables structural subtyping (duck typing), allowing external MCP adapters, test stubs, or third-party plugins to satisfy the agent tool interface without inheriting from internal concrete classes. `BaseTool` provides concrete implementation convenience and the Template Method pattern for internal domain tools.

#### Decision: Template Method Pattern (`execute` vs. `_run`)
- **Option 1:** Require each tool subclass to implement `execute()` and write its own `try/except` and validation logic.
- **Option 2 (Selected):** Implement the Template Method pattern in `BaseTool.execute()`, delegating purely business execution to `_run()`.
- **Rationale:** Centrally enforcing schema validation, logging, and error mapping in `execute()` eliminates repetitive boilerplate across tools, guarantees 100% adherence to the "Zero Naked Crash" policy, and prevents developers from inadvertently leaking raw exceptions.

#### Decision: Dual Execution Wrapper (`execute_shielded` and `@shield_tool_execution`)
- **Option 1:** Provide only class-based execution via `BaseTool`.
- **Option 2 (Selected):** Implement `execute_shielded` as a functional execution engine, complemented by the `@shield_tool_execution` decorator.
- **Rationale:** Offers maximum developer flexibility. Concrete tools subclassing `BaseTool` automatically utilize `execute_shielded`, while ad-hoc functions, standalone utilities, or legacy procedures can be decorated with `@shield_tool_execution` to gain identical resilience.

#### Decision: Structured ToolExecutionResult Payloads vs. Exception Propagation
- **Option 1:** Allow domain exceptions to propagate upward into the ReAct loop.
- **Option 2 (Selected):** Catch all errors at the tool boundary and return `ToolExecutionResult(success=False, error_code=...)`.
- **Rationale:** Autonomous ReAct loops reason over observations. A structured failure payload allows the agent to inspect the failure reason (e.g. `ORDER_NOT_FOUND` or `INVALID_ARGUMENTS`) and formulate appropriate recovery thoughts or escalate to human review (`REQUIRES_HUMAN`) rather than terminating with an unhandled process fault.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/tools/base.py
@runtime_checkable
class ToolInterface(Protocol):
    """Protocol for tools compatible with ReAct loop and MCP runtime."""
    name: str
    description: str
    args_schema: type[BaseModel]

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        """Execute the tool operation safely with complete exception shielding."""
        ...

class BaseTool(ABC, ToolInterface):
    """Abstract base class for support agent tools providing argument validation and exception shielding."""
    name: str
    description: str
    args_schema: type[BaseModel]

    def validate_arguments(self, **kwargs: Any) -> BaseModel:
        return self.args_schema.model_validate(kwargs)

    def get_mcp_spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.args_schema.model_json_schema(),
        }

    @abstractmethod
    async def _run(self, **kwargs: Any) -> Any:
        ...

    async def execute(self, **kwargs: Any) -> ToolExecutionResult:
        return await execute_shielded(
            func=self._run,
            tool_name=self.name,
            args_schema=self.args_schema,
            **kwargs,
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
1. [x] **`ToolInterface` Protocol (`src/tools/base.py`)**: Defined runtime-checkable structural protocol compatible with MCP and ReAct loops.
2. [x] **`BaseTool` Abstract Base Class (`src/tools/base.py`)**: Implemented template method pattern managing argument validation and shielded execution.
3. [x] **`execute_shielded` Engine (`src/tools/base.py`)**: Built core execution wrapper capturing `ValidationError`, `SupportAgentBaseError`, and unexpected `Exception` instances.
4. [x] **`@shield_tool_execution` Decorator (`src/tools/base.py`)**: Added functional decorator with automatic metadata resolution for async and sync callables.
5. [x] **Concrete Tools Refactored (`src/tools/`)**: Updated `OrderStatusTool`, `DelayCalculatorTool`, and `RefundCalculatorTool` to inherit from `BaseTool` with `BaseDTO` argument schemas.
6. [x] **Unit Test Suite (`tests/unit/test_tool_base.py`)**: Implemented 9 test suites validating protocol conformance, abstract instantiation, payload normalization, and exception shielding.
7. [x] **Quality Gates Verified**: `make lint`, `make typecheck` (Mypy strict across 64 files), and `make test` (183 tests passing 100%).
