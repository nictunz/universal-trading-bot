from __future__ import annotations

import json

import pytest

from android.app.src.main.python.mobile_bridge import parse_pasted_backtest_json


def _parse(payload: dict | list) -> dict:
    return json.loads(parse_pasted_backtest_json(json.dumps(payload)))


def test_saved_summary_restores_strategy_and_json_period():
    parsed = _parse({
        "symbol": "BTC/USDT:USDT",
        "timeframe": "5m",
        "requested_start": "2025-09-01",
        "requested_end": "2026-08-31",
        "risk_profile": "공격형",
        "initial_capital": 1000,
        "compounding_enabled": True,
        "execution_model": "signal_close",
        "optimization_base_overrides": {"volume_lookback": 80},
        "risk_profile_selection": {
            "parameters": {"entry_multiplier": 3, "max_pyramiding": 5},
        },
        "return_percent": 260.39,
        "max_drawdown_percent": 41.53,
    })

    assert parsed["symbol"] == "BTC/USDT:USDT"
    assert parsed["requested_start"] == "2025-09-01"
    assert parsed["requested_end"] == "2026-08-31"
    assert parsed["uses_json_period"] is True
    assert parsed["items"][0]["effective_parameters"]["entry_multiplier"] == 3
    assert parsed["items"][0]["effective_parameters"]["volume_lookback"] == 80


def test_full_pipeline_prefers_rolling_final_and_exposes_ranked_choices():
    parsed = _parse({
        "export_type": "full_optimization_pipeline",
        "symbol": "ETH/USDT:USDT",
        "timeframe": "5m",
        "requested_start": "2026-01-01",
        "requested_end": "2026-08-31",
        "rolling_final_selection": {
            "parameters": {"entry_multiplier": 2, "max_pyramiding": 3},
            "result": {"return_percent": 88},
        },
        "top_10_eligible": [{
            "parameters": {"entry_multiplier": 1, "max_pyramiding": 1},
            "result": {"return_percent": 50},
        }],
    })

    assert parsed["items"][0]["effective_parameters"]["entry_multiplier"] == 2
    assert len(parsed["items"]) == 2


def test_stage_ranking_is_accepted():
    parsed = _parse({
        "export_type": "optimization_stage",
        "symbol": "BTC/USDT:USDT",
        "timeframe": "5m",
        "requested_start": "2026-01-01",
        "requested_end": "2026-06-30",
        "result": {
            "ranking": [{
                "parameters": {"entry_multiplier": 1, "max_pyramiding": 2},
                "result": {"return_percent": 10},
            }],
        },
    })

    assert len(parsed["items"]) == 1
    assert parsed["items"][0]["effective_parameters"]["max_pyramiding"] == 2


def test_missing_strategy_parameters_is_rejected():
    with pytest.raises(ValueError, match="전략 파라미터"):
        _parse({
            "symbol": "BTC/USDT:USDT",
            "requested_start": "2026-01-01",
            "requested_end": "2026-01-31",
        })


def test_flat_korean_strategy_json_is_mapped_for_current_screen_period():
    parsed = _parse({
        "name": "BTC 15m 고수익형",
        "symbol": "BTC/USDT:USDT",
        "timeframe": "15m",
        "거래량_SMA_기간": 80,
        "거래량_폭등_배수": 6.0,
        "1봉_변동_최소_pct": 0.1,
        "1봉_변동_최대_pct": 2.4,
        "변동성_기준_봉": 24,
        "TP_변동성_배수": 2.4,
        "SL_변동성_배수": 0.6,
        "TP_최소_pct": 0.3,
        "TP_최대_pct": 2.1,
        "SL_최소_pct": 0.5,
        "SL_최대_pct": 1.0,
        "N_bar_필터_사용": True,
        "N_bar_봉_수": 200,
        "N_bar_최대_변동_pct": 7.3,
        "ADX_필터_사용": False,
        "ADX_길이": 7,
        "ADX_최소": 11.2,
        "ADX_최대": 73.7,
        "RSI_필터_사용": True,
        "RSI_길이": 6,
        "RSI_과매도_최소": 17.4,
        "RSI_과매도_최대": 41.8,
        "RSI_과매수_최소": 72.4,
        "RSI_과매수_최대": 83.6,
        "LONG_허용": True,
        "SHORT_허용": True,
        "최대_피라미딩": 1,
        "쿨다운_봉": 35,
        "재진입_봉": 7,
        "주말_차단": False,
        "제외_시간_UTC": "",
        "진입_비중_pct": 500,
        "백테스트_초기자본": 1000,
        "수수료_pct_side": 0.02,
        "슬리피지_pct_side": 0.01,
    })

    assert parsed["symbol"] == "BTC/USDT:USDT"
    assert parsed["timeframe"] == "15m"
    assert parsed["uses_json_period"] is False
    assert parsed["initial_capital"] == 1000
    assert len(parsed["items"]) == 1
    item = parsed["items"][0]
    assert item["label"] == "BTC 15m 고수익형"
    assert item["effective_parameters"]["volume_lookback"] == 80
    assert item["effective_parameters"]["tp_vol_multiplier"] == 2.4
    assert item["effective_parameters"]["use_adx_filter"] is False
    assert item["effective_parameters"]["rsi_oversold_max"] == 41.8
    assert item["effective_parameters"]["order_percent_of_equity"] == 500
    assert item["effective_parameters"]["entry_multiplier"] == 5.0
    assert item["effective_parameters"]["backtest_fee_percent"] == 0.02
