# Kyrozen Phase 4 交付报告：市场调研与产品机会判断系统

## 1. Market Research Architecture

### 目标

将 Kyrozen 从「能够理解真实问题」升级为「能够判断问题是否值得解决」。
用户在完成 Problem Brief 后可以进入 **Market Research Mode**，Agent 自动：
- 根据 Problem Brief 制定调研计划
- 搜索真实市场信息（产品、应用、开源项目、论文、社区等）
- 记录来源证据，区分事实、推断与未知
- 分析竞品、用户反馈、市场缺口
- 输出 Market Research Report 并给出机会判断

### 架构图

```
User
 |
 v
Web Chat (market_research mode)
 |
 v
/api/chat  (mode="market_research")
 |
 v
MarketResearchAgent  ← 继承 BaseAgent
 | - Research Planning
 | - Search Execution
 | - Evidence Tracking
 | - Competitor Analysis
 | - Opportunity Decision
 |
 v
Kyrozen Core (BaseAgent runtime + Tool System)
 |
 v
Research Tools
 | - web_search (Tavily / Serper)
 | - search_github
 | - search_papers
 | - save_research_source
 | - save_market_research_report
 | - record_opportunity_decision
 |
 v
Project Workspace
 | - Artifact: market_research_report
 | - Artifact: research_source
 | - Decision: opportunity_decision
 | - Task: market_research task
```

### 新增模块

| 文件 | 职责 |
|------|------|
| `kyrozen/research/models.py` | `ResearchPlan`、`ResearchSource`、`Competitor`、`MarketGap`、`MarketResearchReport` 数据模型与验证 |
| `kyrozen/research/state.py` | `ResearchSession` 运行时状态与阶段管理 |
| `kyrozen/research/agent.py` | `MarketResearchAgent`，专用 system prompt，禁止产品设计与编造数据 |
| `kyrozen/tools/research/base.py` | `SearchProvider` 抽象接口与 `UnconfiguredSearchProvider` 占位 |
| `kyrozen/tools/research/providers.py` | Tavily、Serper、GitHub、Semantic Scholar 搜索实现 |
| `kyrozen/tools/research/tools.py` | `web_search`、`search_github`、`search_papers`、`save_research_source`、`save_market_research_report`、`record_opportunity_decision` |

---

## 2. Project Integration

### 如何连接 Phase 3

| Phase 3 能力 | Phase 4 使用方式 |
|--------------|------------------|
| `ProjectManager` | 保存 Market Research Report Artifact、Research Source Artifact、Opportunity Decision |
| `ProjectContextBuilder` | 新增 `build_research_context()`，注入当前 Problem Brief 与已有报告 |
| `Artifact` | `type="market_research_report"` 与 `type="research_source"` |
| `Decision` | 保存机会层判断：`continue_development` / `pivot_target_user` / `narrow_scope` / `use_existing_solution` / `pause` / `abandon` |
| `BaseAgent` | `MarketResearchAgent` 继承，复用任务循环和工具调用 |
| `ToolRegistry` | 注册 Phase 4 research tools |
| `FastAPI` | `/api/chat` 增加 `mode=market_research`，新增 `/api/projects/{id}/market-research/state` |
| `Web UI` | Project Detail 增加「进入 Market Research」按钮，新增 market-research 视图 |

### 数据关系

```
Project
 |
 |-- Task (project_id)
 |     `-- 每次用户消息产生一个 market_research task
 |
 |-- Artifact (project_id, type="problem_brief")
 |     `-- Phase 3 输出，Phase 4 输入
 |
 |-- Artifact (project_id, type="market_research_report")
 |     `-- version 1, 2, 3...
 |
 |-- Artifact (project_id, type="research_source")
 |     `-- 每条外部来源一个 artifact
 |
 |-- Decision (project_id, source="agent")
 |     `-- 机会层判断
```

---

## 3. Market Research Report Artifact 数据结构

```json
{
  "problem_summary": "跑步时音乐节奏与运动状态不匹配，手动切歌分心",
  "market_status": "存在多个音乐 App 与运动耳机方案，但自适应节奏体验仍不完整",
  "competitors": [
    {
      "name": "Spotify Running",
      "company": "Spotify",
      "solution": "根据步频推荐音乐",
      "target_user": "跑步者",
      "main_features": ["步频检测", "动态歌单"],
      "price": "免费 / 付费订阅",
      "advantages": ["曲库大", "算法成熟"],
      "complaints": ["需要携带手机", "检测延迟"],
      "failure_reason": "已于 2018 年下线该功能",
      "sources": ["https://..."]
    }
  ],
  "open_source_projects": [
    {
      "title": "running-music-ai",
      "url": "https://github.com/...",
      "source_type": "github",
      "summary": "开源跑步音乐推荐项目",
      "related_claim": "存在开源尝试",
      "confidence": "medium",
      "fact_type": "fact"
    }
  ],
  "user_feedback": [],
  "alternative_solutions": [],
  "technology_routes": ["手机传感器 + 耳机", "独立可穿戴设备"],
  "market_gap": {
    "existing_solution": "手动切歌、固定歌单、部分 App 步频推荐",
    "problem_remaining": "无需手动操作、实时适配情绪与疲劳状态的方案少",
    "possible_difference": "基于可穿戴设备生理信号自动调整音乐",
    "risk": "硬件依赖、用户习惯差异大",
    "confidence": "medium"
  },
  "risks": ["竞争激烈", "用户习惯依赖现有 App"],
  "recommendation": "continue_development",
  "sources": [
    {
      "title": "...",
      "url": "https://...",
      "source_type": "web_page",
      "publish_date": "",
      "access_date": "2026-07-22",
      "summary": "...",
      "related_claim": "...",
      "confidence": "medium",
      "fact_type": "fact"
    }
  ]
}
```

---

## 4. Web Changes

### Project Detail 页面
- 新增按钮：**进入 Market Research**
- 保留原有「进入 Problem Discovery」、「普通聊天」和「返回列表」

### Market Research 视图
- 左侧：聊天区域（类似普通聊天）
- 右侧：
  - **Research Progress**：当前调研阶段与日志
  - **Recommendation**：机会判断结果
  - **Sources**：已收集的外部来源列表

### 路由
- `/#/projects/{id}` — 项目详情
- `/#/projects/{id}/chat` — 普通聊天
- `/#/projects/{id}/discovery` — Problem Discovery
- `/#/projects/{id}/market-research` — Market Research

---

## 5. Conversation Flow

示例：

```
用户已完成 Problem Brief "AI 跑步音乐设备"
       |
       v
进入 Market Research
       |
       v
Agent 读取 Problem Brief，生成 Research Plan
       |
       v
调用 web_search: "running music app tempo sync"
调用 search_github: "running music recommendation open source"
       |
       v
保存来源证据，分析竞品
       |
       v
Agent: "已发现 Spotify 曾推出 Running 功能但已下线，
        当前主流方案依赖手机传感器...
        建议继续开发，但需聚焦无需手机的体验。"
       |
       v
调用 save_market_research_report
生成 Market Research Report v1
       |
       v
调用 record_opportunity_decision
保存判断：continue_development
```

---

## 6. Test Results

运行全部测试：

```bash
.venv/bin/python -m pytest tests/ -q
```

结果：**119 passed, 1 warning**

Phase 4 新增 21 个测试，覆盖：
- `ResearchSource`、`Competitor`、`MarketResearchReport`、`ResearchPlan` 序列化与验证
- `ResearchSession` 阶段切换、来源去重、竞品去重
- `UnconfiguredSearchProvider` 与 `MockSearchProvider`
- `WebSearchTool`、`GitHubSearchTool`、`PaperSearchTool` 无配置行为
- `save_research_source`、`save_market_research_report`、`record_opportunity_decision` 工具
- `/api/chat` 的 `market_research` 模式
- `/api/projects/{id}/market-research/state` 端点

---

## 7. Limitations

本阶段明确不实现：

- 产品设计（PRD、MVP、功能列表）
- 技术方案设计（架构、硬件选型、BOM）
- 自动写代码
- 外部数据爬取或绕过 API 的搜索
- 自动生成虚假市场数据（未配置 API 时明确返回未配置提示）
- 对来源真实性的外部交叉验证（当前依赖来源自身可信度标注）

---

## 8. 如何运行

```bash
.venv/bin/uvicorn kyrozen.api.server:app --host 127.0.0.1 --port 8000 --reload
```

打开 http://127.0.0.1:8000，创建项目并完成 Problem Discovery 后，点击「进入 Market Research」即可开始。

如需启用真实搜索，配置环境变量：

```bash
export TAVILY_API_KEY=...
export SERPER_API_KEY=...
export GITHUB_TOKEN=...
export SEMANTIC_SCHOLAR_API_KEY=...
```

---

*Commit 已推送至 origin/main。*
