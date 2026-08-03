"""Tests for Kyrozen SQLite persistence."""

from __future__ import annotations

import os

from kyrozen.core.task import Task, TaskManager
from kyrozen.desktop.models import DesktopClient
from kyrozen.project import Project
from kyrozen.project.db import KyrozenDatabase


def test_database_creates_file(temp_dir: str):
    db_path = os.path.join(temp_dir, "kyrozen.db")
    db = KyrozenDatabase(db_path)
    assert os.path.exists(db_path)
    db.close()


def test_project_persistence(temp_dir: str):
    db_path = os.path.join(temp_dir, "kyrozen.db")
    db1 = KyrozenDatabase(db_path)
    p = Project(name="Persisted", goal="G", current_stage="market_research")
    db1.save_project(p)

    db2 = KyrozenDatabase(db_path)
    fetched = db2.get_project(p.id)
    assert fetched is not None
    assert fetched.name == "Persisted"
    assert fetched.goal == "G"
    assert fetched.current_stage == "market_research"


def test_legacy_stage_aliases_restore_into_phase2_workflow():
    assert Project.from_dict({"name": "Legacy discovery", "current_stage": "discovery"}).current_stage == "problem_discovery"
    assert Project.from_dict({"name": "Legacy planning", "current_stage": "planning"}).current_stage == "product_definition"
    assert Project.from_dict({"name": "Legacy learning", "current_stage": "learning"}).current_stage == "iteration"
    assert Project.from_dict({"name": "Legacy hardware", "current_stage": "hardware_development"}).current_stage == "development"
    assert Project.from_dict({"name": "Embedded hardware", "project_type": "embedded", "current_stage": "hardware_development"}).current_stage == "hardware_design"


def test_task_persistence_with_project_id(temp_dir: str):
    db_path = os.path.join(temp_dir, "kyrozen.db")
    db = KyrozenDatabase(db_path)
    from kyrozen.project import ProjectManager

    pm = ProjectManager(db)
    project = pm.create(name="TaskTest", goal="G")

    pm_task = TaskManager(db=db)
    task = pm_task.create(title="Research sensors", description="Find sensors", project_id=project.id)
    task.update_status("running")
    pm_task.update(task)

    loaded = pm_task.get(task.id)
    assert loaded is not None
    assert loaded.project_id == project.id
    assert loaded.status == "running"

    tasks = pm_task.list_tasks(project_id=project.id)
    assert len(tasks) == 1
    assert tasks[0].id == task.id


def test_cascade_delete_project(temp_dir: str):
    db_path = os.path.join(temp_dir, "kyrozen.db")
    db = KyrozenDatabase(db_path)
    p = Project(name="ToDelete")
    db.save_project(p)

    from kyrozen.project import ProjectManager

    pm = ProjectManager(db)
    pm.add_decision(p.id, decision="D", reason="R")

    db.delete_project(p.id)
    assert db.get_project(p.id) is None
    assert len(db.list_decisions(p.id)) == 0


def test_desktop_client_model_persists_without_key_translation(temp_dir: str):
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    client = DesktopClient(user_id="user-1", device_name="Test Mac")

    db.save_desktop_client(client.to_dict())

    stored = db.get_desktop_client(client.client_id)
    assert stored is not None
    assert stored["id"] == client.client_id
    assert stored["device_name"] == "Test Mac"


def test_phase2_project_fields_round_trip_through_postgres_and_supabase_adapters():
    """Exercise both remote row adapters without requiring live credentials."""
    from kyrozen.project.postgres_db import PostgresDatabase, SCHEMA_SQL
    from kyrozen.project.supabase_db import SupabaseDatabase

    for column in ("budget", "project_type", "workflow_version", "type_source", "type_confidence", "type_confirmed"):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in SCHEMA_SQL

    row = {
        "id": "p-phase2",
        "user_id": "u1",
        "name": "Phase 2",
        "description": "",
        "goal": "",
        "status": "active",
        "current_stage": "problem_discovery",
        "next_steps": "",
        "blocked_reason": "",
        "progress": 0,
        "risks": [],
        "project_type": "hybrid",
        "workflow_version": "phase2.v1",
        "type_source": "user_confirmed",
        "type_confidence": "high",
        "type_confirmed": True,
        "created_at": "2026-08-03T00:00:00+00:00",
        "updated_at": "2026-08-03T00:00:00+00:00",
    }
    postgres_project = PostgresDatabase._row_to_project(object.__new__(PostgresDatabase), row)
    supabase_project = SupabaseDatabase._row_to_project(object.__new__(SupabaseDatabase), row)
    for project in (postgres_project, supabase_project):
        assert project.project_type == "hybrid"
        assert project.workflow_version == "phase2.v1"
        assert project.type_source == "user_confirmed"
        assert project.type_confidence == "high"
        assert project.type_confirmed is True

    legacy = {key: value for key, value in row.items() if key not in {"project_type", "workflow_version", "type_source", "type_confidence", "type_confirmed"}}
    for project in (
        PostgresDatabase._row_to_project(object.__new__(PostgresDatabase), legacy),
        SupabaseDatabase._row_to_project(object.__new__(SupabaseDatabase), legacy),
    ):
        assert project.project_type == "software"
        assert project.workflow_version == "phase2.v1"
        assert project.type_confirmed is False
