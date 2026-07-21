"""Tests for Kyrozen tools."""

from __future__ import annotations

import os

from kyrozen.tools import get_default_registry
from kyrozen.tools.file_tools import FileReadTool, FileWriteTool, FindFilesTool, ListDirTool
from kyrozen.tools.terminal_tools import TerminalTool


def test_file_write_and_read(temp_dir: str):
    tool = FileWriteTool()
    path = os.path.join(temp_dir, "hello.txt")
    result = tool.execute("write", {"path": path, "content": "Hello Kyrozen"})
    assert result.success
    assert result.data["characters_written"] == 13

    read_tool = FileReadTool()
    result = read_tool.execute("read", {"path": path})
    assert result.success
    assert result.data["content"] == "Hello Kyrozen"


def test_file_read_missing():
    tool = FileReadTool()
    result = tool.execute("read", {"path": "/tmp/nonexistent_kyrozen_file.txt"})
    assert not result.success
    assert "not found" in result.error.lower()


def test_list_dir(temp_dir: str):
    open(os.path.join(temp_dir, "a.txt"), "w").close()
    os.makedirs(os.path.join(temp_dir, "sub"))
    tool = ListDirTool()
    result = tool.execute("list", {"path": temp_dir})
    assert result.success
    names = {e["name"] for e in result.data["entries"]}
    assert "a.txt" in names
    assert "sub" in names


def test_find_files(temp_dir: str):
    open(os.path.join(temp_dir, "foo.py"), "w").close()
    open(os.path.join(temp_dir, "bar.txt"), "w").close()
    tool = FindFilesTool()
    result = tool.execute("find", {"pattern": "*.py", "directory": temp_dir})
    assert result.success
    assert len(result.data["matches"]) == 1
    assert "foo.py" in result.data["matches"][0]


def test_terminal_echo():
    tool = TerminalTool()
    result = tool.execute("execute", {"command": "echo hello"})
    assert result.success
    assert "hello" in result.data["output"]


def test_terminal_blocked_command():
    tool = TerminalTool()
    result = tool.execute("execute", {"command": "rm -rf /some/path"})
    assert not result.success
    assert "blocked" in result.error.lower()


def test_registry_has_phase1_tools():
    registry = get_default_registry()
    names = registry.list_tools()
    assert "file_read" in names
    assert "file_write" in names
    assert "list_dir" in names
    assert "find_files" in names
    assert "terminal" in names
    assert "git" in names
