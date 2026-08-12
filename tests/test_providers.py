"""
tests/test_providers.py

Tests the ProviderRouter registration, lookup, and extensibility.

The production router now registers real provider adapters (OpenAIProvider,
AnthropicProvider, OllamaProvider). Tests that exercise the full
request/response pipeline inject fakes from tests.fakes so no live API
calls or model downloads occur.
"""

import sys
import os
import pytest
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from providers.router import ProviderRouter
from providers.openai import OpenAIProvider
from providers.anthropic import AnthropicProvider
from providers.ollama import OllamaProvider
from tests.fakes import FakeOpenAIAdapter, FakeAnthropicAdapter, FakeThirdAdapter


def test_router_default_registration():
    """Production router registers openai, anthropic, and ollama."""
    router = ProviderRouter()
    providers = router.list_providers()
    assert "openai" in providers
    assert "anthropic" in providers
    assert "ollama" in providers


def test_router_production_adapter_types():
    """Default adapters are real production classes, not test doubles."""
    router = ProviderRouter()
    assert isinstance(router.get_adapter("openai"), OpenAIProvider)
    assert isinstance(router.get_adapter("anthropic"), AnthropicProvider)
    assert isinstance(router.get_adapter("ollama"), OllamaProvider)


def test_router_unknown_provider():
    router = ProviderRouter()
    with pytest.raises(KeyError) as excinfo:
        router.get_adapter("unknown-llm")
    assert "not registered" in str(excinfo.value)


def test_third_provider_extensibility():
    """A custom adapter can be registered at runtime without code changes to the router."""
    router = ProviderRouter()
    fake_third = FakeThirdAdapter()
    router.register("third", fake_third)

    providers = router.list_providers()
    assert "third" in providers
    assert router.get_adapter("third") is fake_third


def test_fake_third_generate_response():
    """FakeThirdAdapter returns the expected deterministic response."""
    fake = FakeThirdAdapter()
    resp = asyncio.get_event_loop().run_until_complete(
        fake.generate([{"role": "user", "content": "Hello"}])
    )
    assert "FakeThird" in resp.text
    assert resp.provider == "third"


def test_register_overrides_existing():
    """Registering a name a second time replaces the existing adapter."""
    router = ProviderRouter()
    fake = FakeOpenAIAdapter()
    router.register("openai", fake)
    assert router.get_adapter("openai") is fake


def test_openai_raises_on_missing_key():
    """OpenAIProvider raises ProviderAuthenticationError when no API key is set."""
    from core.exceptions import ProviderAuthenticationError
    provider = OpenAIProvider(api_key="")
    with pytest.raises(ProviderAuthenticationError):
        provider._get_client()


def test_anthropic_raises_on_missing_key():
    """AnthropicProvider raises ProviderAuthenticationError when no API key is set."""
    from core.exceptions import ProviderAuthenticationError
    provider = AnthropicProvider(api_key="")
    with pytest.raises(ProviderAuthenticationError):
        provider._get_client()
