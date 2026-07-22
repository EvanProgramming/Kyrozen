"""State management for Kyrozen Phase 7 Hardware Development."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import (
    BOM,
    VALID_HARDWARE_STAGES,
    AssemblyStep,
    BOMItem,
    Component,
    FirmwareProject,
    HardwareArchitecture,
    HardwareDebugRecord,
    WiringDesign,
)


@dataclass
class HardwareSession:
    """Tracks the state of one hardware development conversation."""

    project_id: str
    stage: str = "understanding_inputs"
    architecture: HardwareArchitecture = field(default_factory=HardwareArchitecture)
    components: list[Component] = field(default_factory=list)
    bom: BOM = field(default_factory=BOM)
    wiring: WiringDesign = field(default_factory=WiringDesign)
    firmware: FirmwareProject = field(default_factory=FirmwareProject)
    assembly_steps: list[AssemblyStep] = field(default_factory=list)
    debug_records: list[HardwareDebugRecord] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.stage not in VALID_HARDWARE_STAGES:
            raise ValueError(f"Invalid hardware stage '{self.stage}'")

    def set_stage(self, stage: str) -> None:
        if stage not in VALID_HARDWARE_STAGES:
            raise ValueError(f"Invalid hardware stage '{stage}'")
        self.stage = stage
        self.logs.append(f"Stage: {stage}")

    def update_architecture(self, architecture: HardwareArchitecture) -> None:
        self.architecture = architecture
        self.logs.append("Updated hardware architecture")

    def add_or_update_component(self, component: Component) -> None:
        for i, existing in enumerate(self.components):
            if existing.name == component.name and existing.model == component.model:
                self.components[i] = component
                self.logs.append(f"Updated component: {component.name}")
                return
        self.components.append(component)
        self.logs.append(f"Added component: {component.name}")

    def update_bom(self, bom: BOM) -> None:
        self.bom = bom
        self.logs.append(f"Updated BOM with {len(bom.items)} items")

    def update_bom_item_status(self, name: str, status: str) -> None:
        for item in self.bom.items:
            if item.name == name:
                item.purchase_status = status
                self.logs.append(f"BOM item '{name}' status -> {status}")
                return
        raise ValueError(f"BOM item '{name}' not found")

    def update_wiring(self, wiring: WiringDesign) -> None:
        self.wiring = wiring
        self.logs.append("Updated wiring design")

    def update_firmware(self, firmware: FirmwareProject) -> None:
        self.firmware = firmware
        self.logs.append(f"Updated firmware project ({firmware.platform})")

    def add_or_update_assembly_step(self, step: AssemblyStep) -> None:
        for i, existing in enumerate(self.assembly_steps):
            if existing.order == step.order:
                self.assembly_steps[i] = step
                return
        self.assembly_steps.append(step)
        self.assembly_steps.sort(key=lambda s: s.order)

    def add_debug_record(self, record: HardwareDebugRecord) -> None:
        self.debug_records.append(record)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "stage": self.stage,
            "architecture": self.architecture.to_dict(),
            "components": [c.to_dict() for c in self.components],
            "bom": self.bom.to_dict(),
            "wiring": self.wiring.to_dict(),
            "firmware": self.firmware.to_dict(),
            "assembly_steps": [s.to_dict() for s in self.assembly_steps],
            "debug_records": [r.to_dict() for r in self.debug_records],
            "logs": list(self.logs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwareSession":
        return cls(
            project_id=data.get("project_id", ""),
            stage=data.get("stage", "understanding_inputs"),
            architecture=HardwareArchitecture.from_dict(data.get("architecture") or {}),
            components=[Component.from_dict(c) for c in data.get("components") or []],
            bom=BOM.from_dict(data.get("bom") or {}),
            wiring=WiringDesign.from_dict(data.get("wiring") or {}),
            firmware=FirmwareProject.from_dict(data.get("firmware") or {}),
            assembly_steps=[AssemblyStep.from_dict(s) for s in data.get("assembly_steps") or []],
            debug_records=[HardwareDebugRecord.from_dict(r) for r in data.get("debug_records") or []],
            logs=list(data.get("logs") or []),
        )
