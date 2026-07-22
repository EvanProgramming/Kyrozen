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


def _load_dotenv() -> None:
    """Load environment variables from project root .env file if available."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # Search upward from the current working directory for a .env file.
    cwd = Path(os.getcwd()).resolve()
    for path in [cwd, *cwd.parents]:
        env_file = path / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)
            break


_load_dotenv()


DEFAULT_PROVIDER = "deepseek"


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in ("true", "1", "yes", "on")

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
    db_path: str = ""
    projects_dir: str = ""
    config_path: str = field(default="~/.kyrozen_config.json", repr=False)
    # Phase 4 research provider API keys
    tavily_api_key: str = ""
    serper_api_key: str = ""
    github_token: str = ""
    semantic_scholar_api_key: str = ""
    # Phase 10 productization
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    db_backend: str = "sqlite"  # "sqlite" or "supabase"
    beta_invite_only: bool = False
    cors_origins: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.model_simple:
            self.model_simple = PROVIDER_DEFAULT_MODELS.get(self.provider, ("", ""))[0]
        if not self.model_complex:
            self.model_complex = PROVIDER_DEFAULT_MODELS.get(self.provider, ("", ""))[1]
        if not self.base_url:
            self.base_url = PROVIDER_BASE_URLS.get(self.provider, "")
        self.workspace_root = os.path.abspath(os.path.expanduser(self.workspace_root))
        if not self.db_path:
            self.db_path = os.path.join(self.workspace_root, "kyrozen.db")
        if not self.projects_dir:
            self.projects_dir = os.path.join(self.workspace_root, "projects")
        if not self.cors_origins:
            raw = os.environ.get("KYROZEN_CORS_ORIGINS", "")
            self.cors_origins = [o.strip() for o in raw.split(",") if o.strip()]

    def project_dir(self, project_id: str) -> str:
        return os.path.join(self.projects_dir, project_id)

    def project_memory_path(self, project_id: str) -> str:
        return os.path.join(self.project_dir(project_id), "memory.json")

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

    final_provider = provider or os.environ.get("KYROZEN_PROVIDER", "") or env_provider or file_data.get("provider", "")
    final_api_key = api_key or os.environ.get("KYROZEN_API_KEY", "") or env_api_key or file_data.get("api_key", "")

    base_url = os.environ.get("KYROZEN_BASE_URL", "") or file_data.get("base_url", "")
    permission_mode = os.environ.get("KYROZEN_PERMISSION_MODE", "") or file_data.get("permission_mode", "strict")

    workspace_root = os.environ.get("KYROZEN_WORKSPACE", ".") or file_data.get("workspace_root", ".")
    return KyrozenConfig(
        provider=final_provider,
        api_key=final_api_key,
        base_url=base_url,
        model_simple=file_data.get("model_simple", ""),
        model_complex=file_data.get("model_complex", ""),
        permission_mode=permission_mode or "strict",
        workspace_root=workspace_root,
        log_level=os.environ.get("KYROZEN_LOG_LEVEL", "INFO"),
        memory_backend=file_data.get("memory_backend", "memory"),
        chroma_path=file_data.get("chroma_path", "./chroma_memory"),
        task_store_path=file_data.get("task_store_path", "./kyrozen_tasks.json"),
        db_path=os.environ.get("KYROZEN_DB_PATH", "") or file_data.get("db_path", ""),
        projects_dir=os.environ.get("KYROZEN_PROJECTS_DIR", "") or file_data.get("projects_dir", ""),
        config_path=config_path,
        tavily_api_key=os.environ.get("TAVILY_API_KEY", "") or file_data.get("tavily_api_key", ""),
        serper_api_key=os.environ.get("SERPER_API_KEY", "") or file_data.get("serper_api_key", ""),
        github_token=os.environ.get("GITHUB_TOKEN", "") or file_data.get("github_token", ""),
        semantic_scholar_api_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        or file_data.get("semantic_scholar_api_key", ""),
        supabase_url=os.environ.get("SUPABASE_URL", "") or file_data.get("supabase_url", ""),
        supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", "") or file_data.get("supabase_anon_key", ""),
        supabase_service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        or file_data.get("supabase_service_role_key", ""),
        supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET", "") or file_data.get("supabase_jwt_secret", ""),
        db_backend=os.environ.get("KYROZEN_DB_BACKEND", "") or file_data.get("db_backend", "sqlite"),
        beta_invite_only=_parse_bool(
            os.environ.get("KYROZEN_BETA_INVITE_ONLY", "")
            or file_data.get("beta_invite_only", "false")
        ),
        cors_origins=[o.strip() for o in (os.environ.get("KYROZEN_CORS_ORIGINS", "") or file_data.get("cors_origins", "")).split(",") if o.strip()],
    )
