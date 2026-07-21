# Kyrozen Phase 3 交付报告：问题发现与问题定义系统

## 1. Problem Discovery Architecture

### 目标

将 Kyrozen 从「项目管理 Agent」升级为「能够理解真实问题的 Agent」。
用户在创建项目后可以进入 **Problem Discovery Mode**，通过多轮对话逐步澄清：
- 谁遇到了问题（Who）
- 问题发生在哪里（Where/When）
- 表面问题是什么（Surface Problem）
- 深层需求是什么（Deep Need）
- 当前如何解决（Current Solution）
- 当前方案哪里不好（Pain Point）
- 发生频率与影响（Frequency / Impact）

### 架构图

```
User
 |
 v
Web Chat (discovery mode)
 |
 v
/api/chat  (mode="discovery")
 |
 v
ProblemDiscoveryAgent  ← 继承 BaseAgent
 | - Question Engine
 | - Brief Generator
 | - Evidence Tracker
 | - Confidence Assessor
 | - Decision Recommender
 |
 v
Kyrozen Core (BaseAgent runtime + Tool System)
 |
 v
Project Workspace
 | - Artifact: problem_brief
 | - Artifact: discovery_evidence
 | - Decision: problem decision
 | - Memory: discovery_qa
 | - Task: discovery task
```

### 新增模块

| 文件 | 职责 |
|------|------|
| `kyrozen/discovery/brief.py` | `ProblemBrief`、`EvidenceItem` 数据模型与验证 |
| `kyrozen/discovery/evidence.py` | `Evidence` 模型与 `assess_confidence` 启发式评估 |
| `kyrozen/discovery/question_engine.py` | 自适应问题引擎，按优先级选择下一步问题 |
| `kyrozen/discovery/state.py` | `DiscoverySession` 运行时状态 |
| `kyrozen/discovery/agent.py` | `ProblemDiscoveryAgent`，专用 system prompt |
| `kyrozen/tools/discovery_tools.py` | `save_problem_brief`、`record_evidence`、`assess_confidence`、`record_problem_decision` |

---

## 2. Project Integration

### 如何连接 Phase 2

| Phase 2 能力 | Phase 3 使用方式 |
|--------------|------------------|
| `ProjectManager` | 保存 Problem Brief Artifact、Evidence Artifact、Decision |
| `ProjectContextBuilder` | 新增 `build_discovery_context()`，注入当前 Brief 和最近 Q&A |
| `Artifact` | `type="problem_brief"` 与 `type="discovery_evidence"` |
| `Decision` | 保存问题层判断：`continue_research` / `need_more_information` / `existing_solution_enough` / `problem_not_clear` / `not_suitable_for_product` |
| `ProjectMemory` | 保存 `discovery_qa`、`discovery_evidence` 类别记忆 |
| `BaseAgent` | `ProblemDiscoveryAgent` 继承，复用任务循环和工具调用 |
| `ToolRegistry` | 注册 Phase 3 discovery tools |
| `FastAPI` | `/api/chat` 增加 `mode=discovery`，新增 `/api/projects/{id}/problem-discovery/state` |
| `Web UI` | Project Detail 增加「进入 Problem Discovery」按钮，新增 discovery 视图 |

### 数据关系

```
Project
 |
 |-- Task (project_id)
 |     `-- 每次用户消息产生一个 discovery task
 |
 |-- Artifact (project_id, type="problem_brief")
 |     `-- version 1, 2, 3...
 |
 |-- Artifact (project_id, type="discovery_evidence")
 |     `-- 每条证据一个 artifact
 |
 |-- Decision (project_id, source="agent")
 |     `-- 问题层判断
 |
 |-- Memory (project_id, category="discovery_qa")
       `-- 问答历史
```

---

## 3. Problem Brief Artifact 数据结构

```json
{
  "title": "AI 跑步音乐设备",
  "target_user": "有跑步习惯、希望运动不被音乐操作打断的人",
  "scenario": "户外/健身房跑步过程中",
  "surface_problem": "跑步时音乐节奏和心情/步伐不匹配，手动切歌分心",
  "deep_need": "希望运动全程保持专注和沉浸感，不被设备操作打断",
  "current_solution": "手动选择歌单或手动切歌",
  "current_solution_problem": "需要掏出手机/手表操作，破坏运动节奏",
  "frequency": "每次跑步",
  "impact": "影响运动体验和连续性",
  "unknown_assumptions": [
    {"claim": "很多跑者都有这个问题", "source": "user_statement", "verified": false}
  ],
  "opportunity_direction": "探索根据运动状态自动调整音乐的设备或服务",
  "confidence": "medium",
  "confidence_reason": "基于单一用户描述，需要更多跑者验证",
  "decision": "need_more_information",
  "decision_reason": "问题方向有价值，但需验证假设"
}
```

---

## 4. Web Changes

### Project Detail 页面
- 新增按钮：**进入 Problem Discovery**
- 保留原有「普通聊天」和「返回列表」

### Problem Discovery 视图
- 左侧：聊天区域（类似普通聊天）
- 右侧：
  - **Problem Brief 实时预览**：显示当前已收集的各维度信息
  - **下一步问题**：由 Question Engine 推荐的下一个问题
  - **未验证假设**：标记为 unverified 的假设列表

### 路由
- `/#/projects/{id}` — 项目详情
- `/#/projects/{id}/chat` — 普通聊天
- `/#/projects/{id}/discovery` — Problem Discovery

---

## 5. Conversation Flow

示例：

```
用户创建项目 "AI 跑步设备"
       |
       v
进入 Problem Discovery
       |
       v
用户："我跑步的时候感觉音乐不适合我的状态"
       |
       v
Agent："谢谢分享。想先了解：这个问题通常发生在什么场景？
        你现在是怎么解决这个问题的？"
       |
       v
用户回答...
       |
       v
Agent 保存 discovery_qa 记忆，必要时更新 Problem Brief
       |
       v
信息足够后，Agent 调用 save_problem_brief
生成 Problem Brief v1
       |
       v
Agent："根据目前了解，问题可以总结为...
        [显示 Problem Brief 预览]
        下一步建议：继续访谈 2-3 位跑者验证假设。"
       |
       v
用户关闭页面后重新打开
       |
       v
ProjectContextBuilder 读取当前 Problem Brief 和记忆
Agent 继续追问 / 更新 Brief
```

---

## 6. Test Results

运行全部测试：

```bash
.venv/bin/python -m pytest tests/ -v
```

结果：**81 passed, 1 warning**

Phase 3 新增 11 个测试，覆盖：
- Problem Brief 合并
- 自适应问题引擎
- Evidence 验证
- 可信度评估
- Discovery State API
- save_problem_brief / record_evidence / assess_confidence 工具
- discovery 模式聊天
- Agent Prompt 禁止产品设计与市场调研

---

## 7. Limitations

本阶段明确不实现：

- 市场调研（竞品分析、用户评论、专利、GitHub 分析）
- 产品设计（PRD、MVP、功能列表）
- 技术方案设计（架构、硬件选型、BOM）
- 自动写代码
- 外部数据爬取或搜索
- 证据的外部验证（当前只能由用户声明 verified）

---

## 8. 如何运行

```bash
.venv/bin/uvicorn kyrozen.api.server:app --host 127.0.0.1 --port 8000 --reload
```

打开 http://127.0.0.1:8000，创建项目后点击「进入 Problem Discovery」即可开始。

---

*Commit 已推送至 origin/main。*
