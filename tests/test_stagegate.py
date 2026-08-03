"""Tests for the stage-gate & real-progress engine (feature 3.2)."""

from __future__ import annotations

from pathlib import Path

from kyrozen.core import stagegate as sg
from kyrozen.core.stagegate import (
    STAGES,
    STAGE_DEFINITIONS,
    StageGateStore,
    advance,
    compute_gate,
    compute_progress,
    detect_deliverables,
    refresh_gate,
    sync_artifact_deliverables,
)
from kyrozen.project.workflow import WORKFLOW_STAGES


def _store(tmp_path: Path, stage: str = "problem_discovery") -> StageGateStore:
    s = StageGateStore(tmp_path / "stagegate.json", project_id="p1")
    s.current_stage = stage
    return s


# ---------------------------------------------------------------------------
# 1. Stage definitions exist for all workflow-specific lifecycle stages
# ---------------------------------------------------------------------------

def test_all_workflow_stages_defined():
    assert tuple(WORKFLOW_STAGES["software"]) == (
        "problem_discovery",
        "market_research",
        "product_definition",
        "solution_design",
        "development",
        "testing",
        "iteration",
    )
    expected = tuple(dict.fromkeys(stage for stages in WORKFLOW_STAGES.values() for stage in stages))
    assert STAGES == expected
    for stage in expected:
        assert stage in STAGE_DEFINITIONS or sg._definition(stage) is not None


def test_prd_is_required_non_skippable_in_product_definition():
    definition = STAGE_DEFINITIONS["product_definition"]
    prd = next(i for i in definition.items if i.id == "prd")
    assert prd.kind == "deliverable"
    assert prd.skippable is False


def test_every_stage_defines_required_items():
    for stage, definition in STAGE_DEFINITIONS.items():
        assert definition.items, f"{stage} has no gate items"
        assert definition.label


# ---------------------------------------------------------------------------
# 2. Deliverable detection reads real workspace files
# ---------------------------------------------------------------------------

def test_detect_finds_prd_file(tmp_path: Path):
    (tmp_path / "PRD.md").write_text("# PRD")
    found = detect_deliverables(tmp_path, "product_definition")
    assert found["prd"] is True


def test_detect_uses_nested_glob(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_foo.py").write_text("def test_foo(): assert True")
    found = detect_deliverables(tmp_path, "testing")
    assert found["tests"] is True


def test_detect_reports_missing(tmp_path: Path):
    found = detect_deliverables(tmp_path, "product_definition")
    assert found["prd"] is False


def test_detect_accepts_generated_app_py_as_runnable_source(tmp_path: Path):
    (tmp_path / "app.py").write_text("print('ready')")
    found = detect_deliverables(tmp_path, "development")
    assert found["source_code"] is True


# ---------------------------------------------------------------------------
# 3. Progress is computed from the four real parts
# ---------------------------------------------------------------------------

def test_progress_starts_low(tmp_path: Path):
    s = _store(tmp_path, "problem_discovery")
    s.save()
    assert compute_progress(s) < 20


def test_progress_increases_with_deliverable(tmp_path: Path):
    s = _store(tmp_path, "product_definition")
    before = compute_progress(s)
    (tmp_path / "PRD.md").write_text("# PRD")
    refresh_gate(s, tmp_path)
    after = compute_progress(s)
    assert after > before


def test_progress_reflects_task_completion(tmp_path: Path):
    s = _store(tmp_path, "development")
    s.record_task("t1", "completed")
    s.record_task("t2", "completed")
    high = compute_progress(s)
    s.record_task("t1", "failed")
    low = compute_progress(s)
    assert high > low


def test_progress_reaches_high_when_stage_complete(tmp_path: Path):
    s = _store(tmp_path, "problem_discovery")
    base = compute_progress(s)
    s.record_deliverable("problem_statement", True)
    mid = compute_progress(s)
    s.record_confirmation("problem_confirmed", True)
    full = compute_progress(s)
    assert full > mid > base
    # Fully completing a stage is a meaningful step on the 7-stage scale.
    assert full >= 10


# ---------------------------------------------------------------------------
# 4. Gate shows satisfied / missing conditions item-by-item
# ---------------------------------------------------------------------------

def test_gate_reports_satisfied_and_missing(tmp_path: Path):
    s = _store(tmp_path, "product_definition")
    (tmp_path / "PRD.md").write_text("# PRD")
    refresh_gate(s, tmp_path)
    s.record_confirmation("prd_confirmed", True)
    gate = compute_gate(s)
    ids = {c.item_id for c in gate.satisfied}
    assert "prd" in ids and "prd_confirmed" in ids
    assert gate.can_advance is True
    assert gate.missing == []


def test_gate_missing_lists_unsatisfied(tmp_path: Path):
    s = _store(tmp_path, "product_definition")
    gate = compute_gate(s)
    missing_ids = {c.item_id for c in gate.missing}
    assert "prd" in missing_ids
    assert gate.can_advance is False


# ---------------------------------------------------------------------------
# 5. The three stage actions
# ---------------------------------------------------------------------------

def test_advance_normal_blocked_without_prd(tmp_path: Path):
    """Acceptance: cannot enter development without a PRD."""
    s = _store(tmp_path, "product_definition")
    result = advance(s, "normal")
    assert result["ok"] is False
    assert "PRD" in result["error"]


def test_artifact_deliverables_can_back_phase2_gate(tmp_path: Path):
    store = _store(tmp_path, "embedded")
    store.current_stage = "procurement"
    refresh_gate(store, tmp_path)
    assert not any(item.item_id == "procurement" for item in compute_gate(store).satisfied)
    sync_artifact_deliverables(store, ["bom"])
    assert any(item.item_id == "procurement" for item in compute_gate(store).satisfied)


def test_embedded_entry_uses_artifact_prd_and_requires_confirmed_solution(tmp_path: Path):
    """API-backed embedded projects must not bypass the shared solution gate."""
    store = StageGateStore(tmp_path / "stagegate.json", project_id="p1", project_type="embedded")
    store.current_stage = "product_definition"
    sync_artifact_deliverables(store, ["product_definition"])
    store.record_confirmation("prd_confirmed", True)
    blocked = advance(store, "normal")
    assert blocked["ok"] is False
    assert "方案" in blocked["error"]

    store.record_confirmation("solution_confirmed", True)
    allowed = advance(store, "normal")
    assert allowed["ok"] is True
    assert allowed["stage"] == "hardware_design"


def test_hardware_stage_artifact_requirements_do_not_accept_debug_or_missing_run_aliases():
    from kyrozen.core.stagegate import ARTIFACT_DELIVERABLES

    assert ARTIFACT_DELIVERABLES["firmware"] == frozenset({"firmware_project"})
    assert ARTIFACT_DELIVERABLES["hardware_testing"] == frozenset({"hardware_acceptance"})


def test_advance_normal_success_after_prd(tmp_path: Path):
    s = _store(tmp_path, "product_definition")
    (tmp_path / "PRD.md").write_text("# PRD")
    refresh_gate(s, tmp_path)
    s.record_confirmation("prd_confirmed", True)
    result = advance(s, "normal")
    assert result["ok"] is True
    # product_definition -> solution_design (development is two stages later).
    assert result["stage"] == "solution_design"
    # The next stage is intentionally waiting for the explicit Phase 2
    # solution decision before any implementation stage can be entered.
    assert "方案" in result["gate"]["blocked_entry_reason"]


def test_next_stage_click_is_the_user_confirmation(tmp_path: Path):
    s = _store(tmp_path, "product_definition")
    (tmp_path / "PRD.md").write_text("# PRD")
    gate = refresh_gate(s, tmp_path)
    assert any(item.item_id == "prd_confirmed" for item in gate.missing)
    assert gate.can_advance is True
    result = advance(s, "normal")
    assert result["ok"] is True
    assert s.records["prd_confirmed"]["confirmed"] is True


def test_refresh_removes_legacy_skip_from_hard_requirement(tmp_path: Path):
    s = _store(tmp_path, "product_definition")
    s.record_skip("prd", "旧版本跳过", "影响", "用户", "补救")
    assert s.records["prd"]["skipped"] is True
    refresh_gate(s, tmp_path)
    assert s.records["prd"]["skipped"] is False
    assert all(skip.item_id != "prd" for skip in s.skips)


def test_prd_gates_entry_into_development(tmp_path: Path):
    """Entering development without a PRD is blocked, even via solution_design."""
    s = _store(tmp_path, "solution_design")
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "TECH_DESIGN.md").write_text("# design")
    refresh_gate(s, tmp_path)
    s.record_confirmation("design_confirmed", True)
    # Try to advance into development even though no PRD file exists.
    result = advance(s, "normal")
    assert result["ok"] is False
    assert "PRD" in result["error"]
    # The transition is refused, so we stay before development.
    assert result["stage"] == "solution_design"


def test_prd_allows_development_once_present(tmp_path: Path):
    """With a PRD on disk, the transition into development succeeds."""
    s = _store(tmp_path, "solution_design")
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "TECH_DESIGN.md").write_text("# design")
    (tmp_path / "PRD.md").write_text("# PRD")
    refresh_gate(s, tmp_path)
    s.record_confirmation("design_confirmed", True)
    s.record_confirmation("solution_confirmed", True)
    result = advance(s, "normal")
    assert result["ok"] is True
    assert result["stage"] == "development"


def test_solution_decision_is_required_before_implementation(tmp_path: Path):
    s = _store(tmp_path, "solution_design")
    (tmp_path / "PRD.md").write_text("# PRD")
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "TECH_DESIGN.md").write_text("# design")
    refresh_gate(s, tmp_path)
    s.record_confirmation("design_confirmed", True)
    blocked = advance(s, "normal")
    assert blocked["ok"] is False
    assert "方案" in blocked["error"]
    s.record_confirmation("solution_confirmed", True)
    allowed = advance(s, "normal")
    assert allowed["ok"] is True
    assert allowed["stage"] == "development"


def test_advance_risk_records_skip_with_four_fields(tmp_path: Path):
    s = _store(tmp_path, "market_research")
    result = advance(s, "risk")
    assert result["ok"] is True
    assert result["risk"] is True
    # P0-17: risk advance now records skip for both missing deliverables AND
    # confirmation items, each with full reason/impact/approver/recovery detail.
    assert len(s.skips) == 2
    for skip in s.skips:
        assert skip.reason and skip.impact and skip.approver and skip.recovery


def test_advance_risk_cannot_skip_hard_prd_gate(tmp_path: Path):
    s = _store(tmp_path, "product_definition")
    result = advance(s, "risk", {"reason": "赶时间", "impact": "可能返工", "recovery": "之后补齐"})
    assert result["ok"] is False
    assert "不可带风险跳过" in result["error"]
    assert s.current_stage == "product_definition"


def test_advance_risk_persists_user_reason(tmp_path: Path):
    s = _store(tmp_path, "market_research")
    result = advance(s, "risk", {"reason": "先验证线下需求", "impact": "竞品信息不完整", "recovery": "试点后补充调研"})
    assert result["ok"] is True
    assert all(skip.reason == "先验证线下需求" for skip in s.skips)


def test_advance_return_moves_back_and_clears(tmp_path: Path):
    s = _store(tmp_path, "solution_design")
    s.record_deliverable("tech_design", True)
    before = compute_progress(s)
    result = advance(s, "return")
    assert result["ok"] is True
    assert result["stage"] == "product_definition"
    # Returning re-opens the previous stage's gate for re-evaluation.
    assert result["progress"] < before


def test_advance_return_on_first_stage_fails(tmp_path: Path):
    s = _store(tmp_path, "problem_discovery")
    result = advance(s, "return")
    assert result["ok"] is False


def test_advance_past_last_stage_fails(tmp_path: Path):
    s = _store(tmp_path, "iteration")
    # satisfy iteration gate so the failure is about being last, not the gate.
    s.record_deliverable("changelog", True)
    s.record_verification("regression_passes", True)
    s.record_confirmation("release_confirmed", True)
    result = advance(s, "normal")
    assert result["ok"] is False
    assert "最后阶段" in result["error"]


# ---------------------------------------------------------------------------
# 6. Skip records reason / impact / approver / recovery
# ---------------------------------------------------------------------------

def test_record_skip_requires_all_four_fields(tmp_path: Path):
    s = _store(tmp_path, "market_research")
    assert s.record_skip("market_report", "", "impact", "me", "recover") is False
    assert s.record_skip("market_report", "reason", "impact", "me", "recover") is True
    assert s.records["market_report"]["skipped"] is True


# ---------------------------------------------------------------------------
# 7. Failed tasks surface a repair entry (acceptance)
# ---------------------------------------------------------------------------

def test_failed_task_shows_repair_entry(tmp_path: Path):
    s = _store(tmp_path, "development")
    s.record_task("step-3", "failed", error="ImportError: no module 'requests'")
    gate = compute_gate(s)
    failed = [c for c in gate.missing if c.kind == "task"]
    assert failed
    assert "修复" in failed[0].detail or "修复" in gate.failed_tasks[0]["repair"]
    assert gate.failed_tasks[0]["task_id"] == "step-3"


# ---------------------------------------------------------------------------
# 8. Hard entry gate: no PRD blocks being in development
# ---------------------------------------------------------------------------

def test_blocked_entry_reason_without_prd(tmp_path: Path):
    s = _store(tmp_path, "development")
    gate = compute_gate(s)
    assert gate.blocked_entry_reason is not None
    assert "PRD" in gate.blocked_entry_reason
    assert gate.can_advance is False


# ---------------------------------------------------------------------------
# 9. Persistence: reopening a project yields identical progress (acceptance)
# ---------------------------------------------------------------------------

def test_reopen_project_restores_state(tmp_path: Path):
    s = _store(tmp_path, "product_definition")
    (tmp_path / "PRD.md").write_text("# PRD")
    refresh_gate(s, tmp_path)
    s.record_confirmation("prd_confirmed", True)
    s.save()
    saved_stage = s.current_stage
    saved_progress = s.progress
    saved_records = dict(s.records)

    # Simulate reopening the project: a brand new store loading the same file.
    reopened = StageGateStore(tmp_path / "stagegate.json", project_id="p1")
    assert reopened.current_stage == saved_stage
    assert reopened.progress == saved_progress
    assert reopened.records == saved_records


def test_persisted_advance_survives_reopen(tmp_path: Path):
    s = _store(tmp_path, "product_definition")
    (tmp_path / "PRD.md").write_text("# PRD")
    refresh_gate(s, tmp_path)
    s.record_confirmation("prd_confirmed", True)
    advance(s, "normal")
    assert s.current_stage == "solution_design"

    reopened = StageGateStore(tmp_path / "stagegate.json", project_id="p1")
    assert reopened.current_stage == "solution_design"
    assert reopened.progress == s.progress


def test_embedded_workflow_uses_its_own_stage_sequence(tmp_path: Path):
    s = StageGateStore(tmp_path / "stagegate.json", project_id="p1", project_type="embedded")
    assert s.workflow_type == "embedded"
    assert s.current_stage == "problem_discovery"
    s.current_stage = "hardware_design"
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "HARDWARE.md").write_text("# hardware")
    refresh_gate(s, tmp_path)
    assert compute_gate(s).stage_label == "硬件方案"
    s.save()

    reopened = StageGateStore(tmp_path / "stagegate.json", project_id="p1")
    assert reopened.workflow_type == "embedded"
    assert reopened.current_stage == "hardware_design"


def test_hybrid_protocol_confirmation_is_a_hard_gate(tmp_path: Path):
    s = StageGateStore(tmp_path / "stagegate.json", project_id="p1", project_type="hybrid")
    s.current_stage = "protocol_design"
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "PROTOCOL.md").write_text("# Protocol v1")
    (tmp_path / "PRD.md").write_text("# PRD")
    refresh_gate(s, tmp_path)
    missing = next(item for item in compute_gate(s).missing if item.item_id == "protocol_design_confirmed")
    assert missing.skippable is False
    assert compute_gate(s).can_advance is False
    assert advance(s, "risk")["ok"] is False
    s.record_confirmation("solution_confirmed", True)
    s.record_confirmation("protocol_design_confirmed", True)
    assert compute_gate(s).can_advance is True
