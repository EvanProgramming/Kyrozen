# Phase 4 Integration Analysis

## 1. Phase 4 输出回顾

### 1.1 Market Research Report 存储方式

- **位置**：Project Workspace 的 `Artifact` 表
- **类型**：`market_research_report`
- **标题**：`Market Research Report`
- **读取方式**：
  ```python
  pm.get_latest_artifact(project_id, "market_research_report", title="Market Research Report")
  ```
- **内容格式**：JSON 字符串，可反序列化为 `MarketResearchReport`
- **关键字段**：
  - `problem_summary`：问题摘要
  - `market_status`：市场现状
  - `competitors`：竞品列表
  - `open_source_projects`：开源项目
  - `user_feedback`：用户反馈
  - `alternative_solutions`：替代方案
  - `technology_routes`：可能技术路线
  - `market_gap`：市场缺口
  - `risks`：风险列表
  - `recommendation`：机会判断（OPPORTUNITY_DECISIONS 枚举）
  - `sources`：来源证据

### 1.2 Problem Brief 存储方式

- **位置**：Project Workspace 的 `Artifact` 表
- **类型**：`problem_brief`
- **标题**：`Problem Brief`
- **读取方式**：
  ```python
  pm.get_latest_artifact(project_id, "problem_brief", title="Problem Brief")
  ```
- **关键字段**：
  - `title`：问题标题
  - `target_user`：目标用户
  - `scenario`：场景
  - `surface_problem`：表面问题
  - `deep_need`：深层需求
  - `current_solution`：当前解决方案
  - `current_solution_problem`：当前方案缺陷
  - `frequency` / `impact`：频率与影响
  - `opportunity_direction`：机会方向
  - `unknown_assumptions`：未验证假设
  - `confidence` / `decision`：可信度与问题层决策

### 1.3 Decision 系统

- **位置**：Project Workspace 的 `Decision` 表
- **保存方式**：
  ```python
  pm.add_decision(
      project_id=project_id,
      decision="continue_development",
      reason="...",
      alternatives=[...],
      rejected_reasons={...},
      source="agent",
  )
  ```
- **Phase 4 用途**：保存机会判断（`record_opportunity_decision`）
- **Phase 5 扩展**：保存产品方案决策（solution choice、MVP scope 等）

### 1.4 Project Context 传递方式

`ProjectContextBuilder` 已支持三种上下文：

| 方法 | 用途 |
|------|------|
| `build()` | 通用项目上下文 |
| `build_discovery_context()` | Problem Discovery 模式 |
| `build_research_context()` | Market Research 模式 |

Phase 5 将新增：

```python
build_planning_context(project: Project) -> str
```

注入内容：
- Problem Brief（来自 `problem_brief` artifact）
- Market Research Report（来自 `market_research_report` artifact）
- 最近的产品规划相关记忆（`category="planning"`）
- 最近的决策记录

---

## 2. Product Planning Agent 如何连接 Phase 4

### 2.1 输入

| 输入来源 | 获取方式 | 用途 |
|----------|----------|------|
| Problem Brief | `pm.get_latest_artifact(project_id, "problem_brief")` | 明确要解决的真实问题 |
| Market Research Report | `pm.get_latest_artifact(project_id, "market_research_report")` | 了解市场机会、竞品、风险 |
| 用户消息 | `/api/chat` request | 引导 Agent 进行规划或确认 |
| 历史规划记忆 | `ProjectMemory.query(category="planning")` | 保持多轮对话连贯 |

### 2.2 输出

| 输出 | 保存方式 | Artifact 类型 |
|------|----------|---------------|
| Product Brief | `pm.save_artifact(type="product_brief", title="Product Brief")` | `product_brief` |
| PRD | `pm.save_artifact(type="prd", title="Product Requirements Document")` | `prd` |
| Solution Comparison | `pm.save_artifact(type="solution_comparison", title="Solution Comparison")` | `solution_comparison` |
| MVP Scope | 保存在 Product Brief / PRD 内，同时作为 Decision 记录 | `product_brief` / `prd` + `decision` |
| Product Decision | `pm.add_decision(..., source="agent")` | `decision` |

### 2.3 调用链

```
User enters Product Planning Mode
       |
       v
/api/chat (mode="planning")
       |
       v
ProductPlanningAgent
       |
       v
ProjectContextBuilder.build_planning_context()
       |-- loads Problem Brief
       |-- loads Market Research Report
       |-- loads recent planning memories
       |-- loads recent decisions
       |
       v
Agent decides next step:
  - define_product_goal
  - define_target_user
  - design_user_journey
  - define_features
  - define_mvp
  - generate_solutions
  - compare_solutions
  - save_product_brief
  - save_prd
  - record_product_decision
       |
       v
Tool execution via ToolRegistry
       |
       v
Project Workspace (artifacts + decisions)
```

---

## 3. Project Stage 映射

Phase 5 对应 `PROJECT_STAGES` 中的：

- `product_definition`：定义 Product Goal、Target User、Features、MVP
- `solution_design`：生成并比较多个 Solution，做出方案决策

Agent 可在保存 Product Brief 或做出方案决策后，通过 `update_project` 工具将 `current_stage` 推进到 `solution_design` 或 `development`（但需用户显式确认）。

---

## 4. 与现有 ToolRegistry 的集成

Phase 5 将在 `get_default_registry()` 中新增以下工具：

| 工具 | 职责 |
|------|------|
| `save_product_brief` | 保存 Product Brief artifact |
| `save_prd` | 保存 PRD artifact |
| `save_solution_comparison` | 保存方案比较 artifact |
| `record_product_decision` | 保存产品方案决策 |
| `update_project_stage` | （复用 `update_project`）推进项目阶段 |

---

## 5. 与 Web UI 的集成

- Project Detail 新增按钮：**进入 Product Planning**
- 新增 `/#/projects/{id}/planning` 路由
- 视图布局参考 Market Research：
  - 左侧：聊天区
  - 右侧：
    - Product Goal
    - Target User
    - Features（Must/Should/Could/Not Now）
    - MVP Scope
    - Solutions 比较
    - Decisions

---

## 6. 关键约束承袭

- **不进入开发阶段**：Agent system prompt 禁止讨论技术架构、编程语言、数据库设计、电路设计、芯片选择
- **不替用户做重大决策**：方案比较后必须呈现推荐、理由、风险，等待用户确认
- **不自动接受全部需求**：当用户提出过多功能时，Agent 必须分析并缩小到 MVP
- **所有重大决策必须保存**：通过 `record_product_decision` 记录选择、原因、被放弃方案
