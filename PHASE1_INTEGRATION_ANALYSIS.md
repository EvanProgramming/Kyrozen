# Phase 1 Integration Analysis

## 1. Phase 1 当前架构总览

```
Browser
   ↓
kyrozen/web/index.html  (单页测试控制台)
   ↓
kyrozen/api/server.py   (FastAPI)
   ↓
BaseAgent + TaskManager + MemoryInterface + ToolRegistry + PermissionManager
   ↓
kyrozen_tasks.json  /  logs/  /  InMemoryMemory
```

Phase 1 已经实现了一个可运行的 Agent Core：
- 接收用户消息
- 调用 LLM
- 解析并执行工具
- 多轮循环
- 返回结果
- 记录任务与日志

但当前所有任务都是全局的、一次性的，没有 Project 概念。

---

## 2. 各模块可复用性分析

### 2.1 BaseAgent —— 可直接复用，需要扩展上下文注入

**当前状态：**
- 文件：`kyrozen/core/agent.py`
- 功能：`_build_system_prompt()`、`run()`、工具调用解析、执行、多轮循环
- `run(user_input, confirmed=False)` 只接收用户当前消息

**如何使用：**
- 不需要修改核心循环
- 需要在 `run()` 之前，把 Project Context 注入到 system prompt 或 user message 中
- 建议新增 `run_with_context(project_context, user_input, confirmed=False)`，内部把 context 拼接到 prompt

**需要扩展：**
- `BaseAgent` 本身不感知 Project
- 需要在调用处（API 层）组装 Context

---

### 2.2 TaskManager / Task —— 需要扩展 project_id

**当前状态：**
- 文件：`kyrozen/core/task.py`
- `Task` 字段：`id`, `title`, `description`, `status`, `steps`, `result`, `errors`, `created_at`, `updated_at`
- `TaskManager` 用一个全局 JSON 文件 `kyrozen_tasks.json` 存储所有任务

**如何使用：**
- `Task` 数据模型稳定，可以直接复用
- 需要新增 `project_id` 字段，使任务属于项目
- `TaskManager` 当前按全局文件存储，Phase 2 需要按项目隔离存储

**需要扩展：**
- `Task.__init__` 增加 `project_id: str | None = None`
- `Task.to_dict() / from_dict()` 增加 project_id 序列化
- 不建议继续用单个 `kyrozen_tasks.json`
- 建议改为每个项目一个 `workspace/projects/{project_id}/tasks.json`

---

### 2.3 MemoryInterface —— 需要增加 project_id 过滤

**当前状态：**
- 文件：`kyrozen/memory/interface.py`
- 接口：`save(category, content, **metadata)`、`query(...)`、`update(...)`、`delete(...)`
- 实现：`InMemoryMemory`，纯内存，按 category + 关键词过滤

**如何使用：**
- 接口可以直接复用
- `save()` 已经支持 `**metadata`，可以直接传入 `project_id`
- `query()` 可以通过 metadata 过滤项目级 Memory

**需要扩展：**
- 增加 `ProjectMemory` 或 `ScopedMemory` 包装器，简化项目级查询
- 当前 InMemoryMemory 是进程级内存，Web 重启会丢失
- Phase 2 仍可用 InMemoryMemory 做测试，但建议同时实现 `JsonFileMemory` 作为持久化过渡

---

### 2.4 ToolRegistry / Tools —— 直接复用

**当前状态：**
- 文件：`kyrozen/tools/base.py`、`registry.py`、各类 tool
- 已实现：file_read、file_write、list_dir、find_files、terminal、git

**如何使用：**
- 完全不需要修改
- Phase 2 的 Project Workspace 会新增工作目录，工具执行路径可以基于项目 workspace

**需要扩展：**
- 后续可以增加 Web Search Tool，但 Phase 2 不实现

---

### 2.5 PermissionManager —— 直接复用

**当前状态：**
- 文件：`kyrozen/core/permission.py`
- strict / permissive 模式
- 高风险操作需要确认

**如何使用：**
- 完全复用
- Project Workspace 不会改变权限判断逻辑

---

### 2.6 KyrozenLogger —— 需要增加 project_id 字段

**当前状态：**
- 文件：`kyrozen/logs/logger.py`
- `LogEntry` 有 `event_type`, `message`, `task_id`, `metadata`, `timestamp`
- 写入 `logs/kyrozen_YYYYMMDD.log` 和 `logs/kyrozen_events.jsonl`

**如何使用：**
- 直接复用
- 每次 `log(...)` 传入 `project_id` 到 metadata 即可

**需要扩展：**
- `LogEntry` 可以增加显式 `project_id` 字段，便于查询
- 项目级日志可以写入 `workspace/projects/{project_id}/logs/`

---

### 2.7 KyrozenConfig —— 需要增加 workspace 路径配置

**当前状态：**
- 文件：`kyrozen/config/settings.py`
- 有 `workspace_root`、`task_store_path`、`chroma_path`、`log_level` 等

**如何使用：**
- 直接复用
- 建议新增 `project_store_path` 或统一使用 `workspace_root` 下的 `projects/` 目录

**需要扩展：**
- 增加 `projects_dir` 路径，默认 `./workspace/projects`
- 增加 `artifacts_dir` 路径，默认 `./workspace/artifacts`

---

### 2.8 Web API (server.py) —— 需要大量新增路由

**当前状态：**
- 文件：`kyrozen/api/server.py`
- 端点：`/api/chat`、`/api/tasks`、`/api/tasks/{id}`、`/api/tasks/{id}/confirm`、`/api/tools`、`/api/tools/execute`、`/api/health`、`/api/config`
- `/` 返回 `kyrozen/web/index.html`

**如何使用：**
- 保留现有 Core 相关端点
- 新增 Project 相关路由
- `ChatRequest` 需要增加 `project_id` 字段

**需要扩展：**
- `/api/projects` GET/POST
- `/api/projects/{project_id}` GET/PUT/DELETE
- `/api/projects/{project_id}/tasks`
- `/api/projects/{project_id}/decisions`
- `/api/projects/{project_id}/artifacts`
- `/api/projects/{project_id}/chat` (项目内聊天)

---

### 2.9 Web UI (index.html) —— 需要新增页面视图

**当前状态：**
- 文件：`kyrozen/web/index.html`
- 单页聊天界面

**如何使用：**
- 保留聊天组件
- 新增项目列表视图、项目详情视图
- 通过前端路由或简单视图切换实现

**需要扩展：**
- Project List 页面
- Project Detail 页面
- Project Chat 页面

---

## 3. Storage 现状分析

| 数据 | 当前存储 | 问题 | Phase 2 建议 |
|------|---------|------|-------------|
| Task | `kyrozen_tasks.json` 全局文件 | 无项目隔离，所有任务混在一起 | 每个项目独立 `tasks.json` |
| Memory | InMemoryMemory 进程内存 | 服务重启丢失 | 增加 JsonFileMemory 持久化实现 |
| Log | `logs/` 目录 | 全局日志，无项目隔离 | metadata 中带 project_id，可选项目日志目录 |
| Config | 环境变量 + `~/.kyrozen_config.json` | 无项目配置 | 项目本身不需要改 config，但 workspace 路径需要配置 |

**建议的 Workspace 目录结构：**

```
workspace/
└── projects/
    └── {project_id}/
        ├── project.json          # 项目元数据
        ├── tasks.json            # 项目任务
        ├── decisions.json        # 项目决策
        ├── artifacts.json        # 产物索引
        ├── files/                # 项目文件
        ├── documents/            # 产物文档
        └── memory.json           # 项目级 Memory（若使用 JsonFileMemory）
```

---

## 4. Project Context 注入设计

Phase 2 核心需求：用户进入项目聊天时，Kyrozen 不仅收到当前消息，还要收到项目上下文。

**上下文来源：**
1. Project 基础信息：`name`, `goal`, `description`, `current_stage`, `status`
2. Recent Tasks：最近 3-5 个任务标题与结果摘要
3. Recent Decisions：最近 3-5 个关键决策
4. Recent Memories：项目级 Memory 中相关条目
5. Next Steps：项目当前下一步计划

**注入方式：**

不修改 `BaseAgent.run()` 签名，而是在 API 层构造一条 enriched user message：

```
[Project Context]
Project: 智能跑步设备
Goal: 改善运动音乐体验
Current Stage: problem_discovery
Recent Tasks:
- 创建项目并明确目标 (completed)
Recent Decisions:
- 暂无
Next Steps: 继续分析需求

[User Message]
下一步怎么办？
```

这样 `BaseAgent` 保持通用，Project Workspace 负责上下文组装。

---

## 5. 数据模型设计建议

### Project

```python
class Project:
    id: str
    name: str
    description: str
    goal: str
    status: "active" | "paused" | "completed" | "archived"
    current_stage: "problem_discovery" | "market_research" | "product_definition" | "solution_design" | "development" | "testing" | "iteration"
    next_steps: str
    risks: list[str]
    created_at: str
    updated_at: str
```

### Decision

```python
class Decision:
    id: str
    project_id: str
    decision: str
    reason: str
    alternatives: list[str]
    rejected_reasons: dict[str, str]
    source: str
    timestamp: str
```

### Artifact

```python
class Artifact:
    id: str
    project_id: str
    type: str  # problem_brief, prd, bom, test_report, ...
    title: str
    content: str
    version: int
    change_reason: str
    created_at: str
    updated_at: str
```

### ProjectTask (继承 Task)

```python
class Task:
    # 已有字段
    project_id: str | None = None  # 新增
```

---

## 6. Phase 2 实施方案概要

### 6.1 新增模块

| 模块 | 文件 | 职责 |
|------|------|------|
| Project Entity | `kyrozen/project/project.py` | Project / Decision / Artifact 数据模型 |
| Project Storage | `kyrozen/project/storage.py` | 项目级 JSON 文件持久化 |
| Project Manager | `kyrozen/project/manager.py` | CRUD、查询、打开项目 |
| Context Builder | `kyrozen/project/context.py` | 组装 Project Context |
| Scoped Memory | `kyrozen/memory/scoped.py` | ProjectMemory / JsonFileMemory |

### 6.2 扩展模块

| 模块 | 修改内容 |
|------|---------|
| `kyrozen/core/task.py` | Task 增加 `project_id` |
| `kyrozen/config/settings.py` | 增加 `projects_dir`、`artifacts_dir` |
| `kyrozen/api/server.py` | 新增 Project API 路由，修改 ChatRequest |
| `kyrozen/web/index.html` | 新增项目列表、详情、聊天视图 |

### 6.3 不修改的模块

- `kyrozen/core/agent.py`：不重新设计 Core，只通过 context 注入使用
- `kyrozen/core/permission.py`：直接复用
- `kyrozen/tools/`：直接复用
- `kyrozen/models/`：直接复用

---

## 7. 风险与注意事项

1. **存储迁移**：Phase 1 使用全局 `kyrozen_tasks.json`，Phase 2 改为按项目存储。旧任务可以保留在全局文件中，或归档为 `legacy_tasks`。
2. **Memory 持久化**：InMemoryMemory 在进程重启后丢失。Phase 2 需要至少实现 JsonFileMemory 保证项目上下文可恢复。
3. **并发**：TaskManager 已有线程锁。Project Manager 也需要类似锁保护文件写入。
4. **不要提前实现产品流程**：Phase 2 只建立 Project Workspace 基础设施，不实现 Problem Discovery Agent 等。

---

*分析完成时间：2026-07-21*
*下一步：确认本方案后开始 Phase 2 编码。*
