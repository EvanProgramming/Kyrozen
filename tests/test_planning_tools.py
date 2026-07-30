"""Tests for the real execution-planning tools (P0-R6).

Each Kyrozen agent must call save_plan to write a structured plan to
.kyrozen/PLAN.json *before* doing the work of a stage, and update_plan_step
to mark steps as in_progress / completed / failed.  This test pins:
- plan shape (stage/title/goal/steps) validation
- file persistence to .kyrozen/PLAN.json
- step status updates (in_progress/completed/failed) reflected in the file
- error paths (missing workspace, missing plan, unknown step, bad status)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kyrozen.tools.planning_tools import SavePlanTool, UpdatePlanStepTool


class _StubTool:
    def __init__(self) -> None:
        self.calls: list = []


def _make_save_tool(workspace: Path) -> tuple[SavePlanTool, _StubTool]:
    tools = _StubTool()
    config = type("Cfg", (), {"workspace_root": str(workspace)})()
    return SavePlanTool(project_manager=None, config=config), tools


def _make_update_tool(workspace: Path) -> UpdatePlanStepTool:
    config = type("Cfg", (), {"workspace_root": str(workspace)})()
    return UpdatePlanStepTool(project_manager=None, config=config)


def test_save_plan_persists_structured_file(tmp_path: Path) -> None:
    tool, _ = _make_save_tool(tmp_path)
    result = tool.execute(
        "save",
        {
            "project_id": "proj_test",
            "stage": "market_research",
            "title": "家庭购物清单竞品调研",
            "goal": "梳理 5 个主流家庭购物清单应用的功能和差异点",
            "steps": [
                {"id": "s1", "title": "搜索 5 个竞品", "detail": "Listonic/OurGroceries/Bring!/..."},
                {"id": "s2", "title": "记录核心功能", "detail": "增删改查 / 同步 / 提醒"},
                {"id": "s3", "title": "整理差异化建议"},
            ],
        },
    )
    assert result.success, result.error
    plan_path = Path(result.data["file"])
    assert plan_path.exists()
    assert plan_path.parent.name == ".kyrozen"
    data = json.loads(plan_path.read_text("utf-8"))
    assert data["stage"] == "market_research"
    assert data["goal"].startswith("梳理")
    assert [s["id"] for s in data["steps"]] == ["s1", "s2", "s3"]
    assert all(s["status"] == "pending" for s in data["steps"])


def test_update_plan_step_marks_in_progress_then_completed(tmp_path: Path) -> None:
    save_tool, _ = _make_save_tool(tmp_path)
    save_result = save_tool.execute(
        "save",
        {
            "project_id": "proj_test",
            "stage": "development",
            "title": "MVP 开发计划",
            "goal": "完成 MVP",
            "steps": [
                {"id": "s1", "title": "脚手架"},
                {"id": "s2", "title": "核心 API"},
                {"id": "s3", "title": "前端页面"},
            ],
        },
    )
    assert save_result.success

    update = _make_update_tool(tmp_path)
    in_progress = update.execute("update", {"project_id": "proj_test", "step_id": "s1", "status": "in_progress"})
    assert in_progress.success, in_progress.error
    done = update.execute("update", {"project_id": "proj_test", "step_id": "s1", "status": "completed"})
    assert done.success, done.error

    plan = json.loads((tmp_path / ".kyrozen" / "PLAN.json").read_text("utf-8"))
    s1 = next(s for s in plan["steps"] if s["id"] == "s1")
    s2 = next(s for s in plan["steps"] if s["id"] == "s2")
    assert s1["status"] == "completed"
    assert s2["status"] == "pending"


def test_update_plan_step_rejects_unknown_status(tmp_path: Path) -> None:
    save_tool, _ = _make_save_tool(tmp_path)
    save_tool.execute(
        "save",
        {
            "project_id": "proj_test",
            "stage": "iteration",
            "title": "迭代",
            "goal": "迭代",
            "steps": [{"id": "s1", "title": "step"}],
        },
    )
    update = _make_update_tool(tmp_path)
    res = update.execute("update", {"project_id": "proj_test", "step_id": "s1", "status": "half-baked"})
    assert not res.success
    assert "Invalid status" in res.error


def test_update_plan_step_rejects_unknown_step_id(tmp_path: Path) -> None:
    save_tool, _ = _make_save_tool(tmp_path)
    save_tool.execute(
        "save",
        {
            "project_id": "proj_test",
            "stage": "testing",
            "title": "测试",
            "goal": "测试",
            "steps": [{"id": "s1", "title": "step"}],
        },
    )
    update = _make_update_tool(tmp_path)
    res = update.execute("update", {"project_id": "proj_test", "step_id": "s999", "status": "completed"})
    assert not res.success
    assert "s999" in res.error


def test_update_plan_step_requires_existing_plan_file(tmp_path: Path) -> None:
    update = _make_update_tool(tmp_path)
    res = update.execute("update", {"project_id": "proj_test", "step_id": "s1", "status": "completed"})
    assert not res.success
    assert "PLAN.json" in res.error or "未" in res.error


def test_save_plan_rejects_unknown_stage() -> None:
    """The data model guards against arbitrary stage values."""
    from kyrozen.planning.plan import ExecutionPlan

    with pytest.raises(ValueError, match="Unknown plan stage"):
        ExecutionPlan(stage="not_a_stage", title="x", goal="y", steps=[])


def test_save_plan_requires_at_least_one_step(tmp_path: Path) -> None:
    tool, _ = _make_save_tool(tmp_path)
    res = tool.execute(
        "save",
        {"project_id": "proj_test", "stage": "development", "title": "t", "goal": "g", "steps": []},
    )
    assert not res.success
    assert "step" in res.error.lower() or "步骤" in res.error


def test_save_plan_rejects_unknown_step_status(tmp_path: Path) -> None:
    """Plan steps with bogus status should fail validation."""
    tool, _ = _make_save_tool(tmp_path)
    res = tool.execute(
        "save",
        {
            "project_id": "proj_test",
            "stage": "development",
            "title": "t",
            "goal": "g",
            "steps": [{"id": "s1", "title": "x", "status": "made-up"}],
        },
    )
    assert not res.success
    assert "status" in res.error.lower() or "Invalid" in res.error