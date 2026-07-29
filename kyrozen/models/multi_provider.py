"""Multi-provider model with priority-based fallback.

OmniRoute > Gemini > Groq > DeepSeek
"""
from __future__ import annotations

import os
from typing import Any

from kyrozen.config import KyrozenConfig
from kyrozen.logs import get_logger

from .base import ModelInterface, ModelResponse, Usage
from .providers import GoogleProvider, OpenAICompatProvider

_logger = get_logger(__name__)

_DEFAULT_MODELS: dict[str, str] = {
    "omniroute": "auto",
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.0-flash",
    "deepseek": "deepseek-chat",
}


def _build_omniroute_provider(config: KyrozenConfig) -> ModelInterface | None:
    base_url = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128/v1")
    api_key = os.environ.get("OMNIROUTE_API_KEY", "auto")
    if not api_key:
        return None
    # Health-check probe (longer timeout for slow servers)
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return None
    except Exception as exc:
        _logger.log("warning", f"OmniRoute unavailable: {exc}")
        return None
    from dataclasses import replace
    cfg = replace(config, provider="omniroute", api_key=api_key, base_url=base_url,
                  model_simple=_DEFAULT_MODELS["omniroute"])
    try:
        return OpenAICompatProvider(cfg, model=cfg.model_simple)
    except Exception as exc:
        _logger.log("warning", f"OmniRoute init failed: {exc}")
        return None


def _build_groq_provider(config: KyrozenConfig) -> ModelInterface | None:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or not api_key.startswith("gsk_"):
        return None
    from dataclasses import replace
    cfg = replace(config, provider="groq", api_key=api_key,
                  base_url="https://api.groq.com/openai/v1",
                  model_simple=_DEFAULT_MODELS["groq"])
    try:
        return OpenAICompatProvider(cfg, model=cfg.model_simple)
    except Exception as exc:
        _logger.log("warning", f"Groq unavailable: {exc}")
        return None


def _build_gemini_provider(config: KyrozenConfig) -> ModelInterface | None:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    from dataclasses import replace
    cfg = replace(config, provider="google", api_key=api_key,
                  model_simple=_DEFAULT_MODELS["gemini"])
    try:
        return GoogleProvider(cfg, model=cfg.model_simple)
    except Exception as exc:
        _logger.log("warning", f"Gemini unavailable: {exc}")
        return None


def _build_deepseek_provider(config: KyrozenConfig) -> ModelInterface | None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return None
    from dataclasses import replace
    cfg = replace(config, provider="deepseek", api_key=api_key,
                  base_url="https://api.deepseek.com/v1",
                  model_simple=_DEFAULT_MODELS["deepseek"])
    try:
        return OpenAICompatProvider(cfg, model=cfg.model_simple)
    except Exception as exc:
        _logger.log("warning", f"DeepSeek unavailable: {exc}")
        return None


class MultiProviderModel(ModelInterface):
    """Tries providers in priority order, falling through on any error."""

    def __init__(self, providers: list[tuple[str, ModelInterface]], config: KyrozenConfig) -> None:
        super().__init__(model="multi")
        self._providers = providers
        self._config = config

    @property
    def provider_name(self) -> str:
        names = [name for name, _ in self._providers]
        return f"multi({','.join(names)})"

    def chat(self, messages: list[dict[str, str]], model: str | None = None) -> ModelResponse:
        errors: list[str] = []
        for name, provider in self._providers:
            try:
                response = provider.chat(messages, model)
                response.provider = name
                _logger.log("info", f"Multi-provider routed to {name}")
                return response
            except Exception as exc:
                msg = f"{name}: {exc}"
                errors.append(msg)
                _logger.log("warning", f"Provider {name} failed: {exc}")
                continue
        raise RuntimeError(f"All providers exhausted: {'; '.join(errors)}")

    def chat_stream(self, messages: list[dict[str, str]], model: str | None = None) -> Any:
        errors: list[str] = []
        for name, provider in self._providers:
            try:
                for chunk in provider.chat_stream(messages, model):
                    yield chunk
                return
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                continue
        raise RuntimeError(f"All providers exhausted (stream): {'; '.join(errors)}")


def build_multi_provider(config: KyrozenConfig) -> MultiProviderModel:
    builders = [
        ("omniroute", _build_omniroute_provider),
        ("gemini", _build_gemini_provider),
        ("groq", _build_groq_provider),
        ("deepseek", _build_deepseek_provider),
    ]
    providers: list[tuple[str, ModelInterface]] = []
    for name, builder in builders:
        try:
            provider = builder(config)
            if provider is not None:
                providers.append((name, provider))
                _logger.log("info", f"Multi-provider: {name} ready")
        except Exception as exc:
            _logger.log("warning", f"Multi-provider: {name} unavailable: {exc}")
    if not providers:
        raise RuntimeError("No model providers available. Set at least one API key.")
    _logger.log("info", f"Multi-provider chain: {' > '.join(name for name, _ in providers)}")
    return MultiProviderModel(providers, config)
