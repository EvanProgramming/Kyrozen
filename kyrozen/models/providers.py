"""Concrete model provider implementations for Kyrozen Core."""

from __future__ import annotations

import os
import random
import sys
import time
from typing import Any, Iterator

from kyrozen.config import KyrozenConfig
from kyrozen.config.settings import PROVIDER_BASE_URLS

from .base import ModelInterface, ModelResponse, Usage


# Approximate cost per 1M tokens (input, output) in USD
PROVIDER_COSTS: dict[str, tuple[float, float]] = {
    "deepseek": (0.27, 1.10),
    "openai": (2.50, 10.00),
    "anthropic": (3.00, 15.00),
    "google": (0.15, 0.60),
    "ollama": (0.0, 0.0),
}


def _retry_with_backoff(fn, max_retries: int = 3, base_delay: float = 1.0):
    """Call fn() with exponential backoff on rate-limit or transient errors."""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            msg = str(e).lower()
            is_rate_limit = "429" in msg or "rate limit" in msg or "too many requests" in msg
            is_server_error = "500" in msg or "502" in msg or "503" in msg or "server error" in msg
            if (is_rate_limit or is_server_error) and attempt < max_retries:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                time.sleep(delay)
                continue
            raise
    raise last_exc


class OpenAICompatProvider(ModelInterface):
    """OpenAI-compatible provider: DeepSeek, OpenAI, Ollama."""

    def __init__(self, config: KyrozenConfig, model: str = "") -> None:
        super().__init__(model=model or config.model_simple)
        self.config = config
        try:
            from openai import OpenAI
        except ImportError:
            sys.exit("The 'openai' package is required. Install it with: pip install openai")
        kwargs: dict[str, Any] = {"api_key": config.api_key or "sk-placeholder"}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = OpenAI(**kwargs)

    @property
    def provider_name(self) -> str:
        return self.config.provider

    def chat(self, messages: list[dict[str, str]], model: str | None = None) -> ModelResponse:
        model = model or self.model

        def _call():
            return self._client.chat.completions.create(model=model, messages=messages)

        response = _retry_with_backoff(_call)
        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        usage_obj = None
        if usage is not None:
            usage_obj = Usage(
                prompt_tokens=usage.prompt_tokens or 0,
                completion_tokens=usage.completion_tokens or 0,
            )
        return ModelResponse(content=text.strip(), usage=usage_obj, model=model, provider=self.provider_name)

    def chat_stream(self, messages: list[dict[str, str]], model: str | None = None) -> Iterator[str]:
        model = model or self.model

        def _call():
            return self._client.chat.completions.create(model=model, messages=messages, stream=True)

        stream = _retry_with_backoff(_call)
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content


class AnthropicProvider(ModelInterface):
    """Anthropic Claude provider."""

    def __init__(self, config: KyrozenConfig, model: str = "") -> None:
        super().__init__(model=model or config.model_simple)
        self.config = config
        try:
            import anthropic
        except ImportError:
            sys.exit("The 'anthropic' package is required for Claude. Install it with: pip install anthropic")
        kwargs: dict[str, Any] = {"api_key": config.api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = anthropic.Anthropic(**kwargs)

    @property
    def provider_name(self) -> str:
        return self.config.provider

    def _prepare_messages(self, messages: list[dict[str, str]]) -> tuple[list[str], list[dict]]:
        system_prompts: list[str] = []
        claude_messages: list[dict] = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_prompts.append(content)
            else:
                claude_messages.append({"role": role, "content": content})
        return system_prompts, claude_messages

    def chat(self, messages: list[dict[str, str]], model: str | None = None) -> ModelResponse:
        model = model or self.model
        system_prompts, claude_messages = self._prepare_messages(messages)
        kwargs: dict[str, Any] = {"model": model, "max_tokens": 4096, "messages": claude_messages}
        if system_prompts:
            kwargs["system"] = "\n\n".join(system_prompts)

        def _call():
            return self._client.messages.create(**kwargs)

        response = _retry_with_backoff(_call)
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
        usage = getattr(response, "usage", None)
        usage_obj = None
        if usage is not None:
            usage_obj = Usage(
                prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
                completion_tokens=getattr(usage, "output_tokens", 0) or 0,
            )
        return ModelResponse(content=text.strip(), usage=usage_obj, model=model, provider=self.provider_name)


class GoogleProvider(ModelInterface):
    """Google Gemini provider."""

    def __init__(self, config: KyrozenConfig, model: str = "") -> None:
        super().__init__(model=model or config.model_simple)
        self.config = config
        try:
            import google.generativeai as genai
        except ImportError:
            sys.exit("The 'google-generativeai' package is required for Gemini. Install it with: pip install google-generativeai")
        genai.configure(api_key=config.api_key or os.environ.get("GEMINI_API_KEY", ""))
        self._genai = genai

    @property
    def provider_name(self) -> str:
        return self.config.provider

    def chat(self, messages: list[dict[str, str]], model: str | None = None) -> ModelResponse:
        model = model or self.model
        system_instruction: str | None = None
        history: list[dict] = []
        user_content: str = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_instruction = content if system_instruction is None else system_instruction + "\n\n" + content
            elif role == "user":
                if user_content:
                    history.append({"role": "user", "parts": [user_content]})
                user_content = content
            elif role == "assistant":
                if user_content:
                    history.append({"role": "user", "parts": [user_content]})
                    user_content = ""
                history.append({"role": "model", "parts": [content]})
        if not user_content:
            user_content = "Continue."

        def _call():
            client = self._genai.GenerativeModel(model_name=model, system_instruction=system_instruction)
            chat = client.start_chat(history=history if history else None)
            try:
                return chat.send_message(user_content)
            except Exception:
                return client.generate_content(user_content)

        response = _retry_with_backoff(_call)
        text = response.text or ""
        usage_obj = None
        try:
            meta = getattr(response, "usage_metadata", None)
            if meta is not None:
                usage_obj = Usage(
                    prompt_tokens=getattr(meta, "prompt_token_count", 0) or 0,
                    completion_tokens=getattr(meta, "candidates_token_count", 0) or 0,
                )
        except Exception:
            pass
        return ModelResponse(content=text.strip(), usage=usage_obj, model=model, provider=self.provider_name)


def get_model_provider(config: KyrozenConfig, model: str = "") -> ModelInterface:
    """Factory function for model providers."""
    if config.provider in ("deepseek", "openai", "ollama"):
        return OpenAICompatProvider(config, model=model)
    if config.provider == "anthropic":
        return AnthropicProvider(config, model=model)
    if config.provider == "google":
        return GoogleProvider(config, model=model)
    raise ValueError(f"Unsupported provider: {config.provider}")
