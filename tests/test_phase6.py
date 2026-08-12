import pytest

from app.config import settings
from storage.postgres_repository import PostgresAuditRepository
from storage.audit_logger import AuditLogger


@pytest.fixture
def repo():
    """Use the configured PostgreSQL database for repository tests."""
    repository = PostgresAuditRepository(settings.DATABASE_URL)
    return repository


def test_repository_initialization(repo):
    """PostgreSQL repository initializes and connects successfully."""
    assert repo.health_check() is True


def test_repository_save_and_retrieve(repo):
    """Save and retrieve an audit record from PostgreSQL."""
    import uuid
    unique_id = f"phase6-repo-test-{uuid.uuid4()}"
    
    repo.save(
        audit_id=unique_id,
        timestamp="2026-08-12T12:00:00Z",
        provider="openai",
        request_id="phase6-request-test",
        session_id="phase6-session-test",
        agent_id="phase6-agent-test",
        policy_version="hash-test",
        input_check_result='{"allowed": true}',
        output_check_result=None,
        final_action="allow",
        latency_ms=12.5,
        called_provider=1,
        input_text="hello",
        output_text="hi",
    )

    records = repo.get_audits(provider="openai")

    matching = [
        record
        for record in records
        if record["audit_id"] == unique_id
    ]

    assert len(matching) == 1

    record = matching[0]

    assert record["audit_id"] == unique_id
    assert record["final_action"] == "allow"
    assert record["called_provider"] is True
    assert record["input_text"] == "hello"


def test_audit_logger_repository_integration(repo):
    """AuditLogger correctly persists sanitized records to PostgreSQL."""
    logger = AuditLogger(repository=repo)

    audit_id = logger.log(
        provider="anthropic",
        policy_version="v1.0",
        input_check_result={"allowed": True, "findings": []},
        output_check_result=None,
        final_action="allow",
        latency_ms=45.0,
        called_provider=True,
        input_text="My email is test@example.com",
        output_text="Hello user",
        session_id="phase6-session-logger",
        request_id="phase6-logger-request",
    )

    records = logger.query_audits(provider="anthropic")

    matching = [
        record
        for record in records
        if record["audit_id"] == audit_id
    ]

    assert len(matching) == 1

    record = matching[0]

    assert record["provider"] == "anthropic"

    # Input text must be redacted before persistence.
    assert "test@example.com" not in record["input_text"]
    assert "[REDACTED]" in record["input_text"]

    assert record["called_provider"] is True
    assert record["input_check_result"] == {
        "allowed": True,
        "findings": [],
    }