# Session 5.3: Tool Registry & Schema Exporter
**Date:** 2026-09-28

*Implemented the dynamic `ToolRegistry` in `src/tools/registry.py` with contract validation upon registration, pre-flight Pydantic argument validation, exception-shielded execution dispatch, and dual-format schema exporters for both Model Context Protocol (MCP) and OpenAI Function Calling specifications. Exported `create_default_registry` in `src/tools/__init__.py` to provide a preconfigured production tool suite.*

---

### 1. 🎓 Concepts Introduced
- **Dynamic Tool Registration & Discovery:** Centralized catalog mapping tool identifiers to `ToolInterface` protocol implementations with `register`, `unregister`, `get_tool`, and container protocol operations (`__contains__`, `__len__`).
- **Registration Contract Verification:** Strict validation enforcing `ToolInterface` conformance, non-empty tool names, and valid Pydantic `BaseModel` subclasses for `args_schema`, raising `BusinessRuleViolationError` on violations.
- **Pre-Flight Argument Validation:** `validate_tool_arguments` validates input payloads against the tool's Pydantic schema before execution or idempotency cache hashing.
- **Defensive Exception Shielding during Dispatch:** `execute()` encapsulates tool lookup and execution, mapping missing tools to `TOOL_NOT_FOUND`, known domain errors to structured error codes, and unexpected failures to `UNHANDLED_TOOL_FAULT`.
- **Model Context Protocol (MCP) Exporter:** Automatic derivation of standard MCP tool definitions (`name`, `description`, `parameters`) directly from Pydantic `args_schema.model_json_schema()`.
- **OpenAI Function Calling Exporter:** Standard `{"type": "function", "function": {...}}` exporter enabling out-of-the-box integration with LiteLLM and OpenAI tool-calling APIs.
- **Default Catalog Factory:** `create_default_registry` wires together `OrderStatusTool`, `RefundCalculatorTool`, and `DelayCalculatorTool` with dependency-injected mock ERP client.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Decoupled Instance-Based Registry over Global Singleton
- **Option 1:** Global module-level singleton dictionary with import-time registration decorators.
- **Option 2 (Selected):** Instantiated `ToolRegistry` class with optional initial collection and `create_default_registry` factory.
- **Rationale:** Avoids global mutable state, eliminates test cross-contamination, enables multi-tenant scoping or per-session tool subsets, and allows mock client dependency injection without monkey-patching.

#### Decision: Pydantic model_json_schema() as Single Source of Truth for Schemas
- **Option 1:** Handcrafted JSON schemas maintained alongside Python tool code.
- **Option 2 (Selected):** Automated extraction via Pydantic V2 `model_json_schema()` in `get_mcp_specs()` and `get_openai_tools()`.
- **Rationale:** Guarantees complete consistency between runtime type validation and LLM tool schemas, eliminating schema drift and manual documentation overhead.

#### Decision: Pre-Flight Validation Method for Upstream Caching and Routing
- **Option 1:** Coupling validation solely inside `tool.execute()`.
- **Option 2 (Selected):** Exposing standalone `validate_tool_arguments(tool_name, **kwargs)` in the registry.
- **Rationale:** Allows upstream components (such as Phase 5.4 idempotency cache hashing and Phase 6 ReAct FSM) to validate arguments upfront and generate deterministic cache keys before invoking expensive I/O operations.

#### Decision: Layered Exception Shielding on Registry Execution
- **Option 1:** Allow unregistered tool lookups or tool runtime crashes to bubble raw exceptions up to the agent loop.
- **Option 2 (Selected):** Shield missing tool requests as `TOOL_NOT_FOUND` and catch unexpected errors as `UNHANDLED_TOOL_FAULT` in `ToolExecutionResult`.
- **Rationale:** Ensures the LLM ReAct agent loop receives structured observations even when hallucinating tool names or encountering unhandled edge cases, enabling self-correction rather than crashing the web server thread.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/tools/registry.py
class ToolRegistry:
    """Dynamic catalog and dispatch coordinator for ReAct and MCP agent tools."""

    def __init__(self, tools: Sequence[ToolInterface] | None = None) -> None:
        self._tools: dict[str, ToolInterface] = {}
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: ToolInterface) -> None:
        if not isinstance(tool, ToolInterface):
            raise BusinessRuleViolationError(
                f"Object of type '{type(tool).__name__}' does not conform to ToolInterface.",
                error_code="INVALID_TOOL_PROTOCOL",
            )
        if not tool.name or not tool.name.strip():
            raise BusinessRuleViolationError(
                "Tool name must be a non-empty string.",
                error_code="INVALID_TOOL_METADATA",
            )
        if not isinstance(tool.args_schema, type) or not issubclass(
            tool.args_schema, BaseModel
        ):
            raise BusinessRuleViolationError(
                f"Tool '{tool.name}' args_schema must be a subclass of pydantic.BaseModel.",
                error_code="INVALID_TOOL_METADATA",
            )
        self._tools[tool.name] = tool

    def get_mcp_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.args_schema.model_json_schema(),
            }
            for tool in self._tools.values()
        ]

    def get_openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.args_schema.model_json_schema(),
                },
            }
            for tool in self._tools.values()
        ]
```

```bash
# Verification commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **`ToolRegistry` Core (`src/tools/registry.py`)**: Built dynamic registry with `register`, `unregister`, `get_tool`, `list_tools`, `__contains__`, and `__len__`.
2. [x] **Contract Validation on Registration**: Added fail-fast verification enforcing `ToolInterface`, non-empty names, and valid Pydantic `BaseModel` schema types.
3. [x] **Pre-Flight Argument Validation (`validate_tool_arguments`)**: Provided decoupled argument validation against Pydantic models for upstream caching and FSM routing.
4. [x] **Exception Shielding on Dispatch (`execute`)**: Wrapped tool calls to return structured `ToolExecutionResult` for missing tools (`TOOL_NOT_FOUND`), domain errors, and unhandled faults.
5. [x] **MCP & OpenAI Schema Exporters**: Implemented `get_mcp_specs`, `get_mcp_spec`, and `get_openai_tools` directly from Pydantic `model_json_schema()`.
6. [x] **Default Catalog Factory (`create_default_registry`)**: Factory function instantiating production tools (`OrderStatusTool`, `RefundCalculatorTool`, `DelayCalculatorTool`).
7. [x] **Unit Test Suite (`tests/unit/test_registry.py`)**: Comprehensive tests validating registration, schema exports, exception shielding, and default catalog.
8. [x] **Quality Gates Verified**: `make lint` passed, `make typecheck` passed (strict across 66 files), `make test` passed (204 tests passing 100%).
