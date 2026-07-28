"""User-facing agent status (feature 3.4, requirement #2).

The status bar must only ever show the six states a user can understand:
Reading, Editing, Running, Searching, Waiting, Retrying. Any attempt to set
a different state is rejected so the UI can never display an opaque internal
token. State is persisted to ``<workspace>/.kyrozen/`` so it survives reload.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from pathlib import Path
from typing import Any


class StatusState(str, Enum):
    """The only six states the status bar is allowed to show."""

    READING = "reading"
    EDITING = "editing"
    RUNNING = "running"
    SEARCHING = "searching"
    WAITING = "waiting"
    RETRYING = "retrying"

    @property
    def display(self) -> str:
        return _DISPLAY[self]

    @property
    def is_user_facing(self) -> bool:
        # Every member of this enum is a user-facing state by definition.
        return True


_DISPLAY: dict[StatusState, str] = {
    StatusState.READING: "读取中",
    StatusState.EDITING: "编辑中",
    StatusState.RUNNING: "运行中",
    StatusState.SEARCHING: "搜索中",
    StatusState.WAITING: "等待中",
    StatusState.RETRYING: "重试中",
}

# The canonical, user-understandable set. Used for validation and UI options.
USER_FACING_STATES: list[str] = [s.value for s in StatusState]


def coerce_state(state: Any) -> StatusState | None:
    """Return a StatusState for ``state`` or ``None`` if it is not one of the six."""
    if isinstance(state, StatusState):
        return state
    try:
        return StatusState(str(state).lower())
    except ValueError:
        return None


class StatusManager:
    """Tracks the current agent status and its history for one workspace."""

    def __init__(self, workspace: str | Path) -> None:
        self.dir = Path(workspace) / ".kyrozen"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.status_path = self.dir / "status.json"
        self.log_path = self.dir / "status_log.jsonl"
        self._current = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.status_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {"state": None, "detail": None, "since": None}

    def set(self, state: Any, detail: str | None = None) -> dict[str, Any]:
        """Set the current status. Raises ``ValueError`` for any non-user-facing state."""
        coerced = coerce_state(state)
        if coerced is None:
            raise ValueError(
                "状态必须是以下之一：" + ", ".join(USER_FACING_STATES)
            )
        now = time.time()
        entry = {"ts": now, "state": coerced.value, "detail": detail}
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._current = {"state": coerced.value, "detail": detail, "since": now}
        self.status_path.write_text(
            json.dumps(self._current, ensure_ascii=False), encoding="utf-8"
        )
        return self.current()

    def clear(self) -> dict[str, Any]:
        """Return to the idle (ready) state. This is *not* one of the six; it is the absence of activity."""
        self._current = {"state": None, "detail": None, "since": None}
        self.status_path.write_text(
            json.dumps(self._current, ensure_ascii=False), encoding="utf-8"
        )
        return self.current()

    def current(self) -> dict[str, Any]:
        return dict(self._current)

    def history(self, limit: int | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            for line in self.log_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.append(json.loads(line))
        except Exception:
            pass
        if limit is not None:
            out = out[-limit:]
        return out
