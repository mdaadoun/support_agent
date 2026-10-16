"""Domain models and DTOs for OpenInference and OpenTelemetry tracing."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import ConfigDict, Field

from models.base import BaseDTO

__all__ = [
    "OpenInferenceAttributes",
    "SpanKindEnum",
    "SpanStatusEnum",
    "TraceSpanRecord",
]


class SpanKindEnum(StrEnum):
    """OpenInference span categories for autonomous agent workflows."""

    AGENT = "AGENT"
    TOOL = "TOOL"
    LLM = "LLM"
    CHAIN = "CHAIN"


class SpanStatusEnum(StrEnum):
    """Execution status outcome for an individual trace span."""

    OK = "OK"
    ERROR = "ERROR"


class OpenInferenceAttributes:
    """Semantic convention attribute keys adhering to OpenInference specifications."""

    OPENINFERENCE_SPAN_KIND: str = "openinference.span.kind"
    INPUT_VALUE: str = "input.value"
    INPUT_MIME_TYPE: str = "input.mime_type"
    OUTPUT_VALUE: str = "output.value"
    OUTPUT_MIME_TYPE: str = "output.mime_type"
    TOOL_NAME: str = "tool.name"
    TOOL_PARAMETERS: str = "tool.parameters"
    TOOL_OUTPUT: str = "tool.output"
    LLM_MODEL_NAME: str = "llm.model_name"
    LLM_PROMPT_TOKENS: str = "llm.token_count.prompt"
    LLM_COMPLETION_TOKENS: str = "llm.token_count.completion"
    LLM_TOTAL_TOKENS: str = "llm.token_count.total"
    SESSION_ID: str = "session.id"
    TENANT_ID: str = "tenant.id"


class TraceSpanRecord(BaseDTO):
    """Immutable trace span snapshot compliant with OpenInference conventions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    name: str
    span_kind: SpanKindEnum
    session_id: str
    tenant_id: str = "default_tenant"
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: datetime | None = None
    duration_ms: float = Field(default=0.0, ge=0.0)
    status: SpanStatusEnum = SpanStatusEnum.OK
    error_message: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    def to_openinference_dict(self) -> dict[str, Any]:
        """Convert span record into standard OpenInference trace dictionary."""
        span_attrs = dict(self.attributes)
        span_attrs[OpenInferenceAttributes.OPENINFERENCE_SPAN_KIND] = (
            self.span_kind.value
        )
        span_attrs[OpenInferenceAttributes.SESSION_ID] = self.session_id
        span_attrs[OpenInferenceAttributes.TENANT_ID] = self.tenant_id

        return {
            "id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "error_message": self.error_message,
            "attributes": span_attrs,
        }

    def to_langfuse_observation(self) -> dict[str, Any]:
        """Convert span record into Langfuse-compatible observation dictionary."""
        langfuse_type = "SPAN"
        if self.span_kind == SpanKindEnum.LLM:
            langfuse_type = "GENERATION"
        elif self.span_kind == SpanKindEnum.TOOL:
            langfuse_type = "EVENT"

        return {
            "id": self.span_id,
            "traceId": self.trace_id,
            "parentId": self.parent_span_id,
            "type": langfuse_type,
            "name": self.name,
            "startTime": self.start_time.isoformat(),
            "endTime": self.end_time.isoformat() if self.end_time else None,
            "metadata": {
                "span_kind": self.span_kind.value,
                "session_id": self.session_id,
                "tenant_id": self.tenant_id,
                **self.attributes,
            },
            "level": "ERROR" if self.status == SpanStatusEnum.ERROR else "DEFAULT",
            "statusMessage": self.error_message,
        }
