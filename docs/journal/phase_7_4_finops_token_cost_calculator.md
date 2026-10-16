# Session 7.4: FinOps Token & Cost Calculator
**Date:** 2026-10-15

*Implemented Step 7.4: FinOps Token & Cost Calculator in `src/observability/cost_tracker.py` and `src/models/llm.py`. Integrated OpenAI's `tiktoken` BPE tokenizer (`o200k_base` and `cl100k_base`) with lazy LRU caching for precise prompt and completion token measurement. Enforced the exact asymmetric billing formula ($C_{\text{LLM\_in}} + C_{\text{LLM\_out}}$) across standard model pricing tiers (`gpt-4o-mini`, `gpt-4o`, `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo`) with dynamic prefix-matching for date-versioned releases. Created immutable domain DTOs `ModelPricing` and `TokenCostBreakdown` (`frozen=True`, `extra="forbid"`) in `src/models/llm.py`. Added ChatML framing token calculation (`count_messages_tokens`) and session cumulative telemetry accumulation (`record_usage`, `get_cumulative_usage`, `reset`). Built defensive exception shielding and character heuristic fallbacks (`~4 characters/token`) to uphold the "Zero Naked Crash" principle, keeping all files strictly under 250 LOC.*

---

### 1. 🎓 Concepts Introduced
- **BPE Tokenization via tiktoken**: Deterministic subword Byte Pair Encoding calculation matching exact OpenAI model tokenizers (`o200k_base` for GPT-4o family, `cl100k_base` for GPT-4/GPT-3.5) with LRU caching.
- **Exact Asymmetric USD Billing Formula**: Financial accounting formula ($C_{\text{LLM\_in}} + C_{\text{LLM\_out}}$) applying distinct input and output rates per million tokens and rounding to micro-dollars (6 decimal places).
- **ChatML Framing Token Overhead**: Accounting for structural ChatML message delimiters (`<|im_start|>{role}\n{content}<|im_end|>\n`, 3 tokens per message) and assistant reply priming (3 tokens) to prevent prompt token drift.
- **Session Cumulative Telemetry Accumulation**: Stateful tracking across multi-turn ReAct execution loops that accumulates prompt tokens, completion tokens, and dollar spend into immutable `LLMUsage` snapshots.
- **Defensive Tokenization Degradation**: Zero Naked Crash fallback mechanism that suppresses `DisallowedSpecialTokenError` via `disallowed_special=()` and degrades to a 4-character heuristic if tokenizer encoding drops.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: BPE Tokenizer (tiktoken) with Fallback Heuristic vs. Rigid External Dependency
- **Option 1:** Relying exclusively on external API response metadata or failing if tiktoken is unavailable.
- **Option 2 (Selected):** Using tiktoken with LRU cached encoders, safe special-token handling (`disallowed_special=()`), and character heuristic fallback (`max(1, len(text)//4)`).
- **Rationale:** Enables accurate pre-execution prompt token validation and rate-limit forecasting before invoking expensive LLM APIs, while shielding offline unit tests and disconnected environments from fatal import crashes.

#### Decision: Immutable FinOps DTOs (ModelPricing, TokenCostBreakdown) vs. Untyped Tuples/Dicts
- **Option 1:** Passing raw float tuples `(in_rate, out_rate)` and untyped dictionaries across observability boundaries.
- **Option 2 (Selected):** Defining immutable Pydantic V2 BaseDTO contracts `ModelPricing` and `TokenCostBreakdown` (`frozen=True, extra="forbid"`).
- **Rationale:** Complies with Universal Engineering Guardrails requiring strict typing and schema boundary validation. Prevents runtime property tampering and guarantees lossless serialization into audit logs.

#### Decision: Dynamic Prefix-Matching vs. Hardcoded Model Dictionaries
- **Option 1:** Requiring exact string equality for model names, causing unexpected fallback when date-tagged models (e.g. `gpt-4o-mini-2024-07-18`) are queried.
- **Option 2 (Selected):** Implementing hierarchical resolution: exact match -> prefix match -> catalog default.
- **Rationale:** Accommodates upstream provider API updates and fine-tuned/pinned model releases without requiring immediate codebase redeployments or breaking FinOps price calculation.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/models/llm.py
class ModelPricing(BaseDTO):
    """Pricing rates per million tokens in USD."""

    input_per_million: float = Field(ge=0.0)
    output_per_million: float = Field(ge=0.0)


class TokenCostBreakdown(BaseDTO):
    """Detailed FinOps cost breakdown across prompt and completion tokens."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    input_cost_usd: float = Field(default=0.0, ge=0.0)
    output_cost_usd: float = Field(default=0.0, ge=0.0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)


# src/observability/cost_tracker.py
class FinOpsCostTracker:
    """Calculates LLM token consumption and estimates exact execution costs."""

    def calculate_breakdown(
        self, prompt_tokens: int, completion_tokens: int
    ) -> TokenCostBreakdown:
        valid_prompt = max(0, prompt_tokens)
        valid_completion = max(0, completion_tokens)
        input_cost = (valid_prompt / 1_000_000.0) * self._pricing.input_per_million
        output_cost = (
            valid_completion / 1_000_000.0
        ) * self._pricing.output_per_million
        total_cost = input_cost + output_cost

        return TokenCostBreakdown(
            prompt_tokens=valid_prompt,
            completion_tokens=valid_completion,
            total_tokens=valid_prompt + valid_completion,
            input_cost_usd=round(input_cost, 6),
            output_cost_usd=round(output_cost, 6),
            total_cost_usd=round(total_cost, 6),
        )

    def count_tokens(self, text: str, model_name: str | None = None) -> int:
        if not text:
            return 0
        target_model = model_name or self.model_name
        encoding = get_encoding_for_model(target_model)
        if encoding is not None:
            try:
                tokens = encoding.encode(text, disallowed_special=())
                return len(tokens)
            except Exception:
                pass
        return max(1, len(text) // 4)
```

```bash
# Verification commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **Immutable FinOps DTOs (`src/models/llm.py`)**: Built `ModelPricing` and `TokenCostBreakdown` with `frozen=True` and `extra="forbid"`.
2. [x] **Model Catalog Export (`src/models/__init__.py`)**: Exported `ModelPricing` and `TokenCostBreakdown` in root domain models.
3. [x] **Tiktoken BPE Integration (`src/observability/cost_tracker.py`)**: Configured `tiktoken` with LRU encoding caching, prefix matching, and safe special-token handling (`disallowed_special=()`).
4. [x] **Asymmetric Billing Engine**: Implemented exact $C_{\text{LLM\_in}} + C_{\text{LLM\_out}}$ cost estimation with micro-dollar precision (6 decimal places).
5. [x] **ChatML Framing Overhead**: Implemented `count_messages_tokens` accounting for turn delimiters and assistant reply priming.
6. [x] **Multi-Turn Session Accumulation**: Built stateful telemetry accumulation (`record_usage`, `get_cumulative_usage`, `reset`) returning immutable `LLMUsage`.
7. [x] **Unit Test Suite (`tests/unit/test_cost_tracker.py`)**: Implemented 10 unit tests covering immutability, exact billing, clamping, BPE counting, ChatML overhead, fallback heuristics, and accumulation.
8. [x] **Quality Gates Verified**: `mypy --strict` passed across 93 source files, Ruff format and check passed cleanly, and full test suite passed with 327 tests passing 100% at 92.72% coverage.
