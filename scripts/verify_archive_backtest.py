from __future__ import annotations

import json
import os
from pathlib import Path

from universal_bot.backtest_service import run_symbol_backtest


def main() -> None:
    db = Path(os.environ.get("ARCHIVE_SMOKE_DB", "/tmp/universal-bot-archive-smoke.db"))
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(str(db) + suffix).unlink()
        except FileNotFoundError:
            pass
    os.environ["DATABASE_URL"] = f"sqlite:///{db}"
    os.environ["COINAPI_API_KEY"] = ""
    os.environ["CRYPTO_VOLUME_PROVIDER"] = "none"
    os.environ["USE_FOUR_CRYPTO_EXCHANGES"] = "true"

    result = run_symbol_backtest(
        symbol="ETH/USDT:USDT",
        asset_class="crypto",
        exchange="bitget",
        timeframe="5m",
        start="2026-08-20",
        end="2026-08-21",
    )
    summary = {
        "symbol": result["symbol"],
        "bars": result["bars"],
        "four_exchange_volume": result["four_exchange_volume"],
        "volume_source_bars": result["volume_source_bars"],
        "volume_source_status": result["volume_source_status"],
        "trades": result["trades"],
        "win_rate": result["win_rate"],
        "return_percent": result["return_percent"],
        "max_drawdown_percent": result["max_drawdown_percent"],
    }
    required = {"binance", "bitget", "okx", "bybit"}
    assert result["four_exchange_volume"] is True
    assert set(result["volume_source_bars"]) == required
    assert all(int(result["volume_source_bars"][x]) >= 500 for x in required)
    assert result["volume_source_status"]["binance"]["mode"] == "OFFICIAL_ARCHIVE"
    assert result["volume_source_status"]["bybit"]["mode"] == "OFFICIAL_ARCHIVE"
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
