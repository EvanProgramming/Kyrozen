# Graph Report - .  (2026-08-01)

## Corpus Check
- 275 files · ~182,426 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 4189 nodes · 9765 edges · 218 communities (194 shown, 24 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 779 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- .__init__()
- apiGet()
- .__post_init__()
- .__init__()
- .__init__()
- .__init__()
- .__init__()
- .__init__()
- .__init__()
- # TODO: wire into
- .__init__()
- .__init__()
- .__init__()
- .__init__()
- .__post_init__()
- .__init__()
- ._cancel_task_timeout_timer()
- .__init__()
- .__init__()
- .__init__()
- _store()
- .__post_init__()
- @supabase/supabase-js
- .__post_init__()
- App()
- .__init__()
- .__init__()
- .__init__()
- apiDelete()
- @electron/notarize
- 1. Clone or enter
- .__post_init__()
- .__init__()
- .__post_init__()
- .to_dict()
- 128
- .canonical_feature_values()
- .build()
- .chat()
- Any
- checkAndUpdateHardwareToolchain()
- ACTION_LABELS
- .from_dict()
- .__init__()
- .__init__()
- .__getattr__()
- AGENT_MODE_HINTS
- .__init__()
- .__init__()
- .__post_init__()
- .__init__()
- .confirm_code()
- 1. 目的与完成定义
- .__init__()
- .__init__()
- classifyCreateRepoError()
- .broadcast_to_user()
- 128
- .__init__()
- ._action_required()
- browser-extension/popup.js
- api.ts
- allowArbitraryExtensions
- .__init__()
- .__init__()
- .__init__()
- allowImportingTsExtensions
- .__call__()
- .__init__()
- .__init__()
- Any
- afterSign
- AttachmentInfo
- - http://localhost:5173 用于开发模式
- .test_all_nine_modes_build_correct_agent()
- .__init__()
- .__post_init__()
- .__getattr__()
- apiClient
- allowImportingTsExtensions
- Database backend factory for
- .__init__()
- ._enforce_question_protocol()
- .from_dict()
- .__init__()
- ._execute()
- Any
- .check_token()
- ._persist()
- .build_testing_context()
- ._row_to_decision()
- .__init__()
- assertConnectionConnected()
- .__post_init__()
- .__post_init__()
- .__init__()
- Case
- buildChromeManifest()
- 1. 定位
- BLOCKED_KEYS
- .__init__()
- _load_desktop_agent_module()
- .from_dict()
- ._find_existing_artifact()
- _brief_from_state()
- api_client()
- dependencies
- .__init__()
- ._load_index()
- .to_dict()
- .__init__()
- _make_save_tool()
- ClipPayload
- checkForUpdates()
- App()
- .build_hardware_context()
- .__post_init__()
- .__init__()
- ._execute()
- captureCurrentPage()
- downloadFile()
- crypto
- .__init__()
- .onBegin()
- ._onData()
- CompleteStep()
- _chunk()
- ensureProjectVenv()
- build
- buildDesktop()
- 1. 在 Cloudflare 添加站点
- ._summarize_hardware_dir()
- .from_dict()
- category
- allowSyntheticDefaultImports
- Copy .env.example to .env,
- 2. Set KYROZENDBBACKEND=postgres and
- Automated Verification
- .detect()
- .check_quota()
- .find_missing_dimensions()
- auth_client()
- $schema
- .__init__()
- fixture
- AGENTS.md
- author
- crypto
- .__init__()
- .__post_init__()
- .execute()
- _make_image()
- test_desktop_stage_intent.py
- _FakeModel
- buildTree()
- .__post_init__()
- .__post_init__()
- .__post_init__()
- Kyrozen Missing Features Three
- _read_until_id()
- collectErrors()
- base64Url()
- apply_migrations.py
- browser-extension/background.js
- allowToChangeInstallationDirectory
- Kyrozen Favicon
- Expanding the Oxlint configuration
- .verify_refresh_token()
- .summary()
- notarize.cjs
- macOS 免费未公证版安装
- Kyrozen 第一阶段真实复验报告
- docs/README.md
- files
- .__init__()
- Browser Extension Icon
- electron-builder
- eslint
- vite
- electronApp
- _strip_question_block()
- .cancel()
- .merge()
- .to_markdown()
- Kyrozen Core — AI
- web/__init__.py
- Kyrozen Browser Extension Icon
- Kyrozen Browser Extension Icon
- Vite Logo

## God Nodes (most connected - your core abstractions)
1. `ToolResult` - 154 edges
2. `ToolSchema` - 106 edges
3. `KyrozenDatabase` - 103 edges
4. `ToolParameter` - 103 edges
5. `BaseAgent` - 88 edges
6. `ToolRegistry` - 88 edges
7. `Tool` - 84 edges
8. `ProjectManager` - 82 edges
9. `LearningRepository` - 81 edges
10. `get_default_registry()` - 80 edges

## Surprising Connections (you probably didn't know these)
- `Self-hosted Docker Compose Stack` --semantically_similar_to--> `Docker Compose Stack`  [INFERRED] [semantically similar]
  docker-compose.selfhosted.yml → docker-compose.yml
- `Pinned Python Dependencies` --semantically_similar_to--> `Python Dependency Requirements`  [INFERRED] [semantically similar]
  requirements-lock.txt → requirements.txt
- `PendingConfirmation` --uses--> `BaseAgent`  [INFERRED]
  desktop/python_agent/main.py → kyrozen/core/agent.py
- `PendingConfirmation` --uses--> `HandoffStore`  [INFERRED]
  desktop/python_agent/main.py → kyrozen/core/handoff.py
- `PendingConfirmation` --uses--> `HandoffTool`  [INFERRED]
  desktop/python_agent/main.py → kyrozen/core/handoff.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Kyrozen Multi-client Architecture** — concept_multi_client_application, concept_desktop_local_agent, concept_websocket_task_sync, frontend_index_kyrozen, desktop_index_kyrozen_desktop [INFERRED 0.85]
- **Self-hosted Deployment Stack** — docker_compose_selfhosted, concept_self_hosted_backend, concept_cloudflare_tunnel, docs_selfhosted_deployment [EXTRACTED 1.00]
- **Phase 1 Real-user Acceptance** — docs_kyrozen_missing_features_three_phase_plan, docs_phase1_real_acceptance_rerun_2026_07_29, docs_phase1_real_reacceptance_report_2026_07_29, concept_real_user_acceptance [INFERRED 0.85]

## Communities (218 total, 24 thin omitted)

### Community 0 - ".__init__()"
Cohesion: 0.05
Nodes (49): HandoffTool, Structured agent handoff state for Kyrozen. Persists confirmed goals, non-…, Tool that lets any agent record structured handoff facts in real time., ABC, Base types for the Kyrozen tool system. Every tool must expose: - name -…, Definition of one tool parameter., Schema describing a tool and its supported actions., Base class for all Kyrozen tools. (+41 more)

### Community 1 - "apiGet()"
Cohesion: 0.03
Nodes (64): apiGet(), ArtifactFull, ArtifactSummary, AuditEvent, buildConfirmationDetail(), cancelledTaskIds, ChatMessage, chooseWorkspaceRoot() (+56 more)

### Community 2 - ".__post_init__()"
Cohesion: 0.06
Nodes (45): Software Development module for Kyrozen Phase 6., Changelog, DeploymentGuide, DevelopmentArtifactBundle, FeatureImplementation, Any, Data models for Kyrozen Phase 6 Software Development. These models capture the…, Traceability record linking a PRD feature to code and tests. (+37 more)

### Community 3 - ".__init__()"
Cohesion: 0.04
Nodes (43): HardwareBridge, HardwareBridgeError, Any, Exception, Path, Local Hardware Bridge for compiling and uploading firmware. The bridge wraps…, Compile the firmware project., Upload compiled firmware to the board. (+35 more)

### Community 4 - ".__init__()"
Cohesion: 0.07
Nodes (7): _adapt_sql(), PostgresDatabase, Any, Project, Self-hosted PostgreSQL persistence adapter for Kyrozen., Convert SQLite-style SQL to PostgreSQL-compatible syntax., Thread-safe PostgreSQL database for projects, tasks, decisions, and artifacts.

### Community 5 - ".__init__()"
Cohesion: 0.05
Nodes (53): KyrozenConfig, Central configuration object., Return a list of validation issues., make_authenticated_app(), MockModel, Any, A deterministic model for testing agent loops., Create a FastAPI app with authentication overridden for tests. (+45 more)

### Community 6 - ".__init__()"
Cohesion: 0.06
Nodes (36): ABC, Base abstractions for research tools in Kyrozen Phase 4., Abstract base for external search providers., Return True if this provider is configured and ready., Placeholder provider used when no real search API is configured., SearchProvider, UnconfiguredSearchProvider, Research tools for Kyrozen Phase 4. (+28 more)

### Community 7 - ".__init__()"
Cohesion: 0.07
Nodes (34): Isolated backend used only by the desktop release journey. It deliberately uses…, ReleaseJourneyModel, callable, Cloud-proxied model provider for the Kyrozen desktop client. The desktop client…, ModelInterface, ModelResponse, ABC, Unified model interface for Kyrozen Core. Business logic must use… (+26 more)

### Community 8 - ".__init__()"
Cohesion: 0.09
Nodes (6): KyrozenDatabase, Any, Connection, Project, Thread-safe SQLite database for projects, tasks, decisions, and artifacts., Add desktop-client related columns to existing tasks tables.

### Community 9 - "# TODO: wire into"
Cohesion: 0.19
Nodes (53): BaseModel, AnalyticsSummaryResponse, ChatRequest, ConfirmRequest, create_app(), CreateArtifactRequest, CreateDecisionRequest, CreateEventRequest (+45 more)

### Community 10 - ".__init__()"
Cohesion: 0.08
Nodes (7): Any, Exception, Project, Supabase PostgreSQL database adapter matching the SQLite KyrozenDatabase…, Run an upsert and tolerate transient network errors., Run an insert and tolerate transient network errors., SupabaseDatabase

### Community 11 - ".__init__()"
Cohesion: 0.05
Nodes (31): AgentFactory, _get_agent(), _get_agent_factory(), _get_discovery_agent(), _get_hardware_agent(), _get_learning_agent(), _get_planning_agent(), _get_research_agent() (+23 more)

### Community 12 - ".__init__()"
Cohesion: 0.06
Nodes (36): ProblemDiscoveryAgent, Any, Problem Discovery Agent for Kyrozen Phase 3. This agent inherits from BaseAgent…, Re-evaluate confidence and decision for the current brief., Agent specialized in problem discovery and problem brief generation., Build a context string that includes the current brief and recent Q&A., Problem Brief data model for Kyrozen Phase 3. A Problem Brief captures the…, assess_confidence() (+28 more)

### Community 13 - ".__init__()"
Cohesion: 0.08
Nodes (41): FileReadTool, FileWriteTool, FindFilesTool, ListDirTool, File system tools for Kyrozen Core., Find files matching a glob pattern., Write content to a file., List directory contents. (+33 more)

### Community 14 - ".__post_init__()"
Cohesion: 0.07
Nodes (33): Testing and Validation module for Kyrozen Phase 8., IterationPlan, Data models for Kyrozen Phase 8 Testing, Validation and Iteration Loop., Execution result for a single test case., Collection of test cases tied to product requirements., One piece of user validation feedback., Plan of what to keep, modify, remove, investigate, or add next., Product validation report combining engineering tests and user feedback. (+25 more)

### Community 15 - ".__init__()"
Cohesion: 0.06
Nodes (21): Result of a tool execution., ToolResult, Any, Path, Re-scan the stage gate so the freshly written PROBLEM.md is detected, then…, Resolve the workspace root so we can write docs/PROBLEM.md. Prefer the live…, GitTool, Any (+13 more)

### Community 16 - "._cancel_task_timeout_timer()"
Cohesion: 0.07
Nodes (21): DesktopAgentRuntime, main(), Path, Task, Stop the task timeout timer if it is still running., Mark the current task as timed out and cancel the agent., Read .kyrozen/PLAN.json from the workspace, if present. P0-R6: the file is the…, Report concise tool activity, keep the status bar and operation log, and route… (+13 more)

### Community 17 - ".__init__()"
Cohesion: 0.07
Nodes (27): Base agent runtime for Kyrozen Core. Future professional agents…, Any, Task management system for Kyrozen Core., A long-running task with status, steps, results, and errors., Task, Software Development Agent for Kyrozen Phase 6. The agent receives an approved…, _make_agent(), Path (+19 more)

### Community 18 - ".__init__()"
Cohesion: 0.07
Nodes (27): MemoryInterface, MemoryRecord, ABC, Any, Memory interface for Kyrozen Core. Phase 1 provides a save/query/update/delete…, A single memory record., Abstract memory interface., Save a memory and return the created record. (+19 more)

### Community 19 - ".__init__()"
Cohesion: 0.07
Nodes (29): ProjectManager, Any, Project, High-level manager for project workspaces., Create a new project., Restore an archived project back to active status., Project, A Kyrozen project workspace. (+21 more)

### Community 20 - "_store()"
Cohesion: 0.13
Nodes (42): advance(), compute_gate(), compute_progress(), detect_deliverables(), Scan the workspace for deliverable files of the given stage., Progress = (completed earlier stages + within-stage fraction) / total. The…, Re-scan the workspace, recompute progress, persist and return the gate., Perform a stage transition. mode: * 'normal' -- only if the current stage gate… (+34 more)

### Community 21 - ".__post_init__()"
Cohesion: 0.08
Nodes (24): Product Planning module for Kyrozen Phase 5., Feature, PRD, ProductBrief, Data models for Kyrozen Phase 5 Product Planning. These models capture product…, One product feature with priority., One candidate solution for solving the problem., Comparison of multiple candidate solutions. (+16 more)

### Community 22 - "@supabase/supabase-js"
Cohesion: 0.05
Nodes (43): axios, dependencies, axios, react, react-dom, react-router-dom, @supabase/supabase-js, tailwindcss (+35 more)

### Community 23 - ".__post_init__()"
Cohesion: 0.07
Nodes (9): LearningArtifactBundle, _now(), Any, A validated success pattern extracted from project history., Bundle of all Phase 9 artifacts for easy serialization., SuccessKnowledge, Any, Return matching learning records as plain dicts for suggestion generation. (+1 more)

### Community 24 - "App()"
Cohesion: 0.07
Nodes (30): App(), formatQuota(), Project, QuotaInfo, UpdateStatus, UserProfile, EditorPanel(), Props (+22 more)

### Community 25 - ".__init__()"
Cohesion: 0.08
Nodes (19): ExecutionPlan, PlanStep, Any, Data model for explicit, file-backed execution plans. Each Kyrozen agent…, Update one step's status. Returns True if the step was found., One concrete step the agent intends to perform., Structured plan for the current stage of a project., Any (+11 more)

### Community 26 - ".__init__()"
Cohesion: 0.11
Nodes (20): CompletedProcess, AIImageAnalyzer, _as_float(), _as_int(), AttachmentError, _find_bin(), ImageAnalysis, ImageAnalyzer (+12 more)

### Community 27 - ".__init__()"
Cohesion: 0.10
Nodes (24): Tools for software development in Kyrozen Phase 6. These tools allow the…, Save or update the iteration Changelog and write it to CHANGELOG.md. In…, Save or update the Technical Plan artifact for a project. In addition to…, SaveChangelogTool, SaveTechnicalPlanTool, Save or update the Problem Brief artifact for a project. In addition to…, SaveProblemBriefTool, Tools for product planning in Kyrozen Phase 5. These tools allow the agent to… (+16 more)

### Community 28 - "apiDelete()"
Cohesion: 0.15
Nodes (37): apiDelete(), apiPatch(), apiPost(), apiPut(), clearDispatchWatchdog(), clearTaskTimeout(), connectWebSocket(), getTaskTimeoutForPayload() (+29 more)

### Community 29 - "@electron/notarize"
Cohesion: 0.05
Nodes (37): devDependencies, autoprefixer, electron, @electron/notarize, @eslint/js, globals, @playwright/test, postcss (+29 more)

### Community 30 - "1. Clone or enter"
Cohesion: 0.06
Nodes (35): 1. Clone or enter the project, 1. Configure Supabase, 2. Configure Environment, 2. Copy environment template, 3. Build and Run, 3. Edit .env for local SQLite, 4. Build and run, 4. Configure Reverse Proxy (+27 more)

### Community 31 - ".__post_init__()"
Cohesion: 0.10
Nodes (32): IterationItem, One recommendation for the next iteration., iteration_plan_data(), Any, fixture, TestClient, Tests for Kyrozen Phase 8 Testing, Validation and Iteration Loop., _seed_prd() (+24 more)

### Community 32 - ".__init__()"
Cohesion: 0.09
Nodes (27): _detect_intended_stage(), _make_ai_image_analyzer(), _make_asr_fn(), PendingConfirmation, Python Agent Runtime entry point for Kyrozen Desktop Client. Reads JSON-RPC…, Build an image analyzer using OmniRoute vision (fallback: Gemini direct)., Build a Gemini-based speech-to-text function for video transcription., Return the furthest lifecycle stage the user's message clearly intends to move… (+19 more)

### Community 33 - ".__post_init__()"
Cohesion: 0.12
Nodes (15): LearningExtractor, Rule-based learning extraction from project events., Extract reusable learning records from Phase 8 and earlier events., Return proposed records, failures, and successes without saving them., FailureKnowledge, LearningEvent, LearningRecord, A validated failure pattern extracted from project history. (+7 more)

### Community 34 - ".to_dict()"
Cohesion: 0.10
Nodes (30): classify_create_repo_error(), classify_push_error(), CreateRepoFailure, PushFailure, PushResult, Local Git operations for Kyrozen project workspaces (3.5). All operations run…, Map raw git push stderr to one of the five required failure kinds., Map a GitHub create-repo HTTP response to a failure kind. (+22 more)

### Community 35 - "128"
Cohesion: 0.06
Nodes (32): action, default_popup, default_title, background, service_worker, description, suggested_key, commands (+24 more)

### Community 36 - ".canonical_feature_values()"
Cohesion: 0.14
Nodes (27): build_feature_records(), generate_app_source(), generate_cli_source(), generate_env_example(), generate_gitignore(), generate_readme(), generate_requirements(), generate_sources() (+19 more)

### Community 37 - ".build()"
Cohesion: 0.12
Nodes (24): _add_requirement(), analyze_failure(), apply_repair(), FailureInfo, _kill_preview_proc(), load_manifest(), Path, Re-create app.py / tests from the manifest spec (fixes syntax errors). (+16 more)

### Community 38 - ".chat()"
Cohesion: 0.10
Nodes (31): build_agent(), Tests for the BaseAgent runtime., If the model outputs only an inline tool-call JSON, the final answer must not…, If the model keeps requesting tools, the agent must still produce a non-JSON…, Some models emit XML-style tool calls; the agent must parse them., XML tool-call blocks should be removed from the conversational text., A full loop with an XML tool call must execute the tool and return a clean…, When a confirmation callback approves, the tool should execute. (+23 more)

### Community 39 - "Any"
Cohesion: 0.11
Nodes (31): architecture_data(), assembly_step_data(), bom_data(), bom_item_data(), component_data(), debug_record_data(), firmware_data(), Any (+23 more)

### Community 40 - "checkAndUpdateHardwareToolchain()"
Cohesion: 0.14
Nodes (31): checkAndUpdateHardwareToolchain(), ensureArduinoCLI(), ensurePlatformIO(), extractArchive(), fetchLatestArduinoVersion(), fetchLatestPlatformIOVersion(), fileExists(), getArduinoAssetUrl() (+23 more)

### Community 41 - "ACTION_LABELS"
Cohesion: 0.10
Nodes (24): archiveProject(), createProject(), deleteProject(), getProject(), getProjectState(), listProjects(), renameProject(), restoreProject() (+16 more)

### Community 42 - ".from_dict()"
Cohesion: 0.10
Nodes (18): MVP, ProductGoal, Any, Minimum Viable Product scope., High-level goal of the product., Concrete description of the target user., Before / During / After user experience., TargetUser (+10 more)

### Community 43 - ".__init__()"
Cohesion: 0.11
Nodes (15): ConfirmationStore, PendingConfirmation, Any, Path, Persistent confirmation queue (feature 3.4, requirements #4 and #5). A…, Create a confirmation. If the type is already trusted for this project, the…, Return ``(execute?, pending_id_or_None)``. ``execute`` is True when the…, Load pending confirmations from disk (used after an app restart). (+7 more)

### Community 44 - ".__init__()"
Cohesion: 0.12
Nodes (22): _column_present(), _is_missing_column_error(), _is_missing_table_error(), Any, Exception, Startup schema preflight for the desktop / task tables. The desktop client…, Return True if the column is queryable, False if explicitly missing. Any other…, Verify the desktop schema; raise :class:`SchemaError` if anything is missing.… (+14 more)

### Community 45 - ".__getattr__()"
Cohesion: 0.10
Nodes (21): PlanDetectingModelProvider, callable, Wraps a model provider and emits the first execution plan it detects., Detect a real execution plan in model output. A "real" plan must have an…, _make(), parametrize, Regression tests for the plan-detection heuristic (P0-R5). The previous…, Even with an explicit heading, status-report bullets must be filtered so the… (+13 more)

### Community 46 - "AGENT_MODE_HINTS"
Cohesion: 0.09
Nodes (27): AGENT_MODE_HINTS, AGENT_MODE_ICONS, APP_TYPE_LABELS, ChatPage(), ChatPageProps, ConfirmationRequest, DegradedInfo, DELIVERABLE_LABELS (+19 more)

### Community 47 - ".__init__()"
Cohesion: 0.08
Nodes (27): _decode_github_oauth_state(), _encode_github_oauth_state(), _extract_question_text(), _get_context_builder(), _get_desktop_manager(), _get_learning_repository(), _get_owned_project(), _get_project_manager() (+19 more)

### Community 48 - ".__init__()"
Cohesion: 0.11
Nodes (10): HandoffEntry, HandoffStore, _now(), Any, Path, Snapshot the structured state when the active agent changes., Render the structured state as a context block for the next agent., One structured item recorded during a conversation. (+2 more)

### Community 49 - ".__post_init__()"
Cohesion: 0.11
Nodes (16): Hardware Development module for Kyrozen Phase 7., BOM, Component, FirmwareProject, Data models for Kyrozen Phase 7 Hardware Development., A specific hardware component with technical details., Base validation hook for subclasses to chain via super()., Bill of Materials for the hardware prototype. (+8 more)

### Community 50 - ".__init__()"
Cohesion: 0.17
Nodes (27): BuildRunner, CommandExecutor, Runs shell commands in a working directory (real subprocess)., Runs install/start/build/test/core-flow against a scaffolded project., parametrize, Path, Tests for the 3.3 real software generation / run / repair engine. Covers every…, _scaffold_web() (+19 more)

### Community 51 - ".confirm_code()"
Cohesion: 0.14
Nodes (19): DesktopPairingManager, DesktopTokenManager, _now(), _purge_expired(), Any, Token management for desktop client authentication. The desktop client uses a…, Return user_id if the WebSocket token is valid., Return user_id if a desktop REST API token is valid. (+11 more)

### Community 52 - "1. 目的与完成定义"
Cohesion: 0.07
Nodes (27): 1. 目的与完成定义, 2. 阶段总览, 3. 第一阶段：软件项目完整链路, 3.1 专用 Agent 路由与交接, 3.2 阶段门禁与真实进度, 3.3 真实软件生成、运行与修复, 3.4 附件、状态、操作记录与确认, 3.5 本地 Git 与 GitHub 完整流程 (+19 more)

### Community 53 - ".__init__()"
Cohesion: 0.12
Nodes (18): PermissionDecision, PermissionManager, Any, Permission system for Kyrozen Core. Distinguishes low-risk and high-risk…, Decides whether a tool action is allowed under the current mode., User explicitly confirmed the action., Mark a high-risk action as trusted for the remainder of the session., Clear all session-level trust grants. (+10 more)

### Community 54 - ".__init__()"
Cohesion: 0.11
Nodes (23): HTTPAuthorizationCredentials, Request-scoped authentication context., _cache_path(), _decode_supabase_token(), get_current_user(), get_current_user_optional(), _get_signing_key_with_retry(), _load_cached_jwks() (+15 more)

### Community 55 - "classifyCreateRepoError()"
Cohesion: 0.15
Nodes (23): classifyCreateRepoError(), classifyPushError(), commitAndPush(), CREATE_REPO_FAILURE_RECOVERY, CreateRepoResult, ensureKyrozenGitignore(), getAutoCommit(), getConfigPath() (+15 more)

### Community 56 - ".broadcast_to_user()"
Cohesion: 0.13
Nodes (14): DesktopClientManager, Any, Send a message to all online clients for a user., Update the currently active project for a client., Track online desktop clients and route tasks to them., Register a new desktop client connection., Mark a client as offline., Return all clients for a user, most recently active first. (+6 more)

### Community 57 - "128"
Cohesion: 0.08
Nodes (24): action, default_icon, default_popup, background, service_worker, content_scripts, 128, 16 (+16 more)

### Community 58 - ".__init__()"
Cohesion: 0.12
Nodes (16): Enum, coerce_state(), Any, Path, User-facing agent status (feature 3.4, requirement #2). The status bar must…, The only six states the status bar is allowed to show., Return a StatusState for ``state`` or ``None`` if it is not one of the six., Tracks the current agent status and its history for one workspace. (+8 more)

### Community 59 - "._action_required()"
Cohesion: 0.11
Nodes (13): Any, Task, Extract tool-call JSON objects (and XML-style tool calls) from the model…, Find tool-call JSON objects/arrays embedded anywhere in the text., Parse XML-style tool calls like…, Remove code blocks, inline tool-call JSON, and XML tool-call blocks, keeping…, Execute tool calls and return their results., Execute the agent loop for an already-created task. (+5 more)

### Community 60 - "browser-extension/popup.js"
Cohesion: 0.11
Nodes (22): checkConnection(), extractPageData(), getServerUrl(), sendClip(), Cloudflare Tunnel, Desktop Local Agent, macOS Gatekeeper Installation, Self-hosted Backend (+14 more)

### Community 61 - "api.ts"
Cohesion: 0.13
Nodes (19): confirmTask(), getChatHistory(), getTask(), sendChatMessage(), QuestionData, QuestionModal(), QuestionModalProps, QuestionOption (+11 more)

### Community 62 - "allowArbitraryExtensions"
Cohesion: 0.08
Nodes (23): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+15 more)

### Community 63 - ".__init__()"
Cohesion: 0.11
Nodes (16): Any, QuotaManager, Quota management for desktop client model proxy requests. MVP implementation…, Tracks per-user token usage and enforces configurable limits., Initialize the manager. ``default_limit`` is the fallback per-user token limit.…, Set or update a per-user token limit., Add consumed tokens to the user's running total., Return the current token usage for a user. (+8 more)

### Community 64 - ".__init__()"
Cohesion: 0.13
Nodes (18): InMemoryMemory, Simple in-memory memory implementation with keyword matching., ProjectContextBuilder, Any, Assemble project context to inject into agent conversations., Build a context string for the given project., Load project and build context; return None if not found., test_build_development_context_loads_prd() (+10 more)

### Community 65 - ".__init__()"
Cohesion: 0.11
Nodes (17): _detect_provider_from_env(), get_config(), _load_config_file(), _load_dotenv(), _load_provider_costs(), _parse_bool(), Any, Unified configuration for Kyrozen Core. Reads from environment variables and a… (+9 more)

### Community 66 - "allowImportingTsExtensions"
Cohesion: 0.09
Nodes (22): compilerOptions, allowImportingTsExtensions, baseUrl, isolatedModules, jsx, lib, module, moduleResolution (+14 more)

### Community 67 - ".__call__()"
Cohesion: 0.16
Nodes (19): build_authorize_url(), GitHubClient, Build the OAuth authorize URL. The client *secret* is never included., GitHub API client. Pass a custom ``transport`` to test without network., _bare(), FakeTransport, Tests for kyrozen.core.github (3.5): OAuth URL safety, code exchange, user…, Records calls and returns scripted (status, json) responses. (+11 more)

### Community 68 - ".__init__()"
Cohesion: 0.14
Nodes (11): DiagnosticsLog, OperationLog, OperationRecord, Any, Path, Operation records and diagnostic records (feature 3.4, requirements #3 and #6).…, Separate sink for noisy internal data. Never shown in the operation log., Append-only, time-ordered log of user-facing tool operations. (+3 more)

### Community 69 - ".__init__()"
Cohesion: 0.19
Nodes (20): Analyze project artifacts and generate improvement suggestions., SuggestionGenerator, DeleteLearningRecordTool, _LearningTool, Tools for Kyrozen Phase 9 Learning and Proactive Improvement., Save a validated success pattern to the database., Delete a learning record from the database by its record id., Update the status of a suggestion (accepted, rejected, later, ignored). (+12 more)

### Community 70 - "Any"
Cohesion: 0.13
Nodes (20): competitor_data(), Any, fixture, TestClient, Tests for Kyrozen Phase 4 Market Research., report_data(), research_source_data(), test_competitor_serialization() (+12 more)

### Community 71 - "afterSign"
Cohesion: 0.09
Nodes (22): build, afterSign, appId, directories, dmg, extraResources, files, linux (+14 more)

### Community 72 - "AttachmentInfo"
Cohesion: 0.10
Nodes (21): ConnectionState, AttachmentInfo, FeatureRecord, InteractionStatus, KyrozenAPI, LoginResult, OperationLogEntry, PendingConfirmationInfo (+13 more)

### Community 73 - "- http://localhost:5173 用于开发模式"
Cohesion: 0.09
Nodes (21): 前提条件, 1.  clone 代码到服务器, 2.  配置环境变量, 3.  配置 Caddy（反向代理 + HTTPS）, 4.  启动服务, 5.  验证后端, 6.  桌面客户端连接, AI 模型 (+13 more)

### Community 74 - ".test_all_nine_modes_build_correct_agent()"
Cohesion: 0.16
Nodes (6): AgentRouter, The single router that maps a task to a specialized agent., parametrize, TestDegradation, TestResolveMode, TestRouteAgentSelection

### Community 75 - ".__init__()"
Cohesion: 0.16
Nodes (14): CloudProxyModelProvider, Any, Return an iterator that yields chunks from the cloud stream. The desktop Agent…, Model provider that forwards chat requests to the cloud over WebSocket. Usage…, Synchronous wrapper around the async cloud chat call. This method is safe to…, Process an incoming model_stream_chunk or model_error from the cloud., captured(), provider() (+6 more)

### Community 76 - ".__post_init__()"
Cohesion: 0.13
Nodes (11): A proactive improvement suggestion generated for a project., Suggestion, Any, Find requirements without user feedback., Detect duplicate components in BOM., Detect high architectural complexity or untested critical features., Suggest validated successes and warn about known failures from other projects., Run all heuristic detectors and return new suggestions. (+3 more)

### Community 77 - ".__getattr__()"
Cohesion: 0.23
Nodes (5): KyrozenLogger, LogEntry, Any, A single structured log entry., Thread-safe structured logger with file + stdout output.

### Community 78 - "apiClient"
Cohesion: 0.21
Nodes (14): login(), logout(), register(), apiClient, handleApiError(), Navbar(), LoginPage(), RegisterPage() (+6 more)

### Community 79 - "allowImportingTsExtensions"
Cohesion: 0.10
Nodes (19): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+11 more)

### Community 80 - "Database backend factory for"
Cohesion: 0.15
Nodes (11): get_current_user_id(), Return the user id from the current request context, if any., Data models for Kyrozen Phase 9 Project Self-Learning and Proactive Improvement., Database-backed repository for Kyrozen Phase 9 learning memory., Proactive suggestion generation for Kyrozen Phase 9., SQLite persistence for the Kyrozen Project Workspace., Database backend factory for Kyrozen., Project Workspace System for Kyrozen Phase 2. (+3 more)

### Community 81 - ".__init__()"
Cohesion: 0.30
Nodes (5): KYROZEN_AUTHOR_EMAIL, GitOps, Any, Thin, testable wrapper around the ``git`` CLI for one workspace., Initialize the repo on ``main`` with a ``.gitignore`` and, when the workspace…

### Community 82 - "._enforce_question_protocol()"
Cohesion: 0.16
Nodes (16): Split ``answer`` into (body, trailing question) if it ends in a question.…, Guarantee that a question reaching the user is always a question card. The…, _payload(), parametrize, Kyrozen must never ask the user anything in plain prose. Every question --…, A long paragraph ending in '?' is prose, not a question to click., Specialised agents fully override _build_system_prompt; they still cannot opt…, test_every_agent_inherits_the_protocol() (+8 more)

### Community 83 - ".from_dict()"
Cohesion: 0.13
Nodes (12): _arch_text(), FileTask, generate_project_spec(), load_software_feature(), Milestone, Any, Build a deterministic technical plan, directory tree, milestones and file-level…, A file-level task mapped to a PRD feature, with a repair trail. (+4 more)

### Community 84 - ".__init__()"
Cohesion: 0.15
Nodes (10): One external source collected during market research. Every source must record…, ResearchSource, Any, Return a list of ResearchSource objects for the given query., MockSearchProvider, Any, Deterministic provider for tests and demos., test_mock_search_provider() (+2 more)

### Community 85 - "._execute()"
Cohesion: 0.17
Nodes (13): Any, _get_allowed_root(), Any, Path, Path safety helpers for Kyrozen tools. All file-system and shell tools must…, Return the allowed workspace for the current tool call. If ``project_id`` is…, Resolve ``raw_path`` against ``allowed_root`` and enforce containment. Relative…, _resolve_safe_path() (+5 more)

### Community 86 - "Any"
Cohesion: 0.17
Nodes (17): api_client(), prd_data(), product_brief_data(), Any, fixture, TestClient, Tests for Kyrozen Phase 5 Product Planning., solution_comparison_data() (+9 more)

### Community 87 - ".check_token()"
Cohesion: 0.13
Nodes (11): classify_oauth_error(), CreateRepoResult, _default_transport(), GitHubApiError, GitHubUser, Any, Exception, GitHub API client + OAuth helpers for Kyrozen (3.5). The transport is… (+3 more)

### Community 88 - "._persist()"
Cohesion: 0.18
Nodes (10): build_read_only_registry(), Any, Unified agent routing for Kyrozen. ``AgentRouter`` is the single place that…, A persisted record of one routing decision., Wraps a ToolRegistry and hides/blocks a set of tool names. Blocked tools are…, Restrict a registry to read-only tools (degraded mode)., Return (mode, reason, intent_signals)., Resolve the mode, build the agent, and record the decision. Returns ``(agent,… (+2 more)

### Community 89 - ".build_testing_context()"
Cohesion: 0.25
Nodes (5): Build context for Testing & Validation mode., Any, Bundle of all Phase 8 artifacts for easy serialization., TestingArtifactBundle, test_testing_artifact_bundle_round_trip()

### Community 90 - "._row_to_decision()"
Cohesion: 0.15
Nodes (6): Record a decision in the project., Decision, Any, Update project fields and refresh updated_at., A recorded decision within a project., test_decision_to_from_dict()

### Community 91 - ".__init__()"
Cohesion: 0.35
Nodes (4): InteractionTool, _parse_json(), Any, _ws()

### Community 92 - "assertConnectionConnected()"
Cohesion: 0.19
Nodes (17): assertConnectionConnected(), attachDiagnostics(), buildDesktop(), DESKTOP_ROOT, ensureTestProject(), getMainLogPath(), launchApp(), ProjectSummary (+9 more)

### Community 93 - ".__post_init__()"
Cohesion: 0.13
Nodes (11): _apply_discovery_option_mappings(), _auto_update_discovery_brief(), _parse_json_response(), Return brief fields inferred from known option values., Parse a JSON object from a model response, tolerating markdown fences., Infer Problem Brief fields from the latest Q&A and persist them. This is a…, EvidenceItem, Any (+3 more)

### Community 94 - ".__post_init__()"
Cohesion: 0.12
Nodes (11): Competitor, Structured analysis of one competitor or existing solution., Any, Runtime state for market research on a single project., Move to the next research stage and log it., Add a source if its URL is not already recorded., Add a competitor if its name is not already recorded., Add a community feedback source. (+3 more)

### Community 95 - ".__init__()"
Cohesion: 0.21
Nodes (7): Path, Persists stage-gate state to ``.kyrozen/stagegate.json``. A record for an item…, After a report deliverable file is materialized on disk, re-scan the gate and…, Record a real build/test verification outcome into the stage gate. Called by…, record_report_deliverable(), record_verification_result(), StageGateStore

### Community 96 - "Case"
Cohesion: 0.21
Nodes (14): handleProtocolUrl(), loadCredentials(), redactProtocolUrl(), saveCredentials(), saveServerUrl(), shouldUseSafeStorage(), getWebSocketUrlFromHttp(), isIpAddress() (+6 more)

### Community 97 - "buildChromeManifest()"
Cohesion: 0.16
Nodes (14): buildChromeManifest(), buildFirefoxManifest(), getBrowserNativeMessagingDirs(), getHostExecutablePath(), HostManifest, registerNativeMessagingHost(), ConnectionState, PlanPayload (+6 more)

### Community 98 - "1. 定位"
Cohesion: 0.12
Nodes (15): 1. 定位, 10. 相关文档, 2. 技术栈, 3. 目录结构, 4. 开发环境, 5. 运行开发版, 6. 核心流程, 6.1 登录与连接 (+7 more)

### Community 99 - "BLOCKED_KEYS"
Cohesion: 0.19
Nodes (14): BLOCKED_KEYS, empty(), LABELS, localSummary(), ProjectWorkspacePanel(), Props, readableKey(), Row (+6 more)

### Community 100 - ".__init__()"
Cohesion: 0.17
Nodes (9): _get_development_agent(), Any, Path, Task, Best-effort: recover PRD JSON saved by the planning stage., Agent specialized in building a runnable software prototype from a PRD., Only force tool execution when the user is asking to build, and the workspace…, The model failed to write any files -- scaffold the project ourselves with the… (+1 more)

### Community 101 - "_load_desktop_agent_module()"
Cohesion: 0.13
Nodes (8): Return True for modes that prefer the local desktop client., _requires_local_client(), Regression tests for the acceptance-2026-07-30 protocol/routing fixes. 1.…, A malformed block is salvaged into a valid free-text question card. The raw…, Open-ended questions must remain cards (free-text input), not prose., test_invalid_json_never_leaks_protocol(), test_local_first_routing_covers_all_chat_modes(), test_option_less_question_stays_a_card()

### Community 102 - ".from_dict()"
Cohesion: 0.18
Nodes (8): BOMItem, Any, A component line item in the project BOM with purchase metadata., One wire connection between a device pin and a target., WiringConnection, test_bom_item_validation(), test_component_serialization(), test_hardware_session_component_and_bom()

### Community 103 - "._find_existing_artifact()"
Cohesion: 0.17
Nodes (6): Save a project artifact. If an artifact of the same type/title exists, bump…, Return the latest version of an artifact of the given type., Artifact, A project artifact with versioning., Create a new version of this artifact., test_artifact_version_bump()

### Community 104 - "_brief_from_state()"
Cohesion: 0.24
Nodes (15): client(), fixture, _brief_from_state(), _create_project(), _make_client(), TestClient, End-to-end scenario tests for Problem Discovery. These tests simulate user…, E2E-03: simple existing solution should be flagged. (+7 more)

### Community 105 - "api_client()"
Cohesion: 0.22
Nodes (15): api_client(), fixture, TestClient, Tests for Project API endpoints., test_advance_project_stage_order(), test_chat_with_missing_project(), test_chat_with_project_context(), test_create_project() (+7 more)

### Community 106 - "dependencies"
Cohesion: 0.13
Nodes (15): dependencies, electron-updater, react, react-dom, react-markdown, remark-gfm, simple-git, ws (+7 more)

### Community 107 - ".__init__()"
Cohesion: 0.15
Nodes (10): FastAPI, _Bucket, _client_ip(), Request, RateLimiter, Lightweight in-memory rate limiting for API endpoints. The limiter tracks…, Sliding-window counter for a single client., Thread-safe sliding-window rate limiter keyed by client identifier. (+2 more)

### Community 108 - "._load_index()"
Cohesion: 0.23
Nodes (6): Attachment, AttachmentsManager, Stores, analyzes, and deletes attachments for one workspace., Return analyzed attachment content to inject into a requirements dialogue.…, test_attachment_other_kind_needs_no_ffmpeg(), test_attachment_validation_format_and_size()

### Community 109 - ".to_dict()"
Cohesion: 0.23
Nodes (13): _as_list(), build_deliverable(), _bullets(), DeliverableResult, normalize_fields(), Any, Path, Non-coding deliverable templates (Phase 1, 3.3 — requirement #8). For non-… (+5 more)

### Community 110 - ".__init__()"
Cohesion: 0.35
Nodes (5): GitGithubTool, Any, _ws(), The token is constructor-injected, never in params (3.5 #5)., test_git_github_tool_push_without_token_is_safe()

### Community 111 - "_make_save_tool()"
Cohesion: 0.30
Nodes (14): _make_save_tool(), _make_update_tool(), Path, Tests for the real execution-planning tools (P0-R6). Each Kyrozen agent must…, The data model guards against arbitrary stage values., Plan steps with bogus status should fail validation., test_save_plan_persists_structured_file(), test_save_plan_rejects_unknown_stage() (+6 more)

### Community 112 - "ClipPayload"
Cohesion: 0.25
Nodes (12): ClipPayload, createExtensionServer(), ExtensionServerCallbacks, getNativeMessagingPortFilePath(), hasValidBridgeToken(), isValidClip(), isValidTestReport(), readJsonBody() (+4 more)

### Community 113 - "checkForUpdates()"
Cohesion: 0.24
Nodes (10): UPDATE_PUBLIC_KEY, checkForUpdates(), fetchSignature(), hasTrustedMacSignature(), initAutoUpdater(), sendUpdateStatus(), sha512File(), stopUpdateChecks() (+2 more)

### Community 114 - "App()"
Cohesion: 0.18
Nodes (9): App(), ProtectedRoute(), ProtectedRouteProps, AppRouter(), DashboardPage, LoginPage, ProjectListPage, ProjectWorkspacePage (+1 more)

### Community 115 - ".build_hardware_context()"
Cohesion: 0.31
Nodes (6): HardwareArtifactBundle, Bundle of all Phase 7 artifacts for easy serialization., Any, Build context for Hardware Development mode., test_hardware_artifact_bundle_roundtrip(), test_hardware_session_serialization_roundtrip()

### Community 116 - ".__post_init__()"
Cohesion: 0.18
Nodes (9): __getattr__(), Market Research module for Kyrozen Phase 4., Lazy import MarketResearchAgent to avoid circular imports., MarketGap, Data models for Kyrozen Phase 4 Market Research. These models capture research…, Analysis of the remaining opportunity after reviewing existing solutions., Return today's date as an ISO 8601 string., _today_iso() (+1 more)

### Community 117 - ".__init__()"
Cohesion: 0.32
Nodes (7): _parse_fields(), _parse_prd(), _persist_feature_status(), Any, workspace_root parameter, falling back to the desktop config workspace., Update kyrozen_feature.json file tasks to reflect run/repair outcome., SoftwareFeatureTool

### Community 118 - "._execute()"
Cohesion: 0.19
Nodes (11): _BoomTool, Path, 3.6 #3 — 故障场景集成测试。 直接针对真实代码路径验证文档要求的六种故障模式都能被优雅处理，而不是崩溃： 1. 模型超时 ->…, 模拟模型 API 返回 429（限流），验证提供商的退避重试后优雅失败。 直接驱动真实的…, test_api_rate_limit_retries_then_fails(), test_confirmation_reject_and_restore(), test_disk_write_failure_is_caught(), test_model_timeout_raises_instead_of_hanging() (+3 more)

### Community 119 - "captureCurrentPage()"
Cohesion: 0.33
Nodes (12): captureCurrentPage(), ensureHttpConfig(), ensureNativePort(), extractPageData(), getActiveTab(), loadConfig(), postToDesktopLocalhost(), postToServer() (+4 more)

### Community 120 - "downloadFile()"
Cohesion: 0.31
Nodes (12): downloadFile(), ensurePythonRuntime(), extractTarball(), getCachedPythonRuntime(), getMarkerPath(), getPythonExecutable(), getReleaseUrl(), getRuntimeBaseDir() (+4 more)

### Community 121 - "crypto"
Cohesion: 0.21
Nodes (12): crypto, EXCLUDED_EXTS, findReleaseFiles(), fs, main(), MANIFEST_PATH, path, PRIVATE_KEY_PATH (+4 more)

### Community 122 - ".__init__()"
Cohesion: 0.22
Nodes (9): get_logger(), Structured logging system for Kyrozen Core. Records: user requests, agent…, Return the singleton logger, creating it if needed., # IMPORTANT: logs go to stderr, never stdout. The desktop Python Agent, Regression tests for KyrozenLogger stdlib-method parity. The 2026-07-30 Round-4…, test_delegated_stdlib_attributes(), test_get_logger_returns_drop_in(), test_standard_methods_exist_and_do_not_raise() (+1 more)

### Community 123 - ".onBegin()"
Cohesion: 0.21
Nodes (6): buildReleaseRun(), PROJECT_ROOT, readAppVersion(), ReleaseReporter, ReleaseRunMeta, ReleaseRunResult

### Community 124 - "._onData()"
Cohesion: 0.27
Nodes (7): forwardToDesktop(), getPortFilePath(), NativeMessage, NativeMessagingReader, resolveServerConfig(), runHost(), writeMessage()

### Community 125 - "CompleteStep()"
Cohesion: 0.21
Nodes (9): dict, OnboardingPage(), OnboardingState, OnboardingStep, Project, ProjectStep(), Props, PythonStep() (+1 more)

### Community 126 - "_chunk()"
Cohesion: 0.27
Nodes (10): _chunk(), create_png_rgba(), main(), _mix(), _point_line_distance(), Return perpendicular distance from point to line segment., Return a PNG chunk with length, type, data and CRC., Create a minimal PNG from a flat list of RGBA tuples (top-to-bottom, left-to-… (+2 more)

### Community 127 - "ensureProjectVenv()"
Cohesion: 0.44
Nodes (10): ensureProjectVenv(), getMarkerPath(), getProjectVenv(), getProjectVenvRoot(), getPythonVersion(), getVenvPython(), installProjectDependencies(), runCommand() (+2 more)

### Community 128 - "build"
Cohesion: 0.18
Nodes (11): scripts, build, build:renderer, dev, fix-electron, lint, postinstall, preview (+3 more)

### Community 129 - "buildDesktop()"
Cohesion: 0.29
Nodes (10): buildDesktop(), DESKTOP_ROOT, getMainLogPath(), REPO_ROOT, runTest(), SCRIPT_DIR, sleep(), startBackend() (+2 more)

### Community 130 - "1. 在 Cloudflare 添加站点"
Cohesion: 0.18
Nodes (10): 后续维护, 1. 在 Cloudflare 添加站点, 2. 修改域名 DNS 服务器, 3. 创建 Tunnel, 4. 配置 Public Hostname, 5. 在服务器上启动 cloudflared, 6. 验证, 7. 可选：开启 Cloudflare 代理缓存 (+2 more)

### Community 131 - "._summarize_hardware_dir()"
Cohesion: 0.20
Nodes (6): Project, Build context for Product Planning mode., Return a short summary of the existing software project directory., Build context for Software Development mode., Return a short summary of the existing hardware project directory., Build context for Learning & Proactive Improvement mode.

### Community 132 - ".from_dict()"
Cohesion: 0.35
Nodes (4): Any, A single research direction derived from the Problem Brief., ResearchPlan, test_research_plan_serialization()

### Community 133 - "category"
Cohesion: 0.20
Nodes (10): mac, category, entitlements, entitlementsInherit, executableName, gatekeeperAssess, hardenedRuntime, icon (+2 more)

### Community 134 - "allowSyntheticDefaultImports"
Cohesion: 0.20
Nodes (9): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, strict, include (+1 more)

### Community 135 - "Copy .env.example to .env,"
Cohesion: 0.20
Nodes (9): Copy .env.example to .env, fill in your secrets, then run:, docker compose up -d --build, For local SQLite-only development you only need to set:, For production with Supabase Auth + PostgreSQL set:, Kyrozen Beta — Docker Compose, KYROZENDBBACKEND=sqlite, KYROZENDBBACKEND=supabase, KYROZENDBPATH=./workspace/kyrozen.db (+1 more)

### Community 136 - "2. Set KYROZENDBBACKEND=postgres and"
Cohesion: 0.20
Nodes (9): 1. Copy .env.example to .env and fill in your Supabase + AI keys., 2. Set KYROZENDBBACKEND=postgres and KYROZENPOSTGRESDSN., 3. Add TUNNELTOKEN from Cloudflare Zero Trust (see docs/CLOUDFLARETUNNEL.md)., 4. docker compose -f docker-compose.selfhosted.yml up -d --build --remove-orphans, or local TLS certificates are required on the host., Public access is provided via Cloudflare Tunnel, so no inbound 80/443 ports, Quick start:, Self-hosted Kyrozen backend deployment. (+1 more)

### Community 137 - "Automated Verification"
Cohesion: 0.20
Nodes (9): Automated Verification, Blocking Defects Found, Conclusion, Kyrozen Phase 1 Real Acceptance Rerun - 2026-07-29, Phase 1 Matrix, Required Retest Before Release, Side Effects, Test Scope (+1 more)

### Community 138 - ".detect()"
Cohesion: 0.27
Nodes (3): LocalCapabilities, What the local machine can actually do., TestToolRestriction

### Community 139 - ".check_quota()"
Cohesion: 0.22
Nodes (6): Desktop client support for Kyrozen. This module manages connections to local…, In-memory manager for connected desktop clients., Data models for desktop client management., QuotaStatus, Result of a quota check., Return whether the user can consume the estimated tokens.

### Community 140 - ".find_missing_dimensions()"
Cohesion: 0.27
Nodes (6): NextQuestion, Any, Pick the highest-priority missing dimension and return a question., Return a summary of filled/missing dimensions for UI display., A single recommended next question for the user., Return dimensions that are still empty, ordered by priority.

### Community 141 - "auth_client()"
Cohesion: 0.29
Nodes (9): auth_client(), learning_repository(), project_manager(), fixture, TestClient, Shared fixtures for Kyrozen tests., Authenticated TestClient using the shared test user., temp_dir() (+1 more)

### Community 142 - "$schema"
Cohesion: 0.22
Nodes (8): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema, oxc, typescript, warn

### Community 143 - ".__init__()"
Cohesion: 0.25
Nodes (4): Any, Connection, Add an email to the waitlist. Returns a dict with ``success`` and either ``id``…, Return all waitlist entries, newest first.

### Community 144 - "fixture"
Cohesion: 0.33
Nodes (8): learning_client(), fixture, TestClient, Tests for Learning REST API endpoints., test_failure_and_success_knowledge_crud(), test_learning_isolation_between_projects(), test_learning_record_crud(), test_suggestion_crud_and_status_update()

### Community 145 - "AGENTS.md"
Cohesion: 0.25
Nodes (7): Build, Test, and Development Commands, Coding Style & Naming Conventions, Commit & Pull Request Guidelines, Project Structure & Module Organization, Repository Guidelines, Testing Guidelines, Multi-client Application

### Community 146 - "author"
Cohesion: 0.25
Nodes (7): author, description, homepage, main, name, type, version

### Community 147 - "crypto"
Cohesion: 0.25
Nodes (6): crypto, fs, path, PRIVATE_KEY_PATH, PUBLIC_KEY_TS_PATH, REPO_ROOT

### Community 148 - ".__init__()"
Cohesion: 0.25
Nodes (3): Persists the GitHub token to a path *outside* the workspace. Never call this…, TokenStore, test_token_store_saves_loads_clears_outside_workspace()

### Community 149 - ".__post_init__()"
Cohesion: 0.29
Nodes (3): HardwareDebugRecord, Evidence-driven hardware debugging record., test_debug_record_validation()

### Community 150 - ".execute()"
Cohesion: 0.29
Nodes (4): Any, Concrete implementation. Must return a ToolResult., Validate parameters against the schema for the given action., Validate and execute the tool action, measuring execution time.

### Community 151 - "_make_image()"
Cohesion: 0.46
Nodes (8): skipif, _make_image(), _make_video(), Path, test_image_attachment_thumbnail_and_analysis(), test_interaction_tool_attach_via_jsonrpc(), test_requirements_context_injects_image_and_video(), test_video_attachment_timestamped_summary()

### Community 153 - "_FakeModel"
Cohesion: 0.36
Nodes (7): base_kwargs(), _FakeModel, fixture, Tests for the unified AgentRouter (Kyrozen Missing Features 3.1). Covers: -…, Lightweight stand-in so agents can be constructed without a real provider., registry(), router()

### Community 154 - "buildTree()"
Cohesion: 0.43
Nodes (6): buildTree(), FileTree(), Props, sortNodes(), TreeItem(), TreeNode

### Community 155 - ".__post_init__()"
Cohesion: 0.33
Nodes (3): AssemblyStep, One physical assembly step for the user., test_assembly_step_validation()

### Community 156 - ".__post_init__()"
Cohesion: 0.29
Nodes (4): HardwareArchitecture, High-level hardware architecture for the prototype., test_hardware_architecture_empty_is_valid(), test_hardware_architecture_validation()

### Community 157 - ".__post_init__()"
Cohesion: 0.29
Nodes (4): MarketResearchReport, Final artifact produced by the Market Research Agent., Replace the current report draft., test_invalid_recommendation()

### Community 158 - "Kyrozen Missing Features Three"
Cohesion: 0.40
Nodes (6): Real User Acceptance, Kyrozen Missing Features Three Phase Plan, Phase 1 Real Acceptance Rerun, Phase 1 Real Reacceptance Report, Python Dependency Requirements, Pinned Python Dependencies

### Community 159 - "_read_until_id()"
Cohesion: 0.40
Nodes (5): parametrize, Packaged Python Agent startup smoke test (P0-01). This test launches the…, Read stdout lines until we find a response carrying ``req_id``. Ignores the…, _read_until_id(), test_packaged_agent_starts_and_responds()

### Community 160 - "collectErrors()"
Cohesion: 0.70
Nodes (4): collectErrors(), getServerUrl(), sendFinalReport(), sendTestReport()

### Community 162 - "apply_migrations.py"
Cohesion: 0.50
Nodes (4): main(), migration_files(), Path, Return the baseline first, then numbered migrations in stable order.

### Community 165 - "allowToChangeInstallationDirectory"
Cohesion: 0.50
Nodes (4): nsis, allowToChangeInstallationDirectory, include, oneClick

### Community 166 - "Kyrozen Favicon"
Cohesion: 0.50
Nodes (4): Kyrozen Favicon, Lightning Bolt Shape, Masked Layered Composition, Purple Gradient Glow

### Community 167 - "Expanding the Oxlint configuration"
Cohesion: 0.50
Nodes (3): Expanding the Oxlint configuration, React Compiler, React + TypeScript + Vite

### Community 168 - ".verify_refresh_token()"
Cohesion: 0.50
Nodes (3): Return user_id if the refresh token is valid., Backward-compatible helper to verify a refresh token., verify_desktop_token()

## Knowledge Gaps
- **527 isolated node(s):** `manifest_version`, `name`, `version`, `description`, `activeTab` (+522 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ToolResult` connect `.__init__()` to `.__init__()`, `.__init__()`, `.__init__()`, `.__init__()`, `.__init__()`, `.__init__()`, `.__init__()`, `._cancel_task_timeout_timer()`, `.__init__()`, `._execute()`, `.execute()`, `.__init__()`, `._persist()`, `.__init__()`, `._execute()`, `.__init__()`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Why does `get_default_registry()` connect `.__init__()` to `.__init__()`, `.__init__()`, `_FakeModel`, `.__init__()`, `.__init__()`, `.__init__()`, `.__init__()`, `.chat()`, `# TODO: wire into`, `.__init__()`, `.__init__()`, `.__init__()`, `._cancel_task_timeout_timer()`, `.__init__()`, `.__init__()`, `.__init__()`, `.__init__()`, `.__init__()`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Why does `BaseAgent` connect `# TODO: wire into` to `.__init__()`, `.__init__()`, `.chat()`, `.__init__()`, `._persist()`, `.test_all_nine_modes_build_correct_agent()`, `.__init__()`, `.detect()`, `.__getattr__()`, `.__init__()`, `._cancel_task_timeout_timer()`, `.__init__()`, `._enforce_question_protocol()`, `.__init__()`, `.__init__()`, `.cancel()`, `_FakeModel`, `._action_required()`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 35 inferred relationships involving `ToolResult` (e.g. with `RecordDevelopmentDecisionTool` and `SaveChangelogTool`) actually correct?**
  _`ToolResult` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `ToolSchema` (e.g. with `RecordDevelopmentDecisionTool` and `SaveChangelogTool`) actually correct?**
  _`ToolSchema` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `KyrozenDatabase` (e.g. with `LearningRepository` and `Task`) actually correct?**
  _`KyrozenDatabase` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `ToolParameter` (e.g. with `RecordDevelopmentDecisionTool` and `SaveChangelogTool`) actually correct?**
  _`ToolParameter` has 34 INFERRED edges - model-reasoned connections that need verification._