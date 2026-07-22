# Kyrozen Phase 7 交付报告：硬件与软硬件混合开发路线系统

## 1. Hardware Development Architecture

### 目标

将 Kyrozen 从「软件原型开发」升级为「真实硬件原型开发」。用户在完成 Product Brief、PRD 与 Technical Plan 后可以进入 **Hardware Development Mode**，Agent 自动：
- 读取 Product Brief、PRD、Technical Plan 与已有硬件产物
- 设计硬件架构（控制器、传感器、输出、通信、电源、接口）
- 选择具体元件（制造商 + 型号），并检查电压、电流、GPIO、通信协议兼容性
- 生成完整 BOM，支持采购状态管理
- 生成接线设计与 Pin Mapping
- 创建 Arduino / ESP32 / PlatformIO 固件项目
- 通过 Local Hardware Bridge 调用本地 `arduino-cli` 或 `platformio` 检测串口、编译、烧录、监控
- 提供分步组装指导与调试记录
- 支持 Hybrid 产品（硬件 + Web/App/Cloud API）的数据格式对齐

### 架构图

```
User
 |
 v
Web Chat (hardware mode)
 |
 v
/api/chat (mode="hardware")
 |
 v
HardwareDevelopmentAgent  ← 继承 BaseAgent
 | - Hardware Architecture Design
 | - Component Selection
 | - Compatibility Check
 | - BOM Generation
 | - Wiring Design
 | - Firmware Development
 | - Assembly Guidance
 | - Testing & Debugging
 | - Hybrid Product Alignment
 |
 v
Kyrozen Core (BaseAgent runtime + Tool System)
 |
 v
Hardware Tools
 | - save_hardware_architecture
 | - save_component
 | - save_bom
 | - update_purchase_status
 | - save_wiring_design
 | - save_firmware_project
 | - record_hardware_decision
 | - save_assembly_step
 | - save_debug_record
 | - hardware_bridge
 |
 v
Project Workspace
 | - Artifact: hardware_architecture
 | - Artifact: component_spec
 | - Artifact: bom
 | - Artifact: wiring_design
 | - Artifact: firmware_project
 | - Artifact: assembly_step
 | - Artifact: hardware_debug_record
 | - Decision: hardware_decision
 | - Memory: hardware
 | - Task: hardware task
 | - Directory: projects/{project_id}/hardware/
```

### 新增模块

| 文件 | 职责 |
|------|------|
| `kyrozen/hardware/models.py` | `HardwareArchitecture`、`Component`、`BOMItem`、`BOM`、`WiringConnection`、`WiringDesign`、`FirmwareProject`、`AssemblyStep`、`HardwareDebugRecord`、`HardwareArtifactBundle` 数据模型与验证 |
| `kyrozen/hardware/state.py` | `HardwareSession` 运行时状态与阶段管理 |
| `kyrozen/hardware/agent.py` | `HardwareDevelopmentAgent`，专用 system prompt，禁止 PCB/CAD/制造与危险硬件 |
| `kyrozen/hardware/bridge.py` | `HardwareBridge`，白名单封装 `arduino-cli` / `platformio` |
| `kyrozen/tools/hardware_tools.py` | Phase 7 全部硬件工具 |

---

## 2. Component Database Design

元件信息以 `Component` 数据模型为核心，保存为 Project Artifact（`type="component_spec"`），并嵌入 BOM 的 `BOMItem` 中。

### Component 数据结构

```json
{
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
  "notes": ""
}
```

### 设计要点

- **具体性强制**：Agent prompt 要求必须给出制造商 + 型号，禁止只写 "ESP32"。
- **兼容性字段**：`voltage`、`current`、`logic_level`、`interface_type` 用于后续自动兼容性检查。
- **替代方案**：每个元件必须提供 `alternative`，便于缺货时替换。
- **来源中立**：采购推荐不被佣金影响；无可靠链接时明确说明。

### 支持的控制器

- Arduino（如 Arduino Uno R3）
- ESP32（如 ESP32-S3-DevKitC-1）
- Raspberry Pi

### 支持的输入/输出/通信

- 输入：常见传感器、按钮、摄像头（简单应用）、麦克风
- 输出：LED、Display、蜂鸣器、简单音频、小型舵机
- 通信：WiFi、BLE、UART、I2C、SPI、USB

---

## 3. BOM System Design

BOM（Bill of Materials）是 Phase 7 的核心输出之一，保存为 `type="bom"` Artifact，支持版本管理与采购状态跟踪。

### BOMItem 数据结构

```json
{
  "name": "ESP32-S3-DevKitC-1",
  "manufacturer": "Espressif",
  "model": "ESP32-S3-DevKitC-1-N8R8",
  "quantity": 1,
  "purpose": "Main controller",
  "voltage": "3.3V",
  "current": "< 500mA",
  "logic_level": "3.3V",
  "interface_type": "WiFi / BLE / I2C",
  "purchase_status": "need_purchase",
  "price": "12.99",
  "currency": "USD",
  "vendor": "DigiKey",
  "link": "https://www.digikey.com/example",
  "availability": "in_stock"
}
```

### 采购状态

| 状态 | 含义 |
|------|------|
| `need_purchase` | 需要购买 |
| `purchased` | 已下单 |
| `arrived` | 已到货 |
| `already_owned` | 用户已有 |
| `alternative_needed` | 需要替代品 |

### 采购状态更新

通过 `update_purchase_status` 工具，用户可以告诉 Kyrozen：
- "我已经有这个元件了" → `already_owned`
- "这个缺货，需要替代" → `alternative_needed`

每次更新都会创建新的 BOM Artifact 版本，保留历史记录。

### 支持供应商

- Amazon、淘宝、京东、AliExpress、DigiKey、Mouser、官方商店
- 无可靠链接时明确说明，不生成虚假信息。

---

## 4. Hardware Bridge Design

Local Hardware Bridge 负责在「用户电脑」与「Arduino / ESP32」之间建立安全连接。

### 架构

```
Kyrozen Web  →  Local Hardware Bridge  →  User Computer  →  Arduino / ESP32
                    (Kyrozen process)
```

### 安全设计

- **命令白名单**：只允许 `arduino-cli` 和 `pio`
- **子命令白名单**：
  - `arduino-cli`: `board`, `compile`, `upload`, `monitor`
  - `pio`: `run`, `device`
- **危险字符过滤**：禁止 `;`, `&`, `|`, `` ` ``, `$`, `(`, `)`, `>`, `<`, `\`, `\n`
- **路径隔离**：所有硬件命令在 `projects/{project_id}/hardware/firmware/` 目录下执行
- **工具检查**：执行前检查 `arduino-cli` 或 `pio` 是否存在于 PATH

### 支持操作

| 操作 | 说明 |
|------|------|
| `list_ports` | 检测可用串口 |
| `compile` | 编译固件（自动识别 PlatformIO 项目或 Arduino CLI 项目） |
| `upload` | 烧录固件到板子 |
| `monitor` | 打开 Serial Monitor |

### 使用方式

Agent 通过 `hardware_bridge` 工具调用，例如：

```json
{
  "tool": "hardware_bridge",
  "action": "compile",
  "parameters": {
    "project_id": "proj_xxx",
    "board": "arduino:avr:uno"
  }
}
```

---

## 5. Test Results

运行全部测试：

```bash
.venv/bin/python -m pytest tests/ -q
```

结果：**203 passed, 1 warning**

Phase 7 新增 35 个测试（`tests/test_hardware.py`），覆盖：
- `HardwareArchitecture`、`Component`、`BOMItem`、`BOM`、`WiringConnection`、`WiringDesign`、`FirmwareProject`、`AssemblyStep`、`HardwareDebugRecord`、`HardwareArtifactBundle` 序列化与验证
- `HardwareSession` 阶段切换、元件/BOM/接线/固件更新、序列化往返
- `HardwareBridge` 命令白名单、危险参数过滤、无工具时串口检测
- `save_hardware_architecture`、`save_component`、`save_bom`、`update_purchase_status`、`save_wiring_design`、`save_firmware_project`、`record_hardware_decision`、`save_assembly_step`、`save_debug_record`、`hardware_bridge` 工具
- `/api/chat` 的 `hardware` 模式
- `/api/projects/{id}/hardware/state` 端点
- Agent Prompt 禁止 PCB/CAD/制造与危险硬件
- 用户要求的三类案例：
  - Case 1：Arduino LED 自动控制系统（主控、BOM、接线、固件）
  - Case 2：ESP32 IoT 项目（WiFi、传感器、数据传输）
  - Case 3：混合项目（ESP32 + Web 控制，固件/API/数据格式对齐）

---

## 6. Limitations

本阶段明确不实现：

- PCB 设计软件
- CAD 系统
- 3D 打印平台
- 小批量制造
- 供应链自动化
- 高压、大功率、医疗、安全关键系统
- 自动驾驶控制、工业安全设备
- 自制高容量电池

当前定位是「让用户完成真实硬件原型」，而非「进入量产制造」。

---

## 7. 如何运行

```bash
.venv/bin/uvicorn kyrozen.api.server:app --host 127.0.0.1 --port 8000 --reload
```

打开 http://127.0.0.1:8000，创建项目并完成 Product Planning 与 Software Development 后，点击「进入 Hardware Development」即可开始。

---

*Commit 已推送至 origin/main。*
