"""FinOps token counter and real-time USD cost calculation for 8_support_agent."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Final

from models.llm import LLMUsage, ModelPricing, TokenCostBreakdown
from observability.logger import get_logger

try:
    import tiktoken
except ImportError:
    tiktoken = None  # type: ignore[assignment]

logger = get_logger(__name__)

__all__ = [
    "DEFAULT_PRICING",
    "FinOpsCostTracker",
    "calculate_llm_cost",
    "count_string_tokens",
    "get_encoding_for_model",
    "resolve_pricing",
]

# Standard pricing table per million tokens (USD)
DEFAULT_PRICING: Final[dict[str, ModelPricing]] = {
    "gpt-4o-mini": ModelPricing(input_per_million=0.15, output_per_million=0.60),
    "gpt-4o": ModelPricing(input_per_million=2.50, output_per_million=10.00),
    "gpt-4-turbo": ModelPricing(input_per_million=10.00, output_per_million=30.00),
    "gpt-4": ModelPricing(input_per_million=30.00, output_per_million=60.00),
    "gpt-3.5-turbo": ModelPricing(input_per_million=0.50, output_per_million=1.50),
    "text-embedding-3-small": ModelPricing(
        input_per_million=0.02, output_per_million=0.00
    ),
    "text-embedding-3-large": ModelPricing(
        input_per_million=0.13, output_per_million=0.00
    ),
}


@lru_cache(maxsize=16)
def get_encoding_for_model(model_name: str) -> Any:
    """Retrieve and cache tiktoken encoding object for model with fallback."""
    if tiktoken is None:
        return None
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        try:
            return tiktoken.get_encoding("o200k_base")
        except Exception as exc:
            logger.debug("tiktoken_fallback_failed", error=str(exc))
            return None
    except Exception as exc:
        logger.debug("tiktoken_encoding_failed", model=model_name, error=str(exc))
        return None


def resolve_pricing(
    model_name: str,
    custom_pricing: dict[str, ModelPricing] | None = None,
) -> ModelPricing:
    """Resolve pricing rates for a given model identifier with prefix fallback."""
    catalog = custom_pricing or DEFAULT_PRICING
    if model_name in catalog:
        return catalog[model_name]

    # Prefix-matching for date-versioned models (e.g. gpt-4o-mini-2024-07-18)
    for prefix in ("gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5"):
        if model_name.startswith(prefix):
            target = "gpt-3.5-turbo" if prefix == "gpt-3.5" else prefix
            if target in catalog:
                return catalog[target]

    return catalog.get(
        "gpt-4o-mini", ModelPricing(input_per_million=0.15, output_per_million=0.60)
    )


class FinOpsCostTracker:
    """Calculates LLM token consumption and estimates exact execution costs."""

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        custom_pricing: dict[str, ModelPricing] | None = None,
    ) -> None:
        self.model_name = model_name
        self._pricing = resolve_pricing(model_name, custom_pricing)
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0

    @property
    def pricing(self) -> tuple[float, float]:
        """Return pricing rates as tuple (in_rate, out_rate) for backward compatibility."""
        return (self._pricing.input_per_million, self._pricing.output_per_million)

    @property
    def model_pricing(self) -> ModelPricing:
        """Return immutable ModelPricing contract."""
        return self._pricing

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        r"""Calculate total USD cost ($C_{\text{LLM\_in}} + C_{\text{LLM\_out}}$)."""
        breakdown = self.calculate_breakdown(prompt_tokens, completion_tokens)
        return breakdown.total_cost_usd

    def calculate_breakdown(
        self, prompt_tokens: int, completion_tokens: int
    ) -> TokenCostBreakdown:
        """Calculate detailed FinOps breakdown across prompt and completion tokens."""
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
        """Count tokens in text string via tiktoken BPE tokenizer with fallback."""
        if not text:
            return 0

        target_model = model_name or self.model_name
        encoding = get_encoding_for_model(target_model)

        if encoding is not None:
            try:
                # Treat special tokens as regular text to prevent injection errors
                tokens = encoding.encode(text, disallowed_special=())
                return len(tokens)
            except Exception as exc:
                logger.debug(
                    "tiktoken_encode_failed_using_heuristic",
                    model=target_model,
                    error=str(exc),
                )

        # Fast character heuristic fallback: ~4 characters per token
        return max(1, len(text) // 4)

    def count_messages_tokens(
        self,
        messages: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        model_name: str | None = None,
    ) -> int:
        """Calculate total prompt tokens across ChatML messages including framing overhead."""
        if not messages:
            return 0

        target_model = model_name or self.model_name
        num_tokens = 0

        # Each message follows <|im_start|>{role/name}\n{content}<|im_end|>\n (3 tokens)
        for message in messages:
            num_tokens += 3
            for value in message.values():
                if value and isinstance(value, str):
                    num_tokens += self.count_tokens(value, model_name=target_model)

        # Every reply is primed with <|im_start|>assistant<|message|> (3 tokens)
        num_tokens += 3
        return num_tokens

    def record_usage(
        self, prompt_tokens: int, completion_tokens: int
    ) -> TokenCostBreakdown:
        """Accumulate token counts into cumulative session state and return breakdown."""
        self._total_prompt_tokens += max(0, prompt_tokens)
        self._total_completion_tokens += max(0, completion_tokens)
        return self.calculate_breakdown(prompt_tokens, completion_tokens)

    def get_cumulative_usage(self) -> LLMUsage:
        """Return cumulative token usage and estimated spend across all recorded turns."""
        cost_usd = self.estimate_cost(
            self._total_prompt_tokens, self._total_completion_tokens
        )
        return LLMUsage(
            prompt_tokens=self._total_prompt_tokens,
            completion_tokens=self._total_completion_tokens,
            total_tokens=self._total_prompt_tokens + self._total_completion_tokens,
            cost_usd=cost_usd,
        )

    def reset(self) -> None:
        """Reset cumulative token counters for new conversation session."""
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0


def calculate_llm_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model_name: str = "gpt-4o-mini",
) -> float:
    """Convenience helper to compute total execution cost for an LLM call."""
    tracker = FinOpsCostTracker(model_name=model_name)
    return tracker.estimate_cost(prompt_tokens, completion_tokens)


def count_string_tokens(text: str, model_name: str = "gpt-4o-mini") -> int:
    """Convenience helper to count tokens for a given string using tiktoken."""
    tracker = FinOpsCostTracker(model_name=model_name)
    return tracker.count_tokens(text)
