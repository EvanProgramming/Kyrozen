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
