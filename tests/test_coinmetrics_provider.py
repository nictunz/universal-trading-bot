from __future__ import annotations

from universal_bot.config import Settings
from universal_bot.providers.coinmetrics import CoinMetricsCommunityMarketData


def test_coinmetrics_future_market_mapping_is_symbol_generic():
    p = CoinMetricsCommunityMarketData()
    assert p.market_id("binance", "ETH/USDT:USDT") == "binance-ETHUSDT-future"
    assert p.market_id("bybit", "BTCUSDT") == "bybit-BTCUSDT-future"
    assert p.market_id("binance", "SOL-USDT") == "binance-SOLUSDT-future"


def test_community_provider_supports_strategy_timeframe():
    assert "5m" in CoinMetricsCommunityMarketData.SUPPORTED


def test_paper_defaults_do_not_require_coinapi_key():
    s = Settings(_env_file=None)
    assert s.crypto_volume_provider == "community"
    assert s.coinapi_api_key == ""
    assert s.allow_community_market_data_live is False
    assert s.crypto_fallback_exchange_list == ["binance", "bybit"]
