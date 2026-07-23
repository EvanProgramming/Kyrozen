"""Tests for Project API endpoints."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.auth.dependencies import CurrentUser, get_current_user
from kyrozen.config import KyrozenConfig

from tests.conftest import MockModel


@pytest.fixture
def api_client(temp_dir: str):
    config = KyrozenConfig(
        provider="mock",
        api_key="test-key",
        permission_mode="permissive",
        workspace_root=temp_dir,
        log_level="ERROR",
        task_store_path=os.path.join(temp_dir, "tasks.json"),
    )
    app = create_app(config=config, model=MockModel(["Done"]))
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id="test-user-1",
        email="test@example.com",
        name="Test",
        role="user",
    )
    with TestClient(app) as client:
        yield client


def test_create_project(api_client: TestClient):
    res = api_client.post("/api/projects", json={
        "name": "智能跑步设备",
        "goal": "改善运动音乐体验",
        "description": "AI music device for runners",
        "initial_idea": "AI music device for runners",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "智能跑步设备"
    assert data["goal"] == "改善运动音乐体验"
    assert data["id"].startswith("proj_")


def test_list_and_get_project(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "P1", "goal": "G1"})
    pid = create.json()["id"]

    list_res = api_client.get("/api/projects")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    get_res = api_client.get(f"/api/projects/{pid}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["name"] == "P1"
    assert "recent_tasks" in data
    assert "recent_decisions" in data
    assert "recent_artifacts" in data


def test_update_and_archive_project(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "P2"})
    pid = create.json()["id"]

    put_res = api_client.put(f"/api/projects/{pid}", json={
        "status": "paused",
        "current_stage": "product_definition",
        "next_steps": "Define MVP",
    })
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["status"] == "paused"
    assert data["current_stage"] == "product_definition"
    assert data["next_steps"] == "Define MVP"

    archive_res = api_client.post(f"/api/projects/{pid}/archive", json={})
    assert archive_res.status_code == 200
    assert archive_res.json()["status"] == "archived"


def test_rename_project(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Original Name"})
    pid = create.json()["id"]

    rename_res = api_client.put(f"/api/projects/{pid}", json={"name": "Renamed Project"})
    assert rename_res.status_code == 200
    assert rename_res.json()["name"] == "Renamed Project"

    get_res = api_client.get(f"/api/projects/{pid}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Renamed Project"


def test_advance_project_stage_order(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Advance"})
    pid = create.json()["id"]
    assert create.json()["current_stage"] == "problem_discovery"

    expected_order = [
        "market_research",
        "product_definition",
        "solution_design",
        "development",
        "testing",
        "iteration",
    ]
    for expected_stage in expected_order:
        advance_res = api_client.post(f"/api/projects/{pid}/advance", json={})
        assert advance_res.status_code == 200
        assert advance_res.json()["current_stage"] == expected_stage

    # Final advance marks project completed
    final_res = api_client.post(f"/api/projects/{pid}/advance", json={})
    assert final_res.status_code == 200
    assert final_res.json()["status"] == "completed"
    assert final_res.json()["progress"] == 100


def test_restore_and_delete_project(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "P2-delete"})
    pid = create.json()["id"]

    archive_res = api_client.post(f"/api/projects/{pid}/archive", json={})
    assert archive_res.status_code == 200
    assert archive_res.json()["status"] == "archived"

    restore_res = api_client.post(f"/api/projects/{pid}/restore", json={})
    assert restore_res.status_code == 200
    assert restore_res.json()["status"] == "active"

    delete_res = api_client.delete(f"/api/projects/{pid}")
    assert delete_res.status_code == 200
    assert delete_res.json()["status"] == "deleted"

    assert api_client.get(f"/api/projects/{pid}").status_code == 404


def test_project_decisions_and_artifacts(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "P3"})
    pid = create.json()["id"]

    dec_res = api_client.post(f"/api/projects/{pid}/decisions", json={
        "decision": "Use ESP32-S3",
        "reason": "Need WiFi and BLE",
        "alternatives": ["Arduino Uno"],
        "rejected_reasons": {"Arduino Uno": "性能不足"},
    })
    assert dec_res.status_code == 200

    list_dec = api_client.get(f"/api/projects/{pid}/decisions")
    assert list_dec.status_code == 200
    assert len(list_dec.json()) == 1

    art_res = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "PRD",
        "title": "Product Brief",
        "content": "Draft",
        "change_reason": "Initial",
    })
    assert art_res.status_code == 200

    list_art = api_client.get(f"/api/projects/{pid}/artifacts")
    assert list_art.status_code == 200
    assert len(list_art.json()) == 1


def test_project_tasks_isolation(api_client: TestClient):
    c1 = api_client.post("/api/projects", json={"name": "T1"})
    pid1 = c1.json()["id"]
    c2 = api_client.post("/api/projects", json={"name": "T2"})
    pid2 = c2.json()["id"]

    api_client.post("/api/chat", json={"message": "Hello", "project_id": pid1})

    tasks1 = api_client.get(f"/api/projects/{pid1}/tasks")
    tasks2 = api_client.get(f"/api/projects/{pid2}/tasks")
    assert len(tasks1.json()) == 1
    assert len(tasks2.json()) == 0


def test_chat_with_project_context(api_client: TestClient):
    create = api_client.post("/api/projects", json={
        "name": "智能跑步设备",
        "goal": "改善运动音乐体验",
    })
    pid = create.json()["id"]

    chat_res = api_client.post("/api/chat", json={"message": "下一步怎么办？", "project_id": pid})
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert data["project_id"] == pid
    assert data["task_id"].startswith("task_")

    task_res = api_client.get(f"/api/tasks/{data['task_id']}")
    assert task_res.status_code == 200
    assert task_res.json()["project_id"] == pid


def test_chat_with_missing_project(api_client: TestClient):
    res = api_client.post("/api/chat", json={"message": "Hi", "project_id": "proj_missing"})
    assert res.status_code == 404


def test_project_user_isolation(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Private"})
    assert create.status_code == 200
    pid = create.json()["id"]

    # Switch to a different user within the same app
    api_client.app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id="test-user-2",
        email="other@example.com",
        name="Other",
        role="user",
    )
    try:
        assert api_client.get("/api/projects").json() == []
        assert api_client.get(f"/api/projects/{pid}").status_code == 404
        assert api_client.get(f"/api/projects/{pid}/state").status_code == 404
        assert api_client.post(f"/api/projects/{pid}/advance").status_code == 404
    finally:
        api_client.app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id="test-user-1",
            email="test@example.com",
            name="Test",
            role="user",
        )
