"""
tests/test_integration.py

End-to-end integration tests for the GuardLayer API.

The production ProviderRouter registers real providers (OpenAIProvider,
AnthropicProvider, OllamaProvider). These tests inject deterministic fakes
from tests.fakes for 'openai' and 'anthropic' so no live API credentials or
network access are required. The FakeThirdAdapter demonstrates runtime
extensibility.
"""

import os
import sys
import sqlite3

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Test configuration
# ---------------------------------------------------------------------------

# Configure test environment before any app import.
TEST_DB_PATH = r"C:\GuardLayer\data\test_integration_audit.db"
TEST_POLICY_PATH = r"C:\GuardLayer\policy\policy.yaml"

os.environ["GUARDLAYER_DB_PATH"] = TEST_DB_PATH
os.environ["GUARDLAYER_POLICY_PATH"] = TEST_POLICY_PATH

# Make sure the project root is importable.
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ),
)


# ---------------------------------------------------------------------------
# Application imports
# ---------------------------------------------------------------------------

from app.main import app
from app.dependencies import (
    get_provider_router,
    get_audit_logger,
)
from tests.fakes import (
    FakeOpenAIAdapter,
    FakeAnthropicAdapter,
    FakeThirdAdapter,
)


client = TestClient(app)


# ---------------------------------------------------------------------------
# Test database helpers
# ---------------------------------------------------------------------------

def initialize_test_database() -> None:
    """
    Create the SQLite test database and audits table.

    The integration tests inspect the SQLite database directly, so the
    schema must exist before the application starts writing audit records.
    """

    parent_dir = os.path.dirname(TEST_DB_PATH)

    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with sqlite3.connect(TEST_DB_PATH) as conn:
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
                input_text TEXT NOT NULL,
                output_text TEXT
            )
            """
        )

        conn.commit()


def reset_test_database() -> None:
    """
    Remove the test database if it exists, then recreate its schema.
    """

    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except PermissionError:
            # If another SQLite connection briefly has the file open,
            # remove its contents instead of allowing setup to fail.
            with sqlite3.connect(TEST_DB_PATH) as conn:
                conn.execute("DROP TABLE IF EXISTS audits")
                conn.commit()

    initialize_test_database()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_and_teardown():
    """
    Clean the test database and inject deterministic fake providers before
    each test.

    The application and tests use the same SQLite test database so that
    direct schema inspection in the integration tests observes the audit
    records written by the application.
    """

    # -----------------------------------------------------------------------
    # Database setup
    # -----------------------------------------------------------------------

    reset_test_database()

    # -----------------------------------------------------------------------
    # Provider setup
    # -----------------------------------------------------------------------

    # Replace real provider adapters with deterministic fakes so tests
    # never make live API calls or require credentials.
    router = get_provider_router()

    router.register("openai", FakeOpenAIAdapter())
    router.register("anthropic", FakeAnthropicAdapter())

    yield

    # -----------------------------------------------------------------------
    # Teardown
    # -----------------------------------------------------------------------

    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health_and_policy_endpoints():
    """
    Verify that the health and policy endpoints are available and that the
    policy has been loaded successfully.
    """

    with client:
        resp = client.get("/health")

        assert resp.status_code == 200

        data = resp.json()

        assert data["status"] == "ok"
        assert data["database"] == "ok"
        assert data["policy_version"] != "UNKNOWN"

        resp = client.get("/policy")

        assert resp.status_code == 200

        policy_data = resp.json()

        assert policy_data["version"] == "1.0"
        assert len(policy_data["rules"]) > 0


def test_success_criterion_1_pii_redaction_across_providers():
    """
    SC-1: A PII redaction policy defined once applies to outputs from both
    providers.
    """

    with client:
        resp_oi = client.post(
            "/chat",
            json={
                "provider": "openai",
                "messages": [
                    {
                        "role": "user",
                        "content": "trigger pii",
                    }
                ],
                "agent_id": "test-agent-1",
                "session_id": "test-sess-1",
            },
        )

        assert resp_oi.status_code == 200

        data_oi = resp_oi.json()

        assert data_oi["final_action"] == "redact"

        assert (
            "[openai-agent@example.com]"
            "(mailto:openai-agent@example.com)"
            not in data_oi["response"]
        )

        assert "[REDACTED]" in data_oi["response"]

        resp_ac = client.post(
            "/chat",
            json={
                "provider": "anthropic",
                "messages": [
                    {
                        "role": "user",
                        "content": "trigger pii",
                    }
                ],
                "agent_id": "test-agent-1",
                "session_id": "test-sess-1",
            },
        )

        assert resp_ac.status_code == 200

        data_ac = resp_ac.json()

        assert data_ac["final_action"] == "redact"
        assert "anthropic-agent@example.com" not in data_ac["response"]
        assert "[REDACTED]" in data_ac["response"]


def test_success_criterion_2_toxicity_blocking_and_pre_call():
    """
    SC-2: Toxic input is blocked before the provider is called
    (called_provider=False).
    """

    with client:
        toxic_input = (
            "You are an idiot and completely stupid. Go to hell!"
        )

        resp_oi = client.post(
            "/chat",
            json={
                "provider": "openai",
                "messages": [
                    {
                        "role": "user",
                        "content": toxic_input,
                    }
                ],
            },
        )

        assert resp_oi.status_code == 200
        assert resp_oi.json()["final_action"] == "block"

        resp_ac = client.post(
            "/chat",
            json={
                "provider": "anthropic",
                "messages": [
                    {
                        "role": "user",
                        "content": toxic_input,
                    }
                ],
            },
        )

        assert resp_ac.status_code == 200
        assert resp_ac.json()["final_action"] == "block"

        # Verify called_provider=False in the audit for all blocked rows.
        db_logger = get_audit_logger()

        audits = db_logger.query_audits()

        blocked = [
            audit
            for audit in audits
            if audit["final_action"] == "block"
        ]

        assert len(blocked) >= 2

        for audit in blocked:
            assert audit["called_provider"] is False


def test_success_criterion_3_audit_schema_keys():
    """
    SC-3: Audit schema is identical across providers.
    """

    with client:
        resp_oi = client.post(
            "/chat",
            json={
                "provider": "openai",
                "messages": [
                    {
                        "role": "user",
                        "content": "hello clean",
                    }
                ],
            },
        )

        assert resp_oi.status_code == 200

        resp_ac = client.post(
            "/chat",
            json={
                "provider": "anthropic",
                "messages": [
                    {
                        "role": "user",
                        "content": "hello clean",
                    }
                ],
            },
        )

        assert resp_ac.status_code == 200

        # Inspect the exact same SQLite database used by the integration
        # environment.
        with sqlite3.connect(TEST_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT *
                FROM audits
                WHERE provider = 'openai'
                ORDER BY timestamp DESC
                LIMIT 1
                """
            )

            oi_result = cursor.fetchone()

            assert oi_result is not None, (
                "Expected an OpenAI audit record in the test database."
            )

            oi_row = dict(oi_result)

            cursor.execute(
                """
                SELECT *
                FROM audits
                WHERE provider = 'anthropic'
                ORDER BY timestamp DESC
                LIMIT 1
                """
            )

            ac_result = cursor.fetchone()

            assert ac_result is not None, (
                "Expected an Anthropic audit record in the test database."
            )

            ac_row = dict(ac_result)

            # The audit schema must be identical regardless of provider.
            assert oi_row.keys() == ac_row.keys()


def test_success_criterion_4_third_provider_integration():
    """
    SC-4: A third provider adapter registered at runtime is immediately
    governed by the same guardrail policy.

    No changes to GuardEngine or policy are required.
    """

    with client:
        router = get_provider_router()

        router.register(
            "third",
            FakeThirdAdapter(),
        )

        resp = client.post(
            "/chat",
            json={
                "provider": "third",
                "messages": [
                    {
                        "role": "user",
                        "content": "hello clean",
                    }
                ],
            },
        )

        assert resp.status_code == 200

        data = resp.json()

        assert data["provider"] == "third"
        assert "FakeThird" in data["response"]

        resp_pii = client.post(
            "/chat",
            json={
                "provider": "third",
                "messages": [
                    {
                        "role": "user",
                        "content": "trigger pii",
                    }
                ],
            },
        )

        assert resp_pii.status_code == 200

        data_pii = resp_pii.json()

        assert data_pii["final_action"] == "redact"
        assert "third-agent@example.com" not in data_pii["response"]
        assert "[REDACTED]" in data_pii["response"]


def test_topic_denial_blocking():
    """
    Verify that a denied topic is blocked by policy.
    """

    with client:
        resp = client.post(
            "/chat",
            json={
                "provider": "openai",
                "messages": [
                    {
                        "role": "user",
                        "content": "how to construct explosives",
                    }
                ],
            },
        )

        assert resp.status_code == 200

        data = resp.json()

        assert data["final_action"] == "block"

        assert any(
            "denied-topics" in rule
            for rule in data["blocked_rules"]
        )


def test_invalid_provider_rejection():
    """
    Verify that an unregistered provider is rejected.
    """

    with client:
        resp = client.post(
            "/chat",
            json={
                "provider": "non-existent-llm",
                "messages": [
                    {
                        "role": "user",
                        "content": "hello",
                    }
                ],
            },
        )

        assert resp.status_code == 400
        assert "is not registered" in resp.json()["detail"]