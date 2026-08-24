from __future__ import annotations
from datetime import datetime, timezone
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)
    bot_mode: str = "PAPER"
    exchange: str = "bitget"
    symbol: str = "BTC/USDT:USDT"
    timeframe: str = "5m"
    symbols: str = "BTC/USDT:USDT,ETH/USDT:USDT"
    asset_class: str = "crypto"
    poll_seconds: int = 10
    volume_lookback: int = 70
    volume_break_multiplier: float = 8.0
    use_four_crypto_exchanges: bool = True
    min_one_bar_vol: float = 0.1
    max_one_bar_vol: float = 1.0
    volatility_bars: int = 288
    tp_vol_multiplier: float = 0.4
    sl_vol_multiplier: float = 0.8
    min_tp_percent: float = 0.20
    max_tp_percent: float = 2.00
    min_sl_percent: float = 0.30
    max_sl_percent: float = 2.00
    use_nbar_volatility_block: bool = True
    nbar_volatility_bars: int = 200
    max_nbar_volatility: float = 5.0
    use_adx_filter: bool = False
    adx_length: int = 14
    adx_min: float = 20.0
    adx_max: float = 100.0
    use_rsi_filter: bool = True
    rsi_length: int = 8
    rsi_oversold_min: float = 10.0
    rsi_oversold_max: float = 25.0
    rsi_overbought_min: float = 75.0
    rsi_overbought_max: float = 90.0
    allow_long: bool = True
    allow_short: bool = True
    # First entry + one add-on entry = two total entries.
    max_pyramiding: int = 2
    cooldown_bars: int = 6
    reentry_bars: int = 6
    use_start_date: bool = True
    start_date: datetime = Field(default_factory=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))
    block_weekend: bool = False
    excluded_hours: str = "00"
    order_percent_of_equity: float = 5.0
    initial_capital: float = 1_000_000.0
    backtest_fee_percent: float = 0.06
    backtest_slippage_percent: float = 0.02
    crypto_volume_provider: str = "none"
    crypto_volume_fallback_exchanges: str = "binance,bybit"
    allow_community_market_data_live: bool = False
    coinapi_api_key: str = ""

    # LIVE execution defaults for the user's Classic v2 Elite account.
    leverage: int = 50
    margin_mode: str = "crossed"
    require_exchange_protection: bool = True
    reconciliation_interval_seconds: int = 10
    stale_data_seconds: int = 600
    max_consecutive_api_errors: int = 3
    # Generic/standard LIVE safety limit retained for non-Elite routing.
    live_max_position_notional_percent: float = 10.0
    live_require_one_way_mode: bool = True
    # Elite LIVE sizing only. Each signal uses current available USDT x 15.
    live_entry_multiplier: float = 15.0
    live_max_entries_per_position: int = 2
    live_max_total_multiplier: float = 30.0

    # Bitget credential routing.
    # - standard: normal Bitget API; reserved for funding/spot/standard account work.
    # - elite: dedicated Elite Trading Portfolio API; used for LIVE execution when
    #   BITGET_EXECUTION_PROFILE=elite.
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
