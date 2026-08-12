from typing import Protocol, List, Dict, Any, Optional


class AuditRepository(Protocol):
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
        Saves a single audit log record.
        """
        ...

    def get_audits(
        self,
        provider: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Queries audit log records matching the specified filters.
        """
        ...