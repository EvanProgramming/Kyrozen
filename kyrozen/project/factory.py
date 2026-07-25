"""Database backend factory for Kyrozen."""

from __future__ import annotations

from kyrozen.config import KyrozenConfig

from .db import KyrozenDatabase
from .postgres_db import PostgresDatabase
from .supabase_db import SupabaseDatabase


def create_database(config: KyrozenConfig) -> KyrozenDatabase | PostgresDatabase | SupabaseDatabase:
    """Return the configured database backend."""
    if config.db_backend == "postgres" and config.postgres_dsn:
        return PostgresDatabase(config.postgres_dsn)
    if (
        config.db_backend == "supabase"
        and config.supabase_url
        and config.supabase_service_role_key
    ):
        return SupabaseDatabase(config)
    return KyrozenDatabase(config.db_path)
