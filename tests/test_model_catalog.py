import json
import socket

import httpx
import pytest

from app.admin_schemas import ModelEndpoint
from app.services import admin_config
from app.services.errors import BusinessError


def test_model_endpoints_normalize_full_paths_and_known_provider_roots():
    siliconflow = ModelEndpoint(
        provider="SiliconFlow",
        model_id="Qwen/Qwen2.5-7B-Instruct",
        base_url="https://api.siliconflow.cn/v1/chat/completions",
    )
    deepseek = ModelEndpoint(
        provider="DeepSeek", model_id="deepseek-v4-pro", base_url="https://api.deepseek.com"
    )
    assert siliconflow.base_url == "https://api.siliconflow.cn/v1"
    assert deepseek.base_url == "https://api.deepseek.com/v1"


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.setattr(
        admin_config,
        "runtime_model",
        lambda: {
            "provider": "test",
            "model_id": "manual-model",
            "base_url": "https://models.example.com/v1",
            "tokens_per_credit": 1000,
            "enabled": False,
            "secret": "test-only-secret",
        },
    )
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 443))],
    )
    original = httpx.Client

    def client(*args, **kwargs):
        def respond(request):
            assert request.url == "https://models.example.com/v1/models"
            assert request.headers["Authorization"] == "Bearer test-only-secret"
            return httpx.Response(200, json={"data": [{"id": "model-b"}, {"id": "model-a"}]})

        return original(*args, **kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(httpx, "Client", client)
    return original


def test_model_catalog_reads_published_provider_only(catalog):
    assert admin_config.available_models() == {
        "models": ["model-a", "model-b"],
        "source": "active_provider",
    }


def test_model_catalog_rejects_private_dns(monkeypatch, catalog):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(BusinessError, match="内部网络"):
        admin_config.available_models()


def test_model_catalog_rejects_large_or_invalid_response(monkeypatch, catalog):
    original = catalog

    def client_with_response(payload):
        def client(*args, **kwargs):
            return original(*args, **kwargs, transport=httpx.MockTransport(lambda _: payload))

        return client

    monkeypatch.setattr(
        httpx,
        "Client",
        client_with_response(httpx.Response(200, content=b"x" * 512_001)),
    )
    with pytest.raises(BusinessError, match="过大"):
        admin_config.available_models()
    monkeypatch.setattr(
        httpx,
        "Client",
        client_with_response(httpx.Response(200, content=json.dumps({"data": {}}).encode())),
    )
    with pytest.raises(BusinessError, match="格式"):
        admin_config.available_models()
