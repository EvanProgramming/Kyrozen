# Kyrozen Phase 10 Beta Architecture Design

## 1. 设计目标

把 Kyrozen 从「单租户开发框架」升级为「可部署、可注册、可多人使用的 Beta 产品」。

核心原则（来自 Phase 10 要求）：
- 不增加新的 AI Agent 类型
- 不为了展示功能增加复杂模块
- 稳定 > 功能数量
- 用户控制 > 自动行为

---

## 2. 产品架构

```
┌─────────────────────────────────────────────┐
│              Users / Browsers               │
└──────────────────┬──────────────────────────┘
                   │ HTTPS
┌──────────────────▼──────────────────────────┐
│     Vite + React + TypeScript Frontend      │
│  (Login / Dashboard / Project Workspace)    │
└──────────────────┬──────────────────────────┘
                   │ API calls (JWT)
┌──────────────────▼──────────────────────────┐
│        Kyrozen FastAPI Backend              │
│  - Auth middleware (Supabase JWT verify)    │
│  - Project / Task / Artifact APIs           │
│  - Agent runtime (Phase 1-9)                │
│  - Tool execution + Permission check        │
└──────────────────┬──────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
┌───────▼────────┐   ┌────────▼─────────┐
│   Supabase     │   │  Local Filesystem │
│  - PostgreSQL  │   │  - projects/      │
│  - Auth        │   │  - user files     │
└────────────────┘   └───────────────────┘
```

### 模块职责

| 模块 | 技术 | 职责 |
|------|------|------|
| Frontend | Vite + React + TypeScript | 产品界面、路由、状态管理 |
| Backend | FastAPI + Python 3.12 | API、Agent Runtime、Tool System |
| Database | Supabase PostgreSQL (本地 Docker) | 用户数据、项目、任务、记忆、事件 |
| Auth | Supabase Auth (本地 Docker) | 注册、登录、JWT、密码找回 |
| Storage | 本地文件卷 | 项目源码、生成文件、学习记忆 JSON |

---

## 3. 用户流程

```
邀请链接 / 注册页
       │
       ▼
注册账号（邮箱 + 密码）
       │
       ▼
登录 → 获取 Supabase JWT
       │
       ▼
Dashboard（我的项目 / 最近活动）
       │
       ▼
创建项目
       │
       ▼
Project Workspace（按当前 stage 引导）
       │
       ├── Problem Discovery
       ├── Market Research
       ├── Product Planning
       ├── Development
       ├── Hardware（可选）
       ├── Testing
       └── Learning / Improvement
       │
       ▼
提交反馈（Bug / Feature / 体验 / AI 建议）
```

### 首次登录引导

1. 登录后进入 Dashboard
2. 空项目状态显示「创建第一个项目」引导
3. 创建项目后自动进入 Project Workspace
4. 根据 `current_stage` 显示推荐下一步动作

---

## 4. 部署架构

### 本地服务器部署（推荐 Beta 形态）

```yaml
# docker-compose.yml
services:
  supabase-db:          # PostgreSQL
  supabase-auth:        # GoTrue
  supabase-rest:        # PostgREST
  supabase-storage:     # Storage API
  supabase-meta:        # Postgres Meta
  supabase-studio:      # 管理界面

  kyrozen-backend:
    build: ./backend
    env_file: .env
    volumes:
      - kyrozen_data:/app/workspace
    depends_on:
      - supabase-db

  kyrozen-frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - kyrozen-backend
```

### 数据持久化

| 数据 | 存储位置 | 备注 |
|------|----------|------|
| PostgreSQL | Docker volume `supabase_db` | 必须备份 |
| 项目文件 | Docker volume `kyrozen_data` | 必须备份 |
| 环境变量 | `.env` 文件 | 不提交到 Git |

### 网络访问

- 前端：用户通过服务器 IP/域名访问（默认 80/443）
- 后端：内部网络 `http://kyrozen-backend:8000`，不直接暴露
- Supabase：内部网络，Studio 管理界面按需开放

---

## 5. 数据库设计（Supabase PostgreSQL）

### 5.1 表结构

```sql
-- 用户由 Supabase Auth 管理，此表仅做镜像/扩展
CREATE TABLE user_profiles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    name TEXT,
    role TEXT NOT NULL DEFAULT 'user', -- user | admin | beta
    beta_invite_code TEXT,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    goal TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    current_stage TEXT NOT NULL DEFAULT 'problem_discovery',
    next_steps TEXT,
    blocked_reason TEXT,
    progress INTEGER DEFAULT 0,
    risks JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    steps JSONB DEFAULT '[]',
    result JSONB,
    errors JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE decisions (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    decision TEXT NOT NULL,
    reason TEXT,
    alternatives JSONB DEFAULT '[]',
    rejected_reasons JSONB DEFAULT '{}',
    source TEXT DEFAULT 'agent',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    change_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Phase 9 学习数据迁移到 DB
CREATE TABLE learning_records (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    memory TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    source TEXT,
    confidence TEXT NOT NULL DEFAULT 'low',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    scope TEXT NOT NULL DEFAULT 'private',
    tags JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE failure_knowledge (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    problem TEXT NOT NULL,
    cause TEXT,
    solution TEXT,
    affected_scope TEXT,
    verification TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE success_knowledge (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    goal TEXT,
    solution TEXT NOT NULL,
    conditions TEXT,
    result TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE suggestions (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    suggestion TEXT NOT NULL,
    reason TEXT,
    evidence JSONB DEFAULT '[]',
    impact TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'new',
    category TEXT,
    related_learning_ids JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Phase 10 新增
CREATE TABLE user_feedback (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    type TEXT NOT NULL, -- bug | feature_request | experience | ai_suggestion
    description TEXT NOT NULL,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'open', -- open | in_progress | resolved | closed
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL, -- project_created | stage_changed | chat_sent | tool_executed | error_occurred | ...
    payload JSONB DEFAULT '{}',
    session_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE error_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    endpoint TEXT,
    method TEXT,
    error_type TEXT,
    message TEXT,
    stack TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.2 RLS（Row Level Security）

所有业务表启用 RLS，确保用户只能访问自己的数据：

```sql
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can only access their own projects"
    ON projects FOR ALL
    USING (user_id = auth.uid());
```

后端通过 `service_role` key 绕过 RLS 进行必要的系统操作，但所有查询必须带 `user_id` 过滤。

---

## 6. 认证与安全设计

### 6.1 认证流程

```
Frontend          Supabase Auth          Kyrozen Backend
   │                    │                      │
   │── register ───────▶│                      │
   │◀── user + JWT ─────│                      │
   │                    │                      │
   │── API call with JWT ──────────────────────▶│
   │                    │                      │── verify JWT with Supabase
   │◀───────────────────────────────────────────│
```

### 6.2 FastAPI 认证中间件

- 读取 `Authorization: Bearer <token>`
- 使用 `supabase-py` 或 `jwt` + Supabase public key 验证 token
- 注入 `current_user: User` 到依赖
- 未认证请求返回 401
- 非本人资源请求返回 403

### 6.3 权限模型

| 层级 | 机制 |
|------|------|
| API 访问 | JWT + RLS |
| 项目所有权 | 每个 API 校验 `project.user_id == current_user.user_id` |
| 高风险工具 | 保留 `PermissionManager`，严格模式下需用户确认 |
| 管理员 | `role='admin'` 可访问 `/api/admin/*` 和 analytics |

### 6.4 安全加固

- CORS 限制为前端域名
- Rate Limit：基于 `user_id` 限制 API 调用频率（slowapi）
- Secret 管理：所有 key 通过 `.env` 注入，不写入代码
- 输入校验：Pydantic 模型 + SQL 参数化
- 文件路径校验：禁止 `..` 和绝对路径穿越

---

## 7. API 设计

### 7.1 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 代理或辅助注册（可选） |
| POST | `/api/auth/login` | 代理登录，返回 JWT |
| GET | `/api/auth/me` | 当前用户信息 |
| POST | `/api/auth/logout` | 退出（前端清除 token） |

### 7.2 项目

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects` | 当前用户项目列表 |
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects/{id}` | 项目详情 + 最近活动 |
| PUT | `/api/projects/{id}` | 更新项目 |
| DELETE | `/api/projects/{id}` | 归档项目 |
| GET | `/api/projects/{id}/state` | 产品状态（stage, progress, next_action, blocked_reason） |
| POST | `/api/projects/{id}/advance` | 推进到下一阶段 |

### 7.3 各阶段状态

保留现有状态端点，全部加上 `user_id` 鉴权：

- `/api/projects/{id}/problem-discovery/state`
- `/api/projects/{id}/market-research/state`
- `/api/projects/{id}/planning/state`
- `/api/projects/{id}/development/state`
- `/api/projects/{id}/hardware/state`
- `/api/projects/{id}/testing/state`
- `/api/projects/{id}/learning/state`
- `/api/projects/{id}/improvement/state`

### 7.4 Chat 与任务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 发送消息，按 project_id 鉴权 |
| GET | `/api/tasks` | 当前用户任务 |
| GET | `/api/tasks/{id}` | 任务详情 |
| POST | `/api/tasks/{id}/confirm` | 确认高风险操作 |

### 7.5 反馈与分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/feedback` | 提交用户反馈 |
| GET | `/api/feedback` | 当前用户反馈列表 |
| GET | `/api/admin/analytics` | 管理员查看聚合数据 |
| GET | `/api/admin/errors` | 管理员查看错误日志 |

---

## 8. 前端架构

### 8.1 技术栈

- Vite 5 + React 18 + TypeScript
- React Router 6
- TanStack Query (React Query) 或 Zustand
- Tailwind CSS（或继续使用现有深色主题 CSS）
- Axios + interceptors（自动附加 JWT）

### 8.2 目录结构

```
frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── router.tsx
│   ├── api/
│   │   ├── client.ts
│   │   ├── auth.ts
│   │   ├── projects.ts
│   │   └── chat.ts
│   ├── components/
│   │   ├── Layout.tsx
│   │   ├── Sidebar.tsx
│   │   ├── ProjectCard.tsx
│   │   ├── StageIndicator.tsx
│   │   ├── ChatPanel.tsx
│   │   ├── ArtifactViewer.tsx
│   │   └── SuggestionList.tsx
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── RegisterPage.tsx
│   │   ├── DashboardPage.tsx
│   │   ├── ProjectListPage.tsx
│   │   ├── ProjectWorkspacePage.tsx
│   │   ├── SettingsPage.tsx
│   │   └── AdminPage.tsx
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── useCurrentUser.ts
│   │   └── useProject.ts
│   ├── stores/
│   │   └── authStore.ts
│   ├── types/
│   │   └── api.ts
│   └── utils/
│       └── jwt.ts
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

### 8.3 核心页面

| 页面 | 职责 |
|------|------|
| Login / Register | Supabase Auth 登录注册 |
| Dashboard | 我的项目、最近活动、快速开始 |
| Project List | 所有项目卡片、创建项目 |
| Project Workspace | 左侧阶段导航 + 右侧主内容区 |
| Settings | 用户名、偏好、Beta 反馈 |
| Admin | 分析看板、错误日志、用户反馈 |

### 8.4 与后端的类型对齐

从 FastAPI 的 Pydantic 模型生成 TypeScript 类型（手动维护或使用 openapi-typescript），确保前后端一致。

---

## 9. 产品状态机与引导

### 9.1 Stage 定义

```typescript
type ProjectStage =
  | "problem_discovery"
  | "market_research"
  | "product_definition"
  | "solution_design"
  | "development"
  | "testing"
  | "iteration"
  | "completed"
  | "paused"
  | "archived";
```

### 9.2 Next Action 推荐逻辑

基于当前 stage 和 artifacts 状态推荐下一步：

| 当前 Stage | 判断条件 | 推荐 Next Action |
|------------|----------|------------------|
| problem_discovery | 无 problem_brief | 开始问题发现 |
| market_research | 无 market_research_report | 开始市场调研 |
| product_definition | 无 product_brief / prd | 开始产品规划 |
| solution_design | 无 solution_comparison | 对比解决方案 |
| development | 无 technical_plan | 生成技术方案 |
| testing | 无 test_plan | 创建测试计划 |
| iteration | iteration_plan 存在未处理项 | 处理迭代项 |
| completed | 全部完成 | 查看总结/创建新项目 |

### 9.3 Stage 自动推进

- 用户完成某个阶段的核心 artifact 后，Agent 可建议推进。
- 推进需要用户显式确认（不自动改变阶段）。
- 调用 `POST /api/projects/{id}/advance` 更新 stage。

---

## 10. Beta 系统

### 10.1 邀请机制

- `user_profiles.beta_invite_code` 字段记录邀请码来源。
- 注册时可选填写 invite code。
- Admin 可在后台生成邀请码。
- 未使用邀请码注册的用户进入 waiting list 或限制功能。

### 10.2 反馈闭环

```
用户提交反馈
    │
    ▼
存入 user_feedback 表
    │
    ▼
Admin 查看 /api/admin/feedback
    │
    ▼
转化为任务 / 修复 / 回复
    │
    ▼
更新反馈状态并通知用户
```

### 10.3 使用分析

通过 `events` 表聚合：

- 各阶段完成率
- 功能使用频率
- 常见错误类型
- 用户留存指标（基于 project_created 和 chat_sent 时间）

---

## 11. 错误监控

### 11.1 错误捕获

- FastAPI 全局异常处理写入 `error_logs` 表。
- Agent / Tool 执行失败记录到 `events` 和 `error_logs`。
- 前端错误通过 `/api/client-errors` 上报。

### 11.2 告警

- Admin 页面实时显示最近错误。
- 可配置 webhook 通知（可选，Beta 阶段可用日志替代）。

---

## 12. 版本与文档

### 12.1 版本管理

- `VERSION` 文件：`1.0.0-beta.1`
- `CHANGELOG.md`：记录每个版本变更、已知问题、修复。
- Git tag：`v1.0.0-beta.1`

### 12.2 文档

新增 `docs/` 目录：

```
docs/
├── getting-started.md
├── creating-project.md
├── development-workflow.md
├── hardware-guide.md
├── deployment.md
├── faq.md
└── admin-guide.md
```

---

## 13. 迁移策略

### 13.1 从 SQLite 迁移到 Supabase

- 提供 `scripts/migrate_sqlite_to_supabase.py`。
- 将现有 SQLite 项目、任务、决策、artifacts 导入 PostgreSQL。
- 为所有项目设置一个默认 owner（命令行参数指定）。
- 学习记忆从 `learning_memory.json` 迁移到 `learning_records` / `failure_knowledge` / `success_knowledge` 表。

### 13.2 文件路径迁移

- 旧路径：`workspace/projects/{project_id}`
- 新路径：`workspace/users/{user_id}/projects/{project_id}`
- 迁移脚本在首次启动时检测旧路径并自动迁移。

---

## 14. 实施计划

| 阶段 | 任务 | 输出 |
|------|------|------|
| 1 | 搭建 Vite + React + TS 前端骨架 | `frontend/` 可运行 |
| 2 | 集成 Supabase Auth，实现登录注册 | Login/Register 页面 |
| 3 | FastAPI 接入 Supabase JWT 验证 | Auth middleware + `/api/auth/me` |
| 4 | 重构 Project DB 层为 Supabase 客户端 | `kyrozen/project/supabase_db.py` |
| 5 | 为所有项目 API 加 user_id 鉴权 | 多用户隔离可用 |
| 6 | 迁移 learning memory 到 DB 并按用户隔离 | 跨用户学习不泄露 |
| 7 | 实现产品状态机和 Next Action | `/api/projects/{id}/state` |
| 8 | 开发 Dashboard 和 Project Workspace | 产品化前端成型 |
| 9 | 实现反馈、事件、错误监控 | Beta 闭环 |
| 10 | Docker + docker-compose + .env 模板 | 一键部署 |
| 11 | 文档 + VERSION + Changelog | Beta 发布材料 |
| 12 | 测试覆盖（test_auth, test_multi_user, test_beta_flow） | 测试通过 |

---

## 15. 已知限制

- Beta 阶段暂不支持团队协作（单用户项目）。
- 暂不支持付费/配额系统（仅 Rate Limit）。
- 暂不提供 SLA 级别监控，仅基础错误日志。
- Supabase Storage 可选，Beta 阶段文件仍存本地卷。
- 不实现实时协作编辑。

---

## 16. 需要确认事项

1. 前端 UI 风格：沿用现有深色科技感，还是采用更中性的产品风格？
2. 域名/SSL：是否已有反向代理（Nginx/Caddy/Traefik）？
3. 服务器规格：CPU/内存是否足够同时运行 Supabase + Kyrozen？
4. Beta 范围：是否仅限邀请码注册，还是开放注册？

---

*本设计文档确认后，进入 Phase 10 实施阶段。*
