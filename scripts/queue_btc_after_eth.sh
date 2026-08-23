#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="$HOME/.cache/universal-trading-bot"
VENV="${ONE_YEAR_VENV:-$HOME/.cache/universal-trading-bot-ci-venv}"
ETH_PID_FILE="$CACHE/one-year-backtest.pid"
ETH_RESULT="$CACHE/latest-one-year-backtest.json"
ETH_SAVED="$CACHE/latest-eth-one-year-backtest.json"
BTC_LOG="$CACHE/btc-one-year-backtest.log"
BTC_PID_FILE="$CACHE/btc-one-year-backtest.pid"
BTC_RESULT="$CACHE/latest-btc-one-year-backtest.json"

mkdir -p "$CACHE"

if [[ ! -f "$ETH_PID_FILE" ]]; then
  echo "ETH PID file missing: $ETH_PID_FILE" >&2
  exit 1
fi

ETH_PID="$(cat "$ETH_PID_FILE")"
echo "WAITING_FOR_ETH_PID=$ETH_PID"

while kill -0 "$ETH_PID" 2>/dev/null; do
  sleep 30
done

echo "ETH PROCESS FINISHED"

if [[ ! -f "$ETH_RESULT" ]]; then
  echo "ETH BACKTEST FAILED: result file not found: $ETH_RESULT" >&2
  exit 2
fi

python3 - "$ETH_RESULT" "$ETH_SAVED" <<'PY'
import json, shutil, sys
src, dst = sys.argv[1], sys.argv[2]
data = json.load(open(src, encoding="utf-8"))
if data.get("symbol") != "ETH/USDT:USDT":
    raise SystemExit(f"unexpected ETH result symbol: {data.get('symbol')}")
shutil.copy2(src, dst)
print(f"ETH_RESULT_SAVED={dst}")
PY

cd "$ROOT"

echo "STARTING BTC ONE-YEAR BACKTEST"
BACKTEST_SYMBOL="BTC/USDT:USDT" \
ONE_YEAR_DB="$CACHE/btc-1y-5m.db" \
ONE_YEAR_RESULT="$BTC_RESULT" \
nohup "$VENV/bin/python" scripts/run_one_year_backtest.py \
  > "$BTC_LOG" 2>&1 < /dev/null &

BTC_PID=$!
echo "$BTC_PID" > "$BTC_PID_FILE"
echo "BTC_PID=$BTC_PID"
echo "BTC_LOG=$BTC_LOG"
echo "BTC_RESULT=$BTC_RESULT"
