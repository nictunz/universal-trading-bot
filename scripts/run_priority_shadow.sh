#!/usr/bin/env bash
set -euo pipefail

PRIORITY_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PRIORITY_PYTHON="${PRIORITY_PYTHON:-/home/kpj3669/.cache/universal-trading-bot-dashboard-venv/bin/python}"
PRIORITY_STATE="${PRIORITY_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/universal-trading-bot/priority-shadow}"
if [[ ! -x "$PRIORITY_PYTHON" ]]; then
    echo "Python executable not found: $PRIORITY_PYTHON" >&2
    exit 1
fi
mkdir -p "$PRIORITY_STATE"
cd "$PRIORITY_ROOT"
export PYTHONPATH="$PRIORITY_ROOT"
"$PRIORITY_PYTHON" -c 'import universal_bot.priority_shadow as m; print("Observer:", m.__file__)'
exec "$PRIORITY_PYTHON" -u -m universal_bot.priority_shadow \
    --journal "$PRIORITY_STATE/shadow.sqlite" --boundaries "${1:-3}"
