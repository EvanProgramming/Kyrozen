# Kyrozen Phase 1 真实用户验收与修复记录（2026-07-30 Round 7）

## 1. 本轮目标与规则

- 验收基线：`docs/KYROZEN_MISSING_FEATURES_THREE_PHASE_PLAN.md` 第一阶段。
- 视觉基线：`docs/DESIGN_SYSTEM.md`。
- 测试方式：从 DMG 覆盖安装开始，使用真实桌面客户端，按普通非技术用户习惯用简短自然语言完成登录、建项目、问题探索、市场研究、产品定义、方案设计、开发、测试、预览、Git 提交、GitHub 推送和重启恢复。
- 不通过内部文件名、阶段名或 Kyrozen 实现细节引导 Agent；不把单元测试、构建成功或静态代码存在当作真实流程通过。
- 每个发现立即记录；修复后重新从真实界面验证。未完成项保持 `OPEN`，真实复测通过后才改为 `VERIFIED`。

## 2. 当前测试环境

- 仓库 HEAD：`e50ffa6bd8aa429ee8bd75bdaf0d79696d3f5791`。
- 测试安装包：`desktop/release/Kyrozen-0.1.0-arm64.dmg`。
- DMG SHA256：`2fc50f6508186647e4b1e04850b21a97dafd512e5c02bb21c48f582e7b997c1e`。
- 安装前 `/Applications/Kyrozen.app`：2026-07-30 12:06:55 +0800，版本 `0.1.0`（旧安装）。
- DMG 生成时间：2026-07-30 23:00:35 +0800。
- 系统：macOS（Apple Silicon），时区 Asia/Shanghai。

## 3. 实时流程记录

### R7-STEP-01 覆盖安装

- 状态：`DONE`
- 目标：从当前 DMG 覆盖旧安装，启动打包后的正式客户端，而非 Vite 开发页。
- 真实操作：在 Finder 打开已挂载的 `Kyrozen 0.1.0-arm64`，复制 `Kyrozen.app` 到 Applications，并在覆盖提示中选择 Replace。
- 首次覆盖失败：Finder 提示旧应用仍在使用；使用应用级 `Cmd+Q` 完全退出旧客户端后继续安装。
- 安装前检查发现旧应用包签名已经被首次运行产生的 Python `__pycache__/*.pyc` 修改，`codesign --verify --deep --strict /Applications/Kyrozen.app` 返回 `a sealed resource is missing or invalid`。
- 完全退出后覆盖成功；新安装包首次启动前无 `.pyc`，严格签名验证通过。应用包内容时间为 `2026-07-30 21:54:27 +0800`，但 DMG 生成时间为 `23:00:35`，两者仍难以对应同一修复轮次。

### R7-STEP-02 启动与登录恢复

- 状态：`IN PROGRESS`
- 启动后先显示“使用 GitHub 登录”的登录页；约数秒后未操作即恢复为已登录的 `Evan / @EvanProgramming` 主界面。
- 恢复后右侧 GitHub 面板同时显示“GitHub 账号 未连接 / 授权 GitHub”，与顶部 GitHub 身份造成明显冲突。
- 左侧实际显示 10 个项目，但“我的项目”可访问性值仍为 `2`。
- 当前新包只启动一次后已在 `.app/Contents/Resources/kyrozen` 生成 90 个 `.pyc`；严格签名验证随即从启动前通过变为失败，稳定复现 R7-P0-01。
- 点击“授权 GitHub”后，浏览器完成服务端回调并请求打开 Kyrozen；直接返回客户端时右栏仍保持“GitHub 账号 未连接”，直到随后新建并选中项目才突然刷新为已连接，说明授权成功但当前视图未同步。
- 回调页面把 Supabase 会话、refresh token 与 GitHub token 放入 `kyrozen://` 深链的查询参数；实际浏览器页面、历史 URL 与可访问性树均可读取完整凭据。报告仅记录风险，不保存任何 token 值。

### R7-STEP-03 新建项目、问题探索与市场调研

- 状态：`BLOCKED`
- 新建项目：`家庭植物浇水提醒`（`proj_73b8fdc7`），普通用户只输入“帮我记住家里植物什么时候该浇水”等简短描述，没有指定内部阶段或文档名。
- 用户依次选择“经常忘记浇水”“植物放在角落看不见”“我自己”“看到土干/叶子蔫才浇”，但在澄清尚未结束时问题交付物和用户确认已被自动通过。
- 用户明确两次表示仍想做一个自用简单网页，市场 Agent 第一次调研约四分钟后返回结果；多项持久化工具失败。第二次调研才写出 `docs/MARKET.md`，但市场确认仍由系统自动完成，决策和交接没有保存。
- 在 Agent 问“开源还是从零写”时，用户回答“我想自己从零做一个，继续吧。”；系统没有进入产品定义，而是第三次执行植物浇水市场搜索，状态仍为 `market_research`。这使真实普通用户无法继续完成 PRD、方案、开发、预览与 Git 流程，本轮在此判定为产品流程阻断并转入代码修复。

## 4. 实时问题清单

| ID | 严重度 | 状态 | 环节 | 问题 | 复现/证据 | 修复与复测 |
| --- | --- | --- | --- | --- | --- | --- |
| R7-P0-01 | P0 | OPEN | 安装 / 运行后完整性 | 打包版 Python Agent 在 `.app` 包体内生成 `__pycache__/*.pyc`，导致应用运行后签名失效 | 当前 DMG 覆盖安装后，首次启动前签名通过且 `.pyc=0`；只启动一次后 `.pyc=90`，`codesign --verify --deep --strict` 退出 1：`a sealed resource is missing or invalid` | 待修复：打包运行时禁止向应用包写 bytecode，并从全新覆盖安装开始验证首次启动前后签名均保持有效 |
| R7-P1-02 | P1 | OPEN | 登录 / 恢复 | 有可恢复会话时仍先闪现完整登录页，随后无操作切换主界面 | 当前 DMG 首次启动的真实界面先出现“使用 GitHub 登录”，数秒后自动变为 `Evan / @EvanProgramming` | 待修复：会话判定完成前显示中性恢复状态，确认失效后才显示登录页 |
| R7-P1-03 | P1 | OPEN | 账号 / GitHub | 顶部已显示 GitHub 身份，但右侧面板显示“GitHub 账号 未连接”，用户无法判断是否登录失败 | 同一主界面同时出现 `Evan / @EvanProgramming` 与“GitHub 账号 未连接 / 授权 GitHub” | 待修复：明确区分 Kyrozen 登录身份、GitHub 仓库授权和当前项目远程状态 |
| R7-P2-04 | P2 | OPEN | 项目列表 / 无障碍 | “我的项目”可访问性值固定为 2，与实际 10 个项目不一致 | Computer Use 可访问性树：`heading 我的项目, Value: 2`，下方存在 10 个项目按钮 | 待修复并用动态项目数复测 |
| R7-P2-05 | P2 | OPEN | 发布追踪 | App 版本始终为 `0.1.0`，包体时间与 DMG 生成时间不一致，无法从客户端或 Finder 识别修复轮次 | DMG `23:00:35`；安装后 `.app` 内容时间 `21:54:27`；`CFBundleVersion` / `CFBundleShortVersionString` 均为 `0.1.0` | 待增加可追踪 build number / commit 标识并复测 |
| R7-P0-06 | P0 | OPEN | 预览进程安全 | `BuildRunner.start_preview()` 会扫描 8000–8020 并向占用 PID 发送 SIGKILL，未验证进程是否属于当前项目 | 代码审计发现端口抢占逻辑按 `lsof` PID 直接杀进程；可能终止用户无关服务 | 待改为只管理当前项目登记的 preview PID/process group，并补“不杀无关服务”测试 |
| R7-P1-07 | P1 | OPEN | 测试隔离 / 进程清理 | `test_tool_repair_real` 启动预览后未清理，pytest 结束仍遗留 `app.py` 占用 8000；E2E 也会向真实 `~/KyrozenProjects` 留目录 | 当前 PID 4667 来自 `pytest-56/test_tool_repair_real0` 且 `/api/health` 为 404；本机已有 38 个测试/历史项目目录 | 待修复 fixture/生命周期与 E2E workspace isolation 后复测 |
| R7-P0-08 | P0 | OPEN | 发布门槛真实性 | 最新 4/4 E2E 仍不能证明第一阶段真实旅程 | `desktop/e2e/release-runs/latest.json` 的 account/projectId 为 unknown；核心旅程未真实执行 OAuth、PRD、预览、commit、建库和 push | 待补真实发布旅程、录像截图与完整 release metadata |
| R7-P1-09 | P1 | OPEN | GitHub OAuth | 浏览器授权与深链回调成功后，当前视图不刷新，用户仍看到“未连接”；只有创建并选中项目后才显示已连接 | Computer Use 点击“授权 GitHub”→浏览器回调→“Open Kyrozen”后仍显示未连接；新项目创建完成后变为 `EvanProgramming / scope / 已连接` | 待修复授权完成事件后的即时状态刷新，并用断开、重授权完整复测 |
| R7-P0-10 | P0 Security | OPEN | OAuth 凭据传输 | 登录回调把多种长期/仓库凭据直接放在可见深链 URL 查询参数中 | 浏览器回调页的“打开 Kyrozen”链接和浏览器 URL/可访问性树可直接读取完整 access、refresh、GitHub token；报告未保存具体值 | 待改为一次性短码交换或其他不把凭据暴露在 URL/历史中的机制，并做日志/历史/诊断密钥扫描 |
| R7-P2-11 | P2 | OPEN | 弹层交互 | 用户菜单打开时点击“新建”，菜单没有关闭，仍在新建项目模态后方显示，界面层级混乱 | 真实创建“家庭植物浇水提醒”时，遮罩后仍能看到头像菜单、退出登录和授权按钮 | 待统一 popover/modal 互斥与焦点管理并复测 |
| R7-P0-12 | P0 | OPEN | 阶段门禁 / 用户确认 | Agent 尚在继续提问时，问题交付物和“用户确认问题界定”已经自动标为满足；用户从未确认 Problem Brief | 只回答“容易忘记浇水”和“植物放在角落”后，右栏进度 14%、已满足 2/2；`stagegate.json` 写入 `problem_confirmed.confirmed=true`、detail=`报告已生成，已自动确认`，同时聊天仍在询问目标用户 | 待将 Artifact 生成与用户确认彻底分离；只有明确确认动作才满足门禁，并验证拒绝/修改路径 |
| R7-P1-13 | P1 | OPEN | 问题交付物质量 | `docs/PROBLEM.md` 在澄清未结束时过早落盘，标题为“未命名问题”，内容只有前两项答案且置信度 low | 新项目真实文件首行 `# 问题定义：未命名问题`，尚未记录目标用户却已通过 Artifact 门禁 | 待在信息完整后生成/更新可读 Problem Brief，并让质量不完整的文档不能通过门禁 |
| R7-P2-14 | P2 | OPEN | 结构化问题 UI | 同一个问题正文连续显示两遍，造成视觉冗余 | 第四个问题“你现在通常是怎么处理浇水这个问题的？有没有用什么方法或工具？”在同一张问题卡中出现两次 | 待去重标题/正文并复测所有问题卡 |
| R7-P0-15 | P0 | OPEN | Agent 交接持久化 | 问题探索完成后没有保存任何结构化目标、决策、风险或待办，无法为后续 Agent 提供可靠交接 | Agent 明确总结用户/场景/问题并建议使用现有方案，但 `.kyrozen/handoff.json` 的 `handoffs`、`confirmed_goals`、`decisions`、`risks`、`open_tasks` 仍全为空 | 待在阶段结果与用户决定时写入结构化交接，并验证重启与切换后不重复询问 |
| R7-P1-16 | P1 | OPEN | 阶段状态文案 | 问题探索总结已完成且门禁 2/2，但右栏仍显示“下一步：和 AI 一起澄清问题 / 项目刚创建” | 最终问题总结出现后进度仍为 14%，下一步文案未变化，也没有明确的进入下一阶段主操作 | 待让聊天结果、门禁、下一步与可执行按钮由同一状态源同步刷新 |
| R7-P0-17 | P0 | OPEN | 操作记录 / 失败恢复 | Agent 明确提示“后续几个记录操作因系统临时问题未写入”，却同时声称“不影响核心内容”，没有列出失败对象、原因或重试入口；实际 handoff 仍为空 | 用户要求继续后，回复只给模糊失败说明；展开操作记录仅见成对重复的 `Using save_problem_brief: save`、`assess_confidence`、`record_problem_decision`、`update_project`，无成功/失败、开始/结束、耗时、输入输出摘要或错误原因 | 待接通完整操作结果，提供针对失败步骤的修复/重试，并禁止在关键持久化失败时宣称不影响 |
| R7-P2-18 | P2 | OPEN | 操作记录 UI | 可折叠记录直接暴露英文内部工具名且每条重复两次，普通用户无法理解 | 展开“查看操作记录（8）”后显示 8 条 `Using <tool>: <action>`，四种工具各重复两次 | 待以用户语言聚合动作，技术名仅进诊断详情，去重并显示结果 |
| R7-P1-19 | P1 | OPEN | 运行状态 | 市场调研状态直接显示英文内部搜索语句，不是设计要求的用户可理解中文状态 | 阶段切到 market_research 后主聊天显示 `Researching: houseplant watering tracker app problems complaints` | 待统一为本地化的 Searching 状态，具体查询仅进入诊断记录 |
| R7-P0-20 | P0 | OPEN | 市场调研 / 任务终态 | 市场调研后台已完成搜索和报告生成，但关键持久化操作反复失败；前台约四分钟停在 `Researching...` 且中途没有停止按钮，失败时没有错误/重试提示 | 第一轮 4 次 `save_research_source`、`save_market_research_report`、`record_opportunity_decision` 全部失败；第二轮只有 report 最终写成 `docs/MARKET.md`，source 与 opportunity decision 仍失败，用户也无法得知部分成功状态 | 待修复 project_manager/持久化依赖、任务终态与 activity 清理；失败必须显示摘要和针对性重试，成功才写门禁 |
| R7-P0-21 | P0 | OPEN | 主聊天日志隔离 | 新一轮用户回复执行过程中，原始工具状态直接进入主聊天而非折叠操作记录 | 用户说“我还是想做给自己用”后，主聊天在用户消息下直接显示 `Using save_research_source: save` | 待保证工具事件只进入结构化操作记录/诊断，主聊天仅显示用户可理解状态和最终答复 |
| R7-P0-22 | P0 | OPEN | 市场门禁 / 用户确认 | 市场报告生成即把“用户确认调研结论”自动标为满足，用户没有确认报告 | `stagegate.json` 中 `market_confirmed.confirmed=true`、detail=`报告已生成，已自动确认`；右栏同时显示市场 2/2 已满足 | 与问题门禁一样彻底拆分 Artifact 与明确用户确认，补确认、拒绝、要求修改三条真实路径 |
| R7-P0-23 | P0 | OPEN | Agent 路由 / 阶段推进 | 用户已明确选择“自己从零写、继续”，系统仍把消息交给市场调研 Agent 并重复搜索，无法进入产品定义 | 提交内联回答后 `status.json` 再次为 `searching`，operation log 新增第三轮植物浇水市场查询；顶部仍显示 `market_research / 市场调研 Agent` | 修复路由、阶段决策持久化和显式推进；普通用户表达继续开发时应进入下一未满足阶段，不得重复已完成调研 |
| R7-P1-24 | P1 | OPEN | 进度 / 下一步状态 | 市场交付物与确认已显示 2/2、进度 29%，但右栏仍写“下一步：进行市场调研 / 问题明确后需要了解市场” | 同一实时界面同时出现“市场与竞品调研 已满足”“用户确认 已满足”和要求再次调研的下一步 | 用统一 StageGate 快照派生 Agent、进度、下一步和主操作，禁止互相矛盾 |
| R7-P0-25 | P0 | OPEN | 交接 / 决策持久化 | 两轮市场总结、用户坚持自建和明确“从零写”后，交接仍没有目标、决策、风险与待办 | `.kyrozen/handoff.json` 仅有一次空字段的 problem→market handoff；顶层数组仍全为空，`record_opportunity_decision` 失败 | 修复 ProjectManager 注入与交接写入；切换 Agent、重启后必须恢复已经确认的决策且不重复询问 |
| R7-P1-26 | P1 | OPEN | 交付物语言与可读性 | 中文项目生成的 `docs/MARKET.md` 使用英文标题和面向内部的 JSON 代码块，普通用户难以阅读维护 | 文档以 `# Market Research Report`、`## Problem Summary` 开头，竞品与来源主体为大段 JSON fenced block | 按客户端语言生成用户可读 Markdown 表格/列表，同时保留机器结构化数据到独立内部文件 |
| R7-P0-27 | P0 | OPEN | 任务完成 / 用户反馈 | 用户回答“自己从零做、继续”后，后台搜索与一次保存操作结束，但主聊天没有任何最终回复、错误或下一步；输入框恢复可用，用户只能猜测任务已结束 | `status.json` 已清空，operation log 最后一项为失败的 `save_research_source`；界面最后一行仍是 `Using save_research_source: save`，没有 Assistant 结果 | 所有任务必须以成功、可重试失败或用户停止三种明确终态结束；禁止静默丢失答复 |

## 5. 第一阶段验收矩阵

| 能力 | 首轮 | 修复后 | 证据 |
| --- | --- | --- | --- |
| DMG 安装与首次启动 | 失败 | 待测 | R7-P0-01、R7-P2-05 |
| 登录与会话恢复 | 失败 | 待测 | R7-P1-02、R7-P1-03、R7-P1-09、R7-P0-10 |
| 建立软件项目 | 部分通过 | 待测 | 项目创建成功；R7-P2-11 |
| 专用 Agent 路由与交接 | 失败 | 待测 | R7-P0-15、R7-P0-23、R7-P0-25 |
| 阶段门禁与真实进度 | 失败 | 待测 | R7-P0-12、R7-P0-22、R7-P1-24 |
| 真实软件生成、运行与修复 | 待测 | 待测 | — |
| 附件、状态、操作记录与确认 | 待测 | 待测 | — |
| 本地 Git 与 GitHub | 待测 | 待测 | — |
| 重启恢复 | 待测 | 待测 | — |
| UI 与设计系统 | 待测 | 待测 | — |

## 6. 自动化与产物证据

尚未执行。本轮以真实桌面流程为首要证据，修复后再执行后端、桌面单元测试、lint、renderer build、E2E 与安装包验证。

## 7. 修复回归记录（Round 8 前置）

- `tests/test_python_agent_startup.py` 首次全量回归发现：新工作区执行阶段刷新时，客户端传入的当前阶段被本地默认值 `problem_discovery` 覆盖，导致开发阶段刷新错误回退到问题探索。已修复为仅在没有持久化门禁文件时初始化传入阶段；已有门禁仍以本地持久化状态为准。
- 本次修复后聚焦 Python Agent 测试 `2 passed`，全量 Python 测试 `522 passed`；桌面 renderer build、lint、unit tests `15 passed`。尚未替代真实 DMG→登录→项目→交付验收，最终状态待下一轮 Computer Use。
