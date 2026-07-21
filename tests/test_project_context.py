"""Tests for ProjectContextBuilder."""

from __future__ import annotations

import os

from kyrozen.memory import InMemoryMemory
from kyrozen.project import ProjectContextBuilder, ProjectManager
from kyrozen.project.db import KyrozenDatabase


def test_context_contains_project_info(temp_dir: str):
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    pm = ProjectManager(db)
    p = pm.create(name="智能跑步设备", goal="改善运动音乐体验")
    p.update(current_stage="problem_discovery", next_steps="继续分析目标用户")
    pm.update(p.id, current_stage=p.current_stage, next_steps=p.next_steps)

    builder = ProjectContextBuilder(pm, InMemoryMemory())
    ctx = builder.build(p)

    assert "[Project Context]" in ctx
    assert "Project: 智能跑步设备" in ctx
    assert "Goal: 改善运动音乐体验" in ctx
    assert "Current Stage: problem_discovery" in ctx
    assert "Next Steps: 继续分析目标用户" in ctx
    assert "[User Message]" in ctx


def test_context_includes_recent_tasks_and_decisions(temp_dir: str):
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    pm = ProjectManager(db)
    p = pm.create(name="CtxTest", goal="G")

    from kyrozen.core.task import TaskManager

    tm = TaskManager(db=db)
    t = tm.create(title="Research sensors", project_id=p.id)
    t.update_status("completed")
    tm.update(t)

    pm.add_decision(p.id, decision="Use ESP32", reason="WiFi + BLE")

    builder = ProjectContextBuilder(pm, InMemoryMemory())
    ctx = builder.build(p)

    assert "Research sensors (completed)" in ctx
    assert "Use ESP32" in ctx


def test_context_includes_project_memories(temp_dir: str):
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    pm = ProjectManager(db)
    p = pm.create(name="MemoryTest", goal="G")

    mem = InMemoryMemory()
    mem.save("project", f"MemoryTest: 用户已经购买ESP32-S3", project_id=p.id)
    mem.save("project", f"MemoryTest: 项目预算限制100美元", project_id=p.id)

    builder = ProjectContextBuilder(pm, mem)
    ctx = builder.build(p, memory=mem)

    assert "用户已经购买ESP32-S3" in ctx
    assert "项目预算限制100美元" in ctx


def test_context_builder_for_missing_project(temp_dir: str):
    db = KyrozenDatabase(os.path.join(temp_dir, "kyrozen.db"))
    pm = ProjectManager(db)
    builder = ProjectContextBuilder(pm, InMemoryMemory())
    assert builder.build_for_project_id("nonexistent") is None
