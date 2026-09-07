from __future__ import annotations
from datetime import datetime, timezone
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)
    bot_mode: str = "PAPER"
    exchange: str = "bitget"
    symbol: str = "BTC/USDT:USDT"
    timeframe: str = "15m"
    symbols: str = "BTC/USDT:USDT"
    asset_class: str = "crypto"
    poll_seconds: int = 2
    volume_lookback: int = 40
    volume_break_multiplier: float = 6.4
    use_four_crypto_exchanges: bool = True
    min_one_bar_vol: float = 0.1
    max_one_bar_vol: float = 3.6
    volatility_bars: int = 36
    tp_vol_multiplier: float = 3.8
    sl_vol_multiplier: float = 1.0
    min_tp_percent: float = 0.3
    max_tp_percent: float = 2.1
    min_sl_percent: float = 0.3
    max_sl_percent: float = 1.9
    use_nbar_volatility_block: bool = True
    nbar_volatility_bars: int = 200
    max_nbar_volatility: float = 6.3
    use_adx_filter: bool = False
    adx_length: int = 7
    adx_min: float = 11.6
    adx_max: float = 80.5
    use_rsi_filter: bool = True
    rsi_length: int = 10
    rsi_oversold_min: float = 20.0
    rsi_oversold_max: float = 42.0
    rsi_overbought_min: float = 65.6
    rsi_overbought_max: float = 74.7
    allow_long: bool = True
    allow_short: bool = True
    # Adaptive regime routing uses only closed historical bars.
    adaptive_regime_enabled: bool = False
    regime_lookback_bars: int = 288
    regime_trend_threshold_percent: float = 2.0
    regime_high_volatility_percent: float = 0.8
    regime_high_volatility_risk_multiplier: float = 0.5
    # First entry may require N consecutive same-direction 5-minute candles.
    # 1 preserves the original single-candle reversal behavior.
    first_entry_consecutive_candles: int = 1
    # False=3틱룰은 첫 진입만, True=추가 진입에도 동일한 연속봉 조건 적용.
    apply_consecutive_candles_to_all_entries: bool = False
    # Maximum entries per position; profile optimization may override this.

    max_pyramiding: int = 1
    cooldown_bars: int = 3
    reentry_bars: int = 5
    use_start_date: bool = True
    start_date: datetime = Field(default_factory=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))
    block_weekend: bool = False
    excluded_hours: str = ""
    order_percent_of_equity: float = 860.0
    initial_capital: float = 1_000.0
    backtest_fee_percent: float = 0.02
    backtest_slippage_percent: float = 0.01
    # Backtest-only liquidation model. LIVE/PAPER routing is not changed by these fields.
    backtest_margin_mode: str = "crossed"
    backtest_maintenance_margin_percent: float = 0.5
    backtest_cross_liquidation_buffer_percent: float = 25.0
    backtest_max_total_multiplier: float = 15.0
    # Backtest only: size each new position from current net equity when enabled.
    backtest_compounding_enabled: bool = False
    # signal_close preserves legacy results. next_open executes a confirmed
    # signal at the following candle open to avoid optimistic same-close fills.
    backtest_execution_model: str = "signal_close"
    crypto_volume_provider: str = "none"
    crypto_volume_fallback_exchanges: str = "binance,bybit"
    allow_community_market_data_live: bool = False
    coinapi_api_key: str = ""

    # LIVE execution defaults. Both Classic v2 and UTA v3 adapters preserve the
    # same engine-facing behavior for crossed margin / one-way execution.
    leverage: int = 15
    margin_mode: str = "crossed"
    require_exchange_protection: bool = True
    reconciliation_interval_seconds: int = 10
    stale_data_seconds: int = 600
    max_consecutive_api_errors: int = 3
    # Generic/standard LIVE safety limit retained for non-Elite routing.
    live_max_position_notional_percent: float = 10.0
    live_require_one_way_mode: bool = True
    # Elite LIVE sizing follows 진입_비중_pct=860: current available USDT x 8.6.
    # LEVERAGE=15 is the exchange leverage ceiling, not the order-size multiplier.
    live_entry_multiplier: float = 8.6
    live_max_entries_per_position: int = 1
    live_max_total_multiplier: float = 15.0

    # Discord notifications. Keep the webhook only in .env, never in source.
    discord_notifications_enabled: bool = False
    discord_webhook_url: str = ""
    discord_timeout: float = 5.0

    # Bitget credential / API-family routing.
    # BITGET_API_FAMILY=auto probes UTA v3 first and falls back to Classic v2.
    # After account migration, uta-v3 can be pinned explicitly.
    bitget_api_family: str = "classic-first"
    bitget_execution_profile: str = "elite"
    bitget_standard_api_key: str = ""
    bitget_standard_api_secret: str = ""
    bitget_standard_api_passphrase: str = ""
    bitget_elite_api_key: str = ""
    bitget_elite_api_secret: str = ""
    bitget_elite_api_passphrase: str = ""
    bitget_elite_request_timeout: float = 8.0

    # Legacy names retained for backwards compatibility. New deployments should
    # use BITGET_STANDARD_* and BITGET_ELITE_* instead.
    bitget_api_key: str = ""
    bitget_api_secret: str = ""
    bitget_api_passphrase: str = ""

    binance_api_key: str = ""
    binance_api_secret: str = ""
    okx_api_key: str = ""
    okx_api_secret: str = ""
    okx_api_passphrase: str = ""
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_api_passphrase: str = ""
    stock_data_provider: str = "yfinance"
    broker_api_key: str = ""
    broker_api_secret: str = ""
    database_url: str = "sqlite:///data/universal_bot.db"
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8000
    dashboard_public_url: str = "http://34.132.172.40"
    dashboard_auth_enabled: bool = True
    dashboard_username: str = ""
    dashboard_password: str = ""
    dashboard_session_secret: str = ""
    dashboard_session_hours: int = 12
    dashboard_cookie_secure: bool = False

    @property
    def symbol_list(self) -> list[str]:
        return [x.strip() for x in self.symbols.split(",") if x.strip()]

    @property
    def crypto_fallback_exchange_list(self) -> list[str]:
        return [x.strip().lower() for x in self.crypto_volume_fallback_exchanges.split(",") if x.strip()]

    @property
    def bitget_standard_credentials(self) -> tuple[str, str, str]:
        """Return new standard credentials, falling back to legacy names."""
        return (
            self.bitget_standard_api_key or self.bitget_api_key,
            self.bitget_standard_api_secret or self.bitget_api_secret,
            self.bitget_standard_api_passphrase or self.bitget_api_passphrase,
        )

    @property
    def bitget_elite_credentials(self) -> tuple[str, str, str]:
        return (
            self.bitget_elite_api_key,
            self.bitget_elite_api_secret,
            self.bitget_elite_api_passphrase,
        )
