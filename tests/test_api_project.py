"""Tests for Project API endpoints."""

from __future__ import annotations

import os
import json
from pathlib import Path

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
        client.workspace_root = temp_dir
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

    blocked_stage_update = api_client.put(f"/api/projects/{pid}", json={"current_stage": "product_definition"})
    assert blocked_stage_update.status_code == 409
    put_res = api_client.put(f"/api/projects/{pid}", json={"status": "paused", "next_steps": "Define MVP"})
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["status"] == "paused"
    assert data["current_stage"] == "problem_discovery"
    assert data["next_steps"] == "Define MVP"
    blocked_completed = api_client.put(f"/api/projects/{pid}", json={"status": "completed"})
    assert blocked_completed.status_code == 409
    assert "第二阶段验收条件" in blocked_completed.json()["detail"]["message"]

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


def test_stage_sync_only_accepts_adjacent_gate_transition(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Stage Sync"})
    pid = create.json()["id"]
    assert api_client.post(f"/api/projects/{pid}/workflow-confirm", json={"project_type": "software"}).status_code == 200
    assert api_client.post(f"/api/projects/{pid}/stage-sync", json={"stage": "development", "progress": 50, "gate": {"can_advance": True}}).status_code == 409
    # A truthy but incomplete gate snapshot must not be enough to advance.
    assert api_client.post(f"/api/projects/{pid}/stage-sync", json={"stage": "market_research", "progress": 15, "gate": {"can_advance": True}}).status_code == 409
    project_root = Path(api_client.workspace_root) / "projects" / pid / "docs"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "PROBLEM.md").write_text("# Problem\nConfirmed", encoding="utf-8")
    synced = api_client.post(f"/api/projects/{pid}/stage-sync", json={
        "stage": "market_research", "progress": 15,
        "gate": {"stage": "market_research", "index": 1, "can_advance": True, "missing": []},
    })
    assert synced.status_code == 200
    assert synced.json()["current_stage"] == "market_research"
    assert synced.json()["next_steps"] == "进行市场调研"


def test_advance_project_stage_order(api_client: TestClient, temp_dir: str):
    create = api_client.post("/api/projects", json={"name": "Advance"})
    pid = create.json()["id"]
    assert create.json()["current_stage"] == "problem_discovery"

    # Workflow type confirmation and real deliverables are prerequisites; the
    # endpoint must not advance by stage index alone.
    assert api_client.post(f"/api/projects/{pid}/advance", json={}).status_code == 409
    assert api_client.post(f"/api/projects/{pid}/workflow-confirm", json={"project_type": "software"}).status_code == 200
    root = os.path.join(temp_dir, "projects", pid)
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    os.makedirs(os.path.join(root, "tests"), exist_ok=True)

    def advance_after(relative_path: str, content: str = "# evidence"):
        target = os.path.join(root, relative_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content)
        response = api_client.post(f"/api/projects/{pid}/advance", json={})
        assert response.status_code == 200, response.text
        return response

    first_advance = advance_after("docs/PROBLEM.md")
    assert first_advance.json()["current_stage"] == "market_research"
    assert first_advance.json()["next_steps"] == "进行市场调研"
    advance_after("docs/MARKET.md")
    advance_after("PRD.md")
    tech_design = os.path.join(root, "docs", "TECH_DESIGN.md")
    with open(tech_design, "w", encoding="utf-8") as handle:
        handle.write("# Technical design\n")
    # The solution-design stage is a hard Phase 2 gate: a technical document
    # alone is not enough to enter implementation. Persist a real confirmed
    # three-way comparison through the API.
    evidence = api_client.post(f"/api/projects/{pid}/evidence", json={
        "claim": "目标用户需要在实现前比较方案取舍", "evidence_type": "interview",
    }).json()
    research_source = api_client.post(f"/api/projects/{pid}/research/sources", json={
        "source": {"title": "公开研究资料", "url": "https://example.com/research", "source_type": "web_page", "summary": "真实公开来源"},
    })
    assert research_source.status_code == 200, research_source.text
    dimensions = ["time", "cost", "user_value", "technical_risk", "maintenance_cost", "data_risk", "validation_difficulty"]
    comparison = {
        "solutions": [
            {"name": name, "solution": name, "dimension_scores": {dimension: 3 for dimension in dimensions}, "evidence_ids": [evidence["artifact_id"]]}
            for name in ["保守方案", "平衡方案", "激进方案"]
        ],
        "comparison_dimensions": dimensions,
        "recommendation": "平衡方案",
        "recommendation_reason": "先验证核心价值",
    }
    confirmed_solution = api_client.post(
        f"/api/projects/{pid}/solutions",
        json={"comparison": comparison, "action": "select", "affected_tasks": ["更新 PRD"]},
    )
    assert confirmed_solution.status_code == 200, confirmed_solution.text
    assert confirmed_solution.json()["impact_artifact_id"]
    impact = api_client.get(f"/api/projects/{pid}/artifacts").json()
    assert any(item["type"] == "solution_impact" for item in impact)
    generated = api_client.get(f"/api/projects/{pid}/tasks").json()
    assert {item["title"] for item in generated} >= {
        "方案影响：更新PRD",
        "方案影响：更新Technical Plan",
        "方案影响：更新Test Plan",
        "方案影响：更新Solution File Tasks",
    }
    assert api_client.post(f"/api/projects/{pid}/advance", json={}).status_code == 200
    from kyrozen.core.stagegate import StageGateStore, refresh_gate
    gate_store = StageGateStore(os.path.join(root, ".kyrozen", "stagegate.json"), project_id=pid, project_type="software")
    with open(os.path.join(root, "app.py"), "w", encoding="utf-8") as handle:
        handle.write("print('ok')")
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("# Advance\n")
    gate_store = StageGateStore(os.path.join(root, ".kyrozen", "stagegate.json"), project_id=pid, project_type="software")
    refresh_gate(gate_store, root)
    gate_store.record_verification("build_passes", True, detail="app.py compiled")
    gate_store.save()
    advance_after("tests/test_smoke.py")

    # Testing requires an actual verification result, not just a test file.
    test_file = os.path.join(root, "tests", "test_smoke.py")
    with open(test_file, "w", encoding="utf-8") as handle:
        handle.write("def test_smoke(): assert True\n")
    blocked = api_client.post(f"/api/projects/{pid}/advance", json={})
    assert blocked.status_code == 409
    from kyrozen.core.stagegate import StageGateStore, refresh_gate
    gate_store = StageGateStore(os.path.join(root, ".kyrozen", "stagegate.json"), project_id=pid, project_type="software")
    refresh_gate(gate_store, root)
    gate_store.record_verification("tests_pass", True, detail="test_smoke passed")
    gate_store.save()
    refresh_gate(gate_store, root)
    assert api_client.post(f"/api/projects/{pid}/advance", json={}).json()["current_stage"] == "iteration"
    gate_store = StageGateStore(os.path.join(root, ".kyrozen", "stagegate.json"), project_id=pid, project_type="software")
    refresh_gate(gate_store, root)
    gate_store.record_verification("regression_passes", True, detail="original test regression passed")
    with open(os.path.join(root, "CHANGELOG.md"), "w", encoding="utf-8") as handle:
        handle.write("# Changelog\n")
    gate_store.save()

    # Final Phase 2 completion is stricter than reaching the last lifecycle
    # stage: persist real evidence, research, regression, and three user
    # validation records before the project may become completed.
    evidence = api_client.post(f"/api/projects/{pid}/evidence", json={
        "claim": "用户需要可恢复的本地笔记流程", "evidence_type": "interview",
    })
    assert evidence.status_code == 200
    evidence_id = evidence.json()["artifact_id"]
    brief = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "problem_brief", "title": "Problem Brief",
        "content": json.dumps({"title": "问题", "evidence_ids": [evidence_id], "counter_evidence_ids": [], "unresolved_questions": []}),
    })
    assert brief.status_code == 200
    assert api_client.post(f"/api/projects/{pid}/research/sources", json={
        "source": {"title": "公开资料", "url": "https://example.com/research", "source_type": "web_page", "summary": "真实来源"},
    }).status_code == 200
    research_run = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "research_run", "title": "Research Run final-coverage",
        "content": json.dumps({
            "run_id": "final-coverage", "status": "completed", "sources": [], "retry_queue": [],
            "provider_status": {
                "serper": "success", "github": "success", "semantic_scholar": "success",
                "patent": "success", "crowdfunding": "success", "community": "failed",
            },
        }),
    })
    assert research_run.status_code == 200
    for participant in ("U-01", "U-02", "U-03"):
        assert api_client.post("/api/feedback", json={
            "type": "experience", "description": f"验证记录 {participant}", "project_id": pid,
            "participant_id": participant, "user_type": "目标用户", "task": "完成核心任务",
            "completed": True, "duration_seconds": 30, "satisfaction": 4,
        }).status_code == 200
    failed_result = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "test_result", "title": "Failed: DEF-1",
        "content": json.dumps({"test_case_id": "TC-1", "result": "failed", "defect_id": "DEF-1"}),
    })
    assert failed_result.status_code == 200
    regression = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "test_result", "title": "Regression: DEF-1",
        "content": json.dumps({"test_case_id": "TC-1", "result": "passed", "regression_of": "DEF-1"}),
    })
    assert regression.status_code == 200
    defect = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "defect", "title": "Defect: DEF-1",
        "content": json.dumps({"defect_id": "DEF-1", "title": "原始失败", "status": "open", "severity": "medium"}),
    })
    assert defect.status_code == 200
    fix = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "defect_fix", "title": "Fix: DEF-1",
        "content": json.dumps({"defect_id": "DEF-1", "fix": "修复并回归"}),
    })
    assert fix.status_code == 200
    report = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "validation_report", "title": "Validation Report",
        "content": json.dumps({
            "original_problem": "问题", "tested_solution": "方案",
            "user_feedback": [
                {"participant_id": p, "user_type": "目标用户", "task": "完成核心任务"}
                for p in ("U-01", "U-02", "U-03")
            ],
            "conclusion": "continue_release", "success_metrics": "3/3",
        }),
    })
    assert report.status_code == 200, report.text
    readiness = api_client.get(f"/api/projects/{pid}/phase2/workbench")
    assert readiness.status_code == 200
    assert readiness.json()["phase2_completion"]["ready"] is True
    assert readiness.json()["phase2_completion"]["missing"] == []

    # Final advance marks project completed only after the complete Phase 2
    # readiness contract is satisfied.
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
