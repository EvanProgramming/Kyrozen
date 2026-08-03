# Kyrozen 第二阶段真实普通用户桌面测试记录

日期：2026-08-03
客户端：`desktop/release/Kyrozen-0.1.0-arm64.dmg`
执行方式：从 DMG 安装开始，使用 Computer Use 通过可见桌面界面操作。

## 测试原则

- 按普通用户自然语言逐步操作，不直接调用内部 API 推进阶段。
- 每遇到错误、异常、阻塞或与预期不符的界面行为，立即记录在本文件。
- 测试证据区分“观察到的行为”“自动化证据”和“用户可见结果”。

## 事件记录

| 时间 | 步骤 | 观察 | 严重度 | 处理/结果 |
|---|---|---|---|---|
| 2026-08-03 | DMG 安装后首次点击“使用 GitHub 登录” | 应用显示“登录已过期，请重新登录”，未出现 GitHub 授权页面 | P1 | 已记录；继续一次可恢复性检查，暂未判定通过 |
| 2026-08-03 | 第二次点击“使用 GitHub 登录” | 按钮变为“正在跳转 GitHub...”并保持禁用，仍未打开授权页面 | P1 | 已记录；准备通过关闭并重新启动应用检查恢复 |
| 2026-08-03 | 关闭并重新启动 DMG 安装的应用 | Computer Use 返回 `timeoutReached`，未能把该次重启判定为成功 | P1 | 已记录；重新读取应用状态 |
| 2026-08-03 | 重新读取 Kyrozen 窗口 | Computer Use 再次返回 `timeoutReached` | P1 | 已记录；当前真实测试被安装包登录/窗口状态阻塞 |
| 2026-08-03 | Dia 中点击“打开 Kyrozen”完成协议回调 | Computer Use 返回 `timeoutReached`，未能立即读取回调后的应用状态 | P1 | 已记录；继续只读确认登录状态 |
| 2026-08-03 | Dia 完成 GitHub 授权并点击“打开 Kyrozen”后 | DMG 安装的 Kyrozen 显示“GitHub 登录尚未完成，请检查浏览器提示后重试” | P1 | 已记录；清理挂载卷后重试，未判定登录通过 |
| 2026-08-03 | 清理挂载卷后关闭并重新启动安装包 | Computer Use 返回 `App quit`，未能在同一调用中完成重启 | P1 | 已记录；单独重新读取/启动安装包 |
| 2026-08-03 | Dia 新标签页恢复登录 | Computer Use 返回 `cannotClickOffscreenElement`，无法可靠选择最新登录标签 | P1 | 已记录；停止继续操作，避免绕过真实用户流程 |
| 2026-08-03 | 修复后重新开始 DMG 安装，Finder 中打开“前往文件夹” | Computer Use 返回 `Sky Computer Use native pipe closed before response`，本次 UI 操作未获得结果 | P1 | 已记录；重试 UI 通道 |
| 2026-08-03 | Finder 已定位新 DMG，尝试用 Computer Use 双击挂载 | Computer Use API 返回 `sky.double_click is not a function`，操作未执行 | P1 | 已记录；改用单击后 Return 的可见 UI 操作 |
| 2026-08-03 | 将修复后的 Kyrozen 拖入 Applications 并选择 Replace | Finder 报“The operation can’t be completed because the item ‘Kyrozen’ is in use.”，旧安装进程未完全退出 | P1 | 已记录；通过可见 UI 结束占用进程后重试 |
| 2026-08-03 | 重新安装修复版后在 Dia 点击“Open Kyrozen” | 回调先显示登录按钮处理中，等待约 12 秒后进入“我的项目”主页，GitHub 用户 Evan 可见 | PASS | macOS DMG 安装包登录回调修复验证通过 |
| 2026-08-03 | 新建项目后发送自然语言问题探索消息 | 约 15 秒后仍显示“正在理解你的需求”，输入框保持禁用，未得到引导回复 | P1 | 已记录；继续观察一次并准备使用界面“停止/重试”恢复 |
| 2026-08-03 | 发送第二条自然语言探索消息并等待回复 | Computer Use 执行超时并重置 kernel，未能读取这次消息的最终 UI 结果 | P1 | 已记录；重新建立 UI 状态后检查是否已完成 |
| 2026-08-03 | 打开项目画布查看第二阶段工作中心 | 页面显示“上次操作失败：刷新项目工作台”、`fetch failed`；同时上一条消息显示“发送失败：任务派发超时” | P1 | 已记录；使用界面重试入口，不调用内部接口 |
| 2026-08-03 | 点击“重试：刷新项目工作台” | 约 25 秒后仍显示失败，详情变为 `{"detail":"Not Found"}`，主页资料未加载 | P1 | 已记录；工作台 API/版本不匹配，继续记录可见中心状态但不判定通过 |
| 2026-08-03 | 提交登录回调修复并推送远程 `main` | Git push 被远程拒绝：`[rejected] HEAD -> main (fetch first)`，远程已有本地未包含的提交 | P1 | 已记录；未强推，需先安全同步远程提交后再重试 |
| 2026-08-03 | 同步远程 `main` 并自动恢复未提交工作区 | rebase 后 autostash 应用出现冲突，涉及 `desktop/electron/pythonRuntime.ts` 与 `desktop/src/OnboardingPage.tsx`；stash 仍保留 | P1 | 已记录；恢复冲突文件到原工作区版本，保留 stash 作为安全副本 |
| 2026-08-03 | 生产服务器对齐远程 `main` 并重建 Compose | 镜像构建成功，但 `kyrozen-backend` 健康检查失败，前端依赖启动失败 | P1 | 已记录；读取容器日志并修复启动问题 |
| 2026-08-03 | 补齐未跟踪 Phase 2 模块后重新部署 | 后端健康检查已通过，但前端启动失败：宿主机 `0.0.0.0:80` 端口已被占用 | P1 | 已记录；检查占用者并安全恢复 Compose |
| 2026-08-03 | 检查容器内 Phase 2 路由时首次组合命令 | 远程 shell 报 `Syntax error: "(" unexpected`，仅诊断命令引号错误，服务未受影响 | P2 | 已记录；改用不含嵌套 shell 的只读检查 |
| 2026-08-03 | 第二次用内联 Python 检查容器路由 | 远程命令因转义换行触发 `SyntaxError`，仅诊断命令失败，服务未受影响 | P2 | 已记录；改用 curl 与源码检查 |
| 2026-08-03 | 在工作台填写市场研究问题 | Computer Use 返回 `Cannot set a value for an element that is not settable`，使用了刷新后的错误元素索引，未写入数据 | P2 | 已记录；重新读取完整可访问树后重试 |
| 2026-08-03 | 启动真实市场研究运行并等待结果 | Computer Use 等待调用超时并重置 kernel，未能读取研究最终状态 | P1 | 已记录；重新建立 UI 状态后读取现状，不重复启动运行 |
| 2026-08-03 | 保存 BOM 后读取状态的 Computer Use 脚本 | 脚本字符串中的正则换行转义错误，返回 `Unterminated regular expression`，未执行读取动作 | P2 | 已记录；重新读取界面后验证写入 |
| 2026-08-03 | 读取测试中心状态的 Computer Use 脚本 | 脚本包装器出现 `SyntaxError: Unexpected token ':'`，未执行 UI 动作 | P2 | 已记录；修正脚本后继续 |
| 2026-08-03 | 打开测试结果状态下拉菜单并读取截图 | Computer Use 返回 `Cannot read properties of null (reading 'url')`，原生菜单状态无截图 URL | P2 | 已记录；通过键盘选择下拉选项 |
| 2026-08-03 | 读取失败测试表单值的 Computer Use 脚本 | 脚本输出回调再次出现 `SyntaxError: Unexpected token ':'`，未执行 UI 动作 | P2 | 已记录；修正输出回调后继续 |
| 2026-08-03 | 保存失败测试结果后读取缺陷列表的脚本 | 脚本输出回调再次写错三元表达式，返回 `SyntaxError: Unexpected token ':'`，未执行 UI 动作 | P2 | 已记录；改用正确输出回调读取 |
| 2026-08-03 | 填写回归修复说明的 Computer Use 脚本 | 脚本输出回调再次出现 `SyntaxError: Unexpected token ':'`，未执行 UI 动作 | P2 | 已记录；修正输出回调后继续 |
| 2026-08-03 | 测试中心真实失败→缺陷→修复→原用例回归 | 失败测试保存后自动出现 `Desktop Workbench Defect`（open）；填写修复说明并再次点击回归后显示“回归已通过，缺陷已解决” | PASS | 生产后端和桌面工作台闭环通过 |
| 2026-08-03 | 读取改进中心表单的 Computer Use 脚本 | 脚本输出回调再次出现 `SyntaxError: Unexpected token ':'`，未执行 UI 动作 | P2 | 已记录；修正回调后继续 |
| 2026-08-03 | 从反馈中心切换硬件中心时读取标签的脚本 | 脚本输出回调再次出现 `SyntaxError: Unexpected token ':'`，实际点击了错误标签但未改写数据 | P2 | 已记录；重新读取标签索引后继续 |
| 2026-08-03 | 在工作台选择“嵌入式”并点击“确认流程” | 页面显示“上次操作失败：确认项目流程”，项目类型仍未确认 | P1 | 已记录；读取失败详情并通过界面重试入口检查门禁原因 |

| 2026-08-03 | 工作台只读发现 ESP32 设备 | Arduino CLI 1.5.1 与 ESP32 核心已发现，但未枚举到设备；状态明确为 `BLOCKED`，原因 `board_not_connected` | BLOCKED | 按用户约定停止真实硬件流程，请重新连接 ESP32 N16R8 后继续 |
| 2026-08-03 | 重新执行工作台“只读发现设备” | 第二次探针仍返回 `board detected false`、`BLOCKED / board_not_connected`；上传与串口观察按钮继续禁用 | BLOCKED | 已确认不是一次性探针结果；等待 ESP32 N16R8 重新连接后继续 |
| 2026-08-03 | Fake Transport 协议六场景 | 工作台显示“协议六场景已通过并持久化”；正常通信、离线、重连、重复消息、错误消息、版本不兼容均为 `PASSED` | PASS | 模拟器验证完成；不替代真实串口和 ESP32 实物验收 |
| 2026-08-03 | Fake Transport 版本化协议交换 | 工作台显示 `protocol_exchange 已完成并记录本地硬件证据`，请求/响应均含协议版本、消息类型、字段、方向和时间戳，状态 `PASSED persisted true` | PASS | 未确认未提供的物理/BLE 协议，不点击正式协议确认 |
| 2026-08-03 | 工作台刷新恢复 | 点击“刷新”后仍读取到 BOM、Maker 步骤、硬件探针记录、Fake 六场景和版本化协议交换状态；页面未生成新的失败提示 | PASS | 刷新读取验证通过；真实重启恢复仍需在物理流程结束后再做最终复测 |
| 2026-08-03 | 项目主页窄窗口视觉检查 | 约 1152px 窗口下，市场研究来源详情中的长 URL/文本溢出列边界并覆盖相邻内容，工作台信息不可可靠阅读 | P1 | 已记录；定位工作台响应式布局和长文本换行样式，修复后重新打包安装复测 |
| 2026-08-03 | Finder 安装修复版 DMG 时替换应用 | Finder 提示 `The operation can’t be completed because the item “Kyrozen” is in use.`，旧应用正在运行导致替换失败 | P1 | 已记录；关闭旧 Kyrozen 后重试 Finder 替换 |
| 2026-08-03 | Computer Use 关闭旧 Kyrozen | 点击窗口关闭按钮时原生通道返回 `timeoutReached`，未能直接确认窗口是否已退出 | P2 | 已记录；读取 Finder 与 Kyrozen 状态后继续，不重复假设关闭结果 |
| 2026-08-03 | 启动 Finder 替换后的修复版 Kyrozen | Computer Use 读取/启动应用时再次返回 `timeoutReached`，暂未确认是启动慢、安全提示还是应用启动失败 | P1 | 已记录；读取当前窗口状态后继续启动诊断 |
| 2026-08-03 | Finder 定位已安装应用的 Computer Use 脚本 | 使用刷新前的输入框索引调用 `set_value`，返回 `Cannot set a value for an element that is not settable`；未改变文件 | P2 | 已记录；重新读取 Go to 对话框后再定位 |
| 2026-08-03 | Finder 启动已安装 Kyrozen | 双击当前选中的应用返回 `cannotClickOffscreenElement`，图标不在当前可点击视口；未启动新操作 | P2 | 已记录；改用键盘 Return 启动当前选中应用 |
| 2026-08-03 | 键盘启动修复版 Kyrozen 后读取界面 | 等待启动/读取时 Computer Use 返回 `timeoutReached`，未能直接确认窗口状态 | P1 | 已记录；通过应用列表和窗口状态继续诊断 |

| 2026-08-03 | 修复版重启后首次打开项目画布 | 登录恢复成功，但项目工作台首次加载显示 `上次操作失败：刷新项目工作台` / `fetch failed` | P1 | 已记录；通过界面“重试”入口验证恢复，不伪造刷新成功 |
| 2026-08-03 | 第二次安装错误提示 | Finder 在应用进程已退出后仍提示目标 `Kyrozen` 正在使用，并叠加替换确认对话框 | P1 | 已记录；不强行覆盖，改用 Finder“保留两者”隔离启动最新 DMG 副本 |
| 2026-08-03 | 修复版 DMG 隔离副本重启恢复 | 从 `Kyrozen-0.1.0-arm64.dmg` 安装为 `Kyrozen 2.app` 后，登录会话、项目资料和工作台数据均恢复；首次加载等待后无错误条，窄窗口长 URL/研究内容不再溢出 | PASS | 响应式布局与重试错误清理修复通过真实安装包复测 |
| 2026-08-03 | 工作中心键盘导航首次尝试 | Computer Use 使用 `ArrowRight` 键名返回 `keyNotFound("ArrowRight")`，未执行 UI 切换 | P2 | 已记录；改用 Computer Use 支持的 `Right` 键名重试 |
| 2026-08-03 | 工作中心键盘导航复测 | 聚焦“项目主页”后按 `Right`，真实切换到“决策中心”并保持 `aria-selected` 状态，工作台内容正常显示 | PASS | 键盘 Tab 导航基本路径通过 |
| 2026-08-03 | 七个工作中心键盘遍历 | 使用方向键依次切换到采购、Maker、测试、改进、反馈中心；每次均更新选中状态且未出现新的失败提示 | PASS | 专用工作中心键盘遍历通过 |

## 最终结果

结果：`BLOCKED_AT_PHYSICAL_ESP32`

已完成：DMG 挂载与安装、通过 Dia 默认浏览器完成 GitHub 登录回调、项目创建、问题探索对话、证据写入、真实研究运行与来源状态持久化、嵌入式流程确认、BOM、Maker 步骤、测试失败→缺陷→修复→原用例回归、改进建议写入，以及硬件工具链只读发现。

当前阻塞：修复版隔离 DMG 副本已重新验证工作台、刷新恢复、窄窗口布局和键盘导航；只读发现仍确认 Arduino CLI 1.5.1 和 ESP32 核心已安装，但未发现 ESP32 N16R8 设备，硬件状态为 `BLOCKED / board_not_connected`，因此尚未在本次 DMG 流程中执行编译、上传、串口观察和拔插恢复。

结论：本次不能宣称第二阶段完成。重新连接 ESP32 N16R8 后，需要从只读发现继续真实硬件验收；反馈中心的真实目标用户记录也未伪造，仍需真实参与者数据或明确验收豁免。

| 2026-08-03 | 测试后清理：Finder 弹出 DMG | 第二次操作时 Finder 挂载卷列表刷新，Computer Use 报元素失效（-10005）；已记录并准备重新读取状态后重试 | RETRY | 不影响正式安装，继续清理剩余临时卷 |
| 2026-08-03 | 测试后清理：Finder 搜索 | Computer Use 键名 `ENTER` 不被当前动作接口识别（keyNotFound）；已记录，改用搜索按钮/当前界面继续 | RETRY | 不影响正式安装 |
| 2026-08-03 | 测试后清理：移除临时副本 | Computer Use 键名 `super+delete` 不被当前动作接口识别（keyNotFound）；临时副本仍被精确选中，改用 Finder 文件菜单的 Move to Trash | RETRY | 不影响正式安装 |
| 2026-08-03 | 测试后清理：移除临时副本 | Finder 提示 `Kyrozen 2` 仍处于打开状态，拒绝移到废纸篓；先核对并关闭临时副本进程后重试 | RETRY | 正式安装不受影响 |
| 2026-08-03 | 测试后清理完成 | 退出临时副本、弹出 3 个 Kyrozen DMG 卷、将 `/Applications/Kyrozen 2.app` 移到废纸篓；核对后仅保留 `/Applications/Kyrozen.app`，无 Kyrozen DMG 挂载卷、无 Kyrozen 运行进程 | PASS | 后续每轮 DMG 复测后执行同样清理 |
