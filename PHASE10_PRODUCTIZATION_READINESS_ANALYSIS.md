# Kyrozen Productization Readiness Analysis

## 1. 分析目标

本报告在 Phase 10 编码开始前，对 Phase 1-9 的实现状态进行系统性检查，判断当前代码距离「可对外发布的 Beta 产品」还有哪些缺口，并给出 Beta 架构设计建议。

---

## 2. Phase 1-9 现状速览

| 阶段 | 核心能力 | 当前状态 | 关键文件 |
|------|----------|----------|----------|
| Phase 1 Core | Agent Runtime、Model Interface、Tool System、Task、Logging、Memory | 完整，测试覆盖充分 | `kyrozen/core/agent.py`, `kyrozen/tools/base.py`, `kyrozen/memory/interface.py`, `kyrozen/core/task.py` |
| Phase 2 Workspace | Project 生命周期、Artifact、Decision、SQLite DB | 完整，单实例运行稳定 | `kyrozen/project/project.py`, `kyrozen/project/db.py`, `kyrozen/project/manager.py` |
| Phase 3 Discovery | Problem Brief、问题发现 | 完整 | `kyrozen/discovery/` |
| Phase 4 Research | 市场调研、竞品分析 | 完整 | `kyrozen/research/` |
| Phase 5 Planning | Product Brief、PRD、MVP、Solution Decision | 完整 | `kyrozen/planning/` |
| Phase 6 Development | 软件开发、Coding Agent、Git | 完整 | `kyrozen/development/` |
| Phase 7 Hardware | Hardware Plan、BOM、Firmware、Debug | 完整 | `kyrozen/hardware/` |
| Phase 8 Testing | Test Plan、Test Result、User Validation、Iteration | 完整 | `kyrozen/testing/` |
| Phase 9 Learning | 学习记录、失败/成功知识、主动建议、跨项目学习 | 完整 | `kyrozen/learning/` |
| API | REST API、模式切换、状态端点 | 功能完整，但无认证 | `kyrozen/api/server.py` |
| Web UI | 单文件 HTML + 原生 JS | 可用但为测试入口级别 | `kyrozen/web/index.html` |

---

## 3. 核心能力就绪度评估

### 3.1 Core 稳定性：高

- BaseAgent 循环、Tool Registry、Task Manager、Permission Manager 均经过 244 个测试验证。
- Model Interface 支持 deepseek/openai/anthropic/google/ollama，配置加载顺序正确（环境变量优先）。
- Memory Interface 有 InMemoryMemory、JsonFileMemory、ProjectMemory 三层实现。

**缺口**：
- PermissionManager 目前只有 `strict/permissive` 两种全局模式，没有按用户或按项目的权限判断。
- 没有用户身份，无法做基于角色的访问控制。

### 3.2 Project System 多用户支持：低

- `Project` 模型没有 `user_id` 字段。
- `KyrozenDatabase.list_projects()` 返回全部项目，没有按用户过滤。
- API `/api/projects` 不验证调用者身份，任何知道项目 ID 的人都可以访问。
- 文件系统路径 `projects/{project_id}/` 本身未按用户隔离，但可通过添加 `user_id` 前缀实现。

**结论**：当前是单租户开发工具，不是多用户产品。

### 3.3 Memory 权限隔离：低

- 项目内记忆通过 `ProjectMemory` 隔离到 `projects/{project_id}/memory.json`，这部分基本可靠。
- Phase 9 的 `learning_memory.json` 是全局文件，保存在 `workspace_root` 下，所有用户共享。
- Learning record 的 `scope` 字段（private/user/public）已在模型层定义，但 API 层没有按当前用户过滤。
- 没有用户级 Memory 表/文件。

**风险**：Beta 阶段若多用户共用同一实例，跨项目学习会变成跨用户泄露。

### 3.4 Development Pipeline 闭环：高

- 从 Problem Discovery → Market Research → Planning → Development → Hardware → Testing → Learning 的 Agent 和工具链已全部打通。
- `Project.current_stage` 字段可表达阶段，但目前阶段推进依赖用户手动选择 mode 或更新字段，没有自动引导。

**缺口**：
- 没有「下一步该做什么」的自动推荐逻辑。
- 没有基于当前 stage 锁定可用操作的产品状态机。

### 3.5 Web 产品体验：低

- 当前 `index.html` 是 3000+ 行的单文件原生 JS 测试界面。
- 所有模式（discovery/research/.../learning）以并列视图存在，用户需要知道该点什么。
- 没有登录/注册、没有 Dashboard、没有全局导航、没有用户设置。
- 移动端适配有限。

---

## 4. 与 Phase 10 功能要求的差距映射

| Phase 10 要求 | 当前状态 | 缺口等级 | 关键改造点 |
|---------------|----------|----------|------------|
| **User Account System** | 无 | 高 | 新增 User 模型、注册/登录 API、密码哈希、JWT/Session、用户隔离 |
| **Multi-Project Management** | 部分 | 高 | Project 加 user_id、API 鉴权、文件路径按用户隔离 |
| **Complete Product Workflow** | 功能有，引导无 | 中 | 增加 stage 状态机、Next Action 推荐、模式自动切换 |
| **Product State Management** | 字段有，逻辑弱 | 中 | 标准化 stage 流转、blocked_reason、progress 计算 |
| **Beta User Feedback System** | 无 | 中 | 新增 feedback 表/模型、API、Web 反馈入口 |
| **Analytics System** | 无 | 中 | 事件日志、聚合统计、隐私脱敏 |
| **Error Monitoring** | 基础日志 | 中 | 统一错误捕获、错误事件表、告警/看板 |
| **Deployment System** | 无 | 高 | Dockerfile、docker-compose、环境变量模板、启动脚本 |
| **Version Management** | API version 硬编码 | 低 | VERSION 文件、Changelog、migration 脚本 |
| **Security System** | 基础 | 高 | 认证、鉴权、Rate Limit、Secret 管理、CORS、输入校验 |
| **Documentation System** | README + 交付报告 | 中 | 用户文档目录、Getting Started、FAQ |
| **Beta Release Workflow** | 无 | 中 | Invite code、Beta flag、反馈闭环 |

---

## 5. 关键设计决策建议

### 5.1 认证与账户：JWT + SQLite

- 使用 `python-jose` + `passlib` 做 JWT 和密码哈希。
- 用户表字段：`user_id`, `email`, `hashed_password`, `name`, `role`, `created_at`, `updated_at`, `beta_invite_code`, `is_active`。
- 登录后返回 JWT，后续请求通过 `Authorization: Bearer <token>` 认证。
- 新增 `/api/auth/register`, `/api/auth/login`, `/api/auth/me`。

### 5.2 项目与用户隔离

- `projects` 表新增 `user_id TEXT NOT NULL`。
- 所有 `/api/projects` 相关端点只返回/操作 `current_user.user_id` 的项目。
- 文件路径从 `workspace/projects/{project_id}` 改为 `workspace/users/{user_id}/projects/{project_id}`。
- `learning_memory.json` 改为 `workspace/users/{user_id}/learning_memory.json`。
- 跨项目学习只查询同 `user_id` 下的 `scope=user` 记录，绝不跨用户。

### 5.3 权限模型升级

- 保留 `PermissionManager` 的高风险工具判断。
- 新增 `OwnershipPermission` 中间件：校验当前用户是否拥有 project_id。
- Tool 执行时注入 `current_user_id`，禁止访问他人项目文件。

### 5.4 产品状态机

```
problem_discovery → market_research → product_definition → solution_design
        ↓
   development ──→ testing ──→ iteration ──→ completed
        ↓
    paused / archived
```

- 每个 stage 推荐下一步 action，例如：
  - `problem_discovery` 且 Problem Brief 为空 → 推荐「开始问题发现」。
  - `development` 且没有 technical_plan artifact → 推荐「开始技术规划」。
- 用户仍可通过 AI Assistant 自由提问，但产品主流程给出默认引导。

### 5.5 Web 产品化方案

**推荐方案 A：渐进增强现有单页 HTML（Beta 首选）**
- 在 `index.html` 基础上增加登录/注册视图、Dashboard、全局导航。
- 保留现有模式视图，增加 stage-based 引导面板。
- 优点：改动可控、不引入构建链路、快速达到 Beta。
- 缺点：长期维护性一般。

**方案 B：Vite + React 重构**
- 符合用户技术栈偏好，适合长期产品。
- 但 Phase 10 原则强调「稳定优先，不要为展示功能增加复杂模块」。
- 建议作为 Phase 11 或后续任务，不在 Beta 阶段做完整重写。

**建议**：Phase 10 采用方案 A，仅对必要部分做结构拆分（例如将 JS/CSS 提取为独立文件），不引入 React/Vite 构建链。

### 5.6 部署与运维

- 提供 `Dockerfile` 和 `docker-compose.yml`。
- 数据卷挂载：`workspace/`, `kyrozen.db`。
- 环境变量模板：`.env.example`。
- 启动命令：`docker-compose up -d`。

### 5.7 反馈、分析与监控

- 新增 `events` 表记录用户行为（project_created, stage_changed, chat_sent, tool_executed, error_occurred）。
- 新增 `feedback` 表记录用户反馈（bug/feature/experience/ai_suggestion）。
- 新增 `/api/admin/analytics` 聚合接口（仅 admin 角色可访问）。
- 错误监控：在 API 异常处理中写入 `errors` 表，包含 endpoint、stack、user_id、project_id。

---

## 6. 推荐实施顺序

为了让 Beta 尽快可用，建议按以下顺序实施：

1. **用户与认证**（User model + Auth API + Web login/register）
2. **项目隔离**（Project.user_id + 文件路径隔离 + API 鉴权）
3. **Memory 隔离**（用户级 learning memory + scope 过滤）
4. **产品状态机与引导**（Next Action + stage 自动推荐）
5. **部署系统**（Docker + compose + env 模板）
6. **反馈与分析**（Feedback API + Events + Analytics）
7. **错误监控**（统一异常处理 + errors 表）
8. **文档与版本**（README 用户文档 + VERSION + Changelog）
9. **Beta 流程**（Invite code + Beta flag）
10. **测试覆盖**（新增 test_auth.py, test_multi_user.py, test_beta_flow.py）

---

## 7. 风险与约束

| 风险 | 说明 | 缓解措施 |
|------|------|----------|
| 单文件 HTML 膨胀 | 继续向 `index.html` 添加功能会导致维护困难 | 将 JS/CSS 拆分为 `web/static/` 下的独立文件 |
| 学习记忆跨用户泄露 | 当前 `learning_memory.json` 全局共享 | 立即按用户拆分文件并加 scope 过滤 |
| 文件系统路径变更 | 用户隔离需要改 project_dir | 通过 migration 脚本或首次启动自动迁移 |
| 外部 API 费用 | Beta 用户大量使用模型/搜索 API | 增加 Rate Limit、使用配额提示、默认使用本地/低成本模型 |
| 数据丢失 | Docker 部署时未正确挂载卷 | 文档强调 volume 挂载，提供 backup 脚本 |

---

## 8. 结论

**当前 Kyrozen 已实现完整 AI 产品开发能力链，但仍是单租户开发框架，不是多用户产品。**

Phase 10 的关键不是增加新 Agent，而是：

1. **加用户**：认证、隔离、权限。
2. **加引导**：状态机、Next Action、产品化流程。
3. **加固件**：部署、监控、反馈、文档。

建议先完成架构设计文档确认，再按「用户隔离 → 部署 → 引导 → 反馈/监控 → 文档」的顺序实施。

---

*下一步：确认本分析后，输出 Phase 10 Beta Architecture Design 与实施计划。*
