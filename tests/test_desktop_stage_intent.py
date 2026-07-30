"""Regression tests for Round-3 fixes: natural-language stage progression and
user-facing answer sanitization (no internal tool JSON / annotations in chat).

These load the desktop python_agent module directly because it is not part of
the importable ``kyrozen`` package.
"""

import importlib.util
import os

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
