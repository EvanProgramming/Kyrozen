# macOS 免费未公证版安装

Kyrozen 当前 macOS 包使用 ad-hoc 代码签名，不包含 Apple Developer ID 签名与 Apple 公证。发布物因此不能获得 Gatekeeper 的“已识别开发者”认可。

## 用户安装流程

打开 DMG 后，不要直接拖动应用。打开“终端”，输入 `bash `，再把 DMG 内的 `Install Kyrozen.command` 拖入终端并按回车。阅读提示后输入 `yes`。

安装脚本会：

1. 将 `Kyrozen.app` 复制到 `/Applications`；无写权限时改用 `~/Applications`。
2. 只清除目标应用的 `com.apple.quarantine` 扩展属性。
3. 使用 `codesign --verify --deep --strict` 检查 ad-hoc 签名完整性。
4. 保留已安装旧版本的时间戳备份，然后启动新版本。

脚本不会执行 `spctl --master-disable`，不会关闭 Gatekeeper，也不会改动其他应用。

## 发布验收

```bash
cd desktop
npm run build:renderer
npx electron-builder --mac dmg --arm64
```

挂载生成的 DMG，确认其中同时存在 `Kyrozen.app`、`Applications`、`Install Kyrozen.command` 和 `安装说明.txt`。测试时应先给来源应用写入 quarantine 属性，再通过安装脚本复制，最后验证目标应用不再包含该属性且可真实启动。

这个流程解决的是“无付费开发者账号时仍可明确、可复现地安装”。它不等同于 Apple 公证；`spctl` 仍可能报告 rejected。
