"""PostgreSQL database connectivity and audit trail DDL definitions."""

from typing import Any

from observability.logger import get_logger

try:
    import psycopg
except ImportError:
    try:
        import psycopg2 as psycopg
    except ImportError:
        psycopg = None

logger = get_logger(__name__)

__all__ = [
    "CREATE_AUDIT_LOG_TABLE_SQL",
    "INSERT_AUDIT_LOG_SQL",
    "SELECT_AUDIT_LOGS_BY_SESSION_SQL",
    "SELECT_AUDIT_LOGS_BY_TENANT_SQL",
    "connect_postgres",
    "ensure_audit_table_exists",
]

CREATE_AUDIT_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS agent_audit_logs (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL DEFAULT 'default_tenant',
    message_id VARCHAR(128),
    customer_email VARCHAR(255),
    order_id VARCHAR(64),
    intent VARCHAR(64) NOT NULL,
    status_resolution VARCHAR(64) NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL,
    duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    tokens_prompt INTEGER NOT NULL DEFAULT 0,
    tokens_completion INTEGER NOT NULL DEFAULT 0,
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    human_escalation_reason TEXT,
    internal_technical_summary VARCHAR(250),
    trace_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_session_tenant ON agent_audit_logs(tenant_id, session_id);
CREATE INDEX IF NOT EXISTS idx_audit_customer_email ON agent_audit_logs(customer_email);
"""

INSERT_AUDIT_LOG_SQL = """
INSERT INTO agent_audit_logs (
    session_id,
    tenant_id,
    message_id,
    customer_email,
    order_id,
    intent,
    status_resolution,
    confidence_score,
    duration_ms,
    tokens_prompt,
    tokens_completion,
    cost_usd,
    human_escalation_reason,
    internal_technical_summary,
    trace_data,
    created_at
) VALUES (
    %(session_id)s,
    %(tenant_id)s,
    %(message_id)s,
    %(customer_email)s,
    %(order_id)s,
    %(intent)s,
    %(status_resolution)s,
    %(confidence_score)s,
    %(duration_ms)s,
    %(tokens_prompt)s,
    %(tokens_completion)s,
    %(cost_usd)s,
    %(human_escalation_reason)s,
    %(internal_technical_summary)s,
    %(trace_data)s,
    %(created_at)s
);
"""

SELECT_AUDIT_LOGS_BY_SESSION_SQL = """
SELECT
    session_id,
    tenant_id,
    message_id,
    customer_email,
    order_id,
    intent,
    status_resolution,
    confidence_score,
    duration_ms,
    tokens_prompt,
    tokens_completion,
    cost_usd,
    human_escalation_reason,
    internal_technical_summary,
    trace_data,
    created_at
FROM agent_audit_logs
WHERE session_id = %(session_id)s AND tenant_id = %(tenant_id)s
ORDER BY created_at DESC;
"""

SELECT_AUDIT_LOGS_BY_TENANT_SQL = """
SELECT
    session_id,
    tenant_id,
    message_id,
    customer_email,
    order_id,
    intent,
    status_resolution,
    confidence_score,
    duration_ms,
    tokens_prompt,
    tokens_completion,
    cost_usd,
    human_escalation_reason,
    internal_technical_summary,
    trace_data,
    created_at
FROM agent_audit_logs
WHERE tenant_id = %(tenant_id)s
ORDER BY created_at DESC
LIMIT %(limit)s;
"""


def connect_postgres(postgres_dsn: str) -> Any | None:
    """Establish connection to PostgreSQL database with exception shielding."""
    if psycopg is None:
        return None
    try:
        conn = psycopg.connect(postgres_dsn)
        logger.info("postgres_audit_db_connected", dsn=postgres_dsn)
        return conn
    except Exception as exc:
        logger.debug("postgres_connection_skipped_using_fallback", error=str(exc))
        return None


def ensure_audit_table_exists(conn: Any) -> bool:
    """Ensure agent_audit_logs table and indices exist."""
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_AUDIT_LOG_TABLE_SQL)
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("ensure_audit_table_failed", error=str(exc))
        return False
