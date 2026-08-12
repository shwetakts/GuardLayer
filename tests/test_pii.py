import sys
import os
# Add root path to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.checks.pii_detector import PIIDetector

def test_clean_input():
    text = "Hello world! This is a completely clean input with no personal information."
    res = PIIDetector.detect(text)
    assert res["detected"] is False
    assert res["count"] == 0
    assert len(res["types"]) == 0
    
    redacted, summary = PIIDetector.redact(text)
    assert redacted == text
    assert summary["detected"] is False

def test_email_detection():
    text = "Please email me at alice.smith@company.co.uk for inquiries."
    res = PIIDetector.detect(text)
    assert res["detected"] is True
    assert res["count"] == 1
    assert "email" in res["types"]
    assert res["findings"][0]["type"] == "email"
    
    redacted, _ = PIIDetector.redact(text)
    assert redacted == "Please email me at [REDACTED] for inquiries."

def test_phone_detection():
    test_cases = [
        ("My phone is 800-555-0199.", "My phone is [REDACTED]."),
        ("Call +1-202-555-0143 tomorrow.", "Call [REDACTED] tomorrow."),
        ("Contact (800) 555-0199.", "Contact [REDACTED]."),
    ]
    for raw, expected in test_cases:
        res = PIIDetector.detect(raw)
        assert res["detected"] is True
        assert "phone" in res["types"]
        
        redacted, _ = PIIDetector.redact(raw)
        assert redacted == expected

def test_credit_card_detection():
    # A valid credit card using standard Mastercard mock sequence passing Luhn
    # 5105 1051 0510 5105:
    # 5*2=10->1, 1, 0*2=0, 5, 1*2=2, 0, 5*2=10->1, 1, 0*2=0, 5, 1*2=2, 0, 5*2=10->1, 1, 0*2=0, 5
    # Sum: 1+1+0+5+2+0+1+1+0+5+2+0+1+1+0+5 = 25 (not passing 10)
    # Let's use a standard test visa card: 4111 1111 1111 1111
    # Odd positions from right: 1, 1, 1, 1, 1, 1, 1, 1 -> sum is 8
    # Even positions from right: 1*2=2, 1*2=2, 1*2=2, 1*2=2, 1*2=2, 1*2=2, 1*2=2, 4*2=8 -> sum is 2+2+2+2+2+2+2+8 = 22
    # Total sum: 8 + 22 = 30 -> 30 % 10 == 0! Valid!
    valid_visa = "4111-1111-1111-1111"
    res = PIIDetector.detect(f"My card is {valid_visa}")
    assert res["detected"] is True
    assert "credit_card" in res["types"]
    
    redacted, _ = PIIDetector.redact(f"My card is {valid_visa}")
    assert redacted == "My card is [REDACTED]"

def test_credit_card_luhn_failure():
    # An invalid card (fails Luhn)
    invalid_card = "4111-1111-1111-1112"
    res = PIIDetector.detect(f"My card is {invalid_card}")
    assert res["detected"] is False

def test_false_positives():
    # Standard numbers or sequences that resemble lengths but aren't credit cards
    text = "The coordinates are 2026-08-11 and tracking number 1234567890123."
    res = PIIDetector.detect(text)
    assert res["detected"] is False

def test_multiple_pii():
    text = "Send visa card 4111 1111 1111 1111 or email security@domain.com, or dial 555-555-5555."
    res = PIIDetector.detect(text)
    assert res["count"] == 3
    assert set(res["types"]) == {"email", "phone", "credit_card"}
    
    redacted, _ = PIIDetector.redact(text)
    assert redacted == "Send visa card [REDACTED] or email [REDACTED], or dial [REDACTED]."
