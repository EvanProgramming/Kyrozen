"""Tests for the desktop client's cloud-proxied model provider."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from kyrozen.desktop.cloud_proxy import CloudProxyModelProvider


@pytest.fixture
def captured() -> dict[str, Any]:
    return {"messages": []}


@pytest.fixture
def provider(captured: dict[str, Any]) -> CloudProxyModelProvider:
    def send_message(message: dict[str, Any]) -> None:
        captured["messages"].append(message)

    return CloudProxyModelProvider(send_message=send_message)


def test_cloud_proxy_creates_model_request(provider: CloudProxyModelProvider, captured: dict[str, Any]) -> None:
    messages = [{"role": "user", "content": "Hello"}]

    def resolve_later() -> None:
        time.sleep(0.05)
        request_id = captured["messages"][0]["request_id"]
        provider.handle_response({"request_id": request_id, "finished": True, "full_content": "Hi!"})

    threading.Thread(target=resolve_later, daemon=True).start()
    response = provider.chat(messages)

    assert response.content == "Hi!"
    assert response.provider == "cloud-proxy"
    assert len(captured["messages"]) == 1
    sent = captured["messages"][0]
    assert sent["type"] == "model_request"
    assert sent["messages"] == messages
    assert sent["stream"] is False


def test_cloud_proxy_handles_model_error(provider: CloudProxyModelProvider, captured: dict[str, Any]) -> None:
    messages = [{"role": "user", "content": "Hello"}]

    def resolve_later() -> None:
        time.sleep(0.05)
        request_id = captured["messages"][0]["request_id"]
        provider.handle_response({"request_id": request_id, "type": "model_error", "error": "Quota exceeded"})

    threading.Thread(target=resolve_later, daemon=True).start()
    with pytest.raises(RuntimeError, match="Quota exceeded"):
        provider.chat(messages)


def test_cloud_proxy_includes_usage(provider: CloudProxyModelProvider, captured: dict[str, Any]) -> None:
    messages = [{"role": "user", "content": "Hello"}]

    def resolve_later() -> None:
        time.sleep(0.05)
        request_id = captured["messages"][0]["request_id"]
        provider.handle_response(
            {
                "request_id": request_id,
                "finished": True,
                "full_content": "Answer",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )

    threading.Thread(target=resolve_later, daemon=True).start()
    response = provider.chat(messages)

    assert response.usage is not None
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 5
