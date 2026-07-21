"""Tests for Project API endpoints."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
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

    del_res = api_client.delete(f"/api/projects/{pid}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "archived"


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
