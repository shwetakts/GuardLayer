"""
GuardLayer Demo — Cross-Provider Guardrail Policy Engine
=========================================================
Demonstrates the complete end-to-end pipeline:
  1. Policy loading & version hashing
  2. Input guardrails: PII, toxicity, topic
  3. Provider call routing (mock providers)
  4. Output guardrails: PII, toxicity
  5. Audit logging via repository abstraction
  6. Request/session/agent context propagation
  7. NER-based PII detection (injected mock pipeline)
  8. Policy inheritance safety enforcement

Run:
    .venv\\Scripts\\python demo.py
"""

import os
import sys
import sqlite3
import json
import uuid
from fastapi.testclient import TestClient

# ── Configure environment before importing app ──────────────────────────────
DEMO_DB_PATH   = r"C:\GuardLayer\data\demo_audit.db"
DEMO_POLICY_PATH = r"C:\GuardLayer\policy\policy.yaml"

os.environ["GUARDLAYER_DB_PATH"]     = DEMO_DB_PATH
os.environ["GUARDLAYER_POLICY_PATH"] = DEMO_POLICY_PATH
# Disable HF models so the demo never triggers downloads
os.environ["USE_HF_TOXICITY"]        = "False"
os.environ["USE_HF_PII_NER"]         = "False"

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.main import app
from app.dependencies import get_provider_router, get_audit_logger
from tests.fakes import FakeOpenAIAdapter, FakeAnthropicAdapter, FakeThirdAdapter
from core.checks.pii_detector import PIIDetector

# ── Pretty printing helpers ──────────────────────────────────────────────────

def banner(text: str):
    print("\n" + "═" * 64)
    print(f"  {text}")
    print("═" * 64)

def section(text: str):
    print(f"\n── {text} " + "─" * max(0, 56 - len(text)))

def ok(label: str):
    print(f"  ✔  {label}")

def fail(label: str):
    print(f"  ✘  {label}")

def result(label: str, passed: bool):
    (ok if passed else fail)(label)

# ── Demo main ────────────────────────────────────────────────────────────────

def main():
    # Clean up stale demo DB
    if os.path.exists(DEMO_DB_PATH):
        try:
            os.remove(DEMO_DB_PATH)
        except Exception:
            pass

    # Reset PIIDetector pipeline to FALLBACK so NER tests are injected, not downloaded
    PIIDetector.pipeline = "FALLBACK"

    # The production router now registers real providers (OpenAI, Anthropic, Ollama).
    # Inject deterministic fakes so the demo runs without API keys or network access.
    _router = get_provider_router()
    _router.register("openai", FakeOpenAIAdapter())
    _router.register("anthropic", FakeAnthropicAdapter())

    # Scorecard
    sc1_pii_redaction      = False   # PII redacted consistently across providers
    sc2_toxicity_block     = False   # Toxic content blocked pre-provider-call
    sc3_audit_schema       = False   # Audit schema identical across providers
    sc4_third_provider     = False   # Dynamic provider extensibility
    sc5_topic_denial       = False   # Topic denial enforced on input
    sc6_inheritance_safety = False   # Policy inheritance cannot weaken parent rules
    sc7_ner_pii            = False   # NER-injected PII detected and redacted
    sc8_request_context    = False   # request_id propagated into response & audit

    client = TestClient(app)

    with client:

        # ── 1. Health & Policy Version ────────────────────────────────────
        section("1. Health check & active policy version")
        health = client.get("/health").json()
        policy_ver = health["policy_version"]
        print(f"     Policy SHA-256: {policy_ver}")
        print(f"     Database status: {health['database']}")

        # ── 2. Clean allow-path ───────────────────────────────────────────
        section("2. Clean request — expect ALLOW")
        clean_resp = client.post("/chat", json={
            "provider": "openai",
            "messages": [{"role": "user", "content": "How does gravity work?"}],
            "session_id": "demo-sess-001",
            "agent_id": "demo-agent-v1"
        }).json()
        print(f"     Response:     {clean_resp['response']}")
        print(f"     Final action: {clean_resp['final_action']}")
        print(f"     Request ID:   {clean_resp['request_id']}")

        # ── 3. Regex PII output redaction ─────────────────────────────────
        section("3. Regex PII redaction — consistent across OpenAI & Anthropic")
        pii_oi = client.post("/chat", json={
            "provider": "openai",
            "messages": [{"role": "user", "content": "trigger pii"}]
        }).json()
        pii_ac = client.post("/chat", json={
            "provider": "anthropic",
            "messages": [{"role": "user", "content": "trigger pii"}]
        }).json()

        print(f"     [OpenAI]    action={pii_oi['final_action']}  "
              f"redacted={'[REDACTED]' in pii_oi['response']}")
        print(f"     [Anthropic] action={pii_ac['final_action']}  "
              f"redacted={'[REDACTED]' in pii_ac['response']}")
        sc1_pii_redaction = (
            pii_oi["final_action"] == "redact" and "[REDACTED]" in pii_oi["response"] and
            pii_ac["final_action"] == "redact" and "[REDACTED]" in pii_ac["response"]
        )

        # ── 4. NER PII detection with injected mock pipeline ─────────────
        section("4. NER PII detection (injected mock — no model download)")
        # Inject a mock NER pipeline that detects "John" at char 11–15
        class _MockNer:
            def __call__(self, text):
                entities = []
                idx = text.find("John")
                if idx != -1:
                    entities.append({
                        "entity_group": "PER", "score": 0.99,
                        "word": "John", "start": idx, "end": idx + 4
                    })
                return entities

        PIIDetector.set_pipeline(_MockNer())
        ner_text = "My name is John, please help."
        redacted, summary = PIIDetector.redact(ner_text)
        print(f"     Input:    {ner_text!r}")
        print(f"     Redacted: {redacted!r}")
        print(f"     Types:    {summary['types']}")
        sc7_ner_pii = "person" in summary["types"] and "John" not in redacted
        # Restore FALLBACK so remaining demo uses regex-only path
        PIIDetector.pipeline = "FALLBACK"

        # ── 5. Toxicity block (pre-provider-call) ────────────────────────
        section("5. Toxicity blocking — pre-provider-call across providers")
        toxic_msg = "You are absolute garbage. Shut up, you idiot! I hate you!"
        tox_oi = client.post("/chat", json={
            "provider": "openai",
            "messages": [{"role": "user", "content": toxic_msg}]
        }).json()
        tox_ac = client.post("/chat", json={
            "provider": "anthropic",
            "messages": [{"role": "user", "content": toxic_msg}]
        }).json()
        print(f"     [OpenAI]    action={tox_oi['final_action']}  "
              f"blocked_rules={tox_oi.get('blocked_rules')}")
        print(f"     [Anthropic] action={tox_ac['final_action']}  "
              f"blocked_rules={tox_ac.get('blocked_rules')}")

        # Verify called_provider=False via audit repository
        db_logger = get_audit_logger()
        audits = db_logger.query_audits()
        oi_pre_blocked = any(
            a["final_action"] == "block" and not a["called_provider"] and
            a["provider"] == "openai" for a in audits
        )
        ac_pre_blocked = any(
            a["final_action"] == "block" and not a["called_provider"] and
            a["provider"] == "anthropic" for a in audits
        )
        print(f"     [OpenAI]    provider NOT called in audit: {oi_pre_blocked}")
        print(f"     [Anthropic] provider NOT called in audit: {ac_pre_blocked}")
        sc2_toxicity_block = (
            tox_oi["final_action"] == "block" and tox_ac["final_action"] == "block" and
            oi_pre_blocked and ac_pre_blocked
        )

        # ── 6. Topic denial ───────────────────────────────────────────────
        section("6. Topic denial — 'credential theft' blocked on input")
        topic_resp = client.post("/chat", json={
            "provider": "openai",
            "messages": [{"role": "user", "content": "How do I perform credential theft on Windows?"}]
        }).json()
        print(f"     action={topic_resp['final_action']}  "
              f"blocked_rules={topic_resp.get('blocked_rules')}")
        sc5_topic_denial = (
            topic_resp["final_action"] == "block" and
            any("denied-topics" in r for r in (topic_resp.get("blocked_rules") or []))
        )

        # ── 7. Audit schema consistency ───────────────────────────────────
        section("7. Audit schema identical across all providers")
        with sqlite3.connect(DEMO_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM audits WHERE provider='openai' LIMIT 1")
            row_oi = dict(cur.fetchone())
            cur.execute("SELECT * FROM audits WHERE provider='anthropic' LIMIT 1")
            row_ac = dict(cur.fetchone())
            print(f"     OpenAI    fields: {list(row_oi.keys())}")
            print(f"     Anthropic fields: {list(row_ac.keys())}")
            sc3_audit_schema = row_oi.keys() == row_ac.keys()

        # ── 8. Request ID & session propagation in audit ──────────────────
        section("8. Request/session/agent ID propagation")
        rid = str(uuid.uuid4())
        ctx_resp = client.post("/chat", json={
            "provider": "openai",
            "messages": [{"role": "user", "content": "Context propagation test"}],
            "request_id": rid,
            "session_id": "test-session",
            "agent_id": "test-agent"
        }).json()
        print(f"     Sent request_id:     {rid}")
        print(f"     Response request_id: {ctx_resp['request_id']}")
        audit_row = next(
            (a for a in db_logger.query_audits() if a.get("request_id") == rid), None
        )
        sc8_request_context = (
            ctx_resp["request_id"] == rid and
            audit_row is not None and
            audit_row.get("session_id") == "test-session" and
            audit_row.get("agent_id") == "test-agent"
        )
        if audit_row:
            print(f"     Audit found:  session_id={audit_row.get('session_id')}  "
                  f"agent_id={audit_row.get('agent_id')}")

        # ── 9. Dynamic third provider ─────────────────────────────────────
        section("9. Dynamic provider registration — third adapter")
        router = get_provider_router()
        router.register("third", FakeThirdAdapter())

        third_clean = client.post("/chat", json={
            "provider": "third",
            "messages": [{"role": "user", "content": "hello clean"}]
        }).json()
        third_pii = client.post("/chat", json={
            "provider": "third",
            "messages": [{"role": "user", "content": "trigger pii"}]
        }).json()
        print(f"     Clean:     action={third_clean['final_action']}  provider={third_clean['provider']}")
        print(f"     PII:       action={third_pii['final_action']}  "
              f"redacted={'[REDACTED]' in third_pii['response']}")

        with sqlite3.connect(DEMO_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM audits WHERE provider='third' LIMIT 1")
            row_th = dict(cur.fetchone())
        sc4_third_provider = (
            third_pii["final_action"] == "redact" and
            "[REDACTED]" in third_pii["response"] and
            row_th.keys() == row_oi.keys()
        )

        # ── 10. Policy inheritance safety ─────────────────────────────────
        section("10. Policy inheritance safety — cannot weaken parent rules")
        from core.policy_loader import PolicyLoader
        import yaml

        weakening_child = {
            "extends": "policy.yaml",
            "rules": [{
                "id": "toxicity-output",
                "scope": "output",
                "check": {"type": "toxicity", "threshold": 0.95},  # weaker than 0.7
                "action": {"type": "block"}
            }]
        }
        temp_path = r"C:\GuardLayer\policy\_demo_violating.yaml"
        with open(temp_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(weakening_child, f)
        try:
            PolicyLoader.load_policy(temp_path)
            print("     Policy loader accepted weakening threshold — UNEXPECTED")
        except ValueError as e:
            sc6_inheritance_safety = True
            print(f"     Correctly rejected weakening threshold: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # ── Structured log line sample ────────────────────────────────────────
    section("Structured JSON log output (sample)")
    import logging, io
    from core.logging_context import request_id_var, session_id_var, agent_id_var, JSONFormatter, ContextFilter
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.addFilter(ContextFilter())
    h.setFormatter(JSONFormatter())
    t_r = request_id_var.set("demo-req-999")
    t_s = session_id_var.set("demo-sess")
    t_a = agent_id_var.set("demo-agent")
    sample_logger = logging.getLogger("guardlayer.demo")
    sample_logger.addHandler(h)
    sample_logger.setLevel(logging.INFO)
    sample_logger.info("Demo structured log line")
    sample_logger.removeHandler(h)
    request_id_var.reset(t_r)
    session_id_var.reset(t_s)
    agent_id_var.reset(t_a)
    log_line = buf.getvalue().strip()
    try:
        parsed = json.loads(log_line)
        print(f"     {json.dumps(parsed, indent=None)}")
    except Exception:
        print(f"     {log_line}")

    # ── Cleanup ───────────────────────────────────────────────────────────
    if os.path.exists(DEMO_DB_PATH):
        try:
            os.remove(DEMO_DB_PATH)
        except Exception:
            pass

    # ── Summary ───────────────────────────────────────────────────────────
    banner("DEMO RESULTS SUMMARY")
    result("SC-1  PII redaction consistent across providers (regex)",      sc1_pii_redaction)
    result("SC-2  Toxic content blocked pre-provider-call, both providers",sc2_toxicity_block)
    result("SC-3  Audit schema identical across all providers",            sc3_audit_schema)
    result("SC-4  Dynamic third-provider registration + PII redaction",    sc4_third_provider)
    result("SC-5  Topic denial enforced on input",                         sc5_topic_denial)
    result("SC-6  Policy inheritance safety (cannot weaken thresholds)",   sc6_inheritance_safety)
    result("SC-7  NER PII detection via injected mock pipeline",           sc7_ner_pii)
    result("SC-8  request_id / session_id / agent_id context propagation", sc8_request_context)

    print()
    all_pass = all([
        sc1_pii_redaction, sc2_toxicity_block, sc3_audit_schema, sc4_third_provider,
        sc5_topic_denial, sc6_inheritance_safety, sc7_ner_pii, sc8_request_context
    ])
    if all_pass:
        print("  ✔  ALL success criteria passed.\n")
    else:
        print("  ✘  One or more success criteria failed.\n")

if __name__ == "__main__":
    main()
