from universal_bot.providers.coinapi import CoinAPIMarketData


def test_coinapi_perpetual_symbol_mapping_is_generic():
    provider = CoinAPIMarketData("test")
    assert provider.symbol_id("binance", "ETH/USDT:USDT") == "BINANCEFTS_PERP_ETH_USDT"
    assert provider.symbol_id("bybit", "SOLUSDT") == "BYBIT_PERP_SOL_USDT"
    assert provider.symbol_id("binance", "BTC/USDC:USDC") == "BINANCEFTS_PERP_BTC_USDC"


def test_coinapi_period_mapping_supports_strategy_timeframes():
    provider = CoinAPIMarketData("test")
    assert provider._period_id("5m") == "5MIN"
    assert provider._period_id("1h") == "1HRS"
    assert provider._period_id("1d") == "1DAY"
    assert provider._period_id("1w") == "7DAY"


def test_coinapi_frame_is_sorted_and_numeric():
    provider = CoinAPIMarketData("test")
    payload = [
        {"time_period_start": "2026-01-01T00:05:00Z", "price_open": "2", "price_high": "3", "price_low": "1", "price_close": "2.5", "volume_traded": "20"},
        {"time_period_start": "2026-01-01T00:00:00Z", "price_open": "1", "price_high": "2", "price_low": "0.5", "price_close": "1.5", "volume_traded": "10"},
    ]
    frame = provider._frame(payload)
    assert list(frame.volume) == [10.0, 20.0]
    assert frame.index.is_monotonic_increasing
