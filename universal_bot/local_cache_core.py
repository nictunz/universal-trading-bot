from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from universal_bot.archive_historical import OfficialArchiveHistoricalDataManager
from universal_bot.backtest_service import _validate_crypto_data
from universal_bot.config import Settings
from universal_bot.fast_backtest import run_cached_symbol_backtest
from universal_bot.historical import DataRequest

EXCHANGES = ("binance", "bitget", "okx", "bybit")
DEFAULT_SERVER = "34.132.172.40"
DEFAULT_USER = "kpj3669"
DEFAULT_REMOTE_DIR = "/home/kpj3669/.cache/universal-trading-bot"
MIN_SERVER_UPLOAD_DAYS = 360
MAX_SERVER_UPLOAD_DAYS = 370
MAX_BACKTEST_DAYS = 3660
COMMON_SYMBOLS = (
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "BNB/USDT:USDT",
    "DOGE/USDT:USDT",
    "ADA/USDT:USDT",
    "AVAX/USDT:USDT",
    "LINK/USDT:USDT",
)
COMMON_TIMEFRAMES = ("1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d")


def symbol_slug(symbol: str) -> str:
    base = symbol.split(":", 1)[0].split("/", 1)[0].strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return slug or "asset"


def parse_day(value: str, end: bool = False) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if end:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt.astimezone(timezone.utc)


def inclusive_days(start_text: str, end_text: str) -> int:
    start = datetime.fromisoformat(start_text).date()
    end = datetime.fromisoformat(end_text).date()
    days = (end - start).days + 1
    if days <= 0:
        raise ValueError("종료일은 시작일보다 같거나 뒤여야 합니다.")
    if days > MAX_BACKTEST_DAYS:
        raise ValueError("백테스트 기간은 최대 10년(3660일)까지 가능합니다.")
    return days


def server_upload_eligible(start_text: str, end_text: str) -> bool:
    days = inclusive_days(start_text, end_text)
    return MIN_SERVER_UPLOAD_DAYS <= days <= MAX_SERVER_UPLOAD_DAYS


def cache_file_names(symbol: str, timeframe: str, start_text: str, end_text: str) -> tuple[str, str]:
    slug = symbol_slug(symbol)
    if server_upload_eligible(start_text, end_text):
        return f"{slug}-1y-{timeframe}.db", f"latest-{slug}-one-year-backtest.json"
    start_tag = start_text.replace("-", "")
    end_tag = end_text.replace("-", "")
    return (
        f"{slug}-{start_tag}-{end_tag}-{timeframe}.db",
        f"latest-{slug}-{start_tag}-{end_tag}-backtest.json",
    )


def month_chunks(start: datetime, end: datetime):
    cursor = start
    while cursor <= end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        stop = min(end, next_month - timedelta(microseconds=1))
        yield cursor, stop
        cursor = next_month


def _sync_with_retry(
    manager: OfficialArchiveHistoricalDataManager,
    req: DataRequest,
    log: Callable[[str], None],
    attempts: int = 4,
):
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return manager.sync(req)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = 2 ** (attempt - 1)
            log(
                f"일시적 다운로드 오류 ({type(exc).__name__}: {exc}) "
                f"- {delay}초 후 재시도 {attempt + 1}/{attempts}"
            )
            time.sleep(delay)

    if req.start is not None and req.end is not None:
        span = req.end - req.start
        if span > timedelta(days=2):
            midpoint = req.start + span / 2
            left_end = midpoint
            right_start = midpoint + timedelta(microseconds=1)
            log(
                f"{req.exchange} {req.start:%Y-%m-%d}..{req.end:%Y-%m-%d} "
                f"연속 실패 - {req.start:%m-%d}..{left_end:%m-%d}, "
                f"{right_start:%m-%d}..{req.end:%m-%d} 구간으로 자동 분할"
            )
            left = DataRequest(
                symbol=req.symbol,
                timeframe=req.timeframe,
                start=req.start,
                end=left_end,
                asset_class=req.asset_class,
                exchange=req.exchange,
            )
            right = DataRequest(
                symbol=req.symbol,
                timeframe=req.timeframe,
                start=right_start,
                end=req.end,
                asset_class=req.asset_class,
                exchange=req.exchange,
            )
            left_inserted, _ = _sync_with_retry(manager, left, log, attempts=3)
            right_inserted, _ = _sync_with_retry(manager, right, log, attempts=3)
            return left_inserted + right_inserted, manager.read(req)

    detail = f"{type(last_error).__name__}: {last_error}" if last_error else "알 수 없는 오류"
    raise RuntimeError(
        f"{req.exchange} {req.start:%Y-%m-%d}..{req.end:%Y-%m-%d} "
        f"다운로드가 {attempts}회 실패했습니다. 마지막 원인: {detail}. "
        f"앱을 다시 실행하면 저장된 캐시 다음부터 이어받습니다."
    ) from last_error

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _downsample_equity(points: list[dict], max_points: int = 1200) -> list[dict]:
    if len(points) <= max_points:
        return points
    step = max(1, (len(points) + max_points - 1) // max_points)
    sampled = points[::step]
    if sampled[-1] is not points[-1]:
        sampled.append(points[-1])
    return sampled


def build_cache_and_backtest(
    symbol: str,
    timeframe: str,
    start_text: str,
    end_text: str,
    output_dir: Path,
    log: Callable[[str], None],
    strategy_overrides: dict | None = None,
) -> tuple[Path, Path, dict]:
    os.environ["CRYPTO_VOLUME_PROVIDER"] = "none"
    os.environ["COINAPI_API_KEY"] = ""
    os.environ["USE_FOUR_CRYPTO_EXCHANGES"] = "true"

    start = parse_day(start_text)
    end = parse_day(end_text, end=True)
    range_days = inclusive_days(start_text, end_text)
    upload_eligible = server_upload_eligible(start_text, end_text)

    output_dir.mkdir(parents=True, exist_ok=True)
    db_name, result_name = cache_file_names(symbol, timeframe, start_text, end_text)
    db = output_dir / db_name
    os.environ["DATABASE_URL"] = f"sqlite:///{db}"

    settings = Settings().model_copy(update=dict(strategy_overrides or {}))
    manager = OfficialArchiveHistoricalDataManager(settings.database_url, coinapi_api_key="", fallback_exchanges=[])
    if strategy_overrides:
        log(f"서버 전략 설정 동기화 완료: {len(strategy_overrides)}개 조정값")

    log(f"심볼: {symbol}")
    log(f"타임프레임: {timeframe}")
    log(f"기간: {start_text} ~ {end_text} ({range_days}일)")
    log(f"캐시: {db}")
    if upload_eligible:
        log("서버 업로드 보호: 1년 범위 확인됨 - 완료 후 업로드 가능")
    else:
        log("서버 업로드 보호: 테스트/비1년 범위 - 서버 업로드 자동 잠금")

    for exchange in EXCHANGES:
        log(f"\n===== {exchange.upper()} =====")
        for chunk_start, chunk_end in month_chunks(start, end):
            req = DataRequest(
                symbol=symbol,
                timeframe=timeframe,
                start=chunk_start,
                end=chunk_end,
                asset_class="crypto",
                exchange=exchange,
            )
            log(f"{exchange:7s} {chunk_start:%Y-%m-%d}..{chunk_end:%Y-%m-%d} 확인/다운로드")
            inserted, df = _sync_with_retry(manager, req, log)
            if df.empty:
                raise RuntimeError(f"{exchange} 데이터 없음: {chunk_start.date()}..{chunk_end.date()}")
            _validate_crypto_data(df, timeframe, label=f"{exchange}:{chunk_start:%Y-%m}")
            mode = manager.last_fetch_status.get(exchange, {}).get("mode", "CACHE")
            log(
                f"{exchange:7s} {chunk_start:%Y-%m-%d}..{chunk_end:%Y-%m-%d} "
                f"bars={len(df)} inserted={inserted} mode={mode}"
            )

    log("\n===== CACHE ONLY BACKTEST =====")
    result = run_cached_symbol_backtest(
        symbol=symbol,
        asset_class="crypto",
        exchange="bitget",
        timeframe=timeframe,
        start=start_text,
        end=end_text,
        database_path=db,
        overrides=dict(strategy_overrides or {}),
    )

    keys = (
        "symbol", "bars", "four_exchange_volume", "volume_source_bars", "volume_source_status",
        "trades", "wins", "win_rate", "profit_factor", "pnl", "gross_pnl", "estimated_costs",
        "return_percent", "max_drawdown_percent", "data_start", "data_end",
    )
    summary = {k: result.get(k) for k in keys}
    summary.update({
        "trades_log": result.get("trades_log", []),
        "equity_curve": _downsample_equity(result.get("equity_curve", [])),
        "requested_start": start_text,
        "requested_end": end_text,
        "range_days": range_days,
        "server_upload_eligible": upload_eligible,
        "database": str(db),
        "fast_cache": True,
        "cache_sha256": sha256_file(db),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    result_path = output_dir / result_name
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(json.dumps(summary, ensure_ascii=False, indent=2))
    log("BACKTEST COMPLETE")
    return db, result_path, summary


def _ssh_kwargs(host: str, username: str, password: str = "", key_path: str = "") -> dict:
    kwargs: dict = {
        "hostname": host,
        "username": username,
        "port": 22,
        "timeout": 15,
        "banner_timeout": 15,
        "auth_timeout": 15,
    }
    if key_path.strip():
        kwargs["key_filename"] = key_path.strip()
    if password:
        kwargs["password"] = password
    return kwargs


def test_ssh_connection(host: str, username: str, password: str = "", key_path: str = "") -> str:
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(**_ssh_kwargs(host, username, password, key_path))
    try:
        _, stdout, _ = client.exec_command("printf 'SSH_OK'")
        text = stdout.read().decode("utf-8", errors="replace").strip()
        if text != "SSH_OK":
            raise RuntimeError("SSH 연결은 되었지만 서버 응답 확인에 실패했습니다.")
        return "SSH_OK"
    finally:
        client.close()


def upload_to_server(
    db: Path,
    result_path: Path,
    host: str,
    username: str,
    remote_dir: str,
    password: str,
    key_path: str,
    log: Callable[[str], None],
) -> None:
    import paramiko

    result_meta = json.loads(result_path.read_text(encoding="utf-8"))
    start_text = str(result_meta.get("requested_start", ""))
    end_text = str(result_meta.get("requested_end", ""))
    if not start_text or not end_text or not server_upload_eligible(start_text, end_text):
        raise RuntimeError("서버 업로드 차단: 1년 범위(360~370일)로 완료된 캐시만 서버에 업로드할 수 있습니다.")
    if not bool(result_meta.get("server_upload_eligible", False)):
        raise RuntimeError("서버 업로드 차단: 결과 파일이 서버 업로드용으로 검증되지 않았습니다.")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    log(f"SSH 연결: {username}@{host}")
    client.connect(**_ssh_kwargs(host, username, password, key_path))
    sftp = client.open_sftp()
    try:
        client.exec_command(f"mkdir -p {remote_dir}")
        for local in (db, result_path):
            remote = f"{remote_dir.rstrip('/')}/{local.name}"
            temp = remote + ".uploading"
            log(f"업로드: {local.name}")
            sftp.put(str(local), temp, confirm=True)
            try:
                sftp.remove(remote)
            except FileNotFoundError:
                pass
            sftp.rename(temp, remote)
            log(f"완료: {remote}")

        manifest = {
            "database": db.name,
            "result": result_path.name,
            "requested_start": start_text,
            "requested_end": end_text,
            "range_days": inclusive_days(start_text, end_text),
            "database_sha256": sha256_file(db),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_local = db.parent / f"{db.stem}.upload-manifest.json"
        manifest_local.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        remote_manifest = f"{remote_dir.rstrip('/')}/{manifest_local.name}"
        sftp.put(str(manifest_local), remote_manifest, confirm=True)
        log("서버 캐시 업로드 완료. 대시보드의 빠른 재백테스트에서 바로 사용할 수 있습니다.")
    finally:
        sftp.close()
        client.close()
