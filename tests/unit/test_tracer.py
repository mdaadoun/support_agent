"""Unit tests for OpenInference and OpenTelemetry tracing adapter."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from models.tools import ToolCallTrace, ToolExecutionResult
from models.tracing import (
    OpenInferenceAttributes,
    SpanKindEnum,
    SpanStatusEnum,
    TraceSpanRecord,
)
from observability.span import ActiveSpan
from observability.tracer import AgentTracer, get_tracer


def test_span_kind_and_status_enums() -> None:
    """Verify standard OpenInference enumeration contracts."""
    assert SpanKindEnum.AGENT == "AGENT"
    assert SpanKindEnum.TOOL == "TOOL"
    assert SpanKindEnum.LLM == "LLM"
    assert SpanKindEnum.CHAIN == "CHAIN"
    assert SpanStatusEnum.OK == "OK"
    assert SpanStatusEnum.ERROR == "ERROR"


def test_trace_span_record_immutability() -> None:
    """Verify TraceSpanRecord enforces deep immutability and forbids extra fields."""
    record = TraceSpanRecord(
        span_id="span-12345",
        trace_id="trace-67890",
        name="test_operation",
        span_kind=SpanKindEnum.AGENT,
        session_id="sess-01",
        tenant_id="tenant-01",
    )
    assert record.span_id == "span-12345"
    assert record.status == SpanStatusEnum.OK

    with pytest.raises(ValidationError):
        setattr(record, "status", SpanStatusEnum.ERROR)  # noqa: B010

    with pytest.raises(ValidationError):
        TraceSpanRecord(
            span_id="s1",
            trace_id="t1",
            name="n1",
            span_kind=SpanKindEnum.AGENT,
            session_id="sess-01",
            unknown_attr="invalid",  # type: ignore[call-arg]
        )


def test_active_span_attributes_and_tokens() -> None:
    """Verify ActiveSpan in-flight mutations comply with OpenInference conventions."""
    active = ActiveSpan(
        span_id="s1",
        trace_id="t1",
        name="llm_step",
        span_kind=SpanKindEnum.LLM,
    )
    active.set_attribute("custom.key", "value123")
    active.set_attributes(extra_a="valA", extra_b="valB")
    active.set_input({"query": "where is order?"})
    active.set_output({"status": "shipped"})
    active.record_tokens(prompt=120, completion=45)

    attrs = active.attributes
    assert attrs["custom.key"] == "value123"
    assert attrs[OpenInferenceAttributes.INPUT_VALUE] == '{"query": "where is order?"}'
    assert attrs[OpenInferenceAttributes.OUTPUT_VALUE] == '{"status": "shipped"}'
    assert attrs[OpenInferenceAttributes.LLM_PROMPT_TOKENS] == 120
    assert attrs[OpenInferenceAttributes.LLM_COMPLETION_TOKENS] == 45
    assert attrs[OpenInferenceAttributes.LLM_TOTAL_TOKENS] == 165


def test_tracer_basic_span_execution() -> None:
    """Verify discrete span execution records duration, status, and metadata."""
    tracer = AgentTracer(session_id="SESS-TEST-01", tenant_id="tenant_a")
    assert tracer.session_id == "SESS-TEST-01"
    assert tracer.tenant_id == "tenant_a"

    with tracer.span("execute_computation", step="init") as s:
        s.set_attribute("computed_val", 42)

    spans = tracer.get_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "execute_computation"
    assert span.span_kind == SpanKindEnum.AGENT
    assert span.status == SpanStatusEnum.OK
    assert span.duration_ms >= 0.0
    assert span.attributes["step"] == "init"
    assert span.attributes["computed_val"] == 42
    assert tracer.get_span(span.span_id) == span


def test_tracer_specialized_spans_and_nesting() -> None:
    """Verify agent_span, tool_span, and llm_span create hierarchical trees."""
    tracer = get_tracer(session_id="SESS-NESTED-01", tenant_id="tenant_b")

    with tracer.agent_span("agent_reasoning") as root:
        root.set_attribute("cycle", 1)

        with tracer.tool_span(
            "get_order_details", arguments={"order_id": "CMD-111"}
        ) as t_span:
            t_span.set_output({"order_id": "CMD-111", "status": "DELIVERED"})

        with tracer.llm_span("gpt-4o-mini", prompt="Summarize delivery") as l_span:
            l_span.record_tokens(80, 20)

    spans = tracer.get_spans()
    assert len(spans) == 3
    tool_span = next(s for s in spans if s.span_kind == SpanKindEnum.TOOL)
    llm_span = next(s for s in spans if s.span_kind == SpanKindEnum.LLM)
    root_span = next(s for s in spans if s.span_kind == SpanKindEnum.AGENT)

    assert tool_span.parent_span_id == root_span.span_id
    assert llm_span.parent_span_id == root_span.span_id
    assert root_span.parent_span_id is None
    assert (
        tool_span.attributes[OpenInferenceAttributes.TOOL_NAME] == "get_order_details"
    )
    assert llm_span.attributes[OpenInferenceAttributes.LLM_MODEL_NAME] == "gpt-4o-mini"


def test_tracer_error_capture_and_propagation() -> None:
    """Verify tracer marks span as failed, records diagnostics, and re-raises error."""
    tracer = AgentTracer(session_id="SESS-ERR-01")

    with (
        pytest.raises(ValueError, match="Database connection dropped"),
        tracer.span("faulty_operation"),
    ):
        raise ValueError("Database connection dropped")

    spans = tracer.get_spans()
    assert len(spans) == 1
    failed = spans[0]
    assert failed.status == SpanStatusEnum.ERROR
    assert failed.error_message == "Database connection dropped"
    assert failed.attributes["error.message"] == "Database connection dropped"


def test_tracer_record_tool_call_trace() -> None:
    """Verify record_tool_call_trace converts domain ToolCallTrace into an OpenInference span."""
    tracer = AgentTracer(session_id="SESS-BRIDGE-01")
    trace = ToolCallTrace(
        tool_call_id="call_calc_99999999",
        tool_name="calculate_refund_eligibility",
        arguments={"order_id": "CMD-222", "days_elapsed": 5},
        result=ToolExecutionResult(
            success=True,
            tool_name="calculate_refund_eligibility",
            data={"is_eligible": True, "amount_cents": 4900},
        ),
        timestamp=datetime.now(timezone.utc),
        duration_ms=45.2,
    )

    span = tracer.record_tool_call_trace(trace)
    assert span.span_kind == SpanKindEnum.TOOL
    assert span.name == "tool:calculate_refund_eligibility"
    assert span.status == SpanStatusEnum.OK
    assert span.duration_ms == 45.2
    assert "CMD-222" in span.attributes[OpenInferenceAttributes.INPUT_VALUE]

    # Failed tool trace with error code
    failed_trace = ToolCallTrace(
        tool_call_id="call_err_00000000",
        tool_name="get_order_details",
        arguments={"order_id": "CMD-404"},
        result=ToolExecutionResult(
            success=False,
            tool_name="get_order_details",
            error_code="ORDER_NOT_FOUND",
            error_message="Order CMD-404 missing",
        ),
        timestamp=datetime.now(timezone.utc),
        duration_ms=12.0,
    )
    failed_span = tracer.record_tool_call_trace(failed_trace)
    assert failed_span.status == SpanStatusEnum.ERROR
    assert failed_span.error_message == "Order CMD-404 missing"
    assert failed_span.attributes["error.code"] == "ORDER_NOT_FOUND"


def test_tracer_export_openinference_and_langfuse() -> None:
    """Verify export formats conform to OpenInference and Langfuse specifications."""
    tracer = AgentTracer(session_id="SESS-EXP-01", tenant_id="tenant_exp")

    with tracer.tool_span("calculate_delivery_delay", arguments={"delay": 3}):
        pass

    # OpenInference export
    oi_traces = tracer.export_openinference()
    assert len(oi_traces) == 1
    first_oi = oi_traces[0]
    assert first_oi["name"] == "tool:calculate_delivery_delay"
    assert (
        first_oi["attributes"][OpenInferenceAttributes.OPENINFERENCE_SPAN_KIND]
        == "TOOL"
    )
    assert first_oi["attributes"][OpenInferenceAttributes.SESSION_ID] == "SESS-EXP-01"

    # Langfuse trace envelope export
    lf_trace = tracer.export_langfuse_traces()
    assert lf_trace["sessionId"] == "SESS-EXP-01"
    assert lf_trace["userId"] == "tenant_exp"
    assert len(lf_trace["observations"]) == 1
    assert lf_trace["observations"][0]["name"] == "tool:calculate_delivery_delay"

    # Summary
    summary = tracer.to_trace_summary()
    assert summary["total_spans"] == 1
    assert summary["tool_invocations_count"] == 1
    assert summary["llm_inferences_count"] == 0
    assert summary["error_count"] == 0

    tracer.clear()
    assert len(tracer.get_spans()) == 0


def test_tracer_otel_resilience_and_disabled_mode() -> None:
    """Verify tracer operates cleanly when OpenTelemetry is disabled or encounters faults."""
    tracer_disabled = AgentTracer(session_id="SESS-NO-OTEL", enable_otel=False)
    with tracer_disabled.span("offline_step"):
        pass
    assert len(tracer_disabled.get_spans()) == 1

    # Faulty OTel tracer mocking
    tracer_faulty = AgentTracer(session_id="SESS-FAULTY-OTEL", enable_otel=True)
    mock_otel = MagicMock()
    mock_otel.start_span.side_effect = RuntimeError("OTel buffer overflow")
    tracer_faulty._otel_tracer = mock_otel

    with tracer_faulty.span("resilient_step"):
        pass
    assert len(tracer_faulty.get_spans()) == 1
