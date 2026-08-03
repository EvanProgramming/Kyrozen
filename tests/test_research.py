"""Tests for Kyrozen Phase 4 Market Research."""

from __future__ import annotations

import json
import os
from pathlib import Path
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
from kyrozen.tools.research.providers import (
    CommunitySearchProvider,
    CrowdfundingSearchProvider,
    GitHubDiscussionsProvider,
    GitHubSearchProvider,
    MockSearchProvider,
    PatentSearchProvider,
    RedditSearchProvider,
    UnconfiguredSearchProvider,
)
from kyrozen.research.runs import execute_research_run
from kyrozen.tools.research.tools import (
    GitHubSearchTool,
    PaperSearchTool,
    RecordOpportunityDecisionTool,
    SaveMarketResearchReportTool,
    SaveResearchSourceTool,
    WebSearchTool,
)

from tests.conftest import MockModel, make_authenticated_app


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


def test_phase2_research_run_isolates_provider_failures():
    source = ResearchSource(title="R1", url="https://r1.com", source_type="web_page")
    run = execute_research_run(
        "running music",
        [MockSearchProvider([source]), PatentSearchProvider(endpoint=""), CrowdfundingSearchProvider(endpoint="")],
        run_id="run_1",
        max_attempts=2,
    )
    assert run.status == "completed"
    assert run.provider_status["mock"] == "success"
    assert run.provider_status["patent"] == "unconfigured"
    assert run.provider_status["crowdfunding"] == "unconfigured"
    assert len(run.sources) == 1


def test_phase2_research_run_persists_bounded_retry_queue():
    class RateLimitedProvider(MockSearchProvider):
        name = "limited"

        def search(self, query: str, limit: int = 5, **kwargs: Any):
            return [ResearchSource(title="limited rate limited", source_type="web_page", fact_type="unknown")]

    sleeps: list[float] = []
    run = execute_research_run("retry", [RateLimitedProvider()], run_id="retry_1", max_attempts=3, sleep_fn=sleeps.append)
    assert run.provider_status["limited"] == "rate_limited"
    assert run.provider_attempts["limited"] == 3
    assert [item["backoff_seconds"] for item in run.retry_queue] == [1, 2]
    assert sleeps == [1, 2]


def test_phase2_research_run_retries_transient_provider_failures():
    class FlakyProvider(MockSearchProvider):
        name = "flaky"

        def __init__(self):
            super().__init__()
            self.calls = 0

        def search(self, query: str, limit: int = 5, **kwargs: Any):
            self.calls += 1
            if self.calls == 1:
                return [ResearchSource(title="flaky search failed", source_type="web_page", fact_type="unknown")]
            return [ResearchSource(title="Recovered", url="https://example.test/recovered", source_type="web_page")]

    provider = FlakyProvider()
    sleeps: list[float] = []
    run = execute_research_run("retry failure", [provider], run_id="flaky_1", max_attempts=2, sleep_fn=sleeps.append)
    assert run.provider_status["flaky"] == "success"
    assert run.provider_attempts["flaky"] == 2
    assert run.retry_queue[0]["reason"] == "transient_failure"
    assert sleeps == [1]


def test_phase2_research_run_isolates_unexpected_provider_exception():
    class BrokenProvider(MockSearchProvider):
        name = "broken"
        source_type = "web_page"

        def search(self, query: str, limit: int = 5, **kwargs: Any):
            raise RuntimeError("provider crashed")

    run = execute_research_run("isolated", [BrokenProvider(), MockSearchProvider([])], run_id="broken_1", max_attempts=2)
    assert run.status == "blocked"
    assert run.provider_status["broken"] == "failed"
    assert run.provider_attempts["broken"] == 2
    assert "RuntimeError" in run.errors["broken"]


def test_community_provider_returns_normalized_metadata(monkeypatch):
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"hits": [{"title": "Discussion", "objectID": "42", "points": 7, "created_at": "2026-08-02T00:00:00Z"}]}

    import requests
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())
    result = CommunitySearchProvider().search("esp32", limit=1)
    assert result[0].source_type == "community"
    assert result[0].engagement == 7


def test_reddit_and_github_discussion_providers_preserve_platform_metadata(monkeypatch):
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    import requests

    def fake_get(url, *args, **kwargs):
        if "reddit.com" in url:
            return Response({"data": {"children": [{"data": {"title": "Reddit post", "url": "https://reddit.com/r/x/1", "score": 4, "num_comments": 3, "created_utc": 1, "selftext": "Opinion"}}]}})
        return Response({"items": [{"title": "GitHub discussion", "html_url": "https://github.com/x/y/discussions/1", "comments": 5, "body": "Discussion"}]})

    monkeypatch.setattr(requests, "get", fake_get)
    reddit = RedditSearchProvider().search("esp32", limit=1)
    github = GitHubDiscussionsProvider().search("esp32", limit=1)
    assert reddit[0].platform == "reddit"
    assert reddit[0].engagement == 7
    assert reddit[0].published_at.startswith("1970-01-01T00:00:01")
    assert github[0].platform == "github_discussions"
    assert github[0].engagement == 5


def test_patent_and_crowdfunding_providers_preserve_structured_metadata(monkeypatch):
    class Response:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    import requests

    def fake_get(url, *args, **kwargs):
        if "patent" in url:
            return Response({"results": [{
                "title": "Sensor patent", "publication_number": "US-123",
                "assignee": "Example Labs", "filing_date": "2025-01-02",
                "legal_status": "active", "url": "https://patents.example/US-123",
            }]})
        return Response({"results": [{
            "title": "Device campaign", "goal": "10000 USD", "pledged": "15000 USD",
            "backers": 321, "delivery_status": "delivered", "platform": "Kickstarter",
            "url": "https://crowdfunding.example/campaign",
        }]})

    monkeypatch.setattr(requests, "get", fake_get)
    patent = PatentSearchProvider(endpoint="https://patent.example/search").search("sensor", limit=1)[0]
    crowd = CrowdfundingSearchProvider(endpoint="https://crowdfunding.example/search").search("device", limit=1)[0]
    assert (patent.patent_number, patent.applicant, patent.legal_status) == ("US-123", "Example Labs", "active")
    assert (crowd.target_amount, crowd.raised_amount, crowd.backers, crowd.delivery_status, crowd.platform) == (
        "10000 USD", "15000 USD", 321, "delivered", "Kickstarter",
    )


def test_http_rate_limit_is_preserved_for_research_retry_queue(monkeypatch):
    """A real HTTP 429 must be distinguishable from an ordinary provider error."""
    import requests

    response = requests.Response()
    response.status_code = 429
    error = requests.HTTPError("too many requests", response=response)
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(error))

    result = GitHubSearchProvider(token="").search("esp32", limit=1)
    assert result[0].title == "github rate limited"
    assert "HTTP 429" in result[0].summary

    class LimitedGitHub(GitHubSearchProvider):
        def search(self, query: str, limit: int = 5, **kwargs: Any):
            return result

    run = execute_research_run("esp32", [LimitedGitHub(token="")], run_id="http_429", max_attempts=2)
    assert run.provider_status["github"] == "rate_limited"
    assert run.provider_attempts["github"] == 2
    assert run.retry_queue[0]["reason"] == "rate_limited"


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


def test_save_market_research_report_writes_market_md_server(
    project_manager, test_config: KyrozenConfig, report_data: dict[str, Any]
):
    # Server scenario: project_manager + config → docs/MARKET.md is written
    # into the project directory so the stage gate can detect it.
    project = project_manager.create(name="Test", goal="G")
    tool = SaveMarketResearchReportTool(project_manager, config=test_config)
    result = tool.execute("save", {"project_id": project.id, "report": report_data})
    assert result.success, result.error
    market_md = Path(test_config.project_dir(project.id)) / "docs" / "MARKET.md"
    assert market_md.exists()
    assert "Market Research Report" in market_md.read_text(encoding="utf-8")


def test_save_market_research_report_desktop_mode(tmp_path, report_data: dict[str, Any]):
    # Desktop scenario: no project_manager; config.workspace_root points at
    # the user-selected workspace. The report must still land in docs/MARKET.md.
    class _Cfg:
        workspace_root = str(tmp_path)

    tool = SaveMarketResearchReportTool(None, config=_Cfg())
    result = tool.execute("save", {"project_id": "any", "report": report_data})
    assert result.success, result.error
    assert (tmp_path / "docs" / "MARKET.md").exists()
    assert result.data.get("file", "").endswith("MARKET.md")


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
    app = make_authenticated_app(config, MockModel(["Done"]))
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
