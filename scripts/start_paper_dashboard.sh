#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${DASHBOARD_VENV:-$HOME/.cache/universal-trading-bot-dashboard-venv}"
PIDFILE="${DASHBOARD_PIDFILE:-$HOME/.cache/universal-trading-bot-dashboard.pid}"
LOGFILE="${DASHBOARD_LOGFILE:-$HOME/.cache/universal-trading-bot-dashboard.log}"
STAMP="${DASHBOARD_INSTALL_STAMP:-$HOME/.cache/universal-trading-bot-dashboard.install.sha256}"
PERSISTENT_ENV="${DASHBOARD_ENV_FILE:-$HOME/universal-trading-bot/.env}"
mkdir -p "$HOME/.cache/universal-trading-bot"

if [[ -f "$PERSISTENT_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$PERSISTENT_ENV"
  set +a
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip
fi

# Editable installs point at the stable deployment directory, so reinstall only
# when package metadata/dependencies change. This keeps the e2-micro responsive
# during frequent code-only dashboard deployments.
new_hash="$(sha256sum "$ROOT/pyproject.toml" | awk '{print $1}')"
old_hash="$(cat "$STAMP" 2>/dev/null || true)"
if [[ "$new_hash" != "$old_hash" ]] || ! "$VENV/bin/python" -c 'import universal_bot' >/dev/null 2>&1; then
  "$VENV/bin/pip" install -e "$ROOT"
  echo "$new_hash" > "$STAMP"
fi

if [[ -f "$PIDFILE" ]]; then
  oldpid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "$oldpid" ]] && kill -0 "$oldpid" 2>/dev/null; then
    kill "$oldpid" || true
    sleep 2
  fi
fi

cd "$ROOT"
export BOT_MODE=PAPER
export EXCHANGE=bitget
export ASSET_CLASS=crypto
export SYMBOL=ETH/USDT:USDT
export SYMBOLS=ETH/USDT:USDT
export TIMEFRAME=5m
export USE_FOUR_CRYPTO_EXCHANGES=true
export DATABASE_URL="sqlite:///$HOME/.cache/universal-trading-bot/historical.db"
export DASHBOARD_HOST=0.0.0.0
export DASHBOARD_PORT=8000

RUNNER_TRACKING_ID='' nohup "$VENV/bin/python" -m universal_bot.main >"$LOGFILE" 2>&1 </dev/null &
echo $! > "$PIDFILE"
sleep 5

if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Dashboard process exited unexpectedly. Recent log:" >&2
  tail -n 100 "$LOGFILE" >&2 || true
  exit 1
fi

python3 - <<'PY'
import time, urllib.request
for attempt in range(20):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3) as r:
            print(r.read().decode('utf-8'))
        break
    except Exception:
        if attempt == 19:
            raise
        time.sleep(1)
PY

echo "Dashboard started in PAPER mode."
echo "Local:  http://127.0.0.1:8000/"
echo "Tunnel: http://127.0.0.1:8000/ via Termius Local Forwarding"
echo "PID:    $(cat "$PIDFILE")"
echo "Log:    $LOGFILE"
