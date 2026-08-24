from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import threading
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from universal_bot.archive_historical import OfficialArchiveHistoricalDataManager
from universal_bot.backtest_service import _validate_crypto_data
from universal_bot.config import Settings
from universal_bot.fast_backtest import run_cached_symbol_backtest
from universal_bot.historical import DataRequest

EXCHANGES = ("binance", "bitget", "okx", "bybit")
DEFAULT_SERVER = "34.132.172.40"
DEFAULT_USER = "kpj3669"
DEFAULT_REMOTE_DIR = "/home/kpj3669/.cache/universal-trading-bot"


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


def month_chunks(start: datetime, end: datetime):
    cursor = start
    while cursor <= end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        stop = min(end, next_month - timedelta(microseconds=1))
        yield cursor, stop
        cursor = next_month


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_cache_and_backtest(
    symbol: str,
    timeframe: str,
    start_text: str,
    end_text: str,
    output_dir: Path,
    log: Callable[[str], None],
) -> tuple[Path, Path, dict]:
    os.environ["CRYPTO_VOLUME_PROVIDER"] = "none"
    os.environ["COINAPI_API_KEY"] = ""
    os.environ["USE_FOUR_CRYPTO_EXCHANGES"] = "true"

    output_dir.mkdir(parents=True, exist_ok=True)
    slug = symbol_slug(symbol)
    db = output_dir / f"{slug}-1y-{timeframe}.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db}"

    start = parse_day(start_text)
    end = parse_day(end_text, end=True)
    settings = Settings()
    manager = OfficialArchiveHistoricalDataManager(settings.database_url, coinapi_api_key="", fallback_exchanges=[])

    log(f"심볼: {symbol}")
    log(f"기간: {start_text} ~ {end_text}")
    log(f"캐시: {db}")

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
            inserted, df = manager.sync(req)
            if df.empty:
                raise RuntimeError(f"{exchange} 데이터 없음: {chunk_start.date()}..{chunk_end.date()}")
            _validate_crypto_data(df, timeframe, label=f"{exchange}:{chunk_start:%Y-%m}")
            mode = manager.last_fetch_status.get(exchange, {}).get("mode", "CACHE")
            log(f"{exchange:7s} {chunk_start:%Y-%m-%d}..{chunk_end:%Y-%m-%d} bars={len(df)} inserted={inserted} mode={mode}")

    log("\n===== CACHE ONLY BACKTEST =====")
    result = run_cached_symbol_backtest(
        symbol=symbol,
        asset_class="crypto",
        exchange="bitget",
        timeframe=timeframe,
        start=start_text,
        end=end_text,
        database_path=db,
    )

    keys = (
        "symbol", "bars", "four_exchange_volume", "volume_source_bars", "volume_source_status",
        "trades", "wins", "win_rate", "profit_factor", "pnl", "gross_pnl", "estimated_costs",
        "return_percent", "max_drawdown_percent", "data_start", "data_end",
    )
    summary = {k: result.get(k) for k in keys}
    summary.update({
        "requested_start": start_text,
        "requested_end": end_text,
        "database": str(db),
        "fast_cache": True,
        "cache_sha256": sha256_file(db),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    result_path = output_dir / f"latest-{slug}-one-year-backtest.json"
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(json.dumps(summary, ensure_ascii=False, indent=2))
    log("BACKTEST COMPLETE")
    return db, result_path, summary


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

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = {
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
    log(f"SSH 연결: {username}@{host}")
    client.connect(**kwargs)
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


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Universal Trading Backtester")
        self.geometry("900x700")
        self.minsize(760, 600)
        self.queue: queue.Queue[str] = queue.Queue()
        self.last_db: Path | None = None
        self.last_result: Path | None = None
        self._build()
        self.after(150, self._drain)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        frm = ttk.LabelFrame(root, text="로컬 1년 캐시 / 백테스트", padding=10)
        frm.pack(fill="x")
        self.symbol = tk.StringVar(value="ETH/USDT:USDT")
        self.tf = tk.StringVar(value="5m")
        self.start = tk.StringVar(value="2025-08-19")
        self.end = tk.StringVar(value="2026-08-18")
        self.outdir = tk.StringVar(value=str(Path.home() / "UniversalTradingBotCache"))
        labels = [("심볼", self.symbol), ("타임프레임", self.tf), ("시작일", self.start), ("종료일", self.end)]
        for i, (label, var) in enumerate(labels):
            ttk.Label(frm, text=label).grid(row=0, column=i, sticky="w", padx=4)
            ttk.Entry(frm, textvariable=var, width=18).grid(row=1, column=i, sticky="ew", padx=4)
        ttk.Label(frm, text="저장 폴더").grid(row=2, column=0, sticky="w", pady=(10, 0), padx=4)
        ttk.Entry(frm, textvariable=self.outdir).grid(row=3, column=0, columnspan=3, sticky="ew", padx=4)
        ttk.Button(frm, text="폴더 선택", command=self._pick_outdir).grid(row=3, column=3, padx=4)
        self.run_btn = ttk.Button(frm, text="▶ 캐시 생성 + 백테스트", command=self._run)
        self.run_btn.grid(row=4, column=0, columnspan=4, sticky="ew", padx=4, pady=10)
        for c in range(4):
            frm.columnconfigure(c, weight=1)

        up = ttk.LabelFrame(root, text="서버 바로 업로드 (SFTP/SSH)", padding=10)
        up.pack(fill="x", pady=(10, 0))
        self.host = tk.StringVar(value=DEFAULT_SERVER)
        self.user = tk.StringVar(value=DEFAULT_USER)
        self.remote = tk.StringVar(value=DEFAULT_REMOTE_DIR)
        self.password = tk.StringVar()
        self.key = tk.StringVar()
        ttk.Label(up, text="서버").grid(row=0, column=0, sticky="w")
        ttk.Entry(up, textvariable=self.host).grid(row=1, column=0, sticky="ew", padx=(0, 6))
        ttk.Label(up, text="사용자").grid(row=0, column=1, sticky="w")
        ttk.Entry(up, textvariable=self.user).grid(row=1, column=1, sticky="ew", padx=(0, 6))
        ttk.Label(up, text="원격 폴더").grid(row=0, column=2, sticky="w")
        ttk.Entry(up, textvariable=self.remote).grid(row=1, column=2, sticky="ew")
        ttk.Label(up, text="SSH 비밀번호 (선택)").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(up, textvariable=self.password, show="*").grid(row=3, column=0, sticky="ew", padx=(0, 6))
        ttk.Label(up, text="SSH 개인키 (선택)").grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Entry(up, textvariable=self.key).grid(row=3, column=1, sticky="ew", padx=(0, 6))
        ttk.Button(up, text="키 선택", command=self._pick_key).grid(row=3, column=2, sticky="w")
        self.upload_btn = ttk.Button(up, text="⬆ 마지막 결과 서버 업로드", command=self._upload, state="disabled")
        self.upload_btn.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        for c in range(3):
            up.columnconfigure(c, weight=1)

        self.status = ttk.Label(root, text="준비됨")
        self.status.pack(fill="x", pady=(10, 4))
        self.log = tk.Text(root, height=22, wrap="none")
        self.log.pack(fill="both", expand=True)

    def _pick_outdir(self) -> None:
        p = filedialog.askdirectory(initialdir=self.outdir.get() or str(Path.home()))
        if p:
            self.outdir.set(p)

    def _pick_key(self) -> None:
        p = filedialog.askopenfilename(title="SSH 개인키 선택")
        if p:
            self.key.set(p)

    def _emit(self, text: str) -> None:
        self.queue.put(text)

    def _drain(self) -> None:
        try:
            while True:
                msg = self.queue.get_nowait()
                self.log.insert("end", msg + "\n")
                self.log.see("end")
        except queue.Empty:
            pass
        self.after(150, self._drain)

    def _run(self) -> None:
        self.run_btn.config(state="disabled")
        self.upload_btn.config(state="disabled")
        self.status.config(text="백테스트 실행 중...")
        def worker():
            try:
                db, result, summary = build_cache_and_backtest(
                    self.symbol.get().strip(), self.tf.get().strip(), self.start.get().strip(), self.end.get().strip(),
                    Path(self.outdir.get()).expanduser(), self._emit,
                )
                self.last_db, self.last_result = db, result
                self.after(0, lambda: self.status.config(text=f"완료 · 거래 {summary.get('trades')} · 승률 {summary.get('win_rate', 0):.2f}%"))
                self.after(0, lambda: self.upload_btn.config(state="normal"))
            except Exception:
                self._emit(traceback.format_exc())
                self.after(0, lambda: self.status.config(text="오류 발생 - 로그 확인"))
                self.after(0, lambda: messagebox.showerror("백테스트 오류", "오류가 발생했습니다. 로그를 확인하세요."))
            finally:
                self.after(0, lambda: self.run_btn.config(state="normal"))
        threading.Thread(target=worker, daemon=True).start()

    def _upload(self) -> None:
        if not self.last_db or not self.last_result:
            messagebox.showwarning("업로드", "먼저 백테스트를 완료하세요.")
            return
        self.upload_btn.config(state="disabled")
        self.status.config(text="서버 업로드 중...")
        def worker():
            try:
                upload_to_server(
                    self.last_db, self.last_result, self.host.get().strip(), self.user.get().strip(), self.remote.get().strip(),
                    self.password.get(), self.key.get(), self._emit,
                )
                self.after(0, lambda: self.status.config(text="서버 업로드 완료"))
                self.after(0, lambda: messagebox.showinfo("완료", "서버 업로드가 완료되었습니다."))
            except Exception:
                self._emit(traceback.format_exc())
                self.after(0, lambda: self.status.config(text="업로드 오류 - 로그 확인"))
                self.after(0, lambda: messagebox.showerror("업로드 오류", "서버 업로드에 실패했습니다. 로그를 확인하세요."))
            finally:
                self.after(0, lambda: self.upload_btn.config(state="normal"))
        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
