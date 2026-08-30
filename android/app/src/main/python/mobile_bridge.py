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


def _wait_for_optimization_control() -> None:
    with _CONTROL:
        while _CONTROL_PAUSED and not _CONTROL_STOP:
            _CONTROL.wait(timeout=1.0)
        if _CONTROL_STOP:
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
        "mdd_limit_percent": 40.0,
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
            gc.collect()
            time.sleep(1.5 if position % 10 == 0 else 0.20)
            if position % 25 == 0:
                log(f"안전 모드: {position}회 완료 · 메모리 정리 및 냉각 완료")

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
        "tested_combinations": len(combinations),
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


def _refinement_candidates(top_rows: list[dict], trials: int, seed_material: str) -> list[dict]:
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
    candidates: list[dict] = []
    seen: set[str] = set()
    bases = top_rows[: min(30, len(top_rows))]
    if not bases:
        return candidates
    cursor = 0
    while len(candidates) < trials:
        base = dict(bases[cursor % len(bases)].get("parameters") or {})
        cursor += 1
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
        if identity not in seen:
            seen.add(identity)
            candidates.append(params)
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
) -> dict:
    broad_checkpoint = Path(str(broad_selection["checkpoint"]))
    broad = json.loads(broad_checkpoint.read_text(encoding="utf-8"))
    mdd_limit = float((broad_selection.get("constraints") or {}).get("mdd_limit_percent", 100.0))
    top_rows = _rank_completed_rows(broad.get("completed") or {}, mdd_limit)
    refine_trials = min(5000, max(1, int(trials)))
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "base": base_overrides,
                "broad_checkpoint": str(broad_checkpoint),
                "broad_trials": broad_selection.get("tested_combinations"),
                "refine_trials": refine_trials,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    path = broad_checkpoint.with_name(broad_checkpoint.stem + "-refined.json")
    state = {"version": 1, "strategy_fingerprint": fingerprint, "completed": {}}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if loaded.get("strategy_fingerprint") == fingerprint:
            state = loaded
            log(f"정밀 탐색 체크포인트 재개: {len(state.get('completed') or {})}/{refine_trials}")
        else:
            stale = path.with_suffix(path.suffix + datetime.now(timezone.utc).strftime(".stale-%Y%m%dT%H%M%SZ"))
            path.replace(stale)
    completed = state.setdefault("completed", {})
    candidates = _refinement_candidates(
        top_rows,
        refine_trials,
        f"{symbol}|{timeframe}|{start_text}|{end_text}|{fingerprint}",
    )
    for position, params in enumerate(candidates, 1):
        _wait_for_optimization_control()
        identity = json.dumps(params, sort_keys=True, separators=(",", ":"))
        key = f"refine-{position:04d}-{hashlib.sha256(identity.encode()).hexdigest()[:10]}"
        if key in completed:
            continue
        overrides = dict(base_overrides)
        overrides.update({k: v for k, v in params.items() if k != "entry_multiplier"})
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
        completed[key] = {
            "entry_multiplier": params.get("entry_multiplier"),
            "max_entries": params.get("max_pyramiding"),
            "parameters": params,
            "result": _compact_risk_result(result),
        }
        state["last_completed"] = key
        if position % 25 == 0 or position == len(candidates):
            _save_json_atomic(path, state)
            log(f"정밀 탐색 {position}/{len(candidates)} · 상위 후보 주변 재검증")
        del result, overrides
        gc.collect()
    ranked = _rank_completed_rows(completed, mdd_limit)
    if not ranked:
        raise RuntimeError("정밀 탐색에서 MDD·청산 조건을 통과한 후보가 없습니다.")
    state["stage"] = "COMPLETE"
    state["best"] = ranked[0]
    _save_json_atomic(path, state)
    return {
        "checkpoint": str(path),
        "requested_trials": refine_trials,
        "completed_trials": len(completed),
        "eligible_trials": len(ranked),
        "top_candidates": ranked[:30],
    }


def _parse_day(value: str) -> date:
    return datetime.fromisoformat(value[:10]).date()


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    import calendar
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _three_month_windows(start_text: str, end_text: str) -> list[tuple[str, str]]:
    start = _parse_day(start_text)
    end = _parse_day(end_text)
    windows: list[tuple[str, str]] = []
    cursor = start
    while True:
        window_end = _add_months(cursor, 3) - timedelta(days=1)
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
    refined: dict,
    log,
) -> dict:
    windows = _three_month_windows(start_text, end_text)
    if not windows:
        raise RuntimeError("3개월 롤링 검증에는 최소 3개월의 기간이 필요합니다.")
    candidates = list(refined.get("top_candidates") or [])[:30]
    source = Path(str(refined["checkpoint"]))
    path = source.with_name(source.stem + "-rolling.json")
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "source": str(source),
                "windows": windows,
                "candidate_parameters": [row.get("parameters") for row in candidates],
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    state = {"version": 1, "strategy_fingerprint": fingerprint, "completed": {}}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if loaded.get("strategy_fingerprint") == fingerprint:
            state = loaded
            log(f"3개월 롤링 체크포인트 재개: {len(state.get('completed') or {})}개 구간 완료")
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
            result = run_cached_symbol_backtest(
                symbol=symbol,
                asset_class="crypto",
                exchange="bitget",
                timeframe=timeframe,
                start=window_start,
                end=window_end,
                overrides=overrides,
                database_path=db,
                control_check=_wait_for_optimization_control,
                include_details=False,
            )
            completed[key] = {
                "candidate": candidate_index,
                "candidate_id": identity,
                "parameters": params,
                "window_start": window_start,
                "window_end": window_end,
                "result": _compact_risk_result(result),
            }
            if len(completed) % 10 == 0:
                _save_json_atomic(path, state)
                log(f"3개월 롤링 검증 {len(completed)}/{len(candidates) * len(windows)}")
            del result
            gc.collect()
    summaries: list[dict] = []
    for candidate_index, row in enumerate(candidates, 1):
        params = dict(row.get("parameters") or {})
        identity = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:10]
        results = [
            item["result"] for item in completed.values()
            if item.get("candidate_id") == identity
        ]
        returns = [float(item.get("return_percent") or 0) for item in results]
        pfs = [float(item.get("profit_factor") or 0) for item in results]
        mdds = [float(item.get("max_drawdown_percent") or 0) for item in results]
        trades = [float(item.get("trades") or 0) for item in results]
        summaries.append({
            "candidate": candidate_index,
            "candidate_id": identity,
            "parameters": params,
            "window_count": len(results),
            "target_900_hits": sum(value >= 900.0 for value in returns),
            "median_return_percent": _median_numeric(returns),
            "worst_return_percent": min(returns) if returns else 0.0,
            "best_return_percent": max(returns) if returns else 0.0,
            "median_profit_factor": _median_numeric(pfs),
            "worst_mdd_percent": max(mdds) if mdds else 0.0,
            "median_trades": _median_numeric(trades),
        })
    summaries.sort(
        key=lambda row: (
            int(row["target_900_hits"]),
            float(row["median_return_percent"]),
            float(row["worst_return_percent"]),
            float(row["median_profit_factor"]),
            -float(row["worst_mdd_percent"]),
            float(row["median_trades"]),
        ),
        reverse=True,
    )
    selected = summaries[0] if summaries else None
    payload = {
        "schema_version": 1,
        "symbol": symbol,
        "timeframe": timeframe,
        "requested_start": start_text,
        "requested_end": end_text,
        "window_rule": "3 calendar months, shifted by 1 month",
        "selection_rule": "900% hits, median return, worst return, median PF, lower worst MDD, median trades",
        "candidate_count": len(candidates),
        "window_count": len(windows),
        "completed_validations": len(completed),
        "ranking": summaries,
        "selected": selected,
        "paper_live_applied": False,
    }
    report_path = output_dir / "BacktestResults" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + "-" + re.sub(r"[^A-Za-z0-9]+", "-", symbol).strip("-").lower()
        + f"-{timeframe}-rolling-final.json"
    )
    _save_json_atomic(report_path, payload)
    state["stage"] = "COMPLETE"
    state["report"] = str(report_path)
    _save_json_atomic(path, state)
    log(
        f"최종 선정 완료 · 후보 {len(candidates)}개 · 롤링 {len(windows)}구간 · "
        f"3개월 +900% 달성 {int((selected or {}).get('target_900_hits') or 0)}회"
    )
    return {**payload, "report_path": str(report_path)}



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
    optimization_trials: int = 50,
    compounding_enabled: bool = True,
    optimization_stage: str = "broad",
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
    overrides: dict = {}
    if host.strip() and username.strip() and remote_dir.strip() and key_path.strip():
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
    if selected_stage not in {"broad", "refine", "rolling", "auto"}:
        selected_stage = "broad"
    optimization_trials = int(optimization_trials)
    if optimization_trials < 1 or optimization_trials > 5000:
        raise ValueError("최적화 조합 수는 1~5000이어야 합니다.")
    if selected_profile not in RISK_PROFILES:
        selected_profile = "공격형"
    overrides.update(FIXED_BACKTEST)
    overrides["backtest_compounding_enabled"] = bool(compounding_enabled)
    overrides["order_percent_of_equity"] = 100.0
    overrides["max_pyramiding"] = 1
    profile = RISK_PROFILES[selected_profile]
    log(
        f"위험 프로필: {selected_profile} · MDD {profile['mdd_limit_percent']:.0f}% 이하 · "
        f"진입 {profile['entry_multiplier_min']}~{profile['entry_multiplier_max']}배 · "
        f"최대 진입 {profile['max_entries_values']}"
    )
    stage_names = {
        "broad": "1차 전체 탐색",
        "refine": "상위 후보 정밀 탐색",
        "rolling": "3개월 롤링 + 최종 선정",
        "auto": "전체 자동 실행",
    }
    log(f"최적화 단계: {stage_names[selected_stage]}")
    log("기간은 사용자가 선택한 날짜를 그대로 사용합니다.")
    log("고정 비용: 수수료 편도 0.02% · 슬리피지 편도 0.01%")
    if bool(compounding_enabled):
        log("계산 방식: 복리식 · 매 진입 시 현재 순자산 기준으로 주문 규모와 최대 총노출 재계산")
    else:
        log("계산 방식: 고정식 · 최초자본 1,000 USDT 기준으로 주문 규모와 최대 총노출 유지")
    log("교차마진 청산: 총노출 최대 15배 · 15배에서 약 5% 역행 시 보수적 청산")

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
    del result
    summary.pop("equity_curve", None)
    summary.pop("trades_log", None)
    gc.collect()
    log("휴대폰 안전 모드: 대형 기준 결과 메모리 해제 · trial별 자동 냉각 적용")
    broad_trials = min(1000, optimization_trials)
    log(
        f"단계별 배분: 1차 큰 구간 {broad_trials}회 → "
        f"상위 30개 주변 정밀 {optimization_trials}회 → 상위 30개 3개월 롤링"
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
    )
    for key in (
        "trades", "wins", "win_rate", "profit_factor", "pnl", "gross_pnl",
        "estimated_costs", "return_percent", "max_drawdown_percent",
        "trades_log", "equity_curve", "data_start", "data_end",
        "liquidations", "margin_mode", "maintenance_margin_percent",
        "cross_liquidation_buffer_percent", "max_total_multiplier",
        "compounding_enabled", "sizing_mode",
    ):
        summary[key] = optimized_result.get(key)
    summary["risk_profile"] = selected_profile
    summary["risk_profile_selection"] = risk_selection
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
            optimization_trials, log,
        )
        pipeline["refined"] = {
            key: value for key, value in refined.items() if key != "top_candidates"
        }
    if selected_stage in {"rolling", "auto"}:
        rolling = _rolling_validate_candidates(
            symbol.strip(), timeframe.strip(), start_text.strip(), end_text.strip(),
            Path(db), Path(output_dir), overrides, refined, log,
        )
        pipeline["rolling"] = {
            key: value for key, value in rolling.items() if key != "ranking"
        }
        summary["rolling_final_selection"] = rolling.get("selected")
        summary["rolling_report_path"] = rolling.get("report_path")
    summary["optimization_pipeline"] = pipeline
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



def export_optimization_results(result_path: str) -> str:
    result_file = Path(result_path)
    if not result_file.is_file():
        raise RuntimeError(f"결과 파일이 없습니다: {result_path}")
    summary = json.loads(result_file.read_text(encoding="utf-8"))
    selection = summary.get("risk_profile_selection") or {}
    checkpoint_path = Path(str(selection.get("checkpoint") or ""))
    if not checkpoint_path.is_file():
        raise RuntimeError(f"최적화 체크포인트가 없습니다: {checkpoint_path}")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    completed = checkpoint.get("completed") or {}
    mdd_limit = float((selection.get("constraints") or {}).get("mdd_limit_percent", 100.0))
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
    for rank, row in enumerate(eligible, 1):
        row["eligible_rank"] = rank
    payload = {
        "schema_version": 1,
        "source_result": str(result_file),
        "source_checkpoint": str(checkpoint_path),
        "symbol": summary.get("symbol"),
        "timeframe": summary.get("timeframe"),
        "requested_start": summary.get("requested_start"),
        "requested_end": summary.get("requested_end"),
        "risk_profile": summary.get("risk_profile"),
        "fixed_values": selection.get("fixed_values"),
        "constraints": selection.get("constraints"),
        "ranking_rule": "return_percent desc, profit_factor desc, max_drawdown_percent asc",
        "completed_trials": len(rankings),
        "duplicate_trials_removed": duplicate_trials,
        "eligible_trials": len(eligible),
        "top_10_overall": rankings[:10],
        "top_10_eligible": eligible[:10],
        "all_trials": rankings,
    }
    export_path = result_file.with_name(result_file.stem + "-optimization-ranking.json")
    _save_json_atomic(export_path, payload)
    return json.dumps({"path": str(export_path), "completed_trials": len(rankings), "duplicate_trials_removed": duplicate_trials, "eligible_trials": len(eligible)}, ensure_ascii=False)


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
