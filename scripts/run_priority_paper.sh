#!/usr/bin/env bash
set -euo pipefail
PRIORITY_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PRIORITY_PYTHON="${PRIORITY_PYTHON:-/home/kpj3669/.cache/universal-trading-bot-dashboard-venv/bin/python}"
PRIORITY_STATE="${XDG_STATE_HOME:-$HOME/.local/state}/universal-trading-bot/priority-paper"
mkdir -p "$PRIORITY_STATE"
cd "$PRIORITY_ROOT"
export PYTHONPATH="$PRIORITY_ROOT"
exec "$PRIORITY_PYTHON" -u -m universal_bot.priority_paper_monitor \
  --journal "$PRIORITY_STATE/paper-only.sqlite" --boundaries "${1:-3}"
