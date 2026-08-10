from __future__ import annotations

import json

from kyrozen.memory import InMemoryMemory
from kyrozen.project.context import ProjectContextBuilder


def test_planning_context_includes_current_phase2_evidence_and_sources(project_manager):
    project = project_manager.create(
        name="Phase 2 context",
        goal="验证真实硬件串口工作流",
        project_type="embedded",
    )
    evidence = project_manager.save_artifact(
        project.id,
        "discovery_evidence",
        "Evidence 1",
        json.dumps({
            "claim": "用户需要在设备拔插后恢复串口观察",
            "classification": "fact",
            "status": "active",
            "source": "访谈记录",
        }, ensure_ascii=False),
    )
    project_manager.save_artifact(
        project.id,
        "research_source",
        "Research 1",
        json.dumps({
            "source_type": "github",
            "title": "真实项目讨论",
            "url": "https://github.com/example/discussion",
            "summary": "讨论了串口重连边界",
        }, ensure_ascii=False),
    )

    context = ProjectContextBuilder(project_manager, InMemoryMemory()).build_planning_context(project)

    assert f"evidence_id={evidence.id}" in context
    assert "用户需要在设备拔插后恢复串口观察" in context
    assert "https://github.com/example/discussion" in context
    assert "Only use the evidence and research rows listed above" in context
