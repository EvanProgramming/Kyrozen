"""User-facing desktop activity text must not expose internal tool protocol names."""

from desktop.python_agent.main import DesktopAgentRuntime


def test_tool_activity_uses_plain_language_for_evidence_recording():
    description = DesktopAgentRuntime._describe_tool_operation(
        "record_evidence",
        "record",
        {"claim": "邻居通过微信群报名"},
    )

    assert description == "记录问题证据"
    assert "record_evidence" not in description
    assert "record" not in description


def test_unknown_tool_activity_does_not_leak_protocol_names():
    description = DesktopAgentRuntime._describe_tool_operation(
        "internal_only_tool",
        "execute",
        {},
    )

    assert description == "正在处理项目资料"
    assert "internal_only_tool" not in description


def test_common_tool_activity_is_localized_for_chinese_users():
    assert DesktopAgentRuntime._describe_tool_operation("list_dir", "list", {}) == "正在查看文件：项目工作区"
    assert DesktopAgentRuntime._describe_tool_operation("terminal", "execute", {"command": "pytest -q"}) == "正在运行命令：pytest -q"
