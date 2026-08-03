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
    "groq": "GROQ_API_KEY",
    "omniroute": "OMNIROUTE_API_KEY",
    "ollama": "",
}

PROVIDER_DEFAULT_MODELS: dict[str, tuple[str, str]] = {
    "deepseek": ("deepseek-chat", "deepseek-reasoner"),
    "openai": ("gpt-4o", "gpt-4o"),
    "anthropic": ("claude-sonnet-4-20250514", "claude-sonnet-4-20250514"),
    "google": ("gemini-2.0-flash", "gemini-2.0-flash"),
    "groq": ("llama-3.3-70b-versatile", "llama-3.3-70b-versatile"),
    "omniroute": ("auto", "auto"),
    "ollama": ("llama3.2", "llama3.2"),
    "multi": ("auto", "auto"),
    "mock": ("mock", "mock"),  # test-only; suppresses validation noise in E2E
}

PROVIDER_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "google": "",
    "groq": "https://api.groq.com/openai/v1",
    "omniroute": "http://localhost:20128/v1",
    "ollama": "http://localhost:11434/v1",
}


# Approximate cost per 1M tokens (input, output) in USD.
# These defaults are estimates; override via KYROZEN_PROVIDER_COSTS env var.
DEFAULT_PROVIDER_COSTS: dict[str, tuple[float, float]] = {
    # DeepSeek V4 Pro list price: uncached input/output USD per 1M tokens.
    # Cache-hit input is handled separately by MembershipService.
    "deepseek": (0.435, 0.87),
    "openai": (2.50, 10.00),
    "anthropic": (3.00, 15.00),
    "google": (0.15, 0.60),
    "ollama": (0.0, 0.0),
}


def _load_provider_costs() -> dict[str, tuple[float, float]]:
    """Load provider cost overrides from KYROZEN_PROVIDER_COSTS JSON env var."""
    raw = os.environ.get("KYROZEN_PROVIDER_COSTS", "")
    if not raw:
        return dict(DEFAULT_PROVIDER_COSTS)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return dict(DEFAULT_PROVIDER_COSTS)
        costs: dict[str, tuple[float, float]] = {}
        for provider, value in parsed.items():
            if isinstance(value, (list, tuple)) and len(value) == 2:
                costs[provider] = (float(value[0]), float(value[1]))
        if costs:
            merged = dict(DEFAULT_PROVIDER_COSTS)
            merged.update(costs)
            return merged
    except (json.JSONDecodeError, ValueError):
        pass
    return dict(DEFAULT_PROVIDER_COSTS)


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
    # Deployment-configured endpoints for providers without one universally
    # safe public API. These are URLs, not credentials.
    patent_search_url: str = ""
    crowdfunding_search_url: str = ""
    # Phase 10 productization
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    db_backend: str = "sqlite"  # "sqlite", "postgres", or "supabase"
    postgres_dsn: str = ""  # e.g. postgresql://user:pass@localhost:5432/kyrozen
    beta_invite_only: bool = False
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    github_oauth_redirect_uri: str = ""
    # Afdian payment integration. Secrets are intentionally environment-only
    # in production; plan IDs are safe to expose in server responses.
    afdian_client_id: str = ""
    afdian_client_secret: str = ""
    afdian_open_user_id: str = ""
    afdian_open_api_token: str = ""
    afdian_plan_id_lite: str = ""
    afdian_plan_id_pro: str = ""
    afdian_plan_id_ultimate: str = ""
    afdian_webhook_public_url: str = ""
    afdian_oauth_redirect_uri: str = ""
    afdian_oauth_authorize_url: str = "https://afdian.net/oauth2/authorize"
    afdian_checkout_url_template: str = "https://afdian.com/a/Kyrozen/plan?plan_id={plan_id}"
    afdian_api_base_url: str = "https://afdian.net/api"
    cors_origins: list[str] = field(default_factory=list)
    provider_costs: dict[str, tuple[float, float]] = field(default_factory=dict)
    membership_usd_to_rmb: float = 7.3
    desktop_quota_default_limit: int = 0  # 0 means unlimited; positive value enforces token quota
    free_project_limit: int = 1
    # Paid membership is intentionally disabled for the first beta release.
    # Keep the policy tables and payment integration available for a later
    # release, but do not grant paid entitlements while this flag is false.
    membership_enabled: bool = False
    developer_user_ids: list[str] = field(default_factory=list)
    developer_github_users: list[str] = field(default_factory=lambda: ["EvanProgramming"])

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
        if not self.provider_costs:
            self.provider_costs = _load_provider_costs()

    def project_dir(self, project_id: str) -> str:
        return os.path.join(self.projects_dir, project_id)

    def project_memory_path(self, project_id: str) -> str:
        return os.path.join(self.project_dir(project_id), "memory.json")

    def validate(self) -> list[str]:
        """Return a list of validation issues."""
        issues: list[str] = []
        if self.provider not in PROVIDER_DEFAULT_MODELS:
            issues.append(f"Unknown provider '{self.provider}'")
        if self.provider not in ("ollama", "multi") and not self.api_key:
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
        task_store_path=os.environ.get("KYROZEN_TASK_STORE_PATH", "")
        or file_data.get("task_store_path", "./kyrozen_tasks.json"),
        db_path=os.environ.get("KYROZEN_DB_PATH", "") or file_data.get("db_path", ""),
        projects_dir=os.environ.get("KYROZEN_PROJECTS_DIR", "") or file_data.get("projects_dir", ""),
        config_path=config_path,
        tavily_api_key=os.environ.get("TAVILY_API_KEY", "") or file_data.get("tavily_api_key", ""),
        serper_api_key=os.environ.get("SERPER_API_KEY", "") or file_data.get("serper_api_key", ""),
        github_token=os.environ.get("GITHUB_TOKEN", "") or file_data.get("github_token", ""),
        semantic_scholar_api_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        or file_data.get("semantic_scholar_api_key", ""),
        patent_search_url=os.environ.get("PATENT_SEARCH_URL", "")
        or file_data.get("patent_search_url", ""),
        crowdfunding_search_url=os.environ.get("CROWDFUNDING_SEARCH_URL", "")
        or file_data.get("crowdfunding_search_url", ""),
        supabase_url=os.environ.get("SUPABASE_URL", "") or file_data.get("supabase_url", ""),
        supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", "") or file_data.get("supabase_anon_key", ""),
        supabase_service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        or file_data.get("supabase_service_role_key", ""),
        supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET", "") or file_data.get("supabase_jwt_secret", ""),
        db_backend=os.environ.get("KYROZEN_DB_BACKEND", "") or file_data.get("db_backend", "sqlite"),
        postgres_dsn=os.environ.get("KYROZEN_POSTGRES_DSN", "") or file_data.get("postgres_dsn", ""),
        beta_invite_only=_parse_bool(
            os.environ.get("KYROZEN_BETA_INVITE_ONLY", "")
            or file_data.get("beta_invite_only", "false")
        ),
        github_oauth_client_id=os.environ.get("GITHUB_OAUTH_CLIENT_ID", "") or file_data.get("github_oauth_client_id", ""),
        github_oauth_client_secret=os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", "") or file_data.get("github_oauth_client_secret", ""),
        github_oauth_redirect_uri=os.environ.get("GITHUB_OAUTH_REDIRECT_URI", "") or file_data.get("github_oauth_redirect_uri", ""),
        afdian_client_id=os.environ.get("AFDIAN_CLIENT_ID", "") or file_data.get("afdian_client_id", ""),
        afdian_client_secret=os.environ.get("AFDIAN_CLIENT_SECRET", "") or file_data.get("afdian_client_secret", ""),
        afdian_open_user_id=os.environ.get("AFDIAN_OPEN_USER_ID", "") or file_data.get("afdian_open_user_id", ""),
        afdian_open_api_token=os.environ.get("AFDIAN_OPEN_API_TOKEN", "") or file_data.get("afdian_open_api_token", ""),
        afdian_plan_id_lite=os.environ.get("AFDIAN_PLAN_ID_LITE", "") or file_data.get("afdian_plan_id_lite", ""),
        afdian_plan_id_pro=os.environ.get("AFDIAN_PLAN_ID_PRO", "") or file_data.get("afdian_plan_id_pro", ""),
        afdian_plan_id_ultimate=os.environ.get("AFDIAN_PLAN_ID_ULTIMATE", "") or file_data.get("afdian_plan_id_ultimate", ""),
        afdian_webhook_public_url=os.environ.get("AFDIAN_WEBHOOK_PUBLIC_URL", "") or file_data.get("afdian_webhook_public_url", ""),
        afdian_oauth_redirect_uri=os.environ.get("AFDIAN_OAUTH_REDIRECT_URI", "") or file_data.get("afdian_oauth_redirect_uri", ""),
        afdian_oauth_authorize_url=os.environ.get("AFDIAN_OAUTH_AUTHORIZE_URL", "") or file_data.get("afdian_oauth_authorize_url", "https://afdian.net/oauth2/authorize"),
        afdian_checkout_url_template=os.environ.get("AFDIAN_CHECKOUT_URL_TEMPLATE", "") or file_data.get("afdian_checkout_url_template", "https://afdian.com/a/Kyrozen/plan?plan_id={plan_id}"),
        afdian_api_base_url=os.environ.get("AFDIAN_API_BASE_URL", "") or file_data.get("afdian_api_base_url", "https://afdian.net/api"),
        cors_origins=[o.strip() for o in (os.environ.get("KYROZEN_CORS_ORIGINS", "") or file_data.get("cors_origins", "")).split(",") if o.strip()],
        membership_usd_to_rmb=float(
            os.environ.get("KYROZEN_MEMBERSHIP_USD_TO_RMB", "")
            or file_data.get("membership_usd_to_rmb", 7.3)
            or 7.3
        ),
        desktop_quota_default_limit=int(
            os.environ.get("KYROZEN_DESKTOP_QUOTA_DEFAULT_LIMIT", "")
            or file_data.get("desktop_quota_default_limit", 0)
            or 0
        ),
        free_project_limit=int(
            os.environ.get("KYROZEN_FREE_PROJECT_LIMIT", "")
            or file_data.get("free_project_limit", 1)
            or 1
        ),
        membership_enabled=(
            str(os.environ.get("KYROZEN_MEMBERSHIP_ENABLED", file_data.get("membership_enabled", False))).lower()
            in {"1", "true", "yes", "on"}
        ),
        developer_user_ids=[
            item.strip() for item in (
                os.environ.get("KYROZEN_DEVELOPER_USER_IDS", "")
                or file_data.get("developer_user_ids", "")
            ).split(",") if item.strip()
        ],
        developer_github_users=[
            item.strip() for item in (
                os.environ.get("KYROZEN_DEVELOPER_GITHUB_USERS", "")
                or file_data.get("developer_github_users", "EvanProgramming")
            ).split(",") if item.strip()
        ],
    )
