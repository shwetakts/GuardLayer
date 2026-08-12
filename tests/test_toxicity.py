import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.checks.toxicity_scorer import ToxicityScorer

def test_toxicity_scorer_initialization():
    scorer1 = ToxicityScorer()
    scorer2 = ToxicityScorer()
    # Scorer should be a singleton
    assert scorer1 is scorer2

def test_clean_vs_toxic_scores():
    scorer = ToxicityScorer()
    
    clean_text = "Good morning! I hope you are having an excellent week. Can we review the database?"
    toxic_text = "Shut up you absolute idiot, I hate you and your code is garbage!"
    
    clean_score = scorer.score(clean_text)
    toxic_score = scorer.score(toxic_text)
    
    # Assert that toxic score is higher than clean score
    assert toxic_score > clean_score
    # Verify bounds
    assert 0.0 <= clean_score <= 1.0
    assert 0.0 <= toxic_score <= 1.0
    
    # Toxic text should have a high score
    assert toxic_score > 0.6
    # Clean text should have a low score
    assert clean_score < 0.3

def test_empty_text():
    scorer = ToxicityScorer()
    assert scorer.score("") == 0.0
    assert scorer.score("   ") == 0.0
