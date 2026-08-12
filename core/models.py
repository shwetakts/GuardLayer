from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, model_validator

class RuleCheck(BaseModel):
    type: str  # "pii", "toxicity", "topic"
    entities: Optional[List[str]] = None
    threshold: Optional[float] = None
    topics: Optional[List[str]] = None
    keyword_threshold: Optional[int] = None
    semantic_threshold: Optional[float] = None

class RuleAction(BaseModel):
    type: str  # "allow", "redact", "block"
    replacement: Optional[str] = None

class PolicyRule(BaseModel):
    id: str
    scope: str  # "input", "output"
    check: RuleCheck
    action: RuleAction

    @property
    def threshold(self) -> Optional[float]:
        return self.check.threshold

    @property
    def topics(self) -> Optional[List[str]]:
        return self.check.topics

    @model_validator(mode="before")
    @classmethod
    def convert_flat_to_nested(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 1. Convert flat 'check' to RuleCheck
            raw_check = data.get("check")
            if isinstance(raw_check, str):
                check_dict: Dict[str, Any] = {"type": raw_check}
                if "threshold" in data:
                    check_dict["threshold"] = data.get("threshold")
                if "topics" in data:
                    check_dict["topics"] = data.get("topics")
                data["check"] = check_dict
            
            # 2. Convert flat 'action' to RuleAction
            raw_action = data.get("action")
            if isinstance(raw_action, str):
                action_dict: Dict[str, Any] = {"type": raw_action}
                if "replacement" in data:
                    action_dict["replacement"] = data.get("replacement")
                data["action"] = action_dict
        return data

class PolicyMetadata(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class Policy(BaseModel):
    version: str
    extends: Optional[str] = None
    metadata: Optional[PolicyMetadata] = None
    rules: List[PolicyRule] = Field(default_factory=list)

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    provider: str
    messages: List[Message]
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None

class ProviderResponse(BaseModel):
    provider: str
    model: str
    text: str
    request_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    provider: str
    model: str
    guardrail_applied: bool
    final_action: str
    policy_version: str
    audit_id: str
    request_id: str
    blocked_rules: Optional[List[str]] = None

class HealthResponse(BaseModel):
    status: str
    database: str
    policy_version: str

class GuardResult(BaseModel):
    allowed: bool
    action: str  # "allow", "redact", "block"
    findings: List[Dict[str, Any]]
    matched_rules: List[str]
    text: str  # the (potentially redacted) text
