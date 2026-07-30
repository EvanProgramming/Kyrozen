"""Regression tests for the report-producing stage-gate deliverable tools.

These reproduce the desktop scenario where ``project_manager`` is ``None`` and the
workspace is identified only via ``config.workspace_root``. Every tool must still
materialize its deliverable markdown file (so the stage gate detects it) and must
auto-confirm the paired confirmation item.
"""

from __future__ import annotations

from pathlib import Path

from kyrozen.tools.discovery_tools import SaveProblemBriefTool
from kyrozen.tools.planning_tools import SavePRDTool
from kyrozen.tools.development_tools import SaveTechnicalPlanTool
from kyrozen.tools.research.tools import SaveMarketResearchReportTool


class _FakeConfig:
    def __init__(self, ws: str) -> None:
        self.workspace_root = ws


def _make_store(root: str):
    from kyrozen.core.stagegate import StageGateStore

    return StageGateStore(Path(root) / ".kyrozen" / "stagegate.json")


def test_save_problem_brief_writes_problem_md_and_autoconfirms():
    import tempfile

    tmp = tempfile.mkdtemp()
    tool = SaveProblemBriefTool(project_manager=None, config=_FakeConfig(tmp))
    brief = {
        "problem": "用户难以管理多个 AI 编程工具",
        "target_users": ["独立开发者"],
        "value": "统一入口",
    }
    res = tool._execute("save", {"project_id": "p1", "brief": brief})
    assert res.success, res.error
    target = Path(tmp) / "docs" / "PROBLEM.md"
    assert target.exists(), "docs/PROBLEM.md was not written"
    store = _make_store(tmp)
    assert store.records.get("problem_statement", {}).get("detected") is True
    assert store.records.get("problem_confirmed", {}).get("confirmed") is True


def test_save_prd_writes_prd_md_and_autoconfirms():
    import tempfile

    tmp = tempfile.mkdtemp()
    tool = SavePRDTool(project_manager=None, config=_FakeConfig(tmp))
    prd = {
        "overview": "统一 AI 编程入口",
        "user_stories": ["作为用户，我希望…"],
        "functional_requirements": ["登录", "项目管理"],
        "non_functional_requirements": ["低延迟"],
        "mvp_scope": {},
        "out_of_scope": ["移动端"],
    }
    res = tool._execute("save", {"project_id": "p1", "prd": prd})
    assert res.success, res.error
    target = Path(tmp) / "PRD.md"
    assert target.exists(), "PRD.md was not written"
    store = _make_store(tmp)
    assert store.records.get("prd", {}).get("detected") is True
    # prd_confirmed is the hard-gate confirmation; auto-tick it.
    assert store.records.get("prd_confirmed", {}).get("confirmed") is True


def test_save_technical_plan_writes_tech_design_md_and_autoconfirms():
    import tempfile

    tmp = tempfile.mkdtemp()
    tool = SaveTechnicalPlanTool(project_manager=None, config=_FakeConfig(tmp))
    plan = {
        "application_type": "web_app",
        "architecture": "前后端分离",
        "frontend": "React",
        "backend": "FastAPI",
        "database": "Postgres",
        "apis": "/api/*",
        "deployment": "Docker",
        "dependencies": ["react", "fastapi"],
        "rationale": "易于迭代",
    }
    res = tool._execute("save", {"project_id": "p1", "plan": plan})
    assert res.success, res.error
    target = Path(tmp) / "docs" / "TECH_DESIGN.md"
    assert target.exists(), "docs/TECH_DESIGN.md was not written"
    store = _make_store(tmp)
    assert store.records.get("tech_design", {}).get("detected") is True
    assert store.records.get("design_confirmed", {}).get("confirmed") is True


def test_save_market_research_writes_market_md_and_autoconfirms():
    import tempfile

    tmp = tempfile.mkdtemp()
    tool = SaveMarketResearchReportTool(project_manager=None, config=_FakeConfig(tmp))
    report = {
        "project_id": "p1",
        "topic": "AI 编程助手市场",
        "summary": "市场增长迅速",
        "competitors": [{"name": "Cursor", "notes": "强"}],
        "opportunities": ["垂直场景"],
        "risks": ["巨头竞争"],
        "conclusion": "值得进入",
    }
    res = tool._execute("save", {"project_id": "p1", "report": report})
    assert res.success, res.error
    target = Path(tmp) / "docs" / "MARKET.md"
    assert target.exists(), "docs/MARKET.md was not written"
    store = _make_store(tmp)
    assert store.records.get("market_report", {}).get("detected") is True
    assert store.records.get("market_confirmed", {}).get("confirmed") is True
