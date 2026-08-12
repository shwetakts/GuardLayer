"""Fake third-party adapter — deterministic test double for extensibility tests."""
from typing import List, Dict, Optional
from providers.base import BaseProviderAdapter
from core.models import ProviderResponse


class FakeThirdAdapter(BaseProviderAdapter):
    """
    Demonstrates that registering a third provider adapter requires no changes
    to the GuardEngine or policy system. Used in tests only.
    """

    def complete(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            return "FakeThird: Empty messages."
        last = messages[-1].get("content", "").lower()
        if "trigger pii" in last:
            return "FakeThird: My email is third-agent@example.com and phone is 800-555-0199."
        if "trigger toxicity" in last:
            return "You are absolute garbage. Shut up, you idiot!"
        return "FakeThird: Hello! How can I assist you with this custom provider?"

    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> ProviderResponse:
        text = self.complete(messages)
        return ProviderResponse(
            provider="third",
            model="fake-third-model",
            text=text,
            request_id=request_id,
        )
