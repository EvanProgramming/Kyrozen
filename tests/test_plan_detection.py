"""Regression tests for the plan-detection heuristic (P0-R5).

The previous heuristic was too eager: any text with 2+ bullet lines got
captured as an execution plan and pushed to the 任务计划 panel. This caused
status reports / requirement reviews / question lists to render there as
if they were the agent's plan, which confused ordinary users.

These tests pin the corrected behaviour:
- An explicit heading keyword + ≥1 bullet → captured.
- A numbered step list (1./2./3.) → captured.
- Random bullets describing current state (without a heading or numbered
  enumeration) → NOT captured.
- Status-report style bullets (项目阶段 / Problem Brief / 已完成 / 尚未 …)
  → filtered out even when a heading is present.
"""

from __future__ import annotations

import pytest

from desktop.python_agent.main import PlanDetectingModelProvider, build_stage_plan


class _StubInner:
    def chat(self, messages, model=None):  # pragma: no cover - unused
        return None

    def chat_stream(self, messages, model=None):  # pragma: no cover - unused
        return iter(())


def _make() -> PlanDetectingModelProvider:
    captured: list[list[str]] = []

    def on_plan(steps: list[str]) -> None:
        captured.append(steps)

    provider = PlanDetectingModelProvider(_StubInner(), on_plan)
    return provider


def test_explicit_plan_heading_is_captured() -> None:
    p = _make()
    text = (
        "我已经看完了问题简报，下面是我的执行计划：\n"
        "- 搜索 3 个家庭购物清单竞品\n"
        "- 写一份市场研究摘要\n"
        "- 生成 MVP 代码框架"
    )
    assert p._extract_plan_steps(text) == [
        "搜索 3 个家庭购物清单竞品",
        "写一份市场研究摘要",
        "生成 MVP 代码框架",
    ]


def test_numbered_steps_captured_without_heading() -> None:
    p = _make()
    text = (
        "I'll proceed as follows:\n"
        "1. Search competitor apps\n"
        "2. Draft a market brief\n"
        "3. Generate MVP scaffold"
    )
    assert p._extract_plan_steps(text) == [
        "Search competitor apps",
        "Draft a market brief",
        "Generate MVP scaffold",
    ]


def test_status_report_bullets_are_not_a_plan() -> None:
    """The P0-R5 screenshot case: bullets describe current stage status,
    not future actions. Must not be captured as a plan."""
    p = _make()
    text = (
        "我来帮你看一下当前情况：\n"
        "- 项目阶段: product_definition (产品定义阶段)\n"
        "- Problem Brief: 已经创建，但内容不完整\n"
        "- 市场研究: 尚未进行\n"
        "- PRD: 尚未创建\n"
        "- 这个产品的确切名称和目标用户\n"
        "- 核心功能边界\n"
        "- 相比微信群，它必须解决的核心痛点"
    )
    assert p._extract_plan_steps(text) is None


def test_no_bullets_no_plan() -> None:
    p = _make()
    text = "随便一句话，没有任何列表结构。计划：先思考再行动。"
    assert p._extract_plan_steps(text) is None


def test_single_bullet_without_heading_is_not_a_plan() -> None:
    p = _make()
    text = "- 就这一件事"
    assert p._extract_plan_steps(text) is None


def test_heading_with_status_bullets_filters_them_out() -> None:
    """Even with an explicit heading, status-report bullets must be filtered
    so the panel shows only the actionable steps (P0-R5 hardening)."""
    p = _make()
    text = (
        "执行计划：\n"
        "- 项目阶段: product_definition\n"
        "- 已完成：保存用户输入\n"
        "- 尚未：进行市场研究\n"
        "- 接下来搜索竞品信息\n"
        "- 写一份摘要报告"
    )
    steps = p._extract_plan_steps(text)
    assert steps is not None
    assert "接下来搜索竞品信息" in steps
    assert "写一份摘要报告" in steps
    # Status-report bullets were filtered out.
    assert all("项目阶段" not in s for s in steps)
    assert all("尚未" not in s for s in steps)


def test_single_actionable_step_with_heading_is_a_plan() -> None:
    """One actionable step under a clear heading is still a (minimal) plan."""
    p = _make()
    text = (
        "执行计划：\n"
        "- 项目阶段: product_definition\n"
        "- 已完成：保存用户输入\n"
        "- 唯一要做的事"
    )
    assert p._extract_plan_steps(text) == ["唯一要做的事"]


def test_emit_only_once_per_task() -> None:
    """Once a plan is emitted, subsequent model output should not override it."""
    p = _make()
    emitted: list[list[str]] = []
    p._on_plan = lambda steps: emitted.append(steps)

    p._maybe_emit_plan("执行计划：\n- 先做 X\n- 再做 Y")
    p._maybe_emit_plan("执行计划：\n- 这条不应该出现")
    assert len(emitted) == 1
    assert emitted[0] == ["先做 X", "再做 Y"]


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n  \n",
        "无任何列表的纯文本",
    ],
)
def test_empty_or_plain_text_returns_none(text: str) -> None:
    p = _make()
    assert p._extract_plan_steps(text) is None


def test_stage_plan_is_structured_and_not_model_prose() -> None:
    plan = build_stage_plan("product_definition", "task-123")
    assert plan["title"] == "产品规划计划"
    assert plan["task_id"] == "task-123"
    steps = plan["steps"]
    assert isinstance(steps, list)
    assert len(steps) == 4
    assert steps[0]["status"] == "in_progress"
    assert all(step["title"] for step in steps)
    assert all("content" not in step for step in steps)
