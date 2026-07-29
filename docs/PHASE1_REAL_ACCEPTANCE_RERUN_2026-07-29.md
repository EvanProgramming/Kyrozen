# Kyrozen Phase 1 Real Acceptance Rerun - 2026-07-29

## Conclusion

**Fail. Phase 1 is still not ready for public beta.** I tested the installed desktop app as a normal user, created a new meaningful software project, chatted through problem discovery, initialized Git, created a private GitHub repository, opened the project canvas, restarted the app, and ran the automated suites. The app has improved in login, markdown rendering, inline question UI, and GitHub push, but the user journey is still blocked before market research, PRD, development, testing, and preview.

## Test Scope

| Item | Result |
|---|---|
| App | `/Applications/Kyrozen.app`, Kyrozen 0.1.0 |
| Account | `EvanProgramming`, GitHub avatar and scope shown |
| New project | `小区二手物品交换板`, `proj_0a5d2b6a` |
| Workspace | `/Users/evangong/KyrozenProjects/proj_0a5d2b6a` |
| GitHub repo | `EvanProgramming/kyrozen-phase1-acceptance-swap-board-20260729`, private |
| Production health | `https://kyrozen.chat/api/health` returned 200, provider `multi`, model `auto`, permission `strict` |
| Python tests | `444 passed, 1 warning in 50.85s` |
| Desktop checks | `npm run lint`, `npm run build:renderer`, `npm run test:e2e` passed |

## Phase 1 Matrix

| Area | Result | Evidence |
|---|---|---|
| 3.1 Agent routing and handoff | Fail | Problem discovery produced focused questions, but message completion repeatedly stayed stuck in `正在理解你的需求` until Stop or later refresh. Stage stayed `problem_discovery`; no reliable transition to market/product/design/dev agents was testable. |
| 3.2 Stage gates and progress | Fail | Gate stayed `1/7 7%` after multiple discovery answers and AI messages saying it saved the Problem Brief. No `docs/PROBLEM.md` existed, and `stagegate.json` still had `problem_statement.detected=false`. |
| 3.3 Software generation/run/repair | Blocked | Development remained locked because Phase 1 discovery never produced required artifacts. The visible generation form is present but correctly disabled. No real app generation, preview, repair, or README cold-start could be tested on this new project. |
| 3.4 Attachments/status/operation/confirmation | Partial | Chat markdown table rendered; inline question choices appeared. However selected choices were inserted as raw internal values (`wechat_group`, `monthly_several`), operation log stayed `0`, and status did not finish automatically. |
| 3.5 Git/GitHub | Partial | GitHub login worked after clicking Dia's `Open Kyrozen`. Git init worked, private repo creation worked, `origin/main` pushed successfully, and remote URL had no token. But first commit contained only `.gitignore`, not real project content. |
| 3.6 P0 release gate | Fail | Automated E2E passed 4 tests, but still used mock `release-journey`, unknown users, and did not cover real OAuth, real product generation, preview, repair, fault injection, or three consecutive complete journeys. |

## Blocking Defects Found

| ID | Severity | Issue | Evidence |
|---|---|---|---|
| P0-R1 | Blocker | Chat task completion does not reliably return to idle | Three discovery turns stayed at `正在理解你的需求` for 20-45 seconds. Clicking Stop or later refreshing caused delayed content to appear. |
| P0-R2 | Blocker | Problem Brief is not persisted into stage artifacts | UI says it created/saved a Problem Brief, but workspace has no `docs/PROBLEM.md`; `stagegate.json` still says `problem_statement.detected=false`. |
| P0-R3 | Blocker | Cannot complete Phase 1 flow from a fresh real project | Because problem discovery never satisfies the gate, market research, PRD, solution design, software generation, run, repair, preview, and second commit cannot be reached normally. |
| P0-R4 | Blocker | Restart restore becomes inconsistent and does not settle | After restart: first login page, then partial session; after 14 seconds project list still said `暂无项目`, entitlement showed free account, and UI showed `fetch failed` / `net::ERR_CONNECTION_CLOSED` while selected project Git state was present. |
| P0-R5 | High | Inline question answers leak internal option values | Clicking user-readable choices displayed `wechat_group` and `monthly_several` in chat instead of the labels. |
| P0-R6 | High | Project canvas exposes internal JSON and stale gate state | Canvas showed raw question JSON/options, `stagegate.json` records, and task blobs. It claimed `4 份`資料 and `4 个` tasks while local workspace only had `.gitignore` plus `.kyrozen` files. |
| P0-R7 | High | Git first commit/push is misleading | UI says first commit was pushed and connected, but `git ls-tree HEAD` contains only `.gitignore`; no project brief, README, source, or real project artifact was committed. |
| P0-R8 | High | Operation records are not captured | After chat, Git init, and GitHub repo creation, operation record count still showed `0`. |
| P0-R9 | Medium | New project UI emphasizes disabled software generation too early | The generation form is expanded during problem discovery, before the user has any reason to fill technical features. It is disabled, but visually dominates the workflow. |
| P0-R10 | Medium | Accessibility/project count is wrong | `我的项目` heading value still reports `2` while the UI/account has four projects after creation. |
| P0-R11 | Medium | User-visible setup noise remains in diagnostics/logs | Main log still contains repeated `PlatformIO not found, installing into bundled Python...`; it is not in chat, but it indicates startup still performs noisy/repeated setup work. |

## What Worked

- GitHub account login completed through Dia after clicking `Open Kyrozen`.
- User avatar, login name, and scopes were visible in the app.
- Developer unlimited entitlement appeared immediately after initial login.
- New project creation succeeded and selected the new project.
- Agent asked focused, non-technical discovery questions and rendered markdown tables.
- GitHub repo creation used an inline confirmation card showing owner, repo name, and private visibility.
- Local Git initialized `main`, remote was set, and private GitHub push succeeded.
- `gh repo view` confirmed private repo, default branch `main`, and pushed timestamp.

## Automated Verification

| Command | Result | Important Caveat |
|---|---|---|
| `.venv/bin/python -m pytest` | Passed, 444 tests | Does not catch the real UI stuck-state or artifact persistence failures. |
| `cd desktop && npm run lint` | Passed | Static check only. |
| `cd desktop && npm run build:renderer` | Passed | Build success only. |
| `cd desktop && npm run test:e2e` | Passed, 4 tests | Uses mock `release-journey`; no real complete product journey. |

## Side Effects

- Created local workspace `/Users/evangong/KyrozenProjects/proj_0a5d2b6a`.
- Created private GitHub repository `EvanProgramming/kyrozen-phase1-acceptance-swap-board-20260729`.
- Current app state after restart is inconsistent: logged-in GitHub state is visible, but project list shows no projects and cloud fetch failed.
- No client code was modified during this rerun.

## Required Retest Before Release

A fixed build must pass a fresh project flow without using Stop as a workaround: login, create project, answer discovery questions, persist `docs/PROBLEM.md`, progress to market research, create PRD and technical plan, generate real software, run tests, preview the app, force one build failure, auto-repair it, create and push a private GitHub repo containing real project content, restart the app, and resume with identical project list, entitlement, gate, chat, Git, and canvas state. The release E2E must record real account, real project ID, screenshots or video, and must pass three consecutive complete journeys.
