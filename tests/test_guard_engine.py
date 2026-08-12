import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.guard_engine import GuardEngine
from core.models import Policy, PolicyRule

def test_guard_engine_allow():
    engine = GuardEngine()
    policy = Policy(
        version="1.0",
        rules=[
            PolicyRule(id="pii-in", check="pii", scope="input", action="block"),
            PolicyRule(id="tox-in", check="toxicity", scope="input", action="block", threshold=0.8)
        ]
    )
    
    text = "Hello, I am writing a normal message here."
    res = engine.check_input(text, policy)
    assert res.allowed is True
    assert res.action == "allow"
    assert res.text == text
    assert len(res.findings) == 0

def test_guard_engine_block_input_pii():
    engine = GuardEngine()
    policy = Policy(
        version="1.0",
        rules=[
            PolicyRule(id="pii-in", check="pii", scope="input", action="block")
        ]
    )
    
    text = "Please reach out to email test@example.com."
    res = engine.check_input(text, policy)
    assert res.allowed is False
    assert res.action == "block"
    assert "pii-in" in res.matched_rules
    assert len(res.findings) == 1
    assert res.findings[0]["type"] == "email"

def test_guard_engine_redact_output_pii():
    engine = GuardEngine()
    policy = Policy(
        version="1.0",
        rules=[
            PolicyRule(id="pii-out", check="pii", scope="output", action="redact")
        ]
    )
    
    text = "My email is support@gmail.com and phone is 555-123-4567."
    res = engine.check_output(text, policy)
    assert res.allowed is True
    assert res.action == "redact"
    assert "pii-out" in res.matched_rules
    assert len(res.findings) == 2
    assert res.text == "My email is [REDACTED] and phone is [REDACTED]."

def test_guard_engine_block_toxicity():
    engine = GuardEngine()
    policy = Policy(
        version="1.0",
        rules=[
            PolicyRule(id="tox-out", check="toxicity", scope="output", action="block", threshold=0.6)
        ]
    )
    
    # Text that trains to be toxic
    text = "You are absolute garbage. Shut up, you idiot!"
    res = engine.check_output(text, policy)
    assert res.allowed is False
    assert res.action == "block"
    assert "tox-out" in res.matched_rules
    assert len(res.findings) == 1
    assert res.findings[0]["check"] == "toxicity"
    assert res.findings[0]["score"] >= 0.6
