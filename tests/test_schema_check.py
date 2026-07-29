"""Tests for the startup schema preflight (P0-02)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kyrozen.db.schema_check import SchemaError, verify_desktop_schema


class _ApiError(Exception):
    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _Query:
    def __init__(self, table: str, column: str, missing_cols: set[str], missing_tables: set[str]) -> None:
        self._table = table
        self._column = column
        self._missing_cols = missing_cols
        self._missing_tables = missing_tables

    def select(self, column: str) -> "_Query":
        self._column = column
        return self

    def limit(self, _n: int) -> "_Query":
        return self

    def execute(self) -> object:
        if self._table in self._missing_tables:
            raise _ApiError(
                f'Could not find the "{self._table}" relation in the schema cache',
                code="PGRST106",
            )
        if self._column in self._missing_cols:
            raise _ApiError(
                f"Could not find the '{self._column}' column of '{self._table}' in the schema cache",
                code="PGRST204",
            )
        return SimpleNamespace(data=[])


class _Client:
    def __init__(self, missing_cols: set[str] | None = None, missing_tables: set[str] | None = None) -> None:
        self._missing_cols = missing_cols or set()
        self._missing_tables = missing_tables or set()

    def table(self, name: str) -> _Query:
        return _Query(name, "", self._missing_cols, self._missing_tables)


def _config(backend: str) -> SimpleNamespace:
    return SimpleNamespace(db_backend=backend, supabase_url="", supabase_service_role_key="")


def test_sqlite_backend_skips_check():
    verify_desktop_schema(_config("sqlite"))  # no raise


def test_supabase_complete_schema_ok():
    verify_desktop_schema(_config("supabase"), client=_Client())


def test_supabase_missing_column_raises():
    with pytest.raises(SchemaError) as exc:
        verify_desktop_schema(
            _config("supabase"),
            client=_Client(missing_cols={"assigned_client_id"}),
        )
    assert "tasks.assigned_client_id" in exc.value.missing


def test_supabase_missing_table_raises():
    with pytest.raises(SchemaError) as exc:
        verify_desktop_schema(
            _config("supabase"),
            client=_Client(missing_tables={"desktop_clients"}),
        )
    assert "desktop_clients" in exc.value.missing


def test_supabase_missing_both_raises():
    with pytest.raises(SchemaError) as exc:
        verify_desktop_schema(
            _config("supabase"),
            client=_Client(missing_cols={"assigned_client_id"}, missing_tables={"desktop_clients"}),
        )
    assert set(exc.value.missing) == {"tasks.assigned_client_id", "desktop_clients"}
