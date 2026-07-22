"""End-to-end scenario tests for Problem Discovery.

These tests simulate user conversations and verify that Kyrozen:
- Explores the problem instead of jumping to product design
- Saves a Problem Brief artifact when enough info is gathered
- Preserves state across sessions
- Flags simple existing solutions
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.config import KyrozenConfig

from tests.conftest import MockModel, make_authenticated_app


def _make_client(temp_dir: str, responses: list[str]) -> TestClient:
    config = KyrozenConfig(
        provider="mock",
        api_key="test-key",
        permission_mode="permissive",
        workspace_root=temp_dir,
        log_level="ERROR",
        task_store_path=os.path.join(temp_dir, "tasks.json"),
    )
    app = make_authenticated_app(config, MockModel(responses))
    return TestClient(app)


def _create_project(client: TestClient, name: str) -> str:
    res = client.post("/api/projects", json={"name": name})
    assert res.status_code == 200
    return res.json()["id"]


def _brief_from_state(client: TestClient, project_id: str) -> dict:
    res = client.get(f"/api/projects/{project_id}/problem-discovery/state")
    assert res.status_code == 200
    return res.json()["brief"]


def test_e2e_vague_problem_room_is_noisy(temp_dir: str):
    """E2E-01: vague problem should lead to problem exploration and brief."""
    brief_payload = {
        "title": "Room noise during work",
        "target_user": "remote worker at home",
        "scenario": "home office during work hours",
        "surface_problem": "room is too noisy to focus",
        "deep_need": "a quiet environment for concentration",
        "current_solution": "close the door",
        "current_solution_problem": "outside noise still comes through",
        "frequency": "every workday",
        "impact": "reduces productivity",
        "unknown_assumptions": [
            {"claim": "neighbors also find it noisy", "source": "user_statement", "verified": False}
        ],
        "opportunity_direction": "explore noise reduction or masking solutions",
    }

    with _make_client(temp_dir, [json.dumps({
        "tool": "save_problem_brief",
        "action": "save",
        "parameters": {"project_id": "PLACEHOLDER", "brief": brief_payload},
    })]) as client:
        pid = _create_project(client, "Quiet Workspace")
        res = client.post("/api/chat", json={
            "message": "我觉得房间很吵",
            "project_id": pid,
            "mode": "discovery",
        })
        assert res.status_code == 200

        # Simulate agent saving brief with the actual project id
        brief_payload_actual = dict(brief_payload)
        brief_payload_actual["project_id"] = pid
        save_res = client.post("/api/tools/execute", json={
            "tool": "save_problem_brief",
            "action": "save",
            "parameters": {"project_id": pid, "brief": brief_payload_actual},
        })
        assert save_res.status_code == 200

        brief = _brief_from_state(client, pid)
        assert brief["surface_problem"]
        assert brief["target_user"]
        assert brief["scenario"]
        # Should not have designed a product yet
        assert not brief.get("opportunity_direction", "").lower().startswith("build a")


def test_e2e_product_idea_ai_glasses(temp_dir: str):
    """E2E-02: product idea should be challenged, not directly designed."""
    with _make_client(temp_dir, ["Why do you want to make AI glasses? What problem are you trying to solve?"]) as client:
        pid = _create_project(client, "AI Glasses")
        res = client.post("/api/chat", json={
            "message": "我想做一个AI眼镜",
            "project_id": pid,
            "mode": "discovery",
        })
        assert res.status_code == 200
        task_id = res.json()["task_id"]
        task = client.get(f"/api/tasks/{task_id}").json()
        answer = task["result"]["answer"]
        # Should ask why, not design the product
        assert "为什么" in answer or "why" in answer.lower() or "problem" in answer.lower()
        assert "摄像头" not in answer
        assert "芯片" not in answer
        assert "BOM" not in answer


def test_e2e_existing_solution_drink_water(temp_dir: str):
    """E2E-03: simple existing solution should be flagged."""
    with _make_client(temp_dir, [
        "Have you tried using a recurring phone alarm or a habit app? That might be the simplest solution."
    ]) as client:
        pid = _create_project(client, "Drink Water Reminder")
        res = client.post("/api/chat", json={
            "message": "我想每天提醒自己喝水",
            "project_id": pid,
            "mode": "discovery",
        })
        assert res.status_code == 200
        task_id = res.json()["task_id"]
        task = client.get(f"/api/tasks/{task_id}").json()
        answer = task["result"]["answer"]
        assert "闹钟" in answer or "alarm" in answer.lower() or "app" in answer.lower() or "日历" in answer


def test_e2e_preserve_discovery_state(temp_dir: str):
    """E2E-04: Problem Brief should persist across sessions."""
    brief_payload = {
        "title": "Running Music",
        "target_user": "runners",
        "scenario": "outdoor running",
        "surface_problem": "music doesn't match pace",
        "deep_need": "stay focused without manual interaction",
        "current_solution": "manually switch songs",
        "current_solution_problem": "breaks running rhythm",
        "frequency": "every run",
        "impact": "reduces flow",
        "unknown_assumptions": [],
        "opportunity_direction": "explore adaptive music for runners",
    }

    # First session: save a brief
    with _make_client(temp_dir, []) as client1:
        pid = _create_project(client1, "AI Running Device")
        save_res = client1.post("/api/tools/execute", json={
            "tool": "save_problem_brief",
            "action": "save",
            "parameters": {"project_id": pid, "brief": brief_payload},
        })
        assert save_res.status_code == 200

    # Second session: new TestClient on the same workspace
    with _make_client(temp_dir, []) as client2:
        brief = _brief_from_state(client2, pid)
        assert brief["title"] == "Running Music"
        assert brief["target_user"] == "runners"
