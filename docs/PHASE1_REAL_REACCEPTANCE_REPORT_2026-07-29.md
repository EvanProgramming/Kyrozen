# Kyrozen 第一阶段真实复验报告

## 结论

**不通过，不满足公开 Beta 发布条件。** 本次按 `docs/KYROZEN_MISSING_FEATURES_THREE_PHASE_PLAN.md` 第一阶段要求，从已安装的 `/Applications/Kyrozen.app` 真实操作桌面客户端，创建并使用普通用户项目“邻里活动报名助手”（`proj_6cb2be26`），覆盖生成、运行、预览、故障修复、附件、画布、GitHub、重启恢复和桌面 E2E。第一阶段已有明显改善，但仍没有达到“新用户可完成需求澄清、研究、规划、编码、测试、预览、Git 提交、GitHub 推送和项目恢复”的完整闭环。

## 验收环境与证据

| 项目 | 结果 |
|---|---|
| 仓库版本 | `37b1ee0`，工作区存在其他 AI/用户未提交修改，本次不修代码 |
| 客户端 | `/Applications/Kyrozen.app`，0.1.0，mtime `2026-07-29 12:54:35` |
| 生产服务 | `https://kyrozen.chat/api/health` 200，provider `deepseek`，model `deepseek-chat` |
| 生产模型 | 阻断：DeepSeek API key 返回 401，密钥仅显示尾号 `985a` |
| 真实项目 | `/Users/evangong/KyrozenProjects/proj_6cb2be26` |
| GitHub 仓库 | 私有仓库 `EvanProgramming/kyrozen-acceptance-neighborhood-events-20260729` |
| 最新提交 | `969b57e test: regenerate final acceptance product`，`origin/main` 已同步 |
| 本地验证 | Python `444 passed`；desktop lint、11 unit、renderer build 通过；desktop E2E `4 passed` |
| 发布记录 | `desktop/e2e/release-runs/release-run-2026-07-29T05-11-23-216Z.json` 标记 passed，但 account/projectId 为 `unknown`，recordings/screenshots 为空 |

## 第一阶段验收矩阵

| 范围 | 结果 | 真实表现 |
|---|---|---|
| 3.1 专用 Agent 路由与交接 | 部分通过 | 开发阶段请求显示“当前由 软件开发 Agent 处理”，日志确认 `SoftwareDevelopmentAgent (mode=development)`；但生产模型 401 阻断真实回复，旧项目聊天未稳定经过本地 `AgentRouter`，结构化交接未读取已有 PRD/TECH 文档 |
| 3.2 阶段门禁与真实进度 | 失败 | 门禁能显示已满足/缺失项、失败节点和修复入口；但顶部阶段、右侧门禁、本地 stagegate 三套状态会短暂冲突，切换项目和重启后会出现错误阶段、错误权限、错误 Git 状态的数秒窗口 |
| 3.3 真实软件生成、运行与修复 | 部分通过 | 已生成可运行 Python Web 产品，README、源码、测试、预览和 Git 提交存在；真实预览可创建活动、报名和取消；但自动修复“尝试 0 次”，失败时没有错误摘要和文件定位，手机号去重错误地跨活动全局生效 |
| 3.4 附件、状态、操作记录与确认 | 部分通过 | 图片缩略图、尺寸、主色可用，视频时长和关键帧可用，聊天主区不再刷模型日志；但图片/视频没有语义理解和转写，操作记录缺输入输出摘要和失败原因，高风险确认卡因模型 401 未能真实验收 |
| 3.5 本地 Git 与 GitHub 完整流程 | 部分通过 | 本地 init、提交、第二次功能提交、私有远端 push、secret 扫描均真实通过，头像和账号菜单可见；但断开 GitHub 后重新授权两次均进入 `Invalid or expired OAuth state`，客户端没有恢复界面 |
| 3.6 P0 端到端发布门槛 | 失败 | 4 条桌面 E2E 通过，但使用本地 HS256 JWT、占位 GitHub token 和 mock model；没有真实 OAuth、远端建库推送、阶段全链路、三次连续核心旅程、故障场景、录像或截图 |

## 关键阻断缺陷

| ID | 严重级别 | 问题 | 证据 |
|---|---|---|---|
| P0-01 | 阻断 | 生产模型不可用，真实 Agent 回复无法完成 | 用户聊天返回友好错误，技术详情为 DeepSeek 401 |
| P0-02 | 阻断 | GitHub 重新授权失败 | 断开后两次 Dia 回调均返回 `{"detail":"Invalid or expired OAuth state"}`，客户端停留未连接 |
| P0-03 | 阻断 | 账号登录恢复未完成 | 退出登录后点“使用 GitHub 登录”，客户端提示检查浏览器，Dia 没有出现可用的“打开 Kyrozen”恢复入口 |
| P0-04 | 阻断 | Agent 结构化交接缺失 | 开发 Agent 上下文中 Product Brief/PRD 均为 `(not set)`，但工作区已有 `docs/PRD.md` 和 `docs/TECH_DESIGN.md` |
| P0-05 | 阻断 | 自动修复闭环不成立 | 故意破坏 `app.py` 后运行失败，点击自动修复显示“修复未成功 尝试 0 次” |
| P0-06 | 阻断 | 阶段与进度存在多源冲突 | 进入/返回阶段、切换项目、重启后 UI 会短暂显示错误阶段、错误进度或错误下一步 |
| P0-07 | 阻断 | 项目切换有跨项目状态泄漏窗口 | 新项目已选中时仍显示上一项目 gate、Git 状态和可操作按钮，约数秒后才恢复 |
| P0-08 | 高 | 生成产品业务逻辑有真实缺陷 | 同一手机号报名第二个不同活动时被拒绝，提示“该手机号已经报名，不能重复提交” |
| P0-09 | 高 | 预览服务泄漏 | 同一项目留下 `8000`、`8001`、`8002` 三个监听进程，旧进程 PPID 为 1 |
| P0-10 | 高 | `FeatureImplementation` 未真实持久化 | `kyrozen_feature.json` 任务仍为 `pending`，没有持久化验证结果，UI 却显示已完成 |
| P0-11 | 高 | 非代码交付物丢字段 | `deliverable_research_report.md` 六个章节均为“未填写”，没有保留用户输入的背景、目标、结论 |
| P0-12 | 高 | 操作记录不满足发布要求 | 操作记录有数量并可恢复，但缺开始/结束时间、输入摘要、输出摘要和失败原因 |
| P0-13 | 高 | 画布仍暴露内部对象和原始日志 | 问题、市场、开发、测试页显示扁平内部字段、命令、stdout/stderr、RuntimeError |
| P0-14 | 高 | 附件不能真正参与需求理解 | 图片只有尺寸/主色，视频只有元数据和关键帧，未见视觉语义、时间点摘要或语音转写 |
| P0-15 | 高 | 发布 E2E 证明力不足 | release-run 账号和项目 ID 为 unknown，无录像截图，不覆盖真实 GitHub、预览、修复和故障恢复 |
| P0-16 | 中 | 重启初期状态错误 | 约 4 秒内显示免费账号限制、新建按钮禁用、gate/Git/附件/操作记录未恢复 |
| P0-17 | 中 | 风险推进记录不可读 | 历史 skip 只有 `problem_confirmed`、`market_confirmed`，缺原因、影响、批准人、恢复条件 |
| P0-18 | 中 | 没有锁文件 | 工作区有 `requirements.txt` 和 `.env.example`，未生成锁文件 |
| P0-19 | 中 | 测试反馈未展示 | “测试验证”页录入反馈后提示已保存，但刷新后页面不展示该反馈 |
| P0-20 | 中 | 画布统计不可信 | 项目主页显示“已形成资料 1份”，与本地多份 docs、README、源码、附件不一致 |

## 已通过或已改善项

| 项目 | 结果 |
|---|---|
| 真实软件产物 | `app.py`、`tests/test_app.py`、`README.md`、`.env.example`、`.gitignore` 均存在 |
| 真实运行 | 安装、构建、测试、核心流程测试和预览通过，预览地址最后为 `http://localhost:8002` |
| 真实用户流程 | 创建“社区环保讲座”，提交报名“陈雨 / 13800007029”，取消报名均成功 |
| GitHub | 本地提交和远端 push 成功，remote URL 未包含 token，工作区 secret 正则扫描零命中 |
| 用户菜单 | 右上角能显示 GitHub 头像、`Evan`、`@EvanProgramming` 和退出登录入口 |
| 聊天呈现 | 主聊天区未再显示 PlatformIO、模型调用 JSON、工具日志；运行中状态能显示用户可理解文案 |
| 附件基础能力 | PNG 缩略图和视频关键帧文件生成，并在重启后恢复 |
| 测试套件 | Python、desktop lint、unit、renderer build、4 条 E2E 均能跑通 |

## 额外记录的问题

- 家庭项目聊天历史中仍能看到 `Error: Failed to persist task task_cfa09f7a`，不符合“只显示最终回复或状态”的要求。
- “我的项目”可访问性 heading 显示 Value 2，但列表中实际有三个项目。
- 项目排序在切换和重启后会变化，增加误选风险。
- 右侧门禁在开发阶段仍提示“下一步：开始软件开发 / 进入实现阶段”，文案与实际阶段冲突。
- 返回开发阶段后“构建通过”曾从满足变为缺失，重新运行才恢复，说明验证结果重算不稳定。
- 运行失败只展示聚合失败节点，不展示具体错误摘要、文件路径和原命令。
- 测试页显示测试计划为空，但运行记录已经有 10 个生成测试。
- 学习改进页只有空标题，没有可执行建议、来源、适用条件或处理动作。
- 项目决策页没有可见决策记录，无法形成待确认队列。
- 当前测试结束时，客户端处于已退出登录且 GitHub 已断开的状态，这是验收 GitHub 恢复流程造成的现场状态。

## 修复后再验收准入

下一轮修复后必须重新安装 DMG，并用一个全新普通用户项目完成以下连续验收：登录、建项目、问题澄清、市场/产品/技术交接、开发生成、README 冷启动、故障制造、自动修复、预览业务流程、附件语义参与、GitHub 私有仓库首次推送、第二次提交推送、断开后重新授权、退出重登恢复。发布门槛要求同一核心旅程连续三次通过，且 release-run 必须记录真实账号、真实项目 ID、截图或录像、故障场景结果和可追溯日志。
