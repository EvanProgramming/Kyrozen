"""Tests for Kyrozen Phase 5 Product Planning."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.config import KyrozenConfig
from kyrozen.planning.models import (
    COMPARISON_DIMENSIONS,
    PRIORITY_LEVELS,
    PRODUCT_DECISIONS,
    MVP,
    Feature,
    PRD,
    ProductBrief,
    ProductGoal,
    Solution,
    SolutionComparison,
    TargetUser,
    UserJourney,
)
from kyrozen.planning.state import PLANNING_STAGES, PlanningSession
from kyrozen.tools.planning_tools import (
    RecordProductDecisionTool,
    SavePRDTool,
    SaveProductBriefTool,
    SaveSolutionComparisonTool,
)

from tests.conftest import MockModel


@pytest.fixture
def product_brief_data() -> dict[str, Any]:
    return {
        "product_goal": {
            "product_goal": "Help runners stay in flow with adaptive music",
            "target_user": "runners",
            "core_problem": "music does not match pace",
            "value_proposition": "effortless pace-aware soundtrack",
        },
        "target_user": {
            "primary_user": "weekly runners who train with music",
            "secondary_user": "coaches creating playlists",
            "use_case": "outdoor running",
            "user_context": "phone in armband, focused on pace",
        },
        "user_journey": {
            "before": "Runner manually switches songs",
            "during": "App detects cadence and adjusts music",
            "after": "Runner finishes without touching phone",
        },
        "value_proposition": "Stay in flow without manual controls",
        "user_stories": ["As a runner I want music to match my pace"],
        "core_features": [
            {
                "name": "cadence detection",
                "description": "detect running cadence from phone sensors",
                "user_problem": "music is too slow or fast",
                "priority": "Must Have",
            }
        ],
        "mvp_scope": {
            "mvp_features": ["cadence detection", "tempo-based playlist"],
            "excluded_features": ["AI recommendation", "social sharing"],
            "success_metric": "Runner touches phone less than 2 times per run",
        },
        "non_goals": ["hardware integration", "music streaming service"],
        "success_metrics": ["Runner touches phone less than 2 times per run"],
        "constraints": ["phone-only first version"],
        "risks": ["sensor accuracy varies by device"],
    }


@pytest.fixture
def solution_comparison_data() -> dict[str, Any]:
    return {
        "solutions": [
            {
                "name": "Software Only",
                "solution": "Mobile app using phone sensors",
                "advantages": ["low cost", "fast iteration"],
                "disadvantages": ["sensor accuracy limited"],
                "cost": "low",
                "difficulty": "medium",
                "development_time": "2-4 weeks",
                "risk": "medium",
                "scalability": "high",
            },
            {
                "name": "Hardware Only",
                "solution": "Dedicated music player with sensors",
                "advantages": ["better sensor integration"],
                "disadvantages": ["high cost", "long development"],
                "cost": "high",
                "difficulty": "high",
                "development_time": "6-12 months",
                "risk": "high",
                "scalability": "low",
            },
        ],
        "comparison_dimensions": list(COMPARISON_DIMENSIONS),
        "recommendation": "Software Only",
        "recommendation_reason": "Lower cost and faster validation",
    }


@pytest.fixture
def prd_data(product_brief_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "overview": "A phone app that adapts music tempo to running cadence",
        "user_stories": product_brief_data["user_stories"],
        "functional_requirements": ["detect cadence", "select song by tempo"],
        "non_functional_requirements": ["works offline", "battery efficient"],
        "mvp_scope": product_brief_data["mvp_scope"],
        "out_of_scope": ["social features", "hardware integration"],
    }


def test_product_goal_serialization():
    goal = ProductGoal(
        product_goal="Adaptive running music",
        target_user="runners",
        core_problem="music doesn't match pace",
        value_proposition="stay in flow",
    )
    data = goal.to_dict()
    assert data["product_goal"] == "Adaptive running music"
    restored = ProductGoal.from_dict(data)
    assert restored.value_proposition == "stay in flow"


def test_target_user_serialization():
    user = TargetUser(
        primary_user="weekly runners",
        secondary_user="coaches",
        use_case="outdoor training",
        user_context="phone in armband",
    )
    data = user.to_dict()
    assert data["primary_user"] == "weekly runners"
    assert TargetUser.from_dict(data).use_case == "outdoor training"


def test_user_journey_serialization():
    journey = UserJourney(before="manual", during="auto", after="review")
    data = journey.to_dict()
    assert data["during"] == "auto"
    assert UserJourney.from_dict(data).before == "manual"


def test_feature_priority_validation():
    feature = Feature(name="x", priority="Must Have")
    assert feature.priority in PRIORITY_LEVELS
    with pytest.raises(ValueError):
        Feature(name="x", priority="Later")


def test_mvp_serialization():
    mvp = MVP(mvp_features=["a"], excluded_features=["b"], success_metric="m")
    data = mvp.to_dict()
    assert data["mvp_features"] == ["a"]
    assert MVP.from_dict(data).excluded_features == ["b"]


def test_solution_serialization():
    solution = Solution(name="S1", cost="low", difficulty="medium")
    data = solution.to_dict()
    assert data["name"] == "S1"
    assert Solution.from_dict(data).cost == "low"


def test_solution_comparison_dimensions_validation():
    comparison = SolutionComparison()
    assert comparison.comparison_dimensions == list(COMPARISON_DIMENSIONS)
    with pytest.raises(ValueError):
        SolutionComparison(comparison_dimensions=["invalid"])


def test_solution_comparison_serialization(solution_comparison_data: dict[str, Any]):
    comparison = SolutionComparison.from_dict(solution_comparison_data)
    assert len(comparison.solutions) == 2
    assert comparison.recommendation == "Software Only"
    data = comparison.to_dict()
    assert data["solutions"][0]["name"] == "Software Only"


def test_product_brief_serialization(product_brief_data: dict[str, Any]):
    brief = ProductBrief.from_dict(product_brief_data)
    assert brief.product_goal.product_goal == "Help runners stay in flow with adaptive music"
    assert len(brief.core_features) == 1
    assert brief.core_features[0].priority == "Must Have"
    data = brief.to_dict()
    assert data["mvp_scope"]["mvp_features"] == ["cadence detection", "tempo-based playlist"]


def test_prd_serialization(prd_data: dict[str, Any]):
    prd = PRD.from_dict(prd_data)
    assert prd.overview.startswith("A phone app")
    assert "detect cadence" in prd.functional_requirements
    data = prd.to_dict()
    assert data["out_of_scope"] == ["social features", "hardware integration"]


def test_planning_session_state():
    session = PlanningSession(project_id="proj_123")
    assert session.stage == "understanding_inputs"
    session.set_stage("defining_goal")
    assert session.stage == "defining_goal"
    assert "Stage: defining_goal" in session.logs

    feature = Feature(name="cadence detection", priority="Must Have")
    session.add_feature(feature)
    session.add_feature(Feature(name="cadence detection", priority="Could Have"))  # duplicate
    assert len(session.product_brief.core_features) == 1

    mvp = MVP(mvp_features=["cadence detection"], success_metric="touch phone < 2 times")
    session.set_mvp(mvp)
    assert session.product_brief.mvp_scope.success_metric == "touch phone < 2 times"
    assert session.prd.mvp_scope.success_metric == "touch phone < 2 times"

    solution = Solution(name="Software Only")
    session.add_solution(solution)
    session.add_solution(Solution(name="software only"))  # duplicate case-insensitive
    assert len(session.solution_comparison.solutions) == 1

    session.set_solution_recommendation("Software Only", "lower risk")
    assert session.solution_comparison.recommendation_reason == "lower risk"


def test_planning_session_invalid_stage():
    with pytest.raises(ValueError):
        PlanningSession(project_id="proj_123", stage="invalid_stage")
    session = PlanningSession(project_id="proj_123")
    with pytest.raises(ValueError):
        session.set_stage("invalid_stage")


def test_product_decisions_set():
    assert "continue_with_solution" in PRODUCT_DECISIONS
    assert "abandon" in PRODUCT_DECISIONS


def test_planning_stages_defined():
    assert "understanding_inputs" in PLANNING_STAGES
    assert "completed" in PLANNING_STAGES


def test_save_product_brief_tool(project_manager, product_brief_data: dict[str, Any]):
    tool = SaveProductBriefTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "brief": product_brief_data})
    assert result.success, result.error
    assert "artifact_id" in result.data
    assert result.data["version"] == 1

    # Second save increments version
    result2 = tool.execute("save", {"project_id": project.id, "brief": product_brief_data})
    assert result2.success
    assert result2.data["version"] == 2


def test_save_prd_tool(project_manager, prd_data: dict[str, Any]):
    tool = SavePRDTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "prd": prd_data})
    assert result.success, result.error
    assert result.data["version"] == 1


def test_save_solution_comparison_tool(project_manager, solution_comparison_data: dict[str, Any]):
    tool = SaveSolutionComparisonTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "comparison": solution_comparison_data})
    assert result.success, result.error
    assert "artifact_id" in result.data


def test_record_product_decision_tool(project_manager):
    tool = RecordProductDecisionTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute(
        "record",
        {
            "project_id": project.id,
            "decision": "continue_with_solution",
            "reason": "Software MVP has lowest risk",
            "alternatives": ["hardware_only"],
            "rejected_reasons": {"hardware_only": "too expensive"},
        },
    )
    assert result.success, result.error
    assert result.data["decision"] == "continue_with_solution"

    result_invalid = tool.execute(
        "record",
        {"project_id": project.id, "decision": "invalid", "reason": "x"},
    )
    assert not result_invalid.success


def test_planning_agent_prompt_forbids_development():
    from kyrozen.planning.agent import ProductPlanningAgent

    config = KyrozenConfig(provider="mock", api_key="test", permission_mode="permissive")
    agent = ProductPlanningAgent(config=config, model=MockModel(), project_manager=None)
    prompt = agent._build_system_prompt()
    assert "DO NOT write code" in prompt
    assert "DO NOT enter software development" in prompt
    assert "save_product_brief" in prompt
    assert "save_prd" in prompt


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


def test_planning_chat_mode(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Planning Project", "goal": "G"})
    pid = create.json()["id"]

    # Seed problem brief
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "problem_brief",
        "title": "Problem Brief",
        "content": json.dumps({
            "title": "Running music",
            "target_user": "runners",
            "surface_problem": "music doesn't match pace",
            "deep_need": "stay in flow",
        }),
        "change_reason": "Seed",
    })

    # Seed market research report
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "market_research_report",
        "title": "Market Research Report",
        "content": json.dumps({
            "problem_summary": "Runners need adaptive music",
            "market_status": "Competitive",
            "competitors": [],
            "open_source_projects": [],
            "user_feedback": [],
            "alternative_solutions": [],
            "technology_routes": ["sensor fusion"],
            "market_gap": {
                "existing_solution": "manual playlists",
                "problem_remaining": "not adaptive",
                "possible_difference": "real-time tempo",
                "risk": "hardware dependency",
                "confidence": "medium",
            },
            "risks": ["competition"],
            "recommendation": "continue_development",
            "sources": [],
        }),
        "change_reason": "Seed",
    })

    chat_res = api_client.post("/api/chat", json={
        "message": "开始产品规划",
        "project_id": pid,
        "mode": "planning",
    })
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert data["project_id"] == pid
    assert data["mode"] == "planning"
    assert data["task_id"].startswith("task_")


def test_planning_state_endpoint(api_client: TestClient, product_brief_data: dict[str, Any]):
    create = api_client.post("/api/projects", json={"name": "Planning Project 2", "goal": "G"})
    pid = create.json()["id"]

    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "product_brief",
        "title": "Product Brief",
        "content": json.dumps(product_brief_data),
        "change_reason": "Seed",
    })

    res = api_client.get(f"/api/projects/{pid}/planning/state")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == pid
    assert data["brief"]["product_goal"]["product_goal"] == "Help runners stay in flow with adaptive music"
    assert data["brief"]["mvp_scope"]["mvp_features"] == ["cadence detection", "tempo-based playlist"]


def test_planning_state_requires_project(api_client: TestClient):
    res = api_client.get("/api/projects/proj_missing/planning/state")
    assert res.status_code == 404
