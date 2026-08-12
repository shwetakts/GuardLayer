"""
Real OpenAI provider adapter using the official openai SDK.

Requirements:
  pip install openai

Configuration (environment variables or .env):
  OPENAI_API_KEY   — required at call time (not at import time)
  OPENAI_MODEL     — default: gpt-4o-mini
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


class OpenAIProvider(BaseProviderAdapter):
    """
    Production OpenAI provider. Credentials and model are read from
    app settings at call time so the application starts without requiring
    a key to be present in the environment.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        # Defer settings import so this module can be imported freely without
        # triggering pydantic-settings validation at module load.
        from app.config import settings

        self._api_key = api_key or settings.OPENAI_API_KEY or None
        self._model = model or settings.OPENAI_MODEL
        self._timeout = timeout if timeout is not None else settings.PROVIDER_TIMEOUT

    def _get_client(self):
        """Lazily import and construct the openai client, raising a clear error if missing."""
        try:
            import openai  # noqa: PLC0415
        except ImportError as exc:
            raise ProviderUnavailableError(
                "The 'openai' package is not installed. "
                "Run: pip install openai"
            ) from exc

        key = self._api_key
        if not key:
            raise ProviderAuthenticationError(
                "OPENAI_API_KEY is not configured. "
                "Set the OPENAI_API_KEY environment variable before selecting the 'openai' provider."
            )

        return openai.AsyncOpenAI(api_key=key, timeout=float(self._timeout))

    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> ProviderResponse:
        try:
            import openai  # noqa: PLC0415
        except ImportError as exc:
            raise ProviderUnavailableError(
                "The 'openai' package is not installed. Run: pip install openai"
            ) from exc

        client = self._get_client()

        extra_headers: Dict[str, str] = {}
        if request_id:
            extra_headers["X-Request-ID"] = request_id

        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0,
                extra_headers=extra_headers or None,
            )
        except openai.AuthenticationError as exc:
            raise ProviderAuthenticationError(
                f"OpenAI authentication failed — check OPENAI_API_KEY: {exc}"
            ) from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimitError(f"OpenAI rate limit exceeded: {exc}") from exc
        except openai.APITimeoutError as exc:
            raise ProviderTimeoutError(f"OpenAI request timed out: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailableError(f"OpenAI API unreachable: {exc}") from exc
        except openai.APIStatusError as exc:
            raise ProviderUnavailableError(
                f"OpenAI API returned status {exc.status_code}: {exc.message}"
            ) from exc

        try:
            text = response.choices[0].message.content or ""
            model_used = response.model or self._model
        except (AttributeError, IndexError) as exc:
            raise ProviderUnavailableError(
                f"Unexpected OpenAI response structure: {exc}"
            ) from exc

        return ProviderResponse(
            provider="openai",
            model=model_used,
            text=text,
            request_id=request_id,
        )
