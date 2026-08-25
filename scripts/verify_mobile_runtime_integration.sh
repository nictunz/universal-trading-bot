#!/usr/bin/env bash
set -euo pipefail

ROOT="${BOT_ROOT:-$HOME/universal-trading-bot}"
CACHE_DIR="${UNIVERSAL_CACHE_DIR:-$HOME/.cache/universal-trading-bot}"
RELAY_FILE="$CACHE_DIR/mobile-market-relay.json"

cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="python3"
fi

echo "===== 1. MOBILE RELAY FILE ====="
if [[ ! -s "$RELAY_FILE" ]]; then
  echo "FAIL: relay file missing or empty: $RELAY_FILE"
  exit 2
fi
stat -c 'path=%n size=%s modified=%y' "$RELAY_FILE"

echo
echo "===== 2. PROVIDER + FOUR-VENUE ADAPTER ====="
"$PY" - <<'PY'
from universal_bot.providers.mobile_relay import MobileRelayMarketData
from universal_bot.adapters.hybrid_ccxt_adapter import HybridCCXTAdapter

relay = MobileRelayMarketData(max_age_seconds=90)
for symbol in ("BTC/USDT:USDT", "ETH/USDT:USDT"):
    print(f"[{symbol}]")
    for exchange in ("binance", "bybit"):
        series = relay.fetch_volume(exchange, symbol, "5m", limit=240)
        print(f"  relay {exchange:7s} rows={len(series):3d} latest={series.index[-1]} volume={series.iloc[-1]:.6f}")

adapter = HybridCCXTAdapter(
    "bitget",
    "",
    "",
    "",
    fallback_exchanges=["binance", "bybit"],
    community_fallback=False,
)
volumes = adapter.fetch_volume_sources("ETH/USDT:USDT", "5m", limit=120)
print("four_exchange_status=", adapter.volume_source_status)
print("four_exchange_rows=", {name: len(series) for name, series in volumes.items()})
if set(volumes) != {"binance", "bitget", "okx", "bybit"}:
    raise SystemExit(f"FAIL: four exchange volume incomplete: {sorted(volumes)}")
if any(item.get("status") != "OK" for item in adapter.volume_source_status.values()):
    raise SystemExit(f"FAIL: volume source status: {adapter.volume_source_status}")
frame = adapter.fetch_ohlcv("ETH/USDT:USDT", "5m", limit=120)
print(f"gated_bitget_ohlcv_rows={len(frame)} latest={frame.index[-1]}")
print("BOT_MARKET_DATA_CONNECTION=OK")
PY

echo
echo "===== 3. BACKTEST CACHE INVENTORY ====="
mkdir -p "$CACHE_DIR"
find "$CACHE_DIR" -maxdepth 1 -type f \( -name '*.db' -o -name 'latest-*-backtest.json' \) \
  -printf '%TY-%Tm-%Td %TH:%TM:%TS  %10s  %f\n' | sort || true

echo
echo "===== 4. BOT PROCESS CHECK ====="
pgrep -af 'universal_bot|uvicorn' || echo "No matching bot/uvicorn process found."

echo
echo "INTEGRATION_CHECK_COMPLETE"
