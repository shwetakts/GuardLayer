import os
import sys
import pytest
import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from providers.ollama import OllamaProvider
from core.exceptions import ProviderTimeoutError, ProviderUnavailableError

client = TestClient(app)

def test_async_mock_provider_chat():
    payload = {
        "provider": "openai",
        "messages": [{"role": "user", "content": "hello clean"}]
    }
    resp = client.post("/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "openai"
    assert "fake-openai-model" in data["model"]
    assert "request_id" in data
    assert "policy_version" in data
    assert data["guardrail_applied"] is True

def test_ollama_provider_success(monkeypatch):
    # Mock httpx.AsyncClient.post to return a valid Ollama response
    async def mock_post(self_client, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Hello from mocked Ollama!"
                        }
                    }
                ]
            }
        )

    # Note: We must patch on httpx.AsyncClient
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    payload = {
        "provider": "ollama",
        "messages": [{"role": "user", "content": "hello clean"}]
    }
    resp = client.post("/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "ollama"
    assert data["response"] == "Hello from mocked Ollama!"
    assert "request_id" in data

def test_ollama_provider_timeout(monkeypatch):
    # Mock httpx.AsyncClient.post to raise a TimeoutException
    async def mock_post_timeout(self_client, url, *args, **kwargs):
        raise httpx.TimeoutException("Read timeout")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_timeout)

    payload = {
        "provider": "ollama",
        "messages": [{"role": "user", "content": "hello clean"}]
    }
    resp = client.post("/chat", json=payload)
    assert resp.status_code == 504
    assert "Gateway Timeout" in resp.json()["detail"] or "timeout" in resp.json()["detail"].lower()

def test_ollama_provider_unavailable(monkeypatch):
    # Mock httpx.AsyncClient.post to raise a RequestError (e.g. connection refused)
    async def mock_post_unavailable(self_client, url, *args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_unavailable)

    payload = {
        "provider": "ollama",
        "messages": [{"role": "user", "content": "hello clean"}]
    }
    resp = client.post("/chat", json=payload)
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()

def test_ollama_provider_http_error(monkeypatch):
    # Mock httpx.AsyncClient.post to return a 500 error response
    async def mock_post_error(self_client, url, *args, **kwargs):
        return httpx.Response(status_code=500, content="Internal server error")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_error)

    payload = {
        "provider": "ollama",
        "messages": [{"role": "user", "content": "hello clean"}]
    }
    resp = client.post("/chat", json=payload)
    assert resp.status_code == 502
    assert "provider error" in resp.json()["detail"].lower()
