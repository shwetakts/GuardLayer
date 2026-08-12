"""
Real Anthropic provider adapter using the official anthropic SDK.

Requirements:
  pip install anthropic

Configuration (environment variables or .env):
  ANTHROPIC_API_KEY   — required at call time (not at import time)
  ANTHROPIC_MODEL     — default: claude-3-5-haiku-20241022
"""

from typing import List, Dict, Optional
from providers.base import BaseProviderAdapter
from core.models import ProviderResponse
from core.exceptions import (
    ProviderAuthenticationError,
    ProviderUnavailableError,
    ProviderTimeoutError,
    ProviderRateLimitError,
)


class AnthropicProvider(BaseProviderAdapter):
    """
    Production Anthropic provider. Credentials and model are read from
    app settings at call time so the application starts without requiring
    a key to be present in the environment.

    The Anthropic messages API uses a slightly different structure from
    OpenAI: system messages are passed as a separate top-level parameter,
    and the final response is in response.content[0].text.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        from app.config import settings

        self._api_key = api_key or settings.ANTHROPIC_API_KEY or None
        self._model = model or settings.ANTHROPIC_MODEL
        self._timeout = timeout if timeout is not None else settings.PROVIDER_TIMEOUT

    def _get_client(self):
        """Lazily import and construct the anthropic client."""
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise ProviderUnavailableError(
                "The 'anthropic' package is not installed. "
                "Run: pip install anthropic"
            ) from exc

        key = self._api_key
        if not key:
            raise ProviderAuthenticationError(
                "ANTHROPIC_API_KEY is not configured. "
                "Set the ANTHROPIC_API_KEY environment variable before selecting the 'anthropic' provider."
            )

        return anthropic.AsyncAnthropic(api_key=key, timeout=float(self._timeout))

    @staticmethod
    def _split_messages(
        messages: List[Dict[str, str]],
    ) -> tuple[Optional[str], List[Dict[str, str]]]:
        """
        Anthropic's API separates the system prompt from the conversation.
        Extracts any leading system message and returns (system_text, remaining_messages).
        """
        system_text = None
        conversation: List[Dict[str, str]] = []
        for msg in messages:
            if msg.get("role") == "system":
                # Concatenate multiple system messages if present
                system_text = (system_text or "") + msg.get("content", "")
            else:
                conversation.append({"role": msg["role"], "content": msg.get("content", "")})
        return system_text, conversation

    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> ProviderResponse:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise ProviderUnavailableError(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            ) from exc

        client = self._get_client()
        system_text, conversation = self._split_messages(messages)

        kwargs: Dict = {
            "model": self._model,
            "max_tokens": 1024,
            "messages": conversation,
        }
        if system_text:
            kwargs["system"] = system_text

        try:
            response = await client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise ProviderAuthenticationError(
                f"Anthropic authentication failed — check ANTHROPIC_API_KEY: {exc}"
            ) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimitError(f"Anthropic rate limit exceeded: {exc}") from exc
        except anthropic.APITimeoutError as exc:
            raise ProviderTimeoutError(f"Anthropic request timed out: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailableError(f"Anthropic API unreachable: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderUnavailableError(
                f"Anthropic API returned status {exc.status_code}: {exc.message}"
            ) from exc

        try:
            text = response.content[0].text
            model_used = response.model or self._model
        except (AttributeError, IndexError) as exc:
            raise ProviderUnavailableError(
                f"Unexpected Anthropic response structure: {exc}"
            ) from exc

        return ProviderResponse(
            provider="anthropic",
            model=model_used,
            text=text,
            request_id=request_id,
        )
