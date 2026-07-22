"""Tools for Kyrozen Phase 7 Hardware Development."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kyrozen.hardware.bridge import HardwareBridge
from kyrozen.hardware.models import (
    BOM,
    VALID_HARDWARE_DECISIONS,
    AssemblyStep,
    BOMItem,
    Component,
    FirmwareProject,
    HardwareArchitecture,
    HardwareDebugRecord,
    WiringDesign,
)
from kyrozen.tools.base import Tool, ToolParameter, ToolResult, ToolSchema

if TYPE_CHECKING:
    from kyrozen.project import ProjectManager


def _hardware_dir(project_manager: "ProjectManager | None", project_id: str) -> Path:
    """Return the hardware project directory for a project."""
    if project_manager is None:
        raise RuntimeError("Project manager not available")
    db = project_manager.db
    # Match the layout used by the software project summary helper.
    base = Path(os.path.dirname(db.db_path)) / "projects" / project_id / "hardware"
    base.mkdir(parents=True, exist_ok=True)
    return base


class SaveHardwareArchitectureTool(Tool):
    """Save or update the Hardware Architecture artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_hardware_architecture"
        self.description = "Save or update the Hardware Architecture artifact for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="architecture", param_type="object", description="Hardware Architecture fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        arch_data = parameters.get("architecture", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            arch = HardwareArchitecture.from_dict(arch_data)
            content = json.dumps(arch.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="hardware_architecture",
                title="Hardware Architecture",
                content=content,
                change_reason="Hardware architecture update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveComponentTool(Tool):
    """Save a component specification artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_component"
        self.description = "Save a component specification for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="component", param_type="object", description="Component fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        comp_data = parameters.get("component", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            component = Component.from_dict(comp_data)
            title = f"Component: {component.name}" if component.name else "Component Spec"
            content = json.dumps(component.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="component_spec",
                title=title,
                content=content,
                change_reason="Component selection update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveBOMTool(Tool):
    """Save or update the Bill of Materials artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_bom"
        self.description = "Save or update the Bill of Materials for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="bom", param_type="object", description="BOM fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        bom_data = parameters.get("bom", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            bom = BOM.from_dict(bom_data)
            content = json.dumps(bom.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="bom",
                title="Bill of Materials",
                content=content,
                change_reason="BOM update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class UpdatePurchaseStatusTool(Tool):
    """Update the purchase status of one BOM item."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "update_purchase_status"
        self.description = "Update the purchase status of one BOM item."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "update": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="component_name", param_type="string", description="Component name in the BOM"),
                    ToolParameter(name="status", param_type="string", description="New status: need_purchase, purchased, arrived, already_owned, alternative_needed"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        component_name = parameters.get("component_name")
        status = parameters.get("status")
        if not project_id or not component_name or not status:
            return ToolResult(success=False, data=None, error="Missing project_id, component_name, or status")
        try:
            latest = self.project_manager.get_latest_artifact(project_id, "bom", title="Bill of Materials")
            if latest is None:
                return ToolResult(success=False, data=None, error="No BOM found for project")
            bom = BOM.from_dict(json.loads(latest.content))
            for item in bom.items:
                if item.name == component_name:
                    item.purchase_status = status
                    content = json.dumps(bom.to_dict(), ensure_ascii=False, indent=2)
                    artifact = self.project_manager.save_artifact(
                        project_id=project_id,
                        type="bom",
                        title="Bill of Materials",
                        content=content,
                        change_reason=f"Updated purchase status of {component_name} to {status}",
                    )
                    return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
            return ToolResult(success=False, data=None, error=f"Component '{component_name}' not found in BOM")
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveWiringDesignTool(Tool):
    """Save or update the Wiring Design artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_wiring_design"
        self.description = "Save or update the Wiring Design for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="wiring", param_type="object", description="Wiring Design fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        wiring_data = parameters.get("wiring", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            wiring = WiringDesign.from_dict(wiring_data)
            content = json.dumps(wiring.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="wiring_design",
                title="Wiring Design",
                content=content,
                change_reason="Wiring design update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveFirmwareProjectTool(Tool):
    """Save or update the Firmware Project metadata artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_firmware_project"
        self.description = "Save or update the Firmware Project metadata for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="firmware", param_type="object", description="Firmware Project fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        firmware_data = parameters.get("firmware", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            firmware = FirmwareProject.from_dict(firmware_data)
            content = json.dumps(firmware.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="firmware_project",
                title="Firmware Project",
                content=content,
                change_reason="Firmware project update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class RecordHardwareDecisionTool(Tool):
    """Record a hardware development decision."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "record_hardware_decision"
        self.description = "Record a hardware development decision for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "record": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="decision", param_type="string", description="Decision: continue_hardware, change_component, narrow_scope, pause, abandon"),
                    ToolParameter(name="reason", param_type="string", description="Reason for the decision"),
                    ToolParameter(name="alternatives", param_type="array", description="Alternative decisions considered", required=False),
                    ToolParameter(name="rejected_reasons", param_type="object", description="Reasons rejected alternatives were not chosen", required=False),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        decision = parameters.get("decision")
        reason = parameters.get("reason", "")
        alternatives = parameters.get("alternatives") or []
        rejected_reasons = parameters.get("rejected_reasons") or {}
        if not project_id or not decision:
            return ToolResult(success=False, data=None, error="Missing project_id or decision")
        if decision not in VALID_HARDWARE_DECISIONS:
            return ToolResult(success=False, data=None, error=f"Invalid hardware decision '{decision}'")
        try:
            record = self.project_manager.add_decision(
                project_id=project_id,
                decision=f"Hardware decision: {decision}",
                reason=reason,
                alternatives=alternatives,
                rejected_reasons=rejected_reasons,
            )
            return ToolResult(success=True, data=record.to_dict())
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"{type(e).__name__}: {e}")


class SaveAssemblyStepTool(Tool):
    """Save an assembly step artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_assembly_step"
        self.description = "Save an assembly step for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="step", param_type="object", description="Assembly Step fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        step_data = parameters.get("step", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            step = AssemblyStep.from_dict(step_data)
            title = f"Assembly Step {step.order}: {step.title}" if step.title else f"Assembly Step {step.order}"
            content = json.dumps(step.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="assembly_step",
                title=title,
                content=content,
                change_reason="Assembly step update",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class SaveDebugRecordTool(Tool):
    """Save a hardware debug record artifact for a project."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "save_debug_record"
        self.description = "Save a hardware debug record for the current project."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "save": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                    ToolParameter(name="record", param_type="object", description="Debug Record fields as JSON object"),
                ]
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        record_data = parameters.get("record", {})
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")
        try:
            record = HardwareDebugRecord.from_dict(record_data)
            title = f"Debug: {record.symptom[:40]}" if record.symptom else "Hardware Debug Record"
            content = json.dumps(record.to_dict(), ensure_ascii=False, indent=2)
            artifact = self.project_manager.save_artifact(
                project_id=project_id,
                type="hardware_debug_record",
                title=title,
                content=content,
                change_reason="Hardware debug record",
            )
            return ToolResult(success=True, data={"artifact_id": artifact.id, "version": artifact.version})
        except ValueError as e:
            return ToolResult(success=False, data=None, error=str(e))


class HardwareBridgeTool(Tool):
    """Execute whitelisted local hardware commands (arduino-cli / platformio)."""

    def __init__(self, project_manager: "ProjectManager | None" = None) -> None:
        self.project_manager = project_manager
        self.name = "hardware_bridge"
        self.description = "Execute whitelisted local hardware commands via arduino-cli or platformio."
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            actions={
                "list_ports": [
                    ToolParameter(name="project_id", param_type="string", description="Project ID"),
                ],
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
            },
        )

    def _execute(self, action: str, parameters: dict[str, Any]) -> ToolResult:
        if self.project_manager is None:
            return ToolResult(success=False, data=None, error="Project manager not available")
        project_id = parameters.get("project_id")
        if not project_id:
            return ToolResult(success=False, data=None, error="Missing project_id")

        firmware_dir = _hardware_dir(self.project_manager, project_id) / "firmware"
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
                return ToolResult(success=False, data=None, error=f"Unsupported action '{action}'")
            return ToolResult(success=result.get("success", False), data=result, error=result.get("stderr", ""))
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"{type(e).__name__}: {e}")
