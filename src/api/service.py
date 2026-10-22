"""Application service coordinating support agent execution and state retrieval."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from agent.loop import ReActLoopEngine
from agent.state import create_session
from core.exceptions import BusinessRuleViolationError, SessionNotFoundError
from models.email import InboundEmailMessage
from models.response import AgentFinalResponse
from models.session import AgentSessionSnapshot
from observability.logger import get_logger
from persistence.repository import AuditLogRepository
from persistence.session_store import SessionStateStore
from security.pre_extraction import classify_inbound_demand

if TYPE_CHECKING:
    from agent.state import AgentSessionState

logger = get_logger(__name__)

TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")

__all__ = ["AgentService"]


class AgentService:
    """Application service coordinating agent execution, persistence, and audit logging."""

    def __init__(
        self,
        engine: ReActLoopEngine | None = None,
        session_store: SessionStateStore | None = None,
        audit_repo: AuditLogRepository | None = None,
    ) -> None:
        self.engine = engine or ReActLoopEngine()
        self.session_store = session_store or SessionStateStore()
        self.audit_repo = audit_repo or AuditLogRepository()

    @staticmethod
    def validate_tenant_id(tenant_id: str) -> None:
        """Enforce strict boundary validation on tenant identifier."""
        if not tenant_id or not TENANT_ID_PATTERN.match(tenant_id):
            raise BusinessRuleViolationError(
                f"Invalid tenant_id '{tenant_id}'. Must be alphanumeric with underscores or dashes.",
                error_code="INVALID_TENANT_ID",
            )

    @staticmethod
    def validate_session_id(session_id: str) -> None:
        """Enforce strict boundary validation on session identifier."""
        if not session_id or not SESSION_ID_PATTERN.match(session_id):
            raise BusinessRuleViolationError(
                f"Invalid session_id '{session_id}'. Must be alphanumeric with underscores or dashes.",
                error_code="INVALID_SESSION_ID",
            )

    async def process_email(
        self,
        message: InboundEmailMessage,
        tenant_id: str,
        session_id: str | None = None,
    ) -> AgentFinalResponse:
        """Execute end-to-end support agent cycle for an inbound customer email."""
        self.validate_tenant_id(tenant_id)
        if session_id:
            self.validate_session_id(session_id)
            sid = session_id
        else:
            sid = f"SESS-{uuid.uuid4().hex[:8].upper()}"

        logger.info(
            "agent_service_process_email_start",
            session_id=sid,
            tenant_id=tenant_id,
            message_id=message.message_id,
        )

        session: AgentSessionState = create_session(
            session_id=sid,
            inbound_message=message,
            tenant_id=tenant_id,
        )

        # Pre-extraction and security classification
        demand = classify_inbound_demand(message)
        session.extracted_demand = demand

        # Execute ReAct reasoning loop
        response = await self.engine.run(session)

        # Persist session state snapshot
        self.session_store.save(session)

        # Persist audit record
        self.audit_repo.save_response(
            response=response,
            tenant_id=tenant_id,
            message_id=message.message_id,
            customer_email=str(message.sender_email),
        )

        logger.info(
            "agent_service_process_email_complete",
            session_id=sid,
            tenant_id=tenant_id,
            status=response.status_resolution.value,
        )
        return response

    async def get_session(
        self,
        session_id: str,
        tenant_id: str,
    ) -> AgentSessionSnapshot:
        """Retrieve verified session snapshot from persistent store with tenant isolation."""
        self.validate_tenant_id(tenant_id)
        self.validate_session_id(session_id)

        snapshot = self.session_store.get_snapshot(
            session_id=session_id,
            tenant_id=tenant_id,
        )
        if snapshot is None:
            raise SessionNotFoundError(session_id)
        return snapshot
