"""Kyrozen must never ask the user anything in plain prose.

Every question -- including throwaway confirmations like "需要我帮你做吗？" --
has to reach the user as a ``kyrozen-question`` card so the UI can render
clickable options plus a free-text "其他（自己输入）" field. Two layers guarantee
this and both are covered here:

1. the mandatory protocol section appended to *every* agent's system prompt;
2. ``BaseAgent._enforce_question_protocol``, the deterministic rewrite applied to
   the final answer when the model ignores the prompt anyway.
"""

from __future__ import annotations

import json
import re

import pytest

from kyrozen.core.agent import BaseAgent

BLOCK_RE = re.compile(r"```kyrozen-question\s*([\s\S]*?)\s*```")


def _payload(answer: str) -> dict:
    match = BLOCK_RE.search(answer)
    assert match, f"no question card produced for: {answer!r}"
    return json.loads(match.group(1))


# ---------------------------------------------------------------------------
# Layer 1: the prompt rule reaches every agent
# ---------------------------------------------------------------------------

def test_protocol_prompt_states_the_hard_rules():
    prompt = BaseAgent.QUESTION_PROTOCOL_PROMPT
    assert "kyrozen-question" in prompt
    assert "NEVER ask the user anything in plain prose" in prompt
    # The small-confirmation case the acceptance run kept tripping over.
    assert "需要我帮你做吗" in prompt
    assert "allow_other" in prompt
    # Option-less (free text) form must be documented.
    assert '"options": []' in prompt


def test_every_agent_inherits_the_protocol():
    """Specialised agents fully override _build_system_prompt; they still cannot
    opt out, because the protocol is appended in the loop, not in that method."""
    from kyrozen.development.agent import SoftwareDevelopmentAgent
    from kyrozen.discovery.agent import ProblemDiscoveryAgent
    from kyrozen.planning.agent import ProductPlanningAgent
    from kyrozen.research.agent import MarketResearchAgent
    from kyrozen.testing.agent import TestingAgent

    for agent_cls in (
        ProblemDiscoveryAgent,
        MarketResearchAgent,
        ProductPlanningAgent,
        SoftwareDevelopmentAgent,
        TestingAgent,
    ):
        assert agent_cls.QUESTION_PROTOCOL_PROMPT is BaseAgent.QUESTION_PROTOCOL_PROMPT


# ---------------------------------------------------------------------------
# Layer 2: deterministic enforcement of prose questions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "answer",
    [
        "我已经整理好了问题定义。需要我帮你做吗？",
        "方案已经写完。要继续推进吗？",
        "我可以现在开始生成代码，是否继续？",
        "初稿在这里。这样可以吗？",
        "I drafted the plan. Shall I proceed?",
    ],
)
def test_yes_no_confirmations_become_two_option_cards(answer):
    out = BaseAgent._enforce_question_protocol(answer)
    data = _payload(out)
    assert len(data["options"]) == 2
    assert data["allow_other"] is True
    # The question must not also remain in the prose body.
    body = BLOCK_RE.sub("", out).strip()
    assert data["question"] not in body


def test_open_ended_question_becomes_free_text_card():
    out = BaseAgent._enforce_question_protocol("先确认一下方向。你希望优先解决哪个场景？")
    data = _payload(out)
    assert data["question"] == "你希望优先解决哪个场景？"
    assert data["options"] == []
    assert data["allow_other"] is True
    assert "先确认一下方向。" in out


def test_existing_question_card_is_left_alone():
    answer = (
        "说明文字\n\n```kyrozen-question\n"
        '{"question": "选哪个？", "options": [{"label": "A", "value": "a"}], "allow_other": true}\n```'
    )
    assert BaseAgent._enforce_question_protocol(answer) == answer


def test_xml_form_is_not_double_wrapped():
    answer = '<kyrozen-question>{"question": "选哪个？", "options": []}</kyrozen-question>'
    assert BaseAgent._enforce_question_protocol(answer) == answer


@pytest.mark.parametrize(
    "answer",
    [
        "我已经把源码写进工作区了，可以直接运行。",
        "",
        "这是最终报告，包含 3 条外部证据。",
    ],
)
def test_non_questions_untouched(answer):
    assert BaseAgent._enforce_question_protocol(answer) == answer


def test_question_inside_unclosed_code_fence_is_not_extracted():
    answer = "示例代码：\n\n```python\n# 这样写对吗？\n"
    assert BaseAgent._enforce_question_protocol(answer) == answer


def test_markdown_decoration_stripped_from_question():
    out = BaseAgent._enforce_question_protocol("总结完毕。\n\n- **要现在开始开发吗？**")
    data = _payload(out)
    assert data["question"] == "要现在开始开发吗？"


def test_overly_long_trailing_question_is_not_forced():
    """A long paragraph ending in '?' is prose, not a question to click."""
    answer = "这是一段很长的说明。" + "细节" * 100 + "对吗？"
    assert BaseAgent._enforce_question_protocol(answer) == answer
