#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_APP="$SCRIPT_DIR/Kyrozen.app"
DEFAULT_DEST="/Applications/Kyrozen.app"

if [[ ! -d "$SOURCE_APP" ]]; then
  echo "错误：未在安装镜像中找到 Kyrozen.app。"
  exit 1
fi

DEST_APP="${KYROZEN_INSTALL_DEST:-$DEFAULT_DEST}"
DEST_PARENT="$(dirname "$DEST_APP")"

if [[ "$DEST_APP" == "$DEFAULT_DEST" && ! -w "$DEST_PARENT" ]]; then
  DEST_APP="$HOME/Applications/Kyrozen.app"
  DEST_PARENT="$HOME/Applications"
fi

echo "Kyrozen 免费未公证版安装器"
echo ""
echo "此版本使用 ad-hoc 代码签名，没有 Apple Developer ID 公证。"
echo "脚本只会复制 Kyrozen 到：$DEST_APP"
echo "并只移除该应用自身的 com.apple.quarantine 属性。"
echo "它不会关闭 Gatekeeper，也不会修改系统全局安全设置。"
echo ""

if [[ "${KYROZEN_INSTALL_ASSUME_YES:-0}" != "1" ]]; then
  read -r -p "确认安装？输入 yes 后按回车：" answer
  if [[ "$answer" != "yes" ]]; then
    echo "已取消，未修改任何文件。"
    exit 0
  fi
fi

mkdir -p "$DEST_PARENT"
STAMP="$(date +%Y%m%d-%H%M%S)"
TEMP_APP="$DEST_PARENT/.Kyrozen.installing.$$.app"
BACKUP_APP=""

cleanup() {
  if [[ -d "$TEMP_APP" ]]; then
    rm -rf "$TEMP_APP"
  fi
}
trap cleanup EXIT

/usr/bin/ditto "$SOURCE_APP" "$TEMP_APP"
/usr/bin/xattr -dr com.apple.quarantine "$TEMP_APP"
/usr/bin/codesign --verify --deep --strict "$TEMP_APP"

if [[ -e "$DEST_APP" ]]; then
  BACKUP_APP="${DEST_APP%.app}.backup-$STAMP.app"
  /bin/mv "$DEST_APP" "$BACKUP_APP"
fi

/bin/mv "$TEMP_APP" "$DEST_APP"
trap - EXIT

echo "安装完成：$DEST_APP"
if [[ -n "$BACKUP_APP" ]]; then
  echo "旧版本已保留为：$BACKUP_APP"
fi

if [[ "${KYROZEN_INSTALL_NO_LAUNCH:-0}" != "1" ]]; then
  /usr/bin/open "$DEST_APP"
fi
