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
from kyrozen.tools.development_tools import SaveTechnicalPlanTool, SaveChangelogTool
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
        "sources": [
            {"title": "Cursor 官网", "url": "https://www.cursor.com/"},
            {"title": "GitHub Trending", "url": "https://github.com/trending"},
        ],
    }
    res = tool._execute("save", {"project_id": "p1", "report": report})
    assert res.success, res.error
    target = Path(tmp) / "docs" / "MARKET.md"
    assert target.exists(), "docs/MARKET.md was not written"
    store = _make_store(tmp)
    assert store.records.get("market_report", {}).get("detected") is True
    assert store.records.get("market_confirmed", {}).get("confirmed") is True


def test_save_changelog_writes_changelog_md_and_autoconfirms():
    import tempfile

    tmp = tempfile.mkdtemp()
    tool = SaveChangelogTool(project_manager=None, config=_FakeConfig(tmp))
    changelog = {
        "version": "0.2.0",
        "date": "2026-07-30",
        "summary": "迭代改进：新增自动生成变更记录",
        "entries": [
            {"type": "Added", "text": "SaveChangelogTool 自动写 CHANGELOG.md"},
            {"type": "Fixed", "text": "阶段门禁未检测到报告文件"},
        ],
    }
    res = tool._execute("save", {"project_id": "p1", "changelog": changelog})
    assert res.success, res.error
    target = Path(tmp) / "CHANGELOG.md"
    assert target.exists(), "CHANGELOG.md was not written"
    content = target.read_text(encoding="utf-8")
    assert "Changelog" in content and "v0.2.0" in content
    store = _make_store(tmp)
    assert store.records.get("changelog", {}).get("detected") is True
    assert store.records.get("changelog_confirmed", {}).get("confirmed") is True


def test_save_market_research_without_evidence_not_confirmed():
    """Round-2 fix #94: a report carrying no external evidence (no http/https
    sources) must still be materialized (detected) but must NOT auto-confirm the
    market_confirmed gate, and must warn the caller."""
    import tempfile

    tmp = tempfile.mkdtemp()
    tool = SaveMarketResearchReportTool(project_manager=None, config=_FakeConfig(tmp))
    report = {
        "project_id": "p1",
        "topic": "AI 编程助手市场",
        "summary": "搜索失败，无可用结果",
        "competitors": [],
        "opportunities": [],
        "risks": [],
        "conclusion": "无法确定",
    }
    res = tool._execute("save", {"project_id": "p1", "report": report})
    assert res.success, res.error
    target = Path(tmp) / "docs" / "MARKET.md"
    assert target.exists(), "docs/MARKET.md was not written"
    store = _make_store(tmp)
    assert store.records.get("market_report", {}).get("detected") is True
    # No evidence -> the confirmation gate stays open.
    assert store.records.get("market_confirmed", {}).get("confirmed") is not True
    assert "warning" in res.data


def test_save_prd_rejects_hollow_prd():
    """Round-2 fix #94: a PRD whose required sections are placeholders (e.g. "无")
    must be rejected outright -- no PRD.md on disk, so the hard development gate
    stays unsatisfied."""
    import tempfile

    tmp = tempfile.mkdtemp()
    tool = SavePRDTool(project_manager=None, config=_FakeConfig(tmp))
    hollow = {
        "overview": "无",
        "user_stories": ["无"],
        "functional_requirements": ["无"],
        "non_functional_requirements": ["无"],
        "mvp_scope": {"features": ["无"]},
        "out_of_scope": ["无"],
    }
    res = tool._execute("save", {"project_id": "p1", "prd": hollow})
    assert not res.success, "hollow PRD should be rejected"
    assert not (Path(tmp) / "PRD.md").exists(), "hollow PRD must not be written"


def test_save_changelog_accepts_raw_content():
    import tempfile

    tmp = tempfile.mkdtemp()
    tool = SaveChangelogTool(project_manager=None, config=_FakeConfig(tmp))
    res = tool._execute(
        "save",
        {"project_id": "p1", "content": "# Changelog\n\n- **Added**: raw markdown path"},
    )
    assert res.success, res.error
    target = Path(tmp) / "CHANGELOG.md"
    assert target.exists()
    assert "raw markdown path" in target.read_text(encoding="utf-8")
