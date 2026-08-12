import sys
import os
import pytest
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.policy_loader import PolicyLoader
from core.models import Policy, PolicyRule

@pytest.fixture
def temp_policies(tmp_path):
    """Creates temporary base and child policy files for testing."""
    base_content = {
        "version": "1.0",
        "metadata": {"name": "base-test"},
        "rules": [
            {"id": "pii-rule", "check": "pii", "scope": "input", "action": "block"},
            {"id": "tox-rule", "check": "toxicity", "scope": "output", "action": "block", "threshold": 0.8},
            {"id": "topic-rule", "check": "topic", "scope": "input", "action": "block", "topics": ["malware", "bombs"]}
        ]
    }
    
    base_file = tmp_path / "base_policy.yaml"
    with open(base_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(base_content, f)
        
    return base_file, tmp_path

def test_valid_policy_load(temp_policies):
    base_file, _ = temp_policies
    policy = PolicyLoader.load_policy(str(base_file))
    assert policy.version == "1.0"
    assert len(policy.rules) == 3
    
    h = PolicyLoader.get_policy_hash(policy)
    assert len(h) == 64  # SHA-256 length

def test_policy_inheritance_extends(temp_policies):
    base_file, tmp_path = temp_policies
    
    # Child adds a rule, and strengthens the toxicity threshold (0.8 -> 0.7)
    child_content = {
        "extends": "base_policy.yaml",
        "metadata": {"name": "child-test"},
        "rules": [
            {"id": "tox-rule", "check": "toxicity", "scope": "output", "action": "block", "threshold": 0.7},
            {"id": "new-rule", "check": "pii", "scope": "output", "action": "redact"},
            {"id": "topic-rule", "check": "topic", "scope": "input", "action": "block", "topics": ["malware", "bombs", "phishing"]} # adds phishing
        ]
    }
    
    child_file = tmp_path / "child_policy.yaml"
    with open(child_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(child_content, f)
        
    policy = PolicyLoader.load_policy(str(child_file))
    assert len(policy.rules) == 4
    
    # Find rules
    tox = next(r for r in policy.rules if r.id == "tox-rule")
    assert tox.threshold == 0.7  # overridden and valid
    
    topic = next(r for r in policy.rules if r.id == "topic-rule")
    assert set(topic.topics) == {"malware", "bombs", "phishing"}

def test_inheritance_weakens_action(temp_policies):
    base_file, tmp_path = temp_policies
    # Attempt to change block to redact
    child_content = {
        "extends": "base_policy.yaml",
        "rules": [
            {"id": "pii-rule", "check": "pii", "scope": "input", "action": "redact"}
        ]
    }
    child_file = tmp_path / "child_policy.yaml"
    with open(child_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(child_content, f)
        
    with pytest.raises(ValueError) as excinfo:
        PolicyLoader.load_policy(str(child_file))
    assert "weakens action" in str(excinfo.value)

def test_inheritance_weakens_threshold(temp_policies):
    base_file, tmp_path = temp_policies
    # Attempt to change toxicity threshold from 0.8 to 0.9 (making it less strict)
    child_content = {
        "extends": "base_policy.yaml",
        "rules": [
            {"id": "tox-rule", "check": "toxicity", "scope": "output", "action": "block", "threshold": 0.9}
        ]
    }
    child_file = tmp_path / "child_policy.yaml"
    with open(child_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(child_content, f)
        
    with pytest.raises(ValueError) as excinfo:
        PolicyLoader.load_policy(str(child_file))
    assert "weakens threshold" in str(excinfo.value)

def test_inheritance_removes_topic(temp_policies):
    base_file, tmp_path = temp_policies
    # Attempt to remove "bombs" from topic list
    child_content = {
        "extends": "base_policy.yaml",
        "rules": [
            {"id": "topic-rule", "check": "topic", "scope": "input", "action": "block", "topics": ["malware"]}
        ]
    }
    child_file = tmp_path / "child_policy.yaml"
    with open(child_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(child_content, f)
        
    with pytest.raises(ValueError) as excinfo:
        PolicyLoader.load_policy(str(child_file))
    assert "removes base denied topics" in str(excinfo.value)
