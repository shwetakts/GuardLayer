from typing import List, Dict, Optional

from providers.base import BaseProviderAdapter
from core.models import ProviderResponse
from core.exceptions import (
    ProviderAuthenticationError,
    ProviderUnavailableError,
    ProviderTimeoutError,
    ProviderRateLimitError,
)


class OpenRouterProvider(BaseProviderAdapter):
    """OpenRouter provider using the OpenAI-compatible API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        from app.config import settings

        self._api_key = api_key or settings.OPENROUTER_API_KEY or None
        self._model = model or settings.OPENROUTER_MODEL
        self._timeout = (
            timeout if timeout is not None else settings.PROVIDER_TIMEOUT
        )

    def _get_client(self):
        try:
            import openai
        except ImportError as exc:
            raise ProviderUnavailableError(
                "The 'openai' package is not installed. "
                "Run: pip install openai"
            ) from exc

        if not self._api_key:
            raise ProviderAuthenticationError(
                "OPENROUTER_API_KEY is not configured."
            )

        return openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=float(self._timeout),
        )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> ProviderResponse:

        try:
            import openai
        except ImportError as exc:
            raise ProviderUnavailableError(
                "The 'openai' package is not installed. Run: pip install openai"
            ) from exc

        client = self._get_client()

        headers: Dict[str, str] = {}

        if request_id:
            headers["X-Request-ID"] = request_id

        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0,
                extra_headers=headers or None,
            )

        except openai.AuthenticationError as exc:
            raise ProviderAuthenticationError(
                f"OpenRouter authentication failed: {exc}"
            ) from exc

        except openai.RateLimitError as exc:
            raise ProviderRateLimitError(
                f"OpenRouter rate limit exceeded: {exc}"
            ) from exc

        except openai.APITimeoutError as exc:
            raise ProviderTimeoutError(
                f"OpenRouter request timed out: {exc}"
            ) from exc

        except openai.APIConnectionError as exc:
            raise ProviderUnavailableError(
                f"OpenRouter API unreachable: {exc}"
            ) from exc

        except openai.APIStatusError as exc:
            raise ProviderUnavailableError(
                f"OpenRouter API returned status {exc.status_code}: {exc.message}"
            ) from exc

        try:
            text = response.choices[0].message.content or ""
            model_used = response.model or self._model

        except (AttributeError, IndexError) as exc:
            raise ProviderUnavailableError(
                f"Unexpected OpenRouter response structure: {exc}"
            ) from exc

        return ProviderResponse(
            provider="openrouter",
            model=model_used,
            text=text,
            request_id=request_id,
        )