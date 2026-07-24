# Kyrozen Desktop Client — 已知未实现/待完善项

> 由 Agent 对照 [DESKTOP_CLIENT_ARCHITECTURE.md](file:///Users/evangong/Documents/Programming/AI/Kyrozen/DESKTOP_CLIENT_ARCHITECTURE.md) 检查后整理。
> 当前版本优先跑通核心链路，以下项目后续按需补齐。

## P0 — 影响基础体验

- [ ] **系统托盘图标缺失**  
  `desktop/public/tray-icon.png` 不存在，托盘启动时可能无图标或报错。
- [ ] **代码签名与打包验证**  
  仅配置了 `electron-builder` publish；Windows 免费签名方案未调研；未实际跑过完整打包。
- [ ] **硬件工具链补全**  
  - arduino-cli / PlatformIO 为首次运行时动态下载，未随安装包打包。  
  - 缺少 esptool。  
  - 缺少 Node.js 串口库（如 `serialport`）用于读取串口输出。

## P1 — 功能闭环

- [ ] **内置编辑器**  
  对话旁或新窗口中打开 Monaco/CodeMirror 编辑器，手动保存后不自动 commit。
- [ ] **GitHub 集成闭环**  
  OAuth authorize/callback 已加，但前端缺少「一键 git init / commit / push」引导。
- [ ] **`.env.example` 自动生成与敏感信息警告**  
  Agent 生成含密钥的代码时需生成 `.env.example` 并弹窗提示用户。
- [ ] **高危操作确认 UI 完善**  
  确认对话框未显示「本次会话信任该 Agent」勾选状态。

## P2 — 新手引导与国际化

- [ ] **首次启动新手引导**  
  选择语言 → 登录 → 下载/校验 Python 运行时 → 选择项目目录。
- [ ] **中英双语**  
  首次启动引导中手动选择，默认中文；Agent 回复跟随用户输入语言。

## P3 — 安全与合规

- [ ] **危险命令黑名单**  
  终端工具禁止 `rm -rf /`、`sudo`、`ssh` 等模式。
- [ ] **依赖安装安全扫描**  
  展示来源并对已知恶意包做基础阻断。
- [ ] **更新包签名验证**  
  防止中间人攻击。
- [ ] **完全信任模式审计日志回传云端**  
  所有操作日志必须回传云端审计。
- [ ] **本地 credential 系统 keychain 加密存储**  
  当前仅使用了 `safeStorage`，需确认实际走系统 keychain。

## P4 — UX 增强

- [ ] **文件树摘要展示**  
  在对话中展示 Agent 修改了哪些文件。
- [ ] **原始模型输出展开**  
  AI 消息可展开查看原始内容和工具调用 JSON/XML。
- [ ] **显式「停止」按钮**  
  优雅终止当前 Agent 任务。
- [ ] **拖拽文件/文件夹到对话**  
  作为附件发送给 Agent。
- [ ] **多设备主动选择**  
  用户可手动选择推送到哪台设备。

## P5 — 工程与运维

- [ ] **实际完整打包验证**  
  `npm run build` 生成 dmg/exe/AppImage 并在真实系统安装测试。
- [ ] **WSS/TLS 生产配置**  
  开发环境使用 ws://，生产环境需切换为 wss://。
- [ ] **浏览器扩展上架**  
  当前为本地加载版本，需打包并提交 Chrome Web Store / Edge Add-ons。
