from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

from universal_bot.discord_notifier import DiscordNotifier


KST = ZoneInfo("Asia/Seoul")


class AmbiguousTransferResult(RuntimeError):
    """The transfer request may have reached Bitget without a final response."""


class BitgetRebateClient:
    """Small signed client limited to balance and Elite transfer operations."""

    BASE_URL = "https://api.bitget.com"

    def __init__(
        self,
        api_key: str,
        secret: str,
        passphrase: str,
        *,
        timeout: float = 8.0,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.secret = str(secret or "").strip()
        self.passphrase = str(passphrase or "").strip()
        self.timeout = float(timeout)
        self._session = requests.Session()
        self._session.headers.update({"Connection": "keep-alive"})

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.secret and self.passphrase)

    def _headers(self, method: str, path: str, query: str, body_text: str) -> dict[str, str]:
        if not self.configured:
            raise RuntimeError("Bitget rebate API credentials are not configured")
        timestamp = str(int(time.time() * 1000))
        suffix = f"?{query}" if query else ""
        prehash = f"{timestamp}{method.upper()}{path}{suffix}{body_text}"
        digest = hmac.new(
            self.secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": base64.b64encode(digest).decode("ascii"),
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        transfer_post: bool = False,
    ) -> Any:
        method = method.upper()
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        query = urlencode([(str(k), str(v)) for k, v in clean_params.items()])
        body_text = "" if not body else json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        url = self.BASE_URL + path + (f"?{query}" if query else "")
        try:
            response = self._session.request(
                method,
                url,
                headers=self._headers(method, path, query, body_text),
                data=body_text or None,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            if transfer_post:
                raise AmbiguousTransferResult(
                    f"Bitget transfer response was ambiguous: {type(exc).__name__}"
                ) from exc
            raise RuntimeError(f"Bitget rebate API request failed: {type(exc).__name__}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            if transfer_post:
                raise AmbiguousTransferResult(
                    f"Bitget transfer returned non-JSON HTTP {response.status_code}"
                ) from exc
            raise RuntimeError(
                f"Bitget rebate API returned non-JSON HTTP {response.status_code}"
            ) from exc
        if str(payload.get("code")) != "00000":
            raise RuntimeError(
                f"Bitget rebate API error HTTP {response.status_code} "
                f"{payload.get('code')}: {payload.get('msg')}"
            )
        return payload.get("data")

    def spot_available_usdt(self) -> Decimal:
        data = self.request(
            "GET",
            "/api/v2/spot/account/assets",
            params={"coin": "USDT"},
        )
        rows: list[Any]
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            candidate = data.get("list") or data.get("assets") or data.get("data") or []
            rows = candidate if isinstance(candidate, list) else [data]
        else:
            rows = []
        for row in rows:
            if not isinstance(row, dict) or str(row.get("coin", "")).upper() != "USDT":
                continue
            value = row.get("available", row.get("availableBalance", "0"))
            return _decimal(value)
        return Decimal("0")

    def elite_transfer_in(self, amount: Decimal) -> dict[str, Any]:
        normalized = _money(amount)
        data = self.request(
            "POST",
            "/api/v3/copy/futures/transfer",
            body={
                "type": "in",
                "inAccountType": "funding",
                "coin": "USDT",
                "amount": normalized,
            },
            transfer_post=True,
        )
        return data if isinstance(data, dict) else {}

    def elite_transfer_records(self, *, limit: int = 20) -> list[dict[str, Any]]:
        data = self.request(
            "GET",
            "/api/v3/copy/futures/transfer-record",
            params={"limit": max(1, min(100, int(limit)))},
        )
        if isinstance(data, dict):
            rows = data.get("list", [])
        else:
            rows = data
        return [row for row in (rows or []) if isinstance(row, dict)]

    def find_recent_transfer(
        self,
        amount: Decimal,
        *,
        since_ms: int,
        attempts: int = 3,
    ) -> dict[str, Any] | None:
        target = _decimal(_money(amount))
        for attempt in range(max(1, int(attempts))):
            try:
                rows = self.elite_transfer_records(limit=20)
            except Exception:
                rows = []
            for row in rows:
                created = int(row.get("createdTime") or 0)
                status = str(row.get("status", "")).lower()
                to_type = str(row.get("toType", "")).lower()
                if (
                    created >= since_ms - 5_000
                    and str(row.get("coin", "")).upper() == "USDT"
                    and _decimal(row.get("amount")) == target
                    and "lead" in to_type
                    and status in {"successful", "success"}
                ):
                    return row
            if attempt + 1 < attempts:
                time.sleep(1.0)
        return None


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return result if result.is_finite() else Decimal("0")


def _money(value: Decimal) -> str:
    rounded = max(Decimal("0"), value).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    return format(rounded, "f")


def _clock_minutes(value: str) -> int:
    try:
        hour_text, minute_text = str(value).strip().split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid KST clock value: {value!r}") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid KST clock value: {value!r}")
    return hour * 60 + minute


class EliteRebateTransferService:
    """Move only the USDT increase observed during the configured rebate window."""

    def __init__(
        self,
        spot_client: BitgetRebateClient,
        elite_client: BitgetRebateClient,
        *,
        state_path: str | Path,
        window_start_kst: str = "15:55",
        window_end_kst: str = "16:20",
        minimum_usdt: float = 0.01,
        maximum_daily_usdt: float = 100.0,
        dry_run: bool = True,
        notifier: DiscordNotifier | None = None,
    ) -> None:
        self.spot_client = spot_client
        self.elite_client = elite_client
        self.state_path = Path(state_path).expanduser()
        self.window_start = _clock_minutes(window_start_kst)
        self.window_end = _clock_minutes(window_end_kst)
        if self.window_end <= self.window_start:
            raise ValueError("rebate transfer window must end after it starts")
        self.minimum = _decimal(minimum_usdt)
        self.maximum_daily = _decimal(maximum_daily_usdt)
        self.dry_run = bool(dry_run)
        self.notifier = notifier
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_name(self.state_path.name + ".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.state_path)

    def _notify(self, text: str) -> None:
        if self.notifier is not None:
            self.notifier.send_async(text)

    def tick(self, now: datetime | None = None) -> dict[str, Any]:
        with self._lock:
            current_time = (now or datetime.now(timezone.utc)).astimezone(KST)
            today = current_time.date().isoformat()
            minute = current_time.hour * 60 + current_time.minute
            state = self._load()

            if state.get("date") != today:
                state = {
                    "date": today,
                    "window_opened": False,
                    "transferred": "0",
                    "blocked": False,
                }

            if minute > self.window_end:
                return {"status": "outside-window", "date": today}

            available = self.spot_client.spot_available_usdt()
            state["last_spot_available"] = _money(available)
            state["updated_at"] = current_time.isoformat()

            if minute < self.window_start:
                state["baseline"] = _money(available)
                state["window_opened"] = False
                state["status"] = "baseline-ready"
                self._save(state)
                return {
                    "status": "baseline-ready",
                    "date": today,
                    "spot_available": _money(available),
                }

            if not state.get("window_opened"):
                state["baseline"] = _money(available)
                state["window_opened"] = True
                state["status"] = "window-opened"
                self._save(state)
                return {
                    "status": "window-opened",
                    "date": today,
                    "spot_available": _money(available),
                }

            if state.get("blocked"):
                self._save(state)
                return {"status": "blocked", "date": today, "reason": state.get("reason")}

            baseline = _decimal(state.get("baseline"))
            pending = max(Decimal("0"), available - baseline)
            transferred = _decimal(state.get("transferred"))
            if pending < self.minimum:
                state["status"] = "waiting"
                self._save(state)
                return {
                    "status": "waiting",
                    "date": today,
                    "pending": _money(pending),
                }

            if pending + transferred > self.maximum_daily:
                state.update(
                    {
                        "blocked": True,
                        "status": "daily-limit-blocked",
                        "reason": "daily-limit",
                        "pending": _money(pending),
                    }
                )
                self._save(state)
                self._notify(
                    f"⚠️ Bitget 페이백 자동이체 차단 · 감지 { _money(pending) } USDT · 일일 한도 초과"
                )
                return {"status": "daily-limit-blocked", "amount": _money(pending)}

            if self.dry_run:
                already_seen = _decimal(state.get("dry_run_seen"))
                state.update(
                    {
                        "status": "dry-run-detected",
                        "dry_run_seen": _money(max(already_seen, pending)),
                        "pending": _money(pending),
                    }
                )
                self._save(state)
                if pending > already_seen:
                    self._notify(f"🧪 Bitget 페이백 감지 · { _money(pending) } USDT · DRY RUN")
                return {"status": "dry-run-detected", "amount": _money(pending)}

            started_ms = int(time.time() * 1000)
            try:
                result = self.elite_client.elite_transfer_in(pending)
                transfer_id = str(result.get("transferId") or "")
            except AmbiguousTransferResult as exc:
                record = self.elite_client.find_recent_transfer(pending, since_ms=started_ms)
                if record is None:
                    state.update(
                        {
                            "blocked": True,
                            "status": "ambiguous-blocked",
                            "reason": str(exc),
                            "pending": _money(pending),
                        }
                    )
                    self._save(state)
                    self._notify(
                        f"🚨 Bitget 페이백 이체 응답 불명확 · { _money(pending) } USDT · 중복 방지를 위해 당일 차단"
                    )
                    return {"status": "ambiguous-blocked", "amount": _money(pending)}
                transfer_id = str(record.get("transferId") or "")
            except Exception as exc:
                state.update(
                    {
                        "status": "failed",
                        "reason": f"{type(exc).__name__}: {exc}",
                        "pending": _money(pending),
                    }
                )
                self._save(state)
                self._notify(
                    f"❌ Bitget 페이백 자동이체 실패 · { _money(pending) } USDT · 다음 주기에 재확인"
                )
                return {"status": "failed", "amount": _money(pending)}

            total = transferred + pending
            state.update(
                {
                    "status": "transferred",
                    "transferred": _money(total),
                    "last_amount": _money(pending),
                    "last_transfer_id": transfer_id,
                    "reason": None,
                }
            )
            self._save(state)
            self._notify(
                f"✅ Bitget 페이백 자동이체 완료 · { _money(pending) } USDT · Elite 계정"
            )
            return {
                "status": "transferred",
                "amount": _money(pending),
                "transfer_id": transfer_id,
            }


def _seconds_until_next_tick(now: datetime, start_minute: int, end_minute: int, poll: int) -> float:
    local = now.astimezone(KST)
    minute = local.hour * 60 + local.minute
    if start_minute <= minute <= end_minute:
        return float(max(5, poll))
    if minute < start_minute:
        target = local.replace(
            hour=start_minute // 60,
            minute=start_minute % 60,
            second=0,
            microsecond=0,
        )
    else:
        tomorrow = local + timedelta(days=1)
        target = tomorrow.replace(
            hour=start_minute // 60,
            minute=start_minute % 60,
            second=0,
            microsecond=0,
        )
    return max(5.0, min(300.0, (target - local).total_seconds()))


def run_rebate_transfer_worker(settings: Any) -> None:
    """Run the isolated rebate worker; failures never stop the trading loop."""

    notifier = DiscordNotifier(
        settings.discord_webhook_url,
        enabled=settings.discord_notifications_enabled,
        timeout=settings.discord_timeout,
    )
    standard = BitgetRebateClient(
        *settings.bitget_standard_credentials,
        timeout=settings.bitget_elite_request_timeout,
    )
    elite = BitgetRebateClient(
        *settings.bitget_elite_credentials,
        timeout=settings.bitget_elite_request_timeout,
    )
    if not standard.configured or not elite.configured:
        print(
            "ELITE_REBATE_TRANSFER_DISABLED missing standard spot or Elite credentials",
            flush=True,
        )
        notifier.send_async("⚠️ Bitget 페이백 자동이체 비활성 · API 자격 증명 확인 필요")
        return

    try:
        service = EliteRebateTransferService(
            standard,
            elite,
            state_path=settings.elite_rebate_transfer_state_path,
            window_start_kst=settings.elite_rebate_window_start_kst,
            window_end_kst=settings.elite_rebate_window_end_kst,
            minimum_usdt=settings.elite_rebate_minimum_usdt,
            maximum_daily_usdt=settings.elite_rebate_maximum_daily_usdt,
            dry_run=settings.elite_rebate_auto_transfer_dry_run,
            notifier=notifier,
        )
    except Exception as exc:
        print(f"ELITE_REBATE_TRANSFER_DISABLED invalid settings: {exc}", flush=True)
        notifier.send_async("⚠️ Bitget 페이백 자동이체 비활성 · 설정 오류")
        return

    while True:
        try:
            result = service.tick()
            status = result.get("status")
            if status not in {"waiting", "outside-window"}:
                print(f"ELITE_REBATE_TRANSFER status={status}", flush=True)
        except Exception as exc:
            print(
                f"ELITE_REBATE_TRANSFER_ERROR error={type(exc).__name__}: {exc}",
                flush=True,
            )
        delay = _seconds_until_next_tick(
            datetime.now(timezone.utc),
            service.window_start,
            service.window_end,
            settings.elite_rebate_poll_seconds,
        )
        time.sleep(delay)
