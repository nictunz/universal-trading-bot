from __future__ import annotations

import json

from universal_bot.adapters.bitget_elite import BitgetEliteAdapter
from universal_bot.dashboard import BacktestRequest
from universal_bot.engine import effective_stale_seconds
import universal_bot.strategy_dashboard as strategy_dashboard


def test_server_backtest_defaults_to_btc_15m():
    request = BacktestRequest()
    assert request.symbol == "BTC/USDT:USDT"
    assert request.timeframe == "15m"


def test_strategy_settings_are_backed_up_before_change(tmp_path, monkeypatch):
    store = tmp_path / "dashboard-strategy-settings.json"
    backups = tmp_path / "backups"
    mobile = tmp_path / "mobile-strategy-settings.json"
    previous = {"volume_lookback": 40}
    store.write_text(json.dumps(previous), encoding="utf-8")

    monkeypatch.setattr(strategy_dashboard, "STORE", store)
    monkeypatch.setattr(strategy_dashboard, "BACKUP_DIR", backups)
    monkeypatch.setattr(strategy_dashboard, "MOBILE_STORE", mobile)

    strategy_dashboard._persist({"volume_lookback": 80})

    saved_backups = list(backups.glob("strategy-settings-*.json"))
    assert len(saved_backups) == 1
    assert json.loads(saved_backups[0].read_text(encoding="utf-8")) == previous
    assert json.loads(store.read_text(encoding="utf-8")) == {"volume_lookback": 80}


def test_elite_tpsl_uses_last_trade_trigger_and_market_close():
    adapter = BitgetEliteAdapter.__new__(BitgetEliteAdapter)
    bodies = []
    adapter._symbol_id = lambda symbol: "BTCUSDT"
    adapter._position_mode = lambda symbol: "one_way_mode"
    adapter._price = lambda symbol, price: str(price)
    adapter._client_oid = lambda prefix: prefix
    adapter._request = lambda method, path, body=None, **kwargs: bodies.append(body) or {"orderId": str(len(bodies))}

    result = adapter._place_protection(
        "BTC/USDT:USDT",
        "long",
        "0.001",
        110_000.0,
        90_000.0,
    )

    assert len(result) == 2
    assert len(bodies) == 2
    for body in bodies:
        assert body["triggerType"] == "fill_price"
        assert body["orderType"] == "market"
        assert body["reduceOnly"] == "yes"
        assert body["marginMode"] == "crossed"


def test_stale_data_limit_accounts_for_completed_candle_open_time():
    assert effective_stale_seconds("5m", 600) == 720
    assert effective_stale_seconds("15m", 600) == 1920
    assert effective_stale_seconds("1h", 600) == 7320
    assert effective_stale_seconds("bad", 600) == 600
