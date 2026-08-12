"""Fake OpenAI adapter — deterministic test double. NOT a production provider."""
from typing import List, Dict, Optional
from providers.base import BaseProviderAdapter
from core.models import ProviderResponse


class FakeOpenAIAdapter(BaseProviderAdapter):
    """
    Deterministic test double that mimics OpenAI response shapes without
    calling any external API. Registered as 'openai' only during tests.
    """

    def complete(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            return "FakeOpenAI: Empty messages."
        last = messages[-1].get("content", "").lower()
        if "trigger pii" in last:
            return "FakeOpenAI: My email is openai-agent@example.com and phone is 800-555-0199."
        if "trigger toxicity" in last:
            return "You are absolute garbage. Shut up, you idiot!"
        if "trigger error" in last:
            raise RuntimeError("FakeOpenAI simulated API error.")
        return "FakeOpenAI: Hello! How can I assist you?"

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
            provider="openai",
            model="fake-openai-model",
            text=text,
            request_id=request_id,
        )
