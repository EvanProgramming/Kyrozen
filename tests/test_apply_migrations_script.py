from scripts import apply_migrations


def test_baseline_schema_runs_before_incremental_migrations() -> None:
    names = [path.name for path in apply_migrations.migration_files()]

    assert names[0] == "supabase_schema.sql"
    assert names[1:] == sorted(names[1:])


def test_incremental_migrations_are_safe_to_reapply() -> None:
    user_id_sql = (
        apply_migrations.MIGRATIONS_DIR / "001_add_user_id.sql"
    ).read_text(encoding="utf-8")
    chat_sql = (
        apply_migrations.MIGRATIONS_DIR / "001_add_chat_messages.sql"
    ).read_text(encoding="utf-8")

    assert user_id_sql.count("ADD COLUMN IF NOT EXISTS") == 4
    assert 'DROP POLICY IF EXISTS "Users can access their own chat messages"' in chat_sql
