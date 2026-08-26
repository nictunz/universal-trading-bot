from universal_bot.local_cache_core import (
    cache_file_names,
    server_upload_eligible,
)


def test_completed_ranges_from_one_day_through_ten_years_are_uploadable():
    assert server_upload_eligible("2026-08-25", "2026-08-25")
    assert server_upload_eligible("2025-08-26", "2026-08-25")
    assert server_upload_eligible("2016-08-28", "2026-08-25")


def test_non_one_year_uploads_keep_date_specific_names():
    db, result = cache_file_names(
        "ETH/USDT:USDT", "5m", "2026-05-26", "2026-08-25"
    )
    assert db == "eth-20260526-20260825-5m.db"
    assert result == "latest-eth-20260526-20260825-backtest.json"


def test_one_year_upload_keeps_server_fast_cache_canonical_name():
    db, result = cache_file_names(
        "BTC/USDT:USDT", "5m", "2025-08-26", "2026-08-25"
    )
    assert db == "btc-1y-5m.db"
    assert result == "latest-btc-one-year-backtest.json"
