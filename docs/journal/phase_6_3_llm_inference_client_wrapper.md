# Session 6.3: LLM Inference Client Wrapper & Resilient Tool Calling
**Date:** 2026-10-01

*Implemented the production-grade LLM inference client (`LLMClient`), Tenacity retry controller (`build_llm_retrying`, `execute_with_retry`), response parsing pipeline (`parse_tool_calls`, `parse_usage_metrics`), and structured domain models (`LLMResponse`, `LLMToolCall`, `LLMUsage`) in `src/clients/` and `src/models/llm.py`. Enforced strict operational guardrails: deterministic temperature bounds ($\le 0.2$), exponential backoff retry on transient upstream faults, zero raw third-party exception leaks (`AppBaseError` hierarchy), and structured Pydantic schema validation.*

---

### 1. 🎓 Concepts Introduced
- **Deterministic Sampling Ceiling ($T \le 0.2$):** Hard boundary constraint bounding model entropy to prevent creative hallucinations and guarantee strict adherence to tool and response schemas.
- **Tenacity Retry Executor:** Asynchronous resilience layer decorating inference operations with exponential backoff and jitter across transient upstream provider errors.
- **Selective Fault Discrimination:** Explicit classification distinguishing retriable errors (`RateLimitError`, `APIConnectionError`, `APITimeoutError`, `InternalServerError`) from non-retriable fatal errors (`AuthenticationError`, `BadRequestError`).
- **Structured Tool Calling:** Model generation mode invoking certified tool schemas with normalized arguments wrapped into immutable `LLMToolCall` DTOs.
- **Zero Raw Third-Party Exception Shielding:** Strict boundary encapsulation converting all external SDK errors into standardized domain exceptions (`LLMInferenceError`, `LLMAuthenticationError`, `LLMTimeoutError`).
- **Integrated FinOps Telemetry:** Token counting and cost calculation embedded directly in the inference response contract (`LLMUsage`).

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Strict Clamping and Bounding of LLM Sampling Temperature (<= 0.2)
- **Option 1:** Permit arbitrary temperature ranges configured by external callers.
- **Option 2 (Selected):** Hard clamp and validate `0.0 <= temperature <= 0.2` across client initialization and inference.
- **Rationale:** Deterministic support agents handling regulated ecommerce requests cannot tolerate high entropy or creative generation. Enforcing `temperature <= 0.2` minimizes hallucination risk and guarantees reliable JSON and tool schema compliance.

#### Decision: Tenacity Exponential Backoff Retries with Transient Fault Discrimination
- **Option 1:** Retry all exceptions indiscriminately on any failure.
- **Option 2 (Selected):** Target retries strictly on transient infrastructure faults (`RateLimitError`, `APIConnectionError`, `APITimeoutError`, `InternalServerError`) while failing fast on permanent client faults (`AuthenticationError`, `BadRequestError`).
- **Rationale:** Prevents thundering herd problems and wasted compute on non-recoverable 401/400 errors, while providing resilience against ephemeral network drops and rate limits.

#### Decision: Modular Single-Responsibility Decomposition (llm_client.py, llm_retry.py, llm_parser.py)
- **Option 1:** Maintain a monolithic 300+ LOC client file encompassing all parsing, retrying, and API logic.
- **Option 2 (Selected):** Decompose into client facade (`llm_client.py`), retry executor (`llm_retry.py`), and response parsers (`llm_parser.py`), each strictly $\le 250$ LOC.
- **Rationale:** Adheres to the universal 250 LOC limit, isolates network retry concerns from JSON parsing logic, and enables focused unit testing of edge cases.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/clients/llm_client.py
class LLMClient:
    """Production-grade LLM wrapper interfacing with AsyncOpenAI with shielded execution."""

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
        client: AsyncOpenAI | None = None,
        ...
    ) -> None:
        ...
        if temperature is not None:
            if not (0.0 <= temperature <= 0.2):
                raise BusinessRuleViolationError(
                    f"LLM temperature {temperature} must be between 0.0 and 0.2.",
                    error_code="LLM_TEMPERATURE_INVALID",
                )
            self.temperature = temperature
        else:
            self.temperature = min(0.2, max(0.0, float(settings.llm_temperature)))

        self._retrying = build_llm_retrying(
            max_retries=self.max_retries,
            min_wait=self.retry_min_wait,
            max_wait=self.retry_max_wait,
        )
```

```bash
# Verification commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **LLM Client Facade (`src/clients/llm_client.py`)**: Implemented `LLMClient` with temperature clamping, `generate_structured` (Pydantic schema validation), and `generate_with_tools` (tool execution dispatching).
2. [x] **Retry Engine (`src/clients/llm_retry.py`)**: Created `build_llm_retrying` and `execute_with_retry` wrapping Tenacity `AsyncRetrying` with targeted exception shielding.
3. [x] **Response Parsers (`src/clients/llm_parser.py`)**: Authored `parse_tool_calls` for JSON argument extraction and `parse_usage_metrics` for token telemetry and USD cost estimation.
4. [x] **Domain Models (`src/models/llm.py`)**: Created immutable DTOs (`LLMResponse`, `LLMToolCall`, `LLMUsage`) inheriting from `BaseDTO`.
5. [x] **Exception Hierarchy (`src/core/exceptions.py`)**: Defined `LLMInferenceError`, `LLMResponseValidationError`, `LLMAuthenticationError`, and `LLMTimeoutError`.
6. [x] **Comprehensive Test Suite**: Implemented unit tests covering client initialization, structured outputs, tool calling, and retries across `tests/unit/test_llm_client.py`, `tests/unit/test_llm_structured.py`, and `tests/unit/test_llm_retries.py`.
7. [x] **Roadmap Progress (`docs/roadmap.md`)**: Marked Step 6.3 as completed `[x]`.
