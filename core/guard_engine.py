from typing import List, Dict, Any
from core.models import Policy, PolicyRule, GuardResult
from core.checks.pii_detector import PIIDetector
from core.checks.toxicity_scorer import ToxicityScorer
from core.checks.topic_denier import TopicDenier

class GuardEngine:
    def __init__(self):
        # ToxicityScorer is a singleton, so this gets/creates the instance
        self.toxicity_scorer = ToxicityScorer()
        self.topic_denier = TopicDenier()

    def check_input(self, text: str, policy: Policy) -> GuardResult:
        """
        Orchestrates checks for the 'input' scope.
        """
        return self._evaluate_scope(text, policy, scope="input")

    def check_output(self, text: str, policy: Policy) -> GuardResult:
        """
        Orchestrates checks for the 'output' scope.
        """
        return self._evaluate_scope(text, policy, scope="output")

    def _evaluate_scope(self, text: str, policy: Policy, scope: str) -> GuardResult:
        # Filter rules matching the requested scope
        rules = [r for r in policy.rules if r.scope == scope]
        
        current_text = text
        all_findings: List[Dict[str, Any]] = []
        matched_rules: List[str] = []
        
        # Track if we need to block or redact
        should_block = False
        should_redact = False
        
        for rule in rules:
            if rule.check.type == "pii":
                # Run PII check
                pii_summary = PIIDetector.detect(current_text)
                if pii_summary["detected"]:
                    matched_rules.append(rule.id)
                    all_findings.extend(pii_summary["findings"])
                    
                    if rule.action.type == "block":
                        should_block = True
                    elif rule.action.type == "redact":
                        should_redact = True
                        # Perform redaction on current_text
                        current_text, _ = PIIDetector.redact(current_text)

            elif rule.check.type == "toxicity":
                # Run Toxicity check
                score = self.toxicity_scorer.score(current_text)
                threshold = rule.check.threshold if rule.check.threshold is not None else 0.8
                if score >= threshold:
                    matched_rules.append(rule.id)
                    all_findings.append({
                        "check": "toxicity",
                        "score": round(score, 4),
                        "threshold": threshold,
                        "action": rule.action.type
                    })
                    if rule.action.type == "block":
                        should_block = True
                    elif rule.action.type == "redact":
                        should_redact = True

            elif rule.check.type == "topic":
                # Run Topic check
                topic_findings = self.topic_denier.check_topics(
                    current_text,
                    rule.check.topics or [],
                    semantic_threshold=rule.check.semantic_threshold
                )
                if topic_findings:
                    matched_rules.append(rule.id)
                    all_findings.extend(topic_findings)
                    if rule.action.type == "block":
                        should_block = True
                    elif rule.action.type == "redact":
                        should_redact = True

        # Resolve final action priority: block > redact > allow
        if should_block:
            final_action = "block"
            allowed = False
        elif should_redact:
            final_action = "redact"
            allowed = True
        else:
            final_action = "allow"
            allowed = True

        return GuardResult(
            allowed=allowed,
            action=final_action,
            findings=all_findings,
            matched_rules=matched_rules,
            text=current_text
        )
