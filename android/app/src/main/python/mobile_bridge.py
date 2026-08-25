from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from universal_bot.local_cache_core import (
    DEFAULT_REMOTE_DIR,
    DEFAULT_SERVER,
    DEFAULT_USER,
    build_cache_and_backtest,
    server_upload_eligible,
)


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
    db, result, summary = build_cache_and_backtest(
        symbol.strip(),
        timeframe.strip(),
        start_text.strip(),
        end_text.strip(),
        Path(output_dir),
        logs.append,
        strategy_overrides=overrides,
    )
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
