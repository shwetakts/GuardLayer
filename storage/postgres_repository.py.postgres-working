from typing import Dict, List, Any, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from storage.base import AuditRepository


class PostgresAuditRepository(AuditRepository):
    """PostgreSQL-backed audit repository."""

    def __init__(self, database_url: str):
        """Initialize the PostgreSQL repository and ensure the schema exists."""

        if not database_url:
            raise ValueError("DATABASE_URL must be provided")

        if not database_url.startswith("postgresql"):
            raise ValueError(
                "PostgresAuditRepository requires a PostgreSQL DATABASE_URL"
            )

        self.database_url = database_url

        # SQLAlchemy connection pooling is useful when multiple
        # requests hit GuardLayer concurrently.
        self.engine: Engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=1800,
        )

        self._init_db()

    def _init_db(self) -> None:
        """Create the audits table if it does not already exist."""

        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS audits (
                        audit_id TEXT PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL,
                        provider TEXT NOT NULL,
                        request_id TEXT NOT NULL,
                        session_id TEXT,
                        agent_id TEXT,
                        policy_version TEXT NOT NULL,
                        input_check_result TEXT NOT NULL,
                        output_check_result TEXT,
                        final_action TEXT NOT NULL,
                        latency_ms DOUBLE PRECISION NOT NULL,
                        called_provider BOOLEAN NOT NULL,
                        input_text TEXT,
                        output_text TEXT
                    )
                    """
                )
            )

    def save(
        self,
        audit_id: str,
        timestamp: str,
        provider: str,
        request_id: str,
        session_id: Optional[str],
        agent_id: Optional[str],
        policy_version: str,
        input_check_result: str,
        output_check_result: Optional[str],
        final_action: str,
        latency_ms: float,
        called_provider: int,
        input_text: str,
        output_text: Optional[str],
    ) -> None:
        """Save a single audit record to PostgreSQL."""

        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO audits (
                        audit_id,
                        timestamp,
                        provider,
                        request_id,
                        session_id,
                        agent_id,
                        policy_version,
                        input_check_result,
                        output_check_result,
                        final_action,
                        latency_ms,
                        called_provider,
                        input_text,
                        output_text
                    )
                    VALUES (
                        :audit_id,
                        :timestamp,
                        :provider,
                        :request_id,
                        :session_id,
                        :agent_id,
                        :policy_version,
                        :input_check_result,
                        :output_check_result,
                        :final_action,
                        :latency_ms,
                        :called_provider,
                        :input_text,
                        :output_text
                    )
                    """
                ),
                {
                    "audit_id": audit_id,
                    "timestamp": timestamp,
                    "provider": provider,
                    "request_id": request_id,
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "policy_version": policy_version,
                    "input_check_result": input_check_result,
                    "output_check_result": output_check_result,
                    "final_action": final_action,
                    "latency_ms": latency_ms,
                    "called_provider": bool(called_provider),
                    "input_text": input_text,
                    "output_text": output_text,
                },
            )

    def get_audits(
        self,
        provider: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query audit records from PostgreSQL."""

        query = """
            SELECT
                audit_id,
                timestamp,
                provider,
                request_id,
                session_id,
                agent_id,
                policy_version,
                input_check_result,
                output_check_result,
                final_action,
                latency_ms,
                called_provider,
                input_text,
                output_text
            FROM audits
            WHERE 1=1
        """

        params: Dict[str, Any] = {}

        if provider:
            query += " AND LOWER(provider) = LOWER(:provider)"
            params["provider"] = provider.strip()

        if agent_id:
            query += " AND agent_id = :agent_id"
            params["agent_id"] = agent_id

        if session_id:
            query += " AND session_id = :session_id"
            params["session_id"] = session_id

        query += " ORDER BY timestamp DESC"

        with self.engine.connect() as conn:
            result = conn.execute(text(query), params)

            return [dict(row._mapping) for row in result]

    def health_check(self) -> bool:
        """Return True when PostgreSQL is reachable."""

        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False