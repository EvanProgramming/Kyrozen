# Kyrozen Phase 2 实施计划

## 目标

让 Kyrozen 从「单次任务执行 Agent」升级为「长期项目 Agent」：
- 基本单位从 Conversation 变为 Project
- 项目状态、任务、决策、产物、Memory 持久化
- 用户关闭网页后重新打开，项目上下文仍可恢复
- 当前仍用 Web 形式做测试入口，不实现最终产品 UI

---

## 目录结构变化

```
Kyrozen/
├── kyrozen/
│   ├── api/
│   │   └── server.py              # 扩展 Project API
│   ├── config/
│   │   └── settings.py            # 增加 workspace/projects 路径
│   ├── core/
│   │   ├── agent.py               # 不修改
│   │   ├── permission.py          # 不修改
│   │   └── task.py                # Task 增加 project_id
│   ├── logs/
│   │   └── logger.py              # 可选：增加 project_id 字段
│   ├── memory/
│   │   ├── interface.py           # 不修改
│   │   └── scoped.py              # 新增：ProjectMemory、JsonFileMemory
│   ├── models/                    # 不修改
│   ├── project/                   # 新增
│   │   ├── __init__.py
│   │   ├── project.py             # Project / Decision / Artifact 模型
│   │   ├── db.py                  # 新增：SQLite schema + KyrozenDatabase
│   │   ├── manager.py             # ProjectManager CRUD
│   │   └── context.py             # ProjectContext 组装
│   ├── tools/
│   │   └── project_tools.py       # 新增 update_project 工具
│   └── web/
│       └── index.html             # 扩展项目列表/详情/聊天视图
├── tests/                         # 新增 project 相关测试
└── workspace/                     # 运行时生成
    ├── kyrozen.db                 # SQLite：projects / tasks / decisions / artifacts
    └── projects/
        └── {project_id}/
            ├── memory.json        # 项目级 Memory
            ├── files/             # 项目文件
            └── documents/         # 产物文档
```

---

## 第一阶段：数据模型与存储

### 1.1 新增 `kyrozen/project/project.py`

定义三个核心数据类：

- `Project`
- `Decision`
- `Artifact`

每个类包含：
- `to_dict()` / `from_dict()`
- `update()` 方法更新时间戳

### 1.2 新增 `kyrozen/project/db.py`

- `KyrozenDatabase`
  - 管理 SQLite 连接和表结构
  - 表：`projects`、`tasks`、`decisions`、`artifacts`
  - 初始化时自动创建表和索引
  - 支持按项目 ID 查询任务、决策、产物

实现原则：
- 单文件数据库：`workspace/kyrozen.db`
- 表结构简单，便于后续迁移
- 线程锁保护写操作

### 1.3 新增 `kyrozen/project/manager.py`

- `ProjectManager`
  - `create(name, description, goal) -> Project`
  - `get(project_id) -> Project | None`
  - `list() -> list[Project]`
  - `update(project) -> Project`
  - `archive(project_id) -> Project`
  - `add_decision(project_id, decision, reason, alternatives, ...)`
  - `list_decisions(project_id)`
  - `save_artifact(project_id, type, title, content, change_reason)`
  - `list_artifacts(project_id)`
  - `get_artifact(project_id, artifact_id)`

---

## 第二阶段：上下文系统

### 2.1 新增 `kyrozen/project/context.py`

- `ProjectContextBuilder`
  - `build(project: Project, task_manager, memory, decisions, artifacts) -> str`

组装内容：
1. Project 基本信息
2. Current Stage + Next Steps
3. Recent Tasks（最近 5 条）
4. Recent Decisions（最近 5 条）
5. Relevant Memories（按关键词 query）

输出格式示例：

```
[Project Context]
Project: 智能跑步设备
Goal: 改善运动音乐体验
Current Stage: problem_discovery
Status: active
Next Steps: 继续分析目标用户和使用场景

Recent Tasks:
- 创建项目并明确目标 (completed)

Recent Decisions:
- 暂无

Relevant Memories:
- 用户希望产品价格在 100 美元以内

[User Message]
下一步怎么办？
```

### 2.2 API 层注入

修改 `/api/chat`：
- `ChatRequest` 增加 `project_id: str | None`
- 如果带 `project_id`，从 ProjectManager 读取项目
- 用 ProjectContextBuilder 构造上下文
- 调用 `agent.run(context + message, confirmed=...)`

---

## 第三阶段：任务与 Memory 升级

### 3.1 扩展 `kyrozen/core/task.py`

- `Task` 增加 `project_id: str | None = None`
- `to_dict() / from_dict()` 增加序列化
- `TaskManager` 增加 SQLite 支持：通过 `db` 参数写入 `kyrozen.db`
- 保留原有 JSON 文件能力作为 fallback

建议方案：
- `TaskManager` 增加可选的 `db: KyrozenDatabase | None` 参数
- 如果提供 db，任务保存到 SQLite 并关联 project_id
- API 层为每个项目使用同一个 db 实例
- BaseAgent 继续接收 task_manager 实例

### 3.2 新增 `kyrozen/memory/scoped.py`

- `JsonFileMemory(MemoryInterface)`
  - 使用 JSON 文件持久化 Memory
  - 支持 category、project_id、关键词过滤
- `ProjectMemory`
  - 包装 JsonFileMemory 或 InMemoryMemory
  - `save(content, category, **metadata)` 自动附加 project_id
  - `query(query, category, limit)` 自动过滤 project_id

---

## 第四阶段：API 扩展

### 4.1 新增端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects` | GET | 列出所有项目 |
| `/api/projects` | POST | 创建项目 |
| `/api/projects/{id}` | GET | 获取项目详情 |
| `/api/projects/{id}` | PUT | 更新项目 |
| `/api/projects/{id}` | DELETE | 归档/删除项目 |
| `/api/projects/{id}/tasks` | GET | 项目任务列表 |
| `/api/projects/{id}/decisions` | GET/POST | 决策列表 / 新增决策 |
| `/api/projects/{id}/artifacts` | GET/POST | 产物列表 / 新增产物 |
| `/api/projects/{id}/artifacts/{artifact_id}` | GET | 产物详情 |

### 4.2 修改现有端点

- `ChatRequest` 增加 `project_id: str | None`
- `/api/chat` 根据 project_id 注入上下文
- `/api/tasks` 可选按 `project_id` 过滤
- `/api/tasks/{id}/confirm` 保持现状

---

## 第五阶段：Web UI 扩展

### 5.1 页面结构

单文件 `index.html` 内通过视图切换实现：

1. **Project List View**
   - 项目列表卡片
   - 创建项目按钮
   - 每个项目显示：名称、状态、阶段、更新时间

2. **Project Detail View**
   - 项目标题、Goal、Current Stage、Status、Next Steps
   - 最近任务列表
   - 最近决策列表
   - 最近产物列表
   - 「进入项目聊天」按钮

3. **Project Chat View**
   - 与 Phase 1 聊天界面类似
   - 顶部显示当前项目名称
   - 右侧保留任务步骤面板
   - 发送消息时附带 `project_id`

### 5.2 路由方式

不使用前端框架，使用 hash 路由或简单状态变量：
- `/#/projects` 项目列表
- `/#/projects/{id}` 项目详情
- `/#/projects/{id}/chat` 项目聊天

---

## 第六阶段：测试

新增测试文件：

| 文件 | 测试内容 |
|------|---------|
| `tests/test_project.py` | Project 创建、更新、归档、列表 |
| `tests/test_project_db.py` | SQLite 持久化与查询 |
| `tests/test_project_context.py` | Context Builder 组装 |
| `tests/test_json_memory.py` | JsonFileMemory save/query/update/delete |
| `tests/test_api_project.py` | Project API 端点 |

测试原则：
- 所有测试不依赖真实模型 API
- 使用 Phase 1 已有的 `MockModel` fixture
- 使用临时目录避免污染真实 workspace

---

## 第七阶段：交付报告

完成后输出 `PHASE2_DELIVERY_REPORT.md`，包含：
1. Project Workspace Architecture
2. Database / Storage Design
3. Web Changes
4. Integration Report（如何连接 Phase 1）
5. Test Results
6. Limitations

---

## 开发顺序

1. Project 数据模型 + Storage + Manager
2. Task project_id 扩展 + Project-level TaskManager
3. JsonFileMemory + ProjectMemory
4. Context Builder
5. Project API 端点
6. Web UI 视图切换
7. 测试
8. 交付报告 + commit/push

---

## 不实现的内容

- Problem Discovery Agent
- Market Research Agent
- Product Agent
- Hardware Agent
- Software Agent
- 自动生成 Market Research Report / PRD / BOM 等产品文档
- 复杂 UI 设计（产品画布、决策中心、采购中心、制作模式）

---

*计划完成时间：2026-07-21*
*等待确认后开始编码。*
