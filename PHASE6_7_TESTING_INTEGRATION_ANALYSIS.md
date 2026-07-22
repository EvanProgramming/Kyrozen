# Phase 6/7 Testing Integration Analysis

## 目标

为 Kyrozen Phase 8（测试、产品验证与迭代闭环系统）做前期架构分析，明确：
- Phase 6 软件开发已经产出了哪些可被测试消费的信息
- Phase 7 硬件开发已经产出了哪些可被测试消费的信息
- 如何设计统一的 Test Artifact
- 如何建立 Requirement → Test Case → Result → Validation 的映射机制
- Testing System 如何连接 PRD、Feature、Code、Hardware、User Feedback

---

## 1. Phase 6 软件开发结构回顾

### 1.1 已有数据模型 (`kyrozen/development/models.py`)

| 模型 | 作用 | Phase 8 复用方式 |
|------|------|------------------|
| `TechnicalPlan` | 技术方案（应用类型、架构、前后端、数据库、API、部署） | 作为测试环境输入，判断测试重点 |
| `FeatureImplementation` | PRD Feature → 代码文件 + 测试文件 + 状态 | 直接映射到 Test Case 的 `related_feature` |
| `TestReport` | 简单聚合（total/passed/failed/skipped/errors/fix_history） | 保留，Phase 8 新增详细的 `TestCase`/`TestResult` 后汇总到此处 |
| `DeploymentGuide` | 运行与部署说明 | 作为测试环境/运行方式输入 |
| `DevelopmentArtifactBundle` | 汇总包 | 在 Testing Context 中整体加载 |

### 1.2 已有工具 (`kyrozen/tools/development_tools.py`)

| 工具 | 作用 | Phase 8 复用方式 |
|------|------|------------------|
| `save_technical_plan` | 保存 Technical Plan | 读取，不修改 |
| `save_feature_implementation` | 保存 Feature 与代码/测试映射 | 读取，用于 requirement→test 映射 |
| `save_test_report` | 保存 TestReport | 保留，Phase 8 新增 `save_test_case`/`save_test_result` 后可调用本工具汇总 |
| `save_deployment_guide` | 保存部署指南 | 读取 |
| `record_development_decision` | 记录开发决策 | 读取；Phase 8 重大测试/迭代决策复用 Decision Record 机制 |

### 1.3 代码/文件存储位置

Phase 6 代码统一放在：

```
projects/{project_id}/software/
```

测试执行方式：
- 通过通用 `TerminalTool` 运行 `pytest`、`npm test` 等命令
- 通过 `GitTool` 查看提交历史
- 通过 `FileReadTool`/`FileWriteTool` 读取/写入测试相关文件

---

## 2. Phase 7 硬件开发结构回顾

### 2.1 已有数据模型 (`kyrozen/hardware/models.py`)

| 模型 | 作用 | Phase 8 复用方式 |
|------|------|------------------|
| `HardwareArchitecture` | 控制器、传感器、输出、通信、电源、接口 | 作为硬件测试环境输入 |
| `Component` / `BOMItem` | 元件具体型号与参数 | 用于生成硬件测试清单 |
| `BOM` | 物料清单与采购状态 | 判断元件是否到位，影响测试计划 |
| `WiringDesign` | 接线图、Pin Mapping | 用于硬件集成测试与故障排查 |
| `FirmwareProject` | 平台、板型、框架、库、文件、编译/烧录状态 | 硬件测试核心对象 |
| `AssemblyStep` | 分步组装指导 | 作为硬件测试前置条件 |
| `HardwareDebugRecord` | 症状/假设/实验/结果/修复 | Phase 8 复用其结构，统一为 `TestResult`/`DebugRecord` |
| `HardwareArtifactBundle` | 汇总包 | 在 Testing Context 中整体加载 |

### 2.2 已有工具 (`kyrozen/tools/hardware_tools.py`)

| 工具 | 作用 | Phase 8 复用方式 |
|------|------|------------------|
| `save_hardware_architecture` | 保存硬件架构 | 读取 |
| `save_component` | 保存元件 | 读取 |
| `save_bom` / `update_purchase_status` | 保存/更新 BOM | 读取 |
| `save_wiring_design` | 保存接线设计 | 读取 |
| `save_firmware_project` | 保存固件项目元数据 | 读取并更新 build/upload 状态 |
| `save_assembly_step` | 保存组装步骤 | 读取 |
| `save_debug_record` | 保存硬件调试记录 | Phase 8 测试失败时直接复用 |
| `hardware_bridge` | arduino-cli / platformio 命令 | Phase 8 硬件测试执行直接复用 |
| `record_hardware_decision` | 记录硬件决策 | 读取；Phase 8 重大测试/迭代决策复用 |

### 2.3 固件/文件存储位置

Phase 7 固件统一放在：

```
projects/{project_id}/hardware/firmware/
```

测试执行方式：
- 通过 `hardware_bridge` 调用 `arduino-cli compile/upload/monitor` 或 `pio run`
- 通过 `FileReadTool` 读取串口日志文件或固件源码

---

## 3. PRD 需求如何映射到测试

### 3.1 当前 PRD 结构 (`kyrozen/planning/models.py`)

```python
class PRD:
    overview: str
    user_stories: list[str]
    functional_requirements: list[str]
    non_functional_requirements: list[str]
    mvp_scope: MVP
    out_of_scope: list[str]
```

`functional_requirements` 和 `non_functional_requirements` 是字符串列表，没有 ID。Phase 8 的 Requirement → Test 映射采用「内容哈希/索引」方式：

```
R0: 用户可以实时查看设备状态
R1: 系统响应时间小于 1 秒
R2: 设备通过 WiFi 上传数据
```

每个 `TestCase.related_requirement` 保存对应 requirement 字符串或 `R{N}` 引用。

### 3.2 映射规则

```
PRD.functional_requirements
        |
        v
TestPlan.requirements[]
        |
        v
TestCase.related_requirement
        |
        v
TestResult.test_case_id
        |
        v
ValidationReport.test_results[]
```

同时建立第二层映射到 Feature：

```
PRD.mvp_scope.mvp_features[]
        |
        v
FeatureImplementation.prd_feature
        |
        v
TestCase.related_feature
```

### 3.3 映射示例

PRD requirement: `用户可以实时查看设备状态`

对应 Test Cases:
- `TC-SW-01`: 功能测试 — 设备发送数据后 Web 页面显示最新状态（`related_requirement: 用户可以实时查看设备状态`）
- `TC-SW-02`: API 测试 — GET /api/status 返回 200 且 latency < 1s
- `TC-HW-01`: 硬件测试 — 固件每秒通过 WiFi 发送一次数据

---

## 4. 统一 Test Artifact 设计

### 4.1 新增数据模型 (`kyrozen/testing/models.py`)

#### TestCase

```python
@dataclass
class TestCase:
    id: str = ""                      # e.g. "TC-SW-01"
    name: str = ""                    # 简短名称
    type: str = ""                    # functional | ui | api | performance | security |
                                      # hardware_compile | hardware_module | hardware_integration |
                                      # hardware_power | hardware_stability
    related_requirement: str = ""     # PRD requirement text or R{N} reference
    related_feature: str = ""         # Feature name
    description: str = ""
    steps: list[str] = field(default_factory=list)
    expected: str = ""
    environment: str = ""
    priority: str = "medium"          # low | medium | high | critical
    status: str = "draft"             # draft | ready | skipped | deprecated
```

#### TestResult

```python
@dataclass
class TestResult:
    test_case_id: str = ""
    test_case_name: str = ""
    result: str = ""                  # passed | failed | skipped | error
    actual: str = ""                  # 实际观察
    errors: str = ""                  # 错误信息
    stdout: str = ""                  # 命令输出
    stderr: str = ""
    timestamp: str = ""
    duration_ms: int = 0
    environment: str = ""
    executed_by: str = "agent"        # agent | user | ci
```

#### TestPlan

```python
@dataclass
class TestPlan:
    name: str = ""
    objective: str = ""
    requirements: list[str] = field(default_factory=list)
    test_cases: list[TestCase] = field(default_factory=list)
    success_criteria: str = ""
    environment: str = ""
    status: str = "draft"             # draft | ready | running | completed
```

#### UserFeedback

```python
@dataclass
class UserFeedback:
    source_type: str = ""             # interview | trial | survey | comparison
    content: str = ""
    problems: list[str] = field(default_factory=list)
    sentiment: str = ""               # positive | neutral | negative
    timestamp: str = ""
    participant_id: str = ""
```

#### ValidationReport

```python
@dataclass
class ValidationReport:
    original_problem: str = ""
    tested_solution: str = ""
    test_results_summary: dict[str, Any] = field(default_factory=dict)
    user_feedback: list[UserFeedback] = field(default_factory=list)
    success_metrics: str = ""
    conclusion: str = ""              # pass | fail | partial | insufficient_evidence
    next_iteration: list[IterationItem] = field(default_factory=list)
```

#### IterationPlan / IterationItem

```python
@dataclass
class IterationItem:
    category: str = ""                # keep | modify | remove | investigate | new_feature
    target: str = ""                  # 目标功能/测试/元件
    reason: str = ""
    priority: str = "medium"          # low | medium | high | critical

@dataclass
class IterationPlan:
    items: list[IterationItem] = field(default_factory=list)
    overall_recommendation: str = ""
```

### 4.2 Artifact 保存类型

| Artifact Type | 模型 | 说明 |
|---------------|------|------|
| `test_plan` | `TestPlan` | 测试计划 |
| `test_case` | `TestCase` | 单个测试用例（也内嵌在 TestPlan 中） |
| `test_result` | `TestResult` | 测试执行结果 |
| `validation_report` | `ValidationReport` | 产品验证报告 |
| `iteration_plan` | `IterationPlan` | 迭代建议 |
| `user_feedback` | `UserFeedback` | 用户反馈记录 |

### 4.3 与现有 Artifact 的关系

- `TestReport`（Phase 6）保留为软件测试聚合摘要，Phase 8 在执行完 `TestCase`/`TestResult` 后可自动汇总更新它。
- `HardwareDebugRecord`（Phase 7）保留；当硬件测试失败时，`TestingAgent` 直接调用 `save_debug_record` 记录调试信息。
- `FeatureImplementation.tests` 字段用于反向查询某个 Feature 对应的测试用例。

---

## 5. Testing System 连接方式

### 5.1 整体数据流

```
Product Brief / PRD
        |
        v
Testing & Validation Agent
        |
        v
TestPlan (requirements → test_cases)
        |
        v
自动/手动执行
        |
        v
TestResult
        |
        v
ValidationReport + IterationPlan
        |
        v
Decision Record / Project.next_steps
```

### 5.2 与 Phase 6 软件开发的连接

| 连接点 | 方式 |
|--------|------|
| PRD → Test Plan | 读取 `PRD.functional_requirements` / `non_functional_requirements` |
| Feature → Test Case | 读取 `FeatureImplementation.prd_feature` 作为 `TestCase.related_feature` |
| Code → Test | 通过 `TerminalTool` 在 `projects/{project_id}/software/` 运行测试框架命令 |
| Test Result → Test Report | 汇总到 `TestReport`（total/passed/failed/skipped/errors） |
| 失败 → 调试 | Agent 遵循观察→假设→验证→修复→重测循环，必要时调用 `record_development_decision` |

### 5.3 与 Phase 7 硬件开发的连接

| 连接点 | 方式 |
|--------|------|
| PRD → Hardware Test | 读取 `HardwareArchitecture`、`FirmwareProject`、`BOM` |
| Firmware → Compile Test | 调用 `hardware_bridge` action=`compile` |
| Firmware → Upload Test | 调用 `hardware_bridge` action=`upload` |
| Runtime → Serial Log | 调用 `hardware_bridge` action=`monitor` 并保存输出 |
| Module Test → Assembly Step | 读取 `AssemblyStep` 确认当前组装进度 |
| Failure → Debug Record | 调用 `save_debug_record` |
| BOM → Test Readiness | 读取 `BOM` 采购状态，判断元件是否到位 |

### 5.4 与用户验证的连接

- `TestingAgent` 通过 `record_user_feedback` 工具保存用户访谈/试用/问卷/对比测试反馈。
- `ValidationReport` 综合工程测试结果与用户反馈，给出结论。
- 重大结论（如「删除 GPS 功能」）保存到 Decision Record。

---

## 6. Phase 8 开发计划

### 6.1 新增模块

| 文件 | 职责 |
|------|------|
| `kyrozen/testing/models.py` | TestCase、TestResult、TestPlan、UserFeedback、ValidationReport、IterationPlan 数据模型 |
| `kyrozen/testing/state.py` | TestingSession 阶段管理 |
| `kyrozen/testing/agent.py` | TestingAgent，专用 system prompt |
| `kyrozen/tools/testing_tools.py` | save_test_plan、save_test_case、save_test_result、record_user_feedback、save_validation_report、save_iteration_plan、run_software_test、run_hardware_test |
| `kyrozen/project/context.py` | 新增 `build_testing_context` |
| `kyrozen/api/server.py` | 新增 `mode="testing"` 与 `/api/projects/{id}/testing/state` |
| `kyrozen/web/index.html` | 新增 Testing & Validation 视图 |
| `tests/test_testing.py` | 覆盖模型、工具、Agent、API、三类案例 |

### 6.2 新增工具一览

| 工具 | 作用 |
|------|------|
| `save_test_plan` | 保存测试计划 |
| `save_test_case` | 保存/更新测试用例 |
| `save_test_result` | 保存测试结果 |
| `record_user_feedback` | 保存用户访谈/试用/问卷反馈 |
| `save_validation_report` | 保存产品验证报告 |
| `save_iteration_plan` | 保存迭代建议 |
| `run_software_test` | 在 software 目录执行测试命令（pytest / npm test 等） |
| `run_hardware_test` | 通过 `hardware_bridge` 执行编译/烧录/监控 |

### 6.3 Agent 行为约束

- 必须从 PRD 推导测试，不能脱离需求设计测试
- 必须区分「工程测试通过」与「产品验证通过」
- 测试失败不能直接修改产品，需先记录现象→假设→实验→结果
- 不能未经用户确认直接改变产品方向
- 不能实现 Phase 9 功能（跨项目学习、自动知识迁移）

### 6.4 Web UI 视图

新增 Testing Dashboard，展示：
- Requirements → Test Cases 映射
- Test Plan 与执行状态
- 软件测试结果
- 硬件测试结果（编译/烧录/串口日志）
- 用户反馈列表
- Validation Report
- Iteration Plan
- 最近决策与 Git 日志

---

## 7. 风险与注意事项

1. **PRD 需求是字符串**：映射机制依赖 Agent 正确引用 requirement 文本或统一 ID，需在 prompt 中明确要求。
2. **硬件测试依赖本地工具**：`arduino-cli` / `platformio` 是否安装决定硬件测试能否真正执行；无工具时应返回明确错误并允许保存预期结果。
3. **用户反馈无法自动收集**：当前阶段通过 Agent 引导用户输入并保存，不做主动外呼或真实用户招募。
4. **迭代建议不自动修改产品**：仅保存为 IterationPlan 和 Decision Record，等待用户确认后再进入 Phase 5/6/7 修改。

---

*待本分析确认后，开始 Phase 8 编码。*
