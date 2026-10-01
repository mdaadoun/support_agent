"""Parsers for raw LLM tool calls and token telemetry."""

import json
from typing import Any

from core.exceptions import LLMResponseValidationError
from models.llm import LLMToolCall, LLMUsage
from observability.cost_tracker import FinOpsCostTracker

__all__ = ["parse_tool_calls", "parse_usage_metrics"]


def parse_tool_calls(raw_tool_calls: Any) -> list[LLMToolCall]:
    """Parse raw tool call objects from ChatCompletion into immutable LLMToolCall DTOs."""
    parsed: list[LLMToolCall] = []
    if not raw_tool_calls:
        return parsed

    for raw_call in raw_tool_calls:
        call_id = getattr(raw_call, "id", "")
        fn = getattr(raw_call, "function", None)
        fn_name = getattr(fn, "name", "") if fn else ""
        raw_args = getattr(fn, "arguments", "{}") if fn else "{}"

        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError as exc:
                raise LLMResponseValidationError(
                    f"Malformed JSON arguments in tool call '{fn_name}': {exc}"
                ) from exc
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}

        parsed.append(LLMToolCall(id=call_id, name=fn_name, arguments=args))

    return parsed


def parse_usage_metrics(
    raw_usage: Any,
    cost_tracker: FinOpsCostTracker,
) -> LLMUsage:
    """Extract token counts from ChatCompletion usage and calculate FinOps cost."""
    prompt_tokens = getattr(raw_usage, "prompt_tokens", 0) if raw_usage else 0
    completion_tokens = getattr(raw_usage, "completion_tokens", 0) if raw_usage else 0
    total_tokens = (
        getattr(raw_usage, "total_tokens", prompt_tokens + completion_tokens)
        if raw_usage
        else prompt_tokens + completion_tokens
    )
    cost_usd = cost_tracker.estimate_cost(prompt_tokens, completion_tokens)

    return LLMUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
    )
