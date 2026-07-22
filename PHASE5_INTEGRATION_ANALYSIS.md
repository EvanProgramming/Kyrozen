# Phase 5 Integration Analysis

## 1. Phase 5 Outputs: How They Are Stored

Kyrozen Phase 5 (Product Planning) produces three core artifacts and a set of product decisions. They are persisted through `ProjectManager.save_artifact()` and `ProjectManager.add_decision()` into the SQLite project database (`kyrozen.db`).

| Output | Artifact Type | Title | Key Fields |
|---|---|---|---|
| Product Brief | `product_brief` | "Product Brief" | `product_goal`, `target_user`, `user_journey`, `value_proposition`, `user_stories`, `core_features`, `mvp_scope`, `non_goals`, `success_metrics`, `constraints`, `risks` |
| PRD | `prd` | "Product Requirements Document" | `overview`, `user_stories`, `functional_requirements`, `non_functional_requirements`, `mvp_scope`, `out_of_scope` |
| Solution Comparison | `solution_comparison` | "Solution Comparison" | `solutions`, `comparison_dimensions`, `recommendation`, `recommendation_reason` |
| Product Decision | Decision row | - | `decision` is prefixed with `"Product decision: "` |

### 1.1 PRD Artifact Structure

The PRD model (`kyrozen/planning/models.py::PRD`) is what Phase 6 consumes:

```python
@dataclass
class PRD:
    overview: str = ""
    user_stories: list[str] = field(default_factory=list)
    functional_requirements: list[str] = field(default_factory=list)
    non_functional_requirements: list[str] = field(default_factory=list)
    mvp_scope: MVP = field(default_factory=MVP)
    out_of_scope: list[str] = field(default_factory=list)
```

The `mvp_scope` field contains:
- `mvp_features`: list of feature names included in MVP
- `excluded_features`: list of feature names explicitly excluded
- `success_metric`: measurable success criteria

### 1.2 Approved Decisions

Phase 5 decisions use the prefix `"Product decision: "`. Example: `"Product decision: continue_with_solution"`. Phase 6 must filter decisions by this prefix to understand what the user has already approved (solution direction, scope, etc.).

### 1.3 Project Stage

Projects start at `problem_discovery` and move through `market_research`, `product_definition`, `solution_design`, `development`, `testing`, `iteration`. Phase 6 owns the transition into `development` (and later `testing`).

## 2. How Phase 6 Reads Phase 5 Outputs

### 2.1 Recommended Read Pattern

Phase 6 should mirror Phase 4/5 context loading:

```python
latest_prd = project_manager.get_latest_artifact(
    project_id, "prd", title="Product Requirements Document"
)
prd = PRD()
if latest_prd is not None:
    prd = PRD.from_dict(json.loads(latest_prd.content))

latest_brief = project_manager.get_latest_artifact(
    project_id, "product_brief", title="Product Brief"
)
product_brief = ProductBrief()
if latest_brief is not None:
    product_brief = ProductBrief.from_dict(json.loads(latest_brief.content))

latest_comparison = project_manager.get_latest_artifact(
    project_id, "solution_comparison", title="Solution Comparison"
)
comparison = SolutionComparison()
if latest_comparison is not None:
    comparison = SolutionComparison.from_dict(json.loads(latest_comparison.content))

decisions = [
    d for d in project_manager.list_decisions(project_id)
    if d.decision.startswith("Product decision: ")
]
```

### 2.2 Context Builder Extension

Add `build_development_context(project)` to `ProjectContextBuilder` (`kyrozen/project/context.py`). It should inject:
- PRD overview
- MVP features and success metric
- Out-of-scope list (hard guardrails)
- Product Brief target user / value proposition
- Solution Comparison recommendation
- Recent product decisions
- Existing code state summary (if software project already initialized)

## 3. Software Development Agent Architecture

### 3.1 Agent Design

Create `kyrozen/development/agent.py::SoftwareDevelopmentAgent` inheriting `BaseAgent`.

Input:
- Product Brief
- PRD
- Approved product decisions
- Existing code state (incremental development)

Output:
- Technical Plan artifact
- Source code files in project workspace
- Feature Implementation Records
- Test Report artifact
- Deployment Guide artifact
- Development decisions

### 3.2 Development Session State

Create `kyrozen/development/state.py::DevelopmentSession`:

```python
@dataclass
class DevelopmentSession:
    project_id: str
    stage: str  # technical_planning / initializing / implementing / testing / debugging / completed
    technical_plan: TechnicalPlan = field(default_factory=TechnicalPlan)
    feature_records: list[FeatureImplementation] = field(default_factory=list)
    test_report: TestReport = field(default_factory=TestReport)
    logs: list[str] = field(default_factory=list)
```

### 3.3 Core Data Models

Create `kyrozen/development/models.py`:

```python
@dataclass
class TechnicalPlan:
    application_type: str = ""  # web_app, website, simple_saas, ai_tool, automation_tool, desktop_app
    architecture: str = ""
    frontend: str = ""
    backend: str = ""
    database: str = ""
    apis: str = ""
    deployment: str = ""
    dependencies: list[str] = field(default_factory=list)

@dataclass
class FeatureImplementation:
    prd_feature: str = ""  # links back to PRD feature name
    files: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    status: str = "pending"  # pending / implemented / tested / failed
    notes: str = ""

@dataclass
class TestReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: list[dict] = field(default_factory=list)
    fix_history: list[dict] = field(default_factory=list)

@dataclass
class DeploymentGuide:
    run_instructions: str = ""
    deployment_instructions: str = ""
```

## 4. PRD-to-Code Traceability Mechanism

This is the central requirement of Phase 6.

### 4.1 Mapping Rule

Every code file and test file must be traceable back to one PRD feature:

```
PRD Feature: "用户可以上传图片"
  └─ Implementation:
       ├─ frontend/src/components/ImageUpload.tsx
       ├─ backend/app/api/upload.py
       └─ backend/app/storage.py
  └─ Tests:
       ├─ tests/test_upload.py
       └─ tests/e2e/upload.spec.ts
```

### 4.2 Feature Implementation Record

The `FeatureImplementation` model is saved as a `feature_implementation_record` artifact (JSON) and updated as development progresses.

### 4.3 Agent Prompt Rule

The Software Development Agent system prompt must require:
- "For every file you create, include a comment header that names the PRD feature it implements."
- "Before writing code, identify which PRD feature this task serves."
- "Do not implement features listed in PRD.out_of_scope."
- "Do not expand PRD scope with new product features."

## 5. Tools Needed

Phase 6 reuses existing Phase 1 tools and adds new ones.

### 5.1 Reused Tools

| Tool | Purpose |
|---|---|
| `file_read` | Read existing source files |
| `file_write` | Create/modify source files |
| `list_dir` | Explore project structure |
| `find_files` | Find source/test files |
| `terminal` | Run package managers, tests, lint, servers |
| `git` | Init, commit, diff, log |

### 5.2 New Development Tools

Create `kyrozen/tools/development_tools.py`:

| Tool | Actions | Purpose |
|---|---|---|
| `save_technical_plan` | `save` | Persist Technical Plan artifact |
| `save_feature_implementation` | `save` | Persist Feature Implementation Record |
| `save_test_report` | `save` | Persist Test Report artifact |
| `save_deployment_guide` | `save` | Persist Deployment Guide artifact |
| `record_development_decision` | `record` | Record dev decisions (e.g., chosen stack) |

All tools accept `project_id` and delegate to `ProjectManager.save_artifact()`.

## 6. Project Workspace Layout for Software Project

Each Kyrozen project gets a self-contained software project directory:

```
projects/{project_id}/
├── memory.json
├── software/                  # Phase 6 software project root
│   ├── README.md
│   ├── technical_plan.json
│   ├── package.json / pyproject.toml / requirements.txt
│   ├── frontend/
│   ├── backend/
│   ├── database/
│   ├── tests/
│   └── .git/                  # Initialized by GitTool
└── ...
```

The software project root is computed as:

```python
software_dir = os.path.join(config.project_dir(project_id), "software")
```

All file writes from the Software Development Agent must be scoped to this directory.

## 7. API Changes

### 7.1 Chat Mode

Extend `ChatRequest.mode` to include `"development"`.

Route the development agent:

```python
elif request.mode == "development":
    agent = _get_development_agent()
    context = builder.build_development_context(project)
```

### 7.2 State Endpoint

Add:

```python
@app.get("/api/projects/{project_id}/development/state")
async def api_development_state(project_id: str):
    # Return technical_plan, feature_records, test_report, deployment_guide, recent commits
```

## 8. Web UI Changes

Add a "Software Development" mode button on the project detail page.

New view `view-development` shows:
- PRD summary (read-only)
- Technical Plan panel
- Development task list / progress
- File tree / recent changes
- Test results
- Deployment instructions
- Git log

## 9. Development Constraints

- No hardware/firmware/BOM/PCB/CAD (Phase 7).
- No microservices/Kubernetes for simple MVPs.
- No adding PRD-out-of-scope features.
- Agent must present technical plan for confirmation before writing code.
- Every commit records the related PRD feature.

## 10. Implementation Order

1. Create `kyrozen/development/models.py` and `kyrozen/development/state.py`
2. Create `kyrozen/development/agent.py::SoftwareDevelopmentAgent`
3. Create `kyrozen/tools/development_tools.py`
4. Register tools in `kyrozen/tools/registry.py`
5. Add `build_development_context()` to `kyrozen/project/context.py`
6. Add development agent and `/development/state` endpoint to `kyrozen/api/server.py`
7. Add Software Development view to `kyrozen/web/index.html`
8. Write `tests/test_development.py`
9. Run all tests, restart server, open browser
