# Kyrozen Phase 5 计划：产品规划与方案决策系统

## 1. 目标

将 Phase 3 的 Problem Brief 和 Phase 4 的 Market Research Report 转化为明确的产品方向：

- Product Goal
- Target User
- User Journey
- Feature List（Must / Should / Could / Not Now）
- MVP Scope
- Solution Comparison
- Product Brief & PRD Artifacts
- Product Decisions

**明确不做**：软件开发、硬件开发、写代码、生成 BOM、选择芯片/架构。

---

## 2. 新增模块

```
kyrozen/planning/
├── __init__.py          # 导出 ProductPlanningAgent, ProductBrief, PRD, SolutionComparison
├── models.py            # ProductGoal, TargetUser, Feature, MVP, Solution, ProductBrief, PRD, SolutionComparison
├── state.py             # PlanningSession 运行时状态
└── agent.py             # ProductPlanningAgent

kyrozen/tools/planning_tools.py
# save_product_brief, save_prd, save_solution_comparison, record_product_decision
```

---

## 3. 数据模型设计

### 3.1 ProductGoal

```json
{
  "product_goal": "帮助跑步者在不操作手机的情况下获得与运动状态匹配的音乐体验",
  "target_user": "每周跑步 3 次以上、希望减少手机操作的跑者",
  "core_problem": "跑步时音乐节奏与运动状态不匹配，手动切歌破坏运动节奏",
  "value_proposition": "通过自动识别运动状态，实时推荐匹配节奏的音乐，让跑者保持专注"
}
```

### 3.2 TargetUser

```json
{
  "primary_user": "每周跑步 3 次以上、习惯带手机或运动手表的跑者",
  "secondary_user": "健身房进行节奏性训练的用户",
  "use_case": "户外跑步、健身房跑步",
  "user_context": "运动过程中双手不便操作设备，希望全程沉浸"
}
```

### 3.3 UserJourney

```json
{
  "before": "跑步前手动挑选歌单，担心节奏不匹配",
  "during": "运动中音乐自动适配步伐和心率，无需操作",
  "after": "跑步后获得节奏匹配度反馈，下次自动优化"
}
```

### 3.4 Feature

```json
{
  "name": "自适应节奏推荐",
  "description": "根据步伐或心率实时调整音乐 BPM",
  "user_problem": "音乐节奏与跑步节奏不匹配",
  "priority": "Must Have"
}
```

优先级枚举：`Must Have`, `Should Have`, `Could Have`, `Not Now`。

### 3.5 MVP

```json
{
  "mvp_features": ["自适应节奏推荐", "离线播放", "基础偏好设置"],
  "excluded_features": ["社交分享", "高级数据分析", "多设备同步"],
  "success_metric": "用户单次跑步中手动切歌次数减少 50%"
}
```

### 3.6 Solution

```json
{
  "name": "手机 App + 耳机",
  "solution": "基于手机传感器检测步伐，通过耳机播放适配音乐",
  "advantages": ["开发成本低", "用户无需购买新硬件"],
  "disadvantages": ["需要携带手机", "传感器精度受限"],
  "cost": "低",
  "difficulty": "中",
  "development_time": "2-3 个月",
  "risk": "竞品众多，差异化有限",
  "scalability": "可扩展为订阅服务"
}
```

### 3.7 SolutionComparison

```json
{
  "solutions": [Solution, Solution, ...],
  "comparison_dimensions": [
    "solves_problem", "cost", "difficulty", "development_time",
    "usage_barrier", "stability", "scalability", "risk"
  ],
  "recommendation": "手机 App + 耳机",
  "recommendation_reason": "成本最低，能快速验证核心价值"
}
```

### 3.8 ProductBrief

```json
{
  "product_goal": "...",
  "target_user": {...},
  "value_proposition": "...",
  "user_story": ["作为跑者，我希望..."],
  "core_features": [Feature, ...],
  "mvp_scope": {...},
  "non_goals": ["不做硬件", "不做社交"],
  "success_metrics": ["手动切歌次数减少 50%"],
  "constraints": ["仅支持 iOS/Android", "必须离线可用"],
  "risks": ["竞品多", "传感器精度"]
}
```

### 3.9 PRD

```json
{
  "overview": "...",
  "user_stories": [...],
  "functional_requirements": [...],
  "non_functional_requirements": [...],
  "mvp_scope": {...},
  "out_of_scope": [...]
}
```

---

## 4. ProductPlanningAgent 设计

### 4.1 继承与初始化

```python
class ProductPlanningAgent(BaseAgent):
    def __init__(self, *args, project_manager=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_manager = project_manager
```

### 4.2 System Prompt 核心规则

- 输入：Problem Brief + Market Research Report
- 输出：Product Brief、PRD、Solution Comparison、Decision
- **禁止**：技术架构、编程语言、数据库设计、电路设计、芯片选择、写代码、生成 BOM
- **必须**：提出多个方案并比较，等待用户确认重大决策
- **必须**：缩小范围到可验证的 MVP
- **必须**：成功指标必须可量化

### 4.3 使用工具

Agent 可调用：

- `save_product_brief`
- `save_prd`
- `save_solution_comparison`
- `record_product_decision`
- `update_project`（仅当用户明确要求时推进阶段）

---

## 5. Planning Tools 设计

| 工具 | Action | 参数 |
|------|--------|------|
| `save_product_brief` | `save` | `project_id`, `brief` |
| `save_prd` | `save` | `project_id`, `prd` |
| `save_solution_comparison` | `save` | `project_id`, `comparison` |
| `record_product_decision` | `record` | `project_id`, `decision`, `reason`, `alternatives`, `rejected_reasons` |

---

## 6. ProjectContextBuilder 扩展

新增 `build_planning_context(project)`：

- 加载 `problem_brief` artifact
- 加载 `market_research_report` artifact
- 加载 `planning` category 记忆
- 加载最近决策
- 输出 `[Product Planning Context]` 文本块

---

## 7. API 与 Web UI 扩展

### 7.1 API

- `ChatRequest.mode` 增加 `"planning"`
- 新增 `/api/projects/{id}/planning/state`
- 返回当前 Product Brief、PRD、Solution Comparison、Decisions

### 7.2 Web UI

- Project Detail 增加「进入 Product Planning」按钮
- 新增 `/#/projects/{id}/planning` 路由
- 视图：
  - 左侧聊天
  - 右侧面板：
    - Product Goal
    - Target User
    - User Journey
    - Features（按优先级分组）
    - MVP Scope
    - Solutions
    - Recommendation
    - Decisions

---

## 8. 开发顺序

1. `kyrozen/planning/models.py` — 数据模型
2. `kyrozen/planning/state.py` — PlanningSession
3. `kyrozen/tools/planning_tools.py` — 工具
4. `kyrozen/planning/agent.py` — ProductPlanningAgent
5. `kyrozen/project/context.py` — `build_planning_context`
6. `kyrozen/tools/registry.py` — 注册工具
7. `kyrozen/api/server.py` — planning 模式与状态端点
8. `kyrozen/web/index.html` — Product Planning 视图
9. `tests/test_planning.py` — 测试
10. `PHASE5_DELIVERY_REPORT.md` — 交付报告

---

## 9. 测试计划

新增测试覆盖：

- ProductBrief / PRD / SolutionComparison 序列化与验证
- PlanningSession 状态管理
- save_product_brief / save_prd / save_solution_comparison / record_product_decision 工具
- `/api/chat` planning 模式
- `/api/projects/{id}/planning/state` 端点
- Agent prompt 禁止开发阶段内容

### 测试案例

1. **跑步音乐产品**：验证 Agent 缩小 MVP，不直接开发完整智能耳机
2. **AI 机器人助手（范围过大）**：验证 Agent 拒绝大而全，缩小到可验证范围
3. **多方案比较**：验证生成软件、硬件、混合等方案并比较

---

## 10. 完成标准

用户完成 Phase 5 后能回答：

- Kyrozen 准备做什么？
- 为谁做？
- 解决什么问题？
- 第一版包含什么？
- 第一版不包含什么？
- 如何判断成功？
- 为什么选择这个方案？
