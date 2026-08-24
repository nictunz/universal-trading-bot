#!/usr/bin/env bash
set -euo pipefail

SYMBOL="${1:-ETH/USDT:USDT}"
TIMEFRAME="${2:-5m}"
START="${3:-2025-08-19}"
END="${4:-2026-08-18}"

BASE="${SYMBOL%%/*}"
SLUG="$(printf '%s' "$BASE" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
[[ -n "$SLUG" ]] || { echo "Invalid symbol: $SYMBOL" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="$HOME/.cache/universal-trading-bot"
ENV_FILE="$ROOT/.backtest-$SLUG.env"
mkdir -p "$CACHE"

cat > "$ENV_FILE" <<EOF
BACKTEST_SYMBOL=$SYMBOL
BACKTEST_TIMEFRAME=$TIMEFRAME
BACKTEST_START=$START
BACKTEST_END=$END
ONE_YEAR_DB=$CACHE/$SLUG-1y-$TIMEFRAME.db
ONE_YEAR_RESULT=$CACHE/latest-$SLUG-one-year-backtest.json
EOF
chmod 600 "$ENV_FILE"

sudo systemctl reset-failed "universal-trading-bot-backtest@$SLUG.service" 2>/dev/null || true
sudo systemctl start "universal-trading-bot-backtest@$SLUG.service"

echo "Started isolated backtest: $SLUG"
echo "Symbol: $SYMBOL  Timeframe: $TIMEFRAME  Window: $START .. $END"
echo "Status: systemctl status universal-trading-bot-backtest@$SLUG.service"
echo "Log: $CACHE/$SLUG-one-year-backtest.log"
