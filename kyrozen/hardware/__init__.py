"""Hardware Development module for Kyrozen Phase 7."""

from __future__ import annotations

from .agent import HardwareDevelopmentAgent
from .bridge import HardwareBridge, HardwareBridgeError
from .transport import CONNECTION_LAYERS, FakeSerialTransport, SerialPortTransport, SerialTransport, VersionedMessage, build_connection_model, create_transport, run_fake_protocol_scenarios
from .models import (
    BOM,
    VALID_COMMUNICATIONS,
    VALID_CONTROLLERS,
    VALID_FIRMWARE_PLATFORMS,
    VALID_HARDWARE_DECISIONS,
    VALID_HARDWARE_STAGES,
    VALID_PURCHASE_STATUSES,
    VALID_PROCUREMENT_STATUSES,
    AssemblyStep,
    BOMItem,
    Component,
    FirmwareProject,
    HardwareArchitecture,
    HardwareArtifactBundle,
    HardwareDebugRecord,
    WiringConnection,
    WiringDesign,
)
from .state import HardwareSession

__all__ = [
    "AssemblyStep",
    "BOM",
    "BOMItem",
    "Component",
    "FirmwareProject",
    "HardwareArchitecture",
    "HardwareArtifactBundle",
    "HardwareBridge",
    "HardwareBridgeError",
    "HardwareDebugRecord",
    "HardwareDevelopmentAgent",
    "FakeSerialTransport",
    "CONNECTION_LAYERS",
    "SerialPortTransport",
    "SerialTransport",
    "create_transport",
    "build_connection_model",
    "VersionedMessage",
    "run_fake_protocol_scenarios",
    "HardwareSession",
    "VALID_COMMUNICATIONS",
    "VALID_CONTROLLERS",
    "VALID_FIRMWARE_PLATFORMS",
    "VALID_HARDWARE_DECISIONS",
    "VALID_HARDWARE_STAGES",
    "VALID_PURCHASE_STATUSES",
    "VALID_PROCUREMENT_STATUSES",
    "WiringConnection",
    "WiringDesign",
]
