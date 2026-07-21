# Kyrozen Phase 1 交付报告

## 1. Architecture（架构说明）

Phase 1 的目标是在 Kyrozen 仓库中建立 **Kyrozen Core** —— 所有未来专业 Agent（Problem Discovery、Market Research、Product Management、Software Engineering、Hardware Engineering 等）的运行基础层。

```
Browser
   |
   ↓
Web Interface  (kyrozen/web/index.html)
   |
   ↓
Kyrozen API    (kyrozen/api/server.py — FastAPI)
   |
   ↓
Kyrozen Core
   |-------------------------
   |          |             |
Runtime    Model Layer   Tool Layer
   |          |             |
Task Layer Memory       Registry
   |
Logs / Storage
```

### 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| Agent Runtime | `kyrozen/core/agent.py` | BaseAgent：接收任务、调用模型、解析并执行工具、管理多轮循环、返回结果 |
| Model Layer | `kyrozen/models/base.py`、`providers.py` | 统一模型接口，支持 OpenAI/DeepSeek/Ollama/Anthropic/Google，封装 chat、streaming、token/cost 统计、retry |
| Tool Layer | `kyrozen/tools/base.py`、`registry.py` | 工具基类、Schema、参数验证、注册中心；Phase 1 实现 file_read/file_write/list_dir/find_files/terminal/git |
| Task Manager | `kyrozen/core/task.py` | 任务创建、状态流转、步骤记录、JSON 持久化 |
| Permission | `kyrozen/core/permission.py` | strict / permissive 模式，区分低风险与高风险操作，支持用户确认 |
| Memory | `kyrozen/memory/interface.py` | save/query/update/delete 抽象接口，当前为 InMemoryMemory |
| Logging | `kyrozen/logs/logger.py` | 结构化日志，记录 user/agent/model/tool/error/perf 事件 |
| Config | `kyrozen/config/settings.py` | 统一配置，读取环境变量与配置文件，管理 provider/api_key/权限模式等 |
| Web API | `kyrozen/api/server.py` | FastAPI REST API：/api/chat、/api/tasks、/api/tools、/api/health 等 |
| Web UI | `kyrozen/web/index.html` | 单页测试控制台：输入任务、显示执行过程、步骤跟踪、高风险确认 |

---

## 2. OpenKyrozen 学习结果

参考仓库：`https://github.com/EvanProgramming/OpenKyrozen`

### 参考并采用的设计

| OpenKyrozen 设计 | Kyrozen Core 对应实现 | 采用原因 |
|------------------|----------------------|----------|
| 多模型 Provider 抽象 | `kyrozen/models/base.py` + `providers.py` | 避免业务代码直接调用 `call_openai()`，支持未来多供应商切换 |
| 工具注册与 Schema | `kyrozen/tools/base.py` + `registry.py` | 统一工具接口，便于后续扩展 Web Search、Hardware Bridge 等 |
| 任务 / 会话状态 | `kyrozen/core/task.py` | 长期任务需要状态、步骤、结果、错误记录 |
| 权限分级（高风险确认） | `kyrozen/core/permission.py` | 写文件、执行命令、Git 操作需要用户确认 |
| FastAPI + Web UI 测试入口 | `kyrozen/api/server.py` + `kyrozen/web/index.html` | Phase 1 用 Web 形式验证 Core 能力 |
| 结构化日志 / Audit | `kyrozen/logs/logger.py` | 用于 Debug 与后续自学习 |

### 重新设计或改进的部分

| OpenKyrozen 方式 | Kyrozen Core 方式 | 原因 |
|------------------|-------------------|------|
| 工具参数使用字符串拼接（如 `path\|content`） | 结构化 JSON Schema + 参数验证 | 更符合现代 LLM function calling 规范，减少解析错误 |
| 工具调用格式依赖特定字符串解析 | 支持纯 JSON、```json 代码块、带前言的 inline JSON | 提高对不同模型输出格式的兼容性 |
| 单文件大 Agent | 模块化分层（core / models / tools / memory / logs） | 便于后续专业 Agent 继承 BaseAgent 扩展 |
| 单一 MemoryBank（ChromaDB 为主） | 抽象 MemoryInterface + InMemoryMemory | Phase 1 只定义接口，未来可接入 ChromaDB/向量库 |

### 未采用的部分

- OpenKyrozen 中的自学习循环、自动代码修改与提交策略：Phase 1 以可观测、可控制为主，避免 Agent 自主执行高风险操作。
- 语音、MCP、Plugin 系统：属于后续阶段扩展能力。

---

## 3. Web Interface 说明

### 启动方式

```bash
# 1. 进入项目目录
cd /Users/evangong/Documents/Programming/AI/Kyrozen

# 2. 安装依赖（如未安装）
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 设置模型 API Key
export DEEPSEEK_API_KEY=sk-82fb3d51cf0748789062ca74ae4e985a
# 或使用 OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY

# 4. 启动服务
.venv/bin/uvicorn kyrozen.api.server:app --host 127.0.0.1 --port 8000
```

### 访问与测试

1. 打开浏览器访问 `http://127.0.0.1:8000`
2. 在输入框中输入任务，例如：
   - `分析当前项目目录，列出所有Python文件和README`
   - `读取 requirements.txt 并说明用途`
3. 点击「发送」或按 Enter
4. 右侧面板会显示：
   - 任务 ID
   - 实时状态（Thinking... / Calling tool... / Completed / Failed）
   - 每个工具调用的步骤与结果
5. 当 Agent 请求写文件、执行命令等高风险操作时，页面会弹出确认框，用户可选择「确认执行」或「拒绝」

### 主要 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 返回 Web 测试控制台 |
| `/api/chat` | POST | 发送任务，返回 task_id 与 status |
| `/api/tasks` | GET | 列出所有任务 |
| `/api/tasks/{id}` | GET | 获取任务详情 |
| `/api/tasks/{id}/confirm` | POST | 确认或拒绝高风险操作 |
| `/api/tools` | GET | 列出可用工具 |
| `/api/tools/execute` | POST | 直接执行某个工具 |
| `/api/health` | GET | 健康检查 |
| `/api/config` | GET | 当前配置（不含 API key） |

---

## 4. Test Result

### 运行方式

```bash
.venv/bin/python -m pytest tests/ -v
```

### 结果

```
platform darwin -- Python 3.12.13, pytest-9.1.1

collected 38 items

tests/test_agent.py ......                                   [ 18%]
tests/test_api.py ........                                   [ 39%]
tests/test_config.py ....                                    [ 50%]
tests/test_memory.py ...                                     [ 59%]
tests/test_permission.py ....                                [ 68%]
tests/test_task.py ....                                      [ 78%]
tests/test_tools.py .......                                  [100%]

======================== 38 passed ========================
```

### 测试覆盖范围

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_config.py` | 默认配置、验证缺失 API key、从环境变量读取 |
| `test_permission.py` | strict / permissive 模式、高风险确认 |
| `test_task.py` | 任务生命周期、失败、JSON 持久化 |
| `test_memory.py` | save/query/update/delete |
| `test_tools.py` | file_read/file_write/list_dir/find_files/terminal 及注册表 |
| `test_agent.py` | BaseAgent 直接回答、工具调用、等待确认、inline JSON 提取 |
| `test_api.py` | FastAPI 端点：UI、health、chat、任务查询、工具执行、确认/拒绝 |

### 端到端验证

使用真实 DeepSeek API 进行端到端测试：

- 请求：`分析当前项目目录，列出所有Python文件和README`
- 结果：Agent 正确调用 `list_dir` 与 `find_files` 工具，最终返回包含 29 个 Python 文件与 README 的结构化分析报告。

---

## 5. Limitations（当前限制）

Phase 1 明确不包含以下内容，这些将在后续阶段实现：

- **产品流程**：Problem Discovery、Market Research、PRD 生成、BOM、Roadmap 等专业 Agent
- **项目空间**：多项目、Workspace、用户隔离
- **硬件能力**：Arduino / ESP32 / CAD / PCB / Hardware Bridge
- **高级 Memory**：向量检索、User Memory、Project Memory、Knowledge Memory、Failure Memory 的持久化实现
- **Web Search**：当前 Tool 系统已预留接口，但尚未实现
- **流式输出**：ModelInterface 已定义 `chat_stream`，但 Web UI 当前使用轮询任务状态
- **Plugin 系统**：未实现

---

## 6. Phase 2 准备

Project Workspace 与后续专业 Agent 需要依赖以下已完成的接口：

| 依赖接口 | 当前状态 | 说明 |
|----------|----------|------|
| `BaseAgent` | 已完成 | 所有专业 Agent 的基类 |
| `ModelInterface` | 已完成 | 专业 Agent 统一调用 LLM |
| `ToolRegistry` / `Tool` | 已完成 | 可扩展新工具（Web Search、Hardware Bridge、CAD 等） |
| `TaskManager` / `Task` | 已完成 | 长周期任务状态与持久化 |
| `PermissionManager` | 已完成 | 高风险操作确认 |
| `MemoryInterface` | 已完成（InMemoryMemory） | Phase 2 可替换为 ChromaDB / 向量存储 |
| `KyrozenLogger` | 已完成 | 全流程可观测 |
| REST API | 已完成 | Workspace 可在此基础上扩展项目、用户、会话管理 |

### 下一步建议

1. **Project Workspace**：在 API 层增加 `/api/projects`、项目目录隔离、任务与项目关联。
2. **Memory 持久化**：实现基于 ChromaDB 的向量 Memory。
3. **专业 Agent**：继承 `BaseAgent`，实现 `ProblemDiscoveryAgent`、`MarketResearchAgent` 等。
4. **Web Search Tool**：接入搜索 API。
5. **流式 UI**：在 Web 界面增加 SSE 流式输出。

---

*报告生成时间：2026-07-21*
*Kyrozen Phase 1 已完成并验证通过。*
