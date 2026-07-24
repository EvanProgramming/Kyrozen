# Kyrozen Desktop Client 架构设计

## 1. 背景与目标

Kyrozen 未来将作为线上网站部署在服务器上。网站端适合处理无需本地资源的阶段（问题发现、市场调研、产品规划），而需要操作本地文件、终端、Git、硬件串口等能力时，需要用户在本地打开一个桌面客户端。

**目标**：设计一个安全、可扩展、与现有 Kyrozen Core 复用度高的桌面客户端架构。

## 2. 关键决策

| 维度 | 选型 | 原因 |
|------|------|------|
| 客户端技术栈 | Electron | 团队熟悉 Node.js 生态，开发效率高，可快速复用现有前端 React 代码 |
| 与服务端通信 | WebSocket 长连接 | 实时推送 Agent 输出、任务状态和高危操作确认请求 |
| 从网站唤起客户端 | 自定义 URL Scheme + 临时 JWT | `kyrozen://open?project=xxx&token=xxx`，用户体验流畅，安全性可控 |
| 本地权限模型 | 默认项目目录白名单 + 可选完全信任模式 | 默认安全，高级用户可按需开放 |

## 3. 用户流程

### 3.1 首次使用

1. 用户访问 Kyrozen 网站，完成登录。
2. 进入项目后，点击「在本地打开」或「本地开发」。
3. 浏览器调用 `kyrozen://open?project_id=proj_xxx&token=eyJ...`。
4. 如果未安装客户端，网站引导下载安装包。
5. 客户端被唤起后，用临时 token 向服务端校验并换取长期会话（refresh token + WebSocket token）。
6. 客户端要求用户选择本地项目目录（默认：`~/KyrozenProjects/proj_xxx`）。
7. 客户端与服务端建立 WebSocket 连接，进入待命状态。

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
│  │  Renderer    │  │   Electron   │  │   Node.js Agent      │  │
│  │  (React UI)  │◄─┤   Main       │◄─┤   Runtime            │  │
│  │              │  │   Process    │  │   (复用 Kyrozen Core)│  │
│  └──────────────┘  └──────┬───────┘  └──────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│              本地文件系统 / 终端 / Git / 浏览器 / 串口            │
└─────────────────────────────────────────────────────────────────┘
```

### 4.1 Electron 进程分工

| 进程 | 职责 |
|------|------|
| Main Process | 启动本地 HTTP/WebSocket 客户端、管理本地工作区、调用 Node.js 文件/终端 API、处理 `kyrozen://` 协议、系统通知与确认对话框 |
| Renderer Process | 展示与网站端一致的 React UI，显示任务状态、日志、本地文件树、确认弹窗 |
| Node.js Agent Runtime | 直接复用 `kyrozen/core/agent.py`、`kyrozen/tools/*.py` 等后端代码，作为本地子进程或主进程内的模块运行 |

### 4.2 复用现有代码

桌面客户端应复用以下现有模块，避免重写：
- `kyrozen/core/agent.py`：BaseAgent 运行循环
- `kyrozen/core/permission.py`：权限检查
- `kyrozen/core/task.py`：任务状态管理
- `kyrozen/tools/*.py`：文件、终端、Git 等工具
- `kyrozen/models/*.py`：模型接口
- `kyrozen/config.py`：配置加载

客户端将这些模块运行在本地 Node.js（通过 Python 子进程）或直接内嵌 Python 运行时（如 `python-shell`、`pyodide` 不推荐）。

**推荐方式**：Electron 主进程通过 `child_process.spawn` 启动一个本地 Python Agent 服务，Renderer 通过 IPC 与主进程通信，主进程再与 Python 服务通信。

```
Renderer  <->  Electron Main  <->  Python Agent Service  <->  本地文件/终端
                  ▲                                            │
                  └────────── WebSocket Client <-> Cloud Backend
```

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

## 7. 本地工作区结构

客户端本地目录与云端项目一一对应：

```
~/KyrozenProjects/
└── proj_xxx/
    ├── software/          # 代码产物
    ├── hardware/          # 硬件相关
    ├── documents/         # 本地缓存的文档
    ├── logs/              # 本地运行日志
    └── .kyrozen/          # 客户端元数据、缓存、session
```

客户端启动时同步云端 Artifact（如 PRD、Product Brief）到本地 `.kyrozen/context/`，供本地 Agent 使用。

## 8. 任务状态流转

```
云端创建任务 -> 标记 requires_local_client -> 推送给在线客户端
                                  |
                                  ▼
                    客户端接受并执行 -> 实时上报 step/result
                                  |
                                  ▼
                    任务完成/失败/取消 -> 云端更新 -> 网站端展示
```

如果客户端不在线：
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

| 平台 | 方案 |
|------|------|
| macOS | `electron-builder` 打包 dmg/zip，支持 Apple Silicon + Intel |
| Windows | `electron-builder` 打包 nsis/exe |
| Linux | AppImage / deb（可选） |
| 自动更新 | 接入 electron-updater，从服务器拉取最新版本 |

安装时注册自定义 URL Scheme：
- macOS: `Info.plist` 中注册 `CFBundleURLTypes`
- Windows: 注册表写入 `kyrozen` protocol

## 11. 安全清单

- [ ] 所有本地文件操作限制在项目白名单目录内。
- [ ] 终端命令禁止 `rm -rf /`、`sudo`、`ssh` 等危险模式。
- [ ] 高危操作必须弹窗确认，不可静默执行。
- [ ] WebSocket token 短期有效，支持服务端强制断开。
- [ ] 临时唤起 token 一次性使用，绑定 user_id + project_id。
- [ ] 用户开启完全信任模式需记录 Decision Record。
- [ ] 本地 credential 加密存储（使用系统 keychain）。
- [ ] 客户端与服务端通信强制 TLS/WSS。

## 12. 实施建议（第一阶段 MVP）

1. 创建 `desktop/` 目录，初始化 Electron + Vite + React 项目。
2. 实现 `kyrozen://` 协议解析与临时 token 校验。
3. 实现 WebSocket 客户端连接与心跳保活。
4. 复用现有 Python Agent，通过 `child_process` 在本地运行。
5. 实现文件/终端工具的白名单限制和确认对话框。
6. 打通网站端「在本地打开」按钮与客户端唤起。
7. 在开发阶段（development）完成第一个端到端流程：网站发送指令 -> 客户端生成代码 -> 启动本地预览 -> 回传 URL。

## 13. 待确认问题

- 本地客户端是否需要离线工作？即无网络时仍可编辑文件，联网后同步。
- 是否支持一台电脑同时处理多个用户的多个项目？
- 完全信任模式下，是否还需要记录所有操作日志到云端？
- 本地预览的端口分配由客户端自动选择还是固定端口？
