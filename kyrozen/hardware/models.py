"""Data models for Kyrozen Phase 7 Hardware Development."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALID_CONTROLLERS = {
    "arduino",
    "esp32",
    "raspberry_pi",
}

VALID_COMMUNICATIONS = {
    "wifi",
    "ble",
    "uart",
    "i2c",
    "spi",
    "usb",
}

VALID_PURCHASE_STATUSES = {
    "need_purchase",
    "purchased",
    "arrived",
    "already_owned",
    "alternative_needed",
}

VALID_HARDWARE_DECISIONS = {
    "continue_hardware",
    "change_component",
    "narrow_scope",
    "pause",
    "abandon",
}

VALID_FIRMWARE_PLATFORMS = {
    "arduino",
    "esp32",
    "platformio",
}

VALID_FIRMWARE_STATUSES = {
    "pending",
    "success",
    "failed",
}

VALID_HARDWARE_STAGES = {
    "understanding_inputs",
    "architecture_design",
    "component_selection",
    "bom_generation",
    "wiring_design",
    "firmware_development",
    "assembly",
    "testing",
    "debugging",
    "completed",
    "failed",
}

VALID_ASSEMBLY_STATUSES = {
    "pending",
    "done",
    "blocked",
}

VALID_DEBUG_STATUSES = {
    "open",
    "verified",
    "closed",
}


@dataclass
class HardwareArchitecture:
    """High-level hardware architecture for the prototype."""

    controller: str = ""          # e.g. "esp32"
    controller_model: str = ""    # e.g. "ESP32-S3-DevKitC-1"
    sensors: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    communication: list[str] = field(default_factory=list)
    power: str = ""               # e.g. "5V USB / 3.3V regulator"
    storage: str = ""             # e.g. "onboard flash"
    interfaces: list[str] = field(default_factory=list)
    rationale: str = ""
    safety_notes: str = ""

    def __post_init__(self) -> None:
        if self.controller and self.controller not in VALID_CONTROLLERS:
            raise ValueError(f"Invalid controller '{self.controller}'")
        invalid = {c for c in self.communication if c not in VALID_COMMUNICATIONS}
        if invalid:
            raise ValueError(f"Invalid communication protocols: {invalid}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "controller": self.controller,
            "controller_model": self.controller_model,
            "sensors": list(self.sensors),
            "outputs": list(self.outputs),
            "communication": list(self.communication),
            "power": self.power,
            "storage": self.storage,
            "interfaces": list(self.interfaces),
            "rationale": self.rationale,
            "safety_notes": self.safety_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwareArchitecture":
        return cls(
            controller=data.get("controller", ""),
            controller_model=data.get("controller_model", ""),
            sensors=list(data.get("sensors") or []),
            outputs=list(data.get("outputs") or []),
            communication=list(data.get("communication") or []),
            power=data.get("power", ""),
            storage=data.get("storage", ""),
            interfaces=list(data.get("interfaces") or []),
            rationale=data.get("rationale", ""),
            safety_notes=data.get("safety_notes", ""),
        )


@dataclass
class Component:
    """A specific hardware component with technical details."""

    name: str = ""                # e.g. "MPU6050 GY-521 module"
    manufacturer: str = ""
    model: str = ""
    quantity: int = 1
    purpose: str = ""
    voltage: str = ""             # e.g. "3.3V"
    current: str = ""             # e.g. "< 10mA"
    logic_level: str = ""         # e.g. "3.3V / 5V tolerant"
    interface_type: str = ""      # e.g. "I2C"
    compatibility: str = ""
    alternative: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        """Base validation hook for subclasses to chain via super()."""
        pass

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "quantity": self.quantity,
            "purpose": self.purpose,
            "voltage": self.voltage,
            "current": self.current,
            "logic_level": self.logic_level,
            "interface_type": self.interface_type,
            "compatibility": self.compatibility,
            "alternative": self.alternative,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Component":
        return cls(
            name=data.get("name", ""),
            manufacturer=data.get("manufacturer", ""),
            model=data.get("model", ""),
            quantity=int(data.get("quantity", 1) or 1),
            purpose=data.get("purpose", ""),
            voltage=data.get("voltage", ""),
            current=data.get("current", ""),
            logic_level=data.get("logic_level", ""),
            interface_type=data.get("interface_type", ""),
            compatibility=data.get("compatibility", ""),
            alternative=data.get("alternative", ""),
            notes=data.get("notes", ""),
        )


@dataclass
class BOMItem(Component):
    """A component line item in the project BOM with purchase metadata."""

    purchase_status: str = "need_purchase"
    price: str = ""
    currency: str = "USD"
    vendor: str = ""
    link: str = ""
    availability: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.purchase_status and self.purchase_status not in VALID_PURCHASE_STATUSES:
            raise ValueError(f"Invalid purchase_status '{self.purchase_status}'")

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({
            "purchase_status": self.purchase_status,
            "price": self.price,
            "currency": self.currency,
            "vendor": self.vendor,
            "link": self.link,
            "availability": self.availability,
        })
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BOMItem":
        base = Component.from_dict(data)
        return cls(
            **base.to_dict(),
            purchase_status=data.get("purchase_status", "need_purchase"),
            price=data.get("price", ""),
            currency=data.get("currency", "USD"),
            vendor=data.get("vendor", ""),
            link=data.get("link", ""),
            availability=data.get("availability", ""),
        )


@dataclass
class BOM:
    """Bill of Materials for the hardware prototype."""

    items: list[BOMItem] = field(default_factory=list)
    total_estimate: str = ""
    currency: str = "USD"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "total_estimate": self.total_estimate,
            "currency": self.currency,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BOM":
        return cls(
            items=[BOMItem.from_dict(item) for item in data.get("items") or []],
            total_estimate=data.get("total_estimate", ""),
            currency=data.get("currency", "USD"),
            notes=data.get("notes", ""),
        )


@dataclass
class WiringConnection:
    """One wire connection between a device pin and a target."""

    device: str = ""              # e.g. "MPU6050"
    pin: str = ""                 # e.g. "SDA"
    target: str = ""              # e.g. "GPIO21"
    target_type: str = ""         # e.g. "controller", "power", "gnd"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "pin": self.pin,
            "target": self.target,
            "target_type": self.target_type,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WiringConnection":
        return cls(
            device=data.get("device", ""),
            pin=data.get("pin", ""),
            target=data.get("target", ""),
            target_type=data.get("target_type", ""),
            notes=data.get("notes", ""),
        )


@dataclass
class WiringDesign:
    """Wiring plan including pin mapping and textual diagram."""

    connections: list[WiringConnection] = field(default_factory=list)
    pin_mapping: list[dict[str, Any]] = field(default_factory=list)
    diagram_text: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connections": [c.to_dict() for c in self.connections],
            "pin_mapping": list(self.pin_mapping),
            "diagram_text": self.diagram_text,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WiringDesign":
        return cls(
            connections=[WiringConnection.from_dict(c) for c in data.get("connections") or []],
            pin_mapping=list(data.get("pin_mapping") or []),
            diagram_text=data.get("diagram_text", ""),
            warnings=list(data.get("warnings") or []),
        )


@dataclass
class FirmwareProject:
    """Firmware project metadata and build/upload status."""

    platform: str = ""            # "arduino", "esp32", "platformio"
    board: str = ""               # e.g. "esp32-s3-devkitc-1"
    framework: str = ""           # e.g. "arduino"
    libraries: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    build_status: str = "pending"
    build_output: str = ""
    upload_status: str = "pending"
    upload_output: str = ""

    def __post_init__(self) -> None:
        if self.platform and self.platform not in VALID_FIRMWARE_PLATFORMS:
            raise ValueError(f"Invalid firmware platform '{self.platform}'")
        for status_attr in ("build_status", "upload_status"):
            status = getattr(self, status_attr)
            if status and status not in VALID_FIRMWARE_STATUSES:
                raise ValueError(f"Invalid firmware status '{status}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "board": self.board,
            "framework": self.framework,
            "libraries": list(self.libraries),
            "files": list(self.files),
            "build_status": self.build_status,
            "build_output": self.build_output,
            "upload_status": self.upload_status,
            "upload_output": self.upload_output,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FirmwareProject":
        return cls(
            platform=data.get("platform", ""),
            board=data.get("board", ""),
            framework=data.get("framework", ""),
            libraries=list(data.get("libraries") or []),
            files=list(data.get("files") or []),
            build_status=data.get("build_status", "pending"),
            build_output=data.get("build_output", ""),
            upload_status=data.get("upload_status", "pending"),
            upload_output=data.get("upload_output", ""),
        )


@dataclass
class AssemblyStep:
    """One physical assembly step for the user."""

    order: int = 0
    title: str = ""
    instructions: str = ""
    components_involved: list[str] = field(default_factory=list)
    status: str = "pending"
    verification_method: str = ""

    def __post_init__(self) -> None:
        if self.status and self.status not in VALID_ASSEMBLY_STATUSES:
            raise ValueError(f"Invalid assembly status '{self.status}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "title": self.title,
            "instructions": self.instructions,
            "components_involved": list(self.components_involved),
            "status": self.status,
            "verification_method": self.verification_method,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssemblyStep":
        return cls(
            order=int(data.get("order", 0) or 0),
            title=data.get("title", ""),
            instructions=data.get("instructions", ""),
            components_involved=list(data.get("components_involved") or []),
            status=data.get("status", "pending"),
            verification_method=data.get("verification_method", ""),
        )


@dataclass
class HardwareDebugRecord:
    """Evidence-driven hardware debugging record."""

    symptom: str = ""
    hypothesis: str = ""
    test: str = ""
    result: str = ""
    fix: str = ""
    status: str = "open"

    def __post_init__(self) -> None:
        if self.status and self.status not in VALID_DEBUG_STATUSES:
            raise ValueError(f"Invalid debug status '{self.status}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symptom": self.symptom,
            "hypothesis": self.hypothesis,
            "test": self.test,
            "result": self.result,
            "fix": self.fix,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwareDebugRecord":
        return cls(
            symptom=data.get("symptom", ""),
            hypothesis=data.get("hypothesis", ""),
            test=data.get("test", ""),
            result=data.get("result", ""),
            fix=data.get("fix", ""),
            status=data.get("status", "open"),
        )


@dataclass
class HardwareArtifactBundle:
    """Bundle of all Phase 7 artifacts for easy serialization."""

    architecture: HardwareArchitecture = field(default_factory=HardwareArchitecture)
    bom: BOM = field(default_factory=BOM)
    wiring: WiringDesign = field(default_factory=WiringDesign)
    firmware: FirmwareProject = field(default_factory=FirmwareProject)
    assembly_steps: list[AssemblyStep] = field(default_factory=list)
    debug_records: list[HardwareDebugRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "architecture": self.architecture.to_dict(),
            "bom": self.bom.to_dict(),
            "wiring": self.wiring.to_dict(),
            "firmware": self.firmware.to_dict(),
            "assembly_steps": [s.to_dict() for s in self.assembly_steps],
            "debug_records": [r.to_dict() for r in self.debug_records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwareArtifactBundle":
        return cls(
            architecture=HardwareArchitecture.from_dict(data.get("architecture") or {}),
            bom=BOM.from_dict(data.get("bom") or {}),
            wiring=WiringDesign.from_dict(data.get("wiring") or {}),
            firmware=FirmwareProject.from_dict(data.get("firmware") or {}),
            assembly_steps=[AssemblyStep.from_dict(s) for s in data.get("assembly_steps") or []],
            debug_records=[HardwareDebugRecord.from_dict(r) for r in data.get("debug_records") or []],
        )
