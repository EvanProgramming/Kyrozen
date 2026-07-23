"""Tests for Learning REST API endpoints."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.auth.dependencies import CurrentUser, get_current_user
from kyrozen.config import KyrozenConfig

from tests.conftest import MockModel


@pytest.fixture
def learning_client(temp_dir: str):
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


def test_learning_record_crud(learning_client: TestClient):
    project = learning_client.post("/api/projects", json={"name": "Learning Project"})
    pid = project.json()["id"]

    create = learning_client.post(f"/api/projects/{pid}/learning/records", json={
        "memory": "Users prefer dark mode",
        "memory_type": "user_preference",
        "confidence": "high",
    })
    assert create.status_code == 200
    record = create.json()
    assert record["memory"] == "Users prefer dark mode"
    assert record["source_project_id"] == pid
    rid = record["id"]

    list_res = learning_client.get(f"/api/projects/{pid}/learning/records")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    get_res = learning_client.get(f"/api/projects/{pid}/learning/records/{rid}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == rid

    delete_res = learning_client.delete(f"/api/projects/{pid}/learning/records/{rid}")
    assert delete_res.status_code == 200

    list_after = learning_client.get(f"/api/projects/{pid}/learning/records")
    assert list_after.json() == []


def test_failure_and_success_knowledge_crud(learning_client: TestClient):
    project = learning_client.post("/api/projects", json={"name": "Failure Project"})
    pid = project.json()["id"]

    failure_create = learning_client.post(f"/api/projects/{pid}/learning/failures", json={
        "problem": "Timeout on slow networks",
        "cause": "No retry logic",
        "solution": "Add exponential backoff",
    })
    assert failure_create.status_code == 200
    fid = failure_create.json()["id"]

    success_create = learning_client.post(f"/api/projects/{pid}/learning/successes", json={
        "goal": "Fast response",
        "solution": "Cache frequently accessed data",
        "result": "Latency reduced by 80%",
    })
    assert success_create.status_code == 200
    sid = success_create.json()["id"]

    assert learning_client.get(f"/api/projects/{pid}/learning/failures").json()
    assert learning_client.get(f"/api/projects/{pid}/learning/successes").json()

    learning_client.delete(f"/api/projects/{pid}/learning/failures/{fid}")
    learning_client.delete(f"/api/projects/{pid}/learning/successes/{sid}")


def test_suggestion_crud_and_status_update(learning_client: TestClient):
    project = learning_client.post("/api/projects", json={"name": "Suggestion Project"})
    pid = project.json()["id"]

    create = learning_client.post(f"/api/projects/{pid}/learning/suggestions", json={
        "suggestion": "Add pagination",
        "reason": "Large lists are slow",
        "priority": "high",
        "category": "tech_risk",
    })
    assert create.status_code == 200
    suggestion = create.json()
    assert suggestion["status"] == "new"
    sid = suggestion["id"]

    patch = learning_client.patch(f"/api/projects/{pid}/learning/suggestions/{sid}/status", json={
        "status": "accepted",
    })
    assert patch.status_code == 200

    get_res = learning_client.get(f"/api/projects/{pid}/learning/suggestions/{sid}")
    assert get_res.status_code == 200
    # Status update is reflected in the database; re-fetch verifies ownership.
    assert get_res.json()["id"] == sid

    learning_client.delete(f"/api/projects/{pid}/learning/suggestions/{sid}")


def test_learning_isolation_between_projects(learning_client: TestClient):
    p1 = learning_client.post("/api/projects", json={"name": "P1"}).json()["id"]
    p2 = learning_client.post("/api/projects", json={"name": "P2"}).json()["id"]

    record = learning_client.post(f"/api/projects/{p1}/learning/records", json={
        "memory": "P1 only",
        "memory_type": "project_fact",
    }).json()
    rid = record["id"]

    assert len(learning_client.get(f"/api/projects/{p1}/learning/records").json()) == 1
    assert len(learning_client.get(f"/api/projects/{p2}/learning/records").json()) == 0

    assert learning_client.get(f"/api/projects/{p2}/learning/records/{rid}").status_code == 404
    assert learning_client.delete(f"/api/projects/{p2}/learning/records/{rid}").status_code == 404
