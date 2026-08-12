import sys
import os
import sqlite3
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.audit_logger import AuditLogger

def test_audit_logging_and_redaction(tmp_path):
    db_file = tmp_path / "test_audit.db"
    logger = AuditLogger(db_path=str(db_file))
    
    # Inputs containing PII
    input_text = "Reach out to user1@domain.com or call 555-555-5555."
    output_text = "Confirmed credit card 4111 1111 1111 1111 is linked."
    
    input_findings = {"findings": [{"type": "email", "action": "redact"}]}
    output_findings = {"findings": [{"type": "credit_card", "action": "redact"}]}
    
    audit_id = logger.log(
        provider="openai",
        policy_version="sha256-dummy-hash-value-12345",
        input_check_result=input_findings,
        output_check_result=output_findings,
        final_action="redact",
        latency_ms=120.5,
        called_provider=True,
        input_text=input_text,
        output_text=output_text,
        session_id="session-456",
        agent_id="agent-789"
    )
    
    # Retrieve audit
    records = logger.query_audits(provider="openai")
    assert len(records) == 1
    record = records[0]
    
    # Check fields
    assert record["audit_id"] == audit_id
    assert record["provider"] == "openai"
    assert record["policy_version"] == "sha256-dummy-hash-value-12345"
    assert record["final_action"] == "redact"
    assert record["latency_ms"] == 120.5
    assert record["called_provider"] is True
    
    # Verify JSON structure parsing
    assert record["input_check_result"] == input_findings
    assert record["output_check_result"] == output_findings
    
    # CRITICAL: Verify raw PII values are redacted in text columns!
    assert "user1@domain.com" not in record["input_text"]
    assert "555-555-5555" not in record["input_text"]
    assert "[REDACTED]" in record["input_text"]
    
    assert "4111 1111 1111 1111" not in record["output_text"]
    assert "[REDACTED]" in record["output_text"]

def test_audit_schema_keys(tmp_path):
    db_file = tmp_path / "test_audit.db"
    logger = AuditLogger(db_path=str(db_file))
    
    # Insert from openai
    logger.log(
        provider="openai",
        policy_version="h1",
        input_check_result={},
        output_check_result={},
        final_action="allow",
        latency_ms=50.0,
        called_provider=True,
        input_text="clean"
    )
    # Insert from anthropic
    logger.log(
        provider="anthropic",
        policy_version="h1",
        input_check_result={},
        output_check_result={},
        final_action="allow",
        latency_ms=60.0,
        called_provider=True,
        input_text="clean"
    )
    
    # Read rows using direct sqlite query to compare schemas
    with sqlite3.connect(str(db_file)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM audits WHERE provider = 'openai'")
        openai_row = dict(cursor.fetchone())
        
        cursor.execute("SELECT * FROM audits WHERE provider = 'anthropic'")
        anthropic_row = dict(cursor.fetchone())
        
        # Verify schema keys are identical
        assert openai_row.keys() == anthropic_row.keys()
        
        # Verify mandatory keys exist
        required_fields = {
            "audit_id", "timestamp", "provider", "request_id", "session_id", "agent_id",
            "policy_version", "input_check_result", "output_check_result", "final_action", "latency_ms"
        }
        for field in required_fields:
            assert field in openai_row
