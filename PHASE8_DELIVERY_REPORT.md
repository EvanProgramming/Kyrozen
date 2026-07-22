# Kyrozen Phase 8 交付报告：测试、产品验证与迭代闭环系统

## 1. Testing Architecture

### 目标

将 Kyrozen 从「能生成软件/硬件原型」升级为「能验证产品是否真正解决原始问题」。用户在完成 PRD 与 Software/Hardware Implementation 后可以进入 **Testing & Validation Mode**，Agent 自动：

- 读取 PRD、Product Brief、Technical Plan 与现有实现产物
- 将 PRD 需求映射为具体测试用例（Requirement → Test Case）
- 生成结构化 Test Plan，覆盖软件、硬件与用户验证
- 执行软件测试命令（pytest、npm test 等）
- 通过 Local Hardware Bridge 执行硬件编译、烧录、串口监控
- 分析失败原因，遵循 Hardware Debugging Loop 而非直接修改产品
- 收集并记录用户反馈（访谈、试用、问卷、对比测试）
- 生成 Product Validation Report，回答「产品是否改善了原始问题」
- 输出 Iteration Plan，分类为 keep / modify / remove / investigate / new_feature

### 架构图

```
User
 |
 v
Web Chat (testing mode)
 |
 v
/api/chat (mode="testing")
 |
 v
TestingAgent  ← 继承 BaseAgent
 | - Read Inputs (PRD, Product Brief, Technical Plan, Implementation)
 | - Test Planning
 | - Requirement-to-Test Mapping
 | - Software Test Execution
 | - Hardware Test Execution
 | - Failure Analysis & Debugging Loop
 | - User Feedback Collection
 | - Validation Report Generation
 | - Iteration Planning
 |
 v
Kyrozen Core (BaseAgent runtime + Tool System)
 |
 v
Testing Tools
 | - save_test_plan
 | - save_test_case
 | - save_test_result
 | - record_user_feedback
 | - save_validation_report
 | - save_iteration_plan
 | - run_software_test
 | - run_hardware_test
 |
 v
Project Workspace
 | - Artifact: test_plan
 | - Artifact: test_case
 | - Artifact: test_result
 | - Artifact: user_feedback
 | - Artifact: validation_report
 | - Artifact: iteration_plan
 | - Decision: testing_decision / validation_decision
 | - Memory: testing
 | - Task: testing task
 | - Directory: projects/{project_id}/software/
 | - Directory: projects/{project_id}/hardware/firmware/
```

### 新增模块

| 文件 | 职责 |
|------|------|
| `kyrozen/testing/models.py` | `TestCase`、`TestResult`、`TestPlan`、`UserFeedback`、`IterationItem`、`IterationPlan`、`ValidationReport`、`TestingArtifactBundle` 数据模型与验证 |
| `kyrozen/testing/state.py` | `TestingSession` 运行时状态与阶段管理 |
| `kyrozen/testing/agent.py` | `TestingAgent`，专用 system prompt，禁止直接修改产品与跨项目学习 |
| `kyrozen/tools/testing_tools.py` | Phase 8 全部测试工具，包括保存 Artifact 与执行软件/硬件测试 |

---

## 2. Requirement Validation Flow

Phase 8 的核心设计是：测试不是凭空产生，而是来自 PRD 需求。建立如下闭环：

```
PRD
 |
 v
Requirement (R1, R2, ...)
 |
 v
Test Case (related_requirement = R1)
 |
 v
Test Execution → Test Result (passed / failed / skipped / error)
 |
 v
User Feedback (interview / trial / survey / comparison)
 |
 v
Validation Report (pass / fail / partial / insufficient_evidence)
 |
 v
Iteration Plan (keep / modify / remove / investigate / new_feature)
```

### Requirement-to-Test Mapping

`TestCase.related_requirement` 字段保存对应 PRD 需求文本或 `R{N}` 引用，`TestCase.related_feature` 保存对应 Feature 名称。例如：

| PRD 需求 | Test Case | 类型 | 预期 |
|----------|-----------|------|------|
| 用户可以实时查看设备状态 | TC-SW-01：状态页面渲染 | ui | 页面加载并显示数据 |
| 用户可以实时查看设备状态 | TC-SW-02：API 返回状态 JSON | api | 200 OK，JSON 包含设备状态 |
| 固件能够编译 | TC-HW-01：Firmware compile test | hardware_compile | 编译成功 |
| 传感器数据出现在串口 | TC-HW-02：Serial monitor logs sensor data | hardware_stability | 每秒打印传感器值 |

### 验证结论

`ValidationReport.conclusion` 不允许使用简单「测试通过」作为成功标准，必须结合用户反馈：

- `pass`：工程测试通过且用户验证正面
- `fail`：核心需求未满足或用户验证负面
- `partial`：部分满足，需要迭代
- `insufficient_evidence`：证据不足，需要补充测试或用户反馈

---

## 3. Software Testing Integration

### 连接关系

Software Testing 通过 `RunSoftwareTestTool` 连接 Phase 6 生成的代码：

```
PRD Requirement
       |
       v
Test Case (functional / ui / api / performance / security)
       |
       v
run_software_test
       |
       v
projects/{project_id}/software/
       |
       +-- Source Code
       +-- Test Files
       +-- Git Repo
       |
       v
Terminal Command (pytest / npm test / cargo test / ...)
       |
       v
Test Result Artifact (stdout / stderr / actual / errors)
```

### 支持的软件测试类型

| 类型 | 说明 | 典型执行方式 |
|------|------|--------------|
| `functional` | 验证核心功能是否工作 | 单元测试、集成测试 |
| `ui` | 验证页面与交互 | Playwright / Selenium / 手动检查 |
| `api` | 验证接口与数据 | curl / httpx / pytest |
| `performance` | 验证响应速度与资源占用 | 压力测试、计时测试 |
| `security` | 第一版基础支持：输入验证、权限检查 | 安全扫描、边界测试 |

### 安全约束

`RunSoftwareTestTool` 继承 TerminalTool 的安全策略，禁止以下命令模式：

- `rm -rf`
- `mkfs`
- 重定向到 `/dev/sd*`
- `curl ... | sh` / `wget ... | sh`
- 磁盘格式化、注册表删除、关键系统进程终止

所有命令在 `projects/{project_id}/software/` 目录下执行，路径隔离。

### 与 Git 的集成

测试失败时，Agent 不直接修改代码，而是：

1. 保存失败结果到 `test_result` Artifact
2. 在 Iteration Plan 中提出 `investigate` 或 `modify` 建议
3. 用户确认后，由 Phase 6 Software Development Agent 执行代码修复
4. 修复完成后重新运行 `run_software_test`

---

## 4. Hardware Testing Integration

### 连接关系

Hardware Testing 通过 `RunHardwareTestTool` 复用 Phase 7 的 `HardwareBridge`：

```
PRD Requirement
       |
       v
Test Case (hardware_compile / hardware_module / hardware_integration / hardware_power / hardware_stability)
       |
       v
run_hardware_test
       |
       v
projects/{project_id}/hardware/firmware/
       |
       +-- Arduino / ESP32 / PlatformIO Project
       |
       v
HardwareBridge (arduino-cli / platformio)
       |
       +-- list_ports
       +-- compile
       +-- upload
       +-- monitor
       |
       v
Test Result Artifact (stdout / stderr / actual / errors)
```

### 支持的硬件测试类型

| 类型 | 说明 | 典型执行方式 |
|------|------|--------------|
| `hardware_compile` | 验证固件能否编译 | `arduino-cli compile` / `pio run` |
| `hardware_module` | 单模块测试：传感器、LED、显示器 | 固件测试代码 + 串口读取 |
| `hardware_integration` | 多个模块组合验证 | 集成固件测试 |
| `hardware_power` | 功耗测试：电压、电流、运行时间 | 万用表/电源记录 |
| `hardware_stability` | 连续运行测试 | 长时间串口监控 |

### 硬件调试循环

当硬件测试失败时，Agent 必须遵循以下流程，而不是直接修改代码：

```
观察现象
   |
   v
比较预期
   |
   v
提出可能原因
   |
   v
设计验证实验
   |
   v
执行实验
   |
   v
排除原因
   |
   v
修改
   |
   v
重新测试
```

该流程通过 `TestingAgent` 的 system prompt 强制执行，工具层面不自动修改硬件代码。

### 安全约束

`HardwareBridge` 已对白名单命令、子命令、危险字符进行过滤，`RunHardwareTestTool` 继承这些约束：

- 仅允许 `arduino-cli` 和 `pio`
- 仅允许 `board`、`compile`、`upload`、`monitor` / `run`、`device` 子命令
- 禁止 shell 元字符与重定向

---

## 5. User Validation Design

产品不能只由工程测试判断。Phase 8 提供结构化的用户反馈收集机制：

### 反馈来源类型

| source_type | 说明 | 收集内容 |
|-------------|------|----------|
| `interview` | 用户访谈 | 用户反馈、遇到的问题、满意度 |
| `trial` | 产品试用 | 使用过程、操作障碍、主观感受 |
| `survey` | 问卷 | 满意度评分、问题选项 |
| `comparison` | 对比测试 | 旧方案 vs 新方案的体验差异 |

### 反馈数据结构

```json
{
  "source_type": "trial",
  "content": "功能可以使用，但是操作太复杂",
  "problems": ["操作太复杂", "首次配置步骤太多"],
  "sentiment": "negative",
  "timestamp": "2026-07-22T11:00:00+00:00",
  "participant_id": "P1"
}
```

### 与迭代计划的连接

用户反馈直接驱动 Iteration Plan。例如：

- 问题：用户觉得设备太复杂
- 建议：`modify` 首次配置流程，减少步骤
- 进一步：`investigate` 是否可以通过二维码自动填充 Wi-Fi 信息

### 核心原则

- 不因为「代码运行成功」就认为产品完成
- 不因为「测试通过」就忽略用户负面反馈
- 不自动修改产品方向，必须生成建议并等待用户确认

---

## 6. Test Results

运行全部测试：

```bash
.venv/bin/python -m pytest tests/ -q
```

结果：**238 passed, 3 warnings**

Phase 8 新增 35 个测试（`tests/test_testing.py`），覆盖：

- `TestCase`、`TestResult`、`TestPlan`、`UserFeedback`、`IterationItem`、`IterationPlan`、`ValidationReport`、`TestingArtifactBundle` 序列化与字段验证
- `TestingSession` 阶段切换、测试计划更新、测试用例添加/更新、测试结果/反馈/报告/迭代计划更新、序列化往返
- `SaveTestPlanTool`、`SaveTestCaseTool`、`SaveTestResultTool`、`RecordUserFeedbackTool`、`SaveValidationReportTool`、`SaveIterationPlanTool` 工具与 Artifact 保存
- `RunSoftwareTestTool` 安全命令执行与危险命令拦截
- `RunHardwareTestTool` 串口列表查询与错误处理
- `TestingAgent` system prompt 包含全部测试工具与约束规则
- `ProjectContextBuilder.build_testing_context()` 正确加载 PRD、技术计划、测试结果与现有测试状态
- `/api/chat` 的 `testing` 模式
- `/api/projects/{id}/testing/state` 端点
- 用户要求的三个验证案例：
  - **Case 1：软件项目** — 自动测试、Bug 记录、修复流程（通过 `run_software_test` + `save_test_result` + `save_iteration_plan`）
  - **Case 2：硬件项目** — 编译、串口、硬件测试记录（通过 `run_hardware_test` + `save_test_result`）
  - **Case 3：真实用户验证** — 输入「功能可以使用，但是操作太复杂」，生成下一轮优化建议（通过 `record_user_feedback` + `save_validation_report` + `save_iteration_plan`）

### 测试统计

| 阶段 | 测试文件 | 新增/覆盖 |
|------|----------|-----------|
| Phase 1 | `test_agent.py`, `test_api.py`, `test_config.py`, `test_json_memory.py`, `test_memory.py`, `test_permission.py`, `test_task.py`, `test_tools.py` | Core Agent, Memory, Task, Permission, Tools |
| Phase 2 | `test_project.py`, `test_project_context.py`, `test_project_db.py`, `test_api_project.py` | Project Workspace, Context, API |
| Phase 3 | `test_discovery.py`, `test_e2e_discovery.py` | Problem Discovery |
| Phase 4 | `test_research.py` | Market Research |
| Phase 5 | `test_planning.py` | Product Planning |
| Phase 6 | `test_development.py` | Software Development |
| Phase 7 | `test_hardware.py` | Hardware Development |
| Phase 8 | `test_testing.py` | Testing, Validation, Iteration |

### 警告说明

3 个警告均不影响功能：

1. `fastapi/testclient.py` 的 `StarletteDeprecationWarning`：提示使用 `httpx2`，不影响测试执行。
2. `PytestCollectionWarning: cannot collect test class 'TestingArtifactBundle'`：因为 dataclass 有 `__init__` 构造函数，pytest 不会将其识别为测试类，属于预期行为。
3. `PytestCollectionWarning: cannot collect test class 'TestingSession'`：同上。

---

## 7. Limitations

本阶段明确不实现：

- 自学习系统
- 跨项目知识迁移
- 自动主动分析（无需用户触发就自动分析）
- 专业测试管理平台 / 企业 QA 系统
- 未经用户确认直接修改产品需求、代码或硬件
- 将「工程测试通过」等同于「产品成功」

上述限制中，自学习、跨项目知识迁移与自动主动分析属于 **Phase 9**。

---

## 8. 如何运行

```bash
.venv/bin/uvicorn kyrozen.api.server:app --host 127.0.0.1 --port 8000 --reload
```

打开 http://127.0.0.1:8000，创建项目并完成 Product Planning、Software Development 或 Hardware Development 后，点击「进入 Testing & Validation」即可开始。

---

*Commit 已推送至 origin/main。*
