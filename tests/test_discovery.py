"""Tests for Kyrozen Phase 3 Problem Discovery system."""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.config import KyrozenConfig
from kyrozen.discovery.brief import ProblemBrief
from kyrozen.discovery.evidence import Evidence, assess_confidence
from kyrozen.discovery.question_engine import QuestionEngine
from kyrozen.project import KyrozenDatabase, ProjectManager

from tests.conftest import MockModel, make_authenticated_app


def test_problem_brief_merge():
    brief = ProblemBrief(title="T1", surface_problem="sp")
    update = ProblemBrief(target_user="runners", deep_need="focus")
    merged = brief.merge(update)
    assert merged.title == "T1"
    assert merged.surface_problem == "sp"
    assert merged.target_user == "runners"
    assert merged.deep_need == "focus"


def test_question_engine_finds_missing_dimensions():
    brief = ProblemBrief(surface_problem="music does not fit")
    engine = QuestionEngine()
    missing = engine.find_missing_dimensions(brief)
    assert "target_user" in missing
    assert "surface_problem" not in missing
    next_q = engine.next_question(brief)
    assert next_q is not None
    assert next_q.dimension == "scenario"


def test_question_engine_no_questions_when_complete():
    brief = ProblemBrief(
        target_user="runners",
        scenario="gym",
        surface_problem="manual switching",
        deep_need="focus",
        current_solution="phone",
        current_solution_problem="distracting",
        frequency="daily",
        impact="high",
    )
    engine = QuestionEngine()
    assert engine.next_question(brief) is None


def test_evidence_validation():
    Evidence(claim="many runners have this", source="user_statement")
    with pytest.raises(ValueError):
        Evidence(claim="x", source="invalid_source")


def test_assess_confidence():
    low, _ = assess_confidence({})
    assert low == "low"
    medium, _ = assess_confidence({
        "target_user": "runners", "scenario": "gym", "surface_problem": "x", "deep_need": "y"
    })
    assert medium == "medium"
    high, _ = assess_confidence({
        "target_user": "runners", "scenario": "gym", "surface_problem": "x",
        "deep_need": "y", "current_solution": "phone", "current_solution_problem": "z",
        "unknown_assumptions": [{"claim": "a", "verified": True}],
    })
    assert high == "high"


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
    # Model responds with plain text to avoid tool calls in basic tests
    app = make_authenticated_app(config, MockModel(["Tell me more about who faces this problem."]))
    with TestClient(app) as client:
        yield client


def test_discovery_state_endpoint(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "AI Running Device"})
    pid = create.json()["id"]

    res = api_client.get(f"/api/projects/{pid}/problem-discovery/state")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == pid
    assert data["brief"]["title"] == ""
    assert data["state_summary"]["next_question"] is not None


def test_save_problem_brief_tool_via_api(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "AI Running Device"})
    pid = create.json()["id"]

    brief = ProblemBrief(
        title="AI Running Music",
        target_user="runners",
        scenario="outdoor running",
        surface_problem="music doesn't match pace",
    )
    res = api_client.post("/api/tools/execute", json={
        "tool": "save_problem_brief",
        "action": "save",
        "parameters": {"project_id": pid, "brief": brief.to_dict()}
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["version"] == 1

    state = api_client.get(f"/api/projects/{pid}/problem-discovery/state").json()
    assert state["brief"]["title"] == "AI Running Music"
    assert state["latest_artifact_id"] == data["data"]["artifact_id"]


def test_record_evidence_tool_via_api(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "AI Running Device"})
    pid = create.json()["id"]

    res = api_client.post("/api/tools/execute", json={
        "tool": "record_evidence",
        "action": "record",
        "parameters": {"project_id": pid, "claim": "many runners have this issue", "source": "user_statement"}
    })
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_phase2_evidence_workbench_persists_and_restores(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Evidence Workbench"})
    pid = create.json()["id"]

    created = api_client.post(f"/api/projects/{pid}/evidence", json={
        "claim": "三名社区组织者在活动后仍需人工核对报名名单",
        "source": "user_statement",
        "evidence_type": "interview",
        "target_audience": "社区组织者",
        "related_question": "活动结束后最耗时的工作是什么？",
        "confidence": "high",
    })
    assert created.status_code == 200
    evidence = created.json()
    assert evidence["version"] == 1
    assert evidence["evidence_type"] == "interview"

    snapshot = api_client.get(f"/api/projects/{pid}/phase2/workbench")
    assert snapshot.status_code == 200
    assert snapshot.json()["evidence"]["active_count"] == 1
    assert snapshot.json()["evidence"]["by_type"] == {"interview": 1}

    updated = api_client.patch(f"/api/projects/{pid}/evidence/{evidence['artifact_id']}", json={"status": "invalid"})
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert api_client.get(f"/api/projects/{pid}/evidence").json() == []
    assert len(api_client.get(f"/api/projects/{pid}/evidence", params={"include_invalid": "true"}).json()) == 1

    restored = api_client.post(f"/api/projects/{pid}/evidence/{updated.json()['artifact_id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert api_client.get(f"/api/projects/{pid}/evidence").json()[0]["claim"].startswith("三名社区")


def test_record_evidence_tool_falls_back_to_workspace_when_artifact_store_fails(tmp_path):
    from kyrozen.tools.discovery_tools import RecordEvidenceTool

    class FailingProjectManager:
        def save_artifact(self, **kwargs):
            raise RuntimeError("cloud unavailable")

    config = KyrozenConfig(workspace_root=str(tmp_path))
    result = RecordEvidenceTool(FailingProjectManager(), config=config).execute(
        "record",
        {
            "project_id": "proj-local",
            "claim": "用户在微信群接龙报名",
            "source": "user_statement",
        },
    )

    assert result.success is True
    assert result.data["cloud_sync"] is False
    assert list((tmp_path / ".kyrozen" / "evidence").glob("*.json"))


def test_record_evidence_tool_works_without_cloud_project_manager(tmp_path):
    from kyrozen.tools.discovery_tools import RecordEvidenceTool

    result = RecordEvidenceTool(None, config=KyrozenConfig(workspace_root=str(tmp_path))).execute(
        "record",
        {
            "project_id": "proj-local",
            "claim": "用户通过微信群报名",
            "source": "user_statement",
        },
    )

    assert result.success is True


def test_assess_confidence_reads_local_problem_brief_without_cloud_project_manager(tmp_path):
    from kyrozen.tools.discovery_tools import AssessConfidenceTool

    problem_dir = tmp_path / "docs"
    problem_dir.mkdir()
    (problem_dir / "PROBLEM.md").write_text(
        "**目标用户**：社区组织者\n**使用场景**：周末活动\n**表面问题**：统计人数困难\n"
        "**深层需求**：准确掌握报名人数\n**当前解决方案**：微信群接龙\n"
        "**当前方案痛点**：需要人工统计\n",
        encoding="utf-8",
    )

    result = AssessConfidenceTool(None, config=KyrozenConfig(workspace_root=str(tmp_path))).execute(
        "assess", {"project_id": "proj-local"}
    )

    assert result.success is True
    assert result.data["confidence"] == "high"


def test_assess_confidence_tool_via_api(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "AI Running Device"})
    pid = create.json()["id"]

    # No brief yet -> low
    res = api_client.post("/api/tools/execute", json={
        "tool": "assess_confidence",
        "action": "assess",
        "parameters": {"project_id": pid}
    })
    assert res.status_code == 200
    assert res.json()["data"]["confidence"] == "low"


def test_discovery_chat_mode_uses_discovery_agent(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "AI Running Device"})
    pid = create.json()["id"]

    res = api_client.post("/api/chat", json={
        "message": "I want to build AI glasses",
        "project_id": pid,
        "mode": "discovery",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "discovery"
    assert data["project_id"] == pid
    assert data["task_id"].startswith("task_")


def test_discovery_agent_prompt_forbids_product_design():
    from kyrozen.discovery import ProblemDiscoveryAgent
    config = KyrozenConfig(provider="mock", api_key="test", permission_mode="permissive")
    agent = ProblemDiscoveryAgent(config=config, model=MockModel(), project_manager=None)
    prompt = agent._build_system_prompt()
    assert "DO NOT design a product" in prompt
    assert "DO NOT perform market research" in prompt
