"""Testing and Validation Agent for Kyrozen Phase 8."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kyrozen.core.agent import BaseAgent
from kyrozen.core.task import Task
from kyrozen.testing.models import TestCase

if TYPE_CHECKING:
    from kyrozen.project import ProjectManager


class TestingAgent(BaseAgent):
    """Agent specialized in testing, validating, and iterating on a product."""

    # A testing request is not complete when the model merely reviews files.
    # Requiring the execution tool activates the deterministic fallback below
    # when the model spends its limited rounds on discovery instead.
    required_actions = ("run_software_test",)

    def __init__(self, *args: Any, project_manager: "ProjectManager | None" = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.project_manager = project_manager

    def _build_system_prompt(self) -> str:
        schemas = self.tools.list_schemas()
        tools_text = json.dumps(schemas, ensure_ascii=False, indent=2)
        return (
            "You are Kyrozen Testing & Validation Agent. Your job is to verify whether the "
            "product actually solves the original problem, not just whether the code runs.\n\n"
            "When you need to use a tool, output a single JSON object in this exact format:\n"
            '{\n  "tool": "tool_name",\n  "action": "action_name",\n  "parameters": {...}\n}\n\n'
            "If you need multiple tools, output a JSON array of objects.\n"
            "If no tool is needed, reply with a plain text answer.\n\n"
            "Available tools:\n" + tools_text + "\n\n"
            "Rules:\n"
            "- Always respond in the same language as the user's latest message.\n"
            "- Read the PRD, Product Brief, Technical Plan, and existing implementation from the "
            "context before designing any test.\n"
            "- ALWAYS start by proposing a Test Plan and saving it with save_test_plan. "
            "The test plan must list the PRD requirements being tested and the test cases for each.\n"
            "- Map every test case to a PRD requirement via related_requirement and to a feature "
            "via related_feature when applicable.\n"
            "- Supported test types: functional, ui, api, performance, security, "
            "hardware_compile, hardware_module, hardware_integration, hardware_power, hardware_stability.\n"
            "- For software tests, use run_software_test to execute commands in "
            "projects/{project_id}/software/.\n"
            "- For hardware tests, use run_hardware_test to compile, upload, or monitor via "
            "arduino-cli / platformio.\n"
            "- When a test fails, do NOT immediately modify the product. Follow the debugging loop: "
            "observe symptom, compare with expected behavior, list possible causes, design a verification "
            "experiment, run it, isolate the cause, then propose a fix and re-test.\n"
            "- Save each test result with save_test_result, including stdout, stderr, actual observation, "
            "and errors.\n"
            "- Record user feedback with record_user_feedback. Collect interview, trial, survey, and "
            "comparison feedback when available.\n"
            "- Generate a Validation Report with save_validation_report that answers: did the product "
            "improve the original problem? Use conclusion: pass, fail, partial, or insufficient_evidence.\n"
            "- Generate an Iteration Plan with save_iteration_plan categorized as keep, modify, remove, "
            "investigate, or new_feature.\n"
            "- Record major validation or iteration decisions with record_decision.\n"
            "- Do NOT claim the product is finished just because tests pass. User validation is required.\n"
            "- Do NOT implement cross-project learning or autonomous knowledge migration. That is Phase 9.\n"
            "- Do NOT change product requirements, code, or hardware without explicit user confirmation.\n"
        )

    def _action_required(self, user_input: str) -> bool:
        return bool(re.search(r"测试|运行|执行|验证|验收|回归|test|verify", user_input or "", re.IGNORECASE))

    def _workspace_root(self) -> Path | None:
        root = getattr(self.config, "workspace_root", None)
        if not root:
            return None
        path = Path(root).expanduser().resolve()
        return path if path.is_dir() else None

    def _test_command(self, workspace: Path) -> str | None:
        if (workspace / "tests").is_dir():
            if (workspace / "pytest.ini").exists() or (workspace / "pyproject.toml").exists():
                return "python3 -m pytest -q"
            return "python3 -m unittest discover -s tests -p 'test_*.py' -v"
        package = workspace / "package.json"
        if package.exists():
            try:
                scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
                if scripts.get("test"):
                    return "npm test"
            except (OSError, json.JSONDecodeError):
                pass
        return None

    def _deterministic_fallback(self, task: Task, user_input: str, model_answer: str) -> str | None:
        """Always turn an ordinary testing request into real local evidence."""
        workspace = self._workspace_root()
        if workspace is None:
            return None
        command = self._test_command(workspace)
        if command is None:
            return "我检查了当前项目，但没有找到可执行的测试目录或测试脚本。"

        plan = {
            "name": "阶段验收测试计划",
            "objective": "验证当前项目的核心功能和可运行性",
            "requirements": ["项目能够按 README 提供的方式运行", "已有自动化测试应全部通过"],
            "test_cases": [TestCase(
                id="TC-SW-01",
                name="运行项目自动化测试",
                type="functional",
                related_requirement="已有自动化测试应全部通过",
                related_feature="核心功能",
                description=f"在项目工作区执行 {command}",
                steps=["运行项目测试命令", "检查退出码和测试汇总"],
                expected="命令退出码为 0，所有测试通过",
                environment="本地桌面客户端工作区",
                priority="high",
                status="ready",
            ).to_dict()],
            "success_criteria": "测试命令成功完成且没有失败用例",
            "environment": "本地桌面客户端工作区",
            "status": "running",
        }
        calls = [
            {"tool": "save_test_plan", "action": "save", "parameters": {"project_id": task.project_id or "local", "plan": plan}},
            {"tool": "run_software_test", "action": "run", "parameters": {"project_id": task.project_id or "local", "command": command, "timeout": 120}},
        ]
        results = self._execute_tool_calls(task, calls)
        run = next((item for item in results if item.get("tool") == "run_software_test"), None)
        if not run or not run.get("success"):
            error = (run or {}).get("result", {}).get("error") or (run or {}).get("error") or "测试执行失败"
            return f"测试计划已保存，但实际测试未通过：{error}"
        data = (run.get("result") or {}).get("data") or {}
        stdout = str(data.get("stdout", "")).strip()
        return f"我已实际运行项目测试，结果通过。\n\n命令：{command}\n\n{stdout[-4000:]}".strip()
