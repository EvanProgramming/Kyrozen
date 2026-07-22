# Phase 6 / Phase 7 Integration Analysis

This document analyzes how Kyrozen Phase 7 (Hardware and Hybrid Product Development) consumes the outputs of Phase 5 (Product Planning), Phase 6 (Software Development), and the Project Workspace, and proposes the interface, data models, tools, API, and Web UI design before implementation starts.

## 1. Phase 5 / Phase 6 Outputs: How They Are Stored

Phase 5 and Phase 6 artifacts are persisted through `ProjectManager.save_artifact()` and decisions through `ProjectManager.add_decision()` into the SQLite project database (`kyrozen.db`).

| Output | Artifact Type | Title | Key Fields |
|---|---|---|---|
| Product Brief | `product_brief` | "Product Brief" | `product_goal`, `target_user`, `mvp_scope`, `constraints`, `risks` |
| PRD | `prd` | "Product Requirements Document" | `overview`, `functional_requirements`, `non_functional_requirements`, `mvp_scope`, `out_of_scope` |
| Solution Comparison | `solution_comparison` | "Solution Comparison" | `solutions`, `recommendation` |
| Technical Plan | `technical_plan` | "Technical Plan" | `application_type`, `architecture`, `frontend`, `backend`, `database`, `apis`, `deployment`, `dependencies` |
| Feature Implementation | `feature_implementation_record` | "Feature Implementation: ..." | `prd_feature`, `files`, `tests`, `status` |
| Test Report | `test_report` | "Test Report" | `total`, `passed`, `failed`, `errors`, `fix_history` |
| Deployment Guide | `deployment_guide` | "Deployment Guide" | `run_instructions`, `deployment_instructions`, `requirements`, `environment_variables` |
| Product Decision | Decision row | - | `decision` prefixed with `"Product decision: "` |
| Development Decision | Decision row | - | `decision` prefixed with `"Development decision: "` |

### 1.1 How Phase 7 Reads Phase 5 / Phase 6 Outputs

Phase 7 follows the same read pattern as Phase 4/5/6:

```python
latest_prd = project_manager.get_latest_artifact(
    project_id, "prd", title="Product Requirements Document"
)
prd = PRD()
if latest_prd is not None:
    prd = PRD.from_dict(json.loads(latest_prd.content))

latest_brief = project_manager.get_latest_artifact(
    project_id, "product_brief", title="Product Brief"
)
product_brief = ProductBrief()
if latest_brief is not None:
    product_brief = ProductBrief.from_dict(json.loads(latest_brief.content))

latest_tech_plan = project_manager.get_latest_artifact(
    project_id, "technical_plan", title="Technical Plan"
)
tech_plan = TechnicalPlan()
if latest_tech_plan is not None:
    tech_plan = TechnicalPlan.from_dict(json.loads(latest_tech_plan.content))

product_decisions = [
    d for d in project_manager.list_decisions(project_id)
    if d.decision.startswith("Product decision: ")
]

development_decisions = [
    d for d in project_manager.list_decisions(project_id)
    if d.decision.startswith("Development decision: ")
]
```

### 1.2 Inputs for Hardware Development

The Hardware Development Agent needs:

- **Product Brief**: target user, value proposition, MVP features, constraints, risks.
- **PRD**: functional and non-functional requirements, MVP scope, out-of-scope list (hard guardrail).
- **Technical Plan** (if software is already planned): backend, database, APIs, deployment, dependencies. For hybrid products this defines the software side that the firmware must talk to.
- **Approved Product Decisions**: chosen solution direction and scope limits.
- **Approved Development Decisions**: stack choices that constrain firmware choices.
- **Existing Software Project Files** (for hybrid products): to align data formats and APIs.

## 2. Hardware Development Agent Architecture

### 2.1 Agent Design

Create `kyrozen/hardware/agent.py::HardwareDevelopmentAgent` inheriting `BaseAgent`.

Input:
- Product Brief
- PRD
- Technical Plan (optional, for hybrid products)
- Approved product and development decisions
- Existing hardware project state

Output:
- Hardware Architecture artifact
- Component list / Component Database records
- BOM artifact
- Wiring Design artifact
- Firmware Project artifact
- Assembly Step artifacts
- Hardware Debug Records
- Hardware Decisions

### 2.2 Hardware Session State

Create `kyrozen/hardware/state.py::HardwareSession`:

```python
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

@dataclass
class HardwareSession:
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
```

## 3. Core Data Models

Create `kyrozen/hardware/models.py`:

```python
VALID_CONTROLLERS = {"arduino", "esp32", "raspberry_pi"}
VALID_COMMUNICATIONS = {"wifi", "ble", "uart", "i2c", "spi", "usb"}
VALID_PURCHASE_STATUSES = {
    "need_purchase", "purchased", "arrived", "already_owned", "alternative_needed"
}
VALID_HARDWARE_DECISIONS = {
    "continue_hardware",
    "change_component",
    "narrow_scope",
    "pause",
    "abandon",
}

@dataclass
class HardwareArchitecture:
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

@dataclass
class Component:
    name: str = ""                # e.g. "MPU6050 GY-521 module"
    manufacturer: str = ""
    model: str = ""
    quantity: int = 1
    purpose: str = ""
    voltage: str = ""             # e.g. "3.3V"
    current: str = ""             # e.g. "< 10mA"
    logic_level: str = ""         # e.g. "3.3V / 5V tolerant"
    interface_type: str = ""      # e.g. "I2C"
    compatibility: str = ""       # free-form compatibility notes
    alternative: str = ""
    notes: str = ""

@dataclass
class BOMItem(Component):
    purchase_status: str = "need_purchase"
    price: str = ""               # e.g. "$4.50"
    currency: str = "USD"
    vendor: str = ""              # e.g. "Adafruit"
    link: str = ""
    availability: str = ""        # e.g. "in_stock", "unknown"

@dataclass
class BOM:
    items: list[BOMItem] = field(default_factory=list)
    total_estimate: str = ""
    currency: str = "USD"
    notes: str = ""

@dataclass
class WiringConnection:
    device: str = ""              # e.g. "MPU6050"
    pin: str = ""                 # e.g. "SDA"
    target: str = ""              # e.g. "GPIO21"
    target_type: str = ""         # e.g. "controller", "power", "gnd"
    notes: str = ""

@dataclass
class WiringDesign:
    connections: list[WiringConnection] = field(default_factory=list)
    pin_mapping: list[dict] = field(default_factory=list)
    diagram_text: str = ""        # ASCII / textual representation
    warnings: list[str] = field(default_factory=list)

@dataclass
class FirmwareProject:
    platform: str = ""            # "arduino", "esp32", "platformio"
    board: str = ""               # e.g. "esp32-s3-devkitc-1"
    framework: str = ""           # e.g. "arduino"
    libraries: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    build_status: str = "pending" # "pending", "success", "failed"
    build_output: str = ""
    upload_status: str = "pending"
    upload_output: str = ""

@dataclass
class AssemblyStep:
    order: int = 0
    title: str = ""
    instructions: str = ""
    components_involved: list[str] = field(default_factory=list)
    status: str = "pending"       # "pending", "done", "blocked"
    verification_method: str = "" # e.g. "photo", "continuity_test", "visual"

@dataclass
class HardwareDebugRecord:
    symptom: str = ""
    hypothesis: str = ""
    test: str = ""
    result: str = ""
    fix: str = ""
    status: str = "open"          # "open", "verified", "closed"
```

### 3.1 Compatibility Check Rules

The agent and a dedicated helper should validate:

- **Voltage**: every component's `voltage` must match the controller rail or be explicitly level-shifted.
- **Current**: sum of component currents must be within the controller/power supply budget.
- **GPIO**: no duplicate pin assignment; respect input-only / output-only pins.
- **Communication**: I2C addresses must not collide; SPI/UART bus limits respected.
- **Logic Level**: 5V and 3.3V devices must not be directly connected without a level shifter.

For the first version, these checks can be rule-based helpers used by the agent and surfaced in the Web UI.

## 4. Project Workspace Layout for Hardware Project

Each Kyrozen project gets a self-contained hardware project directory alongside the software directory:

```
projects/{project_id}/
├── memory.json
├── software/                  # Phase 6 software project root
└── hardware/                  # Phase 7 hardware project root
    ├── README.md
    ├── architecture.json
    ├── bom.json
    ├── wiring.json
    ├── firmware/
    │   ├── platformio.ini     # if PlatformIO
    │   └── src/
    │       └── main.cpp / main.py
    └── .git/                  # Initialized by GitTool
```

The hardware project root is computed as:

```python
hardware_dir = os.path.join(config.project_dir(project_id), "hardware")
```

All hardware files, firmware, BOM, and wiring designs must be scoped to this directory.

## 5. PRD-to-Hardware Traceability

Every hardware decision must be traceable back to a PRD requirement:

```
PRD Requirement: "Device measures running cadence"
  └─ Component: MPU6050 GY-521 module
  └─ Wiring: MPU6050.SDA -> ESP32 GPIO21
  └─ Firmware: read_accel() in main.cpp
  └─ Test: test_cadence_reading.py / serial test
```

The agent prompt must require:
- "Before selecting a component, identify which PRD requirement it serves."
- "Do not select components for features listed in PRD.out_of_scope."
- "Do not add new product features that are not in the PRD."
- "Do not design PCB, CAD, 3D prints, or enter manufacturing."

## 6. Tools Needed

### 6.1 Reused Tools

| Tool | Purpose |
|---|---|
| `file_read` | Read existing firmware/source files |
| `file_write` | Create/modify firmware/source files |
| `list_dir` | Explore hardware project structure |
| `find_files` | Find firmware/test files |
| `terminal` | Run package managers, tests, build tools |
| `git` | Init, commit, diff, log |

### 6.2 New Hardware Tools

Create `kyrozen/tools/hardware_tools.py`:

| Tool | Actions | Purpose |
|---|---|---|
| `save_hardware_architecture` | `save` | Persist `hardware_architecture` artifact |
| `save_component` | `save` | Persist a component specification |
| `save_bom` | `save` | Persist `bom` artifact |
| `update_purchase_status` | `update` | Mark BOM item status |
| `save_wiring_design` | `save` | Persist `wiring_design` artifact |
| `save_firmware_project` | `save` | Persist `firmware_project` artifact and write files |
| `record_hardware_decision` | `record` | Record hardware decisions |
| `save_assembly_step` | `save` | Persist an assembly step |
| `save_debug_record` | `save` | Persist a debug record |
| `hardware_bridge` | `list_ports`, `compile`, `upload`, `monitor` | Local Arduino CLI / PlatformIO bridge |

All persistence tools accept `project_id` and delegate to `ProjectManager.save_artifact()` or `ProjectManager.add_decision()`.

### 6.3 Local Hardware Bridge

Create `kyrozen/hardware/bridge.py::HardwareBridge`.

Responsibilities:
- Detect available serial ports.
- Compile firmware with `arduino-cli` or `platformio`.
- Upload firmware to the board.
- Open a serial monitor.

Allowed commands (whitelist):
- `arduino-cli board list`
- `arduino-cli compile ...`
- `arduino-cli upload ...`
- `arduino-cli monitor ...`
- `pio run ...`
- `pio device list ...`
- `pio run --target upload ...`
- `pio device monitor ...`

The bridge runs commands via `subprocess` in the `hardware/firmware/` directory. It returns structured output:

```python
{
    "success": bool,
    "stdout": str,
    "stderr": str,
    "ports": ["COM3", "/dev/ttyUSB0"],
}
```

Security:
- The bridge validates that the command is in the whitelist.
- In strict mode, it still requires user confirmation via the existing permission system.
- It never executes arbitrary shell commands.

## 7. API Changes

### 7.1 Chat Mode

Extend `ChatRequest.mode` to include `"hardware"`.

Route the hardware agent:

```python
elif request.mode == "hardware":
    agent = _get_hardware_agent()
    context = builder.build_hardware_context(project)
```

Create `_hardware_agent` in lifespan and `_get_hardware_agent()` helper.

### 7.2 State Endpoint

Add:

```python
@app.get("/api/projects/{project_id}/hardware/state")
async def api_hardware_state(project_id: str):
    # Return architecture, components, bom, wiring, firmware, assembly_steps,
    # debug_records, hardware decisions, and recent git log for hardware/
```

## 8. Context Builder Extension

Add `build_hardware_context(project)` to `kyrozen/project/context.py`.

Inject:
- Product Brief target user / constraints / MVP features
- PRD functional requirements and out-of-scope list
- Existing Technical Plan (if any)
- Approved product and development decisions
- Existing hardware project files summary
- Recent hardware memories

## 9. Web UI Changes

Add a "Hardware Development" button on the project detail page.

New view `view-hardware` shows:
- PRD / product brief summary (read-only)
- Hardware Architecture panel
- Component / BOM panel with purchase status
- Wiring Design panel
- Firmware panel with compile / upload status
- Assembly Steps checklist
- Debug Records
- Hardware Decisions
- Git log for `hardware/`

## 10. Constraints

- No PCB design, CAD, 3D printing, or manufacturing.
- No high-voltage, high-power, medical, or safety-critical systems.
- Components must be specific (manufacturer + model), not generic names.
- Compilation success is not enough; assembly and real-device testing are required.
- For hybrid projects, firmware and software APIs/data formats must stay consistent.

## 11. Implementation Order

1. Create `kyrozen/hardware/models.py` and `kyrozen/hardware/state.py`
2. Create `kyrozen/hardware/agent.py::HardwareDevelopmentAgent`
3. Create `kyrozen/hardware/bridge.py::HardwareBridge`
4. Create `kyrozen/tools/hardware_tools.py`
5. Register tools in `kyrozen/tools/registry.py`
6. Add `build_hardware_context()` to `kyrozen/project/context.py`
7. Add hardware agent and `/hardware/state` endpoint to `kyrozen/api/server.py`
8. Add Hardware Development view to `kyrozen/web/index.html`
9. Write `tests/test_hardware.py`
10. Run all tests, restart server, open browser
