# Kyrozen Phase 9 交付报告：项目自学习与主动改进系统

## 1. Learning Architecture

### 目标

让 Kyrozen 能够从项目过程中积累经验、区分事实与假设、在未来类似项目中提供参考，并主动发现当前项目的改进机会。本阶段不是简单聊天记录保存，而是经过提取、分类、验证后的结构化学习。

### 架构图

```
Project Data
 |
 v
---------------------
Decisions        Tests        Failures
Successes        Feedback     Documents
 |
 v
Learning System
 | - Event Classification
 | - Learning Extraction
 | - Confidence & Verification
 | - Scope Control
 |
 v
---------------------
User Memory          Project Memory
Experience Knowledge Cross Project Knowledge
 |
 v
Suggestions
```

### 新增模块

| 文件 | 职责 |
|------|------|
| `kyrozen/learning/models.py` | `LearningRecord`、`FailureKnowledge`、`SuccessKnowledge`、`Suggestion`、`LearningEvent`、`LearningArtifactBundle` 数据模型与字段验证 |
| `kyrozen/learning/state.py` | `LearningSession` 运行时状态与阶段管理 |
| `kyrozen/learning/extractor.py` | `LearningExtractor`，从项目事件中提取学习记录、失败知识与成功经验 |
| `kyrozen/learning/suggestions.py` | `SuggestionGenerator`，基于项目产物生成主动改进建议 |
| `kyrozen/learning/agent.py` | `LearningAgent`，专用 system prompt，禁止自动修改项目 |
| `kyrozen/tools/learning_tools.py` | Phase 9 全部学习工具：保存/删除学习记录、失败/成功经验、建议提取、项目分析 |

---

## 2. Memory Classification Design

所有学习内容必须分类，并携带可信度与验证状态。

### Memory Type

| 类型 | 说明 | 示例 |
|------|------|------|
| `user_preference` | 用户长期偏好 | 用户偏好低成本方案 |
| `user_capability` | 用户能力 | 用户熟悉 Arduino |
| `project_fact` | 项目事实 | 项目使用 ESP32-S3 |
| `product_decision` | 产品决策 | 选择软件方案而非硬件方案 |
| `validated_success` | 已验证成功经验 | 某传感器方案连续运行 100 小时稳定 |
| `validated_failure` | 已验证失败经验 | 某模块存在兼容问题 |
| `external_knowledge` | 外部知识 | 某芯片官方限制 |

### Confidence Level

- `low`：单一来源或间接推断
- `medium`：有初步证据支持
- `high`：多次验证或强证据

### Verification Status

- `unverified`：未经验证
- `user_provided`：用户提供
- `externally_verified`：外部资料验证
- `experiment_verified`：实验/测试验证
- `repeatedly_verified`：多次验证

### Learning Scope

- `private`：仅属于当前项目
- `user`：可在同一用户的不同项目间复用
- `public`：可作为公共知识复用

默认 scope 为 `private`，只有用户明确允许时才提升为 `user` 或 `public`。

---

## 3. Knowledge Extraction Flow

```
Project Event
 |
 v
LearningEvent (decision / test_result / user_feedback / validation_report / iteration_plan / hardware_debug)
 |
 v
LearningExtractor
 | - _handle_test_result
 | - _handle_user_feedback
 | - _handle_validation_report
 | - _handle_iteration_plan
 | - _handle_decision
 | - _handle_hardware_debug
 |
 v
---------------------
LearningRecord    FailureKnowledge    SuccessKnowledge
 |
 v
Review (Agent / User)
 |
 v
Save to Memory (with confidence, verification_status, scope)
```

### 示例：测试失败事件

事件：`test_result` 失败，ESP32 无法连接传感器，原因为 GPIO 冲突。

提取结果：

- `FailureKnowledge`：problem="ESP32-S3 与 MPU6050 通信失败"，cause="GPIO 冲突"，solution="更换 I2C 引脚"
- `LearningRecord`：memory_type="validated_failure"，confidence="high"，verification_status="experiment_verified"

---

## 4. Suggestion System Design

`SuggestionGenerator` 在项目空闲或用户触发时主动分析项目产物，生成结构化建议。

### 建议结构

```json
{
  "suggestion": "...",
  "reason": "...",
  "evidence": ["..."],
  "impact": "...",
  "priority": "low | medium | high | critical",
  "status": "new | accepted | rejected | later | ignored",
  "category": "scope_drift | unverified_assumption | cost_optimization | tech_risk | test_gap | new_opportunity"
}
```

### 分析维度

| 维度 | 检测逻辑 | 产物依赖 |
|------|----------|----------|
| `test_gap` | PRD 需求是否在 Test Plan 中有对应测试用例 | `prd`, `test_plan` |
| `scope_drift` | Iteration Plan 是否触及 PRD 的 out-of-scope | `prd`, `iteration_plan` |
| `unverified_assumption` | PRD 有功能需求但无用户反馈 | `prd`, `user_feedback` |
| `cost_optimization` | BOM 中是否存在重复元件 | `bom` |
| `tech_risk` | 技术栈依赖过多或测试未通过 | `technical_plan`, `test_result` |
| `new_opportunity` | 其他项目中是否有可复用的成功经验或失败教训 | `learning_memory` |

### 跨项目学习

`_detect_cross_project_learning` 会查询 `scope="user"` 的学习记录，包括 `validated_success` 和 `validated_failure`：

- 成功经验：推荐已验证方案
- 失败经验：提前警告已知风险

---

## 5. Privacy and Control Design

用户对学习系统拥有完全控制权。

### 用户可执行操作

| 操作 | 实现方式 |
|------|----------|
| 查看学习内容 | Web UI Learning Center 显示 Learning Records、Failure Knowledge、Success Knowledge |
| 查看改进建议 | Web UI Improvement Center 显示 Suggestions 及其证据 |
| 修改建议状态 | `update_suggestion_status` 工具支持 accepted / rejected / later / ignored |
| 删除错误记忆 | `delete_learning_record` 工具按 memory_id 删除 |
| 限制跨项目使用 | 学习记录 `scope` 默认 `private`，仅用户允许时才提升 |
| 关闭空闲分析 | `LearningSession.idle_analysis_enabled` 可开关 |

### 隐私保护

- 私有记忆不会出现在其他项目的建议中
- 只有 `scope="user"` 或 `scope="public"` 的记录才会被跨项目复用
- 所有高风险操作必须通过 confirmation 流程

---

## 6. Web Interface

新增两个核心视图：

### Learning Center

入口：项目详情页点击「进入 Learning Center」。

界面组成：

- 左侧：学习聊天面板，支持与 Learning Agent 交互
- 右侧：Learning Records、Failure Knowledge、Success Knowledge、Improvement Suggestions

### Improvement Center

与学习面板集成，显示：

- New Suggestions
- Reason & Evidence
- Impact & Priority
- Accept / Reject 操作入口

---

## 7. Test Results

运行全部测试：

```bash
python3 -m pytest tests/ -q
```

结果：**244 passed, 3 warnings**

Phase 9 新增 6 个测试（`tests/test_learning.py`），覆盖：

- `LearningExtractor` 从 `test_result` 失败事件中正确提取 `FailureKnowledge` 与 `LearningRecord`
- `SaveFailureKnowledgeTool` 保存失败知识，`SuggestionGenerator` 在类似项目中提示过往失败经验
- `SaveSuccessKnowledgeTool` 保存成功经验，跨项目推荐已验证方案
- `DeleteLearningRecordTool` 删除错误记忆后，该记忆不再存在
- `LearningRecord` 字段枚举验证（memory_type、confidence、verification_status、scope）
- 私有学习记录不会被跨项目复用

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
| Phase 9 | `test_learning.py` | Learning, Proactive Improvement |

### 警告说明

3 个警告均不影响功能：

1. `fastapi/testclient.py` 的 `StarletteDeprecationWarning`：提示使用 `httpx2`，不影响测试执行。
2. `PytestCollectionWarning: cannot collect test class 'TestingArtifactBundle'`：dataclass 有 `__init__`，pytest 不会识别为测试类，属于预期行为。
3. `PytestCollectionWarning: cannot collect test class 'TestingSession'`：同上。

---

## 8. Limitations

本阶段明确不实现：

- 完整团队协作知识库
- 企业级知识中心与权限管理
- 制造供应链学习
- 自动修改项目内容（代码、BOM、PRD、硬件）
- 未经用户确认将聊天内容直接当作学习记录
- 未经权限控制泄露项目隐私

上述限制属于 **Phase 10** 或未来扩展。

---

## 9. 如何运行

```bash
python3 -m uvicorn kyrozen.api.server:app --host 127.0.0.1 --port 8000 --reload
```

打开 http://127.0.0.1:8000，创建项目后点击「进入 Learning Center」，即可查看学习记录、失败/成功经验，并与 Learning Agent 交互生成改进建议。

---

*Commit 已推送至 origin/main。*
