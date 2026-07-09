#!/bin/bash
# NextGenSeeker 自動更新スケジューラのインストール（macOS launchd, ユーザーレベル）
# 6時間ごと＋ログイン時に pipeline/refresh.py を実行する。
#
#   有効化:   bash pipeline/install_scheduler.sh
#   無効化:   bash pipeline/install_scheduler.sh --uninstall
#
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.nextgenseeker.refresh"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ "$1" == "--uninstall" ]; then
    launchctl unload "$DEST" 2>/dev/null || true
    rm -f "$DEST"
    echo "✓ アンインストール完了: $DEST を削除しました"
    exit 0
fi

chmod +x "$DIR/run.sh"
mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"
cp "$DIR/$LABEL.plist" "$DEST"
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"
echo "✓ インストール完了: $DEST"
echo "  6時間ごと＋ログイン時に自動更新します。"
echo "  状態確認: launchctl list | grep nextgenseeker"
echo "  ログ:     tail -f $DIR/logs/refresh.log"
