"""Read models shared by the Phase 2 project workbench.

The projection deliberately reads versioned project artifacts instead of
maintaining a second database. This keeps refresh/reopen behavior deterministic
while the individual research, hardware and testing centers are expanded.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from collections import Counter
from typing import Any
from urllib.parse import urlparse

from kyrozen.discovery.evidence import Evidence
from kyrozen.project.workflow import tracks_for


def _json(content: str) -> dict[str, Any] | None:
    try:
        value = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _is_openable_url(value: Any) -> bool:
    """Accept only absolute HTTP(S) URLs as external research citations."""
    try:
        parsed = urlparse(str(value).strip())
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _default_next_action(project: Any) -> dict[str, str]:
    """Return a type-aware action when the project has no custom next step."""
    if str(getattr(project, "next_steps", "") or "").strip():
        return {
            "label": project.next_steps,
            "stage": project.current_stage,
            "reason": "项目已记录下一步",
        }
    actions = {
        "problem_discovery": ("完成问题探索并记录有效证据", "先确认问题、目标用户和可验证事实"),
        "market_research": ("运行市场研究并检查来源覆盖", "研究结果必须来自真实来源"),
        "product_definition": ("完成产品定义", "把问题证据转化为可验证的产品边界"),
        "solution_design": ("确认保守、平衡或激进方案", "未确认方案前不能进入实现"),
        "protocol_design": ("确认版本化软硬件协议", "混合项目必须先确认消息字段和兼容边界"),
        "development": ("开始软件实现", "进入软件开发或混合项目的软件轨道"),
        "testing": ("运行软件测试并记录回归", "验证核心任务、错误输入和持久化"),
        "hardware_design": ("完成硬件方案和接线安全约束", "明确板卡、电源、引脚和禁止条件"),
        "procurement": ("整理 BOM 并记录采购状态", "装配前需要确认精确型号、数量和替代件"),
        "maker": ("按 Maker 步骤装配并确认结果", "每一步都要保存预期结果和安全提示"),
        "firmware": ("编译并准备上传固件", "固件运行前必须保留工具链和版本记录"),
        "hardware_testing": ("发现设备并执行硬件测试", "需要真实串口、编译、上传、观察和拔插恢复证据"),
        "integration_testing": ("运行软硬件集成测试", "验证协议、离线、重连、重复消息和版本兼容"),
        "iteration": ("根据反馈创建迭代任务", "只有真实验证反馈才能形成发布结论"),
    }
    label, reason = actions.get(project.current_stage, ("继续当前阶段", "等待当前阶段的真实交付"))
    return {"label": label, "stage": project.current_stage, "reason": reason}


def build_workbench_snapshot(project: Any, project_manager: Any) -> dict[str, Any]:
    all_artifacts = project_manager.list_artifacts(project.id)
    # ProjectManager keeps immutable versions. A workbench must project the
    # latest version of each logical artifact, otherwise an invalidated record
    # reappears beside its replacement after refresh.
    latest_by_key: dict[tuple[str, str], Any] = {}
    for artifact in all_artifacts:
        key = (artifact.type, artifact.title)
        previous = latest_by_key.get(key)
        if previous is None or artifact.version > previous.version:
            latest_by_key[key] = artifact
    artifacts = list(latest_by_key.values())
    decisions = project_manager.list_decisions(project.id)
    evidence: list[dict[str, Any]] = []
    research_sources: list[dict[str, Any]] = []
    research_status = Counter()
    research_runs: list[dict[str, Any]] = []
    solution_candidates: list[dict[str, Any]] = []
    solution_impacts: list[dict[str, Any]] = []
    testing: dict[str, Any] = {}
    defects: list[dict[str, Any]] = []
    hardware: dict[str, Any] = {}
    user_feedback: list[dict[str, Any]] = []
    problem_brief: dict[str, Any] | None = None

    for artifact in artifacts:
        data = _json(artifact.content)
        if artifact.type == "discovery_evidence" and data:
            try:
                item = Evidence.from_dict(data).to_dict()
            except ValueError:
                item = data
            item.update({"artifact_id": artifact.id, "version": artifact.version, "title": artifact.title})
            evidence.append(item)
        elif artifact.type == "problem_brief" and data:
            problem_brief = dict(data)
            problem_brief.update({"artifact_id": artifact.id, "version": artifact.version, "title": artifact.title})
        elif artifact.type == "market_research_report" and data:
            for source in data.get("sources", []):
                if isinstance(source, dict):
                    research_sources.append(source)
                    research_status[source.get("source_type", "unknown")] += 1
        elif artifact.type == "research_source" and data:
            research_sources.append(data)
            research_status[data.get("source_type", "unknown")] += 1
        elif artifact.type == "research_run" and data:
            run_data = dict(data)
            # Persistence adapters return artifacts newest-first, but the
            # projection must not depend on that implementation detail when
            # selecting the run whose provider status drives readiness.
            run_data["_artifact_updated_at"] = artifact.updated_at
            research_runs.append(run_data)
        elif artifact.type == "solution_comparison" and data:
            solution_candidates = list(data.get("solutions") or data.get("candidates") or [])
        elif artifact.type == "solution_impact" and data:
            item = dict(data)
            item.update({"artifact_id": artifact.id, "version": artifact.version, "title": artifact.title})
            solution_impacts.append(item)
        elif artifact.type.startswith("hardware_") and data:
            hardware[artifact.type.removeprefix("hardware_")] = data
        elif artifact.type in {"hardware_architecture", "bom", "wiring_design", "firmware_project", "hardware_acceptance"} and data:
            hardware_key = {
                "hardware_architecture": "architecture",
                "bom": "bom",
                "wiring_design": "wiring",
                "firmware_project": "firmware",
                "hardware_acceptance": "physical_acceptance",
            }[artifact.type]
            hardware[hardware_key] = data
        elif artifact.type == "assembly_step" and data:
            hardware.setdefault("assembly_steps", []).append(data)
        elif artifact.type == "hardware_debug_record" and data:
            hardware.setdefault("debug_records", []).append(data)
        elif artifact.type in {"test_plan", "test_result", "validation_report", "iteration_plan"} and data:
            if artifact.type == "test_result":
                testing.setdefault("test_results", []).append(data)
            else:
                testing[artifact.type] = data
        elif artifact.type == "test_case" and data:
            testing.setdefault("test_cases", []).append(data)
        elif artifact.type == "defect" and data:
            item = dict(data)
            item.update({"artifact_id": artifact.id, "version": artifact.version, "title": artifact.title})
            defects.append(item)
        elif artifact.type == "user_feedback" and data:
            user_feedback.append(data)
        elif artifact.type == "protocol_connection_model" and data:
            hardware.setdefault("connection_model", data)

    active_evidence = [item for item in evidence if item.get("status", "active") == "active"]
    now = datetime.now(timezone.utc)
    freshness = {"fresh_7d": 0, "fresh_30d": 0, "older_or_unknown": 0}
    fact_types = Counter()
    polarities = Counter()
    citation_count = 0
    polarity_groups: dict[str, set[str]] = {}
    explicit_conflicts = 0
    for source in research_sources:
        fact_types[source.get("fact_type", "unknown")] += 1
        polarities[source.get("polarity", "unknown")] += 1
        if _is_openable_url(source.get("url")):
            citation_count += 1
        polarity = str(source.get("polarity", "unknown"))
        if polarity == "mixed":
            explicit_conflicts += 1
        claim_key = str(source.get("related_claim", "")).strip().casefold()
        if claim_key and polarity in {"positive", "negative"}:
            polarity_groups.setdefault(claim_key, set()).add(polarity)
        raw_date = source.get("published_at") or source.get("publish_date") or source.get("access_date")
        try:
            parsed = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
            # API sources commonly provide a date-only value. Treat it as a
            # UTC midnight rather than letting the naive/aware subtraction
            # raise and incorrectly classifying a fresh source as unknown.
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age_days = max(0, (now - parsed).days)
        except (TypeError, ValueError):
            age_days = 10_000
        if age_days <= 7:
            freshness["fresh_7d"] += 1
        elif age_days <= 30:
            freshness["fresh_30d"] += 1
        else:
            freshness["older_or_unknown"] += 1
    provider_categories = {
        "web": ["tavily", "serper"],
        "github": ["github"],
        "paper": ["semantic_scholar"],
        "patent": ["patent"],
        "crowdfunding": ["crowdfunding"],
        "community": ["community", "reddit", "github_discussions"],
    }
    provider_status: dict[str, str] = {}
    if research_runs:
        latest_run = max(research_runs, key=lambda item: str(item.get("_artifact_updated_at", "")))
        raw_status = latest_run.get("provider_status") or {}
        for category, providers in provider_categories.items():
            statuses = [str(raw_status[name]) for name in providers if name in raw_status]
            if "success" in statuses:
                provider_status[category] = "success"
            elif "retrying" in statuses:
                provider_status[category] = "retrying"
            elif "rate_limited" in statuses:
                provider_status[category] = "rate_limited"
            elif "failed" in statuses:
                provider_status[category] = "failed"
            elif "unconfigured" in statuses:
                provider_status[category] = "unconfigured"
            else:
                provider_status[category] = "not_run"

    # A project reaching the last lifecycle stage is not, by itself, proof
    # that Phase 2 was accepted. Keep the completion contract in the shared
    # projection so the desktop, API and final stage gate use the same facts.
    latest_by_type: dict[str, Any] = {}
    for artifact in artifacts:
        previous = latest_by_type.get(artifact.type)
        if previous is None or artifact.version > previous.version:
            latest_by_type[artifact.type] = artifact
    persisted_track_state = _json(getattr(latest_by_type.get("workflow_track_state"), "content", "")) or {}
    persisted_tracks = persisted_track_state.get("tracks") if isinstance(persisted_track_state.get("tracks"), dict) else {}
    participant_ids = {
        str(item.get("participant_id"))
        for item in user_feedback
        if str(item.get("participant_id", "")).strip()
        and str(item.get("user_type", "")).strip()
        and str(item.get("task", "")).strip()
    }
    validation_data = _json(getattr(latest_by_type.get("validation_report"), "content", "")) or {}
    final_conclusions = {"continue_release", "release_after_fix", "reduce_scope", "stop_project"}
    validation_ready = validation_data.get("conclusion") in final_conclusions and len(participant_ids) >= 3
    defect_ids = {
        str(item.get("defect_id"))
        for item in defects
        if str(item.get("defect_id", "")).strip()
    }
    fix_data = _json(getattr(latest_by_type.get("defect_fix"), "content", "")) or {}
    fixed_defect_id = str(fix_data.get("defect_id", "")).strip()
    failed_defect_ids = {
        str(result.get("defect_id"))
        for result in testing.get("test_results", [])
        if isinstance(result, dict)
        and result.get("result") in {"failed", "error"}
        and str(result.get("defect_id", "")).strip()
    }
    has_regression = bool(fixed_defect_id and fixed_defect_id in defect_ids and any(
        isinstance(result, dict)
        and result.get("result") == "passed"
        and str(result.get("regression_of", "")).strip() == fixed_defect_id
        for result in testing.get("test_results", [])
    ) and fixed_defect_id in failed_defect_ids)
    solution_data = _json(getattr(latest_by_type.get("solution_decision"), "content", "")) or {}
    solution_ready = solution_data.get("action") in {"select", "compose"}
    problem_brief_data = _json(getattr(latest_by_type.get("problem_brief"), "content", "")) or {}
    valid_evidence_ids = {
        str(item.get("artifact_id"))
        for item in active_evidence
        if str(item.get("artifact_id", "")).strip()
    }
    brief_evidence_ids = [str(item).strip() for item in problem_brief_data.get("evidence_ids", [])]
    problem_brief_ready = bool(
        brief_evidence_ids
        and all(item in valid_evidence_ids for item in brief_evidence_ids)
    )
    comparison_data = _json(getattr(latest_by_type.get("solution_comparison"), "content", "")) or {}
    comparison_ready = len(comparison_data.get("solutions") or comparison_data.get("candidates") or []) >= 3
    protocol_data = _json(getattr(latest_by_type.get("protocol_scenarios"), "content", "")) or {}
    protocol_scenarios = protocol_data.get("scenarios") if isinstance(protocol_data.get("scenarios"), list) else []
    protocol_ready = len(protocol_scenarios) == 6 and all(
        isinstance(item, dict) and item.get("status") == "PASSED"
        for item in protocol_scenarios
    )
    completion_missing: list[str] = []
    if not problem_brief_ready:
        completion_missing.append("引用有效证据的 Problem Brief")
    if not comparison_ready:
        completion_missing.append("保守、平衡、激进三方案比较")
    if project.project_type == "hybrid" and not protocol_ready:
        completion_missing.append("协议正常、离线、重连、重复、错误、版本不兼容六场景通过")
    physical_data = _json(getattr(latest_by_type.get("hardware_acceptance"), "content", "")) or {}
    physical_runs = physical_data.get("hardware_runs") if isinstance(physical_data.get("hardware_runs"), list) else []
    physical_actions = {
        str(run.get("action"))
        for run in physical_runs
        if isinstance(run, dict) and run.get("status") == "PASSED" and run.get("success") is True
    }
    physical_discoveries = [
        run for run in physical_runs
        if isinstance(run, dict)
        and run.get("action") == "list_ports"
        and run.get("status") == "PASSED"
        and run.get("success") is True
        and run.get("board_detected") is True
    ]
    physical_ready = (
        physical_data.get("confirmed_by_user") is True
        and physical_data.get("physical_evidence_required") is True
        and physical_data.get("confirmation_answer") == "confirmed_behavior_and_reconnect"
        and {"compile", "upload", "monitor"}.issubset(physical_actions)
        and len(physical_discoveries) >= 2
    )
    parallel_tracks: dict[str, dict[str, Any]] = {}
    if project.project_type == "hybrid":
        current_stage = project.current_stage
        shared_complete = current_stage in {
            "protocol_design", "development", "testing", "hardware_design",
            "procurement", "maker", "firmware", "hardware_testing",
            "integration_testing", "iteration",
        }
        protocol_confirmation = _json(getattr(latest_by_type.get("protocol_confirmation"), "content", "")) or {}
        protocol_confirmed = protocol_confirmation.get("confirmed") is True
        parallel_tracks = {
            "software": {
                "stages": list(tracks_for("hybrid")["software"]),
                "state": "active" if shared_complete else "pending",
                "next_action": "软件实现与软件测试",
            },
            "hardware": {
                "stages": list(tracks_for("hybrid")["hardware"]),
                "state": "completed" if physical_ready else "active" if shared_complete else "pending",
                "next_action": "采购、Maker 装配、固件与 ESP32 实物验证" if not physical_ready else "已取得实物验收证据",
            },
            "protocol": {
                "stages": list(tracks_for("hybrid")["protocol"]),
                "state": "completed" if protocol_confirmed and protocol_ready else "active" if shared_complete else "pending",
                "next_action": "确认协议并通过六种模拟场景" if not (protocol_confirmed and protocol_ready) else "协议已确认且六场景通过",
            },
            "integration": {
                "stages": list(tracks_for("hybrid")["integration"]),
                "state": "active" if shared_complete and protocol_confirmed else "blocked" if shared_complete else "pending",
                "next_action": "协议、软件和硬件就绪后执行集成测试",
            },
        }
        for track_name, track in parallel_tracks.items():
            saved = persisted_tracks.get(track_name) if isinstance(persisted_tracks, dict) else None
            if isinstance(saved, dict):
                track["state"] = str(saved.get("state") or track["state"])
                track["current_stage"] = saved.get("current_stage")
                track["completed_stages"] = list(saved.get("completed_stages") or [])
                track["next_stage"] = saved.get("next_stage")
            else:
                track["current_stage"] = None
                track["completed_stages"] = []
                track["next_stage"] = track["stages"][0] if track["stages"] else None
    parallel_tracks_ready = project.project_type != "hybrid" or (
        bool(persisted_tracks)
        and set(persisted_tracks) >= set(tracks_for("hybrid"))
        and all(
            isinstance(persisted_tracks.get(name), dict)
            and persisted_tracks[name].get("state") == "completed"
            for name in tracks_for("hybrid")
        )
    )
    if project.project_type == "hybrid" and not parallel_tracks_ready:
        completion_missing.append("软件、硬件、协议和集成四条混合轨道均已完成")
    if not active_evidence:
        completion_missing.append("至少一条有效问题证据")
    real_research_sources = [
        source for source in research_sources
        if _is_openable_url(source.get("url"))
        and not any(marker in str(source.get("title", "")).lower() for marker in ("not configured", "search failed", "rate limited"))
    ]
    successful_research_categories = {
        category for category, status in provider_status.items() if status == "success"
    }
    if not real_research_sources:
        completion_missing.append("至少一条真实研究来源")
    if len(successful_research_categories) < 5:
        completion_missing.append("一次研究任务覆盖六类来源中的至少五类")
    if not solution_ready:
        completion_missing.append("已确认的方案决策")
    if not has_regression:
        completion_missing.append("失败→缺陷→修复→原用例回归证据")
    if not validation_ready:
        completion_missing.append("三名不同目标用户和最终验证报告")
    if project.project_type in {"embedded", "hybrid"} and not physical_ready:
        completion_missing.append("ESP32 实物编译、上传、串口和拔插恢复证据")
    phase2_completion = {
        "ready": not completion_missing,
        "missing": completion_missing,
        "participant_count": len(participant_ids),
        "regression_closed": has_regression,
        "research_categories_succeeded": sorted(successful_research_categories),
        "protocol_scenarios_ready": protocol_ready,
        "physical_acceptance_ready": physical_ready,
        "parallel_tracks_ready": parallel_tracks_ready,
    }
    return {
        "project": project.to_dict(),
        # Keep the immutable latest artifact projection available to desktop
        # clients.  Work centers render specialized sections, but a few
        # centers (notably improvements) also need the original versioned
        # payload so a refresh/reopen can show records that have no dedicated
        # read-model section yet.
        "artifacts": [artifact.to_dict() for artifact in sorted(artifacts, key=lambda item: (item.type, item.title, item.version))],
        "next_action": {
            **_default_next_action(project),
            "blocked_reason": project.blocked_reason or None,
        },
        "evidence": {
            "items": sorted(evidence, key=lambda item: item.get("observed_at", ""), reverse=True),
            "active_count": len(active_evidence),
            "by_type": dict(Counter(item.get("evidence_type", "unknown") for item in active_evidence)),
        },
        "problem_brief": problem_brief,
        "research": {
            "sources": research_sources,
            "source_coverage": dict(research_status),
            "source_count": len(research_sources),
            "runs": [
                {key: value for key, value in item.items() if key != "_artifact_updated_at"}
                for item in sorted(research_runs, key=lambda item: str(item.get("_artifact_updated_at", "")), reverse=True)
            ],
            "provider_status": provider_status,
            "citation_count": citation_count,
            "freshness": freshness,
            "fact_types": dict(fact_types),
            "polarities": dict(polarities),
            "conflict_count": explicit_conflicts + sum(
                1 for values in polarity_groups.values() if {"positive", "negative"}.issubset(values)
            ),
        },
        "decisions": [decision.to_dict() for decision in decisions],
        # Keep the complete comparison in the same project-scoped snapshot as
        # the candidate count.  The desktop workbench previously rendered the
        # count from this snapshot but fetched the comparison through a second
        # request; when that request timed out or failed during the large
        # refresh, the home tab showed three candidates while the decision tab
        # incorrectly showed an empty state.  A single durable projection lets
        # both tabs render the same versioned comparison, while the desktop
        # client may still use the dedicated endpoint as a compatibility
        # fallback for older servers.
        "solutions": {
            "comparison": comparison_data,
            "candidates": solution_candidates,
            "count": len(solution_candidates),
            "impacts": solution_impacts,
        },
        "hardware": hardware,
        "parallel_tracks": parallel_tracks,
        "testing": testing,
        "user_validation": {
            "feedback": user_feedback,
            "participant_count": len(participant_ids),
            "completed_count": sum(1 for item in user_feedback if item.get("completed") is True),
            "minimum_participants_met": len(participant_ids) >= 3,
        },
        "phase2_completion": phase2_completion,
        "defects": defects,
        "risks": list(project.risks),
        "artifact_count": len(artifacts),
    }
