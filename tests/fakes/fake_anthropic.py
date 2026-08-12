"""Fake Anthropic adapter — deterministic test double. NOT a production provider."""
from typing import List, Dict, Optional
from providers.base import BaseProviderAdapter
from core.models import ProviderResponse


class FakeAnthropicAdapter(BaseProviderAdapter):
    """
    Deterministic test double that mimics Anthropic response shapes without
    calling any external API. Registered as 'anthropic' only during tests.
    """

    def complete(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            return "FakeAnthropic: Empty messages."
        last = messages[-1].get("content", "").lower()
        if "trigger pii" in last:
            return "FakeAnthropic: My email is anthropic-agent@example.com and phone is 800-555-0199."
        if "trigger toxicity" in last:
            return "You are absolute garbage. Shut up, you idiot!"
        if "trigger error" in last:
            raise RuntimeError("FakeAnthropic simulated API error.")
        return "FakeAnthropic: Hello! How can I assist you?"

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
            provider="anthropic",
            model="fake-anthropic-model",
            text=text,
            request_id=request_id,
        )
