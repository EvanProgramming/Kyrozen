"""Tests for Project Workspace models and manager."""

from __future__ import annotations

import os

import pytest

from kyrozen.project import Artifact, Decision, Project, ProjectManager
from kyrozen.project.db import KyrozenDatabase
from kyrozen.project.project import PROJECT_STATUSES, PROJECT_STAGES


def test_project_default_fields():
    p = Project(name="Test Project")
    assert p.name == "Test Project"
    assert p.status == "active"
    assert p.current_stage == "problem_discovery"
    assert p.id.startswith("proj_")
    assert p.created_at
    assert p.updated_at


def test_project_invalid_status():
    with pytest.raises(ValueError):
        Project(name="X", status="unknown")


def test_project_invalid_stage():
    with pytest.raises(ValueError):
        Project(name="X", current_stage="shipping")


def test_project_update_refreshes_timestamp():
    p = Project(name="X")
    old_updated = p.updated_at
    p.update(goal="Build something")
    assert p.goal == "Build something"
    assert p.updated_at > old_updated


def test_project_update_invalid_field():
    p = Project(name="X")
    with pytest.raises(ValueError):
        p.update(owner="me")


def test_project_to_from_dict():
    p = Project(name="X", goal="G", status="paused", current_stage="solution_design")
    data = p.to_dict()
    p2 = Project.from_dict(data)
    assert p2.name == p.name
    assert p2.goal == p.goal
    assert p2.status == p.status
    assert p2.current_stage == p.current_stage


def test_decision_to_from_dict():
    d = Decision(
        project_id="proj_1",
        decision="Use ESP32",
        reason="Need WiFi and BLE",
        alternatives=["Arduino Uno"],
        rejected_reasons={"Arduino Uno": "性能不足"},
    )
    data = d.to_dict()
    d2 = Decision.from_dict(data)
    assert d2.decision == d.decision
    assert d2.reason == d.reason
    assert d2.alternatives == d.alternatives
    assert d2.rejected_reasons == d.rejected_reasons


def test_artifact_version_bump():
    a = Artifact(project_id="proj_1", type="PRD", title="Product Brief", content="v1")
    a2 = a.bump_version("v2", change_reason="Added scope")
    assert a2.version == 2
    assert a2.content == "v2"
    assert a2.change_reason == "Added scope"
    assert a2.id != a.id


def test_project_manager_crud(temp_dir: str):
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    pm = ProjectManager(db)

    p = pm.create(name="智能跑步设备", initial_idea="Improve running music", goal="改善运动音乐体验")
    assert p.name == "智能跑步设备"
    assert p.goal == "改善运动音乐体验"
    assert p.description == "Improve running music"

    fetched = pm.get(p.id)
    assert fetched is not None
    assert fetched.name == p.name

    updated = pm.update(p.id, current_stage="product_definition", next_steps="Define MVP")
    assert updated is not None
    assert updated.current_stage == "product_definition"
    assert updated.next_steps == "Define MVP"

    projects = pm.list()
    assert len(projects) == 1

    archived = pm.archive(p.id)
    assert archived is not None
    assert archived.status == "archived"


def test_project_manager_restore(temp_dir: str):
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    pm = ProjectManager(db)

    p = pm.create(name="Restore Me")
    archived = pm.archive(p.id)
    assert archived is not None
    assert archived.status == "archived"

    restored = pm.restore(p.id)
    assert restored is not None
    assert restored.status == "active"
    assert pm.get(p.id).status == "active"

    # Restoring a non-archived project should fail
    assert pm.restore(p.id) is None


def test_project_manager_delete(temp_dir: str):
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    pm = ProjectManager(db)

    p = pm.create(name="Delete Me")
    assert pm.get(p.id) is not None

    deleted = pm.delete(p.id)
    assert deleted is True
    assert pm.get(p.id) is None
    assert pm.list() == []

    # Deleting a non-existent project returns False
    assert pm.delete("nonexistent") is False


def test_project_manager_decisions(temp_dir: str):
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    pm = ProjectManager(db)
    p = pm.create(name="D", goal="G")

    dec = pm.add_decision(
        p.id,
        decision="Use ESP32-S3",
        reason="Need WiFi and BLE",
        alternatives=["Arduino Uno"],
        rejected_reasons={"Arduino Uno": "性能不足"},
    )
    assert dec.project_id == p.id
    assert dec.decision == "Use ESP32-S3"

    decisions = pm.list_decisions(p.id)
    assert len(decisions) == 1
    assert decisions[0].decision == "Use ESP32-S3"


def test_project_manager_artifacts_versioning(temp_dir: str):
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    pm = ProjectManager(db)
    p = pm.create(name="A", goal="G")

    a1 = pm.save_artifact(p.id, "PRD", "Product Brief", "First draft", "Initial")
    a2 = pm.save_artifact(p.id, "PRD", "Product Brief", "Second draft", "Scope update")

    assert a1.id != a2.id
    assert a2.version == 2

    artifacts = pm.list_artifacts(p.id)
    assert len(artifacts) == 2


def test_project_manager_isolation(temp_dir: str):
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    pm = ProjectManager(db)
    p1 = pm.create(name="P1")
    p2 = pm.create(name="P2")

    pm.add_decision(p1.id, decision="D1", reason="R1")
    pm.add_decision(p2.id, decision="D2", reason="R2")

    assert len(pm.list_decisions(p1.id)) == 1
    assert pm.list_decisions(p1.id)[0].decision == "D1"
    assert len(pm.list_decisions(p2.id)) == 1
    assert pm.list_decisions(p2.id)[0].decision == "D2"
