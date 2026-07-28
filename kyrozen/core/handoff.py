"""Structured agent handoff state for Kyrozen.

Persists confirmed goals, non-goals, decisions, risks, and open tasks across
agent switches and application restarts, so a newly routed agent never
re-asks questions the user has already answered.

The store lives inside the project workspace (``.kyrozen/handoff.json``) on
the desktop client, so it survives restarts and stays with the project.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kyrozen.tools.base import Tool, ToolParameter, ToolResult, ToolSchema


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class HandoffEntry:
    """One structured item recorded during a conversation."""

    content: str
    mode: str = ""
    recorded_at: str = field(default_factory=_now)
    status: str = "open"  # only used by open tasks: open | done

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "mode": self.mode,
            "recorded_at": self.recorded_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HandoffEntry":
        return cls(
            content=str(data.get("content", "")),
            mode=str(data.get("mode", "")),
            recorded_at=str(data.get("recorded_at", _now())),
            status=str(data.get("status", "open")),
        )


class HandoffStore:
    """Persistent structured handoff state for one project."""

    CATEGORIES = ("confirmed_goals", "non_goals", "decisions", "risks", "open_tasks")

    def __init__(self, path: str | Path, project_id: str = "") -> None:
        self.path = Path(path)
        self.project_id = project_id
        self.confirmed_goals: list[HandoffEntry] = []
        self.non_goals: list[HandoffEntry] = []
        self.decisions: list[HandoffEntry] = []
        self.risks: list[HandoffEntry] = []
        self.open_tasks: list[HandoffEntry] = []
        self.handoffs: list[dict[str, Any]] = []
        self.last_mode: str = ""
        self.last_agent: str = ""
        self.updated_at: str = ""
        self._load()

    # ------------------------------------------------------------------ io

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for category in self.CATEGORIES:
            entries = data.get(category, [])
            if isinstance(entries, list):
                setattr(
                    self,
                    category,
                    [HandoffEntry.from_dict(e) for e in entries if isinstance(e, dict)],
                )
        self.handoffs = [h for h in data.get("handoffs", []) if isinstance(h, dict)]
        self.last_mode = str(data.get("last_mode", ""))
        self.last_agent = str(data.get("last_agent", ""))
        self.updated_at = str(data.get("updated_at", ""))
        if not self.project_id:
            self.project_id = str(data.get("project_id", ""))

    def save(self) -> None:
        self.updated_at = _now()
        payload: dict[str, Any] = {
            "project_id": self.project_id,
            "updated_at": self.updated_at,
            "last_mode": self.last_mode,
            "last_agent": self.last_agent,
            "handoffs": self.handoffs[-50:],
        }
        for category in self.CATEGORIES:
            payload[category] = [e.to_dict() for e in getattr(self, category)]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)

    # -------------------------------------------------------------- records

    def _add(self, category: str, content: str, mode: str) -> bool:
        content = content.strip()
        if not content:
            return False
        entries: list[HandoffEntry] = getattr(self, category)
        if any(e.content == content for e in entries):
            return False  # already recorded; keep the store deduplicated
        entries.append(HandoffEntry(content=content, mode=mode))
        self.save()
        return True

    def add_confirmed_goal(self, content: str, mode: str = "") -> bool:
        return self._add("confirmed_goals", content, mode)

    def add_non_goal(self, content: str, mode: str = "") -> bool:
        return self._add("non_goals", content, mode)

    def add_decision(self, content: str, mode: str = "") -> bool:
        return self._add("decisions", content, mode)

    def add_risk(self, content: str, mode: str = "") -> bool:
        return self._add("risks", content, mode)

    def add_open_task(self, content: str, mode: str = "") -> bool:
        return self._add("open_tasks", content, mode)

    def complete_open_task(self, content: str) -> bool:
        content = content.strip()
        for entry in self.open_tasks:
            if entry.content == content and entry.status != "done":
                entry.status = "done"
                self.save()
                return True
        return False

    # -------------------------------------------------------------- handoff

    def record_handoff(
        self,
        *,
        source_mode: str,
        source_agent: str,
        target_mode: str,
        target_agent: str,
    ) -> dict[str, Any]:
        """Snapshot the structured state when the active agent changes."""
        summary = {
            "created_at": _now(),
            "source_mode": source_mode,
            "source_agent": source_agent,
            "target_mode": target_mode,
            "target_agent": target_agent,
            "confirmed_goals": [e.content for e in self.confirmed_goals],
            "non_goals": [e.content for e in self.non_goals],
            "decisions": [e.content for e in self.decisions],
            "risks": [e.content for e in self.risks],
            "open_tasks": [e.content for e in self.open_tasks if e.status != "done"],
        }
        self.handoffs.append(summary)
        self.save()
        return summary

    def set_current_agent(self, mode: str, agent_name: str) -> None:
        self.last_mode = mode
        self.last_agent = agent_name
        self.save()

    # -------------------------------------------------------------- context

    def is_empty(self) -> bool:
        return not any(getattr(self, category) for category in self.CATEGORIES)

    def context_block(self) -> str:
        """Render the structured state as a context block for the next agent."""
        if self.is_empty():
            return ""
        lines: list[str] = ["[项目交接上下文 — 以下内容已与用户确认，请勿重复询问]"]
        sections = (
            ("已确认目标", self.confirmed_goals),
            ("非目标（明确不做）", self.non_goals),
            ("已做出的决策", self.decisions),
            ("已识别的风险", self.risks),
        )
        for title, entries in sections:
            if entries:
                lines.append(f"{title}:")
                lines.extend(f"- {e.content}" for e in entries)
        open_entries = [e for e in self.open_tasks if e.status != "done"]
        if open_entries:
            lines.append("未完成任务:")
            lines.extend(f"- {e.content}" for e in open_entries)
        lines.append(
            "规则: 上述目标、非目标与决策已经过用户确认。不要再次询问这些问题；"
            "直接在其基础上继续工作。如果用户明确推翻某项内容，请用 handoff 工具记录新的结论。"
        )
        return "\n".join(lines)


class HandoffTool(Tool):
    """Tool that lets any agent record structured handoff facts in real time."""

    name = "handoff"
    description = (
        "Record confirmed goals, non-goals, decisions, risks, and open tasks so the "
        "next agent (or a restarted session) never re-asks answered questions. "
        "Call this whenever the user confirms a goal, rules something out, makes a "
        "decision, or when you identify a risk or leave a task unfinished."
    )

    def __init__(self, store: HandoffStore, mode: str = "") -> None:
        self.store = store
        self.mode = mode
        content_param = [ToolParameter(name="content", param_type="string", description="Concise statement to record")]
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "record_confirmed_goal": list(content_param),
                "record_non_goal": list(content_param),
                "record_decision": list(content_param),
                "record_risk": list(content_param),
                "record_open_task": list(content_param),
                "complete_open_task": list(content_param),
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        content = str(parameters.get("content", "")).strip()
        if not content:
            return ToolResult(success=False, data=None, error="content is required")
        handlers = {
            "record_confirmed_goal": self.store.add_confirmed_goal,
            "record_non_goal": self.store.add_non_goal,
            "record_decision": self.store.add_decision,
            "record_risk": self.store.add_risk,
            "record_open_task": self.store.add_open_task,
        }
        if action == "complete_open_task":
            done = self.store.complete_open_task(content)
            return ToolResult(success=True, data={"completed": done, "content": content})
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(success=False, data=None, error=f"Unknown action: {action}")
        added = handler(content, self.mode)
        return ToolResult(success=True, data={"recorded": added, "duplicate": not added, "content": content})
