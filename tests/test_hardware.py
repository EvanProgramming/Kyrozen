"""Tests for Kyrozen Phase 7 Hardware Development."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.config import KyrozenConfig
from kyrozen.hardware.bridge import HardwareBridge, HardwareBridgeError, classify_upload_error
from kyrozen.hardware.transport import CONNECTION_LAYERS, FakeSerialTransport, SerialPortTransport, VersionedMessage, build_connection_model, create_transport, run_fake_protocol_scenarios
from kyrozen.hardware.models import (
    BOM,
    VALID_COMMUNICATIONS,
    VALID_CONTROLLERS,
    VALID_FIRMWARE_PLATFORMS,
    VALID_HARDWARE_DECISIONS,
    VALID_HARDWARE_STAGES,
    VALID_PURCHASE_STATUSES,
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
from kyrozen.hardware.state import HardwareSession
from kyrozen.tools.hardware_tools import (
    HardwareBridgeTool,
    RecordHardwareDecisionTool,
    SaveAssemblyStepTool,
    SaveBOMTool,
    SaveComponentTool,
    SaveDebugRecordTool,
    SaveFirmwareProjectTool,
    SaveHardwareArchitectureTool,
    SaveWiringDesignTool,
    UpdatePurchaseStatusTool,
)

from tests.conftest import MockModel, make_authenticated_app


@pytest.fixture
def architecture_data() -> dict[str, Any]:
    return {
        "controller": "arduino",
        "controller_model": "Arduino Uno R3",
        "sensors": ["ambient light sensor"],
        "outputs": ["LED"],
        "communication": ["usb"],
        "power": "5V USB",
        "storage": "onboard flash",
        "interfaces": ["USB Type-B"],
        "rationale": "Simple controller for LED automation",
        "safety_notes": "Low voltage only",
    }


@pytest.fixture
def component_data() -> dict[str, Any]:
    return {
        "name": "ESP32-S3-DevKitC-1",
        "manufacturer": "Espressif",
        "model": "ESP32-S3-DevKitC-1-N8R8",
        "quantity": 1,
        "purpose": "Main controller with Wi-Fi and BLE",
        "voltage": "3.3V",
        "current": "< 500mA",
        "logic_level": "3.3V",
        "interface_type": "UART / I2C / SPI / WiFi / BLE",
        "compatibility": "Arduino IDE, PlatformIO",
        "alternative": "ESP32-DevKitC-32E",
    }


@pytest.fixture
def bom_item_data(component_data: dict[str, Any]) -> dict[str, Any]:
    return {
        **component_data,
        "purchase_status": "need_purchase",
        "price": "12.99",
        "currency": "USD",
        "vendor": "DigiKey",
        "link": "https://www.digikey.com/example",
        "availability": "in_stock",
    }


@pytest.fixture
def bom_data(bom_item_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "items": [bom_item_data],
        "total_estimate": "~$25",
        "currency": "USD",
        "notes": "BOM for LED controller",
    }


@pytest.fixture
def wiring_data() -> dict[str, Any]:
    return {
        "connections": [
            {
                "device": "MPU6050",
                "pin": "SDA",
                "target": "GPIO21",
                "target_type": "controller",
                "notes": "I2C data",
            },
            {
                "device": "MPU6050",
                "pin": "SCL",
                "target": "GPIO22",
                "target_type": "controller",
                "notes": "I2C clock",
            },
        ],
        "pin_mapping": [
            {"device": "MPU6050", "SDA": "GPIO21", "SCL": "GPIO22", "VCC": "3.3V", "GND": "GND"}
        ],
        "diagram_text": "ESP32-S3 <--I2C--> MPU6050",
        "warnings": ["Use 3.3V for MPU6050", "Do not connect to 5V"],
    }


@pytest.fixture
def firmware_data() -> dict[str, Any]:
    return {
        "platform": "arduino",
        "board": "arduino:avr:uno",
        "framework": "arduino",
        "libraries": ["FastLED"],
        "files": ["src/main.ino"],
        "build_status": "pending",
        "upload_status": "pending",
    }


@pytest.fixture
def assembly_step_data() -> dict[str, Any]:
    return {
        "order": 1,
        "title": "Connect power",
        "instructions": "Connect the ESP32 to your computer via USB.",
        "components_involved": ["ESP32-S3-DevKitC-1"],
        "status": "pending",
        "verification_method": "Power LED turns on",
    }


@pytest.fixture
def debug_record_data() -> dict[str, Any]:
    return {
        "symptom": "LED does not blink",
        "hypothesis": "Wrong GPIO pin in firmware",
        "test": "Check wiring and pin number",
        "result": "GPIO pin mismatch confirmed",
        "fix": "Update GPIO number in code",
        "status": "closed",
    }


# ---------------------------------------------------------------------------
# Model serialization and validation
# ---------------------------------------------------------------------------


def test_hardware_architecture_validation(architecture_data: dict[str, Any]):
    arch = HardwareArchitecture.from_dict(architecture_data)
    assert arch.controller == "arduino"
    assert arch.controller_model == "Arduino Uno R3"
    assert arch.outputs == ["LED"]
    data = arch.to_dict()
    assert data["controller"] == "arduino"
    restored = HardwareArchitecture.from_dict(data)
    assert restored.controller_model == "Arduino Uno R3"

    with pytest.raises(ValueError):
        HardwareArchitecture(controller="stm32")
    with pytest.raises(ValueError):
        HardwareArchitecture(communication=["ethernet"])


def test_hardware_architecture_empty_is_valid():
    arch = HardwareArchitecture()
    assert arch.controller == ""
    assert arch.communication == []
    assert HardwareArchitecture.from_dict(arch.to_dict()).controller == ""


def test_valid_controllers_and_communications():
    assert "arduino" in VALID_CONTROLLERS
    assert "esp32" in VALID_CONTROLLERS
    assert "raspberry_pi" in VALID_CONTROLLERS
    assert "i2c" in VALID_COMMUNICATIONS
    assert "wifi" in VALID_COMMUNICATIONS
    assert "ble" in VALID_COMMUNICATIONS


def test_component_serialization(component_data: dict[str, Any]):
    comp = Component.from_dict(component_data)
    assert comp.name == "ESP32-S3-DevKitC-1"
    assert comp.manufacturer == "Espressif"
    assert comp.quantity == 1
    data = comp.to_dict()
    assert Component.from_dict(data).model == "ESP32-S3-DevKitC-1-N8R8"


def test_bom_item_validation(bom_item_data: dict[str, Any]):
    item = BOMItem.from_dict(bom_item_data)
    assert item.purchase_status == "need_purchase"
    assert item.vendor == "DigiKey"
    assert item.price == "12.99"

    with pytest.raises(ValueError):
        BOMItem.from_dict({**bom_item_data, "purchase_status": "ordered"})

    assert item.purchase_status in VALID_PURCHASE_STATUSES


def test_bom_serialization(bom_data: dict[str, Any]):
    bom = BOM.from_dict(bom_data)
    assert len(bom.items) == 1
    assert bom.items[0].name == "ESP32-S3-DevKitC-1"
    assert bom.total_estimate == "~$25"
    data = bom.to_dict()
    assert BOM.from_dict(data).items[0].vendor == "DigiKey"


def test_bom_calculates_line_and_total_price():
    bom = BOM(items=[BOMItem(name="ESP32", quantity=2, price="4.5")])
    assert bom.items[0].total_price == "9"
    assert bom.total_estimate == "9"


def test_wiring_design_serialization(wiring_data: dict[str, Any]):
    wiring = WiringDesign.from_dict(wiring_data)
    assert len(wiring.connections) == 2
    assert wiring.connections[0].target == "GPIO21"
    assert "Do not connect to 5V" in wiring.warnings
    data = wiring.to_dict()
    assert WiringDesign.from_dict(data).connections[1].pin == "SCL"


def test_firmware_project_validation(firmware_data: dict[str, Any]):
    fw = FirmwareProject.from_dict(firmware_data)
    assert fw.platform == "arduino"
    assert fw.build_status == "pending"
    data = fw.to_dict()
    assert FirmwareProject.from_dict(data).libraries == ["FastLED"]

    with pytest.raises(ValueError):
        FirmwareProject(platform="mbed")
    with pytest.raises(ValueError):
        FirmwareProject(build_status="unknown")

    assert "arduino" in VALID_FIRMWARE_PLATFORMS


def test_assembly_step_validation(assembly_step_data: dict[str, Any]):
    step = AssemblyStep.from_dict(assembly_step_data)
    assert step.order == 1
    assert step.status == "pending"
    data = step.to_dict()
    assert AssemblyStep.from_dict(data).title == "Connect power"

    with pytest.raises(ValueError):
        AssemblyStep(status="in_progress")


def test_debug_record_validation(debug_record_data: dict[str, Any]):
    record = HardwareDebugRecord.from_dict(debug_record_data)
    assert record.symptom == "LED does not blink"
    assert record.status == "closed"
    data = record.to_dict()
    assert HardwareDebugRecord.from_dict(data).fix == "Update GPIO number in code"

    with pytest.raises(ValueError):
        HardwareDebugRecord(status="resolved")


def test_hardware_artifact_bundle_roundtrip(
    architecture_data: dict[str, Any],
    bom_data: dict[str, Any],
    wiring_data: dict[str, Any],
    firmware_data: dict[str, Any],
):
    bundle = HardwareArtifactBundle(
        architecture=HardwareArchitecture.from_dict(architecture_data),
        bom=BOM.from_dict(bom_data),
        wiring=WiringDesign.from_dict(wiring_data),
        firmware=FirmwareProject.from_dict(firmware_data),
    )
    data = bundle.to_dict()
    restored = HardwareArtifactBundle.from_dict(data)
    assert restored.architecture.controller == "arduino"
    assert len(restored.bom.items) == 1
    assert restored.firmware.platform == "arduino"


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def test_hardware_session_stage_transitions():
    session = HardwareSession(project_id="proj_123")
    assert session.stage == "understanding_inputs"
    assert "understanding_inputs" in VALID_HARDWARE_STAGES

    session.set_stage("architecture_design")
    assert session.stage == "architecture_design"
    assert "Stage: architecture_design" in session.logs

    with pytest.raises(ValueError):
        session.set_stage("production")
    with pytest.raises(ValueError):
        HardwareSession(project_id="proj_123", stage="invalid")


def test_hardware_session_component_and_bom(component_data: dict[str, Any], bom_data: dict[str, Any]):
    session = HardwareSession(project_id="proj_123")
    comp = Component.from_dict(component_data)
    session.add_or_update_component(comp)
    assert len(session.components) == 1

    # Duplicate updates in place
    comp2 = Component.from_dict({**component_data, "quantity": 2})
    session.add_or_update_component(comp2)
    assert len(session.components) == 1
    assert session.components[0].quantity == 2

    session.update_bom(BOM.from_dict(bom_data))
    assert len(session.bom.items) == 1
    session.update_bom_item_status("ESP32-S3-DevKitC-1", "purchased")
    assert session.bom.items[0].purchase_status == "purchased"

    with pytest.raises(ValueError):
        session.update_bom_item_status("Missing", "arrived")


def test_hardware_session_serialization_roundtrip(
    architecture_data: dict[str, Any],
    bom_data: dict[str, Any],
    wiring_data: dict[str, Any],
    firmware_data: dict[str, Any],
):
    session = HardwareSession(project_id="proj_123")
    session.update_architecture(HardwareArchitecture.from_dict(architecture_data))
    session.update_bom(BOM.from_dict(bom_data))
    session.update_wiring(WiringDesign.from_dict(wiring_data))
    session.update_firmware(FirmwareProject.from_dict(firmware_data))

    data = session.to_dict()
    restored = HardwareSession.from_dict(data)
    assert restored.project_id == "proj_123"
    assert restored.architecture.controller == "arduino"
    assert restored.bom.items[0].name == "ESP32-S3-DevKitC-1"


# ---------------------------------------------------------------------------
# Local Hardware Bridge
# ---------------------------------------------------------------------------


def test_bridge_validates_command_whitelist():
    bridge = HardwareBridge()

    # Allowed command validation passes
    bridge._validate_args(["arduino-cli", "compile", "--fqbn", "x:y:z", "."])
    bridge._validate_args(["pio", "run"])
    bridge._validate_args(["pio", "device", "list"])
    bridge._validate_args(["arduino-cli", "version"])
    bridge._validate_args(["arduino-cli", "core", "list"])
    bridge._validate_args(["pio", "--version"])

    with pytest.raises(HardwareBridgeError):
        bridge._validate_args([])
    with pytest.raises(HardwareBridgeError):
        bridge._validate_args(["rm", "-rf", "/"])
    with pytest.raises(HardwareBridgeError):
        bridge._validate_args(["arduino-cli", "core", "install", "x"])
    with pytest.raises(HardwareBridgeError):
        bridge._validate_args(["pio", "project", "init"])
    with pytest.raises(HardwareBridgeError):
        bridge._validate_args(["arduino-cli", "compile", ";", "rm", "/"])


def test_bridge_list_ports_without_tools():
    bridge = HardwareBridge()
    with patch("kyrozen.hardware.bridge.shutil.which", return_value=None):
        result = bridge.list_ports()
    assert result["success"] is False
    assert "No supported hardware tool found" in result["stderr"]
    assert result["status"] == "BLOCKED"
    assert result["board_detected"] is False
    assert result["toolchain"]["arduino_cli"]["installed"] is False


def test_bridge_list_ports_uses_bundled_tool_path_when_not_on_path(tmp_path, monkeypatch):
    bridge = HardwareBridge(tmp_path)
    bundled_cli = tmp_path / "arduino-cli"
    bundled_cli.write_text("bundled cli", encoding="utf-8")
    monkeypatch.setenv("KYROZEN_ARDUINO_CLI_PATH", str(bundled_cli))
    monkeypatch.setattr(shutil, "which", lambda _command: None)

    def fake_run(args, timeout=120):
        if args[1:] == ["version"]:
            return {"success": True, "stdout": "arduino-cli 1.0.4", "stderr": ""}
        if args[1:] == ["core", "list"]:
            return {"success": True, "stdout": "esp32:esp32 3.3.10", "stderr": ""}
        return {
            "success": True,
            "stdout": "/dev/cu.usbserial-10 serial Serial Port Unknown\\n",
            "stderr": "",
        }

    monkeypatch.setattr(bridge, "run", fake_run)
    result = bridge.list_ports()

    assert result["toolchain"]["arduino_cli"]["installed"] is True
    assert result["success"] is True
    assert result["status"] == "BLOCKED"
    assert result["block_reason"] == "board_not_connected"


def test_bridge_list_ports_does_not_claim_unknown_serial_ports_are_a_board():
    bridge = HardwareBridge()
    output = "Port Protocol Type Board Name FQBN Core\n/dev/cu.debug serial Serial Port Unknown\n"
    with patch("kyrozen.hardware.bridge.shutil.which", side_effect=lambda command: "/usr/bin/arduino-cli" if command == "arduino-cli" else None), patch.object(
        bridge, "run", return_value={"success": True, "returncode": 0, "stdout": output, "stderr": ""}
    ):
        result = bridge.list_ports()
    assert result["board_detected"] is False
    assert result["status"] == "BLOCKED"
    assert result["block_reason"] == "board_not_connected"


def test_bridge_list_ports_accepts_user_confirmed_board_on_usb_uart(tmp_path, monkeypatch):
    bridge = HardwareBridge(tmp_path)

    monkeypatch.setattr(shutil, "which", lambda command: "/usr/bin/arduino-cli" if command == "arduino-cli" else None)

    def fake_run(args, timeout=120):
        if args[1:] == ["version"]:
            return {"success": True, "stdout": "arduino-cli 1.5.1", "stderr": ""}
        if args[1:] == ["core", "list"]:
            return {"success": True, "stdout": "esp32:esp32 3.3.10", "stderr": ""}
        return {
            "success": True,
            "stdout": "/dev/cu.usbserial-10 serial Serial Port (USB) Unknown\n",
            "stderr": "",
        }

    monkeypatch.setattr(bridge, "run", fake_run)
    result = bridge.list_ports(
        board="esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi",
        port="/dev/cu.usbserial-10",
    )

    assert result["board_detected"] is True
    assert result["board_identification"] == "user_confirmed"
    assert result["status"] == "PASSED"


def test_bridge_list_ports_recognizes_an_arduino_cli_fqbn():
    bridge = HardwareBridge()
    output = "Port Protocol Type Board Name FQBN Core\n/dev/cu.usb serial Serial Port ESP32 Dev Module esp32:esp32:esp32 esp32\n"
    with patch("kyrozen.hardware.bridge.shutil.which", side_effect=lambda command: "/usr/bin/arduino-cli" if command == "arduino-cli" else None), patch.object(
        bridge, "run", return_value={"success": True, "returncode": 0, "stdout": output, "stderr": ""}
    ):
        result = bridge.list_ports()
    assert result["board_detected"] is True
    assert result["status"] not in {"BLOCKED"}


def test_bridge_compile_requires_board():
    bridge = HardwareBridge()
    result = bridge.compile()
    assert result["success"] is False
    assert "Board FQBN is required" in result["stderr"]


def test_bridge_enables_usb_cdc_for_esp32s3_probe(monkeypatch):
    bridge = HardwareBridge()
    calls: list[list[str]] = []

    def fake_run(args, timeout=120):
        calls.append(args)
        return {"success": True, "returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(bridge, "run", fake_run)
    bridge.compile(board="esp32:esp32:esp32s3")
    bridge.upload(board="esp32:esp32:esp32s3", port="/dev/cu.usbmodem101")

    assert calls == [
        [
            "arduino-cli",
            "compile",
            "--fqbn",
            "esp32:esp32:esp32s3",
            "--board-options",
            "USBMode=hwcdc,CDCOnBoot=cdc",
            ".",
        ],
        [
            "arduino-cli",
            "upload",
            "--fqbn",
            "esp32:esp32:esp32s3",
            "--board-options",
            "USBMode=hwcdc,CDCOnBoot=cdc",
            "--port",
            "/dev/cu.usbmodem101",
            ".",
        ],
    ]


def test_bridge_prepares_gpio_free_serial_probe(tmp_path):
    result = HardwareBridge(tmp_path).prepare_serial_probe()
    probe = tmp_path / "kyrozen_serial_probe.ino"
    assert result["success"] is True
    assert result["status"] == "PASSED"
    assert probe.exists()
    source = probe.read_text(encoding="utf-8")
    assert "KYROZEN_SERIAL_PROBE heartbeat" in source
    assert "pinMode" not in source


def test_bridge_upload_requires_board():
    bridge = HardwareBridge()
    result = bridge.upload()
    assert result["success"] is False
    assert "Board FQBN is required" in result["stderr"]


def test_api_rejects_unverified_physical_acceptance_artifact(api_client: TestClient):
    project = api_client.post("/api/projects", json={"name": "Physical gate"}).json()
    response = api_client.post(f"/api/projects/{project['id']}/artifacts", json={
        "type": "hardware_acceptance",
        "title": "ESP32 Physical Acceptance",
        "content": json.dumps({"observed_behavior": "LED looked correct"}),
    })
    assert response.status_code == 422
    assert "BLOCKED" in response.json()["detail"]["message"]


def test_api_accepts_only_complete_physical_evidence_summary(api_client: TestClient):
    project = api_client.post("/api/projects", json={"name": "Physical evidence"}).json()
    runs = [
        {"action": "list_ports", "status": "PASSED", "success": True, "board_detected": True},
        {"action": "list_ports", "status": "PASSED", "success": True, "board_detected": True},
        {"action": "compile", "status": "PASSED", "success": True},
        {"action": "upload", "status": "PASSED", "success": True},
        {"action": "monitor", "status": "PASSED", "success": True},
    ]
    response = api_client.post(f"/api/projects/{project['id']}/artifacts", json={
        "type": "hardware_acceptance", "title": "ESP32 Physical Acceptance",
        "content": json.dumps({
            "observed_behavior": "串口输出 telemetry，拔插后恢复",
            "confirmed_by_user": True, "confirmation_answer": "confirmed_behavior_and_reconnect", "confirmed_at": "2026-08-03T00:00:00Z",
            "physical_evidence_required": True, "hardware_run_timestamps": ["t1", "t2"],
            "hardware_runs": runs,
        }),
    })
    assert response.status_code == 200, response.text


def test_api_rejects_non_affirmative_physical_question_answer(api_client: TestClient):
    project = api_client.post("/api/projects", json={"name": "Physical answer gate"}).json()
    runs = [
        {"action": "list_ports", "status": "PASSED", "success": True, "board_detected": True},
        {"action": "list_ports", "status": "PASSED", "success": True, "board_detected": True},
        {"action": "compile", "status": "PASSED", "success": True},
        {"action": "upload", "status": "PASSED", "success": True},
        {"action": "monitor", "status": "PASSED", "success": True},
    ]
    response = api_client.post(f"/api/projects/{project['id']}/artifacts", json={
        "type": "hardware_acceptance", "title": "ESP32 Physical Acceptance",
        "content": json.dumps({
            "observed_behavior": "串口输出异常，未确认拔插恢复",
            "confirmed_by_user": True, "confirmation_answer": "yes", "confirmed_at": "2026-08-03T00:00:00Z",
            "physical_evidence_required": True, "hardware_run_timestamps": ["t1", "t2"],
            "hardware_runs": runs,
        }),
    })
    assert response.status_code == 422
    assert "Ask question 的明确肯定回答（符合，拔插后已恢复）" in response.json()["detail"]["missing"]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def test_save_hardware_architecture_tool(project_manager, architecture_data: dict[str, Any]):
    tool = SaveHardwareArchitectureTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "architecture": architecture_data})
    assert result.success, result.error
    assert "artifact_id" in result.data
    assert result.data["version"] == 1

    result2 = tool.execute("save", {"project_id": project.id, "architecture": architecture_data})
    assert result2.success
    assert result2.data["version"] == 2


def test_save_component_tool(project_manager, component_data: dict[str, Any]):
    tool = SaveComponentTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "component": component_data})
    assert result.success, result.error
    assert result.data["version"] == 1


def test_save_bom_tool(project_manager, bom_data: dict[str, Any]):
    tool = SaveBOMTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "bom": bom_data})
    assert result.success, result.error
    assert result.data["version"] == 1


def test_update_purchase_status_tool(project_manager, bom_data: dict[str, Any]):
    project = project_manager.create(name="Test", goal="G")
    SaveBOMTool(project_manager).execute("save", {"project_id": project.id, "bom": bom_data})

    tool = UpdatePurchaseStatusTool(project_manager)
    result = tool.execute(
        "update",
        {
            "project_id": project.id,
            "component_name": "ESP32-S3-DevKitC-1",
            "status": "already_owned",
        },
    )
    assert result.success, result.error
    assert result.data["version"] == 2

    result_missing = tool.execute(
        "update",
        {"project_id": project.id, "component_name": "Missing", "status": "purchased"},
    )
    assert not result_missing.success


def test_save_wiring_design_tool(project_manager, wiring_data: dict[str, Any]):
    tool = SaveWiringDesignTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "wiring": wiring_data})
    assert result.success, result.error


def test_save_firmware_project_tool(project_manager, firmware_data: dict[str, Any]):
    tool = SaveFirmwareProjectTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "firmware": firmware_data})
    assert result.success, result.error


def test_record_hardware_decision_tool(project_manager):
    tool = RecordHardwareDecisionTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute(
        "record",
        {
            "project_id": project.id,
            "decision": "continue_hardware",
            "reason": "Components are available",
            "alternatives": ["pause"],
            "rejected_reasons": {"pause": "User wants to proceed"},
        },
    )
    assert result.success, result.error
    assert "continue_hardware" in result.data["decision"]

    result_invalid = tool.execute(
        "record",
        {"project_id": project.id, "decision": "invalid", "reason": "x"},
    )
    assert not result_invalid.success

    assert "continue_hardware" in VALID_HARDWARE_DECISIONS
    assert "abandon" in VALID_HARDWARE_DECISIONS


def test_save_assembly_step_tool(project_manager, assembly_step_data: dict[str, Any]):
    tool = SaveAssemblyStepTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "step": assembly_step_data})
    assert result.success, result.error


def test_save_debug_record_tool(project_manager, debug_record_data: dict[str, Any]):
    tool = SaveDebugRecordTool(project_manager)
    project = project_manager.create(name="Test", goal="G")
    result = tool.execute("save", {"project_id": project.id, "record": debug_record_data})
    assert result.success, result.error


def test_hardware_bridge_tool_requires_project():
    tool = HardwareBridgeTool(project_manager=None)
    result = tool.execute("list_ports", {"project_id": "x"})
    assert not result.success
    assert "Project manager not available" in result.error


def test_hardware_bridge_tool_forwards_board_and_port_for_discovery(project_manager):
    project = project_manager.create(name="Test", goal="G")
    tool = HardwareBridgeTool(project_manager)
    with patch.object(
        HardwareBridge,
        "list_ports",
        return_value={"success": True, "status": "PASSED", "board_detected": True},
    ) as list_ports:
        result = tool.execute(
            "list_ports",
            {
                "project_id": project.id,
                "board": "esp32:esp32:esp32",
                "port": "/dev/cu.usbserial-10",
            },
        )

    assert result.success, result.error
    list_ports.assert_called_once_with(
        board="esp32:esp32:esp32",
        port="/dev/cu.usbserial-10",
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


def test_hardware_agent_prompt_forbids_manufacturing():
    from kyrozen.hardware.agent import HardwareDevelopmentAgent

    config = KyrozenConfig(provider="mock", api_key="test", permission_mode="permissive")
    agent = HardwareDevelopmentAgent(config=config, model=MockModel(), project_manager=None)
    prompt = agent._build_system_prompt()
    assert "Hardware Development Agent" in prompt
    assert "Do NOT design PCB" in prompt
    assert "Do NOT design or recommend high-voltage" in prompt
    assert "save_hardware_architecture" in prompt
    assert "save_bom" in prompt
    assert "hardware_bridge" in prompt


def test_fake_serial_transport_supports_reconnect_and_duplicate_messages():
    transport = FakeSerialTransport()
    message = VersionedMessage(protocol_version="1.0", message_type="set_led", fields={"value": 1})
    with pytest.raises(ConnectionError):
        transport.send(message)
    transport.connect("/dev/cu.test")
    transport.duplicate_next = True
    transport.send(message)
    first = transport.receive()
    second = transport.receive()
    assert first is not None and first.correlation_id == message.correlation_id
    assert second is not None and second.correlation_id == message.correlation_id
    transport.disconnect()
    with pytest.raises(ConnectionError):
        transport.receive()


def test_fake_serial_transport_reports_incompatible_protocol():
    transport = FakeSerialTransport(protocol_version="2.0")
    transport.connect("/dev/cu.fake")
    transport.send(VersionedMessage(protocol_version="1.0", message_type="telemetry"))
    response = transport.receive()
    assert response is not None
    assert response.error_code == "protocol_version_incompatible"
    assert response.message_type == "error"


def test_real_serial_transport_uses_injected_device_and_round_trips_messages():
    class Device:
        is_open = True
        timeout = 0

        def __init__(self):
            self.writes = []
            self.reads = [VersionedMessage(protocol_version="1.0", message_type="telemetry").encode_line()]
            self.closed = False

        def write(self, payload):
            self.writes.append(payload)

        def readline(self):
            return self.reads.pop(0) if self.reads else b""

        def close(self):
            self.closed = True
            self.is_open = False

    device = Device()
    transport = SerialPortTransport(lambda port, baud, timeout: device)
    transport.connect("/dev/cu.fake", 115200)
    message = VersionedMessage(protocol_version="1.0", message_type="set_led", fields={"value": 1})
    transport.send(message)
    received = transport.receive()
    assert received is not None and received.message_type == "telemetry"
    assert device.writes == [message.encode_line()]
    transport.disconnect()
    assert not transport.connected


def test_real_serial_transport_turns_malformed_lines_into_explicit_errors():
    class Device:
        is_open = True
        timeout = 0
        def write(self, payload):
            pass
        def readline(self):
            return b"not-json\n"
        def close(self):
            self.is_open = False

    transport = SerialPortTransport(lambda port, baud, timeout: Device())
    transport.connect("/dev/cu.fake")
    response = transport.receive()
    assert response is not None
    assert response.message_type == "error"
    assert response.error_code == "invalid_message"


def test_transport_factory_switches_between_fake_and_real():
    assert isinstance(create_transport("fake"), FakeSerialTransport)
    assert isinstance(create_transport("serial"), SerialPortTransport)
    with pytest.raises(ValueError):
        create_transport("ble")


def test_hardware_bridge_protocol_exchange_can_run_with_fake_transport(project_manager):
    from kyrozen.tools.hardware_tools import HardwareBridgeTool

    project = project_manager.create(name="Protocol", goal="G")
    result = HardwareBridgeTool(project_manager).execute("protocol_exchange", {
        "project_id": project.id,
        "transport": "fake",
        "message": {"protocol_version": "1.0", "message_type": "telemetry", "fields": {"value": 1}},
    })
    assert result.success, result.error
    assert result.data["response"]["message_type"] == "ack:telemetry"
    assert result.data["response"]["correlation_id"] == result.data["request"]["correlation_id"]


def test_fake_protocol_scenarios_cover_all_phase2_cases():
    result = run_fake_protocol_scenarios()
    assert result["status"] == "PASSED"
    assert [item["scenario"] for item in result["scenarios"]] == [
        "normal", "offline", "reconnect", "duplicate", "error", "version_incompatible",
    ]
    assert all(item["status"] == "PASSED" for item in result["scenarios"])


def test_six_layer_connection_model_preserves_protocol_impact_without_device_assumptions():
    model = build_connection_model(
        {"protocol_version": "1.0", "message_type": "telemetry", "fields": {"value": "number"}},
        affected_files=["firmware/protocol.json"], affected_tasks=["更新字段映射"],
    )
    assert [layer["name"] for layer in model["layers"]] == list(CONNECTION_LAYERS)
    assert model["protocol_version"] == "1.0"
    assert model["affected_files"] == ["firmware/protocol.json"]
    assert "ble_uuid" not in model


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("serial port not found", "not_connected"),
        ("resource temporarily unavailable", "port_occupied"),
        ("permission denied opening port", "permission_denied"),
        ("upload speed 921600 is too high", "upload_speed_too_high"),
        ("Timed out waiting for packet header", "board_error"),
        ("brownout detector was triggered", "power_failure"),
    ],
)
def test_upload_failures_have_distinct_recovery_categories(stderr: str, expected: str):
    assert classify_upload_error(stderr) == expected


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(temp_dir: str):
    config = KyrozenConfig(
        provider="mock",
        api_key="test-key",
        permission_mode="permissive",
        workspace_root=temp_dir,
        log_level="ERROR",
        task_store_path=os.path.join(temp_dir, "tasks.json"),
    )
    app = make_authenticated_app(config, MockModel(["Done"]))
    with TestClient(app) as client:
        yield client


def test_hardware_chat_mode(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Hardware Project", "goal": "G"})
    pid = create.json()["id"]

    chat_res = api_client.post("/api/chat", json={
        "message": "开始硬件开发",
        "project_id": pid,
        "mode": "hardware",
    })
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert data["project_id"] == pid
    assert data["mode"] == "hardware"
    assert data["task_id"].startswith("task_")


def test_hardware_state_endpoint(api_client: TestClient, architecture_data: dict[str, Any], bom_data: dict[str, Any]):
    create = api_client.post("/api/projects", json={"name": "Hardware Project 2", "goal": "G"})
    pid = create.json()["id"]

    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "hardware_architecture",
        "title": "Hardware Architecture",
        "content": json.dumps(architecture_data),
        "change_reason": "Seed",
    })
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "bom",
        "title": "Bill of Materials",
        "content": json.dumps(bom_data),
        "change_reason": "Seed",
    })

    res = api_client.get(f"/api/projects/{pid}/hardware/state")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == pid
    assert data["architecture"]["controller"] == "arduino"
    assert data["bom"]["items"][0]["name"] == "ESP32-S3-DevKitC-1"


def test_hardware_state_requires_project(api_client: TestClient):
    res = api_client.get("/api/projects/proj_missing/hardware/state")
    assert res.status_code == 404


def test_hardware_state_ignores_malformed_legacy_artifact(api_client: TestClient):
    create = api_client.post("/api/projects", json={"name": "Legacy Hardware", "goal": "G"})
    pid = create.json()["id"]
    api_client.post(f"/api/projects/{pid}/artifacts", json={
        "type": "firmware_project",
        "title": "Firmware Project",
        "content": "[]",
        "change_reason": "Legacy malformed fixture",
    })

    res = api_client.get(f"/api/projects/{pid}/hardware/state")

    assert res.status_code == 200
    assert res.json()["firmware"]["build_status"] == "pending"


def test_hybrid_protocol_change_generates_impact_tasks_and_test(api_client: TestClient):
    project = api_client.post("/api/projects", json={"name": "协议影响", "project_type": "hybrid"}).json()
    pid = project["id"]
    confirmed = api_client.post(f"/api/projects/{pid}/workflow-confirm", json={"project_type": "hybrid"})
    assert confirmed.status_code == 200, confirmed.text
    protocol = {"protocol_version": "1.0", "message_type": "telemetry", "fields": {"value": "number"}}
    first = api_client.post(f"/api/projects/{pid}/protocol/confirm", json={"protocol": protocol, "confirmed": True})
    assert first.status_code == 200, first.text
    assert first.json()["generated_task_ids"]
    assert first.json()["impact_artifact_id"]

    changed = {**protocol, "protocol_version": "1.1", "fields": {"value": "number", "unit": "string"}}
    second = api_client.post(
        f"/api/projects/{pid}/protocol/confirm",
        json={
            "protocol": changed,
            "confirmed": True,
            "affected_files": ["firmware/src/protocol.cpp", "app/src/protocol.ts"],
            "affected_tasks": ["更新协议字段映射"],
            "expected_version": first.json()["version"],
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["protocol_changed"] is True
    assert len(second.json()["generated_task_ids"]) == 4
    artifacts = api_client.get(f"/api/projects/{pid}/artifacts").json()
    assert any(item["type"] == "protocol_impact" for item in artifacts)
    assert any(item["type"] == "protocol_connection_model" for item in artifacts)


def test_protocol_scenarios_are_server_generated_and_persisted(api_client: TestClient):
    project = api_client.post("/api/projects", json={"name": "服务端协议模拟", "project_type": "hybrid"}).json()
    pid = project["id"]
    result = api_client.post(f"/api/projects/{pid}/protocol/scenarios")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "PASSED"
    assert result.json()["artifact_id"]
    artifacts = api_client.get(f"/api/projects/{pid}/artifacts").json()
    scenario = next(item for item in artifacts if item["type"] == "protocol_scenarios")
    assert "duplicate" in scenario["content"]


# ---------------------------------------------------------------------------
# Requirement test cases: Arduino, ESP32, Hybrid
# ---------------------------------------------------------------------------


def test_case_1_arduino_led_automation(project_manager):
    """Simple Arduino LED controller: verify controller choice, BOM, wiring, firmware."""
    tool = SaveHardwareArchitectureTool(project_manager)
    project = project_manager.create(name="LED Automation", goal="Auto LED")

    arch = {
        "controller": "arduino",
        "controller_model": "Arduino Uno R3",
        "sensors": ["photoresistor module"],
        "outputs": ["5mm red LED", "220 ohm resistor"],
        "communication": ["usb"],
        "power": "5V USB from computer",
        "storage": "onboard flash",
        "interfaces": ["USB Type-B"],
        "rationale": "Arduino is beginner-friendly and sufficient for simple LED control",
    }
    result = tool.execute("save", {"project_id": project.id, "architecture": arch})
    assert result.success

    bom_tool = SaveBOMTool(project_manager)
    bom = {
        "items": [
            {
                "name": "Arduino Uno R3",
                "manufacturer": "Arduino",
                "model": "A000066",
                "quantity": 1,
                "purpose": "Main controller",
                "voltage": "5V",
                "current": "< 500mA",
                "logic_level": "5V",
                "purchase_status": "need_purchase",
                "price": "25.00",
                "vendor": "Arduino Store",
            },
            {
                "name": "5mm Red LED",
                "manufacturer": "Kingbright",
                "model": "WP7113ID",
                "quantity": 1,
                "purpose": "Visual output",
                "voltage": "2.0V",
                "current": "20mA",
                "logic_level": "5V",
                "purchase_status": "need_purchase",
                "price": "0.10",
                "vendor": "DigiKey",
            },
            {
                "name": "220 ohm resistor",
                "manufacturer": "Yageo",
                "model": "CFR-25JB-52-220R",
                "quantity": 1,
                "purpose": "Current limiting for LED",
                "voltage": "",
                "current": "",
                "logic_level": "",
                "purchase_status": "already_owned",
            },
        ],
        "total_estimate": "~$25",
    }
    result = bom_tool.execute("save", {"project_id": project.id, "bom": bom})
    assert result.success

    wiring_tool = SaveWiringDesignTool(project_manager)
    wiring = {
        "connections": [
            {"device": "LED", "pin": "anode", "target": "D13", "target_type": "controller"},
            {"device": "LED", "pin": "cathode", "target": "GND", "target_type": "gnd"},
        ],
        "pin_mapping": [{"device": "LED", "anode": "D13", "cathode": "GND"}],
        "warnings": ["Always use current-limiting resistor with LED"],
    }
    result = wiring_tool.execute("save", {"project_id": project.id, "wiring": wiring})
    assert result.success

    fw_tool = SaveFirmwareProjectTool(project_manager)
    firmware = {
        "platform": "arduino",
        "board": "arduino:avr:uno",
        "framework": "arduino",
        "libraries": [],
        "files": ["src/main.ino"],
    }
    result = fw_tool.execute("save", {"project_id": project.id, "firmware": firmware})
    assert result.success

    # Verify saved artifacts can be loaded
    latest_arch = project_manager.get_latest_artifact(project.id, "hardware_architecture")
    assert latest_arch is not None
    loaded = HardwareArchitecture.from_dict(json.loads(latest_arch.content))
    assert loaded.controller == "arduino"


def test_case_2_esp32_iot_data_transfer(project_manager):
    """ESP32 IoT project: verify WiFi, data transfer, web connectivity."""
    project = project_manager.create(name="ESP32 Sensor", goal="Send sensor data")

    arch_tool = SaveHardwareArchitectureTool(project_manager)
    arch = {
        "controller": "esp32",
        "controller_model": "ESP32-S3-DevKitC-1",
        "sensors": ["DHT22 temperature/humidity sensor"],
        "outputs": [],
        "communication": ["wifi", "i2c"],
        "power": "5V USB / onboard 3.3V regulator",
        "storage": "onboard flash",
        "interfaces": ["USB-C"],
    }
    assert arch_tool.execute("save", {"project_id": project.id, "architecture": arch}).success

    bom_tool = SaveBOMTool(project_manager)
    bom = {
        "items": [
            {
                "name": "ESP32-S3-DevKitC-1",
                "manufacturer": "Espressif",
                "model": "ESP32-S3-DevKitC-1-N8R8",
                "quantity": 1,
                "purpose": "Wi-Fi/BLE controller and main processor",
                "voltage": "3.3V",
                "interface_type": "WiFi / BLE / I2C",
                "purchase_status": "need_purchase",
            },
            {
                "name": "DHT22 AM2302",
                "manufacturer": "Aosong",
                "model": "AM2302",
                "quantity": 1,
                "purpose": "Temperature and humidity sensing",
                "voltage": "3.3V",
                "interface_type": "single-wire",
                "purchase_status": "need_purchase",
            },
        ]
    }
    assert bom_tool.execute("save", {"project_id": project.id, "bom": bom}).success

    fw_tool = SaveFirmwareProjectTool(project_manager)
    firmware = {
        "platform": "esp32",
        "board": "esp32:esp32:esp32s3",
        "framework": "arduino",
        "libraries": ["WiFi", "DHT sensor library"],
        "files": ["src/main.cpp"],
    }
    assert fw_tool.execute("save", {"project_id": project.id, "firmware": firmware}).success

    latest_fw = project_manager.get_latest_artifact(project.id, "firmware_project")
    loaded = FirmwareProject.from_dict(json.loads(latest_fw.content))
    assert loaded.platform == "esp32"
    assert "WiFi" in loaded.libraries


def test_case_3_hybrid_firmware_and_web_api(project_manager):
    """Hybrid product: firmware + web control page, verify API/data format alignment."""
    project = project_manager.create(name="Hybrid Controller", goal="Web controlled device")

    arch = HardwareArchitecture(
        controller="esp32",
        controller_model="ESP32-S3-DevKitC-1",
        sensors=["button"],
        outputs=["LED", "buzzer"],
        communication=["wifi"],
        power="5V USB",
    )
    SaveHardwareArchitectureTool(project_manager).execute(
        "save", {"project_id": project.id, "architecture": arch.to_dict()}
    )

    firmware = FirmwareProject(
        platform="esp32",
        board="esp32:esp32:esp32s3",
        framework="arduino",
        libraries=["WiFi", "ArduinoJson"],
        files=["src/main.cpp"],
    )
    SaveFirmwareProjectTool(project_manager).execute(
        "save", {"project_id": project.id, "firmware": firmware.to_dict()}
    )

    # Simulate alignment record as a decision
    RecordHardwareDecisionTool(project_manager).execute(
        "record",
        {
            "project_id": project.id,
            "decision": "continue_hardware",
            "reason": "Firmware JSON API /led/status matches web app contract",
        },
    )

    decisions = project_manager.list_decisions(project.id)
    assert any("continue_hardware" in d.decision for d in decisions)

    loaded = FirmwareProject.from_dict(
        json.loads(project_manager.get_latest_artifact(project.id, "firmware_project").content)
    )
    assert "ArduinoJson" in loaded.libraries
