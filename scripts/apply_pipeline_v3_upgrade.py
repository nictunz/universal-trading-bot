from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")
    print(f"updated {rel}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, repl: str, label: str) -> str:
    out, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match, found {count}")
    return out


def patch_config(rel: str) -> None:
    text = read(rel)
    if "apply_consecutive_candles_to_all_entries" in text:
        return
    if rel == "universal_bot/config.py":
        text = replace_once(
            text,
            "    first_entry_consecutive_candles: int = 1\n",
            "    first_entry_consecutive_candles: int = 1\n"
            "    # False=3틱룰은 첫 진입만, True=추가 진입에도 동일한 연속봉 조건 적용.\n"
            "    apply_consecutive_candles_to_all_entries: bool = False\n",
            "server config 3tick toggle",
        )
    else:
        text = replace_once(
            text,
            '    "first_entry_consecutive_candles": 1,\n',
            '    "first_entry_consecutive_candles": 1,\n'
            '    "apply_consecutive_candles_to_all_entries": False,\n',
            "android config 3tick toggle",
        )
    write(rel, text)


def patch_strategy() -> None:
    rel = "universal_bot/strategy/v15.py"
    text = read(rel)
    old = '''        if position is None or position.flat:\n            recent = df.iloc[-first_entry_bars:]\n            consecutive_bearish = bool((recent["close"].astype(float) < recent["open"].astype(float)).all())\n            consecutive_bullish = bool((recent["close"].astype(float) > recent["open"].astype(float)).all())\n            long_candle_ok = consecutive_bearish\n            short_candle_ok = consecutive_bullish\n        else:\n            consecutive_bearish = bearish\n            consecutive_bullish = bullish\n            long_candle_ok = bearish\n            short_candle_ok = bullish\n'''
    new = '''        apply_three_tick_to_all = bool(getattr(self.s, "apply_consecutive_candles_to_all_entries", False))\n        require_consecutive = position is None or position.flat or apply_three_tick_to_all\n        if require_consecutive:\n            recent = df.iloc[-first_entry_bars:]\n            consecutive_bearish = bool((recent["close"].astype(float) < recent["open"].astype(float)).all())\n            consecutive_bullish = bool((recent["close"].astype(float) > recent["open"].astype(float)).all())\n            long_candle_ok = consecutive_bearish\n            short_candle_ok = consecutive_bullish\n        else:\n            consecutive_bearish = bearish\n            consecutive_bullish = bullish\n            long_candle_ok = bearish\n            short_candle_ok = bullish\n'''
    if "apply_three_tick_to_all =" not in text:
        text = replace_once(text, old, new, "strategy all-entry 3tick")
        text = replace_once(
            text,
            '            "first_entry_consecutive_candles": first_entry_bars,\n',
            '            "first_entry_consecutive_candles": first_entry_bars,\n'
            '            "apply_consecutive_candles_to_all_entries": apply_three_tick_to_all,\n',
            "strategy diagnostic toggle",
        )
    write(rel, text)


def patch_backtest() -> None:
    rel = "universal_bot/backtest.py"
    text = read(rel)
    if "def _consecutive_candle_direction_ok" not in text:
        anchor = '''def run_backtest(\n    df: pd.DataFrame,\n'''
        helper = '''def _consecutive_candle_direction_ok(\n    opens: np.ndarray,\n    closes: np.ndarray,\n    index: int,\n    candles: int,\n    side: str,\n) -> bool:\n    count = max(1, int(candles))\n    start = index - count + 1\n    if start < 0:\n        return False\n    recent_open = opens[start:index + 1]\n    recent_close = closes[start:index + 1]\n    if side == "LONG":\n        return bool(np.all(recent_close < recent_open))\n    if side == "SHORT":\n        return bool(np.all(recent_close > recent_open))\n    return False\n\n\n'''
        text = replace_once(text, anchor, helper + anchor, "backtest consecutive helper")

    old_signal = '''        signal: str | None = None\n        if base_entry and settings.allow_long and c < o and long_ok:\n            signal = "LONG"\n        elif base_entry and settings.allow_short and c > o and short_ok:\n            signal = "SHORT"\n'''
    new_signal = '''        signal: str | None = None\n        first_entry_bars = max(1, int(settings.first_entry_consecutive_candles))\n        apply_three_tick_to_all = bool(getattr(settings, "apply_consecutive_candles_to_all_entries", False))\n        require_consecutive = position_side is None or apply_three_tick_to_all\n        long_candle_ok = (\n            _consecutive_candle_direction_ok(opens, closes, i, first_entry_bars, "LONG")\n            if require_consecutive else c < o\n        )\n        short_candle_ok = (\n            _consecutive_candle_direction_ok(opens, closes, i, first_entry_bars, "SHORT")\n            if require_consecutive else c > o\n        )\n        if base_entry and settings.allow_long and long_candle_ok and long_ok:\n            signal = "LONG"\n        elif base_entry and settings.allow_short and short_candle_ok and short_ok:\n            signal = "SHORT"\n'''
    if "require_consecutive = position_side is None or apply_three_tick_to_all" not in text:
        text = replace_once(text, old_signal, new_signal, "backtest 3tick signal")
    write(rel, text)


def patch_service() -> None:
    rel = "android/app/src/main/java/com/nictunz/universalbacktester/BacktestForegroundService.java"
    text = read(rel)
    old_call = '''                    request.optString("risk_profile", "공격형"),\n                    request.optInt("optimization_trials", 50),\n                    request.optBoolean("compounding_enabled", true),\n                    request.optString("optimization_stage", "broad")\n'''
    new_call = '''                    request.optString("risk_profile", "공격형"),\n                    request.optInt("broad_optimization_trials", request.optInt("optimization_trials", 1000)),\n                    request.optInt("refine_optimization_trials", request.optInt("optimization_trials", 1000)),\n                    request.optBoolean("compounding_enabled", true),\n                    request.optString("optimization_stage", "broad"),\n                    request.optBoolean("all_entries_three_tick", false)\n'''
    if "broad_optimization_trials" not in text:
        text = replace_once(text, old_call, new_call, "service python args")
        text = replace_once(
            text,
            '        request.put("optimization_trials", intent.getIntExtra("optimization_trials", 50));\n',
            '        request.put("optimization_trials", intent.getIntExtra("optimization_trials", 1000));\n'
            '        request.put("broad_optimization_trials", intent.getIntExtra("broad_optimization_trials", intent.getIntExtra("optimization_trials", 1000)));\n'
            '        request.put("refine_optimization_trials", intent.getIntExtra("refine_optimization_trials", intent.getIntExtra("optimization_trials", 1000)));\n'
            '        request.put("all_entries_three_tick", intent.getBooleanExtra("all_entries_three_tick", false));\n',
            "service request extras",
        )
    write(rel, text)


def patch_main_activity() -> None:
    rel = "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java"
    text = read(rel)
    if "broadTrialCountInput" not in text:
        text = replace_once(
            text,
            "    private AutoCompleteTextView trialCountInput;\n",
            "    private AutoCompleteTextView broadTrialCountInput;\n"
            "    private AutoCompleteTextView refineTrialCountInput;\n"
            "    private AutoCompleteTextView threeTickModeInput;\n",
            "main fields",
        )

        text = text.replace('"3개월 롤링 + 최종 선정"', '"6개월 → 3개월 롤링 + 최종 선정"')
        text = text.replace('new String[]{"1차 탐색", "정밀 탐색", "3개월 롤링", "전체 자동"}',
                            'new String[]{"1차 탐색", "정밀 탐색", "6→3개월 롤링", "전체 자동"}')
        text = text.replace('"후속 단계는 앞 단계 체크포인트를 자동 재사용합니다. 전체 자동은 1차→정밀→롤링→최종 선정을 순서대로 실행합니다."',
                            '"후속 단계는 앞 단계 체크포인트를 자동 재사용합니다. 전체 자동은 1차→TOP10 후보별 정밀→6개월 롤링→3개월 롤링→최종 선정을 순서대로 실행합니다."')

        old_ui = '''        trialCountInput = autocomplete(new String[]{"50", "100", "200", "300", "500", "750", "1000", "2000", "3000", "5000"}, "50");\n        backtestCard.addView(labeled("최적화 조합 수 (1~5000 직접 입력 가능)", trialCountInput), marginTop(12));\n        backtestCard.addView(quickChoiceRow(\n                "빠른 조합 수",\n                trialCountInput,\n                new String[]{"100회", "500회", "1000회", "3000회", "5000회"},\n                new String[]{"100", "500", "1000", "3000", "5000"}\n        ), marginTop(8));\n'''
        new_ui = '''        broadTrialCountInput = autocomplete(new String[]{"100", "500", "1000", "2000", "3000", "5000"}, "1000");\n        backtestCard.addView(labeled("1차 전체 탐색 조합 수 (1~5000)", broadTrialCountInput), marginTop(12));\n        backtestCard.addView(quickChoiceRow(\n                "1차 빠른 선택", broadTrialCountInput,\n                new String[]{"100회", "500회", "1000회", "3000회", "5000회"},\n                new String[]{"100", "500", "1000", "3000", "5000"}\n        ), marginTop(8));\n\n        refineTrialCountInput = autocomplete(new String[]{"100", "500", "1000", "2000", "3000", "5000"}, "1000");\n        backtestCard.addView(labeled("2차 정밀 탐색 · TOP10 후보당 조합 수 (1~5000)", refineTrialCountInput), marginTop(12));\n        backtestCard.addView(quickChoiceRow(\n                "정밀 빠른 선택", refineTrialCountInput,\n                new String[]{"100회", "500회", "1000회", "3000회", "5000회"},\n                new String[]{"100", "500", "1000", "3000", "5000"}\n        ), marginTop(8));\n        backtestCard.addView(text(\n                "예: 후보당 5,000회 선택 시 1차 TOP10 각각을 정밀 탐색하여 최대 50,000개 조합을 검사합니다.",\n                11, MUTED, false\n        ), marginTop(7));\n\n        threeTickModeInput = autocomplete(new String[]{"첫 진입만 3틱룰", "모든 진입 3틱룰"}, "첫 진입만 3틱룰");\n        backtestCard.addView(labeled("3틱룰 적용 범위", threeTickModeInput), marginTop(12));\n        backtestCard.addView(quickChoiceRow(\n                "3틱룰", threeTickModeInput,\n                new String[]{"첫 진입만", "모든 진입"},\n                new String[]{"첫 진입만 3틱룰", "모든 진입 3틱룰"}\n        ), marginTop(8));\n'''
        text = replace_once(text, old_ui, new_ui, "main trial UI")

        old_parse = '''        int optimizationTrials;\n        try {\n            optimizationTrials = Integer.parseInt(trialCountInput.getText().toString().trim());\n        } catch (Exception ignored) {\n            toast("조합 수는 1~5000 사이 숫자로 입력하세요.");\n            return;\n        }\n        if (optimizationTrials < 1 || optimizationTrials > 5000) {\n            toast("조합 수는 1~5000 사이로 입력하세요.");\n            return;\n        }\n'''
        new_parse = '''        int broadOptimizationTrials;\n        int refineOptimizationTrials;\n        try {\n            broadOptimizationTrials = Integer.parseInt(broadTrialCountInput.getText().toString().trim());\n            refineOptimizationTrials = Integer.parseInt(refineTrialCountInput.getText().toString().trim());\n        } catch (Exception ignored) {\n            toast("1차/정밀 조합 수는 각각 1~5000 사이 숫자로 입력하세요.");\n            return;\n        }\n        if (broadOptimizationTrials < 1 || broadOptimizationTrials > 5000\n                || refineOptimizationTrials < 1 || refineOptimizationTrials > 5000) {\n            toast("1차/정밀 조합 수는 각각 1~5000 사이로 입력하세요.");\n            return;\n        }\n        boolean allEntriesThreeTick = "모든 진입 3틱룰".equals(threeTickModeInput.getText().toString().trim());\n'''
        text = replace_once(text, old_parse, new_parse, "main trial parsing")
        text = text.replace('else if ("3개월 롤링 + 최종 선정".equals(stageLabel)) optimizationStage = "rolling";',
                            'else if ("6개월 → 3개월 롤링 + 최종 선정".equals(stageLabel)) optimizationStage = "rolling";')
        text = replace_once(
            text,
            '        intent.putExtra("optimization_trials", optimizationTrials);\n',
            '        intent.putExtra("optimization_trials", broadOptimizationTrials);\n'
            '        intent.putExtra("broad_optimization_trials", broadOptimizationTrials);\n'
            '        intent.putExtra("refine_optimization_trials", refineOptimizationTrials);\n'
            '        intent.putExtra("all_entries_three_tick", allEntriesThreeTick);\n',
            "main intent extras",
        )
        text = replace_once(
            text,
            '                + " · 조합: " + optimizationTrials + "회\\n"\n',
            '                + " · 1차: " + broadOptimizationTrials + "회"\n'
            '                + " · 정밀: TOP10×" + refineOptimizationTrials + "회"\n'
            '                + " · 3틱룰: " + (allEntriesThreeTick ? "모든 진입" : "첫 진입만") + "\\n"\n',
            "main launch log",
        )
        text = text.replace("MDD 40% 초과 포함", "MDD 70% 초과 포함")
        text = text.replace("MDD 초과 포함", "MDD 70% 초과 포함")
    write(rel, text)


def patch_mobile_bridge() -> None:
    rel = "android/app/src/main/python/mobile_bridge.py"
    text = read(rel)
    text = text.replace('"3봉 분할형": {\n        "mdd_limit_percent": 40.0,',
                        '"3봉 분할형": {\n        "mdd_limit_percent": 70.0,')

    # Replace refinement implementation with TOP10 x user-selected per-seed trials.
    refine_block = r"def _refinement_candidates\(.*?\n\ndef _parse_day\(value: str\) -> date:"
    refine_new = '''def _refinement_candidates(top_rows: list[dict], trials_per_seed: int, seed_material: str) -> list[tuple[int, dict]]:\n    rng = random.Random(int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16))\n    fields = {\n        "volume_break_multiplier": (3.0, 25.0, 0.35, 2),\n        "min_one_bar_vol": (0.05, 0.55, 0.04, 2),\n        "max_one_bar_vol": (0.40, 2.50, 0.08, 2),\n        "tp_vol_multiplier": (0.15, 2.50, 0.10, 2),\n        "sl_vol_multiplier": (0.20, 3.50, 0.12, 2),\n        "min_tp_percent": (0.10, 0.80, 0.04, 2),\n        "max_tp_percent": (0.50, 3.00, 0.10, 2),\n        "min_sl_percent": (0.15, 1.20, 0.05, 2),\n        "max_sl_percent": (0.80, 4.00, 0.12, 2),\n        "max_nbar_volatility": (0.80, 10.0, 0.25, 2),\n        "adx_min": (5.0, 35.0, 1.0, 1),\n        "adx_max": (45.0, 100.0, 2.0, 1),\n        "rsi_oversold_min": (0.0, 40.0, 1.0, 1),\n        "rsi_oversold_max": (10.0, 50.0, 1.0, 1),\n        "rsi_overbought_min": (50.0, 90.0, 1.0, 1),\n        "rsi_overbought_max": (60.0, 100.0, 1.0, 1),\n    }\n    bases = top_rows[:10]\n    candidates: list[tuple[int, dict]] = []\n    seen: set[str] = set()\n    for seed_index, row in enumerate(bases, 1):\n        base = dict(row.get("parameters") or {})\n        made = 0\n        attempts = 0\n        while made < trials_per_seed:\n            attempts += 1\n            if attempts > trials_per_seed * 200 + 1000:\n                raise RuntimeError(f"정밀 탐색 후보 생성 실패: TOP{seed_index}에서 중복이 너무 많습니다.")\n            params = dict(base)\n            for name, (low, high, step, digits) in fields.items():\n                if name in params:\n                    params[name] = _clamp(float(params[name]) + rng.choice([-2, -1, 0, 1, 2]) * step, low, high, digits)\n            for name, low, high, radius in (\n                ("volume_lookback", 20, 160, 8),\n                ("adx_length", 5, 30, 2),\n                ("rsi_length", 3, 24, 2),\n                ("cooldown_bars", 0, 36, 3),\n                ("reentry_bars", 0, 24, 3),\n            ):\n                if name in params:\n                    params[name] = max(low, min(high, int(params[name]) + rng.randint(-radius, radius)))\n            if params.get("min_one_bar_vol", 0) >= params.get("max_one_bar_vol", 1):\n                params["max_one_bar_vol"] = _clamp(float(params["min_one_bar_vol"]) + 0.15, 0.40, 2.50)\n            if params.get("min_tp_percent", 0) >= params.get("max_tp_percent", 1):\n                params["max_tp_percent"] = _clamp(float(params["min_tp_percent"]) + 0.10, 0.50, 3.00)\n            if params.get("min_sl_percent", 0) >= params.get("max_sl_percent", 1):\n                params["max_sl_percent"] = _clamp(float(params["min_sl_percent"]) + 0.15, 0.80, 4.00)\n            identity = json.dumps(params, sort_keys=True, separators=(",", ":"))\n            if identity in seen:\n                continue\n            seen.add(identity)\n            candidates.append((seed_index, params))\n            made += 1\n    return candidates\n\n\ndef _refine_top_candidates(\n    symbol: str,\n    timeframe: str,\n    start_text: str,\n    end_text: str,\n    db: Path,\n    output_dir: Path,\n    base_overrides: dict,\n    broad_selection: dict,\n    trials: int,\n    log,\n) -> dict:\n    broad_checkpoint = Path(str(broad_selection["checkpoint"]))\n    broad = json.loads(broad_checkpoint.read_text(encoding="utf-8"))\n    mdd_limit = float((broad_selection.get("constraints") or {}).get("mdd_limit_percent", 100.0))\n    top_rows = _rank_completed_rows(broad.get("completed") or {}, mdd_limit)[:10]\n    if not top_rows:\n        raise RuntimeError("1차 탐색에서 정밀 탐색에 사용할 TOP10 후보가 없습니다.")\n    trials_per_seed = min(5000, max(1, int(trials)))\n    expected_trials = len(top_rows) * trials_per_seed\n    fingerprint = hashlib.sha256(json.dumps({\n        "base": base_overrides,\n        "broad_checkpoint": str(broad_checkpoint),\n        "broad_top10": [row.get("parameters") for row in top_rows],\n        "trials_per_seed": trials_per_seed,\n        "schema": "top10-independent-refine-v3",\n    }, sort_keys=True, default=str).encode("utf-8")).hexdigest()\n    path = broad_checkpoint.with_name(broad_checkpoint.stem + "-refined.json")\n    state = {"version": 3, "strategy_fingerprint": fingerprint, "completed": {}}\n    if path.is_file():\n        loaded = json.loads(path.read_text(encoding="utf-8"))\n        if loaded.get("strategy_fingerprint") == fingerprint:\n            state = loaded\n            log(f"정밀 탐색 체크포인트 재개: {len(state.get('completed') or {})}/{expected_trials}")\n        else:\n            stale = path.with_suffix(path.suffix + datetime.now(timezone.utc).strftime(".stale-%Y%m%dT%H%M%SZ"))\n            path.replace(stale)\n    completed = state.setdefault("completed", {})\n    candidates = _refinement_candidates(top_rows, trials_per_seed, f"{symbol}|{timeframe}|{start_text}|{end_text}|{fingerprint}")\n    for position, (seed_index, params) in enumerate(candidates, 1):\n        _wait_for_optimization_control()\n        identity = json.dumps(params, sort_keys=True, separators=(",", ":"))\n        key = f"refine-top{seed_index:02d}-{position:05d}-{hashlib.sha256(identity.encode()).hexdigest()[:10]}"\n        if key in completed:\n            continue\n        overrides = dict(base_overrides)\n        overrides.update({k: v for k, v in params.items() if k != "entry_multiplier"})\n        result = run_cached_symbol_backtest(symbol=symbol, asset_class="crypto", exchange="bitget", timeframe=timeframe,\n            start=start_text, end=end_text, overrides=overrides, database_path=db,\n            control_check=_wait_for_optimization_control, include_details=False)\n        completed[key] = {\n            "broad_seed_rank": seed_index,\n            "entry_multiplier": params.get("entry_multiplier"),\n            "max_entries": params.get("max_pyramiding"),\n            "parameters": params,\n            "result": _compact_risk_result(result),\n        }\n        state["last_completed"] = key\n        if position % 25 == 0 or position == len(candidates):\n            _save_json_atomic(path, state)\n            log(f"정밀 탐색 {position}/{expected_trials} · TOP10 후보별 {trials_per_seed}회")\n        del result, overrides\n        gc.collect()\n    ranked = _rank_completed_rows(completed, mdd_limit)\n    if not ranked:\n        raise RuntimeError("정밀 탐색에서 MDD·청산 조건을 통과한 후보가 없습니다.")\n    state["stage"] = "COMPLETE"\n    state["best"] = ranked[0]\n    state["top10_broad_seeds"] = top_rows\n    state["trials_per_seed"] = trials_per_seed\n    _save_json_atomic(path, state)\n    return {\n        "checkpoint": str(path),\n        "broad_seed_count": len(top_rows),\n        "trials_per_seed": trials_per_seed,\n        "requested_trials": expected_trials,\n        "completed_trials": len(completed),\n        "eligible_trials": len(ranked),\n        "top_candidates": ranked[:10],\n    }\n\n\ndef _parse_day(value: str) -> date:'''
    if "top10-independent-refine-v3" not in text:
        text = regex_once(text, refine_block, refine_new, "mobile refine block")

    rolling_block = r"def _three_month_windows\(.*?\n\n\ndef _ssh_bridge\(\):"
    rolling_new = '''def _month_windows(start_text: str, end_text: str, months: int) -> list[tuple[str, str]]:\n    start = _parse_day(start_text)\n    end = _parse_day(end_text)\n    windows: list[tuple[str, str]] = []\n    cursor = start\n    while True:\n        window_end = _add_months(cursor, months) - timedelta(days=1)\n        if window_end > end:\n            break\n        windows.append((cursor.isoformat(), window_end.isoformat()))\n        cursor = _add_months(cursor, 1)\n    return windows\n\n\ndef _median_numeric(values: list[float]) -> float:\n    return float(statistics.median(values)) if values else 0.0\n\n\ndef _rolling_validate_candidates(\n    symbol: str,\n    timeframe: str,\n    start_text: str,\n    end_text: str,\n    db: Path,\n    output_dir: Path,\n    base_overrides: dict,\n    candidate_rows: list[dict],\n    source_checkpoint: str,\n    months: int,\n    log,\n) -> dict:\n    windows = _month_windows(start_text, end_text, months)\n    if not windows:\n        raise RuntimeError(f"{months}개월 롤링 검증에는 최소 {months}개월의 기간이 필요합니다.")\n    candidates = list(candidate_rows or [])[:10]\n    if not candidates:\n        raise RuntimeError(f"{months}개월 롤링 검증 후보가 없습니다.")\n    source = Path(str(source_checkpoint))\n    path = source.with_name(source.stem + f"-rolling-{months}m.json")\n    fingerprint = hashlib.sha256(json.dumps({\n        "source": str(source), "months": months, "windows": windows,\n        "candidate_parameters": [row.get("parameters") for row in candidates],\n    }, sort_keys=True, default=str).encode("utf-8")).hexdigest()\n    state = {"version": 2, "strategy_fingerprint": fingerprint, "completed": {}}\n    if path.is_file():\n        loaded = json.loads(path.read_text(encoding="utf-8"))\n        if loaded.get("strategy_fingerprint") == fingerprint:\n            state = loaded\n            log(f"{months}개월 롤링 체크포인트 재개: {len(state.get('completed') or {})}개 구간 완료")\n    completed = state.setdefault("completed", {})\n    for candidate_index, row in enumerate(candidates, 1):\n        params = dict(row.get("parameters") or {})\n        overrides = dict(base_overrides)\n        overrides.update({k: v for k, v in params.items() if k != "entry_multiplier"})\n        identity = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:10]\n        for window_index, (window_start, window_end) in enumerate(windows, 1):\n            _wait_for_optimization_control()\n            key = f"candidate-{candidate_index:02d}-{identity}-window-{window_index:02d}"\n            if key in completed:\n                continue\n            result = run_cached_symbol_backtest(symbol=symbol, asset_class="crypto", exchange="bitget", timeframe=timeframe,\n                start=window_start, end=window_end, overrides=overrides, database_path=db,\n                control_check=_wait_for_optimization_control, include_details=False)\n            completed[key] = {"candidate": candidate_index, "candidate_id": identity, "parameters": params,\n                "window_start": window_start, "window_end": window_end, "result": _compact_risk_result(result)}\n            if len(completed) % 10 == 0:\n                _save_json_atomic(path, state)\n                log(f"{months}개월 롤링 검증 {len(completed)}/{len(candidates) * len(windows)}")\n            del result\n            gc.collect()\n    summaries: list[dict] = []\n    for candidate_index, row in enumerate(candidates, 1):\n        params = dict(row.get("parameters") or {})\n        identity = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:10]\n        results = [item["result"] for item in completed.values() if item.get("candidate_id") == identity]\n        returns = [float(item.get("return_percent") or 0) for item in results]\n        pfs = [float(item.get("profit_factor") or 0) for item in results]\n        mdds = [float(item.get("max_drawdown_percent") or 0) for item in results]\n        trades = [float(item.get("trades") or 0) for item in results]\n        summaries.append({\n            "candidate": candidate_index, "candidate_id": identity, "parameters": params, "window_count": len(results),\n            "positive_windows": sum(value > 0 for value in returns),\n            "median_return_percent": _median_numeric(returns),\n            "worst_return_percent": min(returns) if returns else 0.0,\n            "best_return_percent": max(returns) if returns else 0.0,\n            "median_profit_factor": _median_numeric(pfs),\n            "worst_mdd_percent": max(mdds) if mdds else 0.0,\n            "median_trades": _median_numeric(trades),\n        })\n    summaries.sort(key=lambda row: (\n        int(row["positive_windows"]), float(row["median_return_percent"]), float(row["worst_return_percent"]),\n        float(row["median_profit_factor"]), -float(row["worst_mdd_percent"]), float(row["median_trades"]),\n    ), reverse=True)\n    selected = summaries[0] if summaries else None\n    payload = {\n        "schema_version": 2, "symbol": symbol, "timeframe": timeframe, "requested_start": start_text, "requested_end": end_text,\n        "window_months": months, "window_rule": f"{months} calendar months, shifted by 1 month",\n        "selection_rule": "positive windows, median return, worst return, median PF, lower worst MDD, median trades",\n        "candidate_count": len(candidates), "window_count": len(windows), "completed_validations": len(completed),\n        "ranking": summaries, "selected": selected, "paper_live_applied": False,\n    }\n    report_path = output_dir / "BacktestResults" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")\n        + "-" + re.sub(r"[^A-Za-z0-9]+", "-", symbol).strip("-").lower()\n        + f"-{timeframe}-rolling-{months}m-final.json")\n    _save_json_atomic(report_path, payload)\n    state["stage"] = "COMPLETE"\n    state["report"] = str(report_path)\n    _save_json_atomic(path, state)\n    log(f"{months}개월 롤링 완료 · 후보 {len(candidates)}개 · {len(windows)}구간 · 최종 중간수익률 {float((selected or {}).get('median_return_percent') or 0):.2f}%")\n    return {**payload, "checkpoint": str(path), "report_path": str(report_path)}\n\n\ndef _ssh_bridge():'''
    if "window_months" not in text:
        text = regex_once(text, rolling_block, rolling_new, "mobile rolling block")

    old_sig = '''    risk_profile: str = "공격형",\n    optimization_trials: int = 50,\n    compounding_enabled: bool = True,\n    optimization_stage: str = "broad",\n) -> str:\n'''
    new_sig = '''    risk_profile: str = "공격형",\n    broad_optimization_trials: int = 1000,\n    refine_optimization_trials: int = 1000,\n    compounding_enabled: bool = True,\n    optimization_stage: str = "broad",\n    all_entries_three_tick: bool = False,\n) -> str:\n'''
    if "broad_optimization_trials: int" not in text:
        text = replace_once(text, old_sig, new_sig, "mobile run signature")

    old_validate = '''    optimization_trials = int(optimization_trials)\n    if optimization_trials < 1 or optimization_trials > 5000:\n        raise ValueError("최적화 조합 수는 1~5000이어야 합니다.")\n'''
    new_validate = '''    broad_optimization_trials = int(broad_optimization_trials)\n    refine_optimization_trials = int(refine_optimization_trials)\n    if not 1 <= broad_optimization_trials <= 5000:\n        raise ValueError("1차 최적화 조합 수는 1~5000이어야 합니다.")\n    if not 1 <= refine_optimization_trials <= 5000:\n        raise ValueError("정밀 최적화 후보당 조합 수는 1~5000이어야 합니다.")\n'''
    if "정밀 최적화 후보당" not in text:
        text = replace_once(text, old_validate, new_validate, "mobile count validation")
        text = replace_once(
            text,
            '    overrides["max_pyramiding"] = 1\n',
            '    overrides["max_pyramiding"] = 1\n'
            '    overrides["apply_consecutive_candles_to_all_entries"] = bool(all_entries_three_tick)\n',
            "mobile 3tick override",
        )
        text = text.replace('"rolling": "3개월 롤링 + 최종 선정",', '"rolling": "6개월 → 3개월 롤링 + 최종 선정",')
        text = replace_once(
            text,
            '    log("교차마진 청산: 총노출 최대 15배 · 15배에서 약 5% 역행 시 보수적 청산")\n',
            '    log("교차마진 청산: 총노출 최대 15배 · 15배에서 약 5% 역행 시 보수적 청산")\n'
            '    log(f"3틱룰 적용: {\'모든 진입\' if all_entries_three_tick else \'첫 진입만\'}")\n',
            "mobile 3tick log",
        )

    old_pipeline = '''    broad_trials = min(1000, optimization_trials)\n    log(\n        f"단계별 배분: 1차 큰 구간 {broad_trials}회 → "\n        f"상위 30개 주변 정밀 {optimization_trials}회 → 상위 30개 3개월 롤링"\n    )\n'''
    new_pipeline = '''    broad_trials = broad_optimization_trials\n    refine_trials_per_seed = refine_optimization_trials\n    log(\n        f"단계별 배분: 1차 큰 구간 {broad_trials}회 → 수익률 TOP10 각각 정밀 {refine_trials_per_seed}회 "\n        f"(최대 {refine_trials_per_seed * 10}회) → 6개월 롤링 → 3개월 롤링"\n    )\n'''
    if "refine_trials_per_seed" not in text:
        text = replace_once(text, old_pipeline, new_pipeline, "mobile pipeline allocation")
        text = replace_once(text, "            optimization_trials, log,\n", "            refine_trials_per_seed, log,\n", "mobile refine count call")
        old_roll_call = '''        rolling = _rolling_validate_candidates(\n            symbol.strip(), timeframe.strip(), start_text.strip(), end_text.strip(),\n            Path(db), Path(output_dir), overrides, refined, log,\n        )\n        pipeline["rolling"] = {\n            key: value for key, value in rolling.items() if key != "ranking"\n        }\n        summary["rolling_final_selection"] = rolling.get("selected")\n        summary["rolling_report_path"] = rolling.get("report_path")\n'''
        new_roll_call = '''        rolling_6m = _rolling_validate_candidates(\n            symbol.strip(), timeframe.strip(), start_text.strip(), end_text.strip(),\n            Path(db), Path(output_dir), overrides, list(refined.get("top_candidates") or [])[:10],\n            str(refined.get("checkpoint") or ""), 6, log,\n        )\n        rolling_3m = _rolling_validate_candidates(\n            symbol.strip(), timeframe.strip(), start_text.strip(), end_text.strip(),\n            Path(db), Path(output_dir), overrides, list(rolling_6m.get("ranking") or [])[:10],\n            str(rolling_6m.get("checkpoint") or ""), 3, log,\n        )\n        pipeline["rolling_6m"] = {key: value for key, value in rolling_6m.items() if key != "ranking"}\n        pipeline["rolling_3m"] = {key: value for key, value in rolling_3m.items() if key != "ranking"}\n        summary["rolling_6m_report_path"] = rolling_6m.get("report_path")\n        summary["rolling_3m_report_path"] = rolling_3m.get("report_path")\n        summary["rolling_final_selection"] = rolling_3m.get("selected")\n        summary["rolling_report_path"] = rolling_3m.get("report_path")\n'''
        text = replace_once(text, old_roll_call, new_roll_call, "mobile two-stage rolling")

    # Export both rolling stages while preserving old keys.
    if '"rolling_6m_report"' not in text:
        text = replace_once(
            text,
            '    rolling_report_path = Path(str(summary.get("rolling_report_path") or ""))\n    rolling_report = None\n    if rolling_report_path.is_file():\n        rolling_report = json.loads(rolling_report_path.read_text(encoding="utf-8"))\n',
            '    rolling_report_path = Path(str(summary.get("rolling_report_path") or ""))\n'
            '    rolling_report = json.loads(rolling_report_path.read_text(encoding="utf-8")) if rolling_report_path.is_file() else None\n'
            '    rolling_6m_path = Path(str(summary.get("rolling_6m_report_path") or ""))\n'
            '    rolling_3m_path = Path(str(summary.get("rolling_3m_report_path") or summary.get("rolling_report_path") or ""))\n'
            '    rolling_6m_report = json.loads(rolling_6m_path.read_text(encoding="utf-8")) if rolling_6m_path.is_file() else None\n'
            '    rolling_3m_report = json.loads(rolling_3m_path.read_text(encoding="utf-8")) if rolling_3m_path.is_file() else None\n',
            "mobile export rolling reads",
        )
        text = replace_once(
            text,
            '        "rolling_report": rolling_report,\n        "rolling_final_selection": summary.get("rolling_final_selection"),\n',
            '        "rolling_report": rolling_report,\n'
            '        "rolling_6m_report_path": str(rolling_6m_path),\n'
            '        "rolling_6m_report": rolling_6m_report,\n'
            '        "rolling_3m_report_path": str(rolling_3m_path),\n'
            '        "rolling_3m_report": rolling_3m_report,\n'
            '        "rolling_final_selection": summary.get("rolling_final_selection"),\n',
            "mobile export rolling payload",
        )
    write(rel, text)


def add_tests() -> None:
    rel = "tests/test_pipeline_v3_upgrade.py"
    content = '''from pathlib import Path\nimport numpy as np\n\nfrom universal_bot.backtest import _consecutive_candle_direction_ok\nfrom universal_bot.config import Settings\n\n\ndef test_consecutive_candle_direction_helper():\n    opens = np.array([10.0, 9.0, 8.0, 9.0])\n    closes = np.array([9.0, 8.0, 7.0, 10.0])\n    assert _consecutive_candle_direction_ok(opens, closes, 2, 3, "LONG") is True\n    assert _consecutive_candle_direction_ok(opens, closes, 3, 3, "LONG") is False\n    assert _consecutive_candle_direction_ok(opens, closes, 3, 1, "SHORT") is True\n\n\ndef test_three_tick_all_entries_setting_defaults_off():\n    settings = Settings()\n    assert settings.apply_consecutive_candles_to_all_entries is False\n\n\ndef test_android_pipeline_v3_source_contract():\n    root = Path(__file__).resolve().parents[1]\n    bridge = (root / "android/app/src/main/python/mobile_bridge.py").read_text(encoding="utf-8")\n    main = (root / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")\n    assert '"mdd_limit_percent": 70.0' in bridge\n    assert "top10-independent-refine-v3" in bridge\n    assert "rolling_6m" in bridge and "rolling_3m" in bridge\n    assert "broadOptimizationTrials" in main and "refineOptimizationTrials" in main\n    assert "모든 진입 3틱룰" in main\n'''
    write(rel, content)


def main() -> None:
    patch_config("universal_bot/config.py")
    patch_config("android/compat/config.py")
    patch_strategy()
    patch_backtest()
    patch_service()
    patch_main_activity()
    patch_mobile_bridge()
    add_tests()
    print("pipeline v3 upgrade applied")


if __name__ == "__main__":
    main()
