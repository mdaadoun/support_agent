"""ReAct decision-action-observation execution loop engine for 8_support_agent."""

import json
import time
from datetime import datetime, timezone
from typing import Any

from agent.controller import AgentFSMController
from agent.prompts import PromptManager
from agent.protocols import LLMClientProtocol, ToolRegistryProtocol
from agent.response_builder import (
    build_escalated_response,
    synthesize_certified_response,
)
from agent.state import AgentLifecycleState, AgentSessionState
from agent.validator import ZeroLLMAuthorityGuard
from core.config import get_settings
from models.enums import IntentEnum, ResolutionStatusEnum
from models.response import AgentFinalResponse
from models.tools import ToolCallTrace
from observability.logger import get_logger

logger = get_logger(__name__)

__all__ = ["ReActLoopEngine"]


class ReActLoopEngine:
    """Orchestrates multi-turn ReAct decision-action-observation cycles."""

    def __init__(
        self,
        llm_client: LLMClientProtocol | None = None,
        tool_registry: ToolRegistryProtocol | None = None,
        max_iterations: int | None = None,
        confidence_threshold: float | None = None,
        authority_guard: ZeroLLMAuthorityGuard | None = None,
    ) -> None:
        settings = get_settings()
        self.max_iterations = max_iterations or settings.agent_max_iterations
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.confidence_threshold
        )
        self.authority_guard = authority_guard or ZeroLLMAuthorityGuard()

        if llm_client is not None:
            self.llm_client = llm_client
        else:
            from clients.llm_client import LLMClient

            self.llm_client = LLMClient()

        if tool_registry is not None:
            self.tool_registry = tool_registry
        else:
            from tools.registry import create_default_registry

            self.tool_registry = create_default_registry()

    async def run(self, session: AgentSessionState) -> AgentFinalResponse:
        """Run the complete ReAct loop until resolution, escalation, or limit reach."""
        start_time = time.perf_counter()
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cost_usd = 0.0

        if session.current_state == AgentLifecycleState.RECEIVED:
            AgentFSMController.transition(
                session,
                AgentLifecycleState.ANALYZING,
                reason="Inbound communication analysis initiated",
            )

        # Pre-execution security and scope boundary guard
        if session.extracted_demand:
            if session.extracted_demand.is_legal_threat_or_aggressive:
                AgentFSMController.transition_to_human(
                    session, reason="HOSTILE_OR_LEGAL_THREAT"
                )
                return build_escalated_response(
                    session=session,
                    reason="Hostile tone or legal threat detected; escalated to human supervisor.",
                    intent=session.extracted_demand.intent,
                    start_time=start_time,
                )
            if session.extracted_demand.intent == IntentEnum.OUT_OF_SCOPE:
                AgentFSMController.transition_to_human(
                    session, reason="OUT_OF_SCOPE_INTENT"
                )
                return build_escalated_response(
                    session=session,
                    reason="Inquiry intent is outside automated scope; escalated to human agent.",
                    intent=IntentEnum.OUT_OF_SCOPE,
                    start_time=start_time,
                )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": PromptManager.get_agent_system_prompt()},
            {
                "role": "user",
                "content": PromptManager.build_initial_agent_prompt(session),
            },
        ]
        tools = self.tool_registry.get_openai_tools()

        while True:
            llm_resp = await self.llm_client.generate_with_tools(
                messages=messages,
                tools=tools,
            )
            total_prompt_tokens += llm_resp.usage.prompt_tokens
            total_completion_tokens += llm_resp.usage.completion_tokens
            total_cost_usd += llm_resp.usage.cost_usd

            if not llm_resp.has_tool_calls:
                break

            if session.iteration_count >= self.max_iterations:
                logger.warning(
                    "react_loop_ceiling_reached",
                    session_id=session.session_id,
                    iteration_count=session.iteration_count,
                    max_iterations=self.max_iterations,
                )
                AgentFSMController.transition_to_human(
                    session, reason="LOOP_LIMIT_EXCEEDED"
                )
                return build_escalated_response(
                    session=session,
                    reason=f"Exceeded maximum tool iterations ({self.max_iterations}); escalated to human review.",
                    intent=(
                        session.extracted_demand.intent
                        if session.extracted_demand
                        else IntentEnum.ORDER_STATUS
                    ),
                    start_time=start_time,
                    prompt_tokens=total_prompt_tokens,
                    completion_tokens=total_completion_tokens,
                    cost_usd=total_cost_usd,
                )

            tool_names = [tc.name for tc in llm_resp.tool_calls]
            AgentFSMController.transition(
                session,
                AgentLifecycleState.EXECUTING_TOOL,
                reason=f"Executing tool(s): {', '.join(tool_names)}",
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": llm_resp.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in llm_resp.tool_calls
                    ],
                }
            )

            for tc in llm_resp.tool_calls:
                t_start = time.perf_counter()
                res = await self.tool_registry.execute(
                    tool_name=tc.name,
                    session_id=session.session_id,
                    **tc.arguments,
                )
                dur_ms = (time.perf_counter() - t_start) * 1000.0
                trace = ToolCallTrace(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    result=res,
                    timestamp=datetime.now(timezone.utc),
                    duration_ms=round(dur_ms, 2),
                )
                session.record_trace(trace)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": json.dumps(res.model_dump()),
                    }
                )

            AgentFSMController.transition(
                session,
                AgentLifecycleState.OBSERVING,
                reason="Tool execution completed; observing outcomes",
            )
            session.iteration_count += 1

        AgentFSMController.transition(
            session,
            AgentLifecycleState.GENERATING_RESPONSE,
            reason="Synthesizing certified final response",
        )

        final_response = await synthesize_certified_response(
            llm_client=self.llm_client,
            session=session,
            confidence_threshold=self.confidence_threshold,
            start_time=start_time,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            cost_usd=total_cost_usd,
            authority_guard=self.authority_guard,
        )

        final_response, _ = self.authority_guard.guard_response(
            final_response, session.tool_traces
        )

        if (
            final_response.status_resolution
            == ResolutionStatusEnum.REQUIRES_HUMAN_REVIEW
        ):
            reason = final_response.human_escalation_reason or "REQUIRES_HUMAN_REVIEW"
            AgentFSMController.transition_to_human(session, reason=reason)
        else:
            AgentFSMController.transition(
                session,
                AgentLifecycleState.COMPLETED,
                reason="Final response certified and resolution completed",
            )

        return final_response
