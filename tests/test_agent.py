"""Tests for the BaseAgent runtime."""

from __future__ import annotations

import os

import pytest

from kyrozen.core.agent import BaseAgent
from kyrozen.core.permission import PermissionManager
from kyrozen.core.task import TaskManager
from kyrozen.logs import get_logger
from kyrozen.memory.interface import InMemoryMemory
from kyrozen.tools import get_default_registry

from .conftest import MockModel


def build_agent(test_config, responses=None):
    return BaseAgent(
        config=test_config,
        model=MockModel(responses=responses),
        tools=get_default_registry(),
        memory=InMemoryMemory(),
        task_manager=TaskManager(store_path=test_config.task_store_path),
        permission_manager=PermissionManager(mode=test_config.permission_mode),
        logger=get_logger(test_config.log_level, log_dir=os.path.join(os.path.dirname(test_config.task_store_path), "logs")),
    )


def test_agent_direct_answer(test_config):
    agent = build_agent(test_config, responses=["This is the final answer."])
    task = agent.run("Say hello")
    assert task.status == "completed"
    assert task.result["answer"] == "This is the final answer."


def test_agent_tool_call_then_answer(test_config):
    tool_call = '{"tool": "list_dir", "action": "list", "parameters": {"path": "."}}'
    agent = build_agent(test_config, responses=[tool_call, "I listed the directory."])
    task = agent.run("List files")
    assert task.status == "completed"
    assert task.result["answer"] == "I listed the directory."
    assert any("list_dir" in s.description for s in task.steps)


def test_agent_waiting_confirmation_in_strict_mode(test_config):
    test_config.permission_mode = "strict"
    tool_call = '{"tool": "file_write", "action": "write", "parameters": {"path": "test.txt", "content": "x"}}'
    agent = build_agent(test_config, responses=[tool_call])
    task = agent.run("Write a file")
    assert task.status == "waiting_confirmation"
    assert any(s.status == "waiting_confirmation" for s in task.steps)


def test_agent_confirm_then_continue(test_config):
    test_config.permission_mode = "strict"
    tool_call = '{"tool": "file_write", "action": "write", "parameters": {"path": "test.txt", "content": "x"}}'
    agent = build_agent(test_config, responses=[tool_call, "File written."])
    task = agent.run("Write a file")
    assert task.status == "waiting_confirmation"

    task2 = agent.run(task.description, confirmed=True)
    assert task2.status == "completed"
    assert task2.result["answer"] == "File written."


def test_agent_extract_tool_calls_from_markdown(test_config):
    agent = build_agent(test_config)
    text = 'Some text\n```json\n{"tool": "file_read", "action": "read", "parameters": {"path": "x"}}\n```'
    calls = agent._extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "file_read"


def test_agent_extract_multiple_tool_calls(test_config):
    agent = build_agent(test_config)
    text = '[{"tool": "file_read", "action": "read", "parameters": {"path": "x"}}, {"tool": "list_dir", "action": "list", "parameters": {}}]'
    calls = agent._extract_tool_calls(text)
    assert len(calls) == 2


def test_agent_extract_inline_tool_call_with_preamble(test_config):
    agent = build_agent(test_config)
    text = 'I will list the directory.\n{"tool": "list_dir", "action": "list", "parameters": {"path": "."}}'
    calls = agent._extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "list_dir"


def test_agent_strip_tool_calls_from_text(test_config):
    agent = build_agent(test_config)
    text = 'I will search.\n{"tool": "web_search", "action": "search", "parameters": {"query": "x"}}'
    clean = agent._strip_tool_calls_from_text(text)
    assert clean == "I will search."


def test_agent_tool_call_only_does_not_return_raw_json(test_config):
    """If the model outputs only an inline tool-call JSON, the final answer must not be raw JSON."""
    tool_call = '{"tool": "list_dir", "action": "list", "parameters": {"path": "."}}'
    agent = build_agent(test_config, responses=[tool_call, "Done."])
    task = agent.run("List files")
    assert task.status == "completed"
    assert "tool" not in task.result["answer"]
    assert "{" not in task.result["answer"]


def test_agent_tool_call_in_code_block_does_not_return_raw_json(test_config):
    tool_call = '```json\n{"tool": "list_dir", "action": "list", "parameters": {"path": "."}}\n```'
    agent = build_agent(test_config, responses=[tool_call, "Done."])
    task = agent.run("List files")
    assert task.status == "completed"
    assert "tool" not in task.result["answer"]
    assert "{" not in task.result["answer"]


def test_agent_final_synthesis_when_max_rounds_exhausted(test_config):
    """If the model keeps requesting tools, the agent must still produce a non-JSON final answer."""
    tool_call = '{"tool": "list_dir", "action": "list", "parameters": {"path": "."}}'
    agent = build_agent(test_config, responses=[tool_call])
    task = agent.run("List files")
    assert task.status == "completed"
    assert "tool" not in task.result["answer"]
    assert "{" not in task.result["answer"]


def test_agent_extract_xml_tool_call(test_config):
    """Some models emit XML-style tool calls; the agent must parse them."""
    agent = build_agent(test_config)
    text = (
        "I will list the directory.\n"
        "<tool_call>\n"
        "  <tool_name>list_dir</tool_name>\n"
        "  <action>list</action>\n"
        "  <parameters>\n"
        "    <path>projects/proj_49be49d8/software</path>\n"
        "  </parameters>\n"
        "</tool_call>"
    )
    calls = agent._extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "list_dir"
    assert calls[0]["action"] == "list"
    assert calls[0]["parameters"]["path"] == "projects/proj_49be49d8/software"


def test_agent_strip_xml_tool_call_from_text(test_config):
    """XML tool-call blocks should be removed from the conversational text."""
    agent = build_agent(test_config)
    text = (
        "I will list the directory.\n"
        "<tool_call>\n"
        "  <tool_name>list_dir</tool_name>\n"
        "  <action>list</action>\n"
        "  <parameters><path>.</path></parameters>\n"
        "</tool_call>"
    )
    clean = agent._strip_tool_calls_from_text(text)
    assert "<tool_call>" not in clean
    assert "list_dir" not in clean
    assert clean.strip() == "I will list the directory."


def test_agent_xml_tool_call_then_answer(test_config):
    """A full loop with an XML tool call must execute the tool and return a clean answer."""
    xml_call = (
        "<tool_call>\n"
        "  <tool_name>list_dir</tool_name>\n"
        "  <action>list</action>\n"
        "  <parameters><path>.</path></parameters>\n"
        "</tool_call>"
    )
    agent = build_agent(test_config, responses=[xml_call, "I listed the directory."])
    task = agent.run("List files")
    assert task.status == "completed"
    assert task.result["answer"] == "I listed the directory."
    assert any("list_dir" in s.description for s in task.steps)
