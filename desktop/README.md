# Kyrozen Desktop Client

Kyrozen 桌面客户端是 Kyrozen 网站部署后在用户本地执行 Agent 的配套应用。它负责操作本地文件、运行终端命令、执行 Git 操作、烧录硬件等与本地环境强相关的任务，同时通过 WebSocket 与云端保持实时同步。

## 1. 定位

- 网站端：处理无需本地资源的阶段，例如问题发现、市场调研、产品规划。
- 桌面端：处理需要本地资源的高权限阶段，例如软件开发、硬件开发、测试验证。

用户既可以直接打开客户端使用，也可以从网站点击「在本地打开」通过 `kyrozen://` URL Scheme 唤起客户端。

## 2. 技术栈

| 层级 | 技术 |
| --- | --- |
| 桌面壳 | Electron + Vite + React + TypeScript |
| 渲染进程 UI | AI 对话界面为主，类似 Codex / Claude Code |
| 主进程 | Node.js（文件选择、窗口管理、系统托盘、外部浏览器打开） |
| 本地 Agent | Python（复用 Kyrozen Core） |
| 主进程 ↔ Agent | stdio JSON-RPC |
| 客户端 ↔ 云端 | WebSocket（认证、任务分发、状态同步、模型代理） |
| 样式 | Tailwind CSS |

## 3. 目录结构

```
desktop/
├── electron/            # Electron 主进程与预加载脚本
│   ├── main.ts          # 主进程入口：窗口、托盘、WebSocket、Python Agent 生命周期
│   └── preload.ts       # 预加载脚本，暴露安全的 IPC API 给渲染进程
├── python_agent/        # 本地 Python Agent（stdio JSON-RPC 服务端）
│   └── main.py          # Agent 入口：接收任务、驱动 Kyrozen Core、返回结果
├── src/                 # 渲染进程 React 应用
│   ├── App.tsx          # 路由与全局状态
│   ├── main.tsx         # React 挂载点
│   ├── components/      # 可复用组件
│   └── pages/           # 页面：登录、对话
├── package.json         # Electron + Vite 构建配置
├── vite.config.ts       # Vite + vite-plugin-electron 配置
└── README.md            # 本文档
```

## 4. 开发环境

前置要求：

- Node.js 18+
- Python 3.10+（用于本地 Agent 开发调试）
- 已安装 Kyrozen 后端服务并在 `http://localhost:8000` 运行

安装依赖：

```bash
cd desktop
npm install
```

## 5. 运行开发版

```bash
cd desktop
npm run dev
```

该命令会同时启动：

1. Vite 开发服务器（渲染进程 HMR）
2. Electron 主进程
3. 主进程自动启动本地 Python Agent

开发时可以直接修改 `src/` 下的 React 代码，页面会热更新。修改 `electron/` 或 `python_agent/` 后需要重启 Electron。

## 6. 核心流程

### 6.1 登录与连接

1. 用户在登录页输入账号密码，或直接通过 `kyrozen://` 唤起。
2. 主进程调用后端 `/api/auth/signin` 获取 access token。
3. 主进程调用 `/api/desktop/verify-token` 校验 token 并换取 WebSocket token。
4. 主进程使用 WebSocket token 连接 `/ws/desktop`。
5. 连接成功后，客户端进入待命状态，等待云端派发任务。

### 6.2 任务执行

1. 云端通过 WebSocket 发送 `assign_task` 消息。
2. 主进程将任务通过 stdio JSON-RPC 转发给 Python Agent。
3. Python Agent 运行 Kyrozen Core，操作本地文件/终端/Git/硬件。
4. Agent 每完成一个步骤，返回进度给主进程。
5. 主进程将进度实时回传给云端，并在 UI 中展示。

### 6.3 模型调用

本地 Agent 不直接调用模型 API，而是通过 WebSocket 发送 `model_request` 给云端。云端 `CloudProxyModelProvider` 统一代理模型调用并返回结果，便于：

- 不在客户端暴露 API 密钥
- 统一计费和订阅配额控制
- 支持流式响应

### 6.4 本地工作目录

每个项目首次在桌面端操作时，客户端会弹出目录选择对话框，默认路径为 `~/KyrozenProjects/{project_id}`。选择后路径会持久化到 `userData/workspaces.json`，后续同一项目自动使用已选目录。

## 7. 构建与打包

```bash
cd desktop
npm run build
```

构建产物：

- `dist/`：渲染进程静态资源
- `dist-electron/`：Electron 主进程与预加载脚本编译输出
- `release/`：最终安装包（按平台生成 dmg / nsis / AppImage）

注意：当前 macOS 未配置 Apple Developer 签名，Windows 尝试使用免费签名方案。

## 8. 安全说明

- 文件与终端操作被限制在项目工作目录内，禁止访问外部绝对路径。
- 高危操作（文件写入、终端执行、Git 提交推送）默认需要确认；桌面端可通过配置调整为自动允许同一会话内的操作。
- WebSocket 使用临时 token 认证，token 通过 `kyrozen://` Scheme 一次性传递。
- 模型密钥和订阅状态由云端管理，客户端不保存密钥。

## 9. 已知限制

- Python Agent 的确认对话框响应尚未完全集成到 Agent 运行时循环。
- 本地预览和内置文件编辑器仅提供基础辅助功能。
- Electron 窗口需要 GUI 环境，无法在无头服务器上运行。

## 10. 相关文档

- [DESKTOP_CLIENT_ARCHITECTURE.md](../DESKTOP_CLIENT_ARCHITECTURE.md)：完整架构设计与决策记录
- [kyrozen/desktop/cloud_proxy.py](../kyrozen/desktop/cloud_proxy.py)：云端模型代理实现
- [kyrozen/api/server.py](../kyrozen/api/server.py)：后端 WebSocket 与桌面客户端 API
