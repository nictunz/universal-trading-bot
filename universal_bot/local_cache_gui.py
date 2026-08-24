from __future__ import annotations

import queue
import threading
import traceback
from datetime import date, timedelta
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkcalendar import DateEntry

from universal_bot.local_cache_core import (
    COMMON_SYMBOLS,
    COMMON_TIMEFRAMES,
    DEFAULT_REMOTE_DIR,
    DEFAULT_SERVER,
    DEFAULT_USER,
    build_cache_and_backtest,
    test_ssh_connection,
    upload_to_server,
)

BG = "#0b1220"
PANEL = "#111827"
CARD = "#172033"
BORDER = "#263247"
TEXT = "#f8fafc"
MUTED = "#94a3b8"
ACCENT = "#38bdf8"
GOOD = "#34d399"
WARN = "#fbbf24"
DANGER = "#fb7185"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Universal Trading Backtester")
        self.geometry("1180x820")
        self.minsize(980, 720)
        self.configure(bg=BG)
        self.queue: queue.Queue[str] = queue.Queue()
        self.last_db: Path | None = None
        self.last_result: Path | None = None
        self.last_summary: dict | None = None
        self._setup_style()
        self._build()
        self.after(150, self._drain)

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 20))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 11))
        style.configure("CardTitle.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("CardValue.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 17))
        style.configure("Status.TLabel", background=PANEL, foreground=ACCENT, font=("Segoe UI Semibold", 10))
        style.configure("TEntry", fieldbackground="#0f172a", foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER)
        style.configure("TCombobox", fieldbackground="#0f172a", foreground=TEXT, arrowcolor=TEXT, bordercolor=BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", "#0f172a")], foreground=[("readonly", TEXT)])
        style.configure("TButton", background="#1e293b", foreground=TEXT, bordercolor=BORDER, padding=(10, 7))
        style.map("TButton", background=[("active", "#334155")])
        style.configure("Primary.TButton", background="#0284c7", foreground="white", bordercolor="#0284c7", padding=(12, 9), font=("Segoe UI Semibold", 10))
        style.map("Primary.TButton", background=[("active", "#0369a1"), ("disabled", "#334155")])
        style.configure("Success.TButton", background="#047857", foreground="white", bordercolor="#047857", padding=(12, 9), font=("Segoe UI Semibold", 10))
        style.map("Success.TButton", background=[("active", "#065f46"), ("disabled", "#334155")])

    def _build(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="Universal Trading Backtester", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="PC에서 4개 거래소 장기 캐시를 만들고 전략을 백테스트한 뒤 서버로 안전하게 업로드합니다.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        top = ttk.Frame(root)
        top.pack(fill="x")
        left = ttk.Frame(top, style="Panel.TFrame", padding=14)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = ttk.Frame(top, style="Panel.TFrame", padding=14)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self._build_backtest_panel(left)
        self._build_server_panel(right)
        self._build_metrics(root)

        lower = ttk.Frame(root, style="Panel.TFrame", padding=12)
        lower.pack(fill="both", expand=True, pady=(14, 0))
        status_row = ttk.Frame(lower, style="Panel.TFrame")
        status_row.pack(fill="x", pady=(0, 8))
        ttk.Label(status_row, text="실행 로그", style="Section.TLabel").pack(side="left")
        self.status = ttk.Label(status_row, text="준비됨", style="Status.TLabel")
        self.status.pack(side="right")
        self.log = tk.Text(
            lower,
            height=18,
            wrap="none",
            bg="#07101d",
            fg="#dbeafe",
            insertbackground=TEXT,
            relief="flat",
            padx=10,
            pady=10,
            font=("Consolas", 9),
        )
        self.log.pack(fill="both", expand=True)

    def _build_backtest_panel(self, panel: ttk.Frame) -> None:
        ttk.Label(panel, text="로컬 캐시 / 백테스트", style="Section.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        self.symbol = tk.StringVar(value="ETH/USDT:USDT")
        self.tf = tk.StringVar(value="5m")
        self.outdir = tk.StringVar(value=str(Path.home() / "UniversalTradingBotCache"))

        ttk.Label(panel, text="심볼", style="Section.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(panel, text="타임프레임", style="Section.TLabel").grid(row=1, column=2, sticky="w")
        symbol_box = ttk.Combobox(panel, textvariable=self.symbol, values=COMMON_SYMBOLS, state="normal")
        symbol_box.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 8), pady=(3, 9))
        tf_box = ttk.Combobox(panel, textvariable=self.tf, values=COMMON_TIMEFRAMES, state="normal")
        tf_box.grid(row=2, column=2, columnspan=2, sticky="ew", pady=(3, 9))

        ttk.Label(panel, text="시작일", style="Section.TLabel").grid(row=3, column=0, sticky="w")
        ttk.Label(panel, text="종료일", style="Section.TLabel").grid(row=3, column=2, sticky="w")
        today = date.today()
        default_end = today
        default_start = default_end - timedelta(days=364)
        self.start_date = DateEntry(panel, date_pattern="yyyy-mm-dd", year=default_start.year, month=default_start.month, day=default_start.day)
        self.start_date.grid(row=4, column=0, columnspan=2, sticky="ew", padx=(0, 8), pady=(3, 8))
        self.end_date = DateEntry(panel, date_pattern="yyyy-mm-dd", year=default_end.year, month=default_end.month, day=default_end.day)
        self.end_date.grid(row=4, column=2, columnspan=2, sticky="ew", pady=(3, 8))

        quick = ttk.Frame(panel, style="Panel.TFrame")
        quick.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(0, 9))
        ttk.Label(quick, text="빠른 기간", style="Section.TLabel").pack(side="left", padx=(0, 8))
        for text, days in (("30일", 30), ("90일", 90), ("180일", 180), ("1년", 365)):
            ttk.Button(quick, text=text, command=lambda d=days: self._set_range(d)).pack(side="left", padx=3)

        ttk.Label(panel, text="저장 폴더", style="Section.TLabel").grid(row=6, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.outdir).grid(row=7, column=0, columnspan=3, sticky="ew", padx=(0, 8), pady=(3, 10))
        ttk.Button(panel, text="폴더 선택", command=self._pick_outdir).grid(row=7, column=3, sticky="ew", pady=(3, 10))

        self.run_btn = ttk.Button(panel, text="▶ 캐시 생성 + 백테스트", command=self._run, style="Primary.TButton")
        self.run_btn.grid(row=8, column=0, columnspan=4, sticky="ew")
        ttk.Label(
            panel,
            text="자주 쓰는 값은 목록에서 고르고, 목록에 없으면 심볼/타임프레임 칸에 직접 입력할 수 있습니다.",
            style="Section.TLabel",
        ).grid(row=9, column=0, columnspan=4, sticky="w", pady=(9, 0))
        for c in range(4):
            panel.columnconfigure(c, weight=1)

    def _build_server_panel(self, panel: ttk.Frame) -> None:
        ttk.Label(panel, text="서버 업로드", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self.host = tk.StringVar(value=DEFAULT_SERVER)
        self.user = tk.StringVar(value=DEFAULT_USER)
        self.remote = tk.StringVar(value=DEFAULT_REMOTE_DIR)
        self.password = tk.StringVar()
        self.key = tk.StringVar(value=str(Path.home() / ".ssh" / "id_ed25519"))

        fields = (("서버", self.host), ("사용자", self.user), ("원격 폴더", self.remote))
        for col, (label, var) in enumerate(fields):
            ttk.Label(panel, text=label, style="Section.TLabel").grid(row=1, column=col, sticky="w")
            ttk.Entry(panel, textvariable=var).grid(row=2, column=col, sticky="ew", padx=(0, 8) if col < 2 else 0, pady=(3, 9))

        ttk.Label(panel, text="SSH 비밀번호 (선택)", style="Section.TLabel").grid(row=3, column=0, sticky="w")
        ttk.Label(panel, text="SSH 개인키", style="Section.TLabel").grid(row=3, column=1, sticky="w")
        ttk.Entry(panel, textvariable=self.password, show="*").grid(row=4, column=0, sticky="ew", padx=(0, 8), pady=(3, 9))
        ttk.Entry(panel, textvariable=self.key).grid(row=4, column=1, sticky="ew", padx=(0, 8), pady=(3, 9))
        ttk.Button(panel, text="키 선택", command=self._pick_key).grid(row=4, column=2, sticky="ew", pady=(3, 9))

        self.ssh_btn = ttk.Button(panel, text="SSH 연결 테스트", command=self._test_ssh)
        self.ssh_btn.grid(row=5, column=0, sticky="ew", padx=(0, 8))
        self.upload_btn = ttk.Button(panel, text="⬆ 1년 결과 서버 업로드", command=self._upload, state="disabled", style="Success.TButton")
        self.upload_btn.grid(row=5, column=1, columnspan=2, sticky="ew")
        ttk.Label(
            panel,
            text="보호 기능: 360~370일 범위로 완성된 캐시만 서버에 업로드할 수 있습니다.",
            style="Section.TLabel",
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(9, 0))
        for c in range(3):
            panel.columnconfigure(c, weight=1)

    def _build_metrics(self, root: ttk.Frame) -> None:
        metrics = ttk.Frame(root)
        metrics.pack(fill="x", pady=(14, 0))
        self.metric_vars: dict[str, tk.StringVar] = {}
        items = (("거래", "trades"), ("승률", "win_rate"), ("Profit Factor", "profit_factor"), ("수익률", "return_percent"), ("MDD", "max_drawdown_percent"))
        for i, (title, key) in enumerate(items):
            card = ttk.Frame(metrics, style="Card.TFrame", padding=12)
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 5, 0 if i == len(items) - 1 else 5))
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            var = tk.StringVar(value="—")
            ttk.Label(card, textvariable=var, style="CardValue.TLabel").pack(anchor="w", pady=(4, 0))
            self.metric_vars[key] = var
            metrics.columnconfigure(i, weight=1)

    def _set_range(self, days: int) -> None:
        end = self.end_date.get_date()
        self.start_date.set_date(end - timedelta(days=days - 1))

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

    def _date_texts(self) -> tuple[str, str]:
        return self.start_date.get_date().isoformat(), self.end_date.get_date().isoformat()

    def _update_metrics(self, summary: dict) -> None:
        def num(key: str, suffix: str = "", digits: int = 2) -> str:
            value = summary.get(key)
            if value is None:
                return "—"
            try:
                return f"{float(value):.{digits}f}{suffix}"
            except (TypeError, ValueError):
                return str(value)
        self.metric_vars["trades"].set(str(summary.get("trades", "—")))
        self.metric_vars["win_rate"].set(num("win_rate", "%"))
        self.metric_vars["profit_factor"].set(num("profit_factor"))
        self.metric_vars["return_percent"].set(num("return_percent", "%"))
        self.metric_vars["max_drawdown_percent"].set(num("max_drawdown_percent", "%"))

    def _run(self) -> None:
        self.run_btn.config(state="disabled")
        self.upload_btn.config(state="disabled")
        self.last_db = None
        self.last_result = None
        self.last_summary = None
        self.status.config(text="백테스트 실행 중...")
        start_text, end_text = self._date_texts()

        def worker() -> None:
            try:
                db, result, summary = build_cache_and_backtest(
                    self.symbol.get().strip(),
                    self.tf.get().strip(),
                    start_text,
                    end_text,
                    Path(self.outdir.get()).expanduser(),
                    self._emit,
                )
                self.last_db, self.last_result, self.last_summary = db, result, summary
                self.after(0, lambda: self._update_metrics(summary))
                if bool(summary.get("server_upload_eligible")):
                    self.after(0, lambda: self.status.config(text="완료 · 서버 업로드 가능"))
                    self.after(0, lambda: self.upload_btn.config(state="normal"))
                else:
                    self._emit("서버 업로드 잠금: 테스트/비1년 캐시는 로컬에만 저장됩니다.")
                    self.after(0, lambda: self.status.config(text="완료 · 테스트 캐시(업로드 잠금)"))
            except Exception:
                self._emit(traceback.format_exc())
                self.after(0, lambda: self.status.config(text="오류 발생 - 로그 확인"))
                self.after(0, lambda: messagebox.showerror("백테스트 오류", "오류가 발생했습니다. 로그를 확인하세요."))
            finally:
                self.after(0, lambda: self.run_btn.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _test_ssh(self) -> None:
        self.ssh_btn.config(state="disabled")
        self.status.config(text="SSH 연결 확인 중...")

        def worker() -> None:
            try:
                test_ssh_connection(self.host.get().strip(), self.user.get().strip(), self.password.get(), self.key.get())
                self._emit("SSH 연결 테스트: 성공")
                self.after(0, lambda: self.status.config(text="SSH 연결 성공"))
                self.after(0, lambda: messagebox.showinfo("SSH", "서버 SSH 연결에 성공했습니다."))
            except Exception:
                self._emit(traceback.format_exc())
                self.after(0, lambda: self.status.config(text="SSH 연결 실패"))
                self.after(0, lambda: messagebox.showerror("SSH", "SSH 연결에 실패했습니다. 로그를 확인하세요."))
            finally:
                self.after(0, lambda: self.ssh_btn.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _upload(self) -> None:
        if not self.last_db or not self.last_result or not self.last_summary:
            messagebox.showwarning("업로드", "먼저 1년 백테스트를 완료하세요.")
            return
        if not bool(self.last_summary.get("server_upload_eligible")):
            messagebox.showwarning("업로드 차단", "테스트/비1년 캐시는 서버에 업로드할 수 없습니다. 1년 범위로 실행하세요.")
            return
        self.upload_btn.config(state="disabled")
        self.status.config(text="서버 업로드 중...")

        def worker() -> None:
            try:
                upload_to_server(
                    self.last_db,
                    self.last_result,
                    self.host.get().strip(),
                    self.user.get().strip(),
                    self.remote.get().strip(),
                    self.password.get(),
                    self.key.get(),
                    self._emit,
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
