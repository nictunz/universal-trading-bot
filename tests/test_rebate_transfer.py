from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from universal_bot.rebate_transfer import (
    AmbiguousTransferResult,
    BitgetRebateClient,
    EliteRebateTransferService,
)


KST = ZoneInfo("Asia/Seoul")


class FakeSpot:
    def __init__(self, available: str) -> None:
        self.available = Decimal(available)

    def spot_available_usdt(self) -> Decimal:
        return self.available


class FakeElite:
    def __init__(self) -> None:
        self.transfers: list[Decimal] = []
        self.ambiguous = False
        self.record = None

    def elite_transfer_in(self, amount: Decimal):
        self.transfers.append(amount)
        if self.ambiguous:
            raise AmbiguousTransferResult("timeout")
        return {"transferId": f"transfer-{len(self.transfers)}"}

    def find_recent_transfer(self, amount: Decimal, *, since_ms: int):
        return self.record


def _service(tmp_path, spot, elite, **kwargs):
    return EliteRebateTransferService(
        spot,
        elite,
        state_path=tmp_path / "state.json",
        window_start_kst="15:55",
        window_end_kst="16:20",
        minimum_usdt=0.01,
        maximum_daily_usdt=100,
        dry_run=False,
        **kwargs,
    )


def test_only_window_increase_is_transferred_once(tmp_path):
    spot = FakeSpot("50")
    elite = FakeElite()
    service = _service(tmp_path, spot, elite)

    assert service.tick(datetime(2026, 9, 8, 15, 55, tzinfo=KST))["status"] == "window-opened"
    spot.available = Decimal("52.3456789")
    result = service.tick(datetime(2026, 9, 8, 16, 5, tzinfo=KST))
    assert result == {
        "status": "transferred",
        "amount": "2.345678",
        "transfer_id": "transfer-1",
    }
    assert elite.transfers == [Decimal("2.3456789")]

    # Bitget removes the transferred delta from Spot; a later tick sees no new rebate.
    spot.available = Decimal("50")
    assert service.tick(datetime(2026, 9, 8, 16, 6, tzinfo=KST))["status"] == "waiting"
    assert len(elite.transfers) == 1


def test_first_start_inside_window_baselines_without_sweeping_existing_spot(tmp_path):
    spot = FakeSpot("500")
    elite = FakeElite()
    service = _service(tmp_path, spot, elite)

    result = service.tick(datetime(2026, 9, 8, 16, 5, tzinfo=KST))
    assert result["status"] == "window-opened"
    assert elite.transfers == []


def test_daily_limit_blocks_unrelated_large_deposit(tmp_path):
    spot = FakeSpot("10")
    elite = FakeElite()
    service = _service(tmp_path, spot, elite)
    service.tick(datetime(2026, 9, 8, 15, 55, tzinfo=KST))
    spot.available = Decimal("200")

    assert service.tick(datetime(2026, 9, 8, 16, 5, tzinfo=KST))["status"] == "daily-limit-blocked"
    assert elite.transfers == []


def test_dry_run_detects_without_transfer(tmp_path):
    spot = FakeSpot("10")
    elite = FakeElite()
    service = EliteRebateTransferService(
        spot,
        elite,
        state_path=tmp_path / "state.json",
        dry_run=True,
    )
    service.tick(datetime(2026, 9, 8, 15, 55, tzinfo=KST))
    spot.available = Decimal("11")

    assert service.tick(datetime(2026, 9, 8, 16, 5, tzinfo=KST))["status"] == "dry-run-detected"
    assert elite.transfers == []


def test_ambiguous_transfer_is_resolved_from_history(tmp_path):
    spot = FakeSpot("10")
    elite = FakeElite()
    elite.ambiguous = True
    elite.record = {"transferId": "resolved-1"}
    service = _service(tmp_path, spot, elite)
    service.tick(datetime(2026, 9, 8, 15, 55, tzinfo=KST))
    spot.available = Decimal("11")

    result = service.tick(datetime(2026, 9, 8, 16, 5, tzinfo=KST))
    assert result["status"] == "transferred"
    assert result["transfer_id"] == "resolved-1"


def test_unresolved_ambiguous_transfer_blocks_day(tmp_path):
    spot = FakeSpot("10")
    elite = FakeElite()
    elite.ambiguous = True
    service = _service(tmp_path, spot, elite)
    service.tick(datetime(2026, 9, 8, 15, 55, tzinfo=KST))
    spot.available = Decimal("11")

    assert service.tick(datetime(2026, 9, 8, 16, 5, tzinfo=KST))["status"] == "ambiguous-blocked"
    assert service.tick(datetime(2026, 9, 8, 16, 6, tzinfo=KST))["status"] == "blocked"
    assert len(elite.transfers) == 1


def test_spot_balance_parser_accepts_classic_list(monkeypatch):
    client = BitgetRebateClient("key", "secret", "pass")
    monkeypatch.setattr(
        client,
        "request",
        lambda *args, **kwargs: [{"coin": "USDT", "available": "12.34"}],
    )
    assert client.spot_available_usdt() == Decimal("12.34")


def test_invalid_window_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        EliteRebateTransferService(
            FakeSpot("1"),
            FakeElite(),
            state_path=tmp_path / "state.json",
            window_start_kst="16:20",
            window_end_kst="15:55",
        )
