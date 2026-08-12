import httpx
from typing import List, Dict, Optional
from providers.base import BaseProviderAdapter
from core.models import ProviderResponse
from app.config import settings
from core.exceptions import ProviderTimeoutError, ProviderUnavailableError

class OllamaProvider(BaseProviderAdapter):
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout if timeout is not None else settings.PROVIDER_TIMEOUT

    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None
    ) -> ProviderResponse:
        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0
        }
        
        headers = {}
        if request_id:
            headers["X-Request-ID"] = request_id
            
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"Ollama request timed out: {e}")
        except httpx.RequestError as e:
            raise ProviderUnavailableError(f"Ollama server is unavailable: {e}")

        if response.status_code != 200:
            raise RuntimeError(f"Ollama server returned error status {response.status_code}: {response.text}")

        try:
            resp_data = response.json()
            text = resp_data["choices"][0]["message"]["content"]
            return ProviderResponse(
                provider="ollama",
                model=self.model,
                text=text,
                request_id=request_id
            )
        except (KeyError, IndexError, ValueError) as e:
            raise RuntimeError(f"Malformed response from Ollama server: {e}. Raw response: {response.text}")
