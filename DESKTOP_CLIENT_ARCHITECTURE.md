# Kyrozen Desktop Client 架构设计

## 1. 背景与目标

Kyrozen 未来将作为线上网站部署在服务器上。网站端适合处理无需本地资源的阶段（问题发现、市场调研、产品规划），而需要操作本地文件、终端、Git、硬件串口等能力时，需要用户在本地打开一个桌面客户端。

**目标**：设计一个安全、可扩展、与现有 Kyrozen Core 复用度高的桌面客户端架构。

## 2. 关键决策

| 维度                                       | 选型                                  | 原因                                                                 |
| ------------------------------------------ | ------------------------------------- | -------------------------------------------------------------------- |
| 客户端技术栈                               | Electron                              | 团队熟悉 Node.js 生态，开发效率高，可快速复用现有前端 React 代码     |
| 与服务端通信                               | WebSocket 长连接                      | 实时推送 Agent 输出、任务状态和高危操作确认请求                      |
| 从网站唤起客户端（也可以本地直接打开客户端） | 自定义 URL Scheme + 临时 JWT          | `kyrozen://open?project=xxx&token=xxx`，用户体验流畅，安全性可控    |
| 本地权限模型                               | 默认项目目录白名单 + 可选完全信任模式 | 默认安全，高级用户可按需开放                                         |
| 大模型调用                                 | 云端统一代理                          | 固定云端 API，未来按订阅制收费；本地不暴露密钥                       |
| Python 运行时                              | 客户端内置便携 Python + 预装依赖      | 零配置，首次启动即用                                                 |
| 客户端形态                                 | 完整独立应用                          | 可直接打开使用，也支持从网站唤起                                     |
| 用户代码存储                               | 本地为主，可选加密云端备份（付费会员） | 不默认占用云端空间；用户可自行用 GitHub 备份                         |
| 多设备在线                                 | 允许同时在线，任务推给最近活跃设备    | 用户体验最佳                                                         |
| 开机常驻                                   | 按需启动，不常驻                      | 尊重用户系统资源                                                     |
| Agent 编排                                 | 本地主导循环，云端只代理模型调用      | 最大程度复用现有 Kyrozen Core 代码                                   |
| 进度同步                                   | 实时同步每一步到网站                  | 网站端可看到完整本地执行过程                                         |
| 客户端更新                                 | 检测到新版本弹窗提示手动更新          | 平衡及时性与用户控制权                                               |

## 3. 用户流程

### 3.1 首次使用

#### 方式 A：从网站唤起

1. 用户访问 Kyrozen 网站，完成登录。
2. 进入项目后，点击「在本地打开」或「本地开发」。
3. 浏览器调用 `kyrozen://open?project_id=proj_xxx&token=eyJ...`。
4. 如果未安装客户端，网站引导下载安装包。
5. 客户端被唤起后，用临时 token 向服务端校验并换取长期会话（refresh token + WebSocket token）。
6. 客户端要求用户选择本地项目目录（默认：`~/KyrozenProjects/proj_xxx`）。
7. 客户端与服务端建立 WebSocket 连接，进入待命状态。

#### 方式 B：直接打开客户端

1. 用户安装后双击打开 Kyrozen 桌面客户端。
2. 提供两种登录方式：
   - **账号密码登录**：调用 `/api/auth/signin` 获取 token。
   - **扫码/确认登录**：客户端显示二维码或六位配对码，用户在已登录的网站确认后授权。
3. 登录成功后拉取云端项目列表，用户选择项目并指定本地工作目录。
4. 建立 WebSocket 连接，进入待命状态。

### 3.2 日常任务执行

1. 用户在网站端发送消息，如「生成代码并启动本地预览」。
2. 服务端根据项目阶段和消息内容，判断需要本地能力。
3. 服务端将该任务标记为 `requires_local_client`，通过 WebSocket 推送给对应客户端。
4. 本地客户端接收任务，使用本地 Agent Runtime 执行文件/终端/Git 等操作。
5. 执行过程中的步骤、日志、结果通过 WebSocket 实时回传服务端。
6. 服务端将结果同步给网站前端，用户看到完整对话记录。

### 3.3 高危操作确认

本地客户端在执行写入文件、终端命令、Git push 等操作前，弹出系统级确认对话框，显示：

- 工具名
- 动作
- 参数摘要
- 风险说明

用户确认后，操作才继续执行；取消则返回失败信息。

## 4. 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         Kyrozen 网站                            │
│  React + Zustand  (问题发现 / 市场调研 / 产品规划 / 查看状态)     │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTP / REST / SSE
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Kyrozen Cloud Backend                      │
│  FastAPI / Koa + Supabase + SQLite                              │
│  负责任务调度、用户会话、项目数据、聊天历史、Artifact 存储        │
└───────────────────────┬─────────────────────────────────────────┘
                        │ WebSocket (Agent 任务、状态、确认)
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Kyrozen Desktop Client                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Renderer    │  │   Electron   │  │   Python Agent       │  │
│  │  (React UI)  │◄─┤   Main       │◄─┤   Runtime            │  │
│  │              │  │   Process    │  │   (复用 Kyrozen Core)│  │
│  └──────────────┘  └──────┬───────┘  └──────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│              本地文件系统 / 终端 / Git / 浏览器 / 串口            │
└─────────────────────────────────────────────────────────────────┘
```

### 4.1 Electron 进程分工

| 进程                   | 职责                                                                                                                  |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Main Process           | 启动本地 HTTP/WebSocket 客户端、管理本地工作区、调用 Node.js 文件/终端 API、处理 `kyrozen://` 协议、系统通知与确认对话框 |
| Renderer Process       | 展示与网站端一致的 React UI，显示任务状态、日志、本地文件树、确认弹窗                                                   |
| Python Agent Runtime   | 直接复用 `kyrozen/core/agent.py`、`kyrozen/tools/*.py` 等后端代码，主导 Agent 运行循环，通过云端代理调用大模型         |

### 4.2 复用现有代码

桌面客户端应复用以下现有模块，避免重写：

- `kyrozen/core/agent.py`：BaseAgent 运行循环（本地主导）
- `kyrozen/core/permission.py`：权限检查
- `kyrozen/core/task.py`：任务状态管理
- `kyrozen/tools/*.py`：文件、终端、Git 等工具
- `kyrozen/models/*.py`：模型接口（需新增云端代理实现）
- `kyrozen/config.py`：配置加载

**推荐方式**：Electron 主进程通过 `child_process.spawn` 启动一个本地 Python Agent 服务，Renderer 通过 IPC 与主进程通信，主进程再与 Python 服务通信。

```
Renderer  <->  Electron Main  <->  Python Agent Service  <->  本地文件/终端
                  ▲                    │
                  │                    │ 模型请求/响应
                  │                    ▼
                  └────────── WebSocket Client <-> Cloud Backend (模型代理 + 任务调度)
```

### 4.3 云端模型代理

由于大模型调用统一走云端固定 API，本地 Agent 不再直接调用 DeepSeek/OpenAI，而是通过一个专用的 `CloudProxyModelProvider` 实现 `ModelInterface`：

1. 本地 Agent 调用 `model.chat(messages)`。
2. `CloudProxyModelProvider` 将 `messages` 通过 WebSocket 发送给云端 `/ws/model`。
3. 云端校验用户订阅状态和剩余额度后，调用固定的大模型 API。
4. 云端流式读取模型输出，通过 WebSocket 分段推送给本地客户端。
5. 本地客户端组装完整响应，返回给 `BaseAgent._run_loop`。

**订阅与配额**：云端在每次模型调用前检查用户套餐，返回配额不足错误时，本地 Agent 将错误信息展示给用户并引导升级。

## 5. 认证与安全

### 5.1 URL Scheme 唤起流程

```
1. 网站端调用 /api/desktop/open-token?project_id=xxx
2. 后端生成一次性短期 token（有效期 5 分钟，绑定 project_id + user_id）
3. 浏览器跳转 kyrozen://open?project_id=xxx&token=xxx
4. 客户端解析 token，调用 POST /api/desktop/verify-token
5. 后端返回长期 refresh_token 和 WebSocket 连接凭证
6. 客户端保存 credential，建立 WebSocket
```

### 5.2 WebSocket 认证

客户端在 WebSocket 握手时通过 query string 或首条消息发送 `ws_token`：

```json
{
  "type": "auth",
  "token": "ws_xxx"
}
```

服务端校验 token 并绑定 `user_id` + `client_id`，之后只向该客户端推送属于该用户的任务。

### 5.3 权限模型

#### 默认模式：项目目录白名单

- 客户端首次为项目选择本地根目录 `workspace_root`。
- 所有文件/终端工具通过 `_resolve_safe_path` 强制限制在该目录内。
- 禁止 `..` 路径逃逸、绝对路径越界。
- 以下操作需要弹窗确认：
  - 文件写入/覆盖/删除
  - 终端命令执行
  - Git commit / push
  - 网络请求类工具（如启动本地服务器）

#### 完全信任模式

- 用户在设置中明确开启，需二次确认并记录 Decision Record。
- 允许 Agent 访问用户指定的任意目录和命令。
- 服务端在 project 元数据中标记 `local_trust_mode: full`，便于审计。

## 6. 通信协议

WebSocket 消息格式统一为 JSON：

### 6.1 客户端 -> 服务端

```json
{
  "type": "auth",
  "token": "ws_xxx"
}
```

```json
{
  "type": "task_accepted",
  "task_id": "task_xxx",
  "client_id": "client_xxx"
}
```

```json
{
  "type": "task_step",
  "task_id": "task_xxx",
  "step": {
    "description": "Call terminal.execute",
    "status": "running",
    "metadata": {"tool": "terminal", "action": "execute", "parameters": {...}}
  }
}
```

```json
{
  "type": "task_result",
  "task_id": "task_xxx",
  "status": "completed",
  "result": {"answer": "本地预览已启动: http://localhost:8080"},
  "steps": [...]
}
```

```json
{
  "type": "confirmation_response",
  "task_id": "task_xxx",
  "confirmed": true
}
```

### 6.2 服务端 -> 客户端

```json
{
  "type": "assign_task",
  "task_id": "task_xxx",
  "project_id": "proj_xxx",
  "mode": "development",
  "message": "生成代码并启动本地预览",
  "requires_confirmation": true
}
```

```json
{
  "type": "request_confirmation",
  "task_id": "task_xxx",
  "tool": "terminal",
  "action": "execute",
  "parameters": {...},
  "reason": "该命令将在本地启动 HTTP 服务器"
}
```

```json
{
  "type": "cancel_task",
  "task_id": "task_xxx"
}
```

### 6.3 模型代理消息（本地 <-> 云端）

本地 Agent 调用模型时，通过 WebSocket 与云端模型代理交互：

**本地请求**：

```json
{
  "type": "model_request",
  "request_id": "req_xxx",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "stream": true
}
```

**云端流式推送**：

```json
{
  "type": "model_stream_chunk",
  "request_id": "req_xxx",
  "chunk": "我将",
  "finished": false
}
```

**云端完成/错误**：

```json
{
  "type": "model_stream_chunk",
  "request_id": "req_xxx",
  "chunk": "",
  "finished": true,
  "usage": {"prompt_tokens": 100, "completion_tokens": 50}
}
```

```json
{
  "type": "model_error",
  "request_id": "req_xxx",
  "error": "配额不足，请升级会员。"
}
```

### 6.4 设备心跳

```json
{
  "type": "heartbeat",
  "client_id": "client_xxx",
  "timestamp": "2026-07-24T12:00:00Z",
  "active_project_id": "proj_xxx"
}
```

## 7. 数据边界与云端存储

### 7.1 云端不存储的内容

为控制云端存储成本，用户实际创造的文件产物**默认不上传**：

- 本地生成的代码文件（`software/`、`hardware/`）
- 本地运行日志、编译产物
- 用户用 VS Code 等工具修改后的文件

### 7.2 云端存储的内容

- 用户账户与项目元数据
- 聊天历史与消息
- 任务记录与执行步骤
- 结构化 Artifact：Problem Brief、Market Research Report、Product Brief、PRD、Test Plan 等
- （付费会员可选）加密备份的本地项目快照

### 7.3 本地工作区结构

客户端本地目录与云端项目一一对应：

```
~/KyrozenProjects/
└── proj_xxx/
    ├── software/          # 代码产物（不上传云端）
    ├── hardware/          # 硬件相关（不上传云端）
    ├── documents/         # 本地缓存的文档
    ├── logs/              # 本地运行日志
    └── .kyrozen/          # 客户端元数据、缓存、session、云端 Artifact 副本
```

客户端启动时同步云端 Artifact（如 PRD、Product Brief）到本地 `.kyrozen/context/`，供本地 Agent 使用。

### 7.4 敏感信息与 Git 工作流

**敏感信息处理**：Agent 生成代码时若需要 API Key、数据库密码等，必须：

1. 生成 `.env.example` 文件，内含占位符和填写说明。
2. 弹出警告对话框，提示用户将 `.env.example` 复制为 `.env` 并填入真实值。
3. `.env` 文件默认加入 `.gitignore`，避免误提交。

**GitHub 集成**：Kyrozen 不强制使用 GitHub，但提供可选引导：

1. 用户在项目设置中授权 GitHub OAuth 或手动输入仓库地址。
2. 客户端可帮用户 `git init`、设置 remote、生成初始 commit。
3. 提供「一键 commit + push」按钮，由用户决定是否执行。
4. 默认不自动 push；用户可在设置中开启自动 commit/push。

**灾难恢复**：
- 免费用户：依赖自己的 GitHub/GitLab 仓库恢复代码。
- 付费会员：可选加密云端备份本地项目快照，重装客户端后可下载恢复。

## 8. 任务状态流转

```
云端创建任务 -> 标记 requires_local_client -> 查询用户在线客户端
                                  |
                                  ▼
                    推送给最近活跃的客户端
                                  |
                                  ▼
                    客户端接受并执行 -> 实时上报 step/result
                                  |
                                  ▼
                    任务完成/失败/取消 -> 云端更新 -> 网站端展示
```

**多设备路由**：

- 云端维护每个用户的客户端在线列表（`client_id`、`last_active_at`、`device_name`）。
- 新任务默认推送给 `last_active_at` 最新的设备。
- 如果该设备不接受或超时，可回退到下一台设备，或提示用户在网站端手动选择。

**实时进度同步**：

- 本地 Agent 每执行一步，立即通过 WebSocket 发送 `task_step`。
- 网站端在聊天中显示「正在执行 terminal.execute...」等进度。
- 工具返回结果后，本地 Agent 继续循环，同时将结果摘要上报。

**如果客户端不在线**：

- 网站端提示「需要本地客户端才能执行此任务，请先打开客户端」。
- 用户可选择将任务加入队列，客户端上线后自动拉取。

## 9. 确认对话框 UX

高危操作触发时，客户端弹出模态框：

```
┌─────────────────────────────────────┐
│ Kyrozen 请求执行以下操作             │
├─────────────────────────────────────┤
│ 工具:   terminal                     │
│ 动作:   execute                      │
│ 命令:   python -m http.server 8080   │
│ 目录:   ~/KyrozenProjects/proj_xxx   │
├─────────────────────────────────────┤
│ [ 取消 ]              [ 确认执行 ]   │
└─────────────────────────────────────┘
```

对于批量操作（如生成多个文件），可合并为一个「本次会话信任该 Agent」的选项，但默认每次仍需确认。

## 10. 打包与分发

| 平台      | 方案                                                     |
| ------- | ------------------------------------------------------ |
| macOS   | `electron-builder` 打包 dmg/zip，支持 Apple Silicon + Intel |
| Windows | `electron-builder` 打包 nsis/exe                         |
| Linux   | AppImage / deb（可选）                                     |
| 自动更新    | 接入 electron-updater，从服务器拉取最新版本                         |

安装时注册自定义 URL Scheme：

- macOS: `Info.plist` 中注册 `CFBundleURLTypes`
- Windows: 注册表写入 `kyrozen` protocol

## 11. 安全与合规清单

- [ ] 所有本地文件操作限制在项目白名单目录内。
- [ ] 终端命令禁止 `rm -rf /`、`sudo`、`ssh` 等危险模式。
- [ ] 高危操作必须弹窗确认，不可静默执行。
- [ ] WebSocket token 短期有效，支持服务端强制断开。
- [ ] 临时唤起 token 一次性使用，绑定 user_id + project_id。
- [ ] 用户开启完全信任模式需记录 Decision Record。
- [ ] 本地 credential 加密存储（使用系统 keychain）。
- [ ] 客户端与服务端通信强制 TLS/WSS。
- [ ] 模型调用前校验用户订阅套餐和剩余额度，防止超额使用。
- [ ] 完全信任模式下所有操作日志回传云端审计。
- [ ] 更新包需签名验证，防止中间人攻击。

## 12. 实施建议（第一阶段 MVP）

### 12.1 服务端改造

1. 新增 `/api/desktop/open-token` 与 `/api/desktop/verify-token` 接口。
2. 新增 `/ws/desktop` WebSocket endpoint，支持设备认证、心跳、任务分发、模型代理。
3. 实现 `CloudProxyModelProvider`，封装固定大模型 API 并接入订阅配额检查。
4. 新增 `clients` 表/集合，记录在线设备、最后活跃时间、当前项目。
5. 调整任务调度逻辑：当任务需要本地能力时，标记 `requires_local_client` 并推送给最近活跃设备。

### 12.2 桌面客户端开发

1. 创建 `desktop/` 目录，初始化 Electron + Vite + React 项目。
2. 打包内置便携 Python + 预装 `requirements.txt` 依赖。
3. 实现 `kyrozen://` 协议解析与临时 token 校验。
4. 实现账号密码登录和扫码/配对码登录两种入口。
5. 实现 WebSocket 客户端连接、认证、心跳保活、断线重连。
6. 复用现有 Python Agent：通过 `child_process.spawn` 启动本地 Agent 服务，替换模型提供者为 `CloudProxyModelProvider`。
7. 实现文件/终端工具的白名单限制和确认对话框。
8. 打通网站端「在本地打开」按钮与客户端唤起。
9. 实现系统托盘/状态窗口（按需启动，不常驻）。
10. 实现 `.env.example` 自动生成与敏感信息警告。
11. 实现可选的 Git init + push 引导。
12. 实现更新检测与手动更新弹窗。

### 12.3 端到端验证

在 development 阶段完成第一个完整流程：

1. 网站端发送指令「为 AI 待办事项助手生成前端代码并启动本地预览」。
2. 云端将任务标记为需要本地客户端并推送。
3. 本地客户端接收任务，Agent 通过云端代理调用大模型。
4. Agent 生成本地文件，执行 terminal 启动 HTTP 服务器（用户确认）。
5. 本地客户端自动选择端口，回传 `http://localhost:PORT` 到网站端。
6. 网站端显示预览链接，用户可在浏览器打开。

## 13. 已确认问题汇总

| 问题 | 决策 |
|------|------|
| 离线工作 | AI 任务必须联网；用户可离线手动编辑本地文件 |
| 多用户共用一台电脑 | 当前登录账户只能访问自己的项目 |
| 完全信任模式日志 | 所有操作日志必须回传云端审计 |
| 本地预览端口 | 客户端自动选择可用端口 |
| 大模型调用 | 云端统一代理，固定 API，未来订阅制收费 |
| Python 运行时 | 客户端内置便携 Python + 预装依赖 |
| 客户端形态 | 完整独立应用，也可从网站唤起 |
| 用户代码存储 | 本地为主，付费会员可选加密云端备份 |
| Agent 编排 | 本地主导循环，云端仅代理模型调用 |
| 进度同步 | 实时同步每一步到网站 |
| 登录方式 | 账号密码 + 扫码/配对码两种方式 |
| GitHub 集成 | 可选引导，自动 commit/push 由用户决定 |
| 多设备任务分发 | 推送给最近活跃的客户端 |
| 客户端更新 | 检测到新版本后弹窗提示手动更新 |
| 敏感信息 | 生成 `.env.example` 并弹窗警告用户填写 |

