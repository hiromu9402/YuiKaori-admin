#!/bin/bash
# テストをまとめて実行する。
#   tests/run_all.sh          すべて
#   tests/run_all.sh unit     画面（Chromium）以外
#   tests/run_all.sh e2e      公開ページの回帰テストだけ
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-all}" in
  all)  exec .venv/bin/python manage.py test catalog ;;
  unit) exec .venv/bin/python manage.py test catalog --exclude-tag e2e ;;
  e2e)  exec .venv/bin/python manage.py test catalog --tag e2e ;;
  *)    echo "使い方: $0 [all|unit|e2e]" >&2; exit 2 ;;
esac
