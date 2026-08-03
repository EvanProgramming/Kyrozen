"""Tests for Kyrozen tools."""

from __future__ import annotations

import os
from pathlib import Path

from kyrozen.tools import get_default_registry
from kyrozen.tools.file_tools import FileReadTool, FileWriteTool, FindFilesTool, ListDirTool
from kyrozen.tools.terminal_tools import TerminalTool
from kyrozen.tools.project_tools import AdvanceProjectStageTool, UpdateProjectTool


def _set_workspace(monkeypatch, workspace: str) -> None:
    """Point the global configuration at a temporary workspace for isolation."""
    monkeypatch.setenv("KYROZEN_WORKSPACE", workspace)
    monkeypatch.setenv("KYROZEN_API_KEY", "test-key")


def test_file_write_and_read(temp_dir: str, monkeypatch):
    _set_workspace(monkeypatch, temp_dir)
    tool = FileWriteTool()
    path = os.path.join(temp_dir, "hello.txt")
    result = tool.execute("write", {"path": path, "content": "Hello Kyrozen"})
    assert result.success
    assert result.data["characters_written"] == 13

    read_tool = FileReadTool()
    result = read_tool.execute("read", {"path": path})
    assert result.success
    assert result.data["content"] == "Hello Kyrozen"


def test_file_read_missing(temp_dir: str, monkeypatch):
    _set_workspace(monkeypatch, temp_dir)
    tool = FileReadTool()
    result = tool.execute("read", {"path": os.path.join(temp_dir, "nonexistent_kyrozen_file.txt")})
    assert not result.success
    assert "not found" in result.error.lower()


def test_file_path_escape_blocked(temp_dir: str, monkeypatch):
    _set_workspace(monkeypatch, temp_dir)
    tool = FileWriteTool()
    result = tool.execute("write", {"path": "../outside_workspace.txt", "content": "x"})
    assert not result.success
    assert "outside the allowed workspace" in result.error.lower()


def test_file_absolute_outside_workspace_blocked(temp_dir: str, monkeypatch):
    _set_workspace(monkeypatch, temp_dir)
    tool = FileReadTool()
    result = tool.execute("read", {"path": "/etc/passwd"})
    assert not result.success
    assert "outside the allowed workspace" in result.error.lower()


def test_list_dir(temp_dir: str, monkeypatch):
    _set_workspace(monkeypatch, temp_dir)
    open(os.path.join(temp_dir, "a.txt"), "w").close()
    os.makedirs(os.path.join(temp_dir, "sub"))
    tool = ListDirTool()
    result = tool.execute("list", {"path": temp_dir})
    assert result.success
    names = {e["name"] for e in result.data["entries"]}
    assert "a.txt" in names
    assert "sub" in names


def test_find_files(temp_dir: str, monkeypatch):
    _set_workspace(monkeypatch, temp_dir)
    open(os.path.join(temp_dir, "foo.py"), "w").close()
    open(os.path.join(temp_dir, "bar.txt"), "w").close()
    tool = FindFilesTool()
    result = tool.execute("find", {"pattern": "*.py", "directory": temp_dir})
    assert result.success
    assert len(result.data["matches"]) == 1
    assert "foo.py" in result.data["matches"][0]


def test_terminal_echo(temp_dir: str, monkeypatch):
    _set_workspace(monkeypatch, temp_dir)
    tool = TerminalTool()
    result = tool.execute("execute", {"command": "echo hello"})
    assert result.success
    assert "hello" in result.data["output"]


def test_terminal_blocked_command():
    tool = TerminalTool()
    result = tool.execute("execute", {"command": "rm -rf /some/path"})
    assert not result.success
    assert "blocked" in result.error.lower()


def test_terminal_path_escape_blocked(temp_dir: str, monkeypatch):
    _set_workspace(monkeypatch, temp_dir)
    tool = TerminalTool()
    result = tool.execute("execute", {"command": "cat ../outside.txt"})
    assert not result.success
    assert "path escape" in result.error.lower()


def test_terminal_cwd_outside_workspace_blocked(temp_dir: str, monkeypatch):
    _set_workspace(monkeypatch, temp_dir)
    tool = TerminalTool()
    result = tool.execute("execute", {"command": "pwd", "cwd": "/etc"})
    assert not result.success
    assert "outside the allowed workspace" in result.error.lower()


def test_registry_has_phase1_tools():
    registry = get_default_registry()
    names = registry.list_tools()
    assert "file_read" in names
    assert "file_write" in names
    assert "list_dir" in names
    assert "find_files" in names
    assert "terminal" in names
    assert "git" in names
    assert "advance_project_stage" in names


def test_update_project_cannot_bypass_stage_gate(project_manager):
    project = project_manager.create("Gate protected")
    result = UpdateProjectTool(project_manager).execute(
        "update", {"project_id": project.id, "current_stage": "market_research"}
    )
    assert not result.success
    assert "advance_project_stage" in result.error
    assert project_manager.get(project.id).current_stage == "problem_discovery"


def test_advance_project_stage_uses_persisted_gate(project_manager):
    project = project_manager.create("Advance through gate")
    project_manager.update(project.id, type_confirmed=True)
    root = Path(project_manager.db.db_path).parent / "projects" / project.id / "docs"
    root.mkdir(parents=True)
    (root / "PROBLEM.md").write_text("# Problem\nA real problem", encoding="utf-8")

    result = AdvanceProjectStageTool(project_manager).execute("advance", {"project_id": project.id})
    assert result.success, result.error
    assert result.data["current_stage"] == "market_research"
    assert project_manager.get(project.id).current_stage == "market_research"
