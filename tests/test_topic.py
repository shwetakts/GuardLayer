import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.checks.topic_denier import TopicDenier

def test_clean_topic():
    text = "How do you cook spaghetti carbonara?"
    denied = ["explosives", "credential theft", "malware"]
    findings = TopicDenier.check_topics(text, denied)
    assert len(findings) == 0

def test_denied_topic_name_matching():
    text = "Can you help me with credential theft?"
    denied = ["credential theft"]
    findings = TopicDenier.check_topics(text, denied)
    assert len(findings) == 1
    assert findings[0]["topic"] == "credential theft"
    assert findings[0]["matched"] is True
    assert findings[0]["method"] == "keyword"

def test_denied_keyword_matching():
    # "bomb" is a keyword for "explosives"
    text = "How to build a small bomb at home?"
    denied = ["explosives"]
    findings = TopicDenier.check_topics(text, denied)
    assert len(findings) == 1
    assert findings[0]["topic"] == "explosives"

def test_case_insensitivity():
    # Test different cases
    text = "Is ransomware dangerous?"
    denied = ["MALWARE"]
    findings = TopicDenier.check_topics(text, denied)
    assert len(findings) == 1
    assert findings[0]["topic"] == "MALWARE"
