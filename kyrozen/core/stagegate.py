"""Stage gates & real progress engine (feature 3.2).

This module is the single source of truth for a project's lifecycle stage, the
conditions required to leave each stage, and a progress number that is computed
from *real* signals instead of a stage index:

* task status        -- recorded from agent task results
* deliverable status -- detected by scanning real files in the workspace
* verification results -- recorded when builds/tests actually pass
* user confirmation  -- recorded when the user advances / confirms a stage

All state is persisted to ``.kyrozen/stagegate.json`` (mirroring
``kyrozen.core.handoff.HandoffStore``) so progress is identical after reopening
a project. Stage changes are pushed as events, never polled.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Stage lifecycle (mirrors kyrozen.project.project.PROJECT_STAGES)
# ---------------------------------------------------------------------------

STAGES: tuple[str, ...] = (
    "problem_discovery",
    "market_research",
    "product_definition",
    "solution_design",
    "development",
    "testing",
    "iteration",
)

STAGE_LABELS: dict[str, str] = {
    "problem_discovery": "问题探索",
    "market_research": "市场调研",
    "product_definition": "产品定义",
    "solution_design": "方案设计",
    "development": "软件开发",
    "testing": "测试验证",
    "iteration": "迭代改进",
}


@dataclass(frozen=True)
class GateItem:
    """A single condition that must be satisfied to leave a stage."""

    id: str
    label: str
    kind: str  # 'deliverable' | 'confirmation' | 'verification'
    detect: tuple[str, ...] = ()  # workspace globs/paths for deliverables
    skippable: bool = False


@dataclass(frozen=True)
class StageDefinition:
    key: str
    label: str
    items: tuple[GateItem, ...] = ()
    note: str = ""


def _d(item_id: str, label: str, detect: tuple[str, ...] = (), skippable: bool = False) -> GateItem:
    return GateItem(id=item_id, label=label, kind="deliverable", detect=detect, skippable=skippable)


def _c(item_id: str, label: str, skippable: bool = False) -> GateItem:
    return GateItem(id=item_id, label=label, kind="confirmation", skippable=skippable)


def _v(item_id: str, label: str, skippable: bool = False) -> GateItem:
    return GateItem(id=item_id, label=label, kind="verification", skippable=skippable)


# Per-stage required deliverables / confirmations / verifications.
# ``prd`` is a required, non-skippable deliverable of product_definition, which
# is the hard gate that prevents entering development without a PRD.
STAGE_DEFINITIONS: dict[str, StageDefinition] = {
    "problem_discovery": StageDefinition(
        key="problem_discovery",
        label="问题探索",
        note="明确要解决的问题、目标用户与价值。",
        items=(
            _d("problem_statement", "问题陈述（docs/PROBLEM.md）", ("docs/PROBLEM.md", "PROBLEM.md", "problem_brief.md")),
            _c("problem_confirmed", "用户确认问题界定", skippable=True),
        ),
    ),
    "market_research": StageDefinition(
        key="market_research",
        label="市场调研",
        note="了解市场、用户与竞品，验证需求是否成立。",
        items=(
            _d("market_report", "市场与竞品调研（docs/MARKET.md）", ("docs/MARKET.md", "MARKET_REPORT.md", "market_research.md"), skippable=True),
            _c("market_confirmed", "用户确认调研结论", skippable=True),
        ),
    ),
    "product_definition": StageDefinition(
        key="product_definition",
        label="产品定义",
        note="产出可被开发直接使用的 PRD；缺少 PRD 不能进入开发阶段。",
        items=(
            _d("prd", "产品需求文档 PRD（PRD.md / docs/PRD.md）", ("PRD.md", "prd.md", "docs/PRD.md")),
            _c("prd_confirmed", "用户确认 PRD"),
        ),
    ),
    "solution_design": StageDefinition(
        key="solution_design",
        label="方案设计",
        note="评估可行方案并权衡取舍。",
        items=(
            _d("tech_design", "技术方案（docs/TECH_DESIGN.md）", ("docs/TECH_DESIGN.md", "docs/DESIGN.md", "DESIGN.md"), skippable=True),
            _c("design_confirmed", "用户确认技术方案", skippable=True),
        ),
    ),
    "development": StageDefinition(
        key="development",
        label="软件开发",
        note="实现 PRD 中的功能，产出可运行产品。",
        items=(
            _d("prd", "产品需求文档 PRD（进入开发的硬门槛）", ("PRD.md", "prd.md", "docs/PRD.md")),
            _d("source_code", "可运行源码（package.json / app.py / main.py / index.html）", ("package.json", "pyproject.toml", "app.py", "main.py", "index.html")),
            _d("readme", "项目说明 README.md", ("README.md",), skippable=True),
            _v("build_passes", "构建通过", skippable=True),
            _c("dev_review", "开发自审确认", skippable=True),
        ),
    ),
    "testing": StageDefinition(
        key="testing",
        label="测试验证",
        note="设计用例、执行测试并验收。",
        items=(
            _d("tests", "测试用例（tests/ 或测试文件）", ("tests", "test_*.py", "*.test.ts", "*.spec.ts")),
            _v("tests_pass", "测试通过"),
            _c("test_confirmed", "用户确认测试结果", skippable=True),
        ),
    ),
    "iteration": StageDefinition(
        key="iteration",
        label="迭代改进",
        note="在已有成果上持续打磨改进。",
        items=(
            _d("changelog", "变更记录 CHANGELOG.md", ("CHANGELOG.md",), skippable=True),
            _v("regression_passes", "回归通过", skippable=True),
            _c("release_confirmed", "用户确认发布", skippable=True),
        ),
    ),
}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@dataclass
class SkipRecord:
    item_id: str
    reason: str
    impact: str
    approver: str
    recovery: str
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "reason": self.reason,
            "impact": self.impact,
            "approver": self.approver,
            "recovery": self.recovery,
            "at": self.at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SkipRecord":
        return cls(
            item_id=d.get("item_id", ""),
            reason=d.get("reason", ""),
            impact=d.get("impact", ""),
            approver=d.get("approver", ""),
            recovery=d.get("recovery", ""),
            at=d.get("at", time.time()),
        )


class StageGateStore:
    """Persists stage-gate state to ``.kyrozen/stagegate.json``.

    A record for an item tracks four booleans:
      * detected   -- a deliverable file was found in the workspace
      * confirmed  -- an explicit confirmation / verification was recorded
      * skipped    -- the item was explicitly skipped (with reason/impact/...)
      * failed     -- a required task failed (surfaced as a repair entry)
    """

    def __init__(self, path: str | Path, project_id: str = "") -> None:
        self.path = Path(path)
        self.project_id = project_id
        self.current_stage: str = STAGES[0]
        self.progress: int = 0
        self.records: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.skips: list[SkipRecord] = []
        self.events: list[dict[str, Any]] = []
        self._load()

    # -- load / save (atomic, mirrors HandoffStore) ----------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        self.current_stage = data.get("current_stage", self.current_stage)
        if self.current_stage not in STAGES:
            self.current_stage = STAGES[0]
        self.progress = int(data.get("progress", 0))
        self.records = data.get("records", {})
        self.tasks = data.get("tasks", {})
        self.skips = [SkipRecord.from_dict(s) for s in data.get("skips", [])]
        self.events = data.get("events", [])

    def save(self) -> None:
        # Ensure the .kyrozen directory exists (e.g. on first open of a project
        # before any deliverable has been written) so the gate can persist and
        # surface in the real client instead of raising FileNotFoundError.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_id": self.project_id,
            "current_stage": self.current_stage,
            "progress": self.progress,
            "records": self.records,
            "tasks": self.tasks,
            "skips": [s.to_dict() for s in self.skips],
            "events": self.events[-200:],
            "updated_at": time.time(),
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # -- recording --------------------------------------------------------

    def _rec(self, item_id: str) -> dict[str, Any]:
        rec = self.records.get(item_id)
        if rec is None:
            rec = {"detected": False, "confirmed": False, "skipped": False, "failed": False, "detail": "", "at": 0.0}
            self.records[item_id] = rec
        return rec

    def record_deliverable(self, item_id: str, detected: bool, detail: str = "") -> None:
        rec = self._rec(item_id)
        rec["detected"] = bool(detected)
        if detail:
            rec["detail"] = detail
        rec["at"] = time.time()

    def record_confirmation(self, item_id: str, confirmed: bool, detail: str = "") -> None:
        rec = self._rec(item_id)
        rec["confirmed"] = bool(confirmed)
        if detail:
            rec["detail"] = detail
        rec["at"] = time.time()

    def record_verification(self, item_id: str, passed: bool, detail: str = "") -> None:
        rec = self._rec(item_id)
        rec["confirmed"] = bool(passed)
        if detail:
            rec["detail"] = detail
        rec["at"] = time.time()

    def record_task(self, task_id: str, status: str, error: str = "") -> None:
        self.tasks[task_id] = {"status": status, "error": error, "at": time.time()}

    def record_skip(self, item_id: str, reason: str, impact: str, approver: str, recovery: str) -> bool:
        # Acceptance: a skip must record reason / impact / approver / recovery.
        if not (reason and impact and approver and recovery):
            return False
        self.skips = [s for s in self.skips if s.item_id != item_id]
        self.skips.append(SkipRecord(item_id=item_id, reason=reason, impact=impact, approver=approver, recovery=recovery))
        rec = self._rec(item_id)
        rec["skipped"] = True
        rec["detail"] = f"已跳过：{reason}"
        rec["at"] = time.time()
        return True

    def _reset_stage(self, stage: str) -> None:
        definition = STAGE_DEFINITIONS.get(stage)
        if not definition:
            return
        for item in definition.items:
            self.records.pop(item.id, None)
        self.skips = [s for s in self.skips if s.item_id not in {i.id for i in definition.items}]


# ---------------------------------------------------------------------------
# Detection & evaluation
# ---------------------------------------------------------------------------


def detect_deliverables(workspace_root: str | Path, stage: str) -> dict[str, bool]:
    """Scan the workspace for deliverable files of the given stage."""
    root = Path(workspace_root)
    result: dict[str, bool] = {}
    definition = STAGE_DEFINITIONS.get(stage)
    if definition is None:
        return result
    for item in definition.items:
        if item.kind != "deliverable" or not item.detect:
            continue
        found = False
        for pattern in item.detect:
            if (root / pattern).exists():
                found = True
                break
            try:
                if list(root.glob(pattern)) or list(root.glob(f"**/{pattern}")):
                    found = True
                    break
            except Exception:
                continue
        result[item.id] = found
    return result


def _item_satisfied(rec: dict[str, Any], kind: str) -> bool:
    if rec.get("skipped"):
        return True
    if kind == "deliverable":
        return bool(rec.get("detected")) or bool(rec.get("confirmed"))
    return bool(rec.get("confirmed"))


@dataclass
class Condition:
    item_id: str
    label: str
    kind: str
    satisfied: bool
    skippable: bool
    skipped: bool
    detail: str
    required: bool


@dataclass
class GateStatus:
    stage: str
    stage_label: str
    index: int
    total: int
    satisfied: list[Condition]
    missing: list[Condition]
    can_advance: bool
    blocked_entry_reason: str | None
    failed_tasks: list[dict[str, Any]]
    progress: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "stage_label": self.stage_label,
            "index": self.index,
            "total": self.total,
            "satisfied": [vars(c) for c in self.satisfied],
            "missing": [vars(c) for c in self.missing],
            "can_advance": self.can_advance,
            "blocked_entry_reason": self.blocked_entry_reason,
            "failed_tasks": self.failed_tasks,
            "progress": self.progress,
        }


def compute_progress(store: StageGateStore) -> int:
    """Progress = (completed earlier stages + within-stage fraction) / total.

    The within-stage fraction averages the four real parts: task status,
    deliverable status, verification results and user confirmation.
    """
    stage = store.current_stage
    idx = STAGES.index(stage) if stage in STAGES else 0
    n = len(STAGES)
    definition = STAGE_DEFINITIONS.get(stage)
    if definition is None:
        return int(round((idx + 1) / n * 100))

    def ratio_for(kind: str) -> float:
        items = [i for i in definition.items if i.kind == kind]
        if not items:
            return 1.0
        done = 0
        for i in items:
            rec = store.records.get(i.id, {})
            if _item_satisfied(rec, i.kind):
                done += 1
        return done / len(items)

    def task_ratio() -> float:
        tasks = list(store.tasks.values())
        if not tasks:
            return 1.0
        done = sum(1 for t in tasks if t.get("status") == "completed")
        return done / len(tasks)

    parts = [task_ratio(), ratio_for("deliverable"), ratio_for("verification"), ratio_for("confirmation")]
    within = sum(parts) / len(parts)
    progress = int(round((idx + within) / n * 100))
    return max(0, min(100, progress))


def compute_gate(store: StageGateStore) -> GateStatus:
    stage = store.current_stage
    definition = STAGE_DEFINITIONS.get(stage)
    idx = STAGES.index(stage) if stage in STAGES else 0
    satisfied: list[Condition] = []
    missing: list[Condition] = []
    blocked_entry_reason: str | None = None

    if definition is not None:
        for item in definition.items:
            rec = store.records.get(item.id, {})
            is_sat = _item_satisfied(rec, item.kind)
            cond = Condition(
                item_id=item.id,
                label=item.label,
                kind=item.kind,
                satisfied=is_sat,
                skippable=item.skippable,
                skipped=bool(rec.get("skipped")),
                detail=rec.get("detail", ""),
                required=True,
            )
            (satisfied if is_sat else missing).append(cond)

    # Failed tasks are surfaced as missing conditions with a repair entry.
    failed_tasks: list[dict[str, Any]] = []
    for tid, t in store.tasks.items():
        if t.get("status") == "failed":
            err = t.get("error", "") or "任务执行失败"
            failed_tasks.append({"task_id": tid, "error": err, "repair": f"定位失败任务 {tid} 并修复后重新运行"})
            missing.append(
                Condition(
                    item_id=tid,
                    label=f"任务失败：{tid}",
                    kind="task",
                    satisfied=False,
                    skippable=False,
                    skipped=False,
                    detail=err,
                    required=True,
                )
            )

    # Hard entry gate: cannot be in (or advance within) development without PRD.
    if stage == "development" and not _item_satisfied(store.records.get("prd", {}), "deliverable"):
        blocked_entry_reason = "缺少产品需求文档(PRD)，无法进入开发阶段。请先在「产品定义」阶段完成 PRD。"

    # Clicking “进入下一阶段” is itself the explicit user confirmation. A
    # confirmation item is displayed as pending, but must not make that button
    # impossible to click once all deliverables/verifications are ready.
    blocking_missing = [condition for condition in missing if condition.kind != "confirmation"]
    can_advance = len(blocking_missing) == 0 and blocked_entry_reason is None
    progress = compute_progress(store)
    return GateStatus(
        stage=stage,
        stage_label=definition.label if definition else STAGE_LABELS.get(stage, stage),
        index=idx,
        total=len(STAGES),
        satisfied=satisfied,
        missing=missing,
        can_advance=can_advance,
        blocked_entry_reason=blocked_entry_reason,
        failed_tasks=failed_tasks,
        progress=progress,
    )


def entry_blocked(store: StageGateStore, stage: str) -> str | None:
    """Return a reason if the given stage cannot be entered yet."""
    if stage == "development" and not _item_satisfied(store.records.get("prd", {}), "deliverable"):
        return "缺少产品需求文档(PRD)，无法进入开发阶段。请先在「产品定义」阶段完成 PRD。"
    return None


def refresh_gate(store: StageGateStore, workspace_root: str | Path) -> GateStatus:
    """Re-scan the workspace, recompute progress, persist and return the gate."""
    # Migrate state created by older clients that allowed hard requirements to
    # be skipped. A non-skippable item must never remain satisfied by a legacy
    # skip record after upgrading.
    hard_ids = {item.id for definition in STAGE_DEFINITIONS.values() for item in definition.items if not item.skippable}
    for item_id in hard_ids:
        rec = store.records.get(item_id)
        if rec and rec.get("skipped"):
            rec["skipped"] = False
            if str(rec.get("detail") or "").startswith("已跳过："):
                rec["detail"] = ""
    store.skips = [skip for skip in store.skips if skip.item_id not in hard_ids]
    # PRD is a cross-stage prerequisite for development, so always re-detect it
    # regardless of the current stage (it may have been created in an earlier stage).
    prd_found = detect_deliverables(workspace_root, "product_definition").get("prd", False)
    if not store.records.get("prd", {}).get("skipped"):
        store.record_deliverable("prd", prd_found)
    for item_id, found in detect_deliverables(workspace_root, store.current_stage).items():
        if item_id == "prd":
            continue
        rec = store.records.get(item_id, {})
        # A scan only flips a deliverable to detected; an explicit skip keeps it satisfied.
        if not rec.get("skipped"):
            store.record_deliverable(item_id, found)
    store.progress = compute_progress(store)
    store.save()
    return compute_gate(store)


# ---------------------------------------------------------------------------
# Stage transitions (the three required actions)
# ---------------------------------------------------------------------------


def _status_dict(store: StageGateStore, gate: GateStatus | None = None) -> dict[str, Any]:
    gate = gate or compute_gate(store)
    return {
        "stage": store.current_stage,
        "progress": store.progress,
        "gate": gate.to_dict(),
        "skips": [s.to_dict() for s in store.skips],
    }


def get_status(store: StageGateStore, gate: GateStatus | None = None) -> dict[str, Any]:
    """Public snapshot of the full gate status for UI / event payloads."""
    return _status_dict(store, gate)


def advance(store: StageGateStore, mode: str, risk_details: dict[str, str] | None = None) -> dict[str, Any]:
    """Perform a stage transition.

    mode:
      * 'normal' -- only if the current stage gate is fully satisfied.
      * 'risk'   -- advance despite missing required items; each missing item
                    is recorded as a skip (reason/impact/approver/recovery).
      * 'return' -- move back one stage and clear its gate for re-evaluation.
    """
    gate = compute_gate(store)
    if mode == "return":
        idx = STAGES.index(store.current_stage) if store.current_stage in STAGES else 0
        if idx <= 0:
            return {"ok": False, "error": "已是第一阶段，无法返回。", **_status_dict(store, gate)}
        prev = STAGES[idx - 1]
        store.current_stage = prev
        store.tasks = {}
        store._reset_stage(prev)
        store.progress = compute_progress(store)
        store.events.append({"type": "return", "to": prev, "at": time.time()})
        store.save()
        new_gate = compute_gate(store)
        return {"ok": True, "stage": prev, **_status_dict(store, new_gate)}

    if store.current_stage not in STAGES:
        return {"ok": False, "error": "未知阶段。", **_status_dict(store, gate)}
    idx = STAGES.index(store.current_stage)
    if idx >= len(STAGES) - 1:
        return {"ok": False, "error": "已是最后阶段，无法继续推进。", **_status_dict(store, gate)}

    required_missing = [c for c in gate.missing if c.kind not in {"task", "confirmation"} and c.required]
    if mode == "normal" and required_missing:
        reason = gate.blocked_entry_reason or ("未满足：" + "、".join(c.label for c in required_missing))
        return {"ok": False, "error": reason, **_status_dict(store, gate)}

    if mode == "risk":
        hard_missing = [c for c in required_missing if not c.skippable]
        if hard_missing:
            return {
                "ok": False,
                "error": "以下硬性条件不可带风险跳过：" + "、".join(c.label for c in hard_missing),
                **_status_dict(store, gate),
            }

    if mode == "risk" and required_missing:
        details = risk_details if risk_details is not None else {
            "reason": "系统兼容推进：未提供用户风险说明",
            "impact": "跳过的内容可能在后续引发返工或缺陷",
            "recovery": "返回上一阶段补齐该条件",
        }
        if risk_details is not None and not str(details.get("reason") or "").strip():
            return {"ok": False, "error": "带风险推进前必须填写具体原因。", **_status_dict(store, gate)}
        for c in required_missing:
            store.record_skip(
                c.item_id,
                reason=str(details.get("reason") or "").strip(),
                impact=str(details.get("impact") or "跳过的内容可能在后续引发返工或缺陷").strip(),
                approver="用户",
                recovery=str(details.get("recovery") or "返回上一阶段补齐该条件").strip(),
            )

    # Advancing = the user confirms the current stage's required confirmations.
    definition = STAGE_DEFINITIONS.get(store.current_stage)
    if definition is not None:
        for item in definition.items:
            if item.kind == "confirmation":
                store.record_confirmation(item.id, True, detail="用户确认（进入下一阶段）")

    nxt = STAGES[idx + 1]
    entry_reason = entry_blocked(store, nxt)
    if entry_reason:
        return {"ok": False, "error": entry_reason, **_status_dict(store, gate)}
    store.current_stage = nxt
    store.tasks = {}
    store._reset_stage(nxt)
    store.progress = compute_progress(store)
    store.events.append({"type": "advance", "mode": mode, "to": nxt, "at": time.time()})
    store.save()
    new_gate = compute_gate(store)
    return {"ok": True, "stage": nxt, "risk": mode == "risk", **_status_dict(store, new_gate)}
