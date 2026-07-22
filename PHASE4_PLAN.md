# Kyrozen Phase 4 计划：市场调研与产品机会判断系统

## 1. Phase 3 Integration Analysis

### 1.1 Problem Brief 如何存储

- **存储位置**：`ProjectManager.save_artifact(project_id, type="problem_brief", title="Problem Brief", content=...)` 保存到 SQLite 数据库 `artifacts` 表。
- **数据结构**：[kyrozen/discovery/brief.py](file:///Users/evangong/Documents/Programming/AI/Kyrozen/kyrozen/discovery/brief.py) 中的 `ProblemBrief` 数据类，包含 `title/target_user/scenario/surface_problem/deep_need/current_solution/current_solution_problem/frequency/impact/unknown_assumptions/opportunity_direction/confidence/confidence_reason/decision/decision_reason`。
- **读取方式**：`ProjectManager.get_latest_artifact(project_id, "problem_brief", title="Problem Brief")` 返回最新版本；`ProjectContextBuilder.build_discovery_context()` 负责注入当前 Brief。

### 1.2 Artifact 如何读取

- `ProjectManager.get_latest_artifact(type, title)`：读取某类型最新版本 Artifact。
- `ProjectManager.list_artifacts(project_id)`：列出项目所有产物。
- `ProjectManager.get_artifact(project_id, artifact_id)`：读取指定产物。
- Artifact 内容目前为 JSON 字符串，由调用方 `json.loads()` 解析。

### 1.3 Project Context 如何传递

- 后端：[kyrozen/project/context.py](file:///Users/evangong/Documents/Programming/AI/Kyrozen/kyrozen/project/context.py) 的 `ProjectContextBuilder.build_discovery_context()` 组装项目信息 + 当前 Problem Brief + discovery_qa 记忆。
- API：[kyrozen/api/server.py](file:///Users/evangong/Documents/Programming/AI/Kyrozen/kyrozen/api/server.py) 的 `/api/chat` 根据 `mode` 选择 Agent 和 Context；`mode=discovery` 时调用 `build_discovery_context()`。
- Memory：`ProjectMemory` 自动注入 `project_id` filter，实现项目隔离。

### 1.4 Core 如何调用 Agent

- `BaseAgent` 负责任务循环、工具调用解析、状态管理。
- `ProblemDiscoveryAgent` 继承 `BaseAgent`，覆盖 `_build_system_prompt()`，由 `server.py` 在 lifespan 中创建。
- 调用入口：`agent.run(user_input, confirmed=..., project_id=...)`。

### 1.5 Phase 4 集成点

| Phase 3 输出 | Phase 4 输入 | 说明 |
|--------------|--------------|------|
| `ProblemBrief` | Market Research Agent system prompt | 注入当前问题定义、目标用户、场景、未验证假设 |
| `Artifact` (`problem_brief`) | `ProjectManager.get_latest_artifact` | Agent 读取已有 Brief |
| `Artifact` (`market_research_report`) | `ProjectManager.save_artifact` | Phase 4 输出产物 |
| `Decision` | `ProjectManager.add_decision` | 保存机会判断结果 |
| `ProjectMemory` | `JsonFileMemory` + `ProjectMemory` | 保存研究计划、来源、分析过程 |
| `/api/chat?mode=discovery` | 新增 `/api/chat?mode=market_research` | 复用 Chat 入口，按 mode 路由 |
| `/api/projects/{id}/problem-discovery/state` | 新增 `/api/projects/{id}/market-research/state` | 前端获取研究进度与报告预览 |

---

## 2. Market Research Agent 设计

### 2.1 类定义

```python
class MarketResearchAgent(BaseAgent):
    def __init__(self, *args, project_manager: ProjectManager | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_manager = project_manager

    def _build_system_prompt(self) -> str:
        ...

    def build_research_context(self, project_id: str, session: ResearchSession | None = None) -> str:
        ...
```

### 2.2 System Prompt 核心规则

```text
You are Kyrozen Market Research Agent. Your job is to evaluate whether the problem described in the Problem Brief is worth solving, by searching for real market evidence.

Inputs:
- Problem Brief (title, target_user, scenario, surface_problem, deep_need, current_solution, current_solution_problem, unknown_assumptions)
- User's research direction or clarifications

Outputs:
- Research Plan (research_question, search_direction, reason)
- Search queries and saved sources
- Competitor Analysis
- Community Feedback Analysis
- Market Gap Analysis
- Market Research Report Artifact
- Opportunity Decision

Rules:
- DO NOT design a product, write PRD/MVP, suggest hardware, or write code.
- DO NOT make up companies, products, user numbers, or market sizes.
- If no evidence is found, explicitly say "Insufficient evidence".
- Always save the source URL, access_date, and confidence for every external claim.
- Distinguish Fact, Inference, and Unknown in every source item.
- Analyze competitors honestly: include why they succeed and why they fail.
- After gathering evidence, save the Market Research Report and record an opportunity decision.
- If existing solutions are good enough, recommend "Use Existing Solution" or "Abandon".
```

### 2.3 工作流

```
Problem Brief
    |
    v
Research Plan (multi-step reasoning)
    |
    v
Parallel/sequential searches
 - Web Search (products, apps, companies)
 - GitHub Search (open source projects)
 - Paper Search (academic research)
 - Patent Search (IP landscape)
 - Community Search (Reddit/forum/user reviews)
    |
    v
Source Evidence (save_source tool)
    |
    v
Competitor Analysis + Community Feedback Analysis
    |
    v
Market Gap Analysis
    |
    v
Market Research Report Artifact
    |
    v
Opportunity Decision (record_decision tool)
```

---

## 3. 数据结构设计

### 3.1 Research Plan

```python
@dataclass
class ResearchPlan:
    research_question: str = ""           # 本次调研要回答的问题
    search_directions: list[str] = field(default_factory=list)  # 如 ["运动耳机", "音乐自动适配 App", "开源跑步音乐项目"]
    reason: str = ""                      # 为什么选择这些方向
```

### 3.2 Research Source

```python
@dataclass
class ResearchSource:
    title: str = ""
    url: str = ""
    source_type: str = ""   # product | app | github | paper | patent | community | crowdfunding | diy | alternative
    publish_date: str = ""
    access_date: str = ""
    summary: str = ""
    related_claim: str = ""  # 该来源支持/反驳的论点
    confidence: str = "medium"  # low / medium / high
    fact_type: str = "fact"     # fact / inference / unknown
```

### 3.3 Competitor

```python
@dataclass
class Competitor:
    name: str = ""
    company: str = ""
    solution: str = ""
    target_user: str = ""
    main_features: list[str] = field(default_factory=list)
    price: str = ""
    advantages: list[str] = field(default_factory=list)
    complaints: list[str] = field(default_factory=list)
    failure_reason: str = ""
    sources: list[str] = field(default_factory=list)  # source URLs
```

### 3.4 Market Gap / Opportunity

```python
@dataclass
class MarketGap:
    existing_solution: str = ""
    problem_remaining: str = ""
    possible_difference: str = ""
    risk: str = ""
    confidence: str = "low"
```

### 3.5 Market Research Report Artifact

```python
@dataclass
class MarketResearchReport:
    problem_summary: str = ""
    market_status: str = ""
    competitors: list[Competitor] = field(default_factory=list)
    open_source_projects: list[ResearchSource] = field(default_factory=list)
    user_feedback: list[ResearchSource] = field(default_factory=list)
    alternative_solutions: list[ResearchSource] = field(default_factory=list)
    technology_routes: list[str] = field(default_factory=list)
    market_gap: MarketGap = field(default_factory=MarketGap)
    risks: list[str] = field(default_factory=list)
    recommendation: str = ""   # continue_development / narrow_scope / change_target_user / change_product_form / use_existing_solution / pause / abandon
    sources: list[ResearchSource] = field(default_factory=list)
```

### 3.6 Opportunity Decision

```python
OPPORTUNITY_DECISIONS = {
    "continue_development",
    "narrow_scope",
    "change_target_user",
    "change_product_form",
    "use_existing_solution",
    "pause",
    "abandon",
}
```

---

## 4. Research Tools 设计

### 4.1 搜索抽象层

```python
class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[ResearchSource]: ...
```

### 4.2 具体工具

| Tool | 职责 | 无配置时的行为 |
|------|------|----------------|
| `web_search` | 调用外部搜索 API（Tavily/Serper/等） | 返回 `"No web search provider configured. Please set TAVILY_API_KEY or SERPER_API_KEY."` |
| `fetch_web_page` | 抓取并清洗网页正文 | 返回网页内容或错误 |
| `search_github` | 搜索 GitHub repositories/issues | 使用 GitHub API；无 token 时受速率限制 |
| `search_papers` | 搜索学术论文（Semantic Scholar） | 无 API key 时仍可用公开端点 |
| `search_patents` | 搜索专利 | 使用公开专利 API；未配置时提示 |
| `search_community` | 搜索 Reddit/Forum 讨论 | 依赖 web search 或 Reddit API |
| `save_research_source` | 保存来源到 Artifact | 保存到 `research_source` Artifact |
| `save_market_research_report` | 保存最终报告 | 保存到 `market_research_report` Artifact |
| `record_opportunity_decision` | 记录机会判断 | 保存到 Decision |

### 4.3 配置扩展

在 `KyrozenConfig` 中新增：

```python
TAVILY_API_KEY: str = ""
SERPER_API_KEY: str = ""
GITHUB_TOKEN: str = ""
SEMANTIC_SCHOLAR_API_KEY: str = ""
```

加载优先级：环境变量 > 配置文件。

---

## 5. API 与 Web 扩展

### 5.1 API 扩展

- `ChatRequest.mode` 增加 `"market_research"` 枚举。
- `/api/chat` 当 `mode="market_research"` 时使用 `MarketResearchAgent` + `build_research_context()`。
- 新增 `GET /api/projects/{project_id}/market-research/state`：返回当前研究进度、最新报告、来源列表、建议决策。
- 新增 `POST /api/projects/{project_id}/market-research/plan`（可选）：允许用户手动调整研究方向。

### 5.2 Web UI 扩展

- Project Detail 增加按钮：**进入 Market Research**（仅当项目已有 `problem_brief` 时启用或提示）。
- 新增 `view-market-research`：
  - 左侧：聊天区域
  - 右侧：
    - **Research Progress**：Understanding problem → Searching products → Analyzing competitors → Reviewing user feedback → Generating report
    - **Sources**：来源列表（URL、类型、可信度）
    - **Competitors**：竞品卡片
    - **Market Research Report Preview**：报告预览
    - **Recommendation**：机会判断

---

## 6. 开发顺序

1. **数据模型**（`kyrozen/research/models.py`）
   - ResearchPlan, ResearchSource, Competitor, MarketGap, MarketResearchReport
2. **搜索工具抽象与实现**（`kyrozen/tools/research/`）
   - SearchProvider 抽象
   - WebSearchTool, FetchWebPageTool, GitHubSearchTool, PaperSearchTool, PatentSearchTool, CommunitySearchTool
   - SaveResearchSourceTool, SaveMarketResearchReportTool, RecordOpportunityDecisionTool
3. **Research Session 状态**（`kyrozen/research/state.py`）
4. **MarketResearchAgent**（`kyrozen/research/agent.py`）
5. **Context Builder 扩展**（`kyrozen/project/context.py`）
   - `build_research_context()`
6. **Registry 注册**（`kyrozen/tools/registry.py`）
7. **API 扩展**（`kyrozen/api/server.py`）
8. **Web UI 扩展**（`kyrozen/web/index.html`）
9. **测试**（`tests/test_research.py`, `tests/test_research_integration.py`）
10. **交付报告**（`PHASE4_DELIVERY_REPORT.md`）

---

## 7. 测试计划

| 用例 | 目标 |
|------|------|
| Research Plan | 根据 Problem Brief 生成研究方向 |
| Source Evidence | 保存来源并区分 fact/inference/unknown |
| Competitor Analysis | 竞品结构化字段完整 |
| Market Gap | 基于证据生成机会分析，不编造 |
| 报告保存 | `save_market_research_report` 保存 Artifact |
| 机会判断 | `record_opportunity_decision` 保存 Decision |
| 无搜索配置 | 工具返回明确提示，不伪造数据 |
| 竞品丰富场景 | 跑步音乐问题能找到运动耳机/App/开源项目 |
| 高度竞争场景 | 新笔记 App 不能判断为市场空白 |
| 证据不足场景 | 小众问题标记为 `evidence insufficient` |
| 项目隔离 | 研究来源和报告按项目隔离 |

---

## 8. 开发限制

- ❌ 不生成虚假公司、产品、用户数据、市场规模
- ❌ 不进入产品设计（PRD / MVP / 架构 / BOM）
- ❌ 不推荐硬件、不写代码
- ✅ 必须保存来源、URL、访问时间、可信度
- ✅ 必须区分 Fact / Inference / Unknown
- ✅ 没有资料时明确标记 `Insufficient evidence`

---

## 9. 风险与依赖

| 风险 | 说明 | 缓解 |
|------|------|------|
| 外部搜索 API 缺失 | 没有 API key 时无法获取真实数据 | 工具返回明确提示；架构允许随时接入新 provider；测试使用 mock |
| 网络不稳定 | 搜索请求可能超时/失败 | 设置超时，失败时记录错误，不伪造 |
| LLM 编造来源 | 模型可能生成不存在 URL | prompt 强制要求真实 URL；保存前校验 URL 可访问性（可选） |
| 多源数据质量差异 | 社区评论噪音大 | 要求记录 confidence 和 fact_type |

---

*本计划待确认后进入开发。*
