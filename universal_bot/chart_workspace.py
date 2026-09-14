"""Offline chart replay and indexed diagnostics; never configures a live adapter."""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from contextlib import closing
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path

from universal_bot.config import Settings
from universal_bot.fast_backtest import run_cached_symbol_backtest

V19 = dict(
    volume_lookback=41, volume_break_multiplier=6.4, min_one_bar_vol=0.1,
    max_one_bar_vol=3.6, volatility_bars=36, tp_vol_multiplier=3.8,
    sl_vol_multiplier=1.0, min_tp_percent=0.3, max_tp_percent=2.1,
    min_sl_percent=0.3, max_sl_percent=1.9, use_nbar_volatility_block=True,
    nbar_volatility_bars=200, max_nbar_volatility=6.1, use_rsi_filter=True,
    rsi_length=10, rsi_oversold_min=20.0, rsi_oversold_max=41.5,
    rsi_overbought_min=65.6, rsi_overbought_max=74.7, use_adx_filter=False,
    adx_length=7, adx_min=11.6, adx_max=80.5, cooldown_bars=3, reentry_bars=7,
    block_weekend=False, excluded_hours="", allow_long=True, allow_short=True,
    max_pyramiding=1, first_entry_consecutive_candles=1,
    apply_consecutive_candles_to_all_entries=False, adaptive_regime_enabled=False,
    initial_capital=1000.0, order_percent_of_equity=890.0, leverage=15,
    backtest_max_total_multiplier=15.0, backtest_compounding_enabled=True,
    backtest_execution_model="signal_close", backtest_fee_percent=0.02,
    backtest_slippage_percent=0.01, backtest_margin_mode="crossed",
)
AUDIT_PARAMETERS = set(V19) | {
    "backtest_maintenance_margin_percent", "backtest_cross_liquidation_buffer_percent",
    "regime_lookback_bars", "regime_trend_threshold_percent",
    "regime_high_volatility_percent", "regime_high_volatility_risk_multiplier",
}


def preset() -> str:
    return json.dumps({"symbol": "BTC/USDT:USDT", "timeframe": "15m", "parameters": V19})


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def stamp(path):
    s = Path(path).stat()
    wal = Path(str(path) + "-wal")
    w = wal.stat() if wal.exists() else None
    return {"size": s.st_size, "modified_ns": s.st_mtime_ns,
            "wal_size": w.st_size if w else 0, "wal_modified": w.st_mtime_ns if w else 0}


def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def export_snapshot(source: str, target: str) -> str:
    """Include committed WAL pages when exporting a user database."""
    import contextlib
    with contextlib.closing(readonly(source)) as src, contextlib.closing(sqlite3.connect(target)) as dst, dst:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")
    return target


def apply_strategy(database: str, symbol: str, timeframe: str, parameters: str,
                   cancel_path: str = "", control_check=None) -> str:
    original_check = control_check
    def check():
        if cancel_path and Path(cancel_path).exists():
            raise ValueError("사용자가 전략 계산을 중지했습니다.")
        if original_check:
            original_check()
    control_check = check
    path = Path(database).resolve()
    supplied = json.loads(parameters)
    if not isinstance(supplied, dict):
        raise ValueError("전략 수치는 JSON 객체여야 합니다.")
    # Validate input before model_copy in the cached engine.
    settings = Settings.model_validate({
        **Settings(_env_file=None).model_dump(), **supplied,
        "symbol": symbol, "timeframe": timeframe, "bot_mode": "PAPER",
    })
    for key in AUDIT_PARAMETERS:
        value = getattr(settings, key)
        if isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError(f"유효한 숫자가 필요합니다: {key}")
    for key in ("volume_lookback", "volatility_bars", "nbar_volatility_bars", "adx_length",
                "rsi_length", "first_entry_consecutive_candles", "max_pyramiding"):
        if not 1 <= getattr(settings, key) <= 10000:
            raise ValueError(f"기간/횟수는 1~10000 범위여야 합니다: {key}")
    for key in ("initial_capital", "order_percent_of_equity", "backtest_max_total_multiplier",
                "volume_break_multiplier", "tp_vol_multiplier", "sl_vol_multiplier",
                "min_tp_percent", "max_tp_percent", "min_sl_percent", "max_sl_percent"):
        if getattr(settings, key) <= 0:
            raise ValueError(f"0보다 큰 값이 필요합니다: {key}")
    for key in ("cooldown_bars", "reentry_bars", "min_one_bar_vol", "max_one_bar_vol",
                "backtest_fee_percent", "backtest_slippage_percent"):
        if getattr(settings, key) < 0:
            raise ValueError(f"음수는 허용되지 않습니다: {key}")
    for key in ("rsi_oversold_min", "rsi_oversold_max", "rsi_overbought_min",
                "rsi_overbought_max", "adx_min", "adx_max"):
        if not 0 <= getattr(settings, key) <= 100:
            raise ValueError(f"0~100 범위여야 합니다: {key}")
    if settings.order_percent_of_equity > settings.backtest_max_total_multiplier * 100:
        raise ValueError("1회 진입 규모가 총 노출 한도를 초과합니다.")
    for hour in settings.excluded_hours.split(","):
        if hour.strip() and (not hour.strip().isdigit() or not 0 <= int(hour) <= 23):
            raise ValueError("제외 시간은 00~23을 쉼표로 구분하세요.")
    for lo, hi in [("min_one_bar_vol", "max_one_bar_vol"), ("min_tp_percent", "max_tp_percent"),
                   ("min_sl_percent", "max_sl_percent"), ("rsi_oversold_min", "rsi_oversold_max"),
                   ("rsi_overbought_min", "rsi_overbought_max"), ("adx_min", "adx_max")]:
        if getattr(settings, lo) > getattr(settings, hi):
            raise ValueError(f"입력 범위 오류: {lo} > {hi}")
    if not settings.allow_long and not settings.allow_short:
        raise ValueError("LONG/SHORT 중 하나는 허용해야 합니다.")
    if settings.backtest_execution_model not in ("signal_close", "next_open"):
        raise ValueError("체결 모델은 signal_close 또는 next_open이어야 합니다.")
    before = stamp(path)
    with closing(readonly(path)) as db:
        bounds = db.execute("SELECT min(timestamp),max(timestamp),count(*) FROM ohlcv "
                            "WHERE asset_class='crypto' AND exchange='bitget' AND symbol=? AND timeframe=?",
                            (symbol, timeframe)).fetchone()
    if not bounds or not bounds[2]:
        raise ValueError("선택한 DB에 해당 심볼·주기의 BITGET 캔들이 없습니다.")
    start, end = [datetime.fromtimestamp(t / 1000, timezone.utc).date().isoformat() for t in bounds[:2]]
    warmup = max(200, settings.volume_lookback, settings.volatility_bars,
                 settings.nbar_volatility_bars, settings.adx_length * 3, settings.rsi_length + 10,
                 settings.regime_lookback_bars if settings.adaptive_regime_enabled else 0)
    if bounds[2] <= warmup:
        raise ValueError(f"워밍업 부족: {warmup + 1}봉 이상 필요합니다.")
    name = "chart-backtest-" + uuid.uuid4().hex
    audit = path.parent / (name + ".audit")
    output = path.parent / (name + ".json")
    try:
        with closing(sqlite3.connect(audit)) as db, db:
            db.execute("CREATE TABLE trace(timestamp INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
            def record(row):
                db.execute("INSERT INTO trace VALUES(?,?)", (
                    row["timestamp"], json.dumps(clean(row), ensure_ascii=False, allow_nan=False)))
            result = run_cached_symbol_backtest(
                symbol=symbol, exchange="bitget", timeframe=timeframe, start=start, end=end,
                overrides=settings.model_dump(), database_path=path,
                include_details=True, control_check=control_check, trace_callback=record,
            )
        if stamp(path) != before:
            raise ValueError("계산 중 DB가 변경됐습니다. 다시 적용하세요.")
        result.update(chart_audit_database=str(audit), chart_source=before,
                      effective_parameters={k: settings.model_dump(mode="json")[k]
                                            for k in AUDIT_PARAMETERS},
                      chart_warmup=warmup, chart_period="선택 DB 전체 기간")
        output.write_text(json.dumps(clean(result), ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return json.dumps({"result_path": str(output)}, ensure_ascii=False)
    except BaseException:
        audit.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        raise


@lru_cache(maxsize=2)
def _summary(result_path: str, modified: int):
    value = json.loads(Path(result_path).read_text(encoding="utf-8"))
    return {k: value[k] for k in ("cache_database", "chart_source", "chart_audit_database",
                                 "effective_parameters", "symbol", "timeframe", "chart_warmup")}


def audit_page(result_path: str, first: int, last: int) -> str:
    result_path = str(Path(result_path).resolve())
    summary = _summary(result_path, Path(result_path).stat().st_mtime_ns)
    source = stamp(summary["cache_database"])
    if source != summary.get("chart_source"):
        raise ValueError("DB가 결과 계산 후 변경됐습니다. 전략을 다시 적용하세요.")
    identity = json.dumps([stamp(result_path), source, stamp(summary["chart_audit_database"])], sort_keys=True)
    payload = _audit_page_cached(result_path, first, last, identity)
    current = json.dumps([stamp(result_path), stamp(summary["cache_database"]), stamp(summary["chart_audit_database"])], sort_keys=True)
    if current != identity:
        raise ValueError("진단 로딩 중 DB 또는 결과가 변경됐습니다. 다시 불러오세요.")
    return payload


@lru_cache(maxsize=16)
def _audit_page_cached(result_path: str, first: int, last: int, identity: str) -> str:
    s = _summary(result_path, Path(result_path).stat().st_mtime_ns)
    path = Path(s["cache_database"])
    if stamp(path) != s.get("chart_source"):
        raise ValueError("DB가 결과 계산 후 변경됐습니다. 전략을 다시 적용하세요.")
    with closing(readonly(s["chart_audit_database"])) as db:
        rows = [json.loads(x[0]) for x in db.execute(
            "SELECT payload FROM trace WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp", (first, last))]
        traced_end = db.execute("SELECT max(timestamp) FROM trace").fetchone()[0]
    # Per-exchange audit follows the engine: align to Bitget timestamps, then SMA.
    import pandas as pd
    lookback = int(s["effective_parameters"]["volume_lookback"])
    with closing(readonly(path)) as db:
        base = db.execute("SELECT timestamp FROM ohlcv WHERE asset_class='crypto' AND exchange='bitget' "
                          "AND symbol=? AND timeframe=? AND timestamp<=? ORDER BY timestamp DESC LIMIT ?",
                          (s["symbol"], s["timeframe"], first, lookback)).fetchall()
        lower = min(x[0] for x in base) if base else first
        # Match the composite index prefix; omitting exchange scans unrelated history.
        frame = pd.concat([
            pd.read_sql_query("SELECT timestamp,exchange,volume FROM ohlcv WHERE asset_class='crypto' "
                              "AND exchange=? AND symbol=? AND timeframe=? AND timestamp BETWEEN ? AND ?",
                              db, params=(exchange, s["symbol"], s["timeframe"], lower, last))
            for exchange in ("binance", "bitget", "okx", "bybit")
        ], ignore_index=True)
    ratios = {}
    if not frame.empty:
        wide = frame.pivot(index="timestamp", columns="exchange", values="volume")
        bitget_times = frame.loc[frame.exchange == "bitget", "timestamp"]
        wide = wide.reindex(sorted(bitget_times))
        values = wide / wide.rolling(lookback, min_periods=lookback).mean().replace(0, float("nan"))
        ratios = {int(t): clean(row.to_dict()) for t, row in values.iterrows()}
    for row in rows:
        row["exchanges"] = ratios.get(row["timestamp"], {})
    return json.dumps(clean({"rows": rows, "parameters": s["effective_parameters"],
                             "warmup": s["chart_warmup"], "traced_end": traced_end}), ensure_ascii=False, allow_nan=False)
