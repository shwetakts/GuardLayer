"""Test doubles for provider adapters.

These fakes are used only by automated tests and must never be registered
as production providers.
"""

from .fake_openai import FakeOpenAIAdapter
from .fake_anthropic import FakeAnthropicAdapter
from .fake_third import FakeThirdAdapter

__all__ = [
    "FakeOpenAIAdapter",
    "FakeAnthropicAdapter",
    "FakeThirdAdapter",
]