"""Audit trail repository storing agent run records and execution traces."""

import json
from pathlib import Path
from typing import Any

from models.response import AgentFinalResponse
from observability.logger import get_logger

logger = get_logger(__name__)


class AuditLogRepository:
    """Persists certified agent execution responses to disk or database."""

    def __init__(self, fallback_path: Path = Path("traces.jsonl")) -> None:
        self.fallback_path = fallback_path

    def save_response(self, response: AgentFinalResponse) -> None:
        """Persist certified response as an append-only JSON Lines record."""
        payload: dict[str, Any] = response.model_dump(mode="json")
        try:
            with open(self.fallback_path, "a", encoding="utf-8") as file:
                file.write(json.dumps(payload) + "\n")
            logger.info("audit_log_persisted", session_id=response.session_id)
        except Exception as exc:
            logger.error(
                "audit_log_persist_failed",
                session_id=response.session_id,
                error=str(exc),
            )
