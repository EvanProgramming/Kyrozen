# Phase 8 Learning Integration Analysis

## 目标

在开始 Phase 9 编码之前，先明确：

1. 当前已有 Memory 结构能支持什么。
2. Project Workspace 中哪些数据可以作为学习来源。
3. Phase 8 Testing 系统输出了哪些可被学习的事件。
4. 如何从这些数据中提取、分类、验证并保存为可复用的知识。
5. 如何基于已有数据生成主动改进建议。

---

## 1. 当前 Memory 系统分析

### 1.1 核心接口

```python
# kyrozen/memory/interface.py
@dataclass
class MemoryRecord:
    id: str
    category: str          # user, project, knowledge, failure
    content: str
    metadata: dict[str, Any]
    timestamp: str

class MemoryInterface:
    def save(self, category: str, content: str, **metadata: Any) -> MemoryRecord: ...
    def query(self, category: str | None = None, query: str | None = None, limit: int = 10, **filters: Any) -> list[MemoryRecord]: ...
    def update(self, record_id: str, content: str, **metadata: Any) -> MemoryRecord | None: ...
    def delete(self, record_id: str) -> bool: ...
```

### 1.2 实现

| 实现 | 文件 | 特点 |
|------|------|------|
| `InMemoryMemory` | `kyrozen/memory/interface.py` | 内存存储，关键词匹配 |
| `JsonFileMemory` | `kyrozen/memory/scoped.py` | JSON 文件持久化 |
| `ProjectMemory` | `kyrozen/memory/scoped.py` | 自动注入 `project_id` 到 metadata |

### 1.3 对 Phase 9 的启示

- `category` 字段当前只有 `user / project / knowledge / failure` 四种，**不足以承载 Phase 9 的学习分类**。
- `metadata` 是自由字典，可以扩展，用于存储 `memory_type`、`confidence`、`verification_status`、`source_project_id`、`permissions` 等。
- 当前查询是关键词匹配，**不支持语义相似度**。Phase 9 的跨项目复用需要先基于关键词/标签匹配，后续可升级向量存储。
- `ProjectMemory` 已能按 `project_id` 过滤，可作为项目级学习的基础。

### 1.4 需要扩展的 Memory 能力

- 新增 Learning 专用 category，例如 `learning`。
- 通过 `metadata.memory_type` 区分 `user_preference`、`user_capability`、`project_fact`、`product_decision`、`validated_success`、`validated_failure`、`external_knowledge`。
- 通过 `metadata.confidence` 和 `metadata.verification_status` 管理可信度。
- 通过 `metadata.scope` 区分 `private`（仅本项目）、`user`（跨项目但仅当前用户）、`public`（可共享知识）。

---

## 2. Project Workspace 数据可作为学习来源

### 2.1 Project 实体

```python
# kyrozen/project/project.py
@dataclass
class Project:
    name: str
    description: str = ""          # 初始想法
    goal: str = ""                 # 项目目标
    status: str = "active"         # active | paused | completed | archived
    current_stage: str = "problem_discovery"
    next_steps: str = ""
    risks: list[str] = field(default_factory=list)
    id: str
    created_at: str
    updated_at: str
```

**可学习信息**：

- 项目目标与初始问题的对应关系。
- 项目当前所处阶段，判断是否有阶段跳跃或长期停滞。
- `risks` 列表，可作为风险知识来源。

### 2.2 Decision 记录

```python
@dataclass
class Decision:
    project_id: str
    decision: str                  # 决策内容
    reason: str = ""               # 决策理由
    alternatives: list[str] = field(default_factory=list)
    rejected_reasons: dict[str, str] = field(default_factory=dict)
    source: str = "agent"
    id: str
    timestamp: str
```

**可学习信息**：

- 产品决策（例如：选择 Software Only 而非 Hybrid）。
- 技术决策（例如：选择 Flask 而非 Django）。
- 硬件决策（例如：选择 ESP32-S3 而非 Arduino）。
- 决策理由与备选方案可用于后续相似项目的推荐。

### 2.3 Artifact 系统

```python
@dataclass
class Artifact:
    project_id: str
    type: str                      # problem_brief, market_research_report, product_brief, prd, ...
    title: str
    content: str
    version: int
    change_reason: str
    id: str
    created_at: str
    updated_at: str
```

**已有的 Artifact 类型与学习价值**：

| Artifact 类型 | 来源阶段 | 可学习内容 |
|---------------|----------|------------|
| `problem_brief` | Phase 3 | 原始问题、用户痛点、问题边界 |
| `market_research_report` | Phase 4 | 竞品方案、市场缺口、失败案例 |
| `product_brief` | Phase 5 | 产品目标、目标用户、MVP 范围 |
| `prd` | Phase 5 | 功能需求、非功能需求、成功指标、out_of_scope |
| `solution_comparison` | Phase 5 | 多方案比较维度与推荐理由 |
| `technical_plan` | Phase 6 | 应用类型、架构、技术栈 |
| `feature_implementation` | Phase 6 | PRD 功能与代码文件映射 |
| `test_report` | Phase 6 | 测试结果、错误、修复历史 |
| `deployment_guide` | Phase 6 | 部署方式、环境变量 |
| `hardware_architecture` | Phase 7 | 控制器、传感器、通信方案 |
| `component_spec` | Phase 7 | 元件型号、兼容性、替代方案 |
| `bom` | Phase 7 | 元件清单、采购状态、成本 |
| `wiring_design` | Phase 7 | 接线方案、Pin Mapping |
| `firmware_project` | Phase 7 | 固件框架、库依赖 |
| `assembly_step` | Phase 7 | 组装步骤 |
| `hardware_debug_record` | Phase 7 | 硬件故障现象、原因、解决方案 |
| `test_plan` | Phase 8 | 测试目标、需求覆盖、测试用例 |
| `test_case` | Phase 8 | 需求到用例的映射 |
| `test_result` | Phase 8 | 测试通过/失败、实际结果、错误信息 |
| `user_feedback` | Phase 8 | 用户反馈、问题、情感 |
| `validation_report` | Phase 8 | 验证结论、成功指标、是否解决原始问题 |
| `iteration_plan` | Phase 8 | keep / modify / remove / investigate / new_feature |

### 2.4 Task 记录

```python
# kyrozen/core/task.py
class Task:
    title: str
    description: str
    status: str                     # pending | running | waiting_confirmation | completed | failed | cancelled
    steps: list[TaskStep]
    result: Any
    errors: list[str]
    project_id: str | None
```

**可学习信息**：

- 哪些任务经常失败或需要用户确认。
- 任务结果中的成功/失败模式。
- 用户拒绝的高风险操作类型。

---

## 3. Phase 8 Testing 数据结构与可学习事件

### 3.1 TestResult（测试结果）

```python
@dataclass
class TestResult:
    test_case_id: str
    test_case_name: str
    result: str                     # passed | failed | skipped | error
    actual: str
    errors: str
    stdout: str
    stderr: str
    timestamp: str
    duration_ms: int
    environment: str
    executed_by: str                # agent | user | ci
```

**可学习事件**：

- `result == "failed"` 或 `"error"`：提取失败知识（问题、原因、影响范围）。
- `result == "passed"`：如果与关键需求相关，可提取成功经验。
- 相同测试反复失败：升级为高可信度失败知识。
- 相同测试长期通过：升级为可复用成功方案。

### 3.2 UserFeedback（用户反馈）

```python
@dataclass
class UserFeedback:
    source_type: str                # interview | trial | survey | comparison
    content: str
    problems: list[str]
    sentiment: str                  # positive | neutral | negative
    timestamp: str
    participant_id: str
```

**可学习事件**：

- 负面反馈中反复出现的问题：用户偏好或产品缺陷。
- 正面反馈中反复出现的价值点：成功经验。
- 特定用户群体的反馈：用户能力/偏好。

### 3.3 ValidationReport（验证报告）

```python
@dataclass
class ValidationReport:
    original_problem: str
    tested_solution: str
    test_results_summary: dict[str, Any]
    user_feedback: list[UserFeedback]
    success_metrics: str
    conclusion: str                 # pass | fail | partial | insufficient_evidence
    next_iteration: list[IterationItem]
```

**可学习事件**：

- `conclusion == "pass"`：完整成功案例。
- `conclusion == "partial"`：部分方案有效，记录有效部分与无效部分。
- `conclusion == "fail"`：方案未能解决原始问题，记录失败原因。
- `conclusion == "insufficient_evidence"`：标记为未验证假设，未来需要补充。

### 3.4 IterationPlan（迭代计划）

```python
@dataclass
class IterationItem:
    category: str                   # keep | modify | remove | investigate | new_feature
    target: str
    reason: str
    priority: str                   # low | medium | high | critical

@dataclass
class IterationPlan:
    items: list[IterationItem]
    overall_recommendation: str
```

**可学习事件**：

- `keep`：被验证有价值的部分，可保存为成功知识。
- `modify` / `remove`：用户不满意的部分，可保存为用户偏好或失败知识。
- `investigate`：未验证假设，可用于主动建议。

### 3.5 HardwareDebugRecord（硬件调试记录）

```python
# kyrozen/hardware/models.py
@dataclass
class HardwareDebugRecord:
    symptom: str
    expected: str
    possible_causes: list[str]
    experiment: str
    result: str
    root_cause: str
    fix: str
```

**可学习事件**：

- 完整的调试闭环（symptom → root_cause → fix）是高质量的失败知识。
- 可与 component / BOM 数据关联，形成「某元件 + 某症状 → 某解决方案」的知识。

---

## 4. Learning Data Model 设计

基于以上数据来源，设计 Phase 9 的学习数据模型。

### 4.1 LearningRecord（学习记录）

```python
@dataclass
class LearningRecord:
    id: str
    memory: str                     # 学习内容的自然语言描述
    memory_type: str                # user_preference | user_capability | project_fact
                                    # | product_decision | validated_success | validated_failure | external_knowledge
    source: str                     # 来源描述，如 "test_result:TC-HW-01" / "decision:dec_xxx" / "user_feedback:U1"
    source_project_id: str | None   # 来源项目 ID
    confidence: str                 # low | medium | high
    verification_status: str        # unverified | user_provided | externally_verified | experiment_verified | repeatedly_verified
    scope: str                      # private | user | public
    tags: list[str]                 # 标签，用于检索
    created_at: str
    updated_at: str
```

### 4.2 FailureKnowledge（失败知识）

```python
@dataclass
class FailureKnowledge:
    problem: str
    cause: str
    solution: str
    affected_scope: str             # 例如：ESP32-S3 + DHT22
    verification: str               # 如何验证该解决方案有效
    source_project_id: str | None
    confidence: str
    verification_status: str
```

### 4.3 SuccessKnowledge（成功知识）

```python
@dataclass
class SuccessKnowledge:
    goal: str
    solution: str
    conditions: list[str]           # 适用条件
    result: str                     # 验证结果
    source_project_id: str | None
    confidence: str
    verification_status: str
```

### 4.4 Suggestion（主动建议）

```python
@dataclass
class Suggestion:
    id: str
    suggestion: str                 # 建议内容
    reason: str                     # 理由
    evidence: list[str]             # 证据列表
    impact: str                     # 影响评估
    priority: str                   # low | medium | high | critical
    status: str                     # new | accepted | rejected | later | ignored
    category: str                   # scope_drift | unverified_assumption | cost_optimization | tech_risk | test_gap | new_opportunity
    source_project_id: str
    related_learning_ids: list[str]
    created_at: str
    updated_at: str
```

### 4.5 LearningEvent（触发学习的事件）

```python
@dataclass
class LearningEvent:
    event_type: str                 # decision | test_result | user_feedback | validation_report | iteration_plan | hardware_debug
    project_id: str
    artifact_id: str | None         # 关联的 artifact id
    payload: dict[str, Any]         # 事件数据
    timestamp: str
```

---

## 5. Knowledge Extraction Flow

```
Project Event
   |
   v
LearningEvent (封装事件)
   |
   v
LearningExtractor (基于规则的启发式提取 + Agent 语义提取)
   |
   +-- 判断事件类型
   +-- 读取关联 Artifact
   +-- 提取 memory / failure / success
   +-- 打标签、分类、设定 confidence 与 verification_status
   |
   v
LearningRecord / FailureKnowledge / SuccessKnowledge
   |
   v
Memory Backend (JsonFileMemory / ProjectMemory)
   |
   v
Future Query (按项目、按用户、按标签、按关键词)
```

### 5.1 提取规则示例

| 事件 | 提取规则 | 生成记忆 |
|------|----------|----------|
| `test_result` 中 `result=failed` | 提取 `errors` 和 `actual` | `validated_failure` 或 `project_fact` |
| `test_result` 中 `result=passed` 且关联 high priority test case | 提取 `test_case_name` 和 `related_requirement` | `validated_success` |
| `user_feedback` 中 `sentiment=negative` | 提取 `problems` | `user_preference` / `validated_failure` |
| `validation_report` 中 `conclusion=pass` | 提取 `tested_solution` 和 `success_metrics` | `validated_success` |
| `iteration_plan` 中 `category=remove` | 提取 `target` 和 `reason` | `product_decision` / `user_preference` |
| `hardware_debug_record` 中 `root_cause` 非空 | 提取 symptom/cause/fix | `validated_failure` |
| `decision` 中 alternatives 非空 | 提取决策与理由 | `product_decision` |

### 5.2 可信度与验证状态映射

| 来源 | 默认 confidence | 默认 verification_status |
|------|-----------------|--------------------------|
| Agent 自动生成 | low | unverified |
| 用户明确确认 | medium | user_provided |
| 测试通过 | medium | experiment_verified |
| 多次测试通过 / 多个用户反馈一致 | high | repeatedly_verified |
| 外部官方文档 | high | externally_verified |

---

## 6. Suggestion Pipeline 设计

### 6.1 触发时机

- **事件触发**：当新的 test_result / user_feedback / validation_report / iteration_plan 保存时，立即触发分析。
- **空闲触发**：用户未主动操作时，定时扫描项目数据生成建议（可配置开关）。
- **用户请求**：用户进入 Improvement Center 时，可手动请求分析。

### 6.2 检测维度

| 维度 | 输入数据 | 检测逻辑 |
|------|----------|----------|
| `scope_drift` | PRD.out_of_scope + 当前 iteration_plan / feature_records | 当前迭代是否涉及 out_of_scope 内容 |
| `unverified_assumption` | PRD.functional_requirements + user_feedback + validation_report | 需求是否缺乏用户验证 |
| `cost_optimization` | BOM + component_spec | 是否存在重复元件、可替代低成本方案 |
| `tech_risk` | technical_plan + hardware_architecture + test_report | 架构复杂度、未测试模块 |
| `test_gap` | PRD.requirements + test_plan.test_cases | 哪些需求没有对应测试用例 |
| `new_opportunity` | market_research_report + latest components / tools | 市场变化或新技术 |

### 6.3 建议生成流程

```
Project Data Scan
   |
   v
Heuristic Detectors（规则检测器）
   |
   v
Detected Signals
   |
   v
LearningAgent / SuggestionGenerator
   |
   v
Suggestion (new)
   |
   v
User Review (Improvement Center)
   |
   v
Accepted / Rejected / Later / Ignored
   |
   v
Learning Feedback Loop (更新学习权重)
```

---

## 7. Privacy and Control Design

### 7.1 数据权限范围

| scope | 说明 | 示例 |
|-------|------|------|
| `private` | 仅属于当前项目，不跨项目使用 | 本项目的具体代码文件路径 |
| `user` | 当前用户的所有项目可复用 | 用户偏好低成本方案、用户熟悉 Arduino |
| `public` | 通用技术知识，不绑定用户 | ESP32 某 GPIO 不支持 PWM |

### 7.2 用户控制点

- **查看**：Learning Center 展示所有学习记录，包括来源、可信度、验证状态、权限范围。
- **修改**：用户可以编辑 `memory` 内容、调整 confidence、更改 scope。
- **删除**：用户可以删除错误记忆，删除后未来不再使用。
- **限制**：用户可以将某条记忆的 `scope` 从 `user` 改为 `private`。
- **关闭**：用户可以关闭「空闲分析」，仅保留事件触发分析。
- **恢复**：用户可以查看已拒绝建议的历史，并恢复为 `later` 或 `new`。

### 7.3 安全原则

- 不自动修改项目（代码、BOM、PRD）。
- 不把所有聊天内容当知识，必须经过提取、分类、验证。
- 跨项目学习必须显式获得 `user` 或 `public` scope，默认 `private`。

---

## 8. 与现有系统的集成点

### 8.1 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `kyrozen/learning/models.py` | 新增 `LearningRecord`、`FailureKnowledge`、`SuccessKnowledge`、`Suggestion`、`LearningEvent` |
| `kyrozen/learning/state.py` | 新增 `LearningSession`，管理学习提取进度 |
| `kyrozen/learning/agent.py` | 新增 `LearningAgent`，专用 system prompt |
| `kyrozen/learning/extractor.py` | 基于规则的 LearningEvent → LearningRecord 提取器 |
| `kyrozen/learning/suggestions.py` | 启发式建议生成器 |
| `kyrozen/tools/learning_tools.py` | `save_learning_record`、`update_learning_record`、`delete_learning_record`、`save_suggestion`、`update_suggestion_status`、`run_project_analysis` |
| `kyrozen/tools/registry.py` | 注册 Phase 9 工具 |
| `kyrozen/project/context.py` | 新增 `build_learning_context()` |
| `kyrozen/api/server.py` | 新增 `mode=learning`，新增 `/api/projects/{id}/learning/state`、`/api/projects/{id}/improvement/state` |
| `kyrozen/web/index.html` | 新增 Learning Center 和 Improvement Center 页面 |
| `kyrozen/memory/interface.py` | 可选：扩展 category 枚举文档 |

### 8.2 数据来源汇总

```
Project Workspace
   |
   +-- Project (goal, stage, risks)
   +-- Decision (decision, reason, alternatives)
   +-- Artifact (type, content, version, change_reason)
   |     +-- problem_brief
   |     +-- market_research_report
   |     +-- product_brief / prd / solution_comparison
   |     +-- technical_plan / feature_implementation / test_report / deployment_guide
   |     +-- hardware_architecture / component_spec / bom / wiring_design / firmware_project / assembly_step / hardware_debug_record
   |     +-- test_plan / test_case / test_result / user_feedback / validation_report / iteration_plan
   |
   +-- Task (title, status, result, errors)
   |
   v
LearningExtractor + LearningAgent
   |
   v
Memory Backend (LearningRecord / FailureKnowledge / SuccessKnowledge)
   |
   v
SuggestionGenerator
   |
   v
Suggestion → User Review → Learning Feedback Loop
```

---

## 9. 测试策略

Phase 9 测试需要覆盖：

### 9.1 失败学习（Case 1）

- 输入：ESP32 项目 + `test_result`（传感器通信错误 / GPIO 冲突）
- 验证：
  - 提取 `FailureKnowledge`。
  - 在后续类似项目中，Kyrozen 能提示该 GPIO 冲突风险。

### 9.2 成功复用（Case 2）

- 输入：项目 A 的 `validation_report.conclusion=pass` + `technical_plan`。
- 验证：
  - 提取 `SuccessKnowledge`。
  - 项目 B 有类似需求时，Kyrozen 推荐过去验证过的架构。

### 9.3 错误记忆删除（Case 3）

- 输入：用户删除一条错误学习记录。
- 验证：
  - 该记录从 Memory 中移除。
  - 后续建议不再引用该记录。

---

## 10. 关键设计决策

1. **不新建独立数据库**：Phase 9 的学习记录复用现有 `MemoryInterface`（JsonFileMemory），通过扩展 metadata 承载分类、可信度、权限等字段。未来可迁移到向量数据库。
2. **不自动修改项目**：所有建议必须通过 `Suggestion` 呈现给用户，用户确认后才由对应 Phase 的工具执行修改。
3. **默认私有**：所有学习记录默认 `scope=private`，跨项目复用需要用户显式提升为 `user` 或 `public`。
4. **可信度过渡**：学习记录从 `unverified` 开始，经过多次验证或用户确认后可升级为 `repeatedly_verified`。
5. **与 Phase 8 强关联**：Testing 数据是 Phase 9 最重要的学习来源，尤其是 `TestResult`、`UserFeedback`、`ValidationReport`、`IterationPlan`、`HardwareDebugRecord`。

---

## 11. 下一步开发顺序

1. 实现 `kyrozen/learning/models.py` 数据模型。
2. 实现 `LearningRecord` 的 CRUD 工具（`learning_tools.py`）。
3. 实现基于规则的 `LearningExtractor`，从 Phase 8 事件中提取学习记录。
4. 实现 `SuggestionGenerator` 和主动分析工具。
5. 实现 `LearningAgent` 与 API 端点。
6. 实现 Web UI 的 Learning Center 与 Improvement Center。
7. 编写 `tests/test_learning.py` 覆盖三个测试案例。
