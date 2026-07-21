# Kyrozen Phase 3 实施计划：问题发现与问题定义系统

## 目标

让 Kyrozen 具备**从模糊想法中发现真实问题**的能力：
- 不默认用户想法正确
- 通过自适应提问逐步理解 Who / Where / What / Why
- 生成结构化的 **Problem Brief Artifact**
- 所有内容绑定到 Project Workspace，支持重新打开后继续

本阶段不做：市场调研、产品设计、技术方案、写代码、推荐硬件。

---

## Phase 2 Integration Analysis

### 可直接复用的模块

| 模块 | 用途 | Phase 3 使用方式 |
|------|------|------------------|
| `kyrozen.core.agent.BaseAgent` | Agent 运行时 | `ProblemDiscoveryAgent` 继承 `BaseAgent`，复用工具调用、任务管理、确认流程 |
| `kyrozen.core.task.TaskManager` | 任务持久化 | 所有 Problem Discovery 对话作为 project task 保存，自动绑定 `project_id` |
| `kyrozen.project.ProjectManager` | 项目 CRUD | 创建/读取项目，保存 Problem Brief Artifact 和 Decision |
| `kyrozen.project.Artifact` | 产物模型 | 用 `type="problem_brief"` 保存 Problem Brief |
| `kyrozen.project.Decision` | 决策记录 | 保存「继续研究 / 信息不足 / 已有足够方案 / 问题不清 / 不适合做产品」等判断 |
| `kyrozen.memory.JsonFileMemory` + `ProjectMemory` | 项目级记忆 | 保存用户回答、追问历史、证据标记 |
| `kyrozen.project.ProjectContextBuilder` | 上下文注入 | 进入 Problem Discovery 时注入项目当前状态、已有 Problem Brief、最近记忆 |
| `kyrozen.tools.project_tools` | 项目状态/决策工具 | Agent 可调用 `update_project` / `record_decision`（仅在用户明确要求时） |
| `kyrozen.api.server` FastAPI | Web API | 新增 `/api/projects/{id}/problem-discovery/*` 端点，复用 `/api/chat` |
| `kyrozen.web.index.html` | Web UI | 新增 Problem Discovery 视图：已了解信息 / 未解问题 / 实时 Problem Brief |

### 需要扩展的模块

| 模块 | 扩展点 |
|------|--------|
| `kyrozen.project.project.py` | Artifact 已支持任意 `type` 和 JSON `content`，无需改结构 |
| `kyrozen.project.manager.py` | 增加 `get_latest_artifact(project_id, type)` 方便读取当前 Problem Brief |
| `kyrozen.core.agent.BaseAgent` | 子类 `ProblemDiscoveryAgent` 覆盖 `_build_system_prompt()` 和问题发现专属指令 |
| `kyrozen.tools` | 新增 `problem_discovery_tools`：`save_problem_brief`、`record_evidence`、`assess_confidence` |
| `kyrozen.api.server` | 新增获取/保存 Problem Brief、切换阶段到 `problem_discovery` 的端点 |
| `kyrozen.web.index.html` | 新增 Problem Discovery Mode 视图 |

### 不需要重新开发的模块

- 不重写 Core
- 不重写 Memory Interface
- 不重写 Task Manager
- 不重写 Permission Manager

---

## 目录结构变化

```
Kyrozen/
├── kyrozen/
│   ├── discovery/                     # 新增
│   │   ├── __init__.py
│   │   ├── agent.py                   # ProblemDiscoveryAgent
│   │   ├── brief.py                   # ProblemBrief 数据类 + schema
│   │   ├── evidence.py                # Evidence / Confidence 模型
│   │   ├── question_engine.py         # Adaptive Question System
│   │   └── state.py                   # DiscoverySession 状态机
│   ├── project/
│   │   ├── manager.py                 # 扩展 get_latest_artifact
│   │   └── context.py                 # 扩展 discovery 上下文
│   ├── tools/
│   │   └── discovery_tools.py         # 新增：save_problem_brief / record_evidence
│   ├── api/server.py                  # 扩展 Problem Discovery 端点
│   └── web/index.html                 # 扩展 Discovery 视图
├── tests/test_discovery.py            # 新增
└── PHASE3_DELIVERY_REPORT.md          # 最终交付
```

---

## Problem Brief Artifact 数据结构

```json
{
  "title": "AI 跑步音乐设备",
  "target_user": "有跑步习惯、希望运动不被音乐操作打断的人",
  "scenario": "户外/健身房跑步过程中",
  "surface_problem": "跑步时音乐节奏和心情/步伐不匹配，手动切歌分心",
  "deep_need": "希望运动全程保持专注和沉浸感，不被设备操作打断",
  "current_solution": "手动选择歌单或手动切歌",
  "current_solution_problem": "需要掏出手机/手表操作，破坏运动节奏",
  "frequency": "每次跑步",
  "impact": "影响运动体验和连续性",
  "unknown_assumptions": [
    {"claim": "很多跑者都有这个问题", "source": "user_statement", "verified": false}
  ],
  "opportunity_direction": "探索根据运动状态自动调整音乐的设备或服务",
  "confidence": "medium",
  "confidence_reason": "基于单一用户描述，需要更多跑者验证",
  "decision": "need_more_information",
  "decision_reason": "问题方向有价值，但需验证假设"
}
```

字段说明：
- `title`: 问题标题
- `target_user`: 目标用户
- `scenario`: 发生场景
- `surface_problem`: 表面问题
- `deep_need`: 深层需求
- `current_solution`: 当前解决方法
- `current_solution_problem`: 当前方法不足
- `frequency`: 发生频率
- `impact`: 影响程度
- `unknown_assumptions`: 未验证假设列表
- `opportunity_direction`: 机会方向
- `confidence`: 可信度 `low` / `medium` / `high`
- `confidence_reason`: 可信度说明
- `decision`: 问题层判断：`continue_research` / `need_more_information` / `existing_solution_enough` / `problem_not_clear` / `not_suitable_for_product`
- `decision_reason`: 判断理由

---

## 系统架构

```
User Input (模糊想法)
       |
       v
+-------------------------+
| ProblemDiscoveryAgent   |  <-- 继承 BaseAgent，专用 system prompt
|                         |
| - Question Engine       |  <-- 决定下一步问什么
| - Brief Generator       |  <-- 信息足够时生成/更新 Problem Brief
| - Evidence Tracker      |  <-- 标记每条信息的来源和可信度
| - Confidence Assessor   |  <-- 评估整体可信度
| - Decision Recommender  |  <-- 给出问题层判断
+-------------------------+
       |
       v
Kyrozen Core (BaseAgent runtime)
       |
       v
+-------------------------+
| Project Workspace       |
| - Artifact: problem_brief
| - Memory: Q&A / Evidence
| - Decision: problem decision
| - Task: discovery task
+-------------------------+
```

### Agent 工作方式

1. 每次用户发送一条消息，创建一个 discovery task
2. 将项目上下文 + 当前 Problem Brief + 最近问答记忆注入 prompt
3. Agent 判断：
   - 信息是否足够生成/更新 Problem Brief？
   - 是否需要继续提问？
   - 应该问哪个维度的问题？
4. 如果需要保存 Brief / Evidence / Decision，通过 tool call 写入 Project Workspace
5. 返回给用户：回答 + 下一步问题 + 当前 Brief 预览

### 自适应提问策略

禁止一次性抛出大量问题。采用「最小下一步问题」策略：

```
用户：我想做智能耳机
Agent：你为什么想做这个耳机？目前遇到了什么问题？

用户：跑步时手动切歌很麻烦
Agent：你现在怎么解决这个问题？是用手机还是手表？

用户：用手机，每次都要掏出来
Agent：这个问题每周会出现几次？影响的主要是跑步体验还是安全？
```

Question Engine 维护一个「待探索维度」集合，每次选择最缺失的维度提问。

---

## Project Integration

### 1. 绑定项目

- 进入 Problem Discovery 时，项目 `current_stage` 保持 `problem_discovery`
- 所有 task 的 `project_id` 为当前项目
- 所有 memory 保存到项目 `memory.json`
- 所有 artifact 保存到 SQLite `artifacts` 表

### 2. Memory 使用

保存三类记忆：
- `category="discovery_qa"`: 用户回答的内容
- `category="discovery_evidence"`: 证据标记
- `category="discovery_brief"`: 历次 Problem Brief 版本

### 3. Artifact 使用

- `type="problem_brief"`
- `title="Problem Brief"`
- `content` 为 JSON 字符串化的 Problem Brief
- 每次更新自动 bump version，保留历史

### 4. Decision 使用

当 Agent 判断问题方向时，保存 Decision：
- `decision`: problem decision 结果
- `reason`: 判断理由
- `source`: "agent"

### 5. Context Builder 扩展

进入 discovery 聊天时，上下文包括：
- 项目基本信息
- 当前 Problem Brief（如果存在）
- 最近 discovery 问答
- 未验证假设
- 当前阶段说明

---

## Conversation Flow

```
用户创建项目 "AI 跑步设备"
       |
       v
项目 current_stage = "problem_discovery"
       |
       v
用户输入："我跑步的时候感觉音乐不适合我的状态"
       |
       v
Agent: "谢谢你分享。想先了解几点：
        1. 你现在是怎么解决这个问题的？
        2. 这个问题通常发生在什么场景（户外跑/健身房）？"
       |
       v
用户回答...
       |
       v
Agent 保存 Q&A 到 Memory，更新 Evidence
       |
       v
信息足够后，Agent 调用 save_problem_brief tool
生成 Problem Brief Artifact v1
       |
       v
Agent: "根据目前了解，问题可以总结为...
        [显示 Problem Brief 预览]
        下一步建议：继续访谈 2-3 位跑者验证‘很多跑者都有这个问题’的假设。"
       |
       v
用户关闭页面后重新打开
       |
       v
ProjectContextBuilder 读取当前 Problem Brief 和 Memory
Agent 继续追问 / 更新 Brief
```

---

## 新增工具

| 工具 | action | 用途 |
|------|--------|------|
| `save_problem_brief` | `save` | 保存/更新 Problem Brief Artifact |
| `record_evidence` | `record` | 记录一条信息的来源和可信度 |
| `assess_confidence` | `assess` | 评估当前整体可信度 |
| `record_problem_decision` | `record` | 记录问题层判断 |

---

## Web Interface 扩展

在 Project Detail 页面增加按钮：「进入 Problem Discovery」。

Problem Discovery 视图显示：
1. 左侧：聊天区域
2. 右侧：
   - 当前已了解信息（Who / Where / What / Why）
   - 未解决问题 / 下一步问题
   - Problem Brief 实时预览
   - 未验证假设列表

---

## 开发顺序

1. `kyrozen/discovery/brief.py` — ProblemBrief 数据结构与 validation
2. `kyrozen/discovery/evidence.py` — Evidence / Confidence 模型
3. `kyrozen/discovery/question_engine.py` — 自适应问题引擎
4. `kyrozen/discovery/state.py` — DiscoverySession 状态机
5. `kyrozen/discovery/agent.py` — ProblemDiscoveryAgent
6. `kyrozen/tools/discovery_tools.py` — save_problem_brief / record_evidence 等
7. `kyrozen/project/manager.py` — 扩展 get_latest_artifact
8. `kyrozen/project/context.py` — 扩展 discovery 上下文
9. `kyrozen/api/server.py` — 新增 discovery 端点
10. `kyrozen/web/index.html` — Discovery 视图
11. `tests/test_discovery.py` — 单元/集成测试
12. `PHASE3_DELIVERY_REPORT.md` — 交付报告 + commit/push

---

## 测试计划

| 测试 | 期望 |
|------|------|
| Case 1: "我觉得房间很吵" | 生成问题分析，target_user/scenario/problem 有值 |
| Case 2: "我想做一个AI眼镜" | Agent 不会直接设计眼镜，而是追问为什么需要 |
| Case 3: "我想每天提醒自己喝水" | Agent 会考虑手机闹钟等现有简单方案 |
| Case 4: 多轮对话 | 每次只问 1-2 个问题，逐步填充 Brief |
| Case 5: 重新打开项目 | Problem Brief 和问答历史可恢复 |

---

## 限制

- 本阶段不实现：市场调研、竞品分析、GitHub/专利/评论搜索
- 本阶段不实现：PRD、MVP、技术方案、BOM
- 本阶段不自动鼓励所有项目：会识别「已有简单方案」「问题不清」等情况
- 证据验证依赖用户输入，不做外部数据爬取

---

*等待确认后开始实现。*
