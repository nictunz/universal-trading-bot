from __future__ import annotations

import gc
import hashlib
import statistics
import json
import os
import random
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from universal_bot.fast_backtest import run_cached_symbol_backtest
from universal_bot.local_cache_core import (
    DEFAULT_REMOTE_DIR,
    DEFAULT_SERVER,
    DEFAULT_USER,
    build_cache_and_backtest,
    server_upload_eligible,
)



_CONTROL = threading.Condition()
_CONTROL_PAUSED = False
_CONTROL_STOP = False


def reset_optimization_control() -> None:
    global _CONTROL_PAUSED, _CONTROL_STOP
    with _CONTROL:
        _CONTROL_PAUSED = False
        _CONTROL_STOP = False
        _CONTROL.notify_all()


def set_optimization_paused(paused: bool) -> None:
    global _CONTROL_PAUSED
    with _CONTROL:
        _CONTROL_PAUSED = bool(paused)
        _CONTROL.notify_all()


def request_optimization_stop() -> None:
    global _CONTROL_STOP, _CONTROL_PAUSED
    with _CONTROL:
        _CONTROL_STOP = True
        _CONTROL_PAUSED = False
        _CONTROL.notify_all()


def _native_stop_requested() -> bool:
    """Read the Java flag without waiting for a second Python call to acquire the GIL."""
    try:
        from java import jclass
        service = jclass("com.nictunz.universalbacktester.BacktestForegroundService")
        return bool(service.isStopRequested())
    except Exception:
        return False


def _wait_for_optimization_control() -> None:
    with _CONTROL:
        while _CONTROL_PAUSED and not _CONTROL_STOP and not _native_stop_requested():
            _CONTROL.wait(timeout=1.0)
        if _CONTROL_STOP or _native_stop_requested():
            raise RuntimeError("사용자가 백테스트를 중지했습니다. 완료된 체크포인트는 보존됩니다.")


RISK_PROFILES = {
    "공격형": {
        "mdd_limit_percent": 40.0,
        "entry_multiplier_min": 1,
        "entry_multiplier_max": 25,
        "max_entries_values": [1, 2],
    },
    "중간형": {
        "mdd_limit_percent": 25.0,
        "entry_multiplier_min": 1,
        "entry_multiplier_max": 15,
        "max_entries_values": [1, 2],
    },
    "안전형": {
        "mdd_limit_percent": 15.0,
        "entry_multiplier_min": 1,
        "entry_multiplier_max": 8,
        "max_entries_values": [1],
    },
    "3봉 분할형": {
        "mdd_limit_percent": 70.0,
        "entry_multiplier_min": 1,
        "entry_multiplier_max": 3,
        "max_entries_values": [1, 2, 3, 4, 5],
        "first_entry_consecutive_candles": 3,
    },
}

FIXED_BACKTEST = {
    "initial_capital": 1000.0,
    "leverage": 50,
    "backtest_fee_percent": 0.02,
    "backtest_slippage_percent": 0.01,
    "backtest_margin_mode": "crossed",
    "backtest_maintenance_margin_percent": 0.5,
    "backtest_cross_liquidation_buffer_percent": 25.0,
    "backtest_max_total_multiplier": 15.0,
    "backtest_compounding_enabled": True,
}


OPTIMIZED_STRATEGY_FIELDS = (
    "allow_long",
    "allow_short",
    "first_entry_consecutive_candles",
    "order_percent_of_equity",
    "max_pyramiding",
    "volume_lookback",
    "volume_break_multiplier",
    "min_one_bar_vol",
    "max_one_bar_vol",
    "volatility_bars",
    "tp_vol_multiplier",
    "sl_vol_multiplier",
    "min_tp_percent",
    "max_tp_percent",
    "min_sl_percent",
    "max_sl_percent",
    "use_nbar_volatility_block",
    "nbar_volatility_bars",
    "max_nbar_volatility",
    "use_adx_filter",
    "adx_length",
    "adx_min",
    "adx_max",
    "use_rsi_filter",
    "rsi_length",
    "rsi_oversold_min",
    "rsi_oversold_max",
    "rsi_overbought_min",
    "rsi_overbought_max",
    "cooldown_bars",
    "reentry_bars",
    "block_weekend",
    "excluded_hours",
)


def _risk_checkpoint_path(
    output_dir: Path,
    symbol: str,
    timeframe: str,
    start_text: str,
    end_text: str,
    profile: str,
) -> Path:
    raw = f"{symbol}|{timeframe}|{start_text}|{end_text}|{profile}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return output_dir / "Checkpoints" / f"risk-{digest}.json"


def _save_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _append_checkpoint_journal(path: Path, fingerprint: str, key: str, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"strategy_fingerprint": fingerprint, "key": key, "row": row}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def _load_checkpoint_journal(path: Path, fingerprint: str, completed: dict) -> int:
    if not path.is_file():
        return 0
    loaded = 0
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
                if record.get("strategy_fingerprint") != fingerprint:
                    continue
                key = str(record["key"])
                completed[key] = record["row"]
                loaded += 1
            except Exception:
                continue
    return loaded


def _compact_risk_result(result: dict) -> dict:
    keys = (
        "trades", "wins", "win_rate", "profit_factor", "pnl", "gross_pnl",
        "estimated_costs", "return_percent", "max_drawdown_percent",
        "fee_percent_per_side", "slippage_percent_per_side",
        "liquidations", "margin_mode", "maintenance_margin_percent",
        "cross_liquidation_buffer_percent", "max_total_multiplier",
    )
    return {key: result.get(key) for key in keys}


def _profile_candidates(
    profile_name: str,
    trials: int,
    seed_material: str,
) -> list[dict]:
    profile = RISK_PROFILES[profile_name]
    seed = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    candidates: list[dict] = []
    seen: set[str] = set()
    # Stage 1 deliberately uses wide, human-readable buckets. Fine decimal
    # exploration is reserved for stage 2 around the strongest broad regions.
    while len(candidates) < trials:
        one_min = rng.choice([0.05, 0.15, 0.30, 0.45, 0.55])
        one_max = rng.choice([0.40, 0.75, 1.25, 1.75, 2.50])
        if one_max <= one_min:
            one_max = 0.75
        tp_min = rng.choice([0.10, 0.25, 0.40, 0.60, 0.80])
        tp_max = rng.choice([0.50, 1.00, 1.50, 2.00, 3.00])
        if tp_max <= tp_min:
            tp_max = 1.00
        sl_min = rng.choice([0.15, 0.35, 0.60, 0.90, 1.20])
        sl_max = rng.choice([0.80, 1.25, 2.00, 3.00, 4.00])
        if sl_max <= sl_min:
            sl_max = 1.25
        os_max = rng.choice([20.0, 25.0, 30.0, 35.0, 40.0])
        os_min = rng.choice([0.0, 5.0, 10.0, 15.0, 20.0])
        if os_min >= os_max:
            os_min = max(0.0, os_max - 10.0)
        ob_min = rng.choice([60.0, 65.0, 70.0, 75.0, 80.0])
        ob_max = rng.choice([80.0, 85.0, 90.0, 95.0, 100.0])
        if ob_max <= ob_min:
            ob_max = min(100.0, ob_min + 10.0)
        entry = rng.randint(profile["entry_multiplier_min"], profile["entry_multiplier_max"])
        allow_long, allow_short = rng.choice([(True, True), (True, False), (False, True)])
        params = {
            **FIXED_BACKTEST,
            "allow_long": allow_long,
            "allow_short": allow_short,
            "first_entry_consecutive_candles": int(profile.get("first_entry_consecutive_candles", 1)),
            "entry_multiplier": entry,
            "order_percent_of_equity": float(entry * 100),
            "max_pyramiding": rng.choice(profile["max_entries_values"]),
            "volume_lookback": rng.choice([20, 40, 80, 120, 160]),
            "volume_break_multiplier": rng.choice([3.0, 5.0, 10.0, 15.0, 20.0, 25.0]),
            "min_one_bar_vol": one_min,
            "max_one_bar_vol": one_max,
            "volatility_bars": rng.choice([12, 24, 36, 48, 72, 96, 144, 200, 288, 432]),
            "tp_vol_multiplier": rng.choice([0.15, 0.50, 1.00, 1.50, 2.00, 2.50]),
            "sl_vol_multiplier": rng.choice([0.20, 0.75, 1.50, 2.25, 3.00, 3.50]),
            "min_tp_percent": tp_min,
            "max_tp_percent": tp_max,
            "min_sl_percent": sl_min,
            "max_sl_percent": sl_max,
            "use_nbar_volatility_block": rng.random() < 0.75,
            "nbar_volatility_bars": rng.choice([12, 24, 36, 48, 72, 96, 144, 200, 288]),
            "max_nbar_volatility": rng.choice([0.8, 2.0, 4.0, 6.0, 8.0, 10.0]),
            "use_adx_filter": rng.random() < 0.65,
            "adx_length": rng.choice([5, 10, 14, 20, 25, 30]),
            "adx_min": rng.choice([5.0, 10.0, 15.0, 20.0, 25.0, 35.0]),
            "adx_max": rng.choice([45.0, 55.0, 65.0, 75.0, 85.0, 100.0]),
            "use_rsi_filter": rng.random() < 0.85,
            "rsi_length": rng.choice([3, 5, 7, 10, 14, 20, 24]),
            "rsi_oversold_min": os_min,
            "rsi_oversold_max": os_max,
            "rsi_overbought_min": ob_min,
            "rsi_overbought_max": ob_max,
            "cooldown_bars": rng.choice([0, 3, 6, 12, 24, 36]),
            "reentry_bars": rng.choice([0, 3, 6, 12, 18, 24]),
            "block_weekend": rng.random() < 0.15,
            "excluded_hours": rng.choice(["", "00", "00,13,15,16,17,18,23", "13,15,16,17,18,23"]),
        }
        missing = [field for field in OPTIMIZED_STRATEGY_FIELDS if field not in params]
        if missing:
            raise RuntimeError(f"최적화 파라미터 누락: {missing}")
        identity = json.dumps(params, sort_keys=True, separators=(",", ":"))
        if identity not in seen:
            seen.add(identity)
            candidates.append(params)
    return candidates


def _optimize_risk_profile(
    symbol: str,
    timeframe: str,
    start_text: str,
    end_text: str,
    db: Path,
    output_dir: Path,
    base_overrides: dict,
    profile_name: str,
    trials: int,
    log,
    precheck_enabled: bool = True,
    early_stop_patience: int = 0,
) -> tuple[dict, dict]:
    profile = RISK_PROFILES[profile_name]
    checkpoint_path = _risk_checkpoint_path(
        output_dir, symbol, timeframe, start_text, end_text, profile_name
    )
    journal_path = checkpoint_path.with_suffix(".journal.jsonl")
    strategy_fingerprint = hashlib.sha256(
        json.dumps(
            {"base_overrides": base_overrides, "candidate_schema": "coarse-buckets-v2"},
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    checkpoint = {
        "version": 2,
        "candidate_schema": "coarse-buckets-v2",
        "profile": profile_name,
        "constraints": profile,
        "strategy_fingerprint": strategy_fingerprint,
        "completed": {},
    }
    if checkpoint_path.is_file():
        try:
            loaded = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if (
                loaded.get("version") == 2
                and loaded.get("profile") == profile_name
                and loaded.get("strategy_fingerprint") == strategy_fingerprint
            ):
                checkpoint = loaded
                log(f"위험 프로필 체크포인트 재개: {len(checkpoint.get('completed', {}))}개 조합 완료")
            else:
                stale = checkpoint_path.with_suffix(checkpoint_path.suffix + datetime.now(timezone.utc).strftime(".stale-%Y%m%dT%H%M%SZ"))
                checkpoint_path.replace(stale)
                log(f"전략 설정이 변경되어 이전 체크포인트 보존: {stale.name}")
        except Exception:
            damaged = checkpoint_path.with_suffix(checkpoint_path.suffix + datetime.now(timezone.utc).strftime(".damaged-%Y%m%dT%H%M%SZ"))
            checkpoint_path.replace(damaged)
            log(f"손상된 위험 프로필 체크포인트 보존: {damaged.name}")

    completed = checkpoint.setdefault("completed", {})
    journal_rows = _load_checkpoint_journal(journal_path, strategy_fingerprint, completed)
    if journal_rows:
        log(f"증분 체크포인트 복구: {journal_rows}개 기록 · 총 {len(completed)}개 완료")
    seed_material = f"{symbol}|{timeframe}|{start_text}|{end_text}|{profile_name}|coarse-buckets-v2"
    combinations = _profile_candidates(profile_name, trials, seed_material)
    checkpoint["requested_trials"] = trials
    if precheck_enabled and not checkpoint.get("precheck_complete"):
        precheck_start = max(_parse_day(start_text), _parse_day(end_text) - timedelta(days=29)).isoformat()
        passed: list[str] = []
        log(f"빠른 사전검사: 최근 30일 · {len(combinations)}개 후보의 명백한 탈락 조건 확인")
        for pre_position, params in enumerate(combinations, 1):
            _wait_for_optimization_control()
            pre_overrides = dict(base_overrides)
            pre_overrides.update({k: v for k, v in params.items() if k != "entry_multiplier"})
            pre = run_cached_symbol_backtest(
                symbol=symbol, asset_class="crypto", exchange="bitget", timeframe=timeframe,
                start=precheck_start, end=end_text, overrides=pre_overrides, database_path=db,
                control_check=_wait_for_optimization_control, include_details=False,
            )
            identity = json.dumps(params, sort_keys=True, separators=(",", ":"))
            loose_mdd_limit = min(95.0, max(80.0, float(profile["mdd_limit_percent"]) * 1.5))
            if int(pre.get("trades") or 0) > 0 and int(pre.get("liquidations") or 0) == 0 and float(pre.get("max_drawdown_percent") or 0) <= loose_mdd_limit:
                passed.append(identity)
            if pre_position % 25 == 0 or pre_position == len(combinations):
                log(f"사전검사 {pre_position}/{len(combinations)} · 통과 {len(passed)}개")
        if len(passed) >= min(10, max(3, len(combinations) // 10)):
            checkpoint["precheck_passed"] = passed
            log(f"사전검사 완료: {len(combinations)}개 중 {len(passed)}개만 전체 기간 검사")
        else:
            checkpoint["precheck_passed"] = []
            log("사전검사 통과 후보가 너무 적어 안전하게 전체 후보를 검사합니다.")
        checkpoint["precheck_complete"] = True
        _save_json_atomic(checkpoint_path, checkpoint)
    passed_set = set(checkpoint.get("precheck_passed") or [])
    if passed_set:
        combinations = [p for p in combinations if json.dumps(p, sort_keys=True, separators=(",", ":")) in passed_set]
    checkpoint["screened_trials"] = len(combinations)
    best_seen = float("-inf")
    stale_trials = 0
    stopped_early = False
    for position, params in enumerate(combinations, 1):
        _wait_for_optimization_control()
        param_identity = json.dumps(params, sort_keys=True, separators=(",", ":"))
        key = f"trial-{position:04d}-{hashlib.sha256(param_identity.encode('utf-8')).hexdigest()[:10]}"
        if key in completed:
            continue
        overrides = dict(base_overrides)
        engine_params = {k: v for k, v in params.items() if k != "entry_multiplier"}
        overrides.update(engine_params)
        entry = int(params["entry_multiplier"])
        entries = int(params["max_pyramiding"])
        try:
            result = run_cached_symbol_backtest(
                symbol=symbol,
                asset_class="crypto",
                exchange="bitget",
                timeframe=timeframe,
                start=start_text,
                end=end_text,
                overrides=overrides,
                database_path=db,
                control_check=_wait_for_optimization_control,
                include_details=False,
            )
            if float(result.get("fee_percent_per_side", -1)) != 0.02:
                raise RuntimeError("수수료 고정값 불일치")
            if float(result.get("slippage_percent_per_side", -1)) != 0.01:
                raise RuntimeError("슬리피지 고정값 불일치")
            completed[key] = {
                "entry_multiplier": entry,
                "max_entries": entries,
                "parameters": params,
                "result": _compact_risk_result(result),
            }
            checkpoint["last_completed"] = key
            checkpoint["last_error"] = None
            _append_checkpoint_journal(
                journal_path, strategy_fingerprint, key, completed[key]
            )
            if position % 50 == 0 or position == len(combinations):
                _save_json_atomic(checkpoint_path, checkpoint)
            log(
                f"프로필 탐색 {position}/{len(combinations)} · {entry}배/{entries}회 · "
                f"수익률 {float(result.get('return_percent') or 0):.2f}% · "
                f"MDD {float(result.get('max_drawdown_percent') or 0):.2f}%"
            )
            eligible_now = (
                int(result.get("trades") or 0) > 0
                and int(result.get("liquidations") or 0) == 0
                and float(result.get("max_drawdown_percent") or 0) <= profile["mdd_limit_percent"]
            )
            score_now = float(result.get("pnl") or 0) if eligible_now else float("-inf")
            if score_now > best_seen:
                best_seen = score_now
                stale_trials = 0
            else:
                stale_trials += 1
            if early_stop_patience and position >= max(30, early_stop_patience) and stale_trials >= early_stop_patience:
                stopped_early = True
                checkpoint["early_stopped_at"] = position
                _save_json_atomic(checkpoint_path, checkpoint)
                log(f"자동 조기 종료: {early_stop_patience}회 동안 상위 결과 개선 없음 · {position}회에서 종료")
                break
        except Exception as exc:
            checkpoint["last_error"] = f"{key}: {type(exc).__name__}: {exc}"
            _save_json_atomic(checkpoint_path, checkpoint)
            raise
        finally:
            if "result" in locals():
                del result
            if "overrides" in locals():
                del overrides
            if "engine_params" in locals():
                del engine_params
            if position % 25 == 0:
                gc.collect()
                log(f"가속 모드: {position}회 완료 · 주기적 메모리 정리")

    viable = [
        row for row in completed.values()
        if int(row["result"].get("trades") or 0) > 0
        and int(row["result"].get("liquidations") or 0) == 0
        and float(row["result"].get("max_drawdown_percent") or 0) <= profile["mdd_limit_percent"]
    ]
    if not viable:
        raise RuntimeError(
            f"{profile_name} MDD {profile['mdd_limit_percent']:.0f}% 이하 후보가 없습니다."
        )
    viable.sort(
        key=lambda row: (
            float(row["result"].get("pnl") or 0),
            float(row["result"].get("profit_factor") or 0),
            -float(row["result"].get("max_drawdown_percent") or 0),
        ),
        reverse=True,
    )
    best = viable[0]
    best_overrides = dict(base_overrides)
    best_engine_params = {
        key: value for key, value in best["parameters"].items()
        if key != "entry_multiplier"
    }
    best_overrides.update(best_engine_params)
    full_result = run_cached_symbol_backtest(
        symbol=symbol,
        asset_class="crypto",
        exchange="bitget",
        timeframe=timeframe,
        start=start_text,
        end=end_text,
        overrides=best_overrides,
        database_path=db,
        control_check=_wait_for_optimization_control,
    )
    checkpoint["stage"] = "COMPLETE"
    checkpoint["best"] = best
    _save_json_atomic(checkpoint_path, checkpoint)
    journal_path.unlink(missing_ok=True)
    selection = {
        "profile": profile_name,
        "constraints": profile,
        "entry_multiplier": best["entry_multiplier"],
        "max_entries": best["max_entries"],
        "checkpoint": str(checkpoint_path),
        "requested_trials": trials,
        "optimized_strategy_fields": list(OPTIMIZED_STRATEGY_FIELDS),
        "fixed_values": {
            **FIXED_BACKTEST,
            "backtest_compounding_enabled": bool(
                base_overrides.get("backtest_compounding_enabled", True)
            ),
        },
        "tested_combinations": len(completed),
        "screened_combinations": len(combinations),
        "precheck_enabled": bool(precheck_enabled),
        "early_stopped": stopped_early,
        "viable_combinations": len(viable),
        "parameters": best["parameters"],
    }
    return full_result, selection


def _rank_completed_rows(completed: dict, mdd_limit: float) -> list[dict]:
    rows = [
        row for row in completed.values()
        if int((row.get("result") or {}).get("trades") or 0) > 0
        and int((row.get("result") or {}).get("liquidations") or 0) == 0
        and float((row.get("result") or {}).get("max_drawdown_percent") or 0) <= mdd_limit
    ]
    rows.sort(
        key=lambda row: (
            float((row.get("result") or {}).get("return_percent") or 0),
            float((row.get("result") or {}).get("profit_factor") or 0),
            -float((row.get("result") or {}).get("max_drawdown_percent") or 0),
        ),
        reverse=True,
    )
    return rows


def _clamp(value: float, low: float, high: float, digits: int = 2) -> float:
    return round(max(low, min(high, value)), digits)


def _refinement_candidates(top_rows: list[dict], trials_per_seed: int, seed_material: str) -> list[tuple[int, dict]]:
    rng = random.Random(int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16))
    fields = {
        "volume_break_multiplier": (3.0, 25.0, 0.35, 2),
        "min_one_bar_vol": (0.05, 0.55, 0.04, 2),
        "max_one_bar_vol": (0.40, 2.50, 0.08, 2),
        "tp_vol_multiplier": (0.15, 2.50, 0.10, 2),
        "sl_vol_multiplier": (0.20, 3.50, 0.12, 2),
        "min_tp_percent": (0.10, 0.80, 0.04, 2),
        "max_tp_percent": (0.50, 3.00, 0.10, 2),
        "min_sl_percent": (0.15, 1.20, 0.05, 2),
        "max_sl_percent": (0.80, 4.00, 0.12, 2),
        "max_nbar_volatility": (0.80, 10.0, 0.25, 2),
        "adx_min": (5.0, 35.0, 1.0, 1),
        "adx_max": (45.0, 100.0, 2.0, 1),
        "rsi_oversold_min": (0.0, 40.0, 1.0, 1),
        "rsi_oversold_max": (10.0, 50.0, 1.0, 1),
        "rsi_overbought_min": (50.0, 90.0, 1.0, 1),
        "rsi_overbought_max": (60.0, 100.0, 1.0, 1),
    }
    bases = top_rows[:10]
    candidates: list[tuple[int, dict]] = []
    seen: set[str] = set()
    for seed_index, row in enumerate(bases, 1):
        base = dict(row.get("parameters") or {})
        made = 0
        attempts = 0
        while made < trials_per_seed:
            attempts += 1
            if attempts > trials_per_seed * 200 + 1000:
                raise RuntimeError(f"정밀 탐색 후보 생성 실패: TOP{seed_index}에서 중복이 너무 많습니다.")
            params = dict(base)
            for name, (low, high, step, digits) in fields.items():
                if name in params:
                    params[name] = _clamp(float(params[name]) + rng.choice([-2, -1, 0, 1, 2]) * step, low, high, digits)
            for name, low, high, radius in (
                ("volume_lookback", 20, 160, 8),
                ("adx_length", 5, 30, 2),
                ("rsi_length", 3, 24, 2),
                ("cooldown_bars", 0, 36, 3),
                ("reentry_bars", 0, 24, 3),
            ):
                if name in params:
                    params[name] = max(low, min(high, int(params[name]) + rng.randint(-radius, radius)))
            if params.get("min_one_bar_vol", 0) >= params.get("max_one_bar_vol", 1):
                params["max_one_bar_vol"] = _clamp(float(params["min_one_bar_vol"]) + 0.15, 0.40, 2.50)
            if params.get("min_tp_percent", 0) >= params.get("max_tp_percent", 1):
                params["max_tp_percent"] = _clamp(float(params["min_tp_percent"]) + 0.10, 0.50, 3.00)
            if params.get("min_sl_percent", 0) >= params.get("max_sl_percent", 1):
                params["max_sl_percent"] = _clamp(float(params["min_sl_percent"]) + 0.15, 0.80, 4.00)
            identity = json.dumps(params, sort_keys=True, separators=(",", ":"))
            if identity in seen:
                continue
            seen.add(identity)
            candidates.append((seed_index, params))
            made += 1
    return candidates


def _refine_top_candidates(
    symbol: str,
    timeframe: str,
    start_text: str,
    end_text: str,
    db: Path,
    output_dir: Path,
    base_overrides: dict,
    broad_selection: dict,
    trials: int,
    log,
    top_n: int = 10,
) -> dict:
    broad_checkpoint = Path(str(broad_selection["checkpoint"]))
    broad = json.loads(broad_checkpoint.read_text(encoding="utf-8"))
    mdd_limit = float((broad_selection.get("constraints") or {}).get("mdd_limit_percent", 100.0))
    top_rows = _rank_completed_rows(broad.get("completed") or {}, mdd_limit)[:top_n]
    if not top_rows:
        raise RuntimeError(f"1차 탐색에서 정밀 탐색에 사용할 TOP{top_n} 후보가 없습니다.")
    trials_per_seed = min(5000, max(1, int(trials)))
    expected_trials = len(top_rows) * trials_per_seed
    fingerprint = hashlib.sha256(json.dumps({
        "base": base_overrides,
        "broad_checkpoint": str(broad_checkpoint),
        "broad_top10": [row.get("parameters") for row in top_rows],
        "trials_per_seed": trials_per_seed,
        "schema": "top10-independent-refine-v3",
    }, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    path = broad_checkpoint.with_name(broad_checkpoint.stem + "-refined.json")
    state = {"version": 3, "strategy_fingerprint": fingerprint, "completed": {}}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if loaded.get("strategy_fingerprint") == fingerprint:
            state = loaded
            log(f"정밀 탐색 체크포인트 재개: {len(state.get('completed') or {})}/{expected_trials}")
        else:
            stale = path.with_suffix(path.suffix + datetime.now(timezone.utc).strftime(".stale-%Y%m%dT%H%M%SZ"))
            path.replace(stale)
    completed = state.setdefault("completed", {})
    candidates = _refinement_candidates(top_rows[:top_n], trials_per_seed, f"{symbol}|{timeframe}|{start_text}|{end_text}|{fingerprint}")
    for position, (seed_index, params) in enumerate(candidates, 1):
        _wait_for_optimization_control()
        identity = json.dumps(params, sort_keys=True, separators=(",", ":"))
        key = f"refine-top{seed_index:02d}-{position:05d}-{hashlib.sha256(identity.encode()).hexdigest()[:10]}"
        if key in completed:
            continue
        overrides = dict(base_overrides)
        overrides.update({k: v for k, v in params.items() if k != "entry_multiplier"})
        result = run_cached_symbol_backtest(symbol=symbol, asset_class="crypto", exchange="bitget", timeframe=timeframe,
            start=start_text, end=end_text, overrides=overrides, database_path=db,
            control_check=_wait_for_optimization_control, include_details=False)
        completed[key] = {
            "broad_seed_rank": seed_index,
            "entry_multiplier": params.get("entry_multiplier"),
            "max_entries": params.get("max_pyramiding"),
            "parameters": params,
            "result": _compact_risk_result(result),
        }
        state["last_completed"] = key
        if position % 25 == 0 or position == len(candidates):
            _save_json_atomic(path, state)
            log(f"정밀 탐색 {position}/{expected_trials} · TOP10 후보별 {trials_per_seed}회")
        del result, overrides
        gc.collect()
    ranked = _rank_completed_rows(completed, mdd_limit)
    if not ranked:
        raise RuntimeError("정밀 탐색에서 MDD·청산 조건을 통과한 후보가 없습니다.")
    state["stage"] = "COMPLETE"
    state["best"] = ranked[0]
    state["top10_broad_seeds"] = top_rows
    state["trials_per_seed"] = trials_per_seed
    _save_json_atomic(path, state)
    return {
        "checkpoint": str(path),
        "broad_seed_count": len(top_rows),
        "trials_per_seed": trials_per_seed,
        "requested_trials": expected_trials,
        "completed_trials": len(completed),
        "eligible_trials": len(ranked),
        "top_candidates": ranked[:10],
    }


def _parse_day(value: str) -> date:
    return datetime.fromisoformat(value[:10]).date()


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    import calendar
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _month_windows(start_text: str, end_text: str, months: int) -> list[tuple[str, str]]:
    start = _parse_day(start_text)
    end = _parse_day(end_text)
    windows: list[tuple[str, str]] = []
    cursor = start
    while True:
        window_end = _add_months(cursor, months) - timedelta(days=1)
        if window_end > end:
            break
        windows.append((cursor.isoformat(), window_end.isoformat()))
        cursor = _add_months(cursor, 1)
    return windows


def _median_numeric(values: list[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _rolling_validate_candidates(
    symbol: str,
    timeframe: str,
    start_text: str,
    end_text: str,
    db: Path,
    output_dir: Path,
    base_overrides: dict,
    candidate_rows: list[dict],
    source_checkpoint: str,
    months: int,
    log,
    top_n: int = 10,
) -> dict:
    windows = _month_windows(start_text, end_text, months)
    if not windows:
        raise RuntimeError(f"{months}개월 롤링 검증에는 최소 {months}개월의 기간이 필요합니다.")
    candidates = list(candidate_rows or [])[:top_n]
    if not candidates:
        raise RuntimeError(f"{months}개월 롤링 검증 후보가 없습니다.")
    source = Path(str(source_checkpoint))
    path = source.with_name(source.stem + f"-rolling-{months}m.json")
    fingerprint = hashlib.sha256(json.dumps({
        "source": str(source), "months": months, "windows": windows,
        "candidate_parameters": [row.get("parameters") for row in candidates],
    }, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    state = {"version": 2, "strategy_fingerprint": fingerprint, "completed": {}}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if loaded.get("strategy_fingerprint") == fingerprint:
            state = loaded
            log(f"{months}개월 롤링 체크포인트 재개: {len(state.get('completed') or {})}개 구간 완료")
    completed = state.setdefault("completed", {})
    for candidate_index, row in enumerate(candidates, 1):
        params = dict(row.get("parameters") or {})
        overrides = dict(base_overrides)
        overrides.update({k: v for k, v in params.items() if k != "entry_multiplier"})
        identity = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:10]
        for window_index, (window_start, window_end) in enumerate(windows, 1):
            _wait_for_optimization_control()
            key = f"candidate-{candidate_index:02d}-{identity}-window-{window_index:02d}"
            if key in completed:
                continue
            result = run_cached_symbol_backtest(symbol=symbol, asset_class="crypto", exchange="bitget", timeframe=timeframe,
                start=window_start, end=window_end, overrides=overrides, database_path=db,
                control_check=_wait_for_optimization_control, include_details=False)
            completed[key] = {"candidate": candidate_index, "candidate_id": identity, "parameters": params,
                "window_start": window_start, "window_end": window_end, "result": _compact_risk_result(result)}
            if len(completed) % 10 == 0:
                _save_json_atomic(path, state)
                log(f"{months}개월 롤링 검증 {len(completed)}/{len(candidates) * len(windows)}")
            del result
            gc.collect()
    summaries: list[dict] = []
    for candidate_index, row in enumerate(candidates, 1):
        params = dict(row.get("parameters") or {})
        identity = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:10]
        results = [item["result"] for item in completed.values() if item.get("candidate_id") == identity]
        returns = [float(item.get("return_percent") or 0) for item in results]
        pfs = [float(item.get("profit_factor") or 0) for item in results]
        mdds = [float(item.get("max_drawdown_percent") or 0) for item in results]
        trades = [float(item.get("trades") or 0) for item in results]
        summaries.append({
            "candidate": candidate_index, "candidate_id": identity, "parameters": params, "window_count": len(results),
            "positive_windows": sum(value > 0 for value in returns),
            "median_return_percent": _median_numeric(returns),
            "worst_return_percent": min(returns) if returns else 0.0,
            "best_return_percent": max(returns) if returns else 0.0,
            "median_profit_factor": _median_numeric(pfs),
            "worst_mdd_percent": max(mdds) if mdds else 0.0,
            "median_trades": _median_numeric(trades),
        })
    summaries.sort(key=lambda row: (
        int(row["positive_windows"]), float(row["median_return_percent"]), float(row["worst_return_percent"]),
        float(row["median_profit_factor"]), -float(row["worst_mdd_percent"]), float(row["median_trades"]),
    ), reverse=True)
    selected = summaries[0] if summaries else None
    payload = {
        "schema_version": 2, "symbol": symbol, "timeframe": timeframe, "requested_start": start_text, "requested_end": end_text,
        "window_months": months, "window_rule": f"{months} calendar months, shifted by 1 month",
        "selection_rule": "positive windows, median return, worst return, median PF, lower worst MDD, median trades",
        "candidate_count": len(candidates), "window_count": len(windows), "completed_validations": len(completed),
        "ranking": summaries, "selected": selected, "paper_live_applied": False,
    }
    report_path = output_dir / "BacktestResults" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + "-" + re.sub(r"[^A-Za-z0-9]+", "-", symbol).strip("-").lower()
        + f"-{timeframe}-rolling-{months}m-final.json")
    _save_json_atomic(report_path, payload)
    state["stage"] = "COMPLETE"
    state["report"] = str(report_path)
    _save_json_atomic(path, state)
    log(f"{months}개월 롤링 완료 · 후보 {len(candidates)}개 · {len(windows)}구간 · 최종 중간수익률 {float((selected or {}).get('median_return_percent') or 0):.2f}%")
    return {**payload, "checkpoint": str(path), "report_path": str(report_path)}



def _result_quality(summary: dict) -> dict:
    trades = int(summary.get("trades") or 0)
    win_rate = float(summary.get("win_rate") or 0)
    pf = float(summary.get("profit_factor") or 0)
    mdd = float(summary.get("max_drawdown_percent") or 0)
    liquidations = int(summary.get("liquidations") or 0)
    score = 100
    warnings: list[str] = []
    if trades < 30:
        score -= 30
        warnings.append("거래 수가 30회 미만이라 표본이 부족합니다.")
    elif trades < 80:
        score -= 12
        warnings.append("거래 수가 80회 미만입니다.")
    if pf < 1.2:
        score -= 25
        warnings.append("Profit Factor가 1.2 미만입니다.")
    elif pf < 1.5:
        score -= 10
    if mdd > 50:
        score -= 30
        warnings.append("최대 낙폭이 50%를 초과합니다.")
    elif mdd > 30:
        score -= 15
    if liquidations:
        score -= 40
        warnings.append("청산 기록이 있습니다.")
    if win_rate < 45:
        score -= 10
    score = max(0, min(100, score))
    grade = "A" if score >= 85 else ("B" if score >= 70 else ("C" if score >= 50 else "D"))
    return {"grade": grade, "score": score, "warnings": warnings}


def _monthly_performance(trades: list[dict]) -> list[dict]:
    months: dict[str, dict] = {}
    for trade in trades or []:
        month = str(trade.get("exit_time") or trade.get("entry_time") or "")[:7]
        if len(month) != 7:
            continue
        row = months.setdefault(month, {"month": month, "trades": 0, "wins": 0, "pnl": 0.0})
        pnl = float(trade.get("pnl") or 0)
        row["trades"] += 1
        row["wins"] += int(pnl >= 0)
        row["pnl"] += pnl
    for row in months.values():
        row["pnl"] = round(float(row["pnl"]), 6)
        row["win_rate"] = round(row["wins"] / row["trades"] * 100, 2) if row["trades"] else 0.0
    return [months[key] for key in sorted(months)]


def _attach_result_insights(summary: dict, overrides: dict, speed_mode: str, stage: str) -> None:
    summary["quality"] = _result_quality(summary)
    summary["monthly_performance"] = _monthly_performance(list(summary.get("trades_log") or []))
    reproducibility = {
        "symbol": summary.get("symbol"),
        "timeframe": summary.get("timeframe"),
        "requested_start": summary.get("requested_start"),
        "requested_end": summary.get("requested_end"),
        "data_start": summary.get("data_start"),
        "data_end": summary.get("data_end"),
        "cache_sha256": summary.get("cache_sha256"),
        "execution_model": summary.get("execution_model") or overrides.get("backtest_execution_model"),
        "fee_percent_per_side": summary.get("fee_percent_per_side", 0.02),
        "slippage_percent_per_side": summary.get("slippage_percent_per_side", 0.01),
        "compounding_enabled": summary.get("compounding_enabled"),
        "speed_mode": speed_mode,
        "optimization_stage": stage,
        "strategy_overrides": overrides,
        "candidate_seed_rule": "sha256-deterministic",
        "engine_schema": "mobile-backtest-v4",
    }
    encoded = json.dumps(reproducibility, sort_keys=True, separators=(",", ":"), default=str)
    reproducibility["run_signature"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    summary["reproducibility"] = reproducibility


def _ssh_bridge():
    from java import jclass

    return jclass("com.nictunz.universalbacktester.SshBridge")


def defaults() -> str:
    return json.dumps(
        {
            "server": DEFAULT_SERVER,
            "user": DEFAULT_USER,
            "remote_dir": DEFAULT_REMOTE_DIR,
        },
        ensure_ascii=False,
    )


def run_backtest(
    symbol: str,
    timeframe: str,
    start_text: str,
    end_text: str,
    output_dir: str,
    host: str = "",
    username: str = "",
    remote_dir: str = "",
    key_path: str = "",
    risk_profile: str = "공격형",
    broad_optimization_trials: int = 1000,
    refine_optimization_trials: int = 1000,
    compounding_enabled: bool = True,
    optimization_stage: str = "broad",
    all_entries_three_tick: bool = False,
    selected_parameters_json: str = "",
    execution_model: str = "signal_close",
    optimization_speed: str = "quick",
    precheck_enabled: bool = True,
) -> str:
    logs: list[str] = []
    progress_path = Path(output_dir) / "backtest-progress.log"
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text("", encoding="utf-8")

    def log(message: object) -> None:
        line = str(message)
        logs.append(line)
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    log("백그라운드 작업 시작 · 실시간 진행 로그 연결됨")
    replay_payload: dict = {}
    selected_parameters: dict = {}
    original_candidate_result: dict = {}
    source_context: dict = {}
    if str(selected_parameters_json or "").strip():
        replay_payload = json.loads(selected_parameters_json)
        if not isinstance(replay_payload, dict):
            raise ValueError("선택 전략 수치 형식이 올바르지 않습니다.")
        candidate = replay_payload.get("parameters", replay_payload)
        if not isinstance(candidate, dict):
            raise ValueError("선택 전략 파라미터가 없습니다.")
        selected_parameters = dict(candidate)
        original_candidate_result = dict(replay_payload.get("original_result") or {})
        source_context = dict(replay_payload.get("source_context") or {})
    overrides: dict = {}
    if not selected_parameters and host.strip() and username.strip() and remote_dir.strip() and key_path.strip():
        try:
            raw = str(
                _ssh_bridge().readStrategySettings(
                    host.strip(), username.strip(), remote_dir.strip(), key_path.strip()
                )
            )
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                overrides = parsed
        except Exception as exc:
            log(
                f"서버 전략 설정 동기화 실패 - 현재 앱 기본값 사용: {type(exc).__name__}: {exc}"
            )
    selected_profile = risk_profile.strip() if risk_profile else "공격형"
    selected_stage = (optimization_stage or "broad").strip().lower()
    speed_mode = (optimization_speed or "quick").strip().lower()
    if speed_mode not in {"quick", "standard", "deep"}:
        speed_mode = "quick"
    speed_presets = {
        "quick": {"label": "빠른", "broad": 100, "refine": 100, "top_n": 3},
        "standard": {"label": "표준", "broad": 500, "refine": 300, "top_n": 5},
        "deep": {"label": "정밀", "broad": 5000, "refine": 5000, "top_n": 10},
    }
    speed_preset = speed_presets[speed_mode]
    if selected_stage not in {"broad", "refine", "rolling", "auto"}:
        selected_stage = "broad"
    broad_optimization_trials = min(int(broad_optimization_trials), int(speed_preset["broad"]))
    refine_optimization_trials = min(int(refine_optimization_trials), int(speed_preset["refine"]))
    optimization_top_n = int(speed_preset["top_n"])
    early_stop_patience = 40 if speed_mode == "quick" else (150 if speed_mode == "standard" else 0)
    if not 1 <= broad_optimization_trials <= 5000:
        raise ValueError("1차 최적화 조합 수는 1~5000이어야 합니다.")
    if not 1 <= refine_optimization_trials <= 5000:
        raise ValueError("정밀 최적화 후보당 조합 수는 1~5000이어야 합니다.")
    if selected_profile not in RISK_PROFILES:
        selected_profile = "공격형"
    if selected_parameters:
        overrides.update({
            key: value for key, value in selected_parameters.items()
            if key != "entry_multiplier"
        })
    overrides.update(FIXED_BACKTEST)
    if selected_parameters:
        overrides["backtest_compounding_enabled"] = bool(
            selected_parameters.get("backtest_compounding_enabled", compounding_enabled)
        )
        requested_replay_model = str(
            replay_payload.get("execution_model_override")
            or selected_parameters.get("backtest_execution_model")
            or "signal_close"
        ).strip().lower()
        overrides["backtest_execution_model"] = (
            requested_replay_model if requested_replay_model in {"signal_close", "next_open"}
            else "signal_close"
        )
        entry_multiplier = float(selected_parameters.get("entry_multiplier", 1.0))
        overrides["order_percent_of_equity"] = float(
            selected_parameters.get("order_percent_of_equity", entry_multiplier * 100.0)
        )
        overrides["max_pyramiding"] = int(selected_parameters.get("max_pyramiding", 1))
        log("TOP10 선택 전략: 저장된 모든 전략 수치를 그대로 적용 · 재최적화 없음")
    else:
        overrides["backtest_compounding_enabled"] = bool(compounding_enabled)
        normalized_execution_model = str(execution_model or "signal_close").strip().lower()
        overrides["backtest_execution_model"] = (
            normalized_execution_model if normalized_execution_model in {"signal_close", "next_open"}
            else "signal_close"
        )
        overrides["order_percent_of_equity"] = 100.0
        overrides["max_pyramiding"] = 1
        overrides["apply_consecutive_candles_to_all_entries"] = bool(all_entries_three_tick)
    profile = RISK_PROFILES[selected_profile]
    log(
        f"위험 프로필: {selected_profile} · MDD {profile['mdd_limit_percent']:.0f}% 이하 · "
        f"진입 {profile['entry_multiplier_min']}~{profile['entry_multiplier_max']}배 · "
        f"최대 진입 {profile['max_entries_values']}"
    )
    stage_names = {
        "broad": "1차 전체 탐색",
        "refine": "상위 후보 정밀 탐색",
        "rolling": "6개월 → 3개월 롤링 + 최종 선정",
        "auto": "전체 자동 실행",
    }
    log(f"최적화 단계: {stage_names[selected_stage]}")
    log(f"속도 모드: {speed_preset['label']} · 1차 {broad_optimization_trials}회 · 후속 TOP{optimization_top_n}×{refine_optimization_trials}회")
    log("재실행 가속: 동일 설정 체크포인트와 완료 결과를 자동 재사용합니다.")
    log(f"빠른 사전검사: {'사용' if precheck_enabled else '사용 안 함'} · 자동 조기 종료: {early_stop_patience or '사용 안 함'}")
    log("기간은 사용자가 선택한 날짜를 그대로 사용합니다.")
    log("고정 비용: 수수료 편도 0.02% · 슬리피지 편도 0.01%")
    log(
        "체결 모델: "
        + ("현실형 · 신호 확정 후 다음 봉 시가" if overrides.get("backtest_execution_model") == "next_open"
           else "기존형 · 신호 봉 종가")
    )
    if bool(overrides.get("backtest_compounding_enabled", True)):
        log("계산 방식: 복리식 · 매 진입 시 현재 순자산 기준으로 주문 규모와 최대 총노출 재계산")
    else:
        log("계산 방식: 고정식 · 최초자본 1,000 USDT 기준으로 주문 규모와 최대 총노출 유지")
    log("교차마진 청산: 총노출 최대 15배 · 15배에서 약 5% 역행 시 보수적 청산")
    log(f"3틱룰 적용: {'모든 진입' if all_entries_three_tick else '첫 진입만'}")

    db, result, summary = build_cache_and_backtest(
        symbol.strip(),
        timeframe.strip(),
        start_text.strip(),
        end_text.strip(),
        Path(output_dir),
        log,
        strategy_overrides=overrides,
        control_check=_wait_for_optimization_control,
    )
    if selected_parameters:
        summary["risk_profile"] = selected_profile
        summary["selected_strategy_retest"] = True
        summary["selected_strategy_parameters"] = selected_parameters
        summary["selected_strategy_original_result"] = original_candidate_result
        summary["selected_strategy_source_context"] = source_context
        original_return = float(original_candidate_result.get("return_percent") or 0)
        original_mdd = float(original_candidate_result.get("max_drawdown_percent") or 0)
        same_period = (
            str(source_context.get("requested_start") or "") == start_text.strip()
            and str(source_context.get("requested_end") or "") == end_text.strip()
        )
        same_cache = str(source_context.get("cache_sha256") or "") == str(summary.get("cache_sha256") or "")
        source_execution_model = str(source_context.get("execution_model") or "signal_close")
        same_execution_model = source_execution_model == str(overrides.get("backtest_execution_model"))
        summary["reproduction_comparison"] = {
            "same_requested_period": same_period,
            "same_cache_sha256": same_cache,
            "same_execution_model": same_execution_model,
            "original_execution_model": source_execution_model,
            "retest_execution_model": overrides.get("backtest_execution_model"),
            "original_return_percent": original_return,
            "retest_return_percent": float(summary.get("return_percent") or 0),
            "return_difference_percent_points": float(summary.get("return_percent") or 0) - original_return,
            "original_mdd_percent": original_mdd,
            "retest_mdd_percent": float(summary.get("max_drawdown_percent") or 0),
            "mdd_difference_percent_points": float(summary.get("max_drawdown_percent") or 0) - original_mdd,
        }
        summary["optimization_pipeline"] = {
            "stage": "selected_strategy_retest",
            "paper_live_applied": False,
        }
        _attach_result_insights(summary, overrides, speed_mode, "selected_strategy_retest")
        history_dir = Path(output_dir) / "BacktestResults"
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        slug = re.sub(r"[^A-Za-z0-9]+", "-", symbol.strip()).strip("-").lower()
        archive = history_dir / f"{stamp}-{slug}-{timeframe.strip()}-selected-strategy-backtest.json"
        archive.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log(
            f"선택 전략 기간 재백테스트 완료 · 수익률 {float(summary.get('return_percent') or 0):.2f}% · "
            f"MDD {float(summary.get('max_drawdown_percent') or 0):.2f}%"
        )
        return json.dumps({"db": str(db), "result": str(archive), "summary": summary, "logs": logs}, ensure_ascii=False)
    del result
    summary.pop("equity_curve", None)
    summary.pop("trades_log", None)
    gc.collect()
    log("휴대폰 가속 모드: 대형 기준 결과 메모리 해제 · 불필요한 trial별 대기 제거")
    broad_trials = broad_optimization_trials
    refine_trials_per_seed = refine_optimization_trials
    log(
        f"단계별 배분: 1차 {broad_trials}회 → 수익률 TOP{optimization_top_n} 각각 정밀 {refine_trials_per_seed}회 "
        f"(최대 {refine_trials_per_seed * optimization_top_n}회) → 6개월 롤링 → 3개월 롤링"
    )
    optimized_result, risk_selection = _optimize_risk_profile(
        symbol.strip(),
        timeframe.strip(),
        start_text.strip(),
        end_text.strip(),
        Path(db),
        Path(output_dir),
        overrides,
        selected_profile,
        broad_trials,
        log,
        bool(precheck_enabled),
        early_stop_patience,
    )
    for key in (
        "trades", "wins", "win_rate", "profit_factor", "pnl", "gross_pnl",
        "estimated_costs", "return_percent", "max_drawdown_percent",
        "trades_log", "equity_curve", "data_start", "data_end",
        "liquidations", "margin_mode", "maintenance_margin_percent",
        "cross_liquidation_buffer_percent", "max_total_multiplier",
        "compounding_enabled", "sizing_mode",
        "execution_model",
    ):
        summary[key] = optimized_result.get(key)
    summary["risk_profile"] = selected_profile
    summary["risk_profile_selection"] = risk_selection
    summary["optimization_base_overrides"] = overrides
    pipeline: dict = {
        "stage": selected_stage,
        "broad": {
            "tested_combinations": risk_selection.get("tested_combinations"),
            "viable_combinations": risk_selection.get("viable_combinations"),
            "checkpoint": risk_selection.get("checkpoint"),
        },
        "paper_live_applied": False,
    }
    if selected_stage in {"refine", "rolling", "auto"}:
        refined = _refine_top_candidates(
            symbol.strip(), timeframe.strip(), start_text.strip(), end_text.strip(),
            Path(db), Path(output_dir), overrides, risk_selection,
            refine_trials_per_seed, log, optimization_top_n,
        )
        pipeline["refined"] = {
            key: value for key, value in refined.items() if key != "top_candidates"
        }
    if selected_stage in {"rolling", "auto"}:
        rolling_6m = _rolling_validate_candidates(
            symbol.strip(), timeframe.strip(), start_text.strip(), end_text.strip(),
            Path(db), Path(output_dir), overrides, list(refined.get("top_candidates") or [])[:optimization_top_n],
            str(refined.get("checkpoint") or ""), 6, log, optimization_top_n,
        )
        rolling_3m = _rolling_validate_candidates(
            symbol.strip(), timeframe.strip(), start_text.strip(), end_text.strip(),
            Path(db), Path(output_dir), overrides, list(rolling_6m.get("ranking") or [])[:optimization_top_n],
            str(rolling_6m.get("checkpoint") or ""), 3, log, optimization_top_n,
        )
        pipeline["rolling_6m"] = {key: value for key, value in rolling_6m.items() if key != "ranking"}
        pipeline["rolling_3m"] = {key: value for key, value in rolling_3m.items() if key != "ranking"}
        summary["rolling_6m_report_path"] = rolling_6m.get("report_path")
        summary["rolling_3m_report_path"] = rolling_3m.get("report_path")
        summary["rolling_final_selection"] = rolling_3m.get("selected")
        summary["rolling_report_path"] = rolling_3m.get("report_path")
    summary["optimization_pipeline"] = pipeline
    _attach_result_insights(summary, overrides, speed_mode, selected_stage)
    history_dir = Path(output_dir) / "BacktestResults"
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", symbol.strip()).strip("-").lower()
    archive = history_dir / f"{stamp}-{slug}-{timeframe.strip()}-backtest.json"
    archive.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return json.dumps(
        {
            "db": str(db),
            "result": str(archive),
            "summary": summary,
            "logs": logs,
        },
        ensure_ascii=False,
    )


_HEAVY_SAVED_RESULT_FIELDS = {
    "trades_log",
    "equity_curve",
    "all_trials",
    "optimization_results",
}


def _compact_saved_summary(meta: dict) -> dict:
    """Keep activity startup IPC small even when years of trades are stored."""
    return {
        key: value
        for key, value in meta.items()
        if key not in _HEAVY_SAVED_RESULT_FIELDS
    }


def list_saved_results(output_dir: str, limit: int = 20) -> str:
    history_dir = Path(output_dir) / "BacktestResults"
    items: list[dict] = []
    candidates = list(history_dir.glob("*-backtest.json")) if history_dir.is_dir() else []
    candidates.extend(Path(output_dir).glob("*backtest.json"))
    # Android only needs recent entries for the picker. Reading and returning every
    # multi-year result here can exceed the app heap before the screen is displayed.
    recent = sorted(
        set(candidates), key=lambda p: p.stat().st_mtime, reverse=True
    )[: max(1, min(int(limit), 50))]
    for path in recent:
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
            db = Path(str(meta.get("database", "")))
            if not db.is_file():
                continue
            summary = _compact_saved_summary(meta)
            items.append(
                {
                    "path": str(path),
                    "db": str(db),
                    "summary": summary,
                    "details_available": any(
                        key in meta for key in ("trades_log", "equity_curve")
                    ),
                    "label": (
                        f"{meta.get('symbol', '-')} · {meta.get('requested_start', '-')}~"
                        f"{meta.get('requested_end', '-')} · {meta.get('created_at', '-')}"
                    ),
                }
            )
            del meta
        except Exception:
            continue
    return json.dumps({"items": items}, ensure_ascii=False)


def load_saved_result(result_path: str, include_details: bool = False) -> str:
    path = Path(result_path)
    if not path.is_file():
        raise RuntimeError(f"저장된 결과 파일이 없습니다: {result_path}")
    meta = json.loads(path.read_text(encoding="utf-8"))
    db = Path(str(meta.get("database", "")))
    if not db.is_file():
        raise RuntimeError(f"연결된 캐시 DB가 없습니다: {db}")
    summary = meta if include_details else _compact_saved_summary(meta)
    return json.dumps(
        {
            "result": str(path),
            "db": str(db),
            "summary": summary,
            "details_available": any(
                key in meta for key in ("trades_log", "equity_curve")
            ),
        },
        ensure_ascii=False,
    )


def list_top_strategies(result_path: str, limit: int = 10) -> str:
    """Return selectable highest-return candidates with their complete parameters."""
    result_file = Path(result_path)
    if not result_file.is_file():
        raise RuntimeError(f"결과 파일이 없습니다: {result_path}")
    summary = json.loads(result_file.read_text(encoding="utf-8"))
    if summary.get("selected_strategy_retest"):
        raise RuntimeError("이 결과는 선택 전략 재백테스트입니다. 원래 최적화 결과를 불러오세요.")
    selection = summary.get("risk_profile_selection") or {}
    pipeline = summary.get("optimization_pipeline") or {}
    refined = pipeline.get("refined") or {}
    checkpoint_text = str(refined.get("checkpoint") or selection.get("checkpoint") or "")
    checkpoint_path = Path(checkpoint_text)
    if not checkpoint_path.is_file():
        raise RuntimeError("TOP10 후보 체크포인트가 없습니다.")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    rows = list((checkpoint.get("completed") or {}).values())
    mdd_limit = float((selection.get("constraints") or {}).get("mdd_limit_percent", 100.0))
    eligible = [
        row for row in rows
        if int((row.get("result") or {}).get("trades") or 0) > 0
        and int((row.get("result") or {}).get("liquidations") or 0) == 0
        and float((row.get("result") or {}).get("max_drawdown_percent") or 0) <= mdd_limit
        and isinstance(row.get("parameters"), dict)
    ]
    eligible.sort(key=lambda row: (
        float((row.get("result") or {}).get("return_percent") or 0),
        float((row.get("result") or {}).get("profit_factor") or 0),
        -float((row.get("result") or {}).get("max_drawdown_percent") or 0),
    ), reverse=True)
    count = max(1, min(int(limit), 10))
    base_overrides = dict(summary.get("optimization_base_overrides") or {})
    if not base_overrides:
        # Backward compatibility for optimization results made before the replay
        # snapshot was stored. Candidate fields still reproduce all optimized values.
        base_overrides.update(FIXED_BACKTEST)
        base_overrides["backtest_compounding_enabled"] = bool(
            summary.get("compounding_enabled", True)
        )
    items: list[dict] = []
    for rank, row in enumerate(eligible[:count], 1):
        parameters = dict(row.get("parameters") or {})
        effective = dict(base_overrides)
        effective.update(parameters)
        entry = float(parameters.get("entry_multiplier", 1.0))
        effective["entry_multiplier"] = entry
        effective["order_percent_of_equity"] = float(
            parameters.get("order_percent_of_equity", entry * 100.0)
        )
        item = dict(row)
        item["rank"] = rank
        item["effective_parameters"] = effective
        item["source_context"] = {
            "source_result": str(result_file),
            "requested_start": summary.get("requested_start"),
            "requested_end": summary.get("requested_end"),
            "data_start": summary.get("data_start"),
            "data_end": summary.get("data_end"),
            "cache_sha256": summary.get("cache_sha256"),
            "execution_model": summary.get("execution_model") or base_overrides.get("backtest_execution_model", "signal_close"),
        }
        items.append(item)
    return json.dumps({
        "items": items,
        "source": "refined" if refined.get("checkpoint") else "broad",
        "mdd_limit_percent": mdd_limit,
    }, ensure_ascii=False)



def export_optimization_results(result_path: str) -> str:
    """Export every automatic-optimization stage without hiding high-MDD trials."""
    result_file = Path(result_path)
    if not result_file.is_file():
        raise RuntimeError(f"결과 파일이 없습니다: {result_path}")
    summary = json.loads(result_file.read_text(encoding="utf-8"))
    selection = summary.get("risk_profile_selection") or {}
    mdd_limit = float((selection.get("constraints") or {}).get("mdd_limit_percent", 100.0))

    def checkpoint_ranking(raw_path: str) -> dict:
        checkpoint_path = Path(str(raw_path or ""))
        if not checkpoint_path.is_file():
            return {
                "checkpoint": str(checkpoint_path),
                "available": False,
                "completed_trials": 0,
                "eligible_trials": 0,
                "mdd_over_limit_trials": 0,
                "duplicate_trials_removed": 0,
                "top_30_overall": [],
                "top_30_eligible": [],
                "top_30_mdd_over_limit": [],
                "all_mdd_over_limit": [],
                "all_trials": [],
            }
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        completed = checkpoint.get("completed") or {}
        rankings: list[dict] = []
        seen_parameters: set[str] = set()
        duplicate_trials = 0
        for trial_id, row in completed.items():
            parameters = row.get("parameters") or {}
            identity = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
            if identity in seen_parameters:
                duplicate_trials += 1
                continue
            seen_parameters.add(identity)
            result = dict(row.get("result") or {})
            trades = int(result.get("trades") or 0)
            mdd = float(result.get("max_drawdown_percent") or 0)
            liquidations = int(result.get("liquidations") or 0)
            rankings.append({
                "trial_id": trial_id,
                "eligible": trades > 0 and liquidations == 0 and mdd <= mdd_limit,
                "mdd_over_limit": mdd > mdd_limit,
                "entry_multiplier": row.get("entry_multiplier"),
                "max_entries": row.get("max_entries"),
                "return_percent": result.get("return_percent"),
                "pnl": result.get("pnl"),
                "profit_factor": result.get("profit_factor"),
                "max_drawdown_percent": result.get("max_drawdown_percent"),
                "trades": result.get("trades"),
                "wins": result.get("wins"),
                "win_rate": result.get("win_rate"),
                "estimated_costs": result.get("estimated_costs"),
                "liquidations": liquidations,
                "parameters": parameters,
                "result": result,
            })
        rankings.sort(key=lambda row: (
            float(row.get("return_percent") or 0),
            float(row.get("profit_factor") or 0),
            -float(row.get("max_drawdown_percent") or 0),
        ), reverse=True)
        for rank, row in enumerate(rankings, 1):
            row["overall_rank"] = rank
        eligible = [row for row in rankings if row["eligible"]]
        over_limit = [row for row in rankings if row["mdd_over_limit"]]
        for rank, row in enumerate(eligible, 1):
            row["eligible_rank"] = rank
        for rank, row in enumerate(over_limit, 1):
            row["mdd_over_limit_rank"] = rank
        return {
            "checkpoint": str(checkpoint_path),
            "available": True,
            "completed_trials": len(rankings),
            "eligible_trials": len(eligible),
            "mdd_over_limit_trials": len(over_limit),
            "duplicate_trials_removed": duplicate_trials,
            "top_30_overall": rankings[:30],
            "top_30_eligible": eligible[:30],
            "top_30_mdd_over_limit": over_limit[:30],
            "all_mdd_over_limit": over_limit,
            "all_trials": rankings,
        }

    broad = checkpoint_ranking(str(selection.get("checkpoint") or ""))
    if not broad["available"]:
        raise RuntimeError(f"최적화 체크포인트가 없습니다: {broad['checkpoint']}")

    pipeline = summary.get("optimization_pipeline") or {}
    refined_meta = pipeline.get("refined") or {}
    refined = checkpoint_ranking(str(refined_meta.get("checkpoint") or ""))
    rolling_report_path = Path(str(summary.get("rolling_report_path") or ""))
    rolling_report = json.loads(rolling_report_path.read_text(encoding="utf-8")) if rolling_report_path.is_file() else None
    rolling_6m_path = Path(str(summary.get("rolling_6m_report_path") or ""))
    rolling_3m_path = Path(str(summary.get("rolling_3m_report_path") or summary.get("rolling_report_path") or ""))
    rolling_6m_report = json.loads(rolling_6m_path.read_text(encoding="utf-8")) if rolling_6m_path.is_file() else None
    rolling_3m_report = json.loads(rolling_3m_path.read_text(encoding="utf-8")) if rolling_3m_path.is_file() else None

    payload = {
        "schema_version": 2,
        "export_type": "full_optimization_pipeline",
        "source_result": str(result_file),
        "symbol": summary.get("symbol"),
        "timeframe": summary.get("timeframe"),
        "requested_start": summary.get("requested_start"),
        "requested_end": summary.get("requested_end"),
        "risk_profile": summary.get("risk_profile"),
        "fixed_values": selection.get("fixed_values"),
        "constraints": selection.get("constraints"),
        "ranking_rule": "return_percent desc, profit_factor desc, max_drawdown_percent asc",
        "mdd_policy": (
            f"MDD {mdd_limit:g}% 초과 후보도 보존·표시하지만 적격 후보 및 "
            "PAPER/LIVE 자동 적용 대상에서는 제외"
        ),
        "broad": broad,
        "refined": refined,
        "rolling_report_path": str(rolling_report_path),
        "rolling_report": rolling_report,
        "rolling_6m_report_path": str(rolling_6m_path),
        "rolling_6m_report": rolling_6m_report,
        "rolling_3m_report_path": str(rolling_3m_path),
        "rolling_3m_report": rolling_3m_report,
        "rolling_final_selection": summary.get("rolling_final_selection"),
        # Backward-compatible keys for existing readers.
        "source_checkpoint": broad["checkpoint"],
        "completed_trials": broad["completed_trials"],
        "duplicate_trials_removed": broad["duplicate_trials_removed"],
        "eligible_trials": broad["eligible_trials"],
        "mdd_over_limit_trials": broad["mdd_over_limit_trials"],
        "top_10_overall": broad["top_30_overall"][:10],
        "top_10_eligible": broad["top_30_eligible"][:10],
        "top_10_mdd_over_limit": broad["top_30_mdd_over_limit"][:10],
        "all_mdd_over_limit": broad["all_mdd_over_limit"],
        "all_trials": broad["all_trials"],
    }
    export_path = result_file.with_name(
        result_file.stem + "-full-optimization-pipeline.json"
    )
    _save_json_atomic(export_path, payload)
    return json.dumps({
        "path": str(export_path),
        "completed_trials": broad["completed_trials"],
        "duplicate_trials_removed": broad["duplicate_trials_removed"],
        "eligible_trials": broad["eligible_trials"],
        "mdd_over_limit_trials": broad["mdd_over_limit_trials"],
        "refined_trials": refined["completed_trials"],
        "rolling_candidates": len((rolling_report or {}).get("ranking") or []),
    }, ensure_ascii=False)


def export_optimization_stage(result_path: str, stage: str) -> str:
    stage_key = str(stage or "").strip().lower()
    full_meta = json.loads(export_optimization_results(result_path))
    full_path = Path(full_meta["path"])
    payload = json.loads(full_path.read_text(encoding="utf-8"))
    stage_map = {
        "broad": ("01-broad-ranking", payload.get("broad"), "1차 전체 탐색"),
        "refined": ("02-refined-ranking", payload.get("refined"), "2차 정밀 탐색"),
        "rolling6": ("03-rolling-6m", payload.get("rolling_6m_report"), "3차 6개월 롤링"),
        "rolling3": ("04-rolling-3m", payload.get("rolling_3m_report"), "4차 3개월 롤링"),
        "final": ("05-final-selection", payload.get("rolling_final_selection"), "5차 최종 선정"),
    }
    if stage_key not in stage_map:
        raise RuntimeError(f"지원하지 않는 결과 단계입니다: {stage}")
    suffix, data, label = stage_map[stage_key]
    if data is None:
        raise RuntimeError(f"{label} 결과가 없습니다. 해당 단계까지 최적화를 완료했는지 확인하세요.")
    stage_payload = {
        "schema_version": 1,
        "export_type": "optimization_stage",
        "stage": stage_key,
        "stage_label": label,
        "source_result": payload.get("source_result"),
        "symbol": payload.get("symbol"),
        "timeframe": payload.get("timeframe"),
        "requested_start": payload.get("requested_start"),
        "requested_end": payload.get("requested_end"),
        "risk_profile": payload.get("risk_profile"),
        "constraints": payload.get("constraints"),
        "ranking_rule": payload.get("ranking_rule"),
        "mdd_policy": payload.get("mdd_policy"),
        "result": data,
    }
    out = Path(result_path).with_name(Path(result_path).stem + f"-{suffix}.json")
    _save_json_atomic(out, stage_payload)
    if isinstance(data, dict) and "completed_trials" in data:
        count = int(data.get("completed_trials") or 0)
    elif isinstance(data, dict) and isinstance(data.get("ranking"), list):
        count = len(data.get("ranking") or [])
    elif isinstance(data, list):
        count = len(data)
    else:
        count = 1
    return json.dumps({"path": str(out), "stage": stage_key, "label": label, "count": count}, ensure_ascii=False)


def ensure_ssh_key(app_files_dir: str) -> str:
    return str(_ssh_bridge().ensureKey(app_files_dir))


def test_ssh(host: str, username: str, key_path: str) -> str:
    return str(_ssh_bridge().testConnection(host.strip(), username.strip(), key_path.strip()))


def inspect_server_cache(
    host: str,
    username: str,
    remote_dir: str,
    key_path: str,
) -> str:
    return str(
        _ssh_bridge().inspectServerCache(
            host.strip(),
            username.strip(),
            remote_dir.strip(),
            key_path.strip(),
        )
    )


def upload_result(
    db_path: str,
    result_path: str,
    host: str,
    username: str,
    remote_dir: str,
    key_path: str,
) -> str:
    result_file = Path(result_path)
    if not result_file.is_file():
        raise RuntimeError(f"결과 파일이 없습니다: {result_path}")

    meta = json.loads(result_file.read_text(encoding="utf-8"))
    start_text = str(meta.get("requested_start", ""))
    end_text = str(meta.get("requested_end", ""))
    if not start_text or not end_text or not server_upload_eligible(start_text, end_text):
        raise RuntimeError("서버 업로드 차단: 1일~10년 범위로 완료·검증된 캐시만 업로드할 수 있습니다.")
    if not bool(meta.get("server_upload_eligible", False)):
        raise RuntimeError("서버 업로드 차단: 결과 파일이 서버 업로드용으로 검증되지 않았습니다.")

    from universal_bot.local_cache_core import cache_file_names
    canonical_name = cache_file_names(
        str(meta.get("symbol", "")),
        str(meta.get("timeframe", "5m")),
        start_text,
        end_text,
    )[1]
    canonical_result = result_file.parent.parent / canonical_name
    # The phone keeps the large SQLite cache and full trade/equity details.
    # The low-cost trading server receives only an auditable compact summary.
    server_summary = {
        key: value
        for key, value in meta.items()
        if key not in _HEAVY_SAVED_RESULT_FIELDS
    }
    server_summary["upload_mode"] = "summary_only"
    server_summary["source_result_sha256"] = hashlib.sha256(
        result_file.read_bytes()
    ).hexdigest()
    selection = dict(server_summary.get("risk_profile_selection") or {})
    selection.pop("checkpoint", None)
    if selection:
        server_summary["risk_profile_selection"] = selection
    canonical_result.write_text(
        json.dumps(server_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return str(
        _ssh_bridge().uploadFiles(
            "",
            str(canonical_result),
            host.strip(),
            username.strip(),
            remote_dir.strip(),
            key_path.strip(),
        )
    )
