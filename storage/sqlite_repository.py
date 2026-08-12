import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional


from storage.base import AuditRepository


class SQLiteAuditRepository(AuditRepository):
    """
    SQLite-backed audit repository.

    This repository is primarily intended for integration tests and
    local development. It uses the same logical audit schema as the
    PostgreSQL repository so audit records are provider-independent.
    """

    def __init__(self, database_path: str):
        """
        Initialize the SQLite repository and ensure the schema exists.
        """

        if not database_path:
            raise ValueError("database_path must be provided")

        self.database_path = str(Path(database_path))

        # Make sure the parent directory exists when one is specified.
        parent = Path(self.database_path).parent

        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """
        Open a connection to the configured SQLite database.
        """

        connection = sqlite3.connect(
            self.database_path
        )

        connection.row_factory = sqlite3.Row

        return connection

    def _init_db(self) -> None:
        """
        Create the audits table if it does not already exist.

        The column names and order intentionally match the PostgreSQL
        audit schema.
        """

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audits (
                    audit_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    session_id TEXT,
                    agent_id TEXT,
                    policy_version TEXT NOT NULL,
                    input_check_result TEXT NOT NULL,
                    output_check_result TEXT,
                    final_action TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    called_provider INTEGER NOT NULL,
                    input_text TEXT,
                    output_text TEXT
                )
                """
            )

            conn.commit()

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
        """
        Save a single audit record to SQLite.
        """

        with self._connect() as conn:
            conn.execute(
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
                """,
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
                    "called_provider": 1 if called_provider else 0,
                    "input_text": input_text,
                    "output_text": output_text,
                },
            )

            conn.commit()

    def get_audits(
        self,
        provider: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query audit records from SQLite.
        """

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

        with self._connect() as conn:
            cursor = conn.execute(
                query,
                params,
            )

            rows = cursor.fetchall()

            return [
                dict(row)
                for row in rows
            ]

    def health_check(self) -> bool:
        """
        Return True when the SQLite database is reachable.
        """

        try:
            with self._connect() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False