"""Tests for Kyrozen SQLite persistence."""

from __future__ import annotations

import os

from kyrozen.core.task import Task, TaskManager
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
