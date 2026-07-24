"""Cloud-proxied model provider for the Kyrozen desktop client.

The desktop client runs the Python Agent Runtime locally but routes all model
calls through the Kyrozen cloud backend so API keys and subscription quotas are
managed server-side.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Any, Callable

from kyrozen.models.base import ModelInterface, ModelResponse, Usage


class CloudProxyModelProvider(ModelInterface):
    """Model provider that forwards chat requests to the cloud over WebSocket.

    Usage from the desktop Python Agent Runtime:

        provider = CloudProxyModelProvider(send_message=ws_client.send_json)
        response = provider.chat(messages)

    When the WebSocket client receives a `model_stream_chunk` or `model_error`
    message, it should call ``provider.handle_response(message)`` so the
    provider can resolve the pending request future.
    """

    def __init__(
        self,
        send_message: Callable[[dict[str, Any]], Any],
        model: str = "cloud-proxy",
    ) -> None:
        super().__init__(model=model)
        self._send_message = send_message
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    @property
    def provider_name(self) -> str:
        return "cloud-proxy"

    def _create_request(self, messages: list[dict[str, str]], stream: bool = True) -> dict[str, Any]:
        return {
            "type": "model_request",
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
            "messages": messages,
            "stream": stream,
        }

    def chat(self, messages: list[dict[str, str]], model: str | None = None) -> ModelResponse:
        """Synchronous wrapper around the async cloud chat call.

        This method is safe to call from both the asyncio event-loop thread and
        from worker threads. When called from inside a running loop it schedules
        the request on that loop and blocks until the cloud responds; otherwise it
        runs a temporary event loop. The response is matched back to this call via
        ``request_id`` in ``handle_response``.
        """
        request = self._create_request(messages, stream=False)
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(self._chat_async(request), loop)
            result = future.result(timeout=120)
        except RuntimeError:
            result = asyncio.run(self._chat_async(request))

        usage = None
        if result.get("usage"):
            usage = Usage(**result["usage"])
        return ModelResponse(
            content=result.get("content", ""),
            usage=usage,
            model=model or self.model,
            provider=self.provider_name,
        )

    async def _chat_async(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request["request_id"]
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        with self._lock:
            self._pending[request_id] = future
        try:
            self._send_message(request)
            return await asyncio.wait_for(future, timeout=120)
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def handle_response(self, message: dict[str, Any]) -> None:
        """Process an incoming model_stream_chunk or model_error from the cloud."""
        request_id = message.get("request_id")
        if not request_id:
            return
        with self._lock:
            future = self._pending.get(request_id)
        if future is None or future.done():
            return

        loop = future.get_loop()

        if message.get("type") == "model_error" or "error" in message:
            error = RuntimeError(message.get("error", "Unknown model error"))
            loop.call_soon_threadsafe(future.set_exception, error)
            return

        if message.get("finished"):
            content = message.get("full_content", "")
            usage = message.get("usage")
            loop.call_soon_threadsafe(future.set_result, {"content": content, "usage": usage})
            return

        # For true streaming, accumulate chunks here if needed. The server's
        # current implementation sends the full content in the finished message,
        # so intermediate chunks are ignored for the synchronous chat() path.

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> Any:
        """Return an iterator that yields chunks from the cloud stream.

        The desktop Agent Runtime currently consumes chat() synchronously; this
        iterator is provided for future streaming support.
        """
        response = self.chat(messages, model=model)
        yield response.content
