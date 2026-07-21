"""Validation tests for Phase 1/2/3: performance, security, compatibility."""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.config import KyrozenConfig
from kyrozen.memory import InMemoryMemory
from kyrozen.memory.scoped import JsonFileMemory, ProjectMemory
from kyrozen.models.providers import get_model_provider
from kyrozen.project import KyrozenDatabase, ProjectManager
from kyrozen.tools.file_tools import FileReadTool
from kyrozen.tools.terminal_tools import TerminalTool

from tests.conftest import MockModel


@pytest.fixture
def validation_client(temp_dir: str):
    config = KyrozenConfig(
        provider="mock",
        api_key="test-key",
        permission_mode="permissive",
        workspace_root=temp_dir,
        log_level="ERROR",
        task_store_path=os.path.join(temp_dir, "tasks.json"),
    )
    app = create_app(config=config, model=MockModel(["OK"]))
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# Performance tests
# ---------------------------------------------------------------------------

def test_perf_api_chat_p95(validation_client: TestClient):
    """PERF-01: /api/chat p95 response time < 200ms with mock model."""
    create = validation_client.post("/api/projects", json={"name": "Perf"})
    pid = create.json()["id"]

    times: list[float] = []
    for _ in range(100):
        start = time.perf_counter()
        res = validation_client.post("/api/chat", json={"message": "hi", "project_id": pid})
        elapsed = (time.perf_counter() - start) * 1000
        assert res.status_code == 200
        times.append(elapsed)

    times.sort()
    p95 = times[int(len(times) * 0.95)]
    assert p95 < 200, f"p95 chat latency {p95:.2f}ms >= 200ms"


def test_perf_project_list_50(validation_client: TestClient):
    """PERF-02: Listing 50 projects < 100ms."""
    for i in range(50):
        res = validation_client.post("/api/projects", json={"name": f"P{i}"})
        assert res.status_code == 200

    start = time.perf_counter()
    res = validation_client.get("/api/projects")
    elapsed = (time.perf_counter() - start) * 1000
    assert res.status_code == 200
    assert len(res.json()) == 50
    assert elapsed < 100, f"project list latency {elapsed:.2f}ms >= 100ms"


def test_perf_memory_query_1000(temp_dir: str):
    """PERF-03: Query 1000 memory records < 100ms."""
    path = os.path.join(temp_dir, "memory.json")
    memory = JsonFileMemory(path)
    for i in range(1000):
        memory.save("project", f"content {i}", project_id="proj_x")

    start = time.perf_counter()
    records = memory.query(category="project", project_id="proj_x", limit=10)
    elapsed = (time.perf_counter() - start) * 1000
    assert len(records) == 10
    assert elapsed < 100, f"memory query latency {elapsed:.2f}ms >= 100ms"


def test_perf_artifact_version_chain(temp_dir: str):
    """PERF-04: Read latest artifact from 20 versions < 50ms."""
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    pm = ProjectManager(db)
    project = pm.create(name="Version")

    for i in range(20):
        pm.save_artifact(
            project.id,
            type="problem_brief",
            title="Problem Brief",
            content=f"v{i}",
            change_reason="update",
        )

    start = time.perf_counter()
    latest = pm.get_latest_artifact(project.id, "problem_brief", title="Problem Brief")
    elapsed = (time.perf_counter() - start) * 1000
    assert latest is not None
    assert latest.version == 20
    assert elapsed < 50, f"latest artifact latency {elapsed:.2f}ms >= 50ms"


# ---------------------------------------------------------------------------
# Security tests
# ---------------------------------------------------------------------------

def test_sec_sql_injection_project_name(validation_client: TestClient):
    """SEC-01: Project name/description with SQL metacharacters."""
    payload = "Project '; DROP TABLE projects; --"
    res = validation_client.post("/api/projects", json={
        "name": payload,
        "description": payload,
        "goal": payload,
    })
    assert res.status_code == 200
    pid = res.json()["id"]

    get_res = validation_client.get(f"/api/projects/{pid}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["name"] == payload
    assert data["description"] == payload

    list_res = validation_client.get("/api/projects")
    assert list_res.status_code == 200


def test_sec_path_traversal_file_read():
    """SEC-02: file_read should not read outside allowed paths."""
    tool = FileReadTool()
    result = tool.execute("read", {"path": "../etc/passwd"})
    assert not result.success
    assert "not found" in result.error.lower() or "outside" in result.error.lower()


def test_sec_high_risk_confirmation(temp_dir: str):
    """SEC-03: strict mode blocks file_write/terminal until confirmed."""
    config = KyrozenConfig(
        provider="mock",
        api_key="test-key",
        permission_mode="strict",
        workspace_root=temp_dir,
        log_level="ERROR",
        task_store_path=os.path.join(temp_dir, "tasks.json"),
    )
    app = create_app(config=config, model=MockModel([
        '{"tool": "terminal", "action": "execute", "parameters": {"command": "echo hi"}}'
    ]))
    with TestClient(app) as client:
        res = client.post("/api/chat", json={"message": "run command"})
        assert res.status_code == 200
        task_id = res.json()["task_id"]

        task = client.get(f"/api/tasks/{task_id}").json()
        assert task["status"] == "waiting_confirmation"


def test_sec_api_config_no_key(validation_client: TestClient):
    """SEC-04: /api/config must not expose api_key."""
    res = validation_client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert "api_key" not in data
    assert data.get("provider") == "mock"


def test_sec_project_isolation(validation_client: TestClient):
    """SEC-05: Tasks/decisions/artifacts are isolated by project."""
    p1 = validation_client.post("/api/projects", json={"name": "A"}).json()["id"]
    p2 = validation_client.post("/api/projects", json={"name": "B"}).json()["id"]

    validation_client.post("/api/chat", json={"message": "hello", "project_id": p1})
    validation_client.post(f"/api/projects/{p1}/decisions", json={
        "decision": "D1", "reason": "R1"
    })
    validation_client.post(f"/api/projects/{p1}/artifacts", json={
        "type": "PRD", "title": "T1", "content": "C1", "change_reason": "init"
    })

    assert len(validation_client.get(f"/api/projects/{p1}/tasks").json()) == 1
    assert len(validation_client.get(f"/api/projects/{p2}/tasks").json()) == 0
    assert len(validation_client.get(f"/api/projects/{p1}/decisions").json()) == 1
    assert len(validation_client.get(f"/api/projects/{p2}/decisions").json()) == 0
    assert len(validation_client.get(f"/api/projects/{p1}/artifacts").json()) == 1
    assert len(validation_client.get(f"/api/projects/{p2}/artifacts").json()) == 0


def test_sec_unknown_artifact_type_is_allowed(validation_client: TestClient):
    """SEC-06: Record behavior for artifact types outside allowed list."""
    pid = validation_client.post("/api/projects", json={"name": "Artifact"}).json()["id"]
    res = validation_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "custom_type",
        "title": "Custom",
        "content": "x",
        "change_reason": "test",
    })
    # System currently allows arbitrary artifact types; record this behavior.
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Compatibility tests
# ---------------------------------------------------------------------------

def test_comp_provider_initialization():
    """COMP-02: Multiple providers can be initialized."""
    # Mock provider is injected directly in tests; factory supports openai/deepseek.
    openai_cfg = KyrozenConfig(provider="openai", api_key="test")
    openai_like = get_model_provider(openai_cfg)
    assert openai_like.provider_name == "openai"

    deepseek_cfg = KyrozenConfig(provider="deepseek", api_key="test")
    deepseek_like = get_model_provider(deepseek_cfg)
    assert deepseek_like.provider_name == "deepseek"


def test_comp_web_ui_no_experimental_apis():
    """COMP-03: index.html avoids browser-only experimental APIs."""
    with open("kyrozen/web/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    experimental_apis = ["browsingTopics", "runAdAuction", "getInterestGroupAdAuctionData"]
    for api in experimental_apis:
        assert api not in html, f"Experimental API {api} found in index.html"


def test_comp_project_memory_auto_scope(temp_dir: str):
    """COMP-04: ProjectMemory scopes queries automatically."""
    path = os.path.join(temp_dir, "memory.json")
    backend = JsonFileMemory(path)
    mem_a = ProjectMemory("proj_a", backend)
    mem_b = ProjectMemory("proj_b", backend)

    mem_a.save("project", "A")
    mem_b.save("project", "B")

    assert len(mem_a.query(category="project")) == 1
    assert mem_a.query(category="project")[0].content == "A"
    assert len(mem_b.query(category="project")) == 1
    assert mem_b.query(category="project")[0].content == "B"
