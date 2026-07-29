#!/usr/bin/env python3
"""Apply Kyrozen database migrations to a Postgres / Supabase database.

Usage:
    KYROZEN_POSTGRES_DSN="postgresql://postgres:<pw>@db.sjesqiocedolckqjfrls.supabase.co:5432/postgres" \
        python scripts/apply_migrations.py

    # or pass the DSN explicitly:
    python scripts/apply_migrations.py --dsn "postgresql://..."

The DSN is the Supabase **connection pooler** (or direct) Postgres address,
NOT the REST URL. It requires the `postgres` superuser password. The
migrations themselves are idempotent (IF NOT EXISTS / CREATE TABLE IF NOT
 EXISTS), so re-running is safe.

This must be run against the production database whenever a new
``migrations/*.sql`` file is added, otherwise the server refuses to start
(see kyrozen/db/schema_check.py).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"


def migration_files() -> list[Path]:
    """Return the baseline first, then numbered migrations in stable order."""
    all_sql_files = list(MIGRATIONS_DIR.glob("*.sql"))
    return sorted(
        all_sql_files,
        key=lambda path: (path.name != "supabase_schema.sql", path.name),
    )


def main() -> int:
    dsn = os.environ.get("KYROZEN_POSTGRES_DSN") or (
        sys.argv[sys.argv.index("--dsn") + 1] if "--dsn" in sys.argv else ""
    )
    if not dsn:
        print(
            "ERROR: 未提供数据库连接串。\n"
            "请设置环境变量 KYROZEN_POSTGRES_DSN 或使用 --dsn 'postgresql://...'，\n"
            "值为 Supabase 连接池 Postgres 地址（需 postgres 密码）。",
            file=sys.stderr,
        )
        return 2

    try:
        import psycopg2
    except ImportError:
        print("ERROR: 需要 psycopg2（已内置开发虚拟环境）。", file=sys.stderr)
        return 2

    # The baseline creates the tables consumed by every numbered migration.
    # Lexicographic ordering would otherwise run 001_* before the baseline on
    # a fresh database and fail on missing projects/tasks tables.
    sql_files = migration_files()
    if not sql_files:
        print(f"在 {MIGRATIONS_DIR} 未找到任何迁移文件。")
        return 0

    print(f"连接到数据库并执行 {len(sql_files)} 个迁移文件...")
    conn = psycopg2.connect(dsn)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            for sql_file in sql_files:
                sql = sql_file.read_text(encoding="utf-8")
                print(f"  -> 应用 {sql_file.name} ...")
                cur.execute(sql)
            # PostgREST may otherwise keep serving its old schema cache for a
            # short period after DDL, causing false PGRST204 responses.
            cur.execute("NOTIFY pgrst, 'reload schema'")
        conn.commit()
        print("迁移完成。")
        return 0
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print(f"迁移失败，已回滚：{exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
