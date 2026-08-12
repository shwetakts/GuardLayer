import os
import sys
import pytest
import yaml
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.policy_loader import PolicyLoader
from core.models import PolicyRule
from app.main import app

client = TestClient(app)

@pytest.fixture
def temp_nested_policies(tmp_path):
    """Creates temporary base and child policy files in nested format for testing."""
    base_content = {
        "version": "1.0",
        "metadata": {"name": "base-nested"},
        "rules": [
            {
                "id": "pii-input",
                "scope": "input",
                "check": {
                    "type": "pii",
                    "entities": ["email", "phone"]
                },
                "action": {
                    "type": "block"
                }
            },
            {
                "id": "toxicity-output",
                "scope": "output",
                "check": {
                    "type": "toxicity",
                    "threshold": 0.8
                },
                "action": {
                    "type": "block"
                }
            }
        ]
    }
    
    base_file = tmp_path / "base_nested_policy.yaml"
    with open(base_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(base_content, f)
        
    return base_file, tmp_path

def test_valid_nested_policy_load(temp_nested_policies):
    base_file, _ = temp_nested_policies
    policy = PolicyLoader.load_policy(str(base_file))
    
    assert policy.version == "1.0"
    assert len(policy.rules) == 2
    
    pii_rule = next(r for r in policy.rules if r.id == "pii-input")
    assert pii_rule.check.type == "pii"
    assert pii_rule.check.entities == ["email", "phone"]
    assert pii_rule.action.type == "block"
    
    tox_rule = next(r for r in policy.rules if r.id == "toxicity-output")
    assert tox_rule.check.type == "toxicity"
    assert tox_rule.check.threshold == 0.8
    assert tox_rule.action.type == "block"

def test_invalid_nested_policy_weakening_threshold(temp_nested_policies):
    base_file, tmp_path = temp_nested_policies
    
    # Child attempts to relax toxicity threshold from 0.8 to 0.9
    child_content = {
        "extends": "base_nested_policy.yaml",
        "rules": [
            {
                "id": "toxicity-output",
                "scope": "output",
                "check": {
                    "type": "toxicity",
                    "threshold": 0.9
                },
                "action": {
                    "type": "block"
                }
            }
        ]
    }
    
    child_file = tmp_path / "child_nested_policy.yaml"
    with open(child_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(child_content, f)
        
    with pytest.raises(ValueError) as excinfo:
        PolicyLoader.load_policy(str(child_file))
    assert "weakens threshold" in str(excinfo.value)

def test_invalid_nested_policy_weakening_action(temp_nested_policies):
    base_file, tmp_path = temp_nested_policies
    
    # Child attempts to change block to redact
    child_content = {
        "extends": "base_nested_policy.yaml",
        "rules": [
            {
                "id": "pii-input",
                "scope": "input",
                "check": {
                    "type": "pii",
                    "entities": ["email", "phone"]
                },
                "action": {
                    "type": "redact"
                }
            }
        ]
    }
    
    child_file = tmp_path / "child_nested_policy.yaml"
    with open(child_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(child_content, f)
        
    with pytest.raises(ValueError) as excinfo:
        PolicyLoader.load_policy(str(child_file))
    assert "weakens action" in str(excinfo.value)

def test_policy_validate_endpoint():
    # 1. Valid policy validation
    valid_payload = {
        "version": "1.0",
        "rules": [
            {
                "id": "tox-test",
                "scope": "output",
                "check": {
                    "type": "toxicity",
                    "threshold": 0.8
                },
                "action": {
                    "type": "block"
                }
            }
        ]
    }
    resp = client.post("/policy/validate", json=valid_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == []

    # 2. Invalid policy validation (malformed payload missing scope)
    invalid_payload = {
        "version": "1.0",
        "rules": [
            {
                "id": "tox-test",
                "check": {
                    "type": "toxicity"
                }
                # missing scope and action triggers ValidationError in Pydantic
            }
        ]
    }
    resp = client.post("/policy/validate", json=invalid_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0

def test_flat_backward_compatibility():
    # Flat format should be parsed correctly and converted to nested format automatically
    flat_rule_dict = {
        "id": "tox-rule",
        "check": "toxicity",
        "scope": "output",
        "action": "block",
        "threshold": 0.8
    }
    
    rule = PolicyRule(**flat_rule_dict)
    assert rule.check.type == "toxicity"
    assert rule.check.threshold == 0.8
    assert rule.action.type == "block"
    
    # Property compatibility
    assert rule.threshold == 0.8
