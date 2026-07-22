"""Tests for Kyrozen Phase 4 Market Research."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.config import KyrozenConfig
from kyrozen.research.models import (
    OPPORTUNITY_DECISIONS,
    Competitor,
    MarketGap,
    MarketResearchReport,
    ResearchPlan,
    ResearchSource,
)
from kyrozen.research.state import RESEARCH_STAGES, ResearchSession
from kyrozen.tools.research.providers import MockSearchProvider, UnconfiguredSearchProvider
from kyrozen.tools.research.tools import (
    GitHubSearchTool,
    PaperSearchTool,
    RecordOpportunityDecisionTool,
    SaveMarketResearchReportTool,
    SaveResearchSourceTool,
    WebSearchTool,
)

from tests.conftest import MockModel


@pytest.fixture
def research_source_data() -> dict[str, Any]:
    return {
        "title": "Test Product",
        "url": "https://example.com/product",
        "source_type": "product",
        "summary": "A product summary",
        "related_claim": "It solves X",
        "confidence": "medium",
        "fact_type": "fact",
    }


@pytest.fixture
def competitor_data() -> dict[str, Any]:
    return {
        "name": "Competitor A",
        "company": "Company A",
        "solution": "Mobile app for runners",
        "target_user": "runners",
        "main_features": ["playlist sync", "heart rate"],
        "price": "$9.99/mo",
        "advantages": ["cheap"],
        "complaints": ["ads"],
        "failure_reason": "",
        "sources": ["https://example.com/a"],
    }


@pytest.fixture
def report_data(competitor_data: dict[str, Any], research_source_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "problem_summary": "Runners need better music",
        "market_status": "Competitive",
        "competitors": [competitor_data],
        "open_source_projects": [research_source_data],
        "user_feedback": [],
        "alternative_solutions": [],
        "technology_routes": ["AI recommendation"],
        "market_gap": {
            "existing_solution": "manual playlists",
            "problem_remaining": "not adaptive",
            "possible_difference": "real-time tempo",
            "risk": "hardware dependency",
            "confidence": "medium",
        },
        "risks": ["competition"],
        "recommendation": "continue_development",
        "sources": [research_source_data],
    }


def test_research_source_serialization(research_source_data: dict[str, Any]):
    source = ResearchSource.from_dict(research_source_data)
    assert source.title == "Test Product"
    assert source.url == "https://example.com/product"
    assert source.source_type == "product"
    assert source.confidence == "medium"
    assert source.fact_type == "fact"
    assert source.to_dict()["title"] == "Test Product"


def test_research_source_invalid_source_type():
    with pytest.raises(ValueError):
        ResearchSource(source_type="invalid_type")


def test_competitor_serialization(competitor_data: dict[str, Any]):
    competitor = Competitor.from_dict(competitor_data)
    assert competitor.name == "Competitor A"
    assert competitor.target_user == "runners"
    assert "playlist sync" in competitor.main_features
    assert competitor.to_dict()["price"] == "$9.99/mo"


def test_market_research_report_serialization(report_data: dict[str, Any]):
    report = MarketResearchReport.from_dict(report_data)
    assert report.problem_summary == "Runners need better music"
    assert len(report.competitors) == 1
    assert report.recommendation == "continue_development"
    assert report.to_dict()["market_status"] == "Competitive"


def test_invalid_recommendation():
    with pytest.raises(ValueError):
        MarketResearchReport(recommendation="invalid_choice")


def test_research_plan_serialization():
    plan = ResearchPlan(
        research_question="Who solves this?",
        search_directions=["sport headphones", "music apps"],
        reason="Core categories",
    )
    data = plan.to_dict()
    assert data["research_question"] == "Who solves this?"
    restored = ResearchPlan.from_dict(data)
    assert restored.search_directions == ["sport headphones", "music apps"]


def test_research_session_state():
    session = ResearchSession(project_id="proj_123")
    assert session.stage == "understanding_problem"
    session.set_stage("searching_sources")
    assert session.stage == "searching_sources"
    assert "Stage: searching_sources" in session.logs

    source = ResearchSource(title="S1", url="https://a.com")
    session.add_source(source)
    session.add_source(source)  # duplicate should be ignored
    assert len(session.sources) == 1

    competitor = Competitor(name="C1")
    session.add_competitor(competitor)
    session.add_competitor(Competitor(name="c1"))  # case-insensitive duplicate
    assert len(session.competitors) == 1


def test_research_session_invalid_stage():
    with pytest.raises(ValueError):
        ResearchSession(project_id="proj_123", stage="invalid_stage")


def test_unconfigured_web_search():
    provider = UnconfiguredSearchProvider("web_search", "Set API key")
    results = provider.search("test query")
    assert len(results) == 1
    assert results[0].fact_type == "unknown"
    assert "Set API key" in results[0].summary


def test_web_search_tool_without_config():
    tool = WebSearchTool(tavily_api_key="", serper_api_key="")
    result = tool.execute("search", {"query": "running music app"})
    assert result.success
    sources = result.data["sources"]
    assert len(sources) == 1
    assert "not configured" in sources[0]["title"]


def test_mock_search_provider():
    provider = MockSearchProvider(
        results=[
            ResearchSource(title="R1", url="https://r1.com", source_type="product"),
            ResearchSource(title="R2", url="https://r2.com", source_type="app"),
        ]
    )
    results = provider.search("query", limit=1)
    assert len(results) == 1
    assert results[0].title == "R1"


def test_github_search_tool_without_config():
    tool = GitHubSearchTool(token="")
    result = tool.execute("search", {"query": "running music"})
    assert result.success
    # Without requests installed or token, it may return error source; tool still succeeds structurally
    assert "sources" in result.data


def test_paper_search_tool_without_config():
    tool = PaperSearchTool(api_key="")
    result = tool.execute("search", {"query": "music recommendation"})
    assert result.success
    assert "sources" in result.data


def test_save_research_source_tool(project_manager):
    tool = SaveResearchSourceTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    source = ResearchSource(
        title="Example Source",
        url="https://example.com",
        source_type="product",
        summary="Summary",
        confidence="high",
        fact_type="fact",
    )
    result = tool.execute("save", {"project_id": project.id, "source": source.to_dict()})
    assert result.success, result.error
    assert "artifact_id" in result.data


def test_save_market_research_report_tool(project_manager, report_data: dict[str, Any]):
    tool = SaveMarketResearchReportTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "report": report_data})
    assert result.success, result.error
    assert result.data["version"] == 1

    # Second save increments version
    result2 = tool.execute("save", {"project_id": project.id, "report": report_data})
    assert result2.success
    assert result2.data["version"] == 2


def test_record_opportunity_decision_tool(project_manager):
    tool = RecordOpportunityDecisionTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute(
        "record",
        {"project_id": project.id, "decision": "continue_development", "reason": "Strong evidence"},
    )
    assert result.success, result.error
    assert result.data["decision"] == "continue_development"

    result_invalid = tool.execute(
        "record",
        {"project_id": project.id, "decision": "invalid", "reason": "x"},
    )
    assert not result_invalid.success


def test_opportunity_decisions_set():
    assert "continue_development" in OPPORTUNITY_DECISIONS
    assert "abandon" in OPPORTUNITY_DECISIONS


def test_research_stages_defined():
    assert "understanding_problem" in RESEARCH_STAGES
    assert "completed" in RESEARCH_STAGES


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


def test_market_research_chat_mode(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "MR Project", "goal": "G"})
    pid = create.json()["id"]

    # Seed a problem brief
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

    chat_res = api_client.post("/api/chat", json={
        "message": "开始市场调研",
        "project_id": pid,
        "mode": "market_research",
    })
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert data["project_id"] == pid
    assert data["mode"] == "market_research"
    assert data["task_id"].startswith("task_")


def test_market_research_state_endpoint(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "MR Project 2", "goal": "G"})
    pid = create.json()["id"]

    # Seed a market research report
    report = MarketResearchReport(
        problem_summary="Test",
        market_status="Competitive",
        recommendation="pause",
    )
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "market_research_report",
        "title": "Market Research Report",
        "content": json.dumps(report.to_dict()),
        "change_reason": "Seed",
    })

    res = api_client.get(f"/api/projects/{pid}/market-research/state")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == pid
    assert data["report"]["recommendation"] == "pause"


def test_market_research_state_requires_project(api_client: TestClient):
    res = api_client.get("/api/projects/proj_missing/market-research/state")
    assert res.status_code == 404
