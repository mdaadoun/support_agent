"""FinOps token counter and real-time USD cost calculation for 8_support_agent."""

from typing import Final

# Pricing per million tokens (USD)
DEFAULT_PRICING: Final[dict[str, tuple[float, float]]] = {
    # model: (cost_per_million_input, cost_per_million_output)
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-3.5-turbo": (0.50, 1.50),
}


class FinOpsCostTracker:
    """Calculates LLM token usage and estimates USD execution cost."""

    def __init__(self, model_name: str = "gpt-4o-mini") -> None:
        self.model_name = model_name
        self.pricing = DEFAULT_PRICING.get(model_name, (0.15, 0.60))

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate total USD cost based on token counts and model pricing."""
        in_rate, out_rate = self.pricing
        input_cost = (max(0, prompt_tokens) / 1_000_000.0) * in_rate
        output_cost = (max(0, completion_tokens) / 1_000_000.0) * out_rate
        return round(input_cost + output_cost, 6)

    def count_tokens(self, text: str) -> int:
        """Estimate token count for a text string using character heuristic."""
        if not text:
            return 0
        # Fast fallback heuristic: ~4 characters per token
        return max(1, len(text) // 4)
