"""Regression tests for the deterministic fallback reply (P0-R5).

The previous fallback reply included internal mechanism phrases like
"AI 未能自主写入文件，已由确定性生成引擎兜底完成开发交付" and pasted the
previous failed agent's reasoning under "此前 AI 的实现思路：". These are
implementation details, not user-facing artifacts, and they polluted the
main chat reply (Round 5 acceptance report, P1 issue).

This test pins the corrected behaviour: the fallback reply is a plain
user-language summary that tells the user what was produced and where to
find it; nothing about the AI's internal mode or the previous failed
attempt appears in the main reply.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from kyrozen.core.task import Task
from kyrozen.development.agent import SoftwareDevelopmentAgent


class _StubTool:
    """Minimal stand-in for the tools registry used by SoftwareDevelopmentAgent."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def execute(self, name: str, action: str, params: dict) -> "MagicMock":  # type: ignore[override]
        self.calls.append((name, action, params))
        result = MagicMock()
        result.success = True
        if action == "generate":
            result.data = {"files": [
                "README.md", "main.py", "tests/test_main.py",
                "index.html", "style.css", "app.js", "requirements.txt",
                ".gitignore",
            ]}
        elif action == "run":
            result.data = {
                "preview_url": "http://localhost:8000",
                "build_passes": True,
                "tests_pass": True,
            }
        else:
            result.data = {}
        result.error = None
        return result


def _make_agent(workspace_root: Path) -> tuple[SoftwareDevelopmentAgent, _StubTool]:
    """Build a SoftwareDevelopmentAgent with a stubbed tools registry."""
    config = MagicMock()
    config.workspace_root = str(workspace_root)

    agent = SoftwareDevelopmentAgent.__new__(SoftwareDevelopmentAgent)
    agent.config = config
    agent.logger = MagicMock()
    agent.tools = _StubTool()
    return agent, agent.tools


def test_fallback_reply_does_not_mention_internal_mechanism() -> None:
    """The Round 5 P0 leakage: the user-visible reply must not say things
    like 'AI 未能自主写入文件' or '确定性生成引擎兜底'."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "ws"
        ws.mkdir()
        agent, _tools = _make_agent(ws)
        task = Task(title="build me a family shopping list")

        reply = agent._deterministic_fallback(
            task,
            user_input="build me a family shopping list",
            model_answer="Here is my failed reasoning about how I would write the app…",
        )

    assert reply is not None, "fallback should produce a user-visible reply"
    for forbidden in (
        "AI 未能",
        "确定性生成引擎",
        "兜底完成",
        "兜底",
        "此前 AI 的实现思路",
    ):
        assert forbidden not in reply, (
            f"User-visible reply leaked internal phrase: {forbidden!r}\n"
            f"--- reply ---\n{reply}"
        )


def test_fallback_reply_summarises_user_outcome() -> None:
    """The reply must read like a normal summary for the user."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "ws"
        ws.mkdir()
        agent, _tools = _make_agent(ws)
        task = Task(title="build it")

        reply = agent._deterministic_fallback(task, "build it", "old reasoning")

    assert reply is not None
    # Should tell the user what was produced.
    assert "生成" in reply and "项目文件" in reply
    # Should mention local preview URL.
    assert "http://localhost:8000" in reply
    # Should describe verification result in plain language.
    assert "构建" in reply and ("通过" in reply or "验证" in reply)
    # Should invite further iteration in user-friendly language.
    assert "调整" in reply or "改" in reply


def test_fallback_reply_does_not_paste_failed_model_answer() -> None:
    """The previous failed model's reasoning must not appear in the reply."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "ws"
        ws.mkdir()
        agent, _tools = _make_agent(ws)
        task = Task(title="x")
        secret_marker = "ZZZ_INTERNAL_LEAK_MARKER_ZZZ"

        reply = agent._deterministic_fallback(
            task, "x", f"Here's what I would have done: {secret_marker} and more text"
        )

    assert reply is not None
    assert secret_marker not in reply, (
        "User-visible reply leaked the previous failed model's reasoning."
    )


def test_fallback_returns_none_without_workspace() -> None:
    """Without a workspace, fallback cannot run — return None so the task
    fails explicitly (caller surfaces a friendly error)."""
    config = MagicMock()
    config.workspace_root = None
    agent = SoftwareDevelopmentAgent.__new__(SoftwareDevelopmentAgent)
    agent.config = config
    agent.logger = MagicMock()
    agent.tools = _StubTool()
    task = Task(title="x")

    assert agent._deterministic_fallback(task, "x", "") is None