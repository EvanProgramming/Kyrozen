"""Regression tests for the acceptance-2026-07-30 protocol/routing fixes.

1. ``DesktopAgentRuntime._normalize_question_blocks`` must guarantee that raw
   ``<kyrozen-question>`` protocol text never leaks into the chat area, in any
   of the malformed shapes the model has been observed to emit.
2. ``_requires_local_client`` keeps device/workspace execution local while
   sending research and planning to the server-side ProjectManager so their
   versioned Artifacts are persisted from the desktop journey.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_desktop_agent_module():
    main_py = REPO_ROOT / "desktop" / "python_agent" / "main.py"
    spec = importlib.util.spec_from_file_location("desktop_python_agent_main", main_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("desktop_python_agent_main", module)
    spec.loader.exec_module(module)
    return module


_agent_mod = _load_desktop_agent_module()
_normalize = _agent_mod.DesktopAgentRuntime._normalize_question_blocks


VALID_JSON = '{"question": "选哪个方向？", "options": [{"label": "A", "value": "a"}]}'


def test_plain_text_untouched():
    text = "这是一段普通回复，没有任何协议块。"
    assert _normalize(text) == text


def test_canonical_fenced_block_preserved():
    answer = f"前置说明\n\n```kyrozen-question\n{VALID_JSON}\n```"
    out = _normalize(answer)
    assert out.count("```kyrozen-question") == 1
    assert "选哪个方向？" in out
    assert "<kyrozen-question>" not in out


def test_xml_tag_form_converted_to_fenced():
    answer = f"先说明一下。<kyrozen-question>{VALID_JSON}</kyrozen-question>"
    out = _normalize(answer)
    assert "<kyrozen-question>" not in out
    assert out.count("```kyrozen-question") == 1
    assert "选哪个方向？" in out


def test_fenced_without_newline_normalized():
    answer = f"```kyrozen-question {VALID_JSON}```"
    out = _normalize(answer)
    assert out.count("```kyrozen-question") == 1
    assert "选哪个方向？" in out


def test_invalid_json_never_leaks_protocol():
    """A malformed block is salvaged into a valid free-text question card.

    The raw protocol text must never appear, and since every question has to go
    through the question UI, the salvaged question becomes a card with an empty
    option list (which the renderer shows as a text input) rather than prose.
    """
    answer = '<kyrozen-question>{"question": "坏块", "options": [</kyrozen-question>结尾文本'
    out = _normalize(answer)
    assert "<kyrozen-question>" not in out
    assert "坏块" in out  # human-readable question salvaged
    assert out.count("```kyrozen-question") == 1
    payload = json.loads(out.split("```kyrozen-question")[1].split("```")[0].strip())
    assert payload["question"] == "坏块"
    assert payload["options"] == []
    assert payload["allow_other"] is True


def test_option_less_question_stays_a_card():
    """Open-ended questions must remain cards (free-text input), not prose."""
    answer = '```kyrozen-question\n{"question": "你希望它解决什么问题？", "options": []}\n```'
    out = _normalize(answer)
    assert out.count("```kyrozen-question") == 1
    payload = json.loads(out.split("```kyrozen-question")[1].split("```")[0].strip())
    assert payload["question"] == "你希望它解决什么问题？"
    assert payload["options"] == []
    assert payload["allow_other"] is True


def test_allow_other_defaults_to_true_and_options_normalized():
    answer = (
        '```kyrozen-question\n'
        '{"question": "选哪个？", "options": [{"label": "A"}, "B"]}\n```'
    )
    out = _normalize(answer)
    payload = json.loads(out.split("```kyrozen-question")[1].split("```")[0].strip())
    assert payload["allow_other"] is True
    assert payload["options"] == [
        {"label": "A", "value": "A"},
        {"label": "B", "value": "B"},
    ]


def test_multiple_blocks_collapse_to_one():
    answer = (
        f"```kyrozen-question\n{VALID_JSON}\n```\n\n"
        f"<kyrozen-question>{VALID_JSON}</kyrozen-question>"
    )
    out = _normalize(answer)
    assert out.count("```kyrozen-question") == 1
    assert "<kyrozen-question>" not in out


def test_local_first_routing_keeps_device_work_local_and_artifact_modes_server_side():
    from kyrozen.api.server import _requires_local_client

    for mode in ["discovery", "development", "hardware", "testing", "learning"]:
        assert _requires_local_client(mode), f"mode {mode} should prefer desktop"
    for mode in ["market_research", "planning", "product_definition", "solution_design"]:
        assert not _requires_local_client(mode), f"mode {mode} should persist through the API ProjectManager"
    assert not _requires_local_client("chat_only_nonexistent_mode")
