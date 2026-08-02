"""Read models shared by the Phase 2 project workbench.

The projection deliberately reads versioned project artifacts instead of
maintaining a second database. This keeps refresh/reopen behavior deterministic
while the individual research, hardware and testing centers are expanded.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from kyrozen.discovery.evidence import Evidence


def _json(content: str) -> dict[str, Any] | None:
    try:
        value = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


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
    solution_candidates: list[dict[str, Any]] = []
    testing: dict[str, Any] = {}
    hardware: dict[str, Any] = {}

    for artifact in artifacts:
        data = _json(artifact.content)
        if artifact.type == "discovery_evidence" and data:
            try:
                item = Evidence.from_dict(data).to_dict()
            except ValueError:
                item = data
            item.update({"artifact_id": artifact.id, "version": artifact.version, "title": artifact.title})
            evidence.append(item)
        elif artifact.type == "market_research_report" and data:
            for source in data.get("sources", []):
                if isinstance(source, dict):
                    research_sources.append(source)
                    research_status[source.get("source_type", "unknown")] += 1
        elif artifact.type == "solution_comparison" and data:
            solution_candidates = list(data.get("solutions") or data.get("candidates") or [])
        elif artifact.type.startswith("hardware_") and data:
            hardware[artifact.type.removeprefix("hardware_")] = data
        elif artifact.type in {"test_plan", "test_result", "validation_report", "iteration_plan"} and data:
            testing[artifact.type] = data

    active_evidence = [item for item in evidence if item.get("status", "active") == "active"]
    return {
        "project": project.to_dict(),
        "next_action": {
            "label": project.next_steps or "继续当前阶段",
            "stage": project.current_stage,
            "blocked_reason": project.blocked_reason or None,
        },
        "evidence": {
            "items": sorted(evidence, key=lambda item: item.get("observed_at", ""), reverse=True),
            "active_count": len(active_evidence),
            "by_type": dict(Counter(item.get("evidence_type", "unknown") for item in active_evidence)),
        },
        "research": {
            "sources": research_sources,
            "source_coverage": dict(research_status),
            "source_count": len(research_sources),
        },
        "decisions": [decision.to_dict() for decision in decisions],
        "solutions": {"candidates": solution_candidates, "count": len(solution_candidates)},
        "hardware": hardware,
        "testing": testing,
        "risks": list(project.risks),
        "artifact_count": len(artifacts),
    }
