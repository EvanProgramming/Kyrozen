# Kyrozen Phase 5 交付报告：产品规划与方案决策系统

## 1. Product Planning Architecture

### 目标

将 Kyrozen 从「判断问题是否值得解决」升级为「确定应该做什么产品、为谁做、第一版包含什么」。
用户在完成 Problem Brief 和 Market Research Report 后可以进入 **Product Planning Mode**，Agent 自动：
- 读取 Problem Brief 与 Market Research Report
- 定义产品目标、目标用户、用户旅程
- 列出功能并按 Must/Should/Could/Not Now 分级
- 明确 MVP 范围：第一版做什么、不做什么、成功指标
- 生成多个候选方案（Software Only / Hardware Only / Hybrid / Existing Product Combination / Low Cost / Best Experience）
- 比较方案并给出推荐，等待用户确认后再记录决策
- 输出 Product Brief、PRD 与 Solution Comparison Artifact

### 架构图

```
User
 |
 v
Web Chat (planning mode)
 |
 v
/api/chat  (mode="planning")
 |
 v
ProductPlanningAgent  ← 继承 BaseAgent
 | - Product Goal Definition
 | - Target User Definition
 | - User Journey Design
 | - Feature Definition
 | - MVP Definition
 | - Multiple Solution Generation
 | - Solution Comparison
 | - Decision Recording
 |
 v
Kyrozen Core (BaseAgent runtime + Tool System)
 |
 v
Planning Tools
 | - save_product_brief
 | - save_prd
 | - save_solution_comparison
 | - record_product_decision
 |
 v
Project Workspace
 | - Artifact: product_brief
 | - Artifact: prd
 | - Artifact: solution_comparison
 | - Decision: product_decision
 | - Memory: planning
 | - Task: planning task
```

### 新增模块

| 文件 | 职责 |
|------|------|
| `kyrozen/planning/models.py` | `ProductGoal`、`TargetUser`、`UserJourney`、`Feature`、`MVP`、`Solution`、`SolutionComparison`、`ProductBrief`、`PRD` 数据模型与验证 |
| `kyrozen/planning/state.py` | `PlanningSession` 运行时状态与阶段管理 |
| `kyrozen/planning/agent.py` | `ProductPlanningAgent`，专用 system prompt，禁止技术实现与替用户做重大决策 |
| `kyrozen/tools/planning_tools.py` | `save_product_brief`、`save_prd`、`save_solution_comparison`、`record_product_decision` |

---

## 2. Project Integration

### 如何连接 Phase 4

| Phase 4 能力 | Phase 5 使用方式 |
|--------------|------------------|
| `ProjectManager` | 保存 Product Brief、PRD、Solution Comparison Artifact 与 Product Decision |
| `ProjectContextBuilder` | 新增 `build_planning_context()`，注入 Problem Brief、Market Research Report、当前 Product Brief 与规划记忆 |
| `Artifact` | `type="product_brief"`、`type="prd"`、`type="solution_comparison"` |
| `Decision` | 保存产品层判断：`continue_with_solution` / `pivot_solution` / `narrow_scope` / `expand_scope` / `pause` / `abandon` |
| `BaseAgent` | `ProductPlanningAgent` 继承，复用任务循环和工具调用 |
| `ToolRegistry` | 注册 Phase 5 planning tools |
| `FastAPI` | `/api/chat` 增加 `mode=planning`，新增 `/api/projects/{id}/planning/state` |
| `Web UI` | Project Detail 增加「进入 Product Planning」按钮，新增 planning 视图 |

### 数据关系

```
Project
 |
 |-- Task (project_id)
 |     `-- 每次用户消息产生一个 planning task
 |
 |-- Artifact (project_id, type="problem_brief")
 |     `-- Phase 3 输出，Phase 5 输入
 |
 |-- Artifact (project_id, type="market_research_report")
 |     `-- Phase 4 输出，Phase 5 输入
 |
 |-- Artifact (project_id, type="product_brief")
 |     `-- version 1, 2, 3...
 |
 |-- Artifact (project_id, type="prd")
 |     `-- version 1, 2, 3...
 |
 |-- Artifact (project_id, type="solution_comparison")
 |     `-- version 1, 2, 3...
 |
 |-- Decision (project_id, source="agent")
 |     `-- 产品层判断
 |
 |-- Memory (project_id, category="planning")
       `-- 规划过程笔记
```

---

## 3. Artifact Design

### Product Brief Artifact

```json
{
  "product_goal": {
    "product_goal": "让跑者无需手动操作即可获得匹配步伐的音乐",
    "target_user": "每周跑步 3 次以上、习惯带手机跑步的跑者",
    "core_problem": "跑步时音乐节奏与运动状态不匹配，手动切歌分心",
    "value_proposition": "基于手机传感器自动调整播放节奏，帮助跑者保持运动状态"
  },
  "target_user": {
    "primary_user": "每周跑步 3 次以上、希望减少手机操作的跑者",
    "secondary_user": "健身房团课教练为学员准备音乐",
    "use_case": "户外/跑步机跑步时自动匹配音乐节奏",
    "user_context": "手机固定在臂包或腰包中，不便频繁操作"
  },
  "user_journey": {
    "before": "跑者手动选择歌单，跑步中不断掏出手机切歌",
    "during": "App 检测步伐节奏，自动切换到匹配 BPM 的歌曲",
    "after": "跑者完成训练，全程几乎不需要操作手机"
  },
  "value_proposition": "让跑者保持专注和节奏，不被音乐操作打断",
  "user_stories": [
    "作为跑者，我希望音乐自动匹配我的步伐，这样就不用切歌",
    "作为跑者，我希望第一版只使用手机传感器，这样不需要购买新设备"
  ],
  "core_features": [
    {
      "name": "步伐节奏检测",
      "description": "使用手机加速度计估算当前步频",
      "user_problem": "不知道当前应该放什么节奏的歌",
      "priority": "Must Have"
    },
    {
      "name": "动态歌单切换",
      "description": "根据检测到的步频选择匹配 BPM 的歌曲",
      "user_problem": "手动切歌打断运动节奏",
      "priority": "Must Have"
    }
  ],
  "mvp_scope": {
    "mvp_features": ["步伐节奏检测", "本地音乐按 BPM 自动切换"],
    "excluded_features": ["AI 情绪识别", "社交分享", "硬件传感器", "流媒体集成"],
    "success_metric": "一次跑步中用户手动切歌次数从平均 5 次降到 1 次以下"
  },
  "non_goals": ["开发硬件设备", "自建音乐流媒体服务", "AI 生成音乐"],
  "success_metrics": [
    "一次跑步中用户手动切歌次数从平均 5 次降到 1 次以下",
    "70% 以上测试跑者认为音乐节奏匹配度有明显提升"
  ],
  "constraints": ["第一版仅使用手机传感器", "不依赖网络"],
  "risks": ["不同手机传感器精度差异", "BPM 数据依赖音乐元数据完整性"]
}
```

### PRD Artifact

```json
{
  "overview": "一款手机 App，通过本地传感器检测步频并自动切换到匹配 BPM 的歌曲，帮助跑者保持运动节奏。",
  "user_stories": [
    "作为跑者，我希望音乐自动匹配我的步伐",
    "作为跑者，我希望不需要购买额外设备"
  ],
  "functional_requirements": [
    "App 能够读取本地音乐库的 BPM 元数据",
    "App 能够使用加速度计估算当前步频",
    "App 能够根据步频自动选择下一首歌曲",
    "用户可以在跑步前设置目标步频范围"
  ],
  "non_functional_requirements": [
    "离线可用",
    "运行时耗电量低于主流音乐播放器"
  ],
  "mvp_scope": {
    "mvp_features": ["步伐节奏检测", "本地音乐按 BPM 自动切换"],
    "excluded_features": ["AI 情绪识别", "社交分享", "硬件传感器", "流媒体集成"],
    "success_metric": "一次跑步中用户手动切歌次数从平均 5 次降到 1 次以下"
  },
  "out_of_scope": [
    "硬件设备开发",
    "AI 生成音乐",
    "社交功能"
  ]
}
```

### Solution Comparison Artifact

```json
{
  "solutions": [
    {
      "name": "Software Only",
      "solution": "手机 App 使用本地传感器和音乐库",
      "advantages": ["成本低", "迭代快", "无需额外硬件"],
      "disadvantages": ["传感器精度受限"],
      "cost": "低",
      "difficulty": "中",
      "development_time": "2-4 周",
      "risk": "中",
      "scalability": "高"
    },
    {
      "name": "Hardware Only",
      "solution": "独立可穿戴音乐播放器",
      "advantages": ["传感器更稳定"],
      "disadvantages": ["成本高", "开发周期长", "需供应链"],
      "cost": "高",
      "difficulty": "高",
      "development_time": "6-12 个月",
      "risk": "高",
      "scalability": "低"
    },
    {
      "name": "Hybrid",
      "solution": "手机 App + 低成本蓝牙传感器",
      "advantages": ["精度提升", "仍可用手机处理"],
      "disadvantages": ["需要额外配件", "配对体验复杂"],
      "cost": "中",
      "difficulty": "中高",
      "development_time": "2-3 个月",
      "risk": "中高",
      "scalability": "中"
    }
  ],
  "comparison_dimensions": [
    "solves_problem", "cost", "difficulty", "development_time",
    "usage_barrier", "stability", "scalability", "risk"
  ],
  "recommendation": "Software Only",
  "recommendation_reason": "成本最低、验证周期最短，适合作为第一版 MVP 验证核心假设"
}
```

### Artifact 之间关系

```
Problem Brief + Market Research Report
            |
            v
    ProductGoal / TargetUser / UserJourney
            |
            v
      Feature List + MVP Scope
            |
            v
   Solution Comparison（多方案比较）
            |
            v
   Decision Record（用户确认后的选择）
            |
            v
   Product Brief Artifact + PRD Artifact
```

---

## 4. Web Changes

### Project Detail 页面
- 新增按钮：**进入 Product Planning**
- 保留原有「进入 Problem Discovery」、「进入 Market Research」、「普通聊天」和「返回列表」

### Product Planning 视图
- 左侧：聊天区域（类似普通聊天）
- 右侧：
  - **Product Goal**：产品目标、核心问题、价值主张
  - **Target User**：主要用户、次要用户、使用场景、上下文
  - **MVP Scope**：MVP 功能、明确排除的功能、成功指标
  - **Solutions**：候选方案列表及成本/难度/时间
  - **Recommendation**：推荐方案与理由

### 路由
- `/#/projects/{id}` — 项目详情
- `/#/projects/{id}/chat` — 普通聊天
- `/#/projects/{id}/discovery` — Problem Discovery
- `/#/projects/{id}/market-research` — Market Research
- `/#/projects/{id}/planning` — Product Planning

---

## 5. User Flow

```
Problem Brief
       |
       v
Market Research Report
       |
       v
进入 Product Planning
       |
       v
Agent 读取前序产物，定义 Product Goal 与 Target User
       |
       v
设计 User Journey，列出 Features 与优先级
       |
       v
定义 MVP Scope：第一版做什么 / 不做什么 / 成功指标
       |
       v
生成多个候选 Solution 并进行比较
       |
       v
Agent 给出 Recommendation，等待用户确认
       |
       v
用户确认后记录 Decision
       |
       v
保存 Product Brief + PRD + Solution Comparison
       |
       v
Development Ready（进入 Phase 6）
```

### 测试场景覆盖

| 案例 | 输入 | 验证点 |
|------|------|--------|
| Case 1：普通项目 | 跑步时音乐无法匹配运动状态，已有运动耳机 | Kyrozen 会缩小 MVP，建议先做 Software Only 验证，不直接开发完整智能耳机 |
| Case 2：范围过大 | 我要做 AI 机器人助手，包含视觉、语音、导航、机械臂 | Kyrozen 会要求聚焦，建议先选择单一核心场景（如语音交互）作为 MVP |
| Case 3：多方案比较 | 同一问题 | Kyrozen 会生成 Software Only / Hardware Only / Hybrid 等方案并比较 |

---

## 6. Test Results

运行全部测试：

```bash
.venv/bin/python -m pytest tests/ -q
```

结果：**141 passed, 1 warning**

Phase 5 新增 22 个测试，覆盖：
- `ProductGoal`、`TargetUser`、`UserJourney`、`Feature`、`MVP`、`Solution`、`SolutionComparison`、`ProductBrief`、`PRD` 序列化与验证
- `PlanningSession` 阶段切换、功能去重、方案去重、MVP 同步
- `PRIORITY_LEVELS`、`COMPARISON_DIMENSIONS`、`PRODUCT_DECISIONS`、`PLANNING_STAGES` 枚举
- `save_product_brief`、`save_prd`、`save_solution_comparison`、`record_product_decision` 工具
- `/api/chat` 的 `planning` 模式
- `/api/projects/{id}/planning/state` 端点
- Agent Prompt 禁止技术实现与替用户决策

---

## 7. Limitations

本阶段明确不实现：

- 软件开发（编写代码、选择编程语言、设计数据库）
- 硬件开发（电路设计、芯片选择、BOM）
- 测试执行系统
- 自动替用户做重大产品决策（系统只提供推荐，需用户确认）
- 自动接受全部需求（会分析并缩小到 MVP）
- 最终产品管理界面、代码编辑器、BOM 管理

---

## 8. 如何运行

```bash
.venv/bin/uvicorn kyrozen.api.server:app --host 127.0.0.1 --port 8000 --reload
```

打开 http://127.0.0.1:8000，创建项目并完成 Problem Discovery 与 Market Research 后，点击「进入 Product Planning」即可开始。

---

*Commit 已推送至 origin/main。*
