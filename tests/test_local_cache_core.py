from universal_bot.local_cache_core import (
    COMMON_SYMBOLS,
    COMMON_TIMEFRAMES,
    cache_file_names,
    inclusive_days,
    server_upload_eligible,
)


def test_one_year_cache_is_upload_eligible():
    assert inclusive_days("2025-08-25", "2026-08-24") == 365
    assert server_upload_eligible("2025-08-25", "2026-08-24") is True
    db, result = cache_file_names("BTC/USDT:USDT", "5m", "2025-08-25", "2026-08-24")
    assert db == "btc-1y-5m.db"
    assert result == "latest-btc-one-year-backtest.json"


def test_short_cache_cannot_overwrite_one_year_cache():
    assert server_upload_eligible("2026-08-22", "2026-08-24") is False
    db, result = cache_file_names("ETH/USDT:USDT", "5m", "2026-08-22", "2026-08-24")
    assert db == "eth-20260822-20260824-5m.db"
    assert result == "latest-eth-20260822-20260824-backtest.json"


def test_common_inputs_have_expected_defaults():
    assert "BTC/USDT:USDT" in COMMON_SYMBOLS
    assert "ETH/USDT:USDT" in COMMON_SYMBOLS
    assert "5m" in COMMON_TIMEFRAMES
    assert "1h" in COMMON_TIMEFRAMES
