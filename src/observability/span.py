"""Active span tracking and context handling for in-flight telemetry spans."""

import json
from typing import Any

from models.tracing import (
    OpenInferenceAttributes,
    SpanKindEnum,
    SpanStatusEnum,
)

__all__ = ["ActiveSpan"]


class ActiveSpan:
    """Mutable context handle for an active in-flight telemetry span."""

    def __init__(
        self,
        span_id: str,
        trace_id: str,
        name: str,
        span_kind: SpanKindEnum,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self.span_id = span_id
        self.trace_id = trace_id
        self.name = name
        self.span_kind = span_kind
        self.parent_span_id = parent_span_id
        self._attributes: dict[str, Any] = dict(attributes or {})
        self.status = SpanStatusEnum.OK
        self.error_message: str | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        """Safely attach an attribute to the active span."""
        self._attributes[str(key)] = value

    def set_attributes(self, **attrs: Any) -> None:
        """Attach multiple attributes to the active span."""
        for k, v in attrs.items():
            self._attributes[str(k)] = v

    def set_input(self, value: Any, mime_type: str = "text/plain") -> None:
        """Set input payload and format complying with OpenInference conventions."""
        self._attributes[OpenInferenceAttributes.INPUT_VALUE] = (
            json.dumps(value, default=str)
            if isinstance(value, dict | list)
            else str(value)
        )
        self._attributes[OpenInferenceAttributes.INPUT_MIME_TYPE] = mime_type

    def set_output(self, value: Any, mime_type: str = "text/plain") -> None:
        """Set output payload and format complying with OpenInference conventions."""
        self._attributes[OpenInferenceAttributes.OUTPUT_VALUE] = (
            json.dumps(value, default=str)
            if isinstance(value, dict | list)
            else str(value)
        )
        self._attributes[OpenInferenceAttributes.OUTPUT_MIME_TYPE] = mime_type

    def record_tokens(self, prompt: int, completion: int) -> None:
        """Record token consumption according to OpenInference standards."""
        p = max(0, prompt)
        c = max(0, completion)
        self._attributes[OpenInferenceAttributes.LLM_PROMPT_TOKENS] = p
        self._attributes[OpenInferenceAttributes.LLM_COMPLETION_TOKENS] = c
        self._attributes[OpenInferenceAttributes.LLM_TOTAL_TOKENS] = p + c

    def set_error(self, message: str) -> None:
        """Mark active span as failed with diagnostic message."""
        self.status = SpanStatusEnum.ERROR
        self.error_message = message
        self._attributes["error.message"] = message

    @property
    def attributes(self) -> dict[str, Any]:
        """Return a defensive copy of active attributes."""
        return dict(self._attributes)
