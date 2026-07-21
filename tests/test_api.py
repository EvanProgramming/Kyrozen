"""Tests for the FastAPI REST API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app

from .conftest import MockModel


@pytest.fixture
def client(test_config):
    app = create_app(config=test_config, model=MockModel())
    with TestClient(app) as c:
        yield c


def test_index_serves_ui(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Kyrozen Core" in response.text


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["provider"] == "mock"


def test_config_endpoint(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "mock"
    assert data["permission_mode"] == "permissive"


def test_list_tools(client):
    response = client.get("/api/tools")
    assert response.status_code == 200
    data = response.json()
    names = {t["name"] for t in data["tools"]}
    assert "file_read" in names
    assert "terminal" in names


def test_execute_tool(client):
    response = client.post("/api/tools/execute", json={
        "tool": "terminal",
        "action": "execute",
        "parameters": {"command": "echo api-test"}
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"]
    assert "api-test" in data["data"]["output"]


def test_chat_direct_answer(client, test_config):
    test_config.permission_mode = "permissive"
    app = create_app(config=test_config, model=MockModel(["Final answer from API."]))
    with TestClient(app) as c:
        response = c.post("/api/chat", json={"message": "Hello"})
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "completed"

        task_response = c.get(f"/api/tasks/{data['task_id']}")
        assert task_response.status_code == 200
        task = task_response.json()
        assert task["result"]["answer"] == "Final answer from API."


def test_chat_waiting_confirmation(client, test_config):
    test_config.permission_mode = "strict"
    tool_call = '{"tool": "file_write", "action": "write", "parameters": {"path": "x.txt", "content": "x"}}'
    app = create_app(config=test_config, model=MockModel([tool_call, "File written."]))
    with TestClient(app) as c:
        response = c.post("/api/chat", json={"message": "Write file"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "waiting_confirmation"

        confirm = c.post(f"/api/tasks/{data['task_id']}/confirm", json={"confirmed": True})
        assert confirm.status_code == 200
        task = confirm.json()
        assert task["status"] == "completed"
        assert task["result"]["answer"] == "File written."


def test_confirm_decline(client, test_config):
    test_config.permission_mode = "strict"
    tool_call = '{"tool": "file_write", "action": "write", "parameters": {"path": "x.txt", "content": "x"}}'
    app = create_app(config=test_config, model=MockModel([tool_call]))
    with TestClient(app) as c:
        response = c.post("/api/chat", json={"message": "Write file"})
        task_id = response.json()["task_id"]
        confirm = c.post(f"/api/tasks/{task_id}/confirm", json={"confirmed": False})
        assert confirm.status_code == 200
        task = confirm.json()
        assert task["status"] == "failed"


def test_list_tasks(client):
    response = client.get("/api/tasks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
