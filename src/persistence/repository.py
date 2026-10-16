"""Audit trail repository storing agent run records and execution traces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import get_settings
from models.audit import AuditLogRecord
from models.response import AgentFinalResponse
from observability.logger import get_logger
from persistence.postgres_client import (
    INSERT_AUDIT_LOG_SQL,
    SELECT_AUDIT_LOGS_BY_SESSION_SQL,
    connect_postgres,
    ensure_audit_table_exists,
)

logger = get_logger(__name__)

__all__ = ["AuditLogRepository"]


class AuditLogRepository:
    """Persists certified agent execution responses to PostgreSQL or JSON Lines fallback."""

    def __init__(
        self,
        fallback_path: Path = Path("traces.jsonl"),
        postgres_dsn: str | None = None,
        db_connection: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.fallback_path = fallback_path
        self._postgres_dsn = postgres_dsn or settings.postgres_dsn
        self._db_conn = db_connection
        self._db_initialized = db_connection is not None
        self._in_memory_records: list[AuditLogRecord] = []
        if db_connection is not None:
            ensure_audit_table_exists(db_connection)

    def _get_db(self) -> Any | None:
        """Lazily initialize PostgreSQL connection with exception shielding."""
        if self._db_initialized:
            return self._db_conn
        self._db_initialized = True
        self._db_conn = connect_postgres(self._postgres_dsn)
        if self._db_conn is not None:
            ensure_audit_table_exists(self._db_conn)
        return self._db_conn

    def save(self, record: AuditLogRecord) -> bool:
        """Persist audit record to PostgreSQL and local JSON Lines fallback."""
        conn = self._get_db()
        if conn is not None:
            try:
                params = record.model_dump(mode="json")
                params["trace_data"] = json.dumps(params["trace_data"])
                with conn.cursor() as cur:
                    cur.execute(INSERT_AUDIT_LOG_SQL, params)
                conn.commit()
                logger.info(
                    "audit_log_persisted_postgres", session_id=record.session_id
                )
            except Exception as exc:
                logger.warning(
                    "postgres_insert_failed_fallback_jsonl",
                    session_id=record.session_id,
                    error=str(exc),
                )

        try:
            payload = record.model_dump(mode="json")
            with open(self.fallback_path, "a", encoding="utf-8") as file:
                file.write(json.dumps(payload) + "\n")
            logger.info("audit_log_persisted_jsonl", session_id=record.session_id)
        except Exception as exc:
            logger.error(
                "audit_log_jsonl_persist_failed",
                session_id=record.session_id,
                error=str(exc),
            )

        self._in_memory_records.append(record)
        return True

    def save_response(
        self,
        response: AgentFinalResponse,
        tenant_id: str = "default_tenant",
        message_id: str | None = None,
        customer_email: str | None = None,
        trace_data: dict[str, Any] | None = None,
    ) -> bool:
        """Build AuditLogRecord from AgentFinalResponse and persist."""
        record = AuditLogRecord.from_response(
            response=response,
            tenant_id=tenant_id,
            message_id=message_id,
            customer_email=customer_email,
            trace_data=trace_data,
        )
        return self.save(record)

    def get_by_session_id(
        self, session_id: str, tenant_id: str = "default_tenant"
    ) -> list[AuditLogRecord]:
        """Query audit log records by session_id and tenant_id."""
        conn = self._get_db()
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        SELECT_AUDIT_LOGS_BY_SESSION_SQL,
                        {"session_id": session_id, "tenant_id": tenant_id},
                    )
                    rows = cur.fetchall()
                    if rows:
                        results: list[AuditLogRecord] = []
                        for r in rows:
                            if isinstance(r, dict):
                                data = dict(r)
                            else:
                                cols = [
                                    "session_id",
                                    "tenant_id",
                                    "message_id",
                                    "customer_email",
                                    "order_id",
                                    "intent",
                                    "status_resolution",
                                    "confidence_score",
                                    "duration_ms",
                                    "tokens_prompt",
                                    "tokens_completion",
                                    "cost_usd",
                                    "human_escalation_reason",
                                    "internal_technical_summary",
                                    "trace_data",
                                    "created_at",
                                ]
                                data = dict(zip(cols, r, strict=False))
                            if isinstance(data.get("trace_data"), str):
                                data["trace_data"] = json.loads(data["trace_data"])
                            results.append(AuditLogRecord.model_validate(data))
                        return results
            except Exception as exc:
                logger.warning(
                    "postgres_query_failed_using_file_fallback", error=str(exc)
                )

        records: list[AuditLogRecord] = []
        if self.fallback_path.exists():
            try:
                with open(self.fallback_path, encoding="utf-8") as file:
                    for line in file:
                        stripped = line.strip()
                        if not stripped:
                            continue
                        data = json.loads(stripped)
                        if (
                            data.get("session_id") == session_id
                            and data.get("tenant_id") == tenant_id
                        ):
                            records.append(AuditLogRecord.model_validate(data))
            except Exception as exc:
                logger.warning("fallback_file_read_error", error=str(exc))

        if not records:
            records = [
                r
                for r in self._in_memory_records
                if r.session_id == session_id and r.tenant_id == tenant_id
            ]

        return records

    def clear(self) -> None:
        """Clear in-memory records and truncate fallback file."""
        self._in_memory_records.clear()
        if self.fallback_path.exists():
            try:
                self.fallback_path.write_text("", encoding="utf-8")
            except Exception as exc:
                logger.warning("fallback_clear_failed", error=str(exc))

    async def save_async(self, record: AuditLogRecord) -> bool:
        """Asynchronously persist audit record."""
        return self.save(record)

    async def save_response_async(
        self,
        response: AgentFinalResponse,
        tenant_id: str = "default_tenant",
        message_id: str | None = None,
        customer_email: str | None = None,
        trace_data: dict[str, Any] | None = None,
    ) -> bool:
        """Asynchronously persist certified agent response."""
        return self.save_response(
            response=response,
            tenant_id=tenant_id,
            message_id=message_id,
            customer_email=customer_email,
            trace_data=trace_data,
        )

    async def get_by_session_id_async(
        self, session_id: str, tenant_id: str = "default_tenant"
    ) -> list[AuditLogRecord]:
        """Asynchronously query audit log records by session_id."""
        return self.get_by_session_id(session_id, tenant_id=tenant_id)
