import os
import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.checks.toxicity_scorer import ToxicityScorer
from app.config import settings

class MockClassifierPipeline:
    def __init__(self, mock_output):
        self.mock_output = mock_output
        self.call_count = 0

    def __call__(self, text, *args, **kwargs):
        self.call_count += 1
        return self.mock_output

def test_toxicity_scorer_hf_mock_toxic():
    # Mocking positive HATE output
    mock_output = [{"label": "HATE", "score": 0.85}]
    mock_pipe = MockClassifierPipeline(mock_output)
    
    # Inject mock pipeline and disable synthetic mode
    scorer = ToxicityScorer(pipeline=mock_pipe, use_synthetic=False)
    
    score = scorer.score("some text")
    assert score == 0.85
    assert mock_pipe.call_count == 1

def test_toxicity_scorer_hf_mock_clean():
    # Mocking positive NON_HATE output
    mock_output = [{"label": "NON_HATE", "score": 0.90}]
    mock_pipe = MockClassifierPipeline(mock_output)
    
    scorer = ToxicityScorer(pipeline=mock_pipe, use_synthetic=False)
    
    score = scorer.score("some text")
    # NON_HATE score 0.90 implies HATE score 0.10
    assert abs(score - 0.10) < 1e-5
    assert mock_pipe.call_count == 1

def test_toxicity_normalization_multi_label():
    # Mocking multi-label (toxic, insult, identity_hate, neutral)
    mock_output = [
        {"label": "toxic", "score": 0.80},
        {"label": "insult", "score": 0.50},
        {"label": "neutral", "score": 0.10}
    ]
    mock_pipe = MockClassifierPipeline(mock_output)
    scorer = ToxicityScorer(pipeline=mock_pipe, use_synthetic=False)
    
    score = scorer.score("some text")
    # Should take maximum of explicit toxic labels: max(0.80, 0.50) = 0.80
    assert score == 0.80

def test_toxicity_scorer_fallback_on_error():
    # Mock pipeline that raises an error during inference
    def mock_fail_call(text):
        raise RuntimeError("Inference error")
        
    scorer = ToxicityScorer(pipeline=mock_fail_call, use_synthetic=False)
    
    # Triggering inference error should fall back to synthetic TF-IDF scorer
    score_clean = scorer.score("Hello, how are you?")
    score_toxic = scorer.score("Shut up, you loser. I hate you.")
    
    # TF-IDF clean score should be lower than toxic score
    assert score_clean < 0.5
    assert score_toxic > 0.5

def test_toxicity_scorer_synthetic_force_mode():
    mock_pipe = MockClassifierPipeline([{"label": "HATE", "score": 0.95}])
    scorer = ToxicityScorer(pipeline=mock_pipe, use_synthetic=True)
    
    # With use_synthetic=True, it should not call the mock pipeline
    score = scorer.score("Hello, how are you today?")
    assert score < 0.5
    assert mock_pipe.call_count == 0

def test_toxicity_lazy_load_behavior():
    # Reset instance fields
    scorer = ToxicityScorer()
    scorer.pipeline = None
    scorer.use_synthetic = False
    
    # Mock settings to turn off HF loading during tests if called without injection
    # so we fallback to synthetic immediately and don't try downloading
    original_use_hf = settings.USE_HF_TOXICITY
    try:
        settings.USE_HF_TOXICITY = False
        score = scorer.score("Hello, clean input.")
        # Fallback should run
        assert score < 0.5
        assert scorer.pipeline == "FALLBACK"
    finally:
        settings.USE_HF_TOXICITY = original_use_hf
