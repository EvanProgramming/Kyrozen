"""Operation records and diagnostic records (feature 3.4, requirements #3 and #6).

``OperationLog`` keeps a time-ordered, collapsible record of tool actions shown
to the user (action, start/end, duration, input/output summary, success/failure,
failure reason). ``DiagnosticsLog`` is a *separate* sink for noisy internal data
-- token counts, Python install output, raw tool JSON, internal logs -- that must
NEVER surface in the user-facing operation log or status bar.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The four diagnostic kinds explicitly called out in requirement #6.
DIAGNOSTIC_KINDS: tuple[str, ...] = (
    "token_usage",
    "python_install",
    "tool_json",
    "internal_log",
)


@dataclass
class OperationRecord:
    id: str
    action: str
    started_at: float
    ended_at: float | None = None
    input_summary: str = ""
    output_summary: str = ""
    status: str = "running"  # running | success | failed
    error_reason: str = ""
    is_diagnostic: bool = False

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return round((self.ended_at - self.started_at) * 1000, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "status": self.status,
            "error_reason": self.error_reason,
            "is_diagnostic": self.is_diagnostic,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OperationRecord":
        return cls(
            id=d["id"],
            action=d["action"],
            started_at=d["started_at"],
            ended_at=d.get("ended_at"),
            input_summary=d.get("input_summary", ""),
            output_summary=d.get("output_summary", ""),
            status=d.get("status", "running"),
            error_reason=d.get("error_reason", ""),
            is_diagnostic=d.get("is_diagnostic", False),
        )


class OperationLog:
    """Append-only, time-ordered log of user-facing tool operations."""

    def __init__(self, workspace: str | Path) -> None:
        self.dir = Path(workspace) / ".kyrozen"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "operation_log.jsonl"
        self._pending: dict[str, OperationRecord] = {}

    def start(self, action: str, input_summary: str = "") -> str:
        record_id = f"op_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        rec = OperationRecord(
            id=record_id,
            action=action,
            started_at=time.time(),
            input_summary=input_summary,
        )
        self._pending[record_id] = rec
        return record_id

    def end(
        self,
        record_id: str,
        *,
        output_summary: str = "",
        status: str = "success",
        error_reason: str = "",
    ) -> None:
        rec = self._pending.pop(record_id, None)
        if rec is None:
            # P0-12: try recovering the started record from disk in case the
            # in-memory _pending dict was lost across process restarts.
            existing = self.list()
            for entry in existing:
                if entry.get("id") == record_id:
                    rec = OperationRecord.from_dict(entry)
                    break
            if rec is None:
                rec = OperationRecord(id=record_id, action="", started_at=time.time())
        rec.ended_at = time.time()
        rec.output_summary = output_summary
        rec.status = status
        rec.error_reason = error_reason
        self._append(rec)

    def _append(self, rec: OperationRecord) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

    def list(self, limit: int | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.append(json.loads(line))
        except Exception:
            pass
        out.sort(key=lambda r: r.get("started_at", 0))
        if limit is not None:
            out = out[-limit:]
        return out


class DiagnosticsLog:
    """Separate sink for noisy internal data. Never shown in the operation log."""

    def __init__(self, workspace: str | Path) -> None:
        self.dir = Path(workspace) / ".kyrozen"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "diagnostics.jsonl"

    def append(self, kind: str, payload: Any) -> None:
        if kind not in DIAGNOSTIC_KINDS:
            raise ValueError(f"诊断类型必须是 {DIAGNOSTIC_KINDS} 之一")
        entry = {"ts": time.time(), "kind": kind, "payload": payload}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def list(
        self, kind: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    if kind is None or entry.get("kind") == kind:
                        out.append(entry)
        except Exception:
            pass
        if limit is not None:
            out = out[-limit:]
        return out
