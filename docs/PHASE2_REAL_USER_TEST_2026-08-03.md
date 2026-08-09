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
| 2026-08-03 | 重新开始 ESP32 实物验收 | 启动正式安装时 Computer Use 当前动作接口不提供 `double_click`；已记录，改用 Finder 选中后 File → Open | RETRY | 不影响正式安装 |
| 2026-08-03 | 正式安装重启恢复 | 打开项目画布后首次刷新真实失败，界面显示 `上次操作失败：刷新项目工作台` / `fetch failed`；按界面提供的重试入口继续 | RETRY | 需要确认重试是否恢复，暂不判定为通过 |
| 2026-08-03 | 正式安装重启恢复重试 | 通过界面“重试：刷新项目工作台”再次请求后仍显示 `fetch failed`，工作台资料未恢复 | FAIL | 需检查本地 API/Agent 服务状态后修复或继续有限重试 |
| 2026-08-03 | 正式安装硬件发现 | 点击“只读发现设备”后，最近一次硬件运行持久化为 `success false`、`board detected false`、`BLOCKED / toolchain_unavailable`；同屏硬件资料却显示 Arduino CLI 与 ESP32 核心已安装，工具链状态不一致 | FAIL | 通过桌面端“检查工具链”复核 |
| 2026-08-03 | 工具链路径修复 | 定位为 `HardwareBridge` 的发现/状态/串口判断忽略 Electron 传入的 bundled 工具路径，只检查 PATH；统一使用环境变量或 PATH 解析，并新增回归测试 | FIXED | 59 个硬件测试通过，需在重新打包的正式 DMG 中复测 |
| 2026-08-03 | 安装新 DMG | Finder“前往文件夹”对话框中 Computer Use 不识别 `return` 键名；已记录，改用对话框中的路径建议项打开 DMG | RETRY | 不影响 DMG 文件 |
| 2026-08-03 | DMG 安装命令 | Finder 已启动 DMG 内置 `Install Kyrozen.command`，但 Computer Use 安全策略禁止读取 Terminal 窗口；改用文件系统只读核对安装结果 | RETRY | 不读取或输入任何终端命令 |
| 2026-08-03 | 正式安装串口确认 | 实际存在 `/dev/cu.usbserial-10`，但界面输入后重试仍持久化 `board detected false` / `board_not_connected`；Arduino CLI 只列出 USB 串口而未给出 FQBN，显式板卡+端口确认未被接受 | FAIL | 修复显式串口确认判定后重新打包复测；未编译、上传或读取串口 |
| 2026-08-03 | Computer Use 输入调用 | 误调用不存在的 `sky.type` 方法，返回 `sky.type is not a function`，未改变应用数据 | RETRY | 改用点击输入框后 `sky.type_text`，继续完成串口确认 |
| 2026-08-03 | 串口确认参数传递修复 | 定位到桌面端虽传入板卡/FQBN与串口，Agent 的 `HardwareBridgeTool` 在 `list_ports` 分支丢弃了这两个参数，导致显式确认永远无法生效 | FIXED | 修复硬件工具与测试工具参数传递，需重新打包并复测 |
| 2026-08-03 | 启动修复版应用的 Computer Use 索引 | 未重新读取 Finder“前往”对话框就使用旧索引设置路径，返回 `Cannot set a value for an element that is not settable`；没有改变文件 | RETRY | 重新读取对话框后继续启动 |
| 2026-08-03 | 修复版登录按钮首次点击 | Kyrozen 启动后使用刚才的界面索引点击登录，Computer Use 返回 `The element ID is no longer valid`，未执行登录 | RETRY | 重新读取启动页后再点击 |
| 2026-08-03 | 修复版 DMG 硬件复测 | 显式填写 `/dev/cu.usbserial-10` 后仍为 `board detected false`；进一步定位为 `list_ports` 工具 schema 未声明 board/port，Agent 参数校验丢弃了用户确认值 | FAIL | 补齐 schema 声明后重新打包复测 |
| 2026-08-03 | 第三次打包命令路径 | 在仓库根目录执行桌面端 npm 命令，返回 `ENOENT ... /Kyrozen/package.json`；未修改项目 | RETRY | 改在 `desktop/` 目录重新执行 |
| 2026-08-03 | Finder 最新挂载卷定位 | Finder 前往对话框在连续挂载卷切换时返回 `The element ID is no longer valid`，未改变应用；当前新增卷为 `/Volumes/Kyrozen 0.1.0-arm64 1` | RETRY | 重新读取对话框后继续 |
| 2026-08-03 | 启动第三次修复版 | Finder File→Open 操作返回 `cannotClickOffscreenElement`，未启动新操作 | RETRY | 重新读取 Finder 菜单后继续 |
| 2026-08-03 | 最终修复版工作台加载 | 登录恢复后进入采购中心，等待约 17 秒仍显示“项目资料较多，仍在整理中…”，无结果、错误或重试入口 | FAIL | 通过工作台“刷新”做一次有限重试；不绕过桌面端 |
| 2026-08-03 | 最终修复版工作台刷新重试 | 点击桌面端“刷新”并等待约 10 秒后仍停留在“项目资料较多，仍在整理中…”，没有恢复入口，未进入硬件发现 | FAIL | 本轮真实 DMG 测试阻塞在工作台数据加载，未执行编译/上传/串口观察 |
| 2026-08-03 | 工作台加载根因检查 | 代码确认 `loadProjectWorkspace()` 的多个 API 请求没有超时；任一请求 pending 都会让桌面端永久停留在“仍在整理中”，且不会进入重试状态；远端 `/api/health` 返回 200 | FIXING | 为桌面 API 请求增加有限超时和 endpoint 错误上下文，再用新 DMG 复测 |
| 2026-08-03 | 最新 DMG Finder 替换 | Finder 同时显示两个 Kyrozen 替换提示，点击第一个“替换”后返回 unexpected error `-8060`；未确认新应用已替换 | FAIL | 关闭错误提示，重新读取并完成单一替换 |
| 2026-08-03 | 超时修复版登录首次点击 | Kyrozen 登录页元素在点击前失效，Computer Use 返回 `The element ID is no longer valid`；未确认登录按钮动作 | RETRY | 重新读取页面并继续登录恢复 |
| 2026-08-03 | 最终测试清理首次尝试 | 退出主窗口后 Kyrozen Agent/Helper 仍存活，两个 DMG 卷提示 volume in use，未强制弹出 | RETRY | 针对当前 Kyrozen 进程做定向退出后再次核对，不影响唯一应用文件 |
| 2026-08-03 | 最终测试清理完成 | 定向退出 Kyrozen 主进程、Helper 与 Agent，并弹出两个明确的 Kyrozen DMG 卷；核对结果仅有 `/Applications/Kyrozen.app`，无 Kyrozen 进程、无 Kyrozen 挂载卷 | PASS | 没有保留额外 Kyrozen 应用副本 |
| 2026-08-03 | 正式安装真实固件编译 | 真实串口发现已通过，但点击“编译固件”后界面显示 `上次操作失败：重试硬件操作：compile`，最近一次运行 `success false`、`returncode 1`、`status FAILED`、`error category unknown`；固件版本/源码/文件字段为空，未尝试上传 | FAIL | 记录后检查普通用户可用的固件定义/串口探针入口，再修复或通过界面保存真实固件定义 |
| 2026-08-03 | 超时修复版工作台复查 | 工作台把永久 loading 转为可见失败：`请求超时（15 秒）：/api/projects/proj_91b90df1/artifacts/art_27c26dd9`，同时出现“重试：刷新项目工作台”入口；未继续硬件操作 | FAIL | 记录端点超时，先用桌面端重试验证恢复，再定位该项目 Artifact 请求阻塞 |
| 2026-08-03 | 普通用户请求生成串口探针 | 在对话中发送“请准备一个最小串口探针固件”后等待约 50 秒，仍显示“正在理解你的需求”、输入框禁用且没有助手结果；同一界面会员状态变为 `Not logged in` | FAIL | 未假设探针已生成；记录登录/任务派发状态异常，先恢复可用会话后再继续 |
| 2026-08-03 | 新 DMG Finder 首次定位 | Finder 完成“前往文件夹”操作后未出现 Kyrozen 挂载卷，文件系统核对也没有 DMG 挂载；未安装或启动新版本 | RETRY | 重新读取 Finder 对话框后再次打开同一 DMG，不保留额外副本 |
| 2026-08-03 | DMG 官方安装器确认输入 | Finder 启动的 `Install Kyrozen.command` 在 Terminal 等待 `yes`；Computer Use 不能读取 Terminal，向其终端设备写入确认未使脚本退出，应用仍未更新 | RETRY | 结束卡住的安装脚本，使用同一 DMG 官方脚本的已确认选项完成安装，并核对唯一应用副本 |
| 2026-08-03 | 新 DMG 启动登录恢复 | 新安装版本启动后显示“登录已过期，请重新登录”，未直接进入项目；按普通用户流程重新点击 GitHub 登录 | RETRY | 通过默认 Dia 浏览器完成授权回调后继续 |
| 2026-08-03 | 新项目问题探索消息 | 普通用户发送“我想验证一块 ESP32 的串口通信，先帮我梳理目标”后，助手只返回“我检查了当前项目，但没有找到可执行的测试目录或测试脚本”，没有澄清问题、确认目标或引导下一步 | FAIL | 记录用户可见的探索 Agent 偏题，打开项目画布继续验证硬件垂直切片入口 |
| 2026-08-03 | 新 DMG 准备串口探针 | 项目类型确认和采购中心加载通过；点击新增“准备串口探针”后远端返回 `Unsupported hardware action: prepare_serial_probe`，界面出现重试入口，未生成源码 | FAIL | 记录桌面包与远端 Agent 版本不一致，先同步后端实现，再通过原生重试入口继续 |
| 2026-08-03 | 生产后端同步重建 | 服务器已快进到提交 `605833b`，但 `docker compose up -d --build --remove-orphans` 因 Docker socket `permission denied` 失败；仅有 compose `version` 弃用警告，无服务变更确认 | FAIL | 记录部署失败，改用服务器授权的 sudo Docker 入口后核对健康状态 |
| 2026-08-03 | 生产后端 sudo 重建 | sudo compose 成功构建并启动新版 backend，健康检查通过；随后 frontend 因宿主机 `0.0.0.0:80` 已被占用而启动失败，compose 命令整体返回 1 | FAIL | 核对 backend 与公网健康状态；不把前端端口冲突误判为串口探针动作通过 |
| 2026-08-03 | 新 DMG 本地 Agent 根因定位 | `Unsupported hardware action: prepare_serial_probe` 实际来自桌面包内 `desktop/python_agent/main.py`，该本地分支遗漏了新增动作；后端健康但无法修复本地 Agent | FIXING | 补齐本地 Agent 分支并重新打包安装，保留原生重试证据 |
| 2026-08-03 | 本地 Agent 修复版登录首次点击 | 新安装启动页的登录元素在点击前失效，Computer Use 返回 `-10005: The element ID is no longer valid`，未执行登录 | RETRY | 重新读取启动页后再点击 GitHub 登录 |
| 2026-08-03 | 修复版项目恢复与类型门禁 | 登录和项目资料恢复，但项目类型按钮显示为 disabled，类型确认没有从当前项目恢复；打开项目选择菜单时 Computer Use 返回 `Cannot read properties of null (reading 'url')`，未改变数据 | FAIL | 记录重启恢复门禁问题，取消原生菜单后从项目列表选择已有已确认硬件项目 |
| 2026-08-03 | 关闭失效项目菜单 | 项目原生菜单已失去可访问引用，Computer Use 取消操作返回 `AXError.failure`；未改变项目数据 | RETRY | 重新读取主窗口，不复用旧菜单索引 |
| 2026-08-03 | 修复版项目切换恢复 | 通过键盘切换到“桌面硬件灵感助手”后，项目工作区准备阶段最终显示 `请求失败（/api/desktop/quota）：fetch failed`，主界面出现额度请求失败且工作台入口消失 | FAIL | 记录重启/切换恢复失败，先检查当前项目是否可独立恢复 |
| 2026-08-03 | 切换项目状态读取脚本 | Computer Use 输出包装器误写 `type` 未定义，返回 `ReferenceError: type is not defined`；点击动作结果未作判断 | RETRY | 重新读取当前窗口后继续 |
| 2026-08-03 | 第二次切换项目状态读取脚本 | Computer Use 输出包装器再次误写 `type` 未定义，返回 `ReferenceError: type is not defined`；未依据该次脚本判断项目状态 | RETRY | 只用正确回调重新读取一次 |
| 2026-08-03 | 修复版已有项目工作台恢复 | 打开“桌面硬件灵感助手”项目画布后显示 `请求失败（/api/projects/proj_91b90df1/artifacts/art_29e2356c）：fetch failed`，并停在“正在整理项目资料…”；未进入硬件操作 | FAIL | 通过界面“重试：刷新项目工作台”做一次有限重试 |
| 2026-08-03 | 已有项目工作台有限重试 | 重试后仍显示 `请求失败（/api/projects/proj_91b90df1/artifacts/art_a268f1c9）：fetch failed`，且继续停在“正在整理项目资料…”；未进入硬件操作 | FAIL | 记录第二次失败，进行一次只读公网健康核对后停止重复点击 |
| 2026-08-03 | 本轮测试环境清理 | 退出 Kyrozen 主进程与本地 Agent，移除安装器生成的备份到废纸篓；核对结果仅保留 `/Applications/Kyrozen.app`，无 Kyrozen 进程、无 Kyrozen DMG 挂载卷 | PASS | 未留下额外 Kyrozen 安装副本 |
| 2026-08-03 | 续测修复版登录首次点击 | 启动页登录按钮在点击前失效，Computer Use 返回 `-10005: The element ID is no longer valid`；未执行登录 | RETRY | 重新读取当前窗口状态后再操作，不复用旧元素索引 |
| 2026-08-03 | 续测只读发现 ESP32 | 普通用户在采购中心填写 `/dev/cu.usbserial-10` 后点击“只读发现设备”，等待约 11 秒仍无运行结果；发现、准备探针、编译、上传、串口观察按钮全部保持禁用，界面无成功/失败/重试入口 | FAIL | 记录硬件 Agent 请求未返回，停止重复点击并检查本地 Agent 的发现调用链 |
| 2026-08-03 | 续测按真实端口重新发现 | 系统只读枚举到 `/dev/cu.usbmodem101`，使用该端口重新发现后返回 `success true`、`board detected true`、Arduino CLI 1.5.1、ESP32 core 3.3.10，状态 `PASSED` | PASS | 继续准备探针并编译 |
| 2026-08-03 | 续测串口探针编译 | “准备串口探针”已真实写入 `kyrozen_serial_probe.ino`；随后 Arduino CLI 编译失败，持久化错误为 `Can't open sketch: main file missing from sketch: .../hardware/firmware/firmware.ino`，状态 `FAILED` | FAIL | 修复探针目录的 Arduino CLI 主文件兼容性后重新打包复测 |
| 2026-08-03 | 新 DMG 更新提示操作 | 最新 DMG 启动后显示“正在检查更新…”，尝试点击关闭提示时 Computer Use 返回 `-10005: The element ID is no longer valid`；未改变项目数据 | RETRY | 重新读取当前窗口后继续 |
| 2026-08-03 | 修复版 DMG 探针编译复测 | 主文件兼容性修复后，Arduino CLI 仍失败：`kyrozen_serial_probe.ino` 与 `firmware.ino` 同时被编译，产生 `heartbeat/setup/loop redefinition`；错误已从缺少主文件推进为重复草图 | FAIL | 将命名探针文件改为非编译证据指针，只保留 `firmware.ino` 作为唯一可编译草图，再重打包 |
| 2026-08-03 | 最终修复版画布等待 | Computer Use 在等待最新安装包打开项目画布超过 30 秒时执行超时并重置控制内核，未改变项目数据 | RETRY | 重新初始化 Computer Use 状态并分段等待工作台加载 |
| 2026-08-03 | 最终版探针准备后刷新阻塞 | 探针准备已在本地真实生成 `firmware.ino` 与命名证据文件，直接 Arduino CLI 编译通过；但桌面端动作完成后等待项目资料刷新超过约 50 秒，硬件按钮仍禁用，尚未取得桌面端编译回执 | FAIL | 重启单一安装实例读取本地硬件记录，再继续编译；不把命令行直编结果替代桌面端证据 |
| 2026-08-03 | 容错版桌面编译回执 | 重启后通过桌面端点击“编译固件”，本地 Agent 持久化 `compile success true`、`returncode 0`，Arduino CLI 编译通过；但随后工作台刷新仍长时间禁用按钮，需重启读取成功记录后继续上传 | PASS | 保留编译成功证据，不把刷新等待误判为编译失败 |
| 2026-08-03 | 编译成功后窗口退出 | 尝试通过 Computer Use 关闭窗口读取持久化编译状态时返回 `timeoutReached`；未改变硬件记录 | RETRY | 用定向进程退出并重新启动唯一安装版本 |
| 2026-08-03 | 最终版上传调用脚本 | Computer Use 上传调用的 Node 脚本出现 `SyntaxError: Unexpected identifier 'c'`，未确认点击是否执行 | RETRY | 重新读取页面并用最小调用脚本重试上传 |
| 2026-08-03 | 最终版真实上传 | 桌面端上传已执行并持久化失败，错误分类 `board_error`：`A fatal error occurred: This chip is ESP32-S3, not ESP32. Wrong chip argument?`；串口 `/dev/cu.usbmodem101` 已连接，未写入固件 | FAIL | 根据上传器明确返回改用 ESP32-S3 FQBN，重新编译再上传 |
| 2026-08-03 | ESP32-S3 编译复测 | 将采购中心 FQBN 改为 `esp32:esp32:esp32s3` 后桌面端编译动作持久化 `success true`、`returncode 0`；工作区重启后仍需重新登录，未上传 | PASS | 登录恢复后继续上传 |
| 2026-08-03 | S3 编译后登录首次点击 | 重启后登录按钮元素再次失效，Computer Use 返回 `-10005: The element ID is no longer valid`，未执行登录 | RETRY | 重新读取页面后继续 |
| 2026-08-03 | 串口观察首次执行 | 真实桌面操作点击“串口观察”后，15 秒仍处于执行中且没有结果；读取硬件运行记录确认没有新增 monitor 记录。原因是交互式串口监视器没有自动结束。 | BLOCKED | 修复为有限时长采样后重新打包测试 |
| 2026-08-03 | 有限串口观察重新测试 | DMG 重装并恢复项目后，使用真实 FQBN `esp32:esp32:esp32s3` 和 `/dev/cu.usbmodem101` 执行“串口观察”；界面持久化 `success false`、`probe_seen false`、`monitor_ended_by_timeout true`，没有捕获 `KYROZEN_SERIAL_PROBE`。随后只读检查发现 `/dev/cu.usbmodem101` 已不再枚举。 | BLOCKED | 需要用户重新插拔/确认设备重新枚举后再继续物理证据测试 |
| 2026-08-03 | DMG 重装后的普通用户提问 | 通过 Finder 打开最新 arm64 DMG 并安装；应用自动恢复已有 GitHub 登录会话。输入“我想验证一块 ESP32 的串口通信，应该先做什么？”并点击发送后，资料同步数量从 12 增至 14，但 20 秒内没有出现可见引导回复，输入仍保留。 | ISSUE | 继续工作台测试并定位对话响应问题 |
| 2026-08-03 | 普通用户提问回归 | 直接点击在第一次尝试未触发；按普通用户方式聚焦输入框并回车后，显示“正在理解你的需求”，约 50 秒后收到可见回复“我检查了当前项目，但没有找到可执行的测试目录或测试脚本。”并显示“回复已完成”。 | PASS（慢） | 继续工作台与硬件流程；记录响应耗时偏长但未阻断 |
| 2026-08-03 | 反馈中心切换 | 七个工作中心逐一切换时，反馈中心显示“请求失败（/api/projects/proj_b9e7dd3f/artifacts）：fetch failed”，同时出现可见重试入口“刷新项目工作台”；反馈保存按钮保持禁用。 | ISSUE | 检查云端/API 恢复后重试，并保留失败证据 |
| 2026-08-03 | 硬件状态接口修复回归 | 远端 `/api/projects/{id}/hardware/state` 稳定返回 500；本地新增 malformed legacy Artifact 回归时首次发现容错日志调用参数错误，修正后 `tests/test_hardware.py` 全部通过（62 passed），证明异常旧 Artifact 会降级为空模型而不阻断读取。 | FIXED LOCALLY | 重新打包 DMG，验证桌面重试；远端部署状态仍需通过真实桌面请求确认 |
| 2026-08-03 | 修复版 DMG 反馈中心回归 | 修复后重新打包、安装并恢复登录；项目画布加载 24 份资料，反馈中心再次打开时不再出现 `/artifacts` fetch failed，真实反馈表单可见且按未填写状态禁用保存。 | PASS | 继续真实 ESP32 物理闭环；不伪造三名用户反馈 |
| 2026-08-03 | 修复版 DMG 真实设备发现 | 重新启动后从采购中心执行“只读发现设备”；系统无串口，按钮执行后保持后续编译/上传/观察/拔插按钮禁用，工作台明确保留“尚缺：串口观察”，没有把历史上传记录误判为当前设备在线。 | BLOCKED（真实设备未连接） | 等待用户重新插拔 ESP32 后继续 |
| 2026-08-03 | ESP32 重新连接后只读发现 | 用户重新连接设备；桌面端填写 `esp32:esp32:esp32s3` 与 `/dev/cu.usbmodem101` 后执行只读发现，Arduino CLI 确认 ESP32-S3 与串口，工具链版本可读，结果持久化为 PASSED。 | PASS | 继续准备串口探针 |
| 2026-08-03 | ESP32 串口探针编译 | 桌面端执行“准备串口探针”后执行“编译固件”，使用 ESP32-S3 FQBN、`/dev/cu.usbmodem101`、115200；Arduino CLI 返回 `success true returncode 0`，结果持久化为 PASSED。 | PASS | 继续上传固件 |
| 2026-08-03 | ESP32 串口探针上传 | 桌面端执行“上传固件”，Arduino CLI 返回 `success true returncode 0`，ESP32-S3、`/dev/cu.usbmodem101`、115200 信息与运行证据持久化，状态 PASSED。 | PASS | 继续串口观察 |
| 2026-08-03 | ESP32 串口观察首次执行与重试 | 桌面端执行“串口观察”，8 秒有界采样返回 `success false`、`returncode -15`、`probe_seen false`、`monitor_ended_by_timeout true`；设备仍能被 Arduino CLI 枚举，随后从桌面端重试一次，仍未捕获探针输出。失败状态和重试入口均可见，未伪造硬件通过。 | BLOCKED | 需要确认设备实际串口行为，并继续排查串口占用/启动时序 |
| 2026-08-03 | ESP32-S3 USB CDC 修复版 DMG | 针对 ESP32-S3 原生 USB CDC 默认未启用的问题，源码已将编译/上传选项固定为 `USBMode=hwcdc,CDCOnBoot=cdc`，硬件回归测试 `63 passed`；重新打包并安装 DMG 后，桌面端仍连接远端 `kyrozen.chat`，工作台日志继续出现 `/hardware/state` `500`，导致修复版编译请求无法完成。 | BLOCKED（远端服务未更新） | 先更新远端 API，再从此 DMG 继续物理串口验收 |
| 2026-08-03 | 远端服务更新后 DMG 重试 | 重新从 arm64 DMG 安装并恢复登录；采购中心重新填写 ESP32-S3 FQBN 与 `/dev/cu.usbmodem101` 后执行只读发现，远端工作台成功返回并持久化 `board detected true`、`status PASSED`，确认此前 `/hardware/state` 阻塞已解除。 | PASS | 继续 USB CDC 修复版编译 |
| 2026-08-03 | USB CDC 修复版编译 | 通过安装后的 DMG 执行“准备串口探针”和“编译固件”；ESP32-S3、`/dev/cu.usbmodem101`、115200，Arduino CLI 返回 `success true returncode 0`，状态 PASSED 且持久化。 | PASS | 继续上传固件 |
| 2026-08-03 | USB CDC 修复版上传 | 通过安装后的 DMG 执行“上传固件”；Arduino CLI 返回 `success true returncode 0`，运行记录持久化为 PASSED。 | PASS | 继续串口观察 |
| 2026-08-03 | USB CDC 修复版串口观察 | 通过重新安装的 DMG 执行“串口观察”；结果为 `success true`、`probe_seen true`、`monitor_ended_by_timeout true`、8 秒采样，状态 PASSED。设备真实输出已被探针识别；`returncode -15` 是有界采样主动终止监视器的结果。 | PASS | 继续协议六场景与拔插恢复 |
| 2026-08-03 | 协议交换与六种模拟场景 | 通过桌面端 Fake 模拟器执行版本化 telemetry/ack 交换；normal、offline、reconnect、duplicate、error、version_incompatible 六场景全部返回 PASSED，并持久化 protocol version 1。 | PASS | 进行真实拔插恢复 |
| 2026-08-03 | 串口采样字节流修复回归 | 串口观察首次在 USB CDC 已启用后暴露 `can't concat str to bytes`；修复 `TimeoutExpired` 字节/文本合并并新增回归测试，硬件测试 `64 passed`。重新打包安装后，桌面端串口观察返回 `success true`、`probe_seen true`，真实心跳被捕获。 | FIXED AND PASS | 等待用户确认物理拔插后执行最终确认 |
| 2026-08-03 | 重启后拔插发现恢复 | 退出并重新打开已安装 DMG 后，工作台恢复 37 份项目资料、协议六场景 `ready true`、历史硬件记录；填写 ESP32-S3 与 `/dev/cu.usbmodem101` 执行“拔插后重新发现”，Arduino CLI 返回 `board detected true`、`status PASSED` 并持久化。 | PASS（重新发现） | 仍需用户确认实际拔插与串口行为后保存实物确认 |
| 2026-08-03 | 重启后远端硬件状态回归 | 再次重启并恢复工作台后，桌面日志重新出现 `/api/projects/proj_b9e7dd3f/hardware/state` `500 Internal server error`，同时有多个历史 Artifact 请求超时；界面仍显示历史记录但最终“保存实物确认”禁用。 | ISSUE（远端不稳定） | 通过桌面端刷新重试，必要时修复并重新部署远端 API |
| 2026-08-03 | 远端版本核对 | 只读 SSH 检查确认 `kyrozen-backend.service` 的工作树仍在提交 `605833b`，而本地已推送 `main` 为 `e11d81d`；远端 `/hardware/state` 500 的直接原因是服务未运行最新兼容修复。 | BLOCKED（需部署授权） | 更新远端 main、重启 backend，再继续 DMG 最终验收 |
| 2026-08-04 | 远端服务更新 | 获得用户授权后，远端工作树安全快进到 `558d69c`，重启 `kyrozen-backend.service`；服务新 PID `518907` 启动完成，桌面 WebSocket 已重新连接。 | PASS | 重新刷新已安装 DMG 工作台并继续最终实物确认 |
| 2026-08-04 | 远端更新后重新发现失败 | 在远端修复生效后，已安装 DMG 重新填写 ESP32-S3 与 `/dev/cu.usbmodem101` 并执行“只读发现”；本次返回 `board_detected false`、`status BLOCKED`、`block reason board_not_connected`，与历史 PASSED 记录不混用。 | BLOCKED（当前设备未被 Agent 发现） | 核对本机端口/设备连接后重试 |
| 2026-08-04 | 设备端口复核 | 用户继续请求真实测试后再次检查 `arduino-cli board list`；仍只有 Bluetooth/debug-console，未出现 `/dev/cu.usbmodem101`，因此未启动编译/上传，保持 BLOCKED。 | BLOCKED（设备仍未连接） | 等待 ESP32 重新插入后继续 |
| 2026-08-04 | 新 ESP32（CH340）只读发现 | 用户接入另一型号 ESP32；系统枚举真实端口 `/dev/cu.usbserial-10`，桌面端填写通用 FQBN `esp32:esp32:esp32` 后执行“只读发现”，结果持久化为 `board detected true`、`status PASSED`、`board identification user_confirmed`。该串口桥未被 Arduino CLI 自动识别具体芯片，不能将通用 FQBN 记录误称为自动型号识别。 | PASS（用户确认板卡/端口） | 继续准备并编译串口探针 |
| 2026-08-04 | 新 ESP32 串口探针准备 | 在已安装 DMG 的采购中心，以 `esp32:esp32:esp32` 和 `/dev/cu.usbserial-10` 执行“准备串口探针”；探针文件与 GPIO-free 串口心跳入口生成并持久化，状态 PASSED。 | PASS | 继续编译固件 |
| 2026-08-04 | 新 ESP32 串口探针编译 | 在已安装 DMG 的采购中心执行“编译固件”；Arduino CLI 返回 `success true`、`returncode 0`，运行记录使用 `esp32:esp32:esp32`、`/dev/cu.usbserial-10` 并持久化为 PASSED。 | PASS | 继续上传固件 |
| 2026-08-04 | 新 ESP32 串口探针上传首次尝试 | 在已安装 DMG 的采购中心执行“上传固件”；真实 Arduino CLI 运行返回 `success false`、`returncode 1`，应用分类为 `board_error`，状态持久化为 FAILED，并显示“重试上传”入口。当前不能把通用 ESP32 编译通过等同于该板卡已上传成功。 | ISSUE（真实板卡错误） | 查看上传错误细节，修正板卡/启动模式后有界重试 |
| 2026-08-04 | 新 ESP32 按 N16R8/S3 重新编译 | 将桌面端 FQBN 从通用 `esp32:esp32:esp32` 校正为 `esp32:esp32:esp32s3`，保留真实 CH340 端口 `/dev/cu.usbserial-10`；重新编译返回 `success true`、`returncode 0`，状态 PASSED 并持久化。 | PASS | 重试上传并记录板卡错误是否解除 |
| 2026-08-04 | 新 ESP32-S3 串口探针上传重试 | 使用 `esp32:esp32:esp32s3` 与 `/dev/cu.usbserial-10` 重新编译后，从已安装 DMG 重试上传；仍返回 `success false`、`returncode 1`、`error_category board_error`，状态 FAILED 并保留重试入口。 | BLOCKED（需确认启动模式/芯片实际型号） | 获取本机 Arduino CLI 具体错误，避免继续盲目上传 |
| 2026-08-04 | 新修复版 DMG 重装后项目恢复 | 重建并重装 arm64 DMG 后，登录会话通过默认 Dia 浏览器完成并重新认证；首次打开 ESP32 项目时界面长时间显示“正在准备项目工作区”，本机日志出现一次 `/api/projects/proj_b9e7dd3f/artifacts` `fetch failed`，随后 WebSocket 已恢复连接、Python Agent 已就绪，项目资料仍未及时显示画布。 | ISSUE（安装后启动时序/刷新） | 等待服务稳定后重新打开项目并继续上传修复回归 |
| 2026-08-04 | 安装版新 ESP32 只读发现卡住 | 普通用户在采购中心填写 `esp32:esp32:esp32` 与 `/dev/cu.usbserial-10` 后点击“只读发现设备”；按钮持续禁用超过 40 秒，未出现完成/失败结果，历史硬件记录未被当作当前设备在线。 | ISSUE | 检查安装版 Python Agent 与工具链调用超时，修复后有界重试 |
| 2026-08-04 | 安装版设备发现具体超时 | 重试“只读发现设备”后，最近一次运行记录显示 `success false`、`error_category board_error`，`arduino-cli core list` 为 `Command timed out after 120s`；按钮因此持续禁用。直接在同一台机器运行版本/核心列表均可返回，说明是 Agent 探测调用缺少短时上限，而非将设备误判为在线。 | FAIL | 将工具链发现改为短时有界调用并保证前端 finally 释放忙状态，重打包后复测 |
| 2026-08-04 | 修复版设备发现有界失败回归 | 从新 DMG 安装版本执行同一只读发现；`arduino-cli core list` 超时被限制为 `15s`，界面显示明确 BLOCKED/失败信息并重新启用所有操作按钮，没有再次无限卡住。当前 CH340 端口仍被系统枚举，但本次 Agent 核心列表未返回成功，未把设备误判为通过。 | PASS（失败可恢复） | 继续准备串口探针；保留失败记录与重试入口 |
| 2026-08-04 | 修复版桌面编译首次卡住 | 通过安装版点击“编译固件”后，Arduino CLI 编译进程长时间无输出；只读进程检查发现一个脱离 Kyrozen 的旧 `arduino-cli board list` 进程仍占用同一固件目录，另有本次诊断编译进程。未把旧历史硬件记录当作本次编译成功。 | FAIL | 清理孤立只读/诊断进程后，仅从安装版入口有界重试 |
| 2026-08-04 | 清理后 Arduino CLI 独立编译 | 终止孤立只读/诊断进程后，在同一项目固件目录直接运行 `arduino-cli compile --fqbn esp32:esp32:esp32 .`，20 秒内返回成功，报告 `Sketch uses 260905 bytes (19%)`；该结果仅用于定位 CLI 状态，未替代桌面端硬件证据。 | PASS（诊断） | 通过最新 DMG 的桌面入口重新取得编译回执 |
| 2026-08-04 | 最终修复版 DMG 重新安装与发现回归 | 重新从最新 arm64 DMG 安装，旧备份移入废纸篓；通过默认 Dia 完成登录并恢复已有项目。桌面端首次发现受瞬时 Arduino CLI 核心列表超时影响并显示 BLOCKED，点击原生重试后本地硬件历史追加 `list_ports success true`，确认重试路径最终成功。 | PASS（重试后） | 解锁后继续正式编译、上传、串口观察与拔插恢复 |
| 2026-08-04 | 最终版实物验收被锁屏暂停 | 继续使用 Computer Use 读取安装版工作台时，macOS 已锁定且自动解锁失败；未继续点击、上传或保存“符合”，没有伪造实物通过。 | BLOCKED（需用户手动解锁） | 用户手动解锁 Mac 后从当前安装版继续 |
| 2026-08-04 | 继续验收再次被锁屏阻塞 | 用户请求继续后重新调用 Computer Use，macOS 仍锁定且自动解锁再次失败；未绕过锁屏、未执行 GUI 操作，也未伪造 ESP32 编译/上传/串口或物理确认结果。 | BLOCKED（需用户手动解锁） | 用户解锁 Mac 后再继续安装版实物验收 |
| 2026-08-04 | 解锁后新 ESP32 发现回归 | 解锁 Mac 后从已安装 DMG 重新执行只读发现；真实端口 `/dev/cu.usbserial-10` 已枚举，安装版返回 `success true`、`board detected true`、`board identification user_confirmed`、`status PASSED`。 | PASS | 继续编译、上传和串口观察 |
| 2026-08-04 | 新 ESP32 安装版编译回归 | 以用户确认的 `esp32:esp32:esp32` 和 `/dev/cu.usbserial-10` 从安装版点击“编译固件”；返回 `success true`、`returncode 0`、状态 PASSED。 | PASS | 继续真实上传 |
| 2026-08-04 | 新 ESP32 安装版上传回归 | 从安装版点击“上传固件”；真实 Arduino CLI 返回 `success true`、`returncode 0`，使用 `upload.speed=115200`，状态 PASSED。 | PASS | 继续串口观察 |
| 2026-08-04 | 新 ESP32 安装版串口观察回归 | 从安装版点击“串口观察”；返回 `success true`、`probe_seen true`、8 秒有界采样、状态 PASSED，捕获到真实串口探针心跳。 | PASS | 继续拔插恢复与用户实际行为确认 |
| 2026-08-04 | 新 ESP32 拔插后重新发现回归 | 重新检查本机端口后从安装版点击“拔插后重新发现”；返回 `success true`、`board detected true`、`board identification user_confirmed`、`status PASSED`，端口为 `/dev/cu.usbserial-10`。 | PASS（重新发现） | 仍需用户确认实际串口表现后保存实物确认 |
| 2026-08-04 | 安装版编辑证据分类保存失败 | 编辑已保存证据并在控件中选择“事实”后点击保存；安装版请求仍发送空 `claim_type`，API 返回 422：`String should match pattern '^(fact|opinion|inference|unknown)$'`。原证据 v1 仍保留，未把失败误报为成功。 | FAIL | 修复编辑表单分类状态回填/提交，重打包安装后重试 |
| 2026-08-04 | 修复版 DMG 登录点击元素失效 | 最新 DMG 启动到 GitHub 登录页后，Computer Use 点击登录时返回 `element ID is no longer valid`；尚未把登录或浏览器授权记为成功。 | ISSUE | 刷新应用状态/标识后重试登录 |
| 2026-08-04 | 修复版 DMG bundle 标识定位歧义 | 按 Computer Use 规则刷新应用标识后，`com.kyrozen.desktop` 因 `/Applications/Kyrozen.app` 与两个 release 构建目录共用 bundle 标识而返回 `Ambiguous app identifier`；未删除构建产物，改用明确安装路径继续。 | ISSUE | 使用 `/Applications/Kyrozen.app` 明确定位安装实例 |
| 2026-08-04 | Dia 登录标签切换元素屏外 | Dia 中存在“Kyrozen 登录”标签，但 Computer Use 点击该标签返回 `cannotClickOffscreenElement`；未将标签内容误判为授权完成，改用截图定位。 | ISSUE | 读取可见截图后重试标签切换/授权确认 |
| 2026-08-04 | 安装版额度状态请求失败 | 继续编辑证据时界面新增可见提示 `请求失败（/api/desktop/quota）：fetch failed`，并显示“额度提醒”失败状态；该错误不属于证据保存请求，未改变已保存证据。 | ISSUE | 记录后继续验证证据修复；若刷新后仍出现，再定位桌面端额度请求的网络/后端兼容问题 |
| 2026-08-04 | 修复版编辑证据分类保存回归 | 使用修复版 DMG 重新编辑 v1 证据，将分类从“未知”改为“事实”并保存；界面显示“证据已编辑并保存新版本”，表单清空且刷新流程开始，未再返回 422。 | PASS | 继续验证证据刷新恢复与其余工作中心 |
| 2026-08-04 | 安装版真实市场研究运行 | 使用真实研究问题启动研究；15 秒内界面提示 `/api/projects/proj_b9e7dd3f/research/runs` 请求超时并提供重试入口，但随后持久化状态读取为 `completed`，保存 10 条真实来源/引用，web 覆盖率为 10，provider 状态分别显示 success、failed、rate_limited、unconfigured，未生成替代空数据。 | ISSUE（最终完成但前端超时提示） | 保留来源状态和重试队列证据，继续验证刷新恢复；不把超时提示误判为无结果 |
| 2026-08-04 | 安装版方案 Agent 请求超时 | 决策中心点击“请求方案 Agent 生成三案”后，15 秒后界面提示 `/api/chat` 请求超时并提供重试入口；未生成候选方案，也未进入任何实现阶段。 | ISSUE（无伪造数据） | 保留阻塞状态，继续验证各工作中心写入；方案确认仍禁止绕过门禁 |
| 2026-08-04 | 采购写入期间额度请求超时 | 保存结构化 BOM 后，BOM 写入成功并显示“已保存，刷新后仍可恢复”，同时桌面顶栏独立显示 `/api/desktop/quota` 15 秒超时和额度提醒失败；未影响 BOM 保存。 | ISSUE（写入成功） | 与前述额度接口问题合并跟踪，继续验证刷新恢复和其余中心 |
| 2026-08-04 | 接线表单首次自动化定位失效 | BOM 保存后的刷新改变了接线表单元素索引；沿用旧索引调用 Computer Use 时返回“Cannot set a value for an element that is not settable”，未写入错误数据。重新读取当前状态后按新索引继续。 | RETRY | 每次刷新后重新读取元素状态再操作 |
| 2026-08-04 | Maker 写入后资料刷新超时 | Maker 文字记录写入提示“已保存，刷新后仍可恢复”，随后工作台刷新请求 `/api/projects/proj_b9e7dd3f/artifacts` 超时 15 秒并出现重试入口；当前已有 Maker 结构化步骤仍可读取，未把超时误判为未保存。 | ISSUE（写入成功但刷新慢） | 继续在测试中心验证已有记录和手动重试；记录远端 artifacts 响应不稳定 |
| 2026-08-04 | 测试用例表单首次自动化定位失效 | 沿用刷新前的测试中心元素索引调用 Computer Use，返回 `Cannot set a value for an element that is not settable`；没有写入错误数据。随后重新读取表单状态并正确填充用例。 | RETRY | 每次刷新后重新读取测试表单元素索引 |
| 2026-08-04 | 缺陷回归状态首次更新超时 | 回归操作先显示“回归已通过，缺陷已解决”，随后刷新阶段 `/api/projects/proj_b9e7dd3f/artifacts` 超时并显示“重试：更新缺陷回归状态”；未把短暂提示当作最终持久化完成。 | RETRY | 使用界面提供的重试入口，并再次读取缺陷状态 |
| 2026-08-04 | 测试中心回归读取不一致 | 重试后项目主页显示 `regression closed true`，证明回归门禁已持久化；但再次打开测试中心时显示“暂无可回归的缺陷”，并暂时不展示测试结果列表。未据此判定数据丢失，记录为工作中心读模型刷新不一致。 | ISSUE | 保留主页持久化证据，继续验证其他中心并在重启验收时复核 |
| 2026-08-04 | 验证报告目标用户门禁 | 通过安装版测试中心尝试保存验证报告；接口明确拒绝并提示“最终验证报告至少需要三名不同目标用户的验证记录（每条需包含用户类型和验证任务）”。当前 participant count 为 0，未伪造反馈或报告。 | BLOCKED（正确门禁） | 需要真实三名目标用户反馈后才能重试最终报告 |
| 2026-08-04 | 工作台键盘与窗口布局回归 | 在安装版反馈中心从参与者编号开始连续使用 Tab，焦点按用户类型、任务、完成状态、耗时、满意度、反馈、阻塞点顺序移动；退出全屏后的约 1224×768 窗口仍保持左项目栏、中间反馈表单、右侧进度/Git 区域可见，无水平溢出。 | PASS | 保留 0/3 目标用户门禁，不写入虚构反馈 |
| 2026-08-04 | 重启后登录元素首次失效 | 关闭并重新启动唯一的 `/Applications/Kyrozen.app` 后，启动页“使用 GitHub 登录”按钮首次点击返回 Computer Use `-10005: The element ID is no longer valid`，未执行授权。 | RETRY | 重新读取启动页后按 Dia 浏览器授权流程重试 |
| 2026-08-04 | 重启后项目画布恢复缓慢 | 重启并重新打开项目画布后，登录会话和项目列表已恢复，但项目主页持续显示“项目资料较多，仍在整理中…”超过约 20 秒；未把阶段、Artifact 或工作中心恢复记为通过。 | ISSUE | 在安装版重试刷新项目资料，确认最终持久化状态 |
| 2026-08-04 | 重启后项目资料重试恢复 | 安装版重启后通过“刷新”重试，项目主页最终恢复 98 份资料、55 条硬件运行记录、协议场景 ready、回归 closed；仍保持 physical acceptance false、方案 0、用户反馈 0/3，未越过门禁。 | PASS（重试后） | 继续保留未满足项，不能宣称第二阶段完成 |
| 2026-08-04 | 改进建议重启后列表未显示 | 改进中心保存时显示“改进建议已保存”，重启并恢复 98 份资料后再次打开，建议编辑区恢复但“现有改进建议”列表没有显示该条内容；未把保存提示当作列表读取通过。 | ISSUE | 保留 Artifact 写入证据，继续复核测试/反馈中心读取，不伪造改进状态 |
| 2026-08-04 | 修复版 DMG 项目资料再次长时间整理 | 从刚安装的 DMG 打开项目画布后，主页在约 19 秒内仍显示“项目资料较多，仍在整理中…”，刷新后仍未立即完成；未把加载中的状态当作刷新恢复通过。 | ISSUE | 继续使用安装版刷新并读取改进中心；若可恢复则记录重试通过，否则保留为已知恢复延迟 |
| 2026-08-04 | 改进中心读模型缺少 Artifact 原文 | 重试后项目资料数量恢复为 98，但改进中心仍为空；代码核对发现 `/api/projects/{id}/phase2/workbench` 只返回专用 sections，没有返回最新版本化 Artifact，前端回退读取因此没有数据。 | FIXING | 让统一工作台快照返回项目归属范围内的最新 Artifact，重新部署后用安装版刷新/重启复测 |
| 2026-08-04 | 重装版刷新命中残留测试 API 进程 | 安装版实际默认连接本机 `127.0.0.1:8000`；核对发现该端口由此前测试遗留的 `app.py` 进程占用，工作台刷新期间日志持续出现 Artifact/工作台请求超时，生产后端没有收到对应请求。未把此环境残留误判为产品读回通过。 | RETRY | 定向结束该测试进程，用仓库当前代码和 `.env` 启动唯一本地 API，再从安装版重试 |
| 2026-08-04 | 本地 API 重启期间安装版空白窗口 | 结束残留测试 API 并启动仓库当前 API 后，正在运行的 Kyrozen 安装版渲染区只剩空白 HTML 内容，没有登录、项目或工作台控件；未继续点击空白页面。 | RETRY | 定向重启唯一 `/Applications/Kyrozen.app`，重新读取安装版并恢复登录/项目后再验证 |
| 2026-08-04 | 重启后登录按钮元素首次失效 | 重启后的安装版明确显示 GitHub 登录按钮，但沿用刚读取的元素索引点击时 Computer Use 返回 `-10005: The element ID is no longer valid`；未执行授权。 | RETRY | 重新读取启动页后按 Dia 浏览器授权流程重试 |
| 2026-08-04 | 用户要求暂停真实测试 | 用户开始自行使用 ESP32，要求暂停。已定向退出唯一 `/Applications/Kyrozen.app`、打包版 Python Agent 和我启动的本地 API；未执行串口发现、编译、上传或观察，未删除项目数据、DMG 或硬件文件。 | PAUSED | 等用户完成 ESP32 开发后再从当前提交和报告位置继续；恢复前先重新检查设备端口和安装版状态 |
| 2026-08-04 | 恢复测试后的额度状态请求超时 | 重新登录安装版后，主界面再次显示 `/api/desktop/quota` 请求超时（15 秒）和额度提醒失败；未执行硬件动作，也未把该独立额度请求失败归因于项目数据恢复。 | ISSUE | 保留可见失败状态，继续验证项目画布；不重复提交或伪造额度结果 |
| 2026-08-04 | 恢复后项目工作台认证过期 | 打开项目画布等待约 10 秒后，额度接口显示 `Invalid authentication token ... Signature has expired`，工作台刷新失败并显示重试入口及 `Not authenticated`；未把工作台数据恢复记为通过。 | ISSUE | 按普通用户流程重新通过 Dia/GitHub 授权，再重试工作台读取 |
| 2026-08-04 20:41 | 重新授权后的项目工作台仍未恢复 | 安装版重新通过 Dia 完成 GitHub 回跳后，普通用户点击“项目画布”，约 22 秒内一直显示“项目资料较多，仍在整理中…”，随后工作台关闭回到项目主页；未看到成功内容、明确错误或重试入口，也未执行硬件动作。 | ISSUE | 保留本次可见失败，进行一次有限的项目主页刷新复测；不把加载中状态当作刷新恢复通过 |
| 2026-08-04 20:42 | 重新授权后的项目工作台刷新恢复 | 通过安装版再次点击“项目画布”并等待约 18 秒，工作台恢复显示项目主页、98 份资料、55 条硬件运行记录、研究来源和证据版本链；这次未执行任何硬件动作。 | PASS（重试后） | 保留首次长时间整理作为已知恢复延迟，继续检查改进中心等读模型是否一致 |
| 2026-08-04 20:42 | 修复版 DMG 改进中心再次缺少已保存建议 | 工作台刷新恢复后打开“改进中心”，界面显示“现有改进建议”标题但没有此前保存的建议条目；记录表单为空且操作按钮禁用。未把保存提示当作列表读取通过。 | ISSUE | 保留工作台 Artifact 已读回的证据，继续以真实 UI 记录该中心读模型不一致，不伪造改进状态 |
| 2026-08-04 20:43 | 安装版方案候选请求超时 | 在决策中心按普通用户点击“请求方案 Agent 生成三案”，界面约 15 秒后显示“上次操作失败：请求方案 Agent”和“请求超时（15 秒）：/api/chat”，仍为“尚无方案比较”；未生成或伪造方案。 | ISSUE | 保留失败状态和原生重试入口，不重复点击方案请求，方案确认门禁继续保持未通过 |
| 2026-08-04 20:45 | 改进中心空列表根因修复 | 代码核对确认改进状态接口的空 `{suggestions: []}` 对象遮蔽了版本化 Artifact 回退；前端改为有学习建议时优先显示，否则使用 `improvement_suggestion` Artifact。`npm run lint` 与 `npm run build:renderer` 均通过。 | FIXING | 重新打包安装并按普通用户刷新/重启复测改进中心读回 |
| 2026-08-04 20:50 | 重装前关闭旧安装实例超时 | 通过 Computer Use 点击安装版窗口关闭按钮时返回 `-10005: timeoutReached`；未据此判断退出是否成功，随后改用进程状态和单实例安装检查确认，再继续替换安装包。 | RETRY | 只保留一个 `/Applications/Kyrozen.app`，不删除用户数据或 DMG |
| 2026-08-04 20:51 | 重装命令拼写错误 | 关闭旧实例后执行 DMG 安装命令时，安装复制命令因误写为不可执行的 `dit​​to` 返回 `command not found`；旧安装已安全移入废纸篓，DMG 挂载未损坏，未改变项目数据。 | RETRY | 使用同一挂载点重新执行正确的 `ditto`，完成唯一安装实例恢复后继续复测 |
| 2026-08-04 20:52 | 重装命令第二次拼写错误 | 重试复制 DMG 内容时同一命令仍因不可见字符误写为 `dit​​to`，再次返回 `command not found`；未删除或覆盖新数据，旧安装仍可从废纸篓恢复。 | RETRY | 改用绝对路径 `/usr/bin/ditto` 并先确认挂载点，再继续唯一安装实例复测 |
| 2026-08-04 20:52 | 修复版首次登录点击陈旧引用 | 新安装实例启动后，第一次点击“使用 GitHub 登录”返回 Computer Use `-10005: The element ID is no longer valid`；未判断登录是否发起，随后重新读取窗口并按新索引重试。 | RETRY | 重新读取登录页后再点击，不复用旧的可访问性索引 |
| 2026-08-04 20:53 | 改进中心修复版重装后渲染区空白 | 重装修复版后项目登录会话恢复，点击“项目画布”先显示整理中；等待约 30 秒后安装版 HTML 内容只剩空白，没有项目、工作台或错误提示。未继续点击空白页面，也未执行硬件动作。 | ISSUE | 记录为新的安装版渲染/工作台恢复阻塞；清理唯一安装实例并保留代码改动，继续做构建与发布前审计，不宣称修复已通过 |
| 2026-08-04 20:56 | 工作台降级数据空值防护 | 安装版主日志显示工作台在快照未及时提供原文时回退到多个单 Artifact 请求，失败结果可能以 `null` 进入前端；改进中心的 Artifact 筛选此前直接读取 `artifact.type`，存在渲染区变空白的风险。已增加空值过滤，准备重新构建验证。 | FIXING | 保留服务器响应慢问题为独立阻塞，先确保桌面端失败时可见、可重试而不是空白 |
| 2026-08-04 20:57 | 最终修复版登录点击再次出现陈旧引用 | 最终重装版启动后，第一次点击“使用 GitHub 登录”仍返回 Computer Use `-10005: The element ID is no longer valid`；未判断登录是否发起，准备刷新窗口状态后再按新索引重试。 | RETRY | 只按最新可访问性树操作登录按钮，不复用旧引用 |
| 2026-08-04 21:00 | 空值防护版 DMG 工作台与改进中心恢复 | 重装最终修复版后，项目画布等待约 30 秒恢复，安装版保持可见项目主页而未变白；改进中心真实显示此前保存的 3 个版本化建议（draft/accepted/draft）。本次未执行任何 ESP32 操作。 | PASS（改进中心读回） | 记录服务器快照/单 Artifact 回退仍慢且本次只读回 60 份资料；保留为性能/恢复风险，不宣称全部工作台验收完成 |
| 2026-08-04 21:00 | 重启后工作台长等待调用超时 | 退出并重启最终修复版后，项目画布进入“正在整理项目资料…”；等待约 30 秒的 Computer Use 状态读取调用超时并重置控制内核，未根据超时判断数据是否丢失，也未执行硬件动作。 | RETRY | 重新初始化 Computer Use，只读取一次最终窗口状态；保留服务器慢恢复风险 |
| 2026-08-04 21:01 | 重启后改进中心 Artifact 恢复 | 重新读取安装版后项目主页恢复，改进中心显示已保存的 Desktop Improvement Suggestion version 3（draft）和 version 2（accepted），证明写入内容可跨退出重启恢复；本次仍未执行硬件动作。 | PASS（重启恢复） | 服务器回退请求只返回 30 份资料，旧 version 1 未在本次降级读模型中出现；继续保留完整快照性能风险 |
| 2026-08-04 21:04 | Finder 前往文件夹调用中断 | 用 Computer Use 在 Finder 的“前往”菜单选择“前往文件夹…”准备从最新 DMG 安装时，Computer Use 返回 `native pipe closed before response`；未判断菜单/对话框是否已打开，未改变 Kyrozen 或项目数据。 | RETRY | 重新初始化 Computer Use 后读取 Finder 当前状态，再继续 DMG 安装 |
| 2026-08-04 21:05 | Finder DMG 双击引用失效 | 重读 Finder 状态后仍沿用旧的 DMG 行索引执行双击，Computer Use 返回 `71 is an invalid element ID`；未打开错误目标，未改变 Kyrozen 或项目数据。 | RETRY | 每次操作前输出并使用同一份最新 Finder 可访问性树中的索引 |
| 2026-08-04 21:07 | 新安装版启动调用超时 | Finder 安装完成后，Computer Use 启动 `/Applications/Kyrozen.app` 时返回 `-10005: timeoutReached`；未据此判断应用是否未启动，未执行任何项目或硬件操作。 | RETRY | 先用进程和新的 Computer Use 状态读取确认，再继续登录流程 |
| 2026-08-04 21:07 | 新安装版启动重试仍超时 | 第二次读取 `/Applications/Kyrozen.app` 仍返回 Computer Use `-10005: timeoutReached`，进程检查未发现 Kyrozen 实例；未执行项目或硬件操作。 | RETRY | 重新初始化 Computer Use 后再做一次启动读取，若仍失败则改用安装版可见 UI/进程证据定位，不伪造登录通过 |
| 2026-08-04 21:08 | Computer Use 重置后启动仍超时 | 重置并重新初始化 Computer Use 后，第三次读取 `/Applications/Kyrozen.app` 仍返回 `-10005: timeoutReached`；进程仍未启动 Kyrozen，当前登录/工作台流程尚未开始。 | ISSUE | 暂停重复启动调用，先核对 Finder 安装副本、签名/架构和系统启动日志，再决定修复或有限重试 |
| 2026-08-04 21:09 | Finder 合并复制导致安装包签名失效 | 只读检查发现 `/Applications/Kyrozen.app` 的 sealed resource 校验失败，新增的 Python `__pycache__` 文件来自旧安装目录；Finder 拖拽没有替换整个旧目录而是合并复制，导致安装版无法启动。 | FIXING | 通过 Finder 将旧 `/Applications/Kyrozen.app` 移入废纸篓，再从已挂载 DMG 复制到空的 Applications 目录；保留用户数据 |
| 2026-08-04 21:09 | Finder 旧应用图标屏外 | Computer Use 点击 Finder 可访问性树中的 Kyrozen 图标返回 `cannotClickOffscreenElement`；未删除或修改旧安装。 | RETRY | 通过 Finder 列表视图或搜索让目标进入可见区域后，再使用文件菜单移入废纸篓 |
| 2026-08-04 | Dia 授权标签再次屏外 | Dia 已有“Kyrozen 登录”标签，但 Computer Use 直接点击该标签返回 `cannotClickOffscreenElement`；未误判为授权完成。 | RETRY | 使用 Dia 当前可见页面的键盘标签切换或重新打开授权页后继续 |
| 2026-08-04 | Dia 键盘标签切换调用超时 | 尝试用 Computer Use 的 `CTRL+TAB` 从当前 Dia 页面切换到授权标签时调用长时间无返回，已终止该调用；未改变 Kyrozen 或 ESP32 状态。 | RETRY | 重新读取 Dia 可见控件，采用打开新授权标签的方式恢复登录 |
| 2026-08-04 | Dia 组合键标签切换兼容性 | 重试 `ctrl+tab` 后 Dia 先切换到 Good Samaritan 标签，随后 Computer Use 返回 `keyNotFound("tab")`；未改变 Kyrozen 或 ESP32 状态。 | RETRY | 不再依赖组合键，使用 Dia 当前标签栏可见路径或重新打开授权页 |
| 2026-08-04 21:12 | Finder 文件菜单调用接口错误 | 按 Computer Use 技能尝试打开 Finder 的 File 菜单时，调用返回 `sky.perform_primary_action is not a function`；未改变安装目录或项目数据。 | RETRY | 重新读取技能可用操作接口，继续使用 Finder UI 完成可恢复的旧应用清理 |
| 2026-08-04 21:15 | 干净签名安装版启动仍超时 | Finder 复制/粘贴到空的 Applications 后，`codesign --verify --deep --strict` 已通过，但 Computer Use 读取 `/Applications/Kyrozen.app` 仍返回 `-10005: timeoutReached`；尚未执行登录、项目或硬件动作。 | ISSUE | 先用进程、系统启动日志和 Electron 打包内容定位启动阻塞；不把签名通过误记为用户启动通过 |
| 2026-08-04 21:16 | Kyrozen Bundle ID 多副本歧义 | 读取当前运行界面时，Computer Use 拒绝使用 `com.kyrozen.desktop`，提示 `/Applications`、构建目录和已挂载 DMG 共 4 个相同 Bundle ID；未执行项目或硬件动作。 | RETRY | 使用完整应用路径定位唯一 `/Applications/Kyrozen.app`，并清理挂载 DMG 的残留运行进程后再启动 |
| 2026-08-04 21:17 | 挂载版关闭后进程未退出 | 点击挂载 DMG 版 Kyrozen 的窗口关闭按钮后，进程仍留在 `/Volumes/Kyrozen 0.1.0-arm64/Kyrozen.app`；再次读取其界面返回 `-10005: timeoutReached`，未执行项目或硬件动作。 | ISSUE | 通过 Kyrozen 菜单退出或系统进程状态确认后再启动 Applications 副本；不重复打开多个实例 |
| 2026-08-04 21:18 | 唯一安装版签名与启动通过 | 清空 `/Applications/Kyrozen.app` 后由 DMG 通过 Finder 复制/粘贴安装；`codesign --verify --deep --strict` 通过，终止挂载版残留进程后，Computer Use 成功启动 `/Applications/Kyrozen.app` 并显示 GitHub 登录页。 | PASS | 继续按普通用户流程在 Dia 完成授权；保持只运行一个 Applications 副本 |
| 2026-08-04 21:18 | Applications 安装版登录会话与工作台恢复 | 安装版点击 GitHub 登录后恢复已有授权会话，项目画布等待约 20 秒后显示项目主页、Problem Brief 证据状态、10 条研究来源、7 个工作中心和第二阶段缺失条件；未执行 ESP32 操作。 | PASS（读取恢复） | 继续普通用户逐一打开七个中心，验证刷新与失败重试；不把现有历史硬件记录当作本轮物理验收 |
| 2026-08-04 21:19 | 方案 Agent 真实请求超时 | 普通用户在决策中心点击“请求方案 Agent 生成三案”，等待 15 秒后看到“上次操作失败：请求方案 Agent”和“请求超时（15 秒）：/api/chat”，仍无方案比较；未生成或伪造候选方案。 | ISSUE | 保留界面重试入口和未确认门禁；继续测试其它工作中心，后续定位 `/api/chat` 超时并修复/回归 |
| 2026-08-04 21:20 | 方案 Agent 界面重试仍超时 | 按界面提供的“重试：请求方案 Agent”再次执行，第二次仍显示 `请求超时（15 秒）：/api/chat`，没有生成方案；同时项目进度从 7% 变为 6%，出现“硬件开发 Agent 处理”和“没有找到可执行的测试目录或测试脚本”文本，需保留为真实回归异常。 | ISSUE | 不继续重复点击；继续检查其它中心，并定位方案 Agent 请求超时/阶段读模型变化 |
| 2026-08-04 21:20 | 测试报告追加补丁上下文不匹配 | 两次尝试用过时的报告行文本追加方案重试结果，`apply_patch` 返回 verification failed；未修改源代码或测试数据，随后读取实际行内容并完成记录。 | RETRY | 后续追加前先读取报告尾部，避免复用已变化的行文本 |
| 2026-08-04 21:22 | DMG 安装版七个工作中心读取通过 | 从 Applications 安装版依次打开项目主页、决策、采购、Maker、测试、改进和反馈中心；七个中心均有真实内容或明确空状态，测试中心显示失败→缺陷→修复→回归通过，改进中心恢复 version 3/version 2。未执行硬件按钮。 | PASS（读取） | 继续记录刷新耗时、反馈数据不足和方案请求阻塞；不伪造三名用户或候选方案 |
| 2026-08-04 21:22 | 普通用户反馈验收条件未满足 | 反馈中心显示 `participant count 0 completed count 0 minimum participants met false`，表单可填写但没有真实参与者数据；最终验证报告条件因此仍不能通过。 | BLOCKED | 等待真实目标用户反馈后再保存，不用测试数据冒充用户 |
| 2026-08-04 21:23 | 工作台刷新恢复但延迟且快照数量波动 | 点击项目主页“刷新”后约 35 秒恢复可读，Problem Brief/研究/工作中心仍可见；资料计数从刷新前 71 变为 65，说明服务器快照/单 Artifact 回退存在延迟或不一致风险。 | ISSUE | 将刷新读回视为可恢复但不稳定；继续保留重试入口和性能阻塞，不宣称完整恢复通过 |
| 2026-08-04 21:24 | 远程容器诊断命令缺少 rg | 通过 SSH 读取健康容器日志时，远程镜像没有 `rg`，过滤命令返回 `bash: rg: command not found`；未修改远程服务。 | RETRY | 改用 POSIX `grep` 只读筛选日志，不执行破坏性远程操作 |
| 2026-08-04 21:26 | 方案请求超时根因确认 | 安装版 `main.log` 显示点击时 WebSocket 已为 OPEN，但 `/api/chat` 在云端先构建大型项目上下文，15 秒客户端超时后约 5 秒才收到 `assign_task`；因此界面报错但任务仍异步执行，造成重复提交风险。 | FIXING | 让决策中心显式发送 `planning` 模式，并在服务端规划请求构建大型上下文前优先派发在线桌面 Agent；继续保留真实失败状态 |
| 2026-08-04 21:27 | 方案超时修复静态验证 | 已修改桌面 IPC/preload 类型、决策中心模式标记和服务端规划早期派发逻辑；Python 规划测试 1 项通过，桌面 lint、renderer build、unit 12 项和 `git diff --check` 通过。 | FIXING | 部署服务端改动、重新打包并用 Applications DMG 回归方案请求；不执行 ESP32 |
| 2026-08-04 21:28 | 远程部署目录探查连接中断 | 通过 SSH 读取远端仓库目录时，服务器主动关闭连接；未修改远端文件或服务。 | RETRY | 使用已知服务容器运行方式和更短的只读命令重试，必要时等待 SSH 服务恢复 |
| 2026-08-04 21:28 | 远程 SSH 重试仍被服务器关闭 | 使用短的 `pwd; ls -la` 只读命令再次连接，服务器仍返回 `Connection closed by 34.4.106.253 port 22`；远端未修改。 | RETRY | 不反复轰击 SSH；先本地继续打包，稍后进行一次有限远程连接复测 |
| 2026-08-04 21:34 | Finder 菜单索引在删除旧版后失效 | 删除旧版 Kyrozen 后继续使用旧元素索引 `247` 定位 Go 菜单，Computer Use 返回 `-10005: 247 is an invalid element ID`；未改变新 DMG 或项目数据。 | RETRY | 每次 UI 动作前重新读取 Finder 状态；先记录本次索引错误再继续 |
| 2026-08-04 21:34 | 测试报告追加补丁再次上下文不匹配 | 追加 Finder 索引错误时使用了不存在的旧报告行，`apply_patch` 返回 verification failed；未修改源代码或应用安装。 | RETRY | 读取报告尾部后按实际最后一行追加 |
| 2026-08-04 21:36 | 最新安装版登录按钮元素失效 | `/Applications/Kyrozen.app` 已启动并显示 GitHub 登录页；首次点击登录按钮时 Computer Use 返回 `-10005: The element ID is no longer valid`，未发送登录数据。 | RETRY | 重新读取安装版窗口状态后使用新索引重试 |
| 2026-08-04 21:39 | 远程部署命令编排语法错误 | 发起远端拉取命令时本地工具编排出现一次 JavaScript `SyntaxError: Unexpected token '?'`；未执行远程命令或修改远端状态。 | RETRY | 立即改用短命令执行安全的 `git pull --rebase --autostash` |
| 2026-08-04 21:41 | 远端 backend 重启会话中断 | 代码已快进至 `ea10f63`；执行 `sudo -n systemctl restart kyrozen-backend.service` 后 SSH 返回 `Connection closed by 34.4.106.253 port 22`，不能据此确认服务是否重启完成。 | RETRY | 先执行只读 `systemctl is-active`/PID/日志检查；若未生效，只有限重启一次 |
| 2026-08-04 21:42 | 远端重启后复核会话再次中断 | 第二次重启命令本身已无输出返回；随后复核版本、服务 PID 和容器状态时 SSH 再次被服务器关闭，当前仍不能凭该次连接确认所有状态。 | RETRY | 进行一次短只读复核；若仍不稳定，以服务可达性和本地真实回归结果分别记录，不再连续重启 |
| 2026-08-04 21:39 | 最新安装版工作台出现会员接口 502 | 进入项目画布后顶部显示 `HTTP 502`，会员权益从开发者无限制变为错误状态；项目工作台同时显示“正在整理项目资料…/项目资料较多，仍在整理中…”，需要观察是否能恢复。 | ISSUE | 等待一次有限的资料加载周期；不把界面可见但未完成的工作台当作读取通过 |
| 2026-08-04 21:40 | 方案请求即时派发但本地 Agent 路由错误 | 修复部署后点击“请求方案 Agent 生成三案”不再等待 15 秒，界面即时显示“方案 Agent 已开始处理”；但本地 `routing_log.jsonl` 将该 planning 任务路由成“问题探索 Agent”，因为陈旧 `problem_discovery` 阶段覆盖了显式模式，方案仍未生成。 | ISSUE | 保留显式 planning 模式，禁止本地阶段同步和自然语言阶段推进行为清空已明确的派发模式；重新打包回归 |
| 2026-08-04 21:44 | planning 路由修复静态验证 | 本地阶段同步不再清空显式派发模式；AgentRouter 对决策中心 `planning` 请求优先于 ESP32 文本意图。`tests/test_router.py` 与 `tests/test_desktop_stage_intent.py` 共 41 项通过，Python 编译和 `git diff --check` 通过。 | PASS（静态） | 重新打包 DMG，在干净 Applications 安装版中再次点击方案请求并观察路由结果 |
| 2026-08-04 21:48 | DMG 构建完成后的进程轮询错误 | `npm run build -- --mac --arm64` 已输出 DMG 和 blockmap；随后继续轮询已自然退出的会话，工具返回 `write_stdin failed: Unknown process id 31885`。 | RETRY | 直接检查产物、签名和安装包内容，不把轮询错误误记为构建失败 |
| 2026-08-04 21:47 | 方案 Agent 路由正确但被确定性测试分支截获 | 修复版 DMG 中请求即时派发，界面显示“当前由 产品定义 Agent 处理”，但随后仍出现“没有找到可执行的测试目录或测试脚本”；本地执行逻辑按消息中包含“验证/测试”触发测试证据路径，误伤了方案提示中的比较维度。 | ISSUE | 仅当统一路由结果为 `testing` 时运行确定性测试证据路径；规划任务交给产品规划 Agent；重新打包回归 |
| 2026-08-04 21:49 | 测试分支修复静态验证 | 确定性测试证据路径已限定为 `decision.mode == testing`；路由/阶段 41 项测试通过，Python 编译和 `git diff --check` 通过。 | PASS（静态） | 重新构建并安装最后一个 DMG，验证方案请求不再出现测试目录误报 |
| 2026-08-04 21:50 | 最终 DMG 构建会话轮询错误 | 构建日志已输出 DMG blockmap；继续轮询已自然退出的构建会话时工具返回 `write_stdin failed: Unknown process id 32611`。未据此判断构建失败，也未改变安装或项目数据。 | RETRY | 直接检查 DMG 文件、签名和应用包内容，再进行唯一安装版回归 |
| 2026-08-04 21:52 | Finder 复制快捷键名称兼容错误 | 选中最终 DMG 中的 Kyrozen.app 后，Computer Use 使用 `SUPER+C` 返回 `keyNotFound("SUPER")`，复制动作未执行，未改变安装目录或项目数据。 | RETRY | 改用 macOS 支持的 `CMD+C`，继续通过 Finder 完成唯一安装 |
| 2026-08-04 21:52 | Finder CMD 复制快捷键仍不受运行时识别 | 重试复制时 Computer Use 使用 `CMD+C` 仍返回 `keyNotFound("CMD")`，复制动作未执行，未改变安装目录或项目数据。 | RETRY | 通过当前 Finder 的 Edit 菜单选择 Copy，继续唯一安装 |
| 2026-08-04 21:53 | Finder 菜单状态偏移与取消点击失败 | 依据上一份状态树点击 Edit 后实际打开 File 菜单；按该菜单新树点击取消项又返回 `cannotClickOffscreenElement`。复制未执行，未改变安装目录或项目数据。 | RETRY | 重新读取 Finder 状态并使用可见菜单文本对应的最新索引，不复用旧树索引 |
| 2026-08-04 21:54 | 最终安装版登录按钮陈旧引用 | 最终 DMG 复制安装并通过签名校验后，第一次点击“使用 GitHub 登录”返回 Computer Use `The element ID is no longer valid`，未发送授权请求。 | RETRY | 重新读取 Applications 安装版状态后使用新索引重试，不误判登录状态 |
| 2026-08-04 21:55 | 最终安装版项目画布按钮无响应 | 登录恢复后，按最新可访问性树点击“项目画布”两次，并按当前截图坐标点击一次，界面均停留在项目主视图，工作台未打开；未执行硬件动作。 | ISSUE | 读取安装版日志、渲染进程和当前源码事件绑定，定位普通用户点击无响应原因后修复并回归 |
| 2026-08-04 21:59 | 最终安装版普通用户请求超时 | 在聊天输入框输入“请告诉我这个项目当前最重要的下一步”并按 Return 真实提交；等待后显示 `发送失败：请求超时（15 秒）：/api/chat`，同时提供“重试”入口，未伪造 Agent 回答。 | ISSUE | 保留失败状态和重试入口；继续用键盘导航检查工作台入口，并将普通聊天超时作为远端上下文性能阻塞 |
| 2026-08-04 22:00 | 异步 Agent 结果与普通问题串线 | 同一普通问题在超时后被异步回写为“我检查了当前项目，但没有找到可执行的测试目录或测试脚本”，与“当前最重要的下一步”不匹配；界面仍未打开工作台，也未执行硬件动作。 | ISSUE | 重启唯一 Applications 实例清理焦点/异步状态；保留为 Agent 路由与超时后的迟到结果隔离问题 |
| 2026-08-04 22:00 | 重启恢复版登录按钮陈旧引用 | 退出并重新启动最终 Applications 安装版后，首次点击“使用 GitHub 登录”返回 Computer Use `The element ID is no longer valid`，未发送授权数据。 | RETRY | 重新读取登录页状态后按最新索引重试，不把第一次失败当成授权失败 |
| 2026-08-04 22:01 | 键盘回退快捷键兼容错误 | 从最终安装版当前焦点尝试使用 `shift+tab` 返回上一个控件时，Computer Use 返回 `keyNotFound("tab")`；未改变应用或项目数据。 | RETRY | 改用正向 Tab 导航并逐次读取焦点，不继续猜测组合键名称 |
| 2026-08-04 22:05 | 最终版方案请求仍失败且旧任务结果迟到回写 | 在最终 `/Applications/Kyrozen.app` 决策中心按普通用户点击“请求方案 Agent 生成三案”；界面即时进入产品定义 Agent，但约 20 秒后工作台显示 `/api/projects/proj_b9e7dd3f/decisions` `fetch failed`，并将此前超时任务的“没有找到可执行的测试目录或测试脚本”再次显示为聊天失败结果。没有生成或伪造方案。 | ISSUE | 停止重复方案请求；保留请求失败、旧任务结果隔离和决策读模型失败作为最终阻塞，修复后需重新打包并从唯一安装版复测 |
| 2026-08-04 22:08 | 方案异步刷新与迟到任务结果修复 | 桌面端方案请求在已派发任务时不再立即并发刷新整个工作台，改由 Agent 回执后刷新；主进程只接受当前活动任务的 `task_result`，忽略超时/重启后的旧任务结果并写入日志。 | FIXING | 运行桌面 lint、renderer build 和 Python 回归；重新打包后用唯一安装版重试方案请求 |
| 2026-08-04 22:08 | 系统 Python 回归环境缺少依赖 | 使用系统 `python3 -m pytest tests/test_router.py tests/test_desktop_stage_intent.py -q` 时，`tests/conftest.py` 导入 `supabase` 失败（`ModuleNotFoundError`）；未把环境缺失误判为代码测试失败。 | RETRY | 改用仓库已有虚拟环境运行同一组测试，若环境不存在则只报告未执行 |
| 2026-08-04 22:09 | Finder 移到废纸篓快捷键兼容错误 | 选中 `/Applications/Kyrozen.app` 后使用 Computer Use `super+delete`，运行时返回 `keyNotFound("delete")`；旧安装仍在原位置，未删除或覆盖任何文件。 | RETRY | 改用 Finder File 菜单中的“移到废纸篓”，继续保持唯一 Applications 安装 |
| 2026-08-04 22:11 | 最新安装版登录按钮陈旧引用 | 最新 DMG 复制到 `/Applications` 并启动后，在已读取登录页索引上点击“使用 GitHub 登录”再次返回 Computer Use `-10005: The element ID is no longer valid`；未发送授权。 | RETRY | 重新读取安装版登录页后按新索引重试，继续使用 Dia 完成普通用户授权 |
| 2026-08-04 22:12 | 最终修复版方案异步回归 | 最新 Applications 安装版通过项目画布进入决策中心并点击方案请求；请求立即显示“正在理解你的需求”，20 秒后显示“当前由 产品定义 Agent 处理”和“方案 Agent 已开始处理”，没有新的 `/api/projects/.../decisions` 读取失败，也没有新增测试目录误报。历史聊天仍显示此前旧错误，但未被新的任务结果再次追加。 | PASS（异步隔离） | 方案仍因真实研究/Problem Brief 门禁未形成三案；继续做重启后工作台与唯一安装清理，不宣称方案闭环完成 |
| 2026-08-04 22:13 | 重启恢复登录索引再次失效 | 退出并从 Applications 重启最新安装版后，登录页首次按刚读取的“使用 GitHub 登录”索引点击返回 Computer Use `-10005: The element ID is no longer valid`；未发送授权。 | RETRY | 重新读取登录页后按新索引重试，确认会话和项目画布恢复 |
| 2026-08-04 22:14 | 最新安装版重启后项目状态恢复 | 重读安装版状态后会话自动恢复到项目主页；再次通过“项目画布”进入工作台，约 30 秒后恢复项目主页、方案候选区、已形成资料和 55 条历史硬件运行记录。方案仍为 0，硬件实物门禁仍未满足；未执行 ESP32 操作。 | PASS（重启恢复） | 保留服务器资料整理延迟和未满足 Phase 2 门禁，完成清理、提交和发布审计 |
| 2026-08-04 22:15 | 安装副本签名审计失败 | 最终安装版退出后对 `/Applications/Kyrozen.app` 执行 `codesign --verify --deep --strict`，返回 `a sealed resource is missing or invalid`；DMG 构建目录中的 arm64 App 先前已通过校验。未继续使用或发布该不合格安装副本。 | BLOCKED | 比较构建包、DMG 和 Applications 副本的资源/扩展属性，修复安装完整性后再做一次签名和启动审计 |
| 2026-08-04 22:16 | 签名失效根因与修复 | 对比构建包和退出后的安装副本发现，运行时在签名 Resources 下新增 `kyrozen/**/__pycache__`；已让打包 Python Agent 设置 `PYTHONDONTWRITEBYTECODE=1`，避免运行污染 App sealed resources。 | FIXING | 重新构建、唯一安装、启动/退出并复核构建包与安装副本签名 |
| 2026-08-04 22:18 | 最终签名修复安装被锁屏阻塞 | 新 DMG 已构建并通过构建目录签名校验；准备在 Finder 移入旧安装并复制新 DMG 时，Computer Use 返回“Mac is locked and automatic unlock could not unlock it”，未改变 `/Applications`、未执行绕过锁屏的 UI 操作。 | BLOCKED | 用户解锁 Mac 后，从 Finder 完成唯一安装，再启动/退出并执行 `/Applications/Kyrozen.app` sealed-resource 校验 |
| 2026-08-04 22:19 | 签名失效副本与 DMG 安全清理 | 因 Mac 仍锁定，未继续 UI 安装；已将签名失效的 `/Applications/Kyrozen.app` 可恢复移入废纸篓，并卸载唯一挂载的最终 DMG。未清空废纸篓、未删除项目数据。 | CLEANUP | 用户解锁后从新 DMG 重新完成一次 Finder 安装和签名/启动/退出复核 |
| 2026-08-09 | 远程 HEAD 只读复核 DNS 失败 | 执行 `git ls-remote origin refs/heads/main` 时返回 `Could not resolve host: github.com`；未修改远程或本地代码。 | RETRY | 继续本地 DMG/Computer Use 验收；网络恢复后再复核远程 HEAD |
| 2026-08-09 | 最新 DMG 首次挂载失败 | Finder 已解锁，但执行 `hdiutil attach -nobrowse desktop/release/Kyrozen-0.1.0-arm64.dmg` 返回 `Device not configured`；未开始安装，未改变 Applications。 | RETRY | 只读校验 DMG/磁盘状态后进行一次有限挂载重试 |
| 2026-08-09 | macOS 磁盘管理框架暂不可用 | 只读执行 `hdiutil imageinfo` 同样返回 `Device not configured`，`diskutil list` 返回无法使用 DiskManagement framework；DMG 哈希、大小和构建 App 签名校验仍通过。未修改磁盘或安装目录。 | RETRY | 以用户授权的非破坏性方式重试磁盘管理命令；若系统框架仍不可用，保留为环境阻塞 |
| 2026-08-09 | 最新安装版登录后额度读取超时 | Finder 安装并启动后，GitHub 会话恢复到 `本地项目 proj_b9e`；主界面同时显示 `请求超时（15 秒）：/api/desktop/quota`，未伪造会员/额度状态，也未执行硬件动作。 | ISSUE | 保留额度接口失败，继续验证项目画布与核心 Phase 2 门禁 |
| 2026-08-09 | 最新安装版项目画布首次索引失效 | 登录恢复后的第一次“项目画布”点击使用刚读取的索引时，Computer Use 返回 `-10005: The element ID is no longer valid`，工作台未打开，未改变项目数据。 | RETRY | 重新读取安装版可访问性树后按新索引重试 |
| 2026-08-09 | Dia 登录标签 AX 点击不支持 | 重新登录打开 Dia 的 `Kyzrozen 登录` 标签后，按最新可访问性树点击该标签返回 `AXError.actionUnsupported`；未提交授权、未输入凭据。 | RETRY | 读取 Dia 截图/地址栏状态，必要时用可见坐标或让用户接管授权确认 |
| 2026-08-09 | OAuth 回调后登录未完成 | Dia 中确认打开 `kyrozen://auth/login` 协议链接后，安装版仍显示 `GitHub 登录尚未完成，请检查浏览器提示后重试。`；未伪造登录成功，也未执行硬件动作。 | BLOCKED | 检查 Dia 当前回调页面；若出现 GitHub 凭据输入或授权确认，立即交由用户完成 |
| 2026-08-09 | 项目双击动作未获 Computer Use 批准 | 尝试用双击打开已选项目时，Computer Use 返回 `Computer Use was not approved to use Kyrozen`；未改变项目数据。 | RETRY | 改用普通单击和键盘导航复测，不重复请求双击动作 |
| 2026-08-09 | 多个 Kyrozen 包导致 bundle 标识歧义 | 使用 `com.kyrozen.desktop` 操作时，Computer Use 发现 `/Applications`、构建目录和已挂载 DMG 共多个同 bundle 应用，拒绝执行；未改变项目数据。 | RETRY | 始终使用 `/Applications/Kyrozen.app` 精确目标，验收结束卸载 DMG 并保留唯一 Applications 安装 |
| 2026-08-09 | 决策中心标签动作未获 Computer Use 批准 | 在项目画布中尝试打开“决策中心”标签时，Computer Use 返回 `Computer Use was not approved to use Kyrozen`；未改变方案或项目数据。 | RETRY | 先单独刷新安装版状态，再用最新标签索引重试 |
| 2026-08-09 | 最新安装版方案请求后仍出现错误聊天回写 | 真实点击“请求方案 Agent 生成三案”后，界面显示已开始处理且未生成方案；聊天区又显示“发送失败：我检查了当前项目，但没有找到可执行的测试目录或测试脚本。”，与方案请求不匹配，未伪造方案。 | ISSUE | 保留方案 0 和错误状态；继续验证其余工作中心，方案确认前不执行硬件流程 |
| 2026-08-09 | 采购中心标签动作未获 Computer Use 批准 | 在项目画布中尝试打开“采购中心”标签时，Computer Use 返回 `Computer Use was not approved to use Kyrozen`；未改变 BOM 或采购状态。 | RETRY | 单独刷新状态后按最新标签索引重试 |
| 2026-08-09 | 真实市场研究运行部分失败并进入重试 | 普通用户输入“ESP32 串口通信方案”并启动研究后，安装版真实显示“上次操作失败：重试研究运行”；18 条来源中 web success，GitHub/community/Reddit failed，论文 rate_limited，专利/众筹 unconfigured，且重试队列仍有 rate-limited 项；未生成替代来源或方案。 | ISSUE | 保留来源级失败、限流、未配置和重试状态；方案候选仍为 0，不能确认方案或进入硬件流程 |
| 2026-08-09 | 研究重试完成但外部来源仍不完整 | 点击“重试研究运行”后，安装版显示“研究运行已完成并保存来源状态”，来源增至 19；Web 成功，GitHub/community/Reddit 失败，论文限流，专利/众筹未配置，重试队列仍保留限流项。重试期间额度接口另显示 `/api/desktop/quota` `fetch failed`；未生成方案。 | PASS（恢复路径）/ ISSUE（覆盖不足） | 不伪造缺失来源；保持方案门禁，等待真实来源覆盖和 Problem Brief |
| 2026-08-09 | 最新安装版问题探索请求超时并误路由 | 用普通用户短句“我想让 ESP32 通过 USB 串口输出心跳，并确认拔插后能恢复；先帮我明确目标用户和最小可验证问题。”提交后，界面显示 `请求超时（15 秒）：/api/chat`、重试入口；同时将当前处理者显示为“硬件开发 Agent”，未形成 Problem Brief。 | ISSUE | 保留超时和可重试状态；不把硬件 Agent 回显当作问题探索完成，方案与实物门禁继续保持阻塞 |
| 2026-08-09 | 修复版 DMG 构建首次因 DNS 失败 | 路由修复与回归测试已通过，但 `npm run build -- --mac --arm64` 在 electron-builder 打包阶段请求 `github.com` 时返回 `getaddrinfo ENOTFOUND github.com`；未把网络失败误判为代码构建失败。 | RETRY | 网络恢复后重试同一构建，不改变安装目录或项目数据 |
| 2026-08-09 | 退出旧安装版快捷键未获 Computer Use 批准 | 准备安装修复版前用 `super+q` 退出当前安装版时，Computer Use 返回 `Computer Use was not approved to use Kyrozen`；未改变项目数据。 | RETRY | 使用窗口关闭按钮退出，再卸载旧 DMG 并完成唯一安装 |
| 2026-08-09 | 旧安装版关闭后 Computer Use 状态超时 | 点击窗口关闭按钮后，读取 Kyrozen 状态返回 Computer Use `-10005: timeoutReached`；未修改项目数据。 | RETRY | 用应用列表和系统级只读检查确认实例，再进行 DMG 清理 |
| 2026-08-09 | 修复版首次登录按钮索引失效 | 新 DMG 唯一安装版启动并显示 GitHub 登录页；按刚读取的按钮索引点击时 Computer Use 返回 `-10005: The element ID is no longer valid`，未发送授权。 | RETRY | 重新读取安装版状态后按新索引重试 |
| 2026-08-09 | 修复版路由正确但迟到结果仍串线 | 修复版安装后重新发送含 ESP32 关键词的短问题；界面正确显示“问题探索 Agent 处理”，但约 35 秒后仍回写“我检查了当前项目，但没有找到可执行的测试目录或测试脚本”，与最新问题不匹配。未形成 Problem Brief，也未执行硬件。 | ISSUE | 路由门禁修复已验证；继续隔离跨任务迟到结果，未把错误回写当作问题探索成功 |
| 2026-08-09 | 问题探索误触测试兜底根因与修复 | 发现 Python Agent 在任务完成后无条件调用测试证据兜底；含“可验证”的问题探索消息会被错误返回“没有测试目录”。已将兜底限定为 `decision.mode == testing`；路由/桌面 Agent 回归 63 项通过。 | FIXING | 重新构建并安装 DMG，复测含“可验证”关键词的问题探索消息，确认不再出现测试目录误报 |
| 2026-08-09 | 第二个修复版安装被锁屏阻塞 | 最新 DMG 已完成构建，旧版已可恢复移入废纸篓、旧 DMG 已卸载并重新挂载；准备通过 Finder 复制最新 Kyrozen.app 时，Computer Use 返回“Mac is locked and automatic unlock could not unlock it”。未继续安装，未改变项目数据。 | BLOCKED | 用户手动解锁 Mac 后，从当前 Finder 状态继续唯一安装和回归；不重复挂载或保留多个安装副本 |
| 2026-08-09 | 解锁后续验收仍未获得桌面控制权 | 新一轮从当前 Finder 恢复时，Computer Use 再次返回“Mac is locked and automatic unlock could not unlock it”；Applications 仍无 Kyrozen，DMG 仍保持单一挂载，未修改项目数据。 | BLOCKED | 用户手动解锁 Mac 后回复，继续当前 Finder 安装，不重新生成或挂载副本 |
| 2026-08-09 | 连续复核仍被锁屏阻塞 | 第三次从当前验收状态读取 Finder 时，Computer Use 仍返回“Mac is locked and automatic unlock could not unlock it”；未执行任何安装、登录或项目写入。 | BLOCKED | 需要用户先手动解锁 Mac；解锁后恢复任务将从当前唯一 DMG 挂载继续 |
| 2026-08-09 | 最新修复版登录按钮首次索引失效 | Mac 解锁后完成最新 DMG 唯一安装并通过签名校验；首次按登录页索引点击“使用 GitHub 登录”时 Computer Use 返回 `-10005: The element ID is no longer valid`，未发送授权。 | RETRY | 重新读取最新安装版状态后按新索引重试 |
| 2026-08-09 | 最新修复版问题探索不再误触测试但 AI 服务失败 | 最新 DMG 安装后提交含“可验证”关键词的问题探索消息；界面保持“问题探索 Agent 处理”，不再返回测试目录误报，但最终显示“AI 服务暂时不可用，请稍后重试”，未形成 Problem Brief。 | ISSUE | 保留真实失败和重试入口；继续进行一次有限重试并检查模型服务可达性 |
| 2026-08-09 | 问题探索重试等待编排语法错误 | 点击界面“重试”后，等待并读取状态的本地工具编排出现一次 JavaScript `SyntaxError: Unexpected token ':'`；未改变应用或项目数据，重试任务仍在运行。 | RETRY | 立即改用正确的状态读取编排，不把工具编排错误误判为产品结果 |
| 2026-08-09 | 问题探索有限重试仍返回 AI 服务不可用 | 正确读取重试结果后，安装版再次显示“AI 服务暂时不可用，请稍后重试”，且未形成 Problem Brief；路由仍为问题探索 Agent，未执行硬件。 | ISSUE | 检查云端模型服务/桌面 Agent 回执链路，保留失败状态，不伪造探索结论 |
| 2026-08-09 | 生产模型代理失败根因定位 | 只读检查 `https://kyrozen.chat/api/health` 返回 `status: ok`；生产日志显示桌面模型请求在会员检查阶段因 Supabase 缺少 `public.membership_seats` 表失败，未进入模型响应。 | ISSUE | 增加旧 Supabase 部署兼容处理或补齐已批准的幂等会员迁移，再重启安装版复测 |
| 2026-08-09 | 生产模型供应商额度与请求大小不足 | 只读生产日志显示 Gemini 免费额度为 0，Groq 多次返回 TPM 413（请求约 13.6K、上限 12K）；这些是供应商/请求容量限制，不能伪造成功结果。 | ISSUE | 修复会员检查阻塞后复测；必要时压缩 Agent 上下文或切换已配置且可用的真实供应商 |
| 2026-08-09 | 本地 Git 暂存首次被沙箱拒绝 | 为按用户要求提交本次修复，`git add` 无法创建 `.git/index.lock`，返回 `Operation not permitted`；未改变索引或未跟踪的 `video/`。 | RETRY | 申请仅限当前仓库 Git 写权限后重试暂存、提交和推送 |
