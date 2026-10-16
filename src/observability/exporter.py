"""Trace envelope serialization and exporter utilities for OpenInference and Langfuse."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from models.tools import ToolCallTrace
from models.tracing import (
    OpenInferenceAttributes,
    SpanKindEnum,
    SpanStatusEnum,
    TraceSpanRecord,
)

__all__ = [
    "build_trace_summary",
    "export_langfuse_trace_envelope",
    "export_openinference_traces",
    "tool_call_to_trace_span",
]


def tool_call_to_trace_span(
    trace: ToolCallTrace,
    trace_id: str,
    session_id: str,
    tenant_id: str,
    parent_span_id: str | None = None,
) -> TraceSpanRecord:
    """Bridge domain ToolCallTrace into an immutable OpenInference TOOL span."""
    span_id = uuid.uuid4().hex[:16]
    start_time = trace.timestamp
    end_time = datetime.fromtimestamp(
        trace.timestamp.timestamp() + (trace.duration_ms / 1000.0),
        tz=timezone.utc,
    )
    status = SpanStatusEnum.OK if trace.result.success else SpanStatusEnum.ERROR
    error_msg = trace.result.error_message if not trace.result.success else None

    param_json = json.dumps(trace.arguments, default=str)
    attributes: dict[str, Any] = {
        OpenInferenceAttributes.TOOL_NAME: trace.tool_name,
        OpenInferenceAttributes.TOOL_PARAMETERS: param_json,
        OpenInferenceAttributes.INPUT_VALUE: param_json,
        OpenInferenceAttributes.OUTPUT_VALUE: json.dumps(
            trace.result.data or {}, default=str
        ),
    }
    if trace.result.error_code:
        attributes["error.code"] = trace.result.error_code

    return TraceSpanRecord(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        name=f"tool:{trace.tool_name}",
        span_kind=SpanKindEnum.TOOL,
        session_id=session_id,
        tenant_id=tenant_id,
        start_time=start_time,
        end_time=end_time,
        duration_ms=trace.duration_ms,
        status=status,
        error_message=error_msg,
        attributes=attributes,
    )


def build_trace_summary(
    spans: tuple[TraceSpanRecord, ...],
    session_id: str,
    tenant_id: str,
    trace_id: str,
) -> dict[str, Any]:
    """Compute aggregated telemetry summary across session spans."""
    total_spans = len(spans)
    total_duration = round(sum(s.duration_ms for s in spans), 2)
    tool_count = sum(1 for s in spans if s.span_kind == SpanKindEnum.TOOL)
    llm_count = sum(1 for s in spans if s.span_kind == SpanKindEnum.LLM)
    error_count = sum(1 for s in spans if s.status == SpanStatusEnum.ERROR)

    return {
        "session_id": session_id,
        "tenant_id": tenant_id,
        "trace_id": trace_id,
        "total_spans": total_spans,
        "total_duration_ms": total_duration,
        "tool_invocations_count": tool_count,
        "llm_inferences_count": llm_count,
        "error_count": error_count,
    }


def export_openinference_traces(
    spans: tuple[TraceSpanRecord, ...],
) -> list[dict[str, Any]]:
    """Export sequence of spans formatted according to OpenInference specifications."""
    return [s.to_openinference_dict() for s in spans]


def export_langfuse_trace_envelope(
    spans: tuple[TraceSpanRecord, ...],
    trace_id: str,
    session_id: str,
    tenant_id: str,
    service_name: str,
) -> dict[str, Any]:
    """Export structured trace envelope ready for Langfuse trace ingestion."""
    summary = build_trace_summary(spans, session_id, tenant_id, trace_id)
    return {
        "id": trace_id,
        "name": f"support_agent_{session_id}",
        "sessionId": session_id,
        "userId": tenant_id,
        "metadata": {
            "service_name": service_name,
            "tenant_id": tenant_id,
            "summary": summary,
        },
        "observations": [s.to_langfuse_observation() for s in spans],
    }
