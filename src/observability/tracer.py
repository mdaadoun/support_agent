"""OpenTelemetry and Langfuse tracing adapter adhering to OpenInference conventions."""

import json
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import structlog

from core.exceptions import TracingError
from models.tools import ToolCallTrace
from models.tracing import (
    OpenInferenceAttributes,
    SpanKindEnum,
    TraceSpanRecord,
)
from observability.exporter import (
    build_trace_summary,
    export_langfuse_trace_envelope,
    export_openinference_traces,
    tool_call_to_trace_span,
)
from observability.span import ActiveSpan

logger = structlog.get_logger(__name__)

__all__ = ["AgentTracer", "get_tracer"]


class AgentTracer:
    """Manages OpenInference and OpenTelemetry telemetry spans with Langfuse export."""

    def __init__(
        self,
        session_id: str,
        tenant_id: str = "default_tenant",
        service_name: str = "support-agent",
        enable_otel: bool = True,
        trace_id: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.service_name = service_name
        self.trace_id = trace_id or uuid.uuid4().hex
        self._spans: list[TraceSpanRecord] = []
        self._span_stack: list[str] = []
        self._otel_tracer: Any = None

        if enable_otel:
            try:
                import opentelemetry.trace as otel_trace

                self._otel_tracer = otel_trace.get_tracer(service_name)
            except Exception as exc:
                logger.debug("otel_tracer_disabled", error=str(exc))
                self._otel_tracer = None

    @contextmanager
    def span(
        self,
        operation: str,
        span_kind: SpanKindEnum = SpanKindEnum.AGENT,
        parent_span_id: str | None = None,
        **attributes: Any,
    ) -> Generator[ActiveSpan, None, None]:
        """Track elapsed duration, OpenInference metadata, and hierarchical spans."""
        span_id = uuid.uuid4().hex[:16]
        parent_id = parent_span_id or (
            self._span_stack[-1] if self._span_stack else None
        )
        self._span_stack.append(span_id)

        active = ActiveSpan(
            span_id=span_id,
            trace_id=self.trace_id,
            name=operation,
            span_kind=span_kind,
            parent_span_id=parent_id,
            attributes=attributes,
        )
        perf_start = time.perf_counter()
        start_time = datetime.now(timezone.utc)
        otel_span = None

        if self._otel_tracer is not None:
            try:
                otel_span = self._otel_tracer.start_span(
                    name=operation,
                    attributes={
                        OpenInferenceAttributes.OPENINFERENCE_SPAN_KIND: span_kind.value,
                        OpenInferenceAttributes.SESSION_ID: self.session_id,
                        OpenInferenceAttributes.TENANT_ID: self.tenant_id,
                    },
                )
            except Exception:
                otel_span = None

        logger.info("span_start", session_id=self.session_id, operation=operation)
        try:
            yield active
        except Exception as exc:
            active.set_error(str(exc))
            if otel_span is not None:
                try:
                    from opentelemetry.trace import StatusCode

                    otel_span.record_exception(exc)
                    otel_span.set_status(StatusCode.ERROR, str(exc))
                except Exception:
                    pass
            raise
        finally:
            duration_ms = round((time.perf_counter() - perf_start) * 1000.0, 2)
            end_time = datetime.now(timezone.utc)
            if self._span_stack and self._span_stack[-1] == span_id:
                self._span_stack.pop()

            if otel_span is not None:
                try:
                    for k, v in active.attributes.items():
                        if isinstance(v, str | int | float | bool):
                            otel_span.set_attribute(k, v)
                    otel_span.end()
                except Exception:
                    pass

            try:
                record = TraceSpanRecord(
                    span_id=span_id,
                    trace_id=self.trace_id,
                    parent_span_id=parent_id,
                    name=operation,
                    span_kind=span_kind,
                    session_id=self.session_id,
                    tenant_id=self.tenant_id,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    status=active.status,
                    error_message=active.error_message,
                    attributes=active.attributes,
                )
                self._spans.append(record)
            except Exception as exc:
                raise TracingError(f"Failed to record trace span: {exc}") from exc

            logger.info("span_end", session_id=self.session_id, duration_ms=duration_ms)

    @contextmanager
    def agent_span(
        self, name: str = "agent_run", **attributes: Any
    ) -> Generator[ActiveSpan, None, None]:
        """Convenience context manager for high-level agent reasoning span."""
        with self.span(name, span_kind=SpanKindEnum.AGENT, **attributes) as s:
            yield s

    @contextmanager
    def tool_span(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        **attributes: Any,
    ) -> Generator[ActiveSpan, None, None]:
        """Convenience context manager for discrete tool execution span."""
        attrs = dict(attributes)
        attrs[OpenInferenceAttributes.TOOL_NAME] = tool_name
        if arguments:
            p_json = json.dumps(arguments, default=str)
            attrs[OpenInferenceAttributes.TOOL_PARAMETERS] = p_json
            attrs[OpenInferenceAttributes.INPUT_VALUE] = p_json
        with self.span(f"tool:{tool_name}", span_kind=SpanKindEnum.TOOL, **attrs) as s:
            yield s

    @contextmanager
    def llm_span(
        self,
        model_name: str,
        prompt: str | None = None,
        **attributes: Any,
    ) -> Generator[ActiveSpan, None, None]:
        """Convenience context manager for LLM inference span."""
        attrs = dict(attributes)
        attrs[OpenInferenceAttributes.LLM_MODEL_NAME] = model_name
        if prompt:
            attrs[OpenInferenceAttributes.INPUT_VALUE] = prompt
        with self.span(f"llm:{model_name}", span_kind=SpanKindEnum.LLM, **attrs) as s:
            yield s

    def record_tool_call_trace(self, trace: ToolCallTrace) -> TraceSpanRecord:
        """Bridge domain ToolCallTrace into an immutable OpenInference TOOL span."""
        parent_id = self._span_stack[-1] if self._span_stack else None
        record = tool_call_to_trace_span(
            trace, self.trace_id, self.session_id, self.tenant_id, parent_id
        )
        self._spans.append(record)
        return record

    def get_spans(self) -> tuple[TraceSpanRecord, ...]:
        """Return an immutable snapshot of all recorded spans for this session."""
        return tuple(self._spans)

    def get_span(self, span_id: str) -> TraceSpanRecord | None:
        """Lookup a discrete span by its unique identifier."""
        return next((s for s in self._spans if s.span_id == span_id), None)

    def export_openinference(self) -> list[dict[str, Any]]:
        """Export list of spans compliant with OpenInference specifications."""
        return export_openinference_traces(self.get_spans())

    def export_langfuse_traces(self) -> dict[str, Any]:
        """Export trace envelope ready for Langfuse trace ingestion."""
        return export_langfuse_trace_envelope(
            self.get_spans(),
            self.trace_id,
            self.session_id,
            self.tenant_id,
            self.service_name,
        )

    def to_trace_summary(self) -> dict[str, Any]:
        """Compute aggregated telemetry summary across session spans."""
        return build_trace_summary(
            self.get_spans(), self.session_id, self.tenant_id, self.trace_id
        )

    def clear(self) -> None:
        """Clear the recorded spans and active stack."""
        self._spans.clear()
        self._span_stack.clear()


def get_tracer(
    session_id: str,
    tenant_id: str = "default_tenant",
    service_name: str = "support-agent",
    enable_otel: bool = True,
) -> AgentTracer:
    """Factory helper creating an AgentTracer instance."""
    return AgentTracer(
        session_id=session_id,
        tenant_id=tenant_id,
        service_name=service_name,
        enable_otel=enable_otel,
    )
