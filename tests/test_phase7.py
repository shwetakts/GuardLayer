"""
Phase 7: Structured logging context tests.

Verifies:
- request_id_var, session_id_var, agent_id_var propagate into log records
- ContextFilter injects values onto LogRecord
- JSONFormatter produces valid JSON with expected fields
- Context vars reset cleanly between requests (no cross-request leakage)
- setup_logging installs the JSON handler without duplicate handlers
"""

import json
import logging
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.logging_context import (
    setup_logging,
    ContextFilter,
    JSONFormatter,
    request_id_var,
    session_id_var,
    agent_id_var,
)


def test_context_filter_injects_defaults():
    """ContextFilter adds N/A defaults when no context vars are set."""
    f = ContextFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)

    # Clear context vars to defaults
    token_r = request_id_var.set("N/A")
    token_s = session_id_var.set("N/A")
    token_a = agent_id_var.set("N/A")
    try:
        f.filter(record)
        assert record.request_id == "N/A"
        assert record.session_id == "N/A"
        assert record.agent_id == "N/A"
    finally:
        request_id_var.reset(token_r)
        session_id_var.reset(token_s)
        agent_id_var.reset(token_a)


def test_context_filter_injects_set_values():
    """ContextFilter picks up non-default context var values."""
    f = ContextFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)

    token_r = request_id_var.set("req-abc")
    token_s = session_id_var.set("sess-xyz")
    token_a = agent_id_var.set("agent-001")
    try:
        f.filter(record)
        assert record.request_id == "req-abc"
        assert record.session_id == "sess-xyz"
        assert record.agent_id == "agent-001"
    finally:
        request_id_var.reset(token_r)
        session_id_var.reset(token_s)
        agent_id_var.reset(token_a)


def test_json_formatter_produces_valid_json():
    """JSONFormatter output is parseable JSON with required keys."""
    f = ContextFilter()
    fmt = JSONFormatter()

    record = logging.LogRecord("mylogger", logging.WARNING, "", 0, "test message", (), None)
    token_r = request_id_var.set("req-999")
    token_s = session_id_var.set("N/A")
    token_a = agent_id_var.set("N/A")
    try:
        f.filter(record)
        output = fmt.format(record)
        data = json.loads(output)

        assert data["level"] == "WARNING"
        assert data["message"] == "test message"
        assert data["logger"] == "mylogger"
        assert data["request_id"] == "req-999"
        assert "timestamp" in data
    finally:
        request_id_var.reset(token_r)
        session_id_var.reset(token_s)
        agent_id_var.reset(token_a)


def test_context_vars_do_not_leak_between_requests():
    """Context vars set and reset in one scope do not affect another."""
    token_r = request_id_var.set("req-first")
    request_id_var.reset(token_r)

    # After reset, default value is restored
    assert request_id_var.get() == "N/A"


def test_setup_logging_installs_one_handler():
    """setup_logging does not add duplicate handlers on repeated calls."""
    root = logging.getLogger()
    initial_count = len(root.handlers)

    setup_logging("DEBUG")
    after_first = len(root.handlers)

    setup_logging("INFO")
    after_second = len(root.handlers)

    # Should have exactly one handler after each call (removes existing first)
    assert after_first == 1
    assert after_second == 1


def test_setup_logging_respects_log_level():
    """setup_logging sets the root logger to the specified level."""
    setup_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING

    setup_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG

    # Restore to INFO for other tests
    setup_logging("INFO")
