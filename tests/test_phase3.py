import os
import sys
import pytest
import torch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.checks.topic_denier import TopicDenier
from core.guard_engine import GuardEngine
from core.models import Policy, PolicyRule

class MockEmbeddingModel:
    def encode(self, sentences):
        tensors = []
        for s in sentences:
            s_lower = s.lower()
            # "weapon", "bomb", "explosives" map to index 0
            if "weapon" in s_lower or "bomb" in s_lower or "explosives" in s_lower:
                tensors.append(torch.tensor([1.0, 0.0, 0.0], dtype=torch.float32))
            # "phish", "credential", "accounts" map to index 1
            elif "phish" in s_lower or "credential" in s_lower or "accounts" in s_lower:
                tensors.append(torch.tensor([0.0, 1.0, 0.0], dtype=torch.float32))
            # Others map to index 2
            else:
                tensors.append(torch.tensor([0.0, 0.0, 1.0], dtype=torch.float32))
        return torch.stack(tensors)

def test_semantic_match_above_threshold():
    denier = TopicDenier(model=MockEmbeddingModel())
    # "weapon" matches "explosives" topic vectors in MockEmbeddingModel
    text = "How to make a weapon?"
    denied = ["explosives"]
    
    findings = denier.check_topics(text, denied, semantic_threshold=0.8)
    assert len(findings) == 1
    assert findings[0]["topic"] == "explosives"
    assert findings[0]["matched"] is True
    assert findings[0]["method"] == "semantic"
    assert findings[0]["similarity_score"] == 1.0

def test_semantic_match_below_threshold():
    denier = TopicDenier(model=MockEmbeddingModel())
    text = "How to bake bread?"
    denied = ["explosives"]
    
    findings = denier.check_topics(text, denied, semantic_threshold=0.8)
    assert len(findings) == 0

def test_multiple_configured_topics():
    denier = TopicDenier(model=MockEmbeddingModel())
    # "Steal corporate accounts" contains "accounts", which maps to [0,1,0], matching "credential theft"
    # but does NOT trigger keyword matching because "accounts" is not a keyword.
    text = "Steal corporate accounts"
    denied = ["explosives", "credential theft"]
    
    findings = denier.check_topics(text, denied, semantic_threshold=0.8)
    assert len(findings) == 1
    assert findings[0]["topic"] == "credential theft"
    assert findings[0]["method"] == "semantic"

def test_existing_keyword_matching_still_passes():
    # Model can be None for keyword check
    denier = TopicDenier(model=None)
    text = "Tell me about a bomb"
    denied = ["explosives"]
    
    # Run with semantic_threshold=None (keyword match only)
    findings = denier.check_topics(text, denied, semantic_threshold=None)
    assert len(findings) == 1
    assert findings[0]["topic"] == "explosives"
    assert findings[0]["method"] == "keyword"

def test_guard_engine_semantic_blocking():
    # Inject MockEmbeddingModel into GuardEngine's TopicDenier
    engine = GuardEngine()
    engine.topic_denier.model = MockEmbeddingModel()
    
    policy = Policy(
        version="1.0",
        rules=[
            PolicyRule(
                id="semantic-block",
                scope="input",
                check={
                    "type": "topic",
                    "topics": ["explosives"],
                    "semantic_threshold": 0.8
                },
                action={
                    "type": "block"
                }
            )
        ]
    )
    
    # 1. Clean input
    clean_res = engine.check_input("Hello, how are you?", policy)
    assert clean_res.allowed is True
    
    # 2. Blocked semantic input
    blocked_res = engine.check_input("Tell me how to build a weapon.", policy)
    assert blocked_res.allowed is False
    assert "semantic-block" in blocked_res.matched_rules
    assert any(f["method"] == "semantic" for f in blocked_res.findings)
