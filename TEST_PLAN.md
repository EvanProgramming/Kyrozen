# Kyrozen Phase 1/2/3 全面验证测试计划

## 1. 测试目标

对 Kyrozen 已完成的三个阶段（Core / Project Workspace / Problem Discovery）进行系统性验证，确保：

- 各阶段功能符合需求规格
- 系统性能达到预期指标
- 在指定环境（Python 3.12 + macOS）中稳定运行
- 不存在高危安全漏洞
- 缺陷被记录、修复并经过回归测试验证

## 2. 测试环境

| 项目 | 值 |
|------|-----|
| OS | macOS |
| Python | 3.12.13（项目虚拟环境 `.venv`） |
| 测试框架 | pytest 9.1.1 |
| Web 框架 | FastAPI 0.110+ / uvicorn |
| 浏览器 | Chrome / Safari（Web UI 为纯 HTML/CSS/JS） |
| 模型 Provider | mock / deepseek / openai（按需） |

## 3. 测试范围

### 3.1 Phase 1 — Kyrozen Core

| 模块 | 测试重点 |
|------|----------|
| Agent Runtime | 任务状态流转、工具调用解析、等待确认、inline JSON 提取 |
| Model Interface | 多 Provider 初始化、chat/chat_stream 接口、token/cost 统计 |
| Tool System | Schema 验证、参数校验、注册表、执行结果封装 |
| Task Manager | 任务生命周期、JSON/SQLite 持久化、失败处理 |
| Permission | strict/permissive 模式、高风险确认、拒绝后任务状态 |
| Memory | save/query/update/delete、metadata filters |
| Config | 默认值、环境变量优先、缺失 API key 检测 |
| API / Web | health、chat、tasks、tools、确认框、UI 服务 |

### 3.2 Phase 2 — Project Workspace

| 模块 | 测试重点 |
|------|----------|
| Project Entity | 字段验证、状态/阶段约束、to_dict/from_dict |
| SQLite Database | CRUD、外键级联删除、任务 project_id 持久化 |
| Project Manager | 项目 CRUD、Decision、Artifact 版本、项目隔离 |
| JsonFileMemory | 持久化、category/query/filter、ProjectMemory 自动 scope |
| Context Builder | 项目信息/任务/决策/记忆组装、discovery context |
| Project API | `/api/projects/*`、聊天上下文注入、多项目隔离 |
| Web UI | 项目列表/详情/聊天视图切换、hash 路由 |

### 3.3 Phase 3 — Problem Discovery

| 模块 | 测试重点 |
|------|----------|
| Problem Brief | 字段验证、合并、to_dict/from_dict |
| Evidence | 来源标记、verified 状态、可信度评估 |
| Question Engine | 缺失维度识别、优先级、下一步问题生成 |
| Discovery Agent | Prompt 禁止产品/市场调研、工具调用 |
| Discovery Tools | save_problem_brief、record_evidence、assess_confidence、record_problem_decision |
| Discovery API | `/api/chat?mode=discovery`、state 端点 |
| Web UI | Discovery 视图、Problem Brief 预览、下一步问题、未验证假设 |
| 场景测试 | 模糊问题 / 产品想法 / 无需开发 |

## 4. 测试类型与用例

### 4.1 功能测试

执行全部已有单元测试与集成测试：

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```

覆盖文件：

- `test_agent.py`：Phase 1 Agent Runtime
- `test_api.py`：Phase 1 API
- `test_config.py`：配置
- `test_memory.py`：InMemoryMemory
- `test_permission.py`：权限
- `test_task.py`：任务管理
- `test_tools.py`：工具系统
- `test_project.py`：Phase 2 Project Manager
- `test_project_db.py`：SQLite
- `test_project_context.py`：上下文
- `test_json_memory.py`：文件 Memory
- `test_api_project.py`：Project API
- `test_discovery.py`：Phase 3 Problem Discovery

### 4.2 性能测试

| 用例 ID | 目标 | 方法 | 通过标准 |
|---------|------|------|----------|
| PERF-01 | API 响应时间 | TestClient 调用 `/api/chat` 100 次取均值 | p95 < 200ms（mock 模型） |
| PERF-02 | 项目列表查询 | 创建 50 个项目后 GET `/api/projects` | < 100ms |
| PERF-03 | Memory 查询 | 写入 1000 条记录后按 category 查询 | < 100ms |
| PERF-04 | Artifact 版本链 | 同一类型保存 20 个版本后读取最新 | < 50ms |

### 4.3 兼容性测试

| 用例 ID | 目标 | 方法 | 通过标准 |
|---------|------|------|----------|
| COMP-01 | Python 版本 | 使用项目 `.venv` Python 3.12 运行全部测试 | 全部通过 |
| COMP-02 | Provider 切换 | mock / openai / deepseek 配置初始化 | 不报错 |
| COMP-03 | Web UI 浏览器 | 检查 index.html 不使用仅 Chrome/Safari 支持的实验性 API | 无 `document.browsingTopics` 等仅 Chrome API |
| COMP-04 | 路径分隔符 | 在 macOS `/` 路径下运行 file_tools 测试 | 通过 |

### 4.4 安全性测试

| 用例 ID | 目标 | 方法 | 通过标准 |
|---------|------|------|----------|
| SEC-01 | SQL 注入防护 | 项目名称/描述包含 `'"; DROP TABLE` 后创建项目并查询 | 数据正常，无异常/删除 |
| SEC-02 | 路径遍历防护 | file_read 传入 `../etc/passwd` | 被拒绝或返回 not found |
| SEC-03 | 高风险操作确认 | strict 模式下调用 file_write/terminal | 任务进入 waiting_confirmation |
| SEC-04 | API key 不泄露 | `/api/config` 返回值 | 不含 api_key |
| SEC-05 | 项目隔离 | 项目 A 的任务/决策/产物不会出现在项目 B | 断言隔离 |
| SEC-06 | 非法 Artifact 类型 | 保存不在允许列表中的 artifact type | 视实现而定，记录行为 |

### 4.5 端到端场景测试

| 用例 ID | 场景 | 输入 | 期望 |
|---------|------|------|------|
| E2E-01 | 模糊问题 | "我觉得房间很吵" | Agent 询问场景、当前方案、深层需求，不设计产品 |
| E2E-02 | 产品想法 | "我想做一个 AI 眼镜" | Agent 追问为什么需要、遇到什么问题，不直接设计硬件 |
| E2E-03 | 无需开发 | "我想每天提醒自己喝水" | Agent 指出手机闹钟/日历等现有简单方案 |
| E2E-04 | 重新打开项目 | 关闭页面后重新进入 Discovery | Problem Brief 和问答历史恢复 |

## 5. 缺陷管理

所有缺陷记录于 [TEST_REPORT.md](TEST_REPORT.md) 的「缺陷记录」章节，字段包括：

- ID
- 阶段
- 描述
- 复现步骤
- 严重程度（Critical / High / Medium / Low）
- 状态（Open / Fixed / Verified）
- 修复提交

## 6. 回归测试

每次缺陷修复后执行：

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```

并针对修复模块补充定向用例，确保不引入新缺陷。

## 7. 交付物

- `TEST_PLAN.md`（本文件）
- `TEST_REPORT.md`（测试结果、缺陷分析、改进建议）
