"""Tests for Kyrozen Phase 3 Problem Discovery system."""

from __future__ import annotations

import json
import time
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.config import KyrozenConfig
from kyrozen.discovery.brief import ProblemBrief
from kyrozen.discovery.evidence import Evidence, assess_confidence
from kyrozen.discovery.question_engine import QuestionEngine
from kyrozen.project import KyrozenDatabase, ProjectManager
from kyrozen.phase2.workbench import _default_next_action

from tests.conftest import MockModel, make_authenticated_app


def test_problem_brief_merge():
    brief = ProblemBrief(title="T1", surface_problem="sp")
    update = ProblemBrief(target_user="runners", deep_need="focus")
    merged = brief.merge(update)
    assert merged.title == "T1"
    assert merged.surface_problem == "sp"
    assert merged.target_user == "runners"
    assert merged.deep_need == "focus"


def test_problem_brief_markdown_includes_evidence_and_open_questions():
    brief = ProblemBrief(
        title="问题", decision="continue_research", evidence_ids=["ev-1"],
        counter_evidence_ids=["ev-2"], unresolved_questions=["样本是否足够？"],
    )
    markdown = brief.to_markdown()
    assert "支持证据" in markdown and "`ev-1`" in markdown
    assert "反对证据" in markdown and "`ev-2`" in markdown
    assert "未解决问题" in markdown and "样本是否足够" in markdown


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


def test_problem_brief_persists_evidence_references_and_rejects_missing_ids(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "Brief Evidence Links"}).json()["id"]
    support = api_client.post(f"/api/projects/{pid}/evidence", json={"claim": "支持问题", "evidence_type": "interview"}).json()
    counter = api_client.post(f"/api/projects/{pid}/evidence", json={"claim": "反对问题", "evidence_type": "observation"}).json()
    saved = api_client.post("/api/tools/execute", json={
        "tool": "save_problem_brief", "action": "save", "parameters": {
            "project_id": pid,
            "brief": {
                "title": "有证据的问题", "surface_problem": "需要核对", "decision": "continue_research",
                "evidence_ids": [support["artifact_id"]],
                "counter_evidence_ids": [counter["artifact_id"]],
                "unresolved_questions": ["样本是否足够？"],
            },
        },
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["success"] is True
    state = api_client.get(f"/api/projects/{pid}/problem-discovery/state").json()
    assert state["brief"]["evidence_ids"] == [support["artifact_id"]]
    assert state["brief"]["counter_evidence_ids"] == [counter["artifact_id"]]
    assert state["brief"]["unresolved_questions"] == ["样本是否足够？"]

    missing = api_client.post("/api/tools/execute", json={
        "tool": "save_problem_brief", "action": "save", "parameters": {
            "project_id": pid, "brief": {"evidence_ids": ["missing-evidence"]},
        },
    })
    assert missing.status_code == 200
    assert missing.json()["success"] is False


def test_phase2_evidence_workbench_persists_and_restores(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Evidence Workbench"})
    pid = create.json()["id"]

    created = api_client.post(f"/api/projects/{pid}/evidence", json={
        "claim": "三名社区组织者在活动后仍需人工核对报名名单",
        "source": "user_statement",
        "evidence_type": "interview",
        "target_audience": "社区组织者",
        "related_question": "活动结束后最耗时的工作是什么？",
        "confidence": "high",
    })
    assert created.status_code == 200
    evidence = created.json()
    assert evidence["version"] == 1
    assert evidence["evidence_type"] == "interview"

    snapshot = api_client.get(f"/api/projects/{pid}/phase2/workbench")
    assert snapshot.status_code == 200
    assert snapshot.json()["evidence"]["active_count"] == 1
    assert snapshot.json()["phase2_completion"]["ready"] is False
    assert "至少一条真实研究来源" in snapshot.json()["phase2_completion"]["missing"]
    assert snapshot.json()["evidence"]["by_type"] == {"interview": 1}

    stale = api_client.patch(f"/api/projects/{pid}/evidence/{evidence['artifact_id']}", json={"status": "invalid", "expected_version": 99})
    assert stale.status_code == 409
    updated = api_client.patch(f"/api/projects/{pid}/evidence/{evidence['artifact_id']}", json={"status": "invalid", "expected_version": 1})
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert api_client.get(f"/api/projects/{pid}/evidence").json() == []
    assert len(api_client.get(f"/api/projects/{pid}/evidence", params={"include_invalid": "true"}).json()) == 1

    restored = api_client.post(f"/api/projects/{pid}/evidence/{updated.json()['artifact_id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert api_client.get(f"/api/projects/{pid}/evidence").json()[0]["claim"].startswith("三名社区")


def test_phase2_workbench_projects_research_provider_status_by_category(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "研究覆盖状态"}).json()["id"]
    run = {
        "run_id": "run-status-1", "query": "ESP32", "status": "completed",
        "provider_status": {
            "tavily": "unconfigured", "serper": "success", "github": "failed",
            "semantic_scholar": "rate_limited", "patent": "unconfigured",
            "crowdfunding": "unconfigured", "community": "success",
            "reddit": "failed", "github_discussions": "failed",
        }, "sources": [], "retry_queue": [], "errors": {},
    }
    saved = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "research_run", "title": "Research Run run-status-1",
        "content": json.dumps(run), "change_reason": "Seed",
    })
    assert saved.status_code == 200
    research = api_client.get(f"/api/projects/{pid}/phase2/workbench").json()["research"]
    assert research["provider_status"] == {
        "web": "success", "github": "failed", "paper": "rate_limited",
        "patent": "unconfigured", "crowdfunding": "unconfigured", "community": "success",
    }


def test_phase2_workbench_uses_newest_research_run_status(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "最新研究运行"}).json()["id"]
    first = {
        "run_id": "run-old", "status": "completed",
        "provider_status": {"tavily": "success", "serper": "success", "github": "success", "semantic_scholar": "success", "patent": "success", "crowdfunding": "success", "community": "success"},
        "sources": [], "retry_queue": [], "errors": {},
    }
    second = {
        "run_id": "run-new", "status": "blocked",
        "provider_status": {"tavily": "unconfigured", "serper": "unconfigured", "github": "failed", "semantic_scholar": "rate_limited", "patent": "unconfigured", "crowdfunding": "unconfigured", "community": "failed"},
        "sources": [], "retry_queue": [], "errors": {},
    }
    for run in (first, second):
        response = api_client.post(f"/api/projects/{pid}/artifacts", json={
            "type": "research_run", "title": f"Research Run {run['run_id']}",
            "content": json.dumps(run), "change_reason": "Seed",
        })
        assert response.status_code == 200
        time.sleep(0.01)
    research = api_client.get(f"/api/projects/{pid}/phase2/workbench").json()["research"]
    assert research["provider_status"]["web"] == "unconfigured"
    assert research["provider_status"]["github"] == "failed"
    assert research["provider_status"]["paper"] == "rate_limited"


def test_phase2_workbench_treats_date_only_research_as_fresh(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "研究新鲜度"}).json()["id"]
    source = {
        "title": "今天的公开资料",
        "url": "https://example.com/today",
        "source_type": "web_page",
        "publish_date": date.today().isoformat(),
        "summary": "真实来源摘要",
        "fact_type": "fact",
    }
    saved = api_client.post(f"/api/projects/{pid}/research/sources", json={"source": source})
    assert saved.status_code == 200, saved.text
    freshness = api_client.get(f"/api/projects/{pid}/phase2/workbench").json()["research"]["freshness"]
    assert freshness["fresh_7d"] == 1
    assert freshness["older_or_unknown"] == 0


def test_phase2_readiness_requires_absolute_research_urls_and_counts_conflicts(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "研究链接与冲突"}).json()["id"]
    invalid = api_client.post(f"/api/projects/{pid}/research/sources", json={
        "source": {"title": "伪来源", "url": "not-a-url", "source_type": "web_page"},
    })
    assert invalid.status_code == 422
    valid_sources = [
        {"title": "支持来源", "url": "https://example.com/positive", "source_type": "web_page", "related_claim": "同一主张", "polarity": "positive"},
        {"title": "反对来源", "url": "https://example.com/negative", "source_type": "web_page", "related_claim": "同一主张", "polarity": "negative"},
    ]
    for source in valid_sources:
        assert api_client.post(f"/api/projects/{pid}/research/sources", json={"source": source}).status_code == 200
    research = api_client.get(f"/api/projects/{pid}/phase2/workbench").json()["research"]
    assert research["citation_count"] == 2
    assert research["conflict_count"] == 1
    completion = api_client.get(f"/api/projects/{pid}/phase2/workbench").json()["phase2_completion"]
    assert "至少一条真实研究来源" not in completion["missing"]


def test_phase2_workbench_projects_structured_hardware_artifacts(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "硬件工作台投影"}).json()["id"]
    for artifact_type, title, content in (
        ("bom", "Bill of Materials", {"items": [{"model": "ESP32-DEV", "quantity": 1}]}),
        ("wiring_design", "Wiring Design", {"connections": [{"device": "LED", "pin": "A", "target": "GPIO2", "target_type": "controller", "voltage": "3.3V", "current_direction": "out"}]}),
    ):
        saved = api_client.post(f"/api/projects/{pid}/artifacts", json={
            "type": artifact_type, "title": title, "content": json.dumps(content), "change_reason": "Seed",
        })
        assert saved.status_code == 200
    hardware = api_client.get(f"/api/projects/{pid}/phase2/workbench").json()["hardware"]
    assert hardware["bom"]["items"][0]["model"] == "ESP32-DEV"
    assert hardware["wiring"]["connections"][0]["target"] == "GPIO2"
    artifacts = api_client.get(f"/api/projects/{pid}/phase2/workbench").json()["artifacts"]
    assert {item["type"] for item in artifacts} == {"bom", "wiring_design"}


def test_phase2_workbench_exposes_complete_solution_comparison(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "方案投影一致性"}).json()["id"]
    dimensions = ["time", "cost", "user_value", "technical_risk", "maintenance_cost", "data_risk", "validation_difficulty"]
    comparison = {
        "solutions": [
            {
                "name": name,
                "solution": name,
                "dimension_scores": {dimension: 3 for dimension in dimensions},
                "evidence_ids": [],
            }
            for name in ("保守方案", "平衡方案", "激进方案")
        ],
        "comparison_dimensions": dimensions,
        "recommendation": "平衡方案",
        "recommendation_reason": "统一投影",
    }
    saved = api_client.post(f"/api/projects/{pid}/solutions", json={
        "comparison": comparison,
        "action": "save",
    })
    assert saved.status_code == 200

    projected = api_client.get(f"/api/projects/{pid}/phase2/workbench")
    assert projected.status_code == 200
    solutions = projected.json()["solutions"]
    assert solutions["count"] == 3
    assert solutions["confirmed"] is False
    assert solutions["comparison"]["recommendation"] == "平衡方案"
    assert [item["name"] for item in solutions["comparison"]["solutions"]] == ["保守方案", "平衡方案", "激进方案"]


def test_hybrid_workbench_exposes_independent_parallel_tracks(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "并行混合工作流"}).json()["id"]
    confirmed = api_client.post(f"/api/projects/{pid}/workflow-confirm", json={"project_type": "hybrid"})
    assert confirmed.status_code == 200
    tracks = api_client.get(f"/api/projects/{pid}/phase2/workbench").json()["parallel_tracks"]
    assert set(tracks) == {"software", "hardware", "protocol", "integration"}
    assert all(item["state"] == "pending" for item in tracks.values())
    assert tracks["software"]["stages"] == ["development", "testing"]
    assert tracks["hardware"]["stages"] == [
        "hardware_design", "procurement", "maker", "firmware", "hardware_testing",
    ]


def test_hybrid_tracks_persist_independent_progress_and_require_deliverables(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "独立混合轨道"}).json()["id"]
    assert api_client.post(f"/api/projects/{pid}/workflow-confirm", json={"project_type": "hybrid"}).status_code == 200
    evidence = api_client.post(f"/api/projects/{pid}/evidence", json={
        "claim": "用户需要设备状态和软件控制共同验证", "evidence_type": "interview",
    }).json()
    research_source = api_client.post(f"/api/projects/{pid}/research/sources", json={
        "source": {"title": "混合设备公开资料", "url": "https://example.com/hybrid-research", "source_type": "web_page", "summary": "真实公开来源"},
    })
    assert research_source.status_code == 200, research_source.text
    dimensions = ["time", "cost", "user_value", "technical_risk", "maintenance_cost", "data_risk", "validation_difficulty"]
    solution = api_client.post(f"/api/projects/{pid}/solutions", json={
        "action": "select",
        "comparison": {
            "solutions": [{"name": name, "solution": name, "dimension_scores": {dimension: 3 for dimension in dimensions}, "evidence_ids": [evidence["artifact_id"]]} for name in ("保守方案", "平衡方案", "激进方案")],
            "comparison_dimensions": dimensions,
            "recommendation": "平衡方案",
            "recommendation_reason": "先验证核心价值",
        },
    })
    assert solution.status_code == 200
    assert api_client.get(f"/api/projects/{pid}/phase2/workbench").json()["solutions"]["confirmed"] is True

    activated = api_client.post(f"/api/projects/{pid}/phase2/tracks/software/advance", json={})
    assert activated.status_code == 200, activated.text
    assert activated.json()["state"]["current_stage"] == "development"
    blocked = api_client.post(f"/api/projects/{pid}/phase2/tracks/software/advance", json={
        "expected_version": activated.json()["version"],
    })
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["state"]["current_stage"] == "testing"
    blocked_testing = api_client.post(f"/api/projects/{pid}/phase2/tracks/software/advance", json={
        "expected_version": blocked.json()["version"],
    })
    assert blocked_testing.status_code == 409
    test_artifact = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "test_result", "title": "Software Test Result",
        "content": json.dumps({"test_case_id": "TC-1", "result": "passed"}),
    })
    assert test_artifact.status_code == 200
    test_plan = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "test_plan", "title": "Software Test Plan",
        "content": json.dumps({"scope": "软件核心旅程"}),
    })
    assert test_plan.status_code == 200
    completed = api_client.post(f"/api/projects/{pid}/phase2/tracks/software/advance", json={
        "expected_version": blocked.json()["version"],
    })
    assert completed.status_code == 200, completed.text
    assert completed.json()["state"]["completed_stages"] == ["development", "testing"]

    protocol_blocked = api_client.post(f"/api/projects/{pid}/phase2/tracks/protocol/advance", json={})
    assert protocol_blocked.status_code == 409
    integration_blocked = api_client.post(f"/api/projects/{pid}/phase2/tracks/integration/advance", json={})
    assert integration_blocked.status_code == 409
    tracks = api_client.get(f"/api/projects/{pid}/phase2/workbench").json()["parallel_tracks"]
    assert tracks["software"]["state"] == "completed"
    assert tracks["software"]["current_stage"] == "testing"


def test_hybrid_track_state_cannot_be_forged_through_generic_artifact_api(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "轨道状态防绕过"}).json()["id"]
    forged = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "workflow_track_state", "title": "Hybrid Workflow Track State",
        "content": json.dumps({"tracks": {"software": {"state": "completed"}}}),
    })
    assert forged.status_code == 422


@pytest.mark.parametrize("artifact_type", ["solution_comparison", "solution_decision", "protocol_confirmation", "protocol_connection_model", "protocol_scenarios"])
def test_gate_artifacts_cannot_be_forged_through_generic_api(api_client: TestClient, artifact_type: str):
    pid = api_client.post("/api/projects", json={"name": f"门禁伪造-{artifact_type}"}).json()["id"]
    response = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": artifact_type, "title": "Protected Gate Artifact", "content": json.dumps({"confirmed": True, "action": "select"}),
    })
    assert response.status_code == 422


@pytest.mark.parametrize("stage, expected", [
    ("development", "开始软件实现"),
    ("testing", "运行软件测试并记录回归"),
    ("procurement", "整理 BOM 并记录采购状态"),
    ("maker", "按 Maker 步骤装配并确认结果"),
    ("firmware", "编译并准备上传固件"),
    ("hardware_testing", "发现设备并执行硬件测试"),
    ("protocol_design", "确认版本化软硬件协议"),
    ("integration_testing", "运行软硬件集成测试"),
])
def test_phase2_next_action_uses_current_workflow_stage(stage: str, expected: str):
    from types import SimpleNamespace

    project = SimpleNamespace(current_stage=stage, next_steps="")
    assert _default_next_action(project)["label"] == expected


def test_phase2_readiness_uses_newest_validation_artifact(api_client: TestClient):
    project = api_client.post("/api/projects", json={"name": "最新验证报告"}).json()
    pid = project["id"]
    for index in range(1, 4):
        response = api_client.post("/api/feedback", json={
            "project_id": pid, "type": "experience", "description": f"反馈 {index}",
            "participant_id": f"P-{index}", "user_type": "目标用户", "task": "完成核心任务",
            "completed": True,
        })
        assert response.status_code == 200
    valid = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "validation_report", "title": "Validation Report",
        "content": json.dumps({
            "conclusion": "continue_release",
            "user_feedback": [
                {"participant_id": f"P-{index}", "user_type": "目标用户", "task": "完成核心任务"}
                for index in range(1, 4)
            ],
        }),
    })
    assert valid.status_code == 200
    newest_invalid = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "validation_report", "title": "Validation Report",
        "content": json.dumps({"conclusion": ""}),
    })
    assert newest_invalid.status_code == 200
    snapshot = api_client.get(f"/api/projects/{pid}/phase2/workbench").json()
    assert "三名不同目标用户和最终验证报告" in snapshot["phase2_completion"]["missing"]


def test_hybrid_completion_requires_persisted_protocol_scenarios(api_client: TestClient):
    project = api_client.post("/api/projects", json={"name": "混合协议门禁", "project_type": "hybrid"}).json()
    pid = project["id"]
    snapshot = api_client.get(f"/api/projects/{pid}/phase2/workbench").json()
    assert snapshot["phase2_completion"]["protocol_scenarios_ready"] is False
    assert "协议正常、离线、重连、重复、错误、版本不兼容六场景通过" in snapshot["phase2_completion"]["missing"]
    assert snapshot["phase2_completion"]["parallel_tracks_ready"] is False
    assert "软件、硬件、协议和集成四条混合轨道均已完成" in snapshot["phase2_completion"]["missing"]


def test_evidence_impact_and_merge_rewrite_problem_brief_references(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "Evidence Merge"}).json()["id"]
    source = api_client.post(f"/api/projects/{pid}/evidence", json={"claim": "原始访谈证据", "evidence_type": "interview"}).json()
    target = api_client.post(f"/api/projects/{pid}/evidence", json={"claim": "合并目标证据", "evidence_type": "observation"}).json()
    brief = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "problem_brief", "title": "Problem Brief",
        "content": json.dumps({"title": "问题", "evidence_ids": [source["artifact_id"]], "counter_evidence_ids": []}),
    })
    assert brief.status_code == 200

    impact = api_client.get(f"/api/projects/{pid}/evidence/{source['artifact_id']}/impact")
    assert impact.status_code == 200
    assert any(item["category"] == "Problem Brief" for item in impact.json()["affected"])

    merged = api_client.post(f"/api/projects/{pid}/evidence/{source['artifact_id']}/merge", json={"target_evidence_id": target["artifact_id"]})
    assert merged.status_code == 200, merged.text
    assert merged.json()["count"] == 1
    current_brief = api_client.get(f"/api/projects/{pid}/artifacts").json()
    brief_versions = [item for item in current_brief if item["type"] == "problem_brief"]
    assert any(target["artifact_id"] in item["content"] for item in brief_versions)
    assert api_client.get(f"/api/projects/{pid}/evidence", params={"include_invalid": "true"}).json()


def test_evidence_delete_requires_impact_confirmation_and_is_restorable(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "可恢复删除证据"}).json()["id"]
    evidence = api_client.post(
        f"/api/projects/{pid}/evidence",
        json={"claim": "待删除证据", "evidence_type": "interview"},
    ).json()
    evidence_id = evidence["artifact_id"]

    blocked = api_client.delete(f"/api/projects/{pid}/evidence/{evidence_id}", params={"expected_version": 1})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["impact"]["evidence_id"] == evidence_id

    deleted = api_client.delete(
        f"/api/projects/{pid}/evidence/{evidence_id}",
        params={"expected_version": 1, "confirm_impact": "true"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["status"] == "deleted"
    assert api_client.get(f"/api/projects/{pid}/evidence").json() == []
    restored = api_client.post(f"/api/projects/{pid}/evidence/{deleted.json()['artifact_id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"


def test_project_workflow_is_suggested_and_confirmed(api_client: TestClient):
    create = api_client.post("/api/projects", json={
        "name": "ESP32 活动灯",
        "description": "通过 ESP32 传感器控制灯光，并提供网页控制面板",
    })
    assert create.status_code == 200
    pid = create.json()["id"]

    suggestion = api_client.get(f"/api/projects/{pid}/workflow-suggestion")
    assert suggestion.status_code == 200
    assert suggestion.json()["project_type"] == "hybrid"

    confirmed = api_client.post(f"/api/projects/{pid}/workflow-confirm", json={
        "project_type": "hybrid",
        "type_source": "user_confirmed",
    })
    assert confirmed.status_code == 200
    assert confirmed.json()["project_type"] == "hybrid"
    assert confirmed.json()["type_confirmed"] is True
    assert "protocol_design" in confirmed.json()["workflow_stages"]
    assert confirmed.json()["workflow_stages"] == [
        "problem_discovery", "market_research", "product_definition",
        "solution_design", "protocol_design", "development", "testing",
        "hardware_design", "procurement", "maker", "firmware",
        "hardware_testing", "integration_testing", "iteration",
    ]

    bypass = api_client.put(f"/api/projects/{pid}", json={"project_type": "software"})
    assert bypass.status_code == 409


def test_hybrid_protocol_confirmation_is_versioned_and_project_scoped(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Protocol project", "description": "ESP32 device with web app"})
    assert create.status_code == 200
    pid = create.json()["id"]
    assert api_client.post(f"/api/projects/{pid}/workflow-confirm", json={"project_type": "hybrid"}).status_code == 200
    response = api_client.post(f"/api/projects/{pid}/protocol/confirm", json={
        "protocol": {"protocol_version": "1.0", "message_type": "telemetry", "fields": {"value": {"unit": "celsius"}}},
        "affected_files": ["hardware/firmware/src/protocol.h"],
        "affected_tasks": ["protocol-review"],
    })
    assert response.status_code == 200, response.text
    assert response.json()["protocol"]["protocol_version"] == "1.0"
    artifacts = api_client.get(f"/api/projects/{pid}/artifacts").json()
    assert any(item["type"] == "protocol_confirmation" for item in artifacts)

    stale = api_client.post(f"/api/projects/{pid}/protocol/confirm", json={
        "protocol": {"protocol_version": "1.1", "message_type": "telemetry", "fields": {"value": {"unit": "celsius"}}},
        "expected_version": 99,
    })
    assert stale.status_code == 409


def test_phase2_mutations_reject_stale_research_and_defect_versions(api_client: TestClient):
    pid = api_client.post("/api/projects", json={"name": "Versioned Phase 2"}).json()["id"]
    source = {
        "title": "A source",
        "url": "https://example.com/source",
        "source_type": "web_page",
        "summary": "Initial source",
    }
    saved = api_client.post(f"/api/projects/{pid}/research/sources", json={"source": source})
    assert saved.status_code == 200, saved.text
    stale_source = api_client.post(f"/api/projects/{pid}/research/sources", json={
        "source": {**source, "summary": "Changed"},
        "expected_version": 99,
    })
    assert stale_source.status_code == 409

    defect = api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "defect", "title": "Defect: serial", "content": json.dumps({
            "title": "serial", "status": "open", "owner": "", "reproduction_steps": [],
            "expected": "output", "actual": "none", "regression_result_id": "",
        }),
    })
    assert defect.status_code == 200, defect.text
    defect_id = defect.json()["id"]
    stale_defect = api_client.patch(f"/api/projects/{pid}/defects/{defect_id}", json={
        "status": "in_progress", "expected_version": 99,
    })
    assert stale_defect.status_code == 409


def test_record_evidence_tool_falls_back_to_workspace_when_artifact_store_fails(tmp_path):
    from kyrozen.tools.discovery_tools import RecordEvidenceTool

    class FailingProjectManager:
        def save_artifact(self, **kwargs):
            raise RuntimeError("cloud unavailable")

    config = KyrozenConfig(workspace_root=str(tmp_path))
    result = RecordEvidenceTool(FailingProjectManager(), config=config).execute(
        "record",
        {
            "project_id": "proj-local",
            "claim": "用户在微信群接龙报名",
            "source": "user_statement",
        },
    )

    assert result.success is True
    assert result.data["cloud_sync"] is False
    assert list((tmp_path / ".kyrozen" / "evidence").glob("*.json"))


def test_record_evidence_tool_works_without_cloud_project_manager(tmp_path):
    from kyrozen.tools.discovery_tools import RecordEvidenceTool

    result = RecordEvidenceTool(None, config=KyrozenConfig(workspace_root=str(tmp_path))).execute(
        "record",
        {
            "project_id": "proj-local",
            "claim": "用户通过微信群报名",
            "source": "user_statement",
        },
    )

    assert result.success is True


def test_assess_confidence_reads_local_problem_brief_without_cloud_project_manager(tmp_path):
    from kyrozen.tools.discovery_tools import AssessConfidenceTool

    problem_dir = tmp_path / "docs"
    problem_dir.mkdir()
    (problem_dir / "PROBLEM.md").write_text(
        "**目标用户**：社区组织者\n**使用场景**：周末活动\n**表面问题**：统计人数困难\n"
        "**深层需求**：准确掌握报名人数\n**当前解决方案**：微信群接龙\n"
        "**当前方案痛点**：需要人工统计\n",
        encoding="utf-8",
    )

    result = AssessConfidenceTool(None, config=KyrozenConfig(workspace_root=str(tmp_path))).execute(
        "assess", {"project_id": "proj-local"}
    )

    assert result.success is True
    assert result.data["confidence"] == "high"


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
