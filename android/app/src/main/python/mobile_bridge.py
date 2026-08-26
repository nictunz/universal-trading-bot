from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from universal_bot.fast_backtest import run_cached_symbol_backtest
from universal_bot.local_cache_core import (
    DEFAULT_REMOTE_DIR,
    DEFAULT_SERVER,
    DEFAULT_USER,
    build_cache_and_backtest,
    server_upload_eligible,
)


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
}

FIXED_BACKTEST = {
    "leverage": 50,
    "backtest_fee_percent": 0.02,
    "backtest_slippage_percent": 0.01,
}


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


def _compact_risk_result(result: dict) -> dict:
    keys = (
        "trades", "wins", "win_rate", "profit_factor", "pnl", "gross_pnl",
        "estimated_costs", "return_percent", "max_drawdown_percent",
        "fee_percent_per_side", "slippage_percent_per_side",
    )
    return {key: result.get(key) for key in keys}


def _optimize_risk_profile(
    symbol: str,
    timeframe: str,
    start_text: str,
    end_text: str,
    db: Path,
    output_dir: Path,
    base_overrides: dict,
    profile_name: str,
    log,
) -> tuple[dict, dict]:
    profile = RISK_PROFILES[profile_name]
    checkpoint_path = _risk_checkpoint_path(
        output_dir, symbol, timeframe, start_text, end_text, profile_name
    )
    strategy_fingerprint = hashlib.sha256(
        json.dumps(base_overrides, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    checkpoint = {
        "version": 1,
        "profile": profile_name,
        "constraints": profile,
        "strategy_fingerprint": strategy_fingerprint,
        "completed": {},
    }
    if checkpoint_path.is_file():
        try:
            loaded = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if (
                loaded.get("version") == 1
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
    combinations = [
        (entry, entries)
        for entry in range(profile["entry_multiplier_min"], profile["entry_multiplier_max"] + 1)
        for entries in profile["max_entries_values"]
    ]
    for position, (entry, entries) in enumerate(combinations, 1):
        key = f"{entry}x-{entries}"
        if key in completed:
            continue
        overrides = dict(base_overrides)
        overrides.update(FIXED_BACKTEST)
        overrides["order_percent_of_equity"] = float(entry * 100)
        overrides["max_pyramiding"] = int(entries)
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
            )
            if float(result.get("fee_percent_per_side", -1)) != 0.02:
                raise RuntimeError("수수료 고정값 불일치")
            if float(result.get("slippage_percent_per_side", -1)) != 0.01:
                raise RuntimeError("슬리피지 고정값 불일치")
            completed[key] = {
                "entry_multiplier": entry,
                "max_entries": entries,
                "result": _compact_risk_result(result),
            }
            checkpoint["last_completed"] = key
            checkpoint["last_error"] = None
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

    viable = [
        row for row in completed.values()
        if int(row["result"].get("trades") or 0) > 0
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
    best_overrides.update(FIXED_BACKTEST)
    best_overrides["order_percent_of_equity"] = float(best["entry_multiplier"] * 100)
    best_overrides["max_pyramiding"] = int(best["max_entries"])
    full_result = run_cached_symbol_backtest(
        symbol=symbol,
        asset_class="crypto",
        exchange="bitget",
        timeframe=timeframe,
        start=start_text,
        end=end_text,
        overrides=best_overrides,
        database_path=db,
    )
    checkpoint["stage"] = "COMPLETE"
    checkpoint["best"] = best
    _save_json_atomic(checkpoint_path, checkpoint)
    selection = {
        "profile": profile_name,
        "constraints": profile,
        "entry_multiplier": best["entry_multiplier"],
        "max_entries": best["max_entries"],
        "checkpoint": str(checkpoint_path),
        "tested_combinations": len(combinations),
        "viable_combinations": len(viable),
    }
    return full_result, selection



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
) -> str:
    logs: list[str] = []
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
            logs.append(
                f"서버 전략 설정 동기화 실패 - 현재 앱 기본값 사용: {type(exc).__name__}: {exc}"
            )
    selected_profile = risk_profile.strip() if risk_profile else "공격형"
    if selected_profile not in RISK_PROFILES:
        selected_profile = "공격형"
    overrides.update(FIXED_BACKTEST)
    overrides["order_percent_of_equity"] = 100.0
    overrides["max_pyramiding"] = 1
    profile = RISK_PROFILES[selected_profile]
    logs.append(
        f"위험 프로필: {selected_profile} · MDD {profile['mdd_limit_percent']:.0f}% 이하 · "
        f"진입 {profile['entry_multiplier_min']}~{profile['entry_multiplier_max']}배 · "
        f"최대 진입 {profile['max_entries_values']}"
    )
    logs.append("기간은 사용자가 선택한 날짜를 그대로 사용합니다.")
    logs.append("고정 비용: 수수료 편도 0.02% · 슬리피지 편도 0.01%")

    db, result, summary = build_cache_and_backtest(
        symbol.strip(),
        timeframe.strip(),
        start_text.strip(),
        end_text.strip(),
        Path(output_dir),
        logs.append,
        strategy_overrides=overrides,
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
        logs.append,
    )
    for key in (
        "trades", "wins", "win_rate", "profit_factor", "pnl", "gross_pnl",
        "estimated_costs", "return_percent", "max_drawdown_percent",
        "trades_log", "equity_curve", "data_start", "data_end",
    ):
        summary[key] = optimized_result.get(key)
    summary["risk_profile"] = selected_profile
    summary["risk_profile_selection"] = risk_selection
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


def list_saved_results(output_dir: str) -> str:
    history_dir = Path(output_dir) / "BacktestResults"
    items: list[dict] = []
    candidates = list(history_dir.glob("*-backtest.json")) if history_dir.is_dir() else []
    candidates.extend(Path(output_dir).glob("*backtest.json"))
    for path in sorted(set(candidates), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
            db = Path(str(meta.get("database", "")))
            if not db.is_file():
                continue
            items.append(
                {
                    "path": str(path),
                    "db": str(db),
                    "summary": meta,
                    "label": (
                        f"{meta.get('symbol', '-')} · {meta.get('requested_start', '-')}~"
                        f"{meta.get('requested_end', '-')} · {meta.get('created_at', '-')}"
                    ),
                }
            )
        except Exception:
            continue
    return json.dumps({"items": items}, ensure_ascii=False)


def load_saved_result(result_path: str) -> str:
    path = Path(result_path)
    if not path.is_file():
        raise RuntimeError(f"저장된 결과 파일이 없습니다: {result_path}")
    meta = json.loads(path.read_text(encoding="utf-8"))
    db = Path(str(meta.get("database", "")))
    if not db.is_file():
        raise RuntimeError(f"연결된 캐시 DB가 없습니다: {db}")
    return json.dumps({"result": str(path), "db": str(db), "summary": meta}, ensure_ascii=False)


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
        raise RuntimeError("서버 업로드 차단: 1년 범위(360~370일)로 완료된 캐시만 업로드할 수 있습니다.")
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
    canonical_result.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return str(
        _ssh_bridge().uploadFiles(
            db_path,
            str(canonical_result),
            host.strip(),
            username.strip(),
            remote_dir.strip(),
            key_path.strip(),
        )
    )
