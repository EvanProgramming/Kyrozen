"""Tools for Kyrozen Phase 8 Testing, Validation and Iteration Loop."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kyrozen.hardware.bridge import HardwareBridge
from kyrozen.testing.models import (
    IterationPlan,
    TestCase,
    TestPlan,
    TestResult,
    UserFeedback,
    ValidationReport,
)

from .base import Tool, ToolParameter, ToolResult, ToolSchema

if TYPE_CHECKING:
    from kyrozen.project import ProjectManager


# Safety patterns borrowed from TerminalTool.
_BLOCKED_PATTERNS = [
    r"\brm\s+(-rf?|-\s*rf?)\s",
    r"\brm\s+.*-r",
    r"^\s*rm\s+-rf",
    r"\brm\s+-rf\b",
    r"\bmkfs\.\w+",
    r">\s*/dev/sd",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&",
    r"wget\s+.*\|\s*sh\s*$",
    r"curl\s+.*\|\s*sh\s*$",
    r"\bdel\s+/[fs](?:\s+/[sq])?\s+\S:\\\\",
    r"\brd\s+/[sq]\s+\S:\\\\",
    r"\brmdir\s+/[sq]\s+\S:\\\\",
    r"\bformat\s+\w:",
    r"\bdiskpart\b",
    r"\bwmic\s+process\s+where.*delete\b",
    r"\btaskkill\s+/f\s+/im\s+(?:svchost|winlogon|csrss|lsass|smss|wininit|services)\b",
    r"\breg\s+delete\s+HKLM",
    r"\bicacls\s+\S+\s+/deny",
    r"\bdeltree\b",
]
_BLOCKED_RE = re.compile("|".join(_BLOCKED_PATTERNS), re.IGNORECASE)


def _is_dangerous(cmd: str) -> bool:
    return bool(_BLOCKED_RE.search(cmd))


def _project_dir(project_manager: "ProjectManager | None", project_id: str, subdir: str) -> Path:
    """Return a project subdirectory, creating it if necessary."""
    if project_manager is None:
        raise RuntimeError("Project manager not available")
    workspace_root = getattr(project_manager, "workspace_root", "")
    if not workspace_root:
        workspace_root = os.path.dirname(getattr(project_manager.db, "db_path", ""))
    base = Path(workspace_root) / "projects" / project_id / subdir
    base.mkdir(parents=True, exist_ok=True)
    return base


class SaveTestPlanTool(Tool):
    """Save or update the Test Plan artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_test_plan"
        self.description = "Save or update the Test Plan artifact for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="plan", param_type="object", description="Test Plan fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        plan_data = parameters.get("plan", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            plan = TestPlan.from_dict(plan_data)
            content = json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="test_plan",
                title="Test Plan",
                content=content,
                change_reason="Test plan update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveTestCaseTool(Tool):
    """Save or update a single Test Case artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_test_case"
        self.description = "Save or update a Test Case artifact for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="case", param_type="object", description="Test Case fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        case_data = parameters.get("case", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            case = TestCase.from_dict(case_data)
            title = f"Test Case: {case.id} - {case.name}" if case.id else "Test Case"
            content = json.dumps(case.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="test_case",
                title=title,
                content=content,
                change_reason="Test case update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveTestResultTool(Tool):
    """Save a Test Result artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_test_result"
        self.description = "Save a Test Result artifact for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="result", param_type="object", description="Test Result fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        result_data = parameters.get("result", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            if not result_data.get("timestamp"):
                result_data["timestamp"] = datetime.now(timezone.utc).isoformat()
            result = TestResult.from_dict(result_data)
            title = f"Test Result: {result.test_case_id} -> {result.result}" if result.test_case_id else "Test Result"
            content = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="test_result",
                title=title,
                content=content,
                change_reason="Test result recorded",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class RecordUserFeedbackTool(Tool):
    """Record a piece of user validation feedback for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "record_user_feedback"
        self.description = "Record user validation feedback (interview, trial, survey, comparison)."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "record": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="feedback", param_type="object", description="User Feedback fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        feedback_data = parameters.get("feedback", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            if not feedback_data.get("timestamp"):
                feedback_data["timestamp"] = datetime.now(timezone.utc).isoformat()
            feedback = UserFeedback.from_dict(feedback_data)
            title = f"User Feedback: {feedback.source_type} ({feedback.sentiment})"
            content = json.dumps(feedback.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="user_feedback",
                title=title,
                content=content,
                change_reason="User feedback recorded",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveValidationReportTool(Tool):
    """Save or update the Product Validation Report artifact."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_validation_report"
        self.description = "Save or update the Product Validation Report artifact."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="report", param_type="object", description="Validation Report fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        report_data = parameters.get("report", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            report = ValidationReport.from_dict(report_data)
            content = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="validation_report",
                title="Validation Report",
                content=content,
                change_reason="Validation report update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveIterationPlanTool(Tool):
    """Save or update the Iteration Plan artifact."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_iteration_plan"
        self.description = "Save or update the Iteration Plan artifact."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="plan", param_type="object", description="Iteration Plan fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        plan_data = parameters.get("plan", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            plan = IterationPlan.from_dict(plan_data)
            content = json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="iteration_plan",
                title="Iteration Plan",
                content=content,
                change_reason="Iteration plan update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class RunSoftwareTestTool(Tool):
    """Execute a software test command in the project's software directory."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "run_software_test"
        self.description = "Run a software test command in projects/{project_id}/software/."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "run": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="command", param_type="string", description="Test command, e.g. pytest or npm test"),
                    ToolParameter(name="timeout", param_type="integer", description="Timeout in seconds", required=False),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        command = parameters.get("command", "").strip()
        timeout = int(parameters.get("timeout") or 120)
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        if not command:
            return ToolResult(success=False, data=None, error="Missing command")
        if _is_dangerous(command):
            return ToolResult(success=False, data=None, error="Command blocked for safety")

        cwd = _project_dir(self.project_manager, project_id, "software")
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ToolResult(
                success=result.returncode == 0,
                data={
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "cwd": str(cwd),
                },
                error=result.stderr if result.returncode != 0 else "",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, data=None, error=f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"Error executing command: {e}")


class RunHardwareTestTool(Tool):
    """Execute a hardware test action via the Local Hardware Bridge."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "run_hardware_test"
        self.description = "Run a hardware test action (compile, upload, monitor) via arduino-cli or platformio."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "compile": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="board", param_type="string", description="Board FQBN (for arduino-cli)", required=False),
                ],
                "upload": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="board", param_type="string", description="Board FQBN (for arduino-cli)", required=False),
                    ToolParameter(name="port", param_type="string", description="Serial port", required=False),
                ],
                "monitor": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="port", param_type="string", description="Serial port"),
                    ToolParameter(name="baud", param_type="integer", description="Baud rate", required=False),
                ],
                "list_ports": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                ],
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")

        firmware_dir = _project_dir(self.project_manager, project_id, "hardware") / "firmware"
        firmware_dir.mkdir(parents=True, exist_ok=True)
        bridge = HardwareBridge(firmware_dir)

        try:
            if action == "list_ports":
                result = bridge.list_ports()
            elif action == "compile":
                result = bridge.compile(board=parameters.get("board"))
            elif action == "upload":
                result = bridge.upload(board=parameters.get("board"), port=parameters.get("port"))
            elif action == "monitor":
                port = parameters.get("port")
                if not port:
                    return ToolResult(success=False, data=None, error="Missing port for monitor")
                result = bridge.monitor(port=port, baud=int(parameters.get("baud") or 115200))
            else:
                return ToolResult(success=False, data=None, error=f"Unsupported hardware test action '{action}'")
            return ToolResult(success=result.get("success", False), data=result, error=result.get("stderr", ""))
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"{type(e).__name__}: {e}")
