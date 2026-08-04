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
