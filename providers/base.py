from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from core.models import ProviderResponse

class BaseProviderAdapter(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None
    ) -> ProviderResponse:
        """
        Takes list of messages and returns the normalized ProviderResponse.
        """
        pass
