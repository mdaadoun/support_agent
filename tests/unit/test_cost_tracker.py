"""Unit tests for FinOps token counter and real-time USD cost calculator."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from models.llm import LLMUsage, ModelPricing, TokenCostBreakdown
from observability.cost_tracker import (
    FinOpsCostTracker,
    calculate_llm_cost,
    count_string_tokens,
    resolve_pricing,
)


def test_model_pricing_immutability() -> None:
    """Verify ModelPricing and TokenCostBreakdown enforce immutability and schema rigidity."""
    pricing = ModelPricing(input_per_million=0.15, output_per_million=0.60)
    assert pricing.input_per_million == 0.15
    assert pricing.output_per_million == 0.60

    with pytest.raises(ValidationError):
        setattr(pricing, "input_per_million", 1.0)  # noqa: B010

    with pytest.raises(ValidationError):
        ModelPricing(
            input_per_million=0.15,
            output_per_million=0.60,
            unexpected_field="forbidden",  # type: ignore[call-arg]
        )


def test_token_cost_breakdown_immutability() -> None:
    """Verify TokenCostBreakdown is frozen and forbids extra attributes."""
    breakdown = TokenCostBreakdown(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        input_cost_usd=0.000015,
        output_cost_usd=0.000030,
        total_cost_usd=0.000045,
    )
    assert breakdown.total_tokens == 150

    with pytest.raises(ValidationError):
        setattr(breakdown, "total_cost_usd", 0.99)  # noqa: B010

    with pytest.raises(ValidationError):
        TokenCostBreakdown(
            prompt_tokens=10,
            extra_field="invalid",  # type: ignore[call-arg]
        )


def test_resolve_pricing_exact_and_prefix_matching() -> None:
    """Verify pricing lookup supports exact match, date-versioned prefixes, and defaults."""
    assert resolve_pricing("gpt-4o-mini").input_per_million == 0.15
    assert resolve_pricing("gpt-4o").input_per_million == 2.50
    assert resolve_pricing("gpt-4").input_per_million == 30.00
    assert resolve_pricing("gpt-3.5-turbo").input_per_million == 0.50

    # Date-versioned model prefixes
    assert resolve_pricing("gpt-4o-mini-2024-07-18").input_per_million == 0.15
    assert resolve_pricing("gpt-4o-2024-08-06").input_per_million == 2.50
    assert resolve_pricing("gpt-3.5-turbo-0125").input_per_million == 0.50

    # Unknown model falls back to gpt-4o-mini default
    assert resolve_pricing("unknown-llm-provider").input_per_million == 0.15

    # Custom pricing override
    custom = {
        "my-custom-model": ModelPricing(input_per_million=1.0, output_per_million=2.0)
    }
    assert resolve_pricing("my-custom-model", custom).input_per_million == 1.0


def test_exact_cost_calculation_formula() -> None:
    """Verify exact formula (C_in + C_out) calculation with micro-dollar rounding."""
    tracker = FinOpsCostTracker(model_name="gpt-4o-mini")
    # Rate: $0.15 / 1M in, $0.60 / 1M out
    # 1,000,000 in ($0.15) + 1,000,000 out ($0.60) = $0.75
    cost = tracker.estimate_cost(1_000_000, 1_000_000)
    assert cost == 0.75

    # 10,000 in ($0.0015) + 5,000 out ($0.0030) = $0.0045
    breakdown = tracker.calculate_breakdown(10_000, 5_000)
    assert breakdown.prompt_tokens == 10_000
    assert breakdown.completion_tokens == 5_000
    assert breakdown.total_tokens == 15_000
    assert breakdown.input_cost_usd == 0.0015
    assert breakdown.output_cost_usd == 0.003
    assert breakdown.total_cost_usd == 0.0045

    # Backward compatibility tuple unpacking
    in_rate, out_rate = tracker.pricing
    assert (in_rate, out_rate) == (0.15, 0.60)


def test_cost_calculation_bounds_and_zero_tokens() -> None:
    """Verify zero and negative token counts clamp safely without negative billing."""
    tracker = FinOpsCostTracker(model_name="gpt-4o-mini")
    assert tracker.estimate_cost(0, 0) == 0.0

    breakdown = tracker.calculate_breakdown(-50, -100)
    assert breakdown.prompt_tokens == 0
    assert breakdown.completion_tokens == 0
    assert breakdown.total_cost_usd == 0.0


def test_tiktoken_token_counting() -> None:
    """Verify accurate BPE token counting with tiktoken."""
    tracker = FinOpsCostTracker(model_name="gpt-4o-mini")

    assert tracker.count_tokens("") == 0
    token_count = tracker.count_tokens("Hello, world! Order CMD-12345.")
    assert token_count == 10

    # Ensure special tokens do not trigger DisallowedSpecialTokenError
    special_text = "Testing special token: <|endoftext|> and <|im_start|>"
    assert tracker.count_tokens(special_text) > 0


def test_count_messages_tokens_chatml_overhead() -> None:
    """Verify ChatML message prompt token calculation accounts for formatting framing."""
    tracker = FinOpsCostTracker(model_name="gpt-4o-mini")

    assert tracker.count_messages_tokens([]) == 0

    messages = [
        {"role": "system", "content": "You are a helpful customer support agent."},
        {"role": "user", "content": "Where is my order CMD-99999?"},
    ]
    total_tokens = tracker.count_messages_tokens(messages)
    # Expected: tokens for content + 3 per message (6) + 3 reply priming = content + 9
    content_tokens = (
        tracker.count_tokens("You are a helpful customer support agent.")
        + tracker.count_tokens("Where is my order CMD-99999?")
        + tracker.count_tokens("system")
        + tracker.count_tokens("user")
    )
    assert total_tokens == content_tokens + 9


def test_tiktoken_fallback_heuristic_when_unavailable() -> None:
    """Verify safe fallback to character heuristic when tiktoken encoding fails."""
    tracker = FinOpsCostTracker(model_name="gpt-4o-mini")

    with patch("observability.cost_tracker.get_encoding_for_model", return_value=None):
        count = tracker.count_tokens("A quick brown fox jumps over the lazy dog.")
        # Length 42 chars -> 42 // 4 = 10 tokens
        assert count == 10
        assert tracker.count_tokens("") == 0


def test_session_cumulative_usage_accumulation() -> None:
    """Verify cumulative multi-turn token tracking and session reset."""
    tracker = FinOpsCostTracker(model_name="gpt-4o-mini")

    # Turn 1
    tracker.record_usage(prompt_tokens=500, completion_tokens=100)
    usage_1 = tracker.get_cumulative_usage()
    assert isinstance(usage_1, LLMUsage)
    assert usage_1.prompt_tokens == 500
    assert usage_1.completion_tokens == 100
    assert usage_1.total_tokens == 600

    # Turn 2
    tracker.record_usage(prompt_tokens=700, completion_tokens=200)
    usage_2 = tracker.get_cumulative_usage()
    assert usage_2.prompt_tokens == 1200
    assert usage_2.completion_tokens == 300
    assert usage_2.total_tokens == 1500
    expected_cost = tracker.estimate_cost(1200, 300)
    assert usage_2.cost_usd == expected_cost

    # Session Reset
    tracker.reset()
    reset_usage = tracker.get_cumulative_usage()
    assert reset_usage.prompt_tokens == 0
    assert reset_usage.completion_tokens == 0
    assert reset_usage.total_tokens == 0
    assert reset_usage.cost_usd == 0.0


def test_convenience_helpers() -> None:
    """Verify standalone convenience helper functions."""
    cost = calculate_llm_cost(10_000, 2_000, model_name="gpt-4o-mini")
    assert cost > 0.0

    tokens = count_string_tokens(
        "Status check for order CMD-88888", model_name="gpt-4o-mini"
    )
    assert tokens > 0
