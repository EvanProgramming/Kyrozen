# Kyrozen Phase 2 交付报告

## 1. Project Workspace Architecture

Phase 2 将 Kyrozen 从「单次任务执行 Agent」升级为「长期项目 Agent」。基本单位从 Conversation 变为 Project。

```
Browser
   |
Kyrozen Web Interface  (kyrozen/web/index.html)
   |
Project API            (kyrozen/api/server.py)
   |
Project Workspace System
   ├── Project Entity    (kyrozen/project/project.py)
   ├── SQLite Database   (kyrozen/project/db.py)
   ├── Project Manager   (kyrozen/project/manager.py)
   └── Context Builder   (kyrozen/project/context.py)
   |
Kyrozen Core
   ├── BaseAgent         (kyrozen/core/agent.py)
   ├── TaskManager       (kyrozen/core/task.py)
   ├── MemoryInterface   (kyrozen/memory/interface.py)
   ├── JsonFileMemory    (kyrozen/memory/scoped.py)
   ├── ProjectMemory     (kyrozen/memory/scoped.py)
   └── Tool Registry     (kyrozen/tools/registry.py)
   |
Storage
   ├── kyrozen.db        (projects / tasks / decisions / artifacts)
   └── projects/{id}/
       ├── memory.json
       ├── files/
       └── documents/
```

### 核心设计原则

- **Project 为中心**：所有任务、决策、产物、记忆都关联到 project_id。
- **不修改 Core**：Phase 1 的 `BaseAgent`、`PermissionManager`、`Task` 等核心类保持不变，仅做必要扩展（如 `Task.project_id`）。
- **上下文注入**：用户进入项目聊天时，自动把项目目标、阶段、最近任务、决策、记忆注入到模型输入中。
- **持久化**：项目元数据、任务、决策、产物保存在 SQLite；项目级 Memory 保存在 `{project_id}/memory.json`。

---

## 2. Database / Storage Design

### 2.1 SQLite Schema

数据库文件：`{workspace_root}/kyrozen.db`

#### projects
| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 项目 ID，例如 `proj_188c9796` |
| name | TEXT | 项目名称 |
| description | TEXT | 项目描述 / 初始想法 |
| goal | TEXT | 项目目标 |
| status | TEXT | active / paused / completed / archived |
| current_stage | TEXT | problem_discovery / market_research / ... |
| next_steps | TEXT | 下一步计划 |
| risks | TEXT (JSON) | 风险列表 |
| created_at | TEXT | 创建时间 ISO |
| updated_at | TEXT | 更新时间 ISO |

#### tasks
| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 任务 ID |
| project_id | TEXT FK → projects(id) ON DELETE CASCADE | 所属项目 |
| title | TEXT | 任务标题 |
| description | TEXT | 任务描述 |
| status | TEXT | pending / running / waiting_confirmation / completed / failed / cancelled |
| steps | TEXT (JSON) | 任务步骤 |
| result | TEXT (JSON) | 最终结果 |
| errors | TEXT (JSON) | 错误列表 |
| created_at / updated_at | TEXT | 时间戳 |

#### decisions
| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 决策 ID |
| project_id | TEXT FK | 所属项目 |
| decision | TEXT | 决策内容 |
| reason | TEXT | 决策原因 |
| alternatives | TEXT (JSON) | 备选方案 |
| rejected_reasons | TEXT (JSON) | 被拒绝方案及原因 |
| source | TEXT | agent / user |
| timestamp | TEXT | 决策时间 |

#### artifacts
| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 产物 ID |
| project_id | TEXT FK | 所属项目 |
| type | TEXT | PRD / BOM / Test Report 等 |
| title | TEXT | 产物标题 |
| content | TEXT | 产物内容 |
| version | INTEGER | 版本号 |
| change_reason | TEXT | 修改原因 |
| created_at / updated_at | TEXT | 时间戳 |

### 2.2 文件存储

每个项目拥有独立目录：

```
projects/{project_id}/
├── memory.json      # 项目级 Memory（JsonFileMemory）
├── files/           # 项目文件（预留）
└── documents/       # 产物文档（预留）
```

### 2.3 关系图

```
Project 1 ──< Task
         ──< Decision
         ──< Artifact
         ──< Memory (via project_id metadata)
```

- 任务、决策、产物通过外键级联删除。
- Memory 通过 `project_id` metadata 字段过滤，不强制外键，以支持更灵活的写入场景。

---

## 3. Web Changes

`kyrozen/web/index.html` 从单一聊天界面扩展为三个视图，使用 hash 路由：

| 路由 | 视图 | 功能 |
|------|------|------|
| `/#/projects` | Project List | 显示所有项目卡片（名称、目标、阶段、状态、更新时间），支持创建新项目 |
| `/#/projects/{id}` | Project Detail | 显示项目 Goal、Stage、Status、Next Steps、最近任务 / 决策 / 产物，可进入聊天 |
| `/#/projects/{id}/chat` | Project Chat | 项目级聊天，发送消息自动附带 `project_id` |

### 新增 UI 组件

- 项目卡片（`.project-card`）
- 创建项目表单（`.form-card`）
- 项目详情区块（`.section`）
- 任务 / 决策 / 产物列表（`.item-list` / `.item`）

### 保留功能

- 实时任务状态轮询
- 任务步骤面板
- 高风险操作确认框
- Health 检查

---

## 4. Integration Report

### 4.1 Core（BaseAgent）

- **未修改** `BaseAgent` 主循环。
- 仅利用 `BaseAgent.run(user_input, project_id=...)` 已有的 `project_id` 参数，使创建的任务自动关联项目。
- `BaseAgent` 运行结束后会把 user / agent 消息保存到当前 `agent.memory`，当在项目中时 `agent.memory` 被替换为 `ProjectMemory`。

### 4.2 Task Manager

- `Task` 类已新增 `project_id` 字段，并在 `to_dict` / `from_dict` 中序列化。
- `TaskManager` 新增可选 `db` 参数：提供 `KyrozenDatabase` 时，任务写入 SQLite 而不是 JSON 文件。
- API 层统一使用 `TaskManager(db=_db)`，所有任务自动持久化到数据库。

### 4.3 Memory

- `InMemoryMemory.query()` 扩展为支持 `**filters`，兼容项目级过滤。
- 新增 `JsonFileMemory`：文件持久化 Memory，支持 category / query / metadata filters。
- 新增 `ProjectMemory`：包装任意 `MemoryInterface`，自动附加 `project_id`，确保项目隔离。

### 4.4 Logs

- `BaseAgent.run` 已在日志中记录 `project_id`。
- 未新增独立项目日志文件，后续阶段可按需扩展。

### 4.5 Tools

- 新增 `update_project` 工具：Agent 可更新项目阶段、下一步、目标、风险。
- 新增 `record_decision` 工具：Agent 可记录决策及备选方案拒绝原因。
- 工具通过 `get_default_registry(project_manager)` 注册到 Agent。

### 4.6 Context Injection

`ProjectContextBuilder.build(project)` 组装以下内容并注入用户消息前：

1. 项目基本信息（名称、目标、阶段、状态、下一步、风险）
2. 最近任务（默认 5 条）
3. 最近决策（默认 5 条）
4. 相关项目记忆（按项目名称关键词过滤）
5. 可用阶段提示 + `update_project` 工具提示

---

## 5. Test Results

新增 5 个测试文件，共 32 个测试：

| 文件 | 测试数 | 覆盖内容 |
|------|--------|---------|
| `tests/test_project.py` | 12 | Project / Decision / Artifact 模型，ProjectManager CRUD、决策、产物版本、项目隔离 |
| `tests/test_project_db.py` | 4 | SQLite 持久化、任务 project_id 持久化、级联删除 |
| `tests/test_project_context.py` | 4 | Context Builder 组装项目信息、任务、决策、记忆 |
| `tests/test_json_memory.py` | 5 | JsonFileMemory save/query/update/delete/persist，ProjectMemory 隔离 |
| `tests/test_api_project.py` | 7 | Project API 端点、聊天上下文注入、多项目隔离 |

### 运行结果

```bash
.venv/bin/python -m pytest tests/ -v
# 70 passed, 1 warning in 0.62s
```

- Phase 1 原有 38 个测试全部通过。
- Phase 2 新增 32 个测试全部通过。
- 总计 **70 个测试通过**。

### 关键验证场景

- ✅ 创建项目：智能跑步设备
- ✅ 保存项目元数据到 SQLite
- ✅ 关闭重新打开后项目信息可恢复
- ✅ 项目上下文恢复（目标、阶段、任务、决策、记忆）
- ✅ 多项目隔离（任务、决策、记忆互不干扰）
- ✅ 项目聊天绑定 project_id

---

## 6. Limitations

Phase 2 仅建立基础设施，以下功能明确**未实现**：

- Problem Discovery Agent
- Market Research Agent
- Product Agent
- Hardware Agent
- Software Agent
- 自动生成 Market Research Report / PRD / BOM / Test Report 等产品文档
- 产品画布、决策中心、采购中心、制作模式等复杂 UI
- 全局 Memory 与用户 Memory 的完整分类管理（当前仅支持 Global / Project 两级，User Memory 接口已预留）
- 项目文件 / documents 目录的自动管理（目录已预留，未实现上传/同步逻辑）

---

## 7. 文件变更清单

### 新增
- `kyrozen/project/__init__.py`
- `kyrozen/project/project.py`
- `kyrozen/project/db.py`
- `kyrozen/project/manager.py`
- `kyrozen/project/context.py`
- `kyrozen/memory/scoped.py`
- `kyrozen/tools/project_tools.py`
- `tests/test_project.py`
- `tests/test_project_db.py`
- `tests/test_project_context.py`
- `tests/test_json_memory.py`
- `tests/test_api_project.py`
- `PHASE2_DELIVERY_REPORT.md`

### 修改
- `kyrozen/config/settings.py`：新增 `db_path`、`projects_dir`、`project_dir()`、`project_memory_path()`
- `kyrozen/core/task.py`：新增 `project_id` 字段；`TaskManager` 支持 SQLite db
- `kyrozen/memory/interface.py`：`InMemoryMemory.query()` 支持 metadata filters
- `kyrozen/memory/__init__.py`：导出 `JsonFileMemory`、`ProjectMemory`
- `kyrozen/tools/registry.py`：注册 `UpdateProjectTool`、`RecordDecisionTool`
- `kyrozen/api/server.py`：新增 Project API 端点、项目上下文注入
- `kyrozen/web/index.html`：项目列表 / 详情 / 聊天多视图

---

*交付日期：2026-07-21*
