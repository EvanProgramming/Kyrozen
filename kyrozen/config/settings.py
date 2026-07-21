"""Unified configuration for Kyrozen Core.

Reads from environment variables and a local JSON config file.
Never hard-codes secrets.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


DEFAULT_PROVIDER = "deepseek"

PROVIDER_ENV_VARS: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "ollama": "",
}

PROVIDER_DEFAULT_MODELS: dict[str, tuple[str, str]] = {
    "deepseek": ("deepseek-chat", "deepseek-reasoner"),
    "openai": ("gpt-4o", "gpt-4o"),
    "anthropic": ("claude-sonnet-4-20250514", "claude-sonnet-4-20250514"),
    "google": ("gemini-2.5-flash", "gemini-2.5-pro"),
    "ollama": ("llama3.2", "llama3.2"),
}

PROVIDER_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "google": "",
    "ollama": "http://localhost:11434/v1",
}


@dataclass
class KyrozenConfig:
    """Central configuration object."""

    provider: str = DEFAULT_PROVIDER
    api_key: str = ""
    base_url: str = ""
    model_simple: str = ""
    model_complex: str = ""
    permission_mode: str = "strict"  # "strict" requires confirmation for high-risk tools
    workspace_root: str = "."
    log_level: str = "INFO"
    memory_backend: str = "memory"  # "memory" or "chromadb"
    chroma_path: str = "./chroma_memory"
    task_store_path: str = "./kyrozen_tasks.json"
    config_path: str = field(default="~/.kyrozen_config.json", repr=False)

    def __post_init__(self) -> None:
        if not self.model_simple:
            self.model_simple = PROVIDER_DEFAULT_MODELS.get(self.provider, ("", ""))[0]
        if not self.model_complex:
            self.model_complex = PROVIDER_DEFAULT_MODELS.get(self.provider, ("", ""))[1]
        if not self.base_url:
            self.base_url = PROVIDER_BASE_URLS.get(self.provider, "")
        self.workspace_root = os.path.abspath(os.path.expanduser(self.workspace_root))

    def validate(self) -> list[str]:
        """Return a list of validation issues."""
        issues: list[str] = []
        if self.provider not in PROVIDER_DEFAULT_MODELS:
            issues.append(f"Unknown provider '{self.provider}'")
        if self.provider != "ollama" and not self.api_key:
            env_var = PROVIDER_ENV_VARS.get(self.provider, "")
            issues.append(f"No API key for {self.provider} (set {env_var} or KYROZEN_API_KEY)")
        return issues

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _detect_provider_from_env() -> tuple[str, str]:
    """Detect provider and API key from environment variables."""
    provider = os.environ.get("KYROZEN_PROVIDER", "").strip().lower()
    api_key = os.environ.get("KYROZEN_API_KEY", "")

    if not provider:
        for name, env_var in PROVIDER_ENV_VARS.items():
            if env_var and os.environ.get(env_var):
                provider = name
                if not api_key:
                    api_key = os.environ.get(env_var, "")
                break
    if not provider:
        provider = DEFAULT_PROVIDER

    if not api_key:
        env_var = PROVIDER_ENV_VARS.get(provider, "")
        if env_var:
            api_key = os.environ.get(env_var, "")

    return provider, api_key


def _load_config_file(path: str) -> dict[str, Any]:
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        return {}
    try:
        with open(expanded, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_config(
    provider: str | None = None,
    api_key: str | None = None,
    config_path: str = "~/.kyrozen_config.json",
) -> KyrozenConfig:
    """Build a KyrozenConfig from env, file, and optional overrides."""
    env_provider, env_api_key = _detect_provider_from_env()
    file_data = _load_config_file(config_path)

    final_provider = provider or os.environ.get("KYROZEN_PROVIDER", "") or file_data.get("provider", "") or env_provider
    final_api_key = api_key or os.environ.get("KYROZEN_API_KEY", "") or file_data.get("api_key", "") or env_api_key

    base_url = os.environ.get("KYROZEN_BASE_URL", "") or file_data.get("base_url", "")
    permission_mode = os.environ.get("KYROZEN_PERMISSION_MODE", "") or file_data.get("permission_mode", "strict")

    return KyrozenConfig(
        provider=final_provider,
        api_key=final_api_key,
        base_url=base_url,
        model_simple=file_data.get("model_simple", ""),
        model_complex=file_data.get("model_complex", ""),
        permission_mode=permission_mode or "strict",
        workspace_root=os.environ.get("KYROZEN_WORKSPACE", ".") or file_data.get("workspace_root", "."),
        log_level=os.environ.get("KYROZEN_LOG_LEVEL", "INFO"),
        memory_backend=file_data.get("memory_backend", "memory"),
        chroma_path=file_data.get("chroma_path", "./chroma_memory"),
        task_store_path=file_data.get("task_store_path", "./kyrozen_tasks.json"),
        config_path=config_path,
    )
