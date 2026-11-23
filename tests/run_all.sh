#!/bin/bash
# テストをまとめて実行する。
#   tests/run_all.sh          すべて
#   tests/run_all.sh unit     画面（Chromium）以外
#   tests/run_all.sh e2e      公開ページの回帰テストだけ
set -euo pipefail
cd "$(dirname "$0")/.."
# 本番の DB と秘密鍵（~/.local/share/yuikaori-admin）に触れないよう、指定がなければ使い捨ての保存先にする
if [ -z "${YUIKAORI_DATA_DIR:-}" ]; then
  YUIKAORI_DATA_DIR="$(mktemp -d)"
  export YUIKAORI_DATA_DIR
  trap 'rm -rf "$YUIKAORI_DATA_DIR"' EXIT
fi
case "${1:-all}" in
  all)  .venv/bin/python manage.py test catalog ;;
  unit) .venv/bin/python manage.py test catalog --exclude-tag e2e ;;
  e2e)  .venv/bin/python manage.py test catalog --tag e2e ;;
  *)    echo "使い方: $0 [all|unit|e2e]" >&2; exit 2 ;;
esac
