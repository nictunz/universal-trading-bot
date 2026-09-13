from __future__ import annotations

import os
import math
from datetime import datetime, timezone


_DEFAULTS = {
    "bot_mode": "PAPER",
    "exchange": "bitget",
    "symbol": "BTC/USDT:USDT",
    "timeframe": "5m",
    "symbols": "BTC/USDT:USDT,ETH/USDT:USDT",
    "asset_class": "crypto",
    "poll_seconds": 10,
    "volume_lookback": 70,
    "volume_break_multiplier": 8.0,
    "use_four_crypto_exchanges": True,
    "min_one_bar_vol": 0.1,
    "max_one_bar_vol": 1.0,
    "volatility_bars": 288,
    "tp_vol_multiplier": 0.4,
    "sl_vol_multiplier": 0.8,
    "min_tp_percent": 0.20,
    "max_tp_percent": 2.00,
    "min_sl_percent": 0.30,
    "max_sl_percent": 2.00,
    "use_nbar_volatility_block": True,
    "nbar_volatility_bars": 200,
    "max_nbar_volatility": 5.0,
    "use_adx_filter": False,
    "adx_length": 14,
    "adx_min": 20.0,
    "adx_max": 100.0,
    "use_rsi_filter": True,
    "rsi_length": 8,
    "rsi_oversold_min": 10.0,
    "rsi_oversold_max": 25.0,
    "rsi_overbought_min": 75.0,
    "rsi_overbought_max": 90.0,
    "allow_long": True,
    "allow_short": True,
    "adaptive_regime_enabled": False,
    "regime_lookback_bars": 288,
    "regime_trend_threshold_percent": 2.0,
    "regime_high_volatility_percent": 0.8,
    "regime_high_volatility_risk_multiplier": 0.5,
    "first_entry_consecutive_candles": 1,
    "apply_consecutive_candles_to_all_entries": False,
    "max_pyramiding": 2,
    "cooldown_bars": 6,
    "reentry_bars": 6,
    "use_start_date": True,
    "start_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
    "block_weekend": False,
    "excluded_hours": "00",
    "order_percent_of_equity": 5.0,
    "initial_capital": 1_000_000.0,
    "backtest_fee_percent": 0.06,
    "backtest_slippage_percent": 0.02,
    "backtest_margin_mode": "crossed",
    "backtest_maintenance_margin_percent": 0.5,
    "backtest_cross_liquidation_buffer_percent": 25.0,
    "backtest_max_total_multiplier": 15.0,
    "backtest_compounding_enabled": False,
    "backtest_execution_model": "signal_close",
    "crypto_volume_provider": "none",
    "crypto_volume_fallback_exchanges": "binance,bybit",
    "allow_community_market_data_live": False,
    "coinapi_api_key": "",
    "leverage": 50,
    "margin_mode": "cross",
    "require_exchange_protection": True,
    "reconciliation_interval_seconds": 10,
    "stale_data_seconds": 600,
    "max_consecutive_api_errors": 3,
    "live_max_position_notional_percent": 10.0,
    "live_require_one_way_mode": True,
    "binance_api_key": "",
    "binance_api_secret": "",
    "bitget_api_key": "",
    "bitget_api_secret": "",
    "bitget_api_passphrase": "",
    "okx_api_key": "",
    "okx_api_secret": "",
    "okx_api_passphrase": "",
    "bybit_api_key": "",
    "bybit_api_secret": "",
    "bybit_api_passphrase": "",
    "stock_data_provider": "yfinance",
    "broker_api_key": "",
    "broker_api_secret": "",
    "database_url": "sqlite:///data/universal_bot.db",
    "dashboard_host": "127.0.0.1",
    "dashboard_port": 8000,
    "dashboard_public_url": "http://34.132.172.40",
    "dashboard_auth_enabled": True,
    "dashboard_username": "",
    "dashboard_password": "",
    "dashboard_session_secret": "",
    "dashboard_session_hours": 12,
    "dashboard_cookie_secure": False,
}


def _parse_env(value: str, default):
    if isinstance(default, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int) and not isinstance(default, bool):
        return int(value)
    if isinstance(default, float):
        return float(value)
    if isinstance(default, datetime):
        text = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return value


class Settings:
    """Android-only lightweight replacement for pydantic Settings.

    The desktop/server build continues using the normal pydantic-backed config.py.
    Android only needs deterministic defaults, environment overrides and model_copy.
    """

    def __init__(self, **overrides):
        for key, default in _DEFAULTS.items():
            env = os.getenv(key.upper())
            value = _parse_env(env, default) if env is not None else default
            setattr(self, key, value)
        for key, value in overrides.items():
            setattr(self, key, value)

    def model_copy(self, *, update=None):
        values = {key: getattr(self, key) for key in _DEFAULTS}
        values.update(dict(update or {}))
        return Settings(**values)

    @classmethod
    def model_validate(cls, values):
        """Validate known scalar settings without shipping pydantic on Android.

        Strategy-specific ranges are checked by chart_workspace afterwards.
        Keep model_copy's existing non-validating behavior for engine callers.
        """
        if not isinstance(values, dict):
            raise ValueError("설정은 JSON 객체여야 합니다.")
        parsed = {}
        for key, value in values.items():
            if key not in _DEFAULTS:
                continue
            default = _DEFAULTS[key]
            try:
                if isinstance(default, bool):
                    if isinstance(value, bool):
                        pass
                    elif isinstance(value, (str, int)) and str(value).lower() in ("true", "1", "yes", "on", "false", "0", "no", "off"):
                        value = str(value).lower() in ("true", "1", "yes", "on")
                    else:
                        raise ValueError("boolean required")
                elif isinstance(default, (int, float)):
                    if isinstance(value, bool):
                        raise ValueError("number required")
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError("finite number required")
                    if isinstance(default, int):
                        if not number.is_integer():
                            raise ValueError("integer required")
                        value = int(number)
                    else:
                        value = number
                elif isinstance(default, datetime):
                    if not isinstance(value, datetime):
                        value = _parse_env(value, default)
                elif isinstance(default, str) and not isinstance(value, str):
                    raise ValueError("string required")
            except (ValueError, TypeError, AttributeError, OverflowError) as exc:
                raise ValueError(f"설정값 형식 오류: {key}") from exc
            parsed[key] = value
        return cls(**parsed)

    def model_dump(self, *, mode="python"):
        values = {key: getattr(self, key) for key in _DEFAULTS}
        if mode == "json":
            return {key: value.isoformat() if isinstance(value, datetime) else value
                    for key, value in values.items()}
        return values

    @property
    def symbol_list(self):
        return [x.strip() for x in self.symbols.split(",") if x.strip()]

    @property
    def crypto_fallback_exchange_list(self):
        return [x.strip().lower() for x in self.crypto_volume_fallback_exchanges.split(",") if x.strip()]
