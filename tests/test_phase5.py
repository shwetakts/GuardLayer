import os
import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.checks.pii_detector import PIIDetector
from core.guard_engine import GuardEngine
from core.models import Policy, PolicyRule
from app.config import settings

class MockNerPipeline:
    def __init__(self, entities):
        self.entities = entities
        self.call_count = 0

    def __call__(self, text, *args, **kwargs):
        self.call_count += 1
        return self.entities

@pytest.fixture(autouse=True)
def reset_pii_detector_pipeline():
    """Reset PII detector state and NER settings between tests."""
    original_pipeline = PIIDetector.pipeline
    original_use_hf = settings.USE_HF_PII_NER

    # Each test starts with a clean detector and NER enabled.
    PIIDetector.pipeline = None
    settings.USE_HF_PII_NER = True

    yield

    # Restore global state after the test.
    PIIDetector.pipeline = original_pipeline
    settings.USE_HF_PII_NER = original_use_hf

def test_person_ner_detection():
    # Mocking person detection "John Doe" at character offsets 5 to 13
    mock_entities = [{"entity_group": "PER", "score": 0.99, "word": "John Doe", "start": 5, "end": 13}]
    mock_pipe = MockNerPipeline(mock_entities)
    PIIDetector.set_pipeline(mock_pipe)

    res = PIIDetector.detect("I am John Doe.")
    assert res["detected"] is True
    assert "person" in res["types"]
    assert len(res["findings"]) == 1
    assert res["findings"][0]["type"] == "person"
    assert res["findings"][0]["start"] == 5
    assert res["findings"][0]["end"] == 13

def test_org_ner_detection():
    # Mocking org detection "Google" at offsets 9 to 15
    mock_entities = [{"entity_group": "ORG", "score": 0.98, "word": "Google", "start": 9, "end": 15}]
    mock_pipe = MockNerPipeline(mock_entities)
    PIIDetector.set_pipeline(mock_pipe)

    res = PIIDetector.detect("I work at Google.")
    assert res["detected"] is True
    assert "org" in res["types"]
    assert res["findings"][0]["type"] == "org"

def test_location_ner_detection():
    # Mocking location detection "London" at offsets 10 to 16
    mock_entities = [{"entity_group": "LOC", "score": 0.97, "word": "London", "start": 10, "end": 16}]
    mock_pipe = MockNerPipeline(mock_entities)
    PIIDetector.set_pipeline(mock_pipe)

    res = PIIDetector.detect("I live in London.")
    assert res["detected"] is True
    assert "location" in res["types"]
    assert res["findings"][0]["type"] == "location"

def test_regex_pii_detection():
    # Verify regexes are still fully functional without any pipeline calls
    PIIDetector.pipeline = "FALLBACK"
    
    # 1. Email
    res = PIIDetector.detect("My email is test@example.com.")
    assert res["detected"] is True
    assert "email" in res["types"]

    # 2. Phone
    res = PIIDetector.detect("My phone is 800-555-0199.")
    assert res["detected"] is True
    assert "phone" in res["types"]

    # 3. Credit Card with Luhn validation (Valid card)
    valid_card = "4007 0000 0002 7"  # passes Luhn validation
    res = PIIDetector.detect(f"My card is {valid_card}.")
    assert res["detected"] is True
    assert "credit_card" in res["types"]

    # 4. Credit Card invalid Luhn checksum
    invalid_card = "4007 0000 0002 8"  # fails Luhn validation
    res = PIIDetector.detect(f"My card is {invalid_card}.")
    assert res["detected"] is False

def test_mixed_regex_ner_detection():
    # Mocking person while scanning text containing an email
    mock_entities = [{"entity_group": "PER", "score": 0.99, "word": "John", "start": 10, "end": 14}]
    mock_pipe = MockNerPipeline(mock_entities)
    PIIDetector.set_pipeline(mock_pipe)

    text = "Contact is John, test@example.com."
    res = PIIDetector.detect(text)
    
    # Should detect both 'person' (NER) and 'email' (regex)
    assert res["detected"] is True
    assert set(res["types"]) == {"person", "email"}
    assert len(res["findings"]) == 2

def test_redaction_behavior():
    mock_entities = [{"entity_group": "PER", "score": 0.99, "word": "John", "start": 11, "end": 15}]
    mock_pipe = MockNerPipeline(mock_entities)
    PIIDetector.set_pipeline(mock_pipe)

    text = "My name is John and email is test@example.com."
    redacted, summary = PIIDetector.redact(text)
    
    # Both names and emails must be redacted
    assert "John" not in redacted
    assert "test@example.com" not in redacted
    assert redacted == "My name is [REDACTED] and email is [REDACTED]."

def test_ner_disabled_fallback():
    mock_entities = [{"entity_group": "PER", "score": 0.99, "word": "John", "start": 5, "end": 9}]
    mock_pipe = MockNerPipeline(mock_entities)
    PIIDetector.set_pipeline(mock_pipe)

    original_use_hf = settings.USE_HF_PII_NER
    try:
        settings.USE_HF_PII_NER = False
        text = "I am John, email is test@example.com."
        res = PIIDetector.detect(text)
        
        # When disabled, mock pipeline should not be called and only email detected
        assert mock_pipe.call_count == 0
        assert "person" not in res["types"]
        assert "email" in res["types"]
        assert PIIDetector.pipeline == "FALLBACK"
    finally:
        settings.USE_HF_PII_NER = original_use_hf

def test_ner_inference_failure_fallback():
    # Mock pipeline that raises an exception during execution
    def mock_fail_call(text):
        raise RuntimeError("Inference failed")
        
    PIIDetector.set_pipeline(mock_fail_call)

    text = "I am John, email is test@example.com."
    res = PIIDetector.detect(text)
    
    # Error should be handled cleanly, falling back to regex-only results
    assert res["detected"] is True
    assert "email" in res["types"]
    assert "person" not in res["types"]

def test_lazy_loading_behavior():
    PIIDetector.pipeline = None
    
    # By default, accessing _get_pipeline with USE_HF_PII_NER=False should set fallback state without importing transformers
    original_use_hf = settings.USE_HF_PII_NER
    try:
        settings.USE_HF_PII_NER = False
        pipe = PIIDetector._get_pipeline()
        assert pipe == "FALLBACK"
        assert PIIDetector.pipeline == "FALLBACK"
    finally:
        settings.USE_HF_PII_NER = original_use_hf

def test_guard_engine_integration():
    # Mocking location detection inside GuardEngine check
    mock_entities = [{"entity_group": "LOC", "score": 0.99, "word": "London", "start": 14, "end": 20}]
    mock_pipe = MockNerPipeline(mock_entities)
    PIIDetector.set_pipeline(mock_pipe)

    engine = GuardEngine()
    policy = Policy(
        version="1.0",
        rules=[
            PolicyRule(
                id="pii-block",
                scope="input",
                check={"type": "pii"},
                action={"type": "block"}
            )
        ]
    )

    # London as location should be classified as PII, triggering the block action
    res = engine.check_input("I am traveling to London.", policy)
    assert res.allowed is False
    assert "pii-block" in res.matched_rules
