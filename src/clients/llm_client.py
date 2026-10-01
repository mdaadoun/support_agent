"""LLM inference client wrapper with structured output support and Tenacity retries."""

from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from clients.llm_parser import parse_tool_calls, parse_usage_metrics
from clients.llm_retry import build_llm_retrying, execute_with_retry
from core.config import get_settings
from core.exceptions import (
    BusinessRuleViolationError,
    LLMResponseValidationError,
)
from models.llm import LLMResponse
from observability.cost_tracker import FinOpsCostTracker
from observability.logger import get_logger

logger = get_logger(__name__)

__all__ = ["LLMClient"]

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Production-grade LLM wrapper interfacing with AsyncOpenAI with shielded execution."""

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        client: AsyncOpenAI | None = None,
        cost_tracker: FinOpsCostTracker | None = None,
        max_retries: int | None = None,
        retry_min_wait: float | None = None,
        retry_max_wait: float | None = None,
    ) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.llm_model

        if temperature is not None:
            if not (0.0 <= temperature <= 0.2):
                raise BusinessRuleViolationError(
                    f"LLM temperature {temperature} must be between 0.0 and 0.2.",
                    error_code="LLM_TEMPERATURE_INVALID",
                )
            self.temperature = temperature
        else:
            self.temperature = min(0.2, max(0.0, float(settings.llm_temperature)))

        self.max_retries = max_retries or settings.llm_max_retries
        self.retry_min_wait = (
            retry_min_wait
            if retry_min_wait is not None
            else settings.retry_min_wait_seconds
        )
        self.retry_max_wait = (
            retry_max_wait
            if retry_max_wait is not None
            else settings.retry_max_wait_seconds
        )

        effective_key = api_key or settings.openai_api_key or "mock-development-key"
        self.client = client or AsyncOpenAI(
            api_key=effective_key,
            base_url=base_url,
        )
        self.cost_tracker = cost_tracker or FinOpsCostTracker(
            model_name=self.model_name
        )
        self._retrying = build_llm_retrying(
            max_retries=self.max_retries,
            min_wait=self.retry_min_wait,
            max_wait=self.retry_max_wait,
        )

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[T],
        messages: list[dict[str, Any]] | None = None,
    ) -> T:
        """Issue structured inference request validated against a Pydantic schema."""
        logger.info(
            "llm_structured_call",
            model=self.model_name,
            temperature=self.temperature,
            schema=response_schema.__name__,
        )
        if messages is not None:
            assembled_messages = list(messages)
        else:
            assembled_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

        # Use beta parse if available on client
        beta = getattr(self.client, "beta", None)
        chat = getattr(beta, "chat", None) if beta else None
        completions = getattr(chat, "completions", None) if chat else None
        has_beta_parse = hasattr(completions, "parse") if completions else False

        if has_beta_parse:
            parse_kwargs: dict[str, Any] = {
                "model": self.model_name,
                "messages": assembled_messages,
                "response_format": response_schema,
                "temperature": self.temperature,
            }
            response = await execute_with_retry(
                self._retrying,
                lambda: self.client.beta.chat.completions.parse(**parse_kwargs),
            )
            choice = response.choices[0]
            if getattr(choice.message, "refusal", None):
                raise LLMResponseValidationError(
                    f"LLM refused structured output: {choice.message.refusal}"
                )
            parsed_val = getattr(choice.message, "parsed", None)
            if isinstance(parsed_val, response_schema):
                return parsed_val
            content = getattr(choice.message, "content", None)
            if content:
                try:
                    return response_schema.model_validate_json(str(content))
                except ValidationError as exc:
                    raise LLMResponseValidationError(
                        f"Failed to validate response against schema {response_schema.__name__}: {exc}"
                    ) from exc
            raise LLMResponseValidationError(
                "LLM response did not contain parsed content."
            )

        create_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": assembled_messages,
            "response_format": {"type": "json_object"},
            "temperature": self.temperature,
        }
        response = await execute_with_retry(
            self._retrying,
            lambda: self.client.chat.completions.create(**create_kwargs),
        )
        content_val = getattr(response.choices[0].message, "content", "") or ""
        try:
            return response_schema.model_validate_json(str(content_val))
        except ValidationError as exc:
            raise LLMResponseValidationError(
                f"Failed to validate response against schema {response_schema.__name__}: {exc}"
            ) from exc

    async def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> LLMResponse:
        """Execute chat completion with tool calling options and return typed LLMResponse."""
        if not messages:
            raise BusinessRuleViolationError(
                "Messages sequence cannot be empty for LLM inference.",
                error_code="LLM_EMPTY_MESSAGES",
            )

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        logger.info(
            "llm_tools_call",
            model=self.model_name,
            temperature=self.temperature,
            tool_count=len(tools) if tools else 0,
        )

        response = await execute_with_retry(
            self._retrying,
            lambda: self.client.chat.completions.create(**kwargs),
        )

        choice = response.choices[0]
        message = choice.message
        content: str | None = message.content
        raw_finish = getattr(choice, "finish_reason", None)
        finish_reason: str = raw_finish if isinstance(raw_finish, str) else "stop"
        tool_calls = parse_tool_calls(getattr(message, "tool_calls", None))
        usage = parse_usage_metrics(response.usage, self.cost_tracker)
        raw_model = getattr(response, "model", None)
        model_name: str = raw_model if isinstance(raw_model, str) else self.model_name

        return LLMResponse(
            content=content,
            tool_calls=tuple(tool_calls),
            usage=usage,
            model=model_name,
            finish_reason=finish_reason,
        )
