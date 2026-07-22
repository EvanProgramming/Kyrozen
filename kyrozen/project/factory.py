"""Database backend factory for Kyrozen."""

from __future__ import annotations

from kyrozen.config import KyrozenConfig

from .db import KyrozenDatabase
from .supabase_db import SupabaseDatabase


def create_database(config: KyrozenConfig) -> KyrozenDatabase | SupabaseDatabase:
    """Return the configured database backend."""
    if (
        config.db_backend == "supabase"
        and config.supabase_url
        and config.supabase_service_role_key
    ):
        return SupabaseDatabase(config)
    return KyrozenDatabase(config.db_path)
