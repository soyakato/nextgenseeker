#!/bin/bash
# NextGenSeeker データ更新ラッパー（launchd / cron から呼ばれる）
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"
cd "$DIR"
# APIキー等を .env から読み込む（launchdはシェル環境を継承しないため）
if [ -f "$DIR/.env" ]; then
    set -a; . "$DIR/.env"; set +a
fi
TS="$(date '+%Y-%m-%d %H:%M:%S')"
echo "===== NGS refresh start $TS =====" >> logs/refresh.log
"$PY" refresh.py >> logs/refresh.log 2>&1
echo "===== NGS refresh end   $(date '+%Y-%m-%d %H:%M:%S') =====" >> logs/refresh.log

# ログローテーション: 直近4000行だけ保持（無限肥大の防止）
if [ "$(wc -l < logs/refresh.log)" -gt 4000 ]; then
    tail -n 4000 logs/refresh.log > logs/refresh.log.tmp && mv logs/refresh.log.tmp logs/refresh.log
fi
