"""Tests for Kyrozen Phase 7 Hardware Development."""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from kyrozen.api.server import create_app
from kyrozen.config import KyrozenConfig
from kyrozen.hardware.bridge import HardwareBridge, HardwareBridgeError
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

from tests.conftest import MockModel


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


def test_bridge_compile_requires_board():
    bridge = HardwareBridge()
    result = bridge.compile()
    assert result["success"] is False
    assert "Board FQBN is required" in result["stderr"]


def test_bridge_upload_requires_board():
    bridge = HardwareBridge()
    result = bridge.upload()
    assert result["success"] is False
    assert "Board FQBN is required" in result["stderr"]


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
    app = create_app(config=config, model=MockModel(["Done"]))
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
