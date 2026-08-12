from typing import Dict, List
from providers.base import BaseProviderAdapter
from providers.openai import OpenAIProvider
from providers.anthropic import AnthropicProvider
from providers.ollama import OllamaProvider
from providers.openrouter import OpenRouterProvider


class ProviderRouter:
    def __init__(self):
        self._adapters: Dict[str, BaseProviderAdapter] = {}
        # Register production providers only.
        # Credentials are read lazily from settings — no key required at startup.
        self.register("openai", OpenAIProvider())
        self.register("anthropic", AnthropicProvider())
        self.register("ollama", OllamaProvider())
        self.register("openrouter", OpenRouterProvider())

    def register(self, name: str, adapter: BaseProviderAdapter) -> None:
        """Registers a provider adapter by name, replacing any existing entry."""
        self._adapters[name.strip().lower()] = adapter

    def get_adapter(self, name: str) -> BaseProviderAdapter:
        """Retrieves a provider adapter by name. Raises KeyError if not registered."""
        key = name.strip().lower()
        if key not in self._adapters:
            raise KeyError(f"Provider '{name}' is not registered.")
        return self._adapters[key]

    def list_providers(self) -> List[str]:
        """Returns the names of all currently registered providers."""
        return list(self._adapters.keys())
