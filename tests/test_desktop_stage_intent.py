"""Regression tests for Round-3 fixes: natural-language stage progression and
user-facing answer sanitization (no internal tool JSON / annotations in chat).

These load the desktop python_agent module directly because it is not part of
the importable ``kyrozen`` package.
"""

import importlib.util
import os
from pathlib import Path

from kyrozen.core.handoff import HandoffStore
from kyrozen.core.stagegate import StageGateStore

_AGENT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "desktop", "python_agent", "main.py"
)
_spec = importlib.util.spec_from_file_location(
    "kyrozen_test_desktop_agent", os.path.abspath(_AGENT_PATH)
)
desktop_agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(desktop_agent)


def test_detect_intended_stage_development():
    assert (
        desktop_agent._detect_intended_stage(
            "可以开始，直接帮我做出来，我想打开看看能不能用"
        )
        == "development"
    )
    assert desktop_agent._detect_intended_stage("帮我生成这个应用") == "development"


def test_detect_intended_stage_market_product_tech():
    assert (
        desktop_agent._detect_intended_stage("帮我看看这种旅行清单工具有没有人需要")
        == "market_research"
    )
    assert (
        desktop_agent._detect_intended_stage("你帮我把产品功能定下来")
        == "product_definition"
    )
    assert (
        desktop_agent._detect_intended_stage("你继续设计实现方式") == "solution_design"
    )


def test_detect_intended_stage_none_for_plain_qa():
    assert desktop_agent._detect_intended_stage("我主要是自己和家人周末出游用") is None
    assert desktop_agent._detect_intended_stage("当前进度如何") is None
    assert desktop_agent._detect_intended_stage("") is None


def test_detect_intended_stage_picks_furthest_match():
    # A message mentioning both market and development should land in development.
    assert (
        desktop_agent._detect_intended_stage("先调研一下市场，再帮我做出来")
        == "development"
    )


def test_explicit_ordinary_user_advance_phrases():
    assert desktop_agent._is_explicit_stage_advance_message("我想自己从零做一个，继续吧。")
    assert desktop_agent._is_explicit_stage_advance_message("可以继续下一步")
    assert not desktop_agent._is_explicit_stage_advance_message("继续调研第二个竞品")


def test_explicit_continue_confirms_and_advances_exactly_one_stage(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "MARKET.md").write_text("# 市场调研\n\n有外部证据", encoding="utf-8")
    store = StageGateStore(tmp_path / ".kyrozen" / "stagegate.json", project_id="p1")
    store.current_stage = "market_research"
    store.save()

    result = desktop_agent._advance_stage_for_user_message(
        store, tmp_path, "我想自己从零做一个，继续吧。"
    )

    assert result is not None and result["ok"] is True
    assert result["stage"] == "product_definition"
    assert store.current_stage == "product_definition"
    assert store.records["market_confirmed"]["confirmed"] is True
    # The same message cannot jump again because product_definition has no PRD.
    blocked = desktop_agent._advance_stage_for_user_message(store, tmp_path, "直接帮我做出来")
    assert blocked is not None and blocked["ok"] is False
    assert store.current_stage == "product_definition"


def test_desktop_project_manager_persists_tool_artifacts_and_decisions(tmp_path: Path):
    manager = desktop_agent._ensure_desktop_project_manager(
        tmp_path, "cloud_project_42", "market_research"
    )
    assert manager is not None
    assert manager.get("cloud_project_42") is not None

    registry = desktop_agent.get_default_registry(project_manager=manager)
    decision = registry.execute(
        "record_opportunity_decision",
        "record",
        {
            "project_id": "cloud_project_42",
            "decision": "continue_development",
            "reason": "用户选择自己从零实现",
        },
    )
    assert decision.success, decision.error
    assert manager.list_decisions("cloud_project_42")


def test_successful_transition_is_written_to_handoff_and_project_store(tmp_path: Path):
    manager = desktop_agent._ensure_desktop_project_manager(tmp_path, "p1", "market_research")
    handoff = HandoffStore(tmp_path / ".kyrozen" / "handoff.json", project_id="p1")
    text = desktop_agent._persist_stage_transition_decision(
        handoff,
        manager,
        "p1",
        "我想自己从零做，继续吧",
        {"ok": True, "from_stage": "market_research", "stage": "product_definition"},
    )
    assert text is not None
    assert handoff.decisions and text in handoff.decisions[0].content
    assert manager is not None
    assert manager.list_decisions("p1")[0].decision == text


def test_stage_action_ignores_stale_renderer_stage(tmp_path: Path):
    store = StageGateStore(tmp_path / ".kyrozen" / "stagegate.json", project_id="p1")
    store.current_stage = "market_research"
    store.save()
    runtime = desktop_agent.DesktopAgentRuntime.__new__(desktop_agent.DesktopAgentRuntime)
    responses = []
    runtime._send_response = lambda req_id, **payload: responses.append((req_id, payload))
    runtime._push_stage = lambda *_args, **_kwargs: None

    runtime._handle_stage_action(
        {
            "action": "refresh",
            "workspace_root": str(tmp_path),
            "project_id": "p1",
            "stage": "problem_discovery",
        },
        "req-1",
    )

    reopened = StageGateStore(tmp_path / ".kyrozen" / "stagegate.json", project_id="p1")
    assert reopened.current_stage == "market_research"
    assert responses and responses[0][1]["result"]["stage"] == "market_research"


def test_sanitize_strips_inline_tool_json():
    cls = desktop_agent.DesktopAgentRuntime
    out = cls._sanitize_user_answer(
        '结论 {"tool": "save_problem_brief", "action": "save", "parameters": {}} 谢谢 ← 使用空数组替代 none'
    )
    assert '"tool"' not in out
    assert "save_problem_brief" not in out
    assert "←" not in out


def test_sanitize_strips_fenced_tool_json():
    cls = desktop_agent.DesktopAgentRuntime
    out = cls._sanitize_user_answer(
        '请执行：\n```json\n{"tool": "file_write", "action": "write"}\n```'
    )
    assert '"tool"' not in out
