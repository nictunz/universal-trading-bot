from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import pytest

from universal_bot.main import _relay_snapshot_revision, _wait_for_relay_change
from universal_bot.providers.mobile_relay import MobileRelayMarketData

ROOT = Path(__file__).resolve().parents[1]


def _payload(generated_at_ms: int) -> dict:
    base = 1_700_000_000_000
    rows = [[base + i * 300_000, float(i + 1)] for i in range(4)]
    return {
        "schema_version": 1,
        "generated_at_ms": generated_at_ms,
        "timeframe": "5m",
        "markets": {
            "BTC/USDT:USDT": {
                "binance": rows,
                "bybit": rows,
            }
        },
    }


def test_mobile_relay_parses_volume_and_common_timestamp(tmp_path):
    path = tmp_path / "relay.json"
    path.write_text(json.dumps(_payload(int(time.time() * 1000))), encoding="utf-8")
    relay = MobileRelayMarketData(path, max_age_seconds=90)

    series = relay.fetch_volume("binance", "BTC/USDT:USDT", "5m", limit=3)
    assert list(series.astype(float)) == [2.0, 3.0, 4.0]
    assert isinstance(series.index, pd.DatetimeIndex)
    assert str(series.index.tz) == "UTC"
    assert relay.latest_common_timestamp("BTC/USDT:USDT", "5m") == series.index[-1]


def test_mobile_relay_fails_closed_when_stale(tmp_path):
    path = tmp_path / "relay.json"
    path.write_text(json.dumps(_payload(int((time.time() - 180) * 1000))), encoding="utf-8")
    relay = MobileRelayMarketData(path, max_age_seconds=90)

    with pytest.raises(RuntimeError, match="stale"):
        relay.fetch_volume("bybit", "BTC/USDT:USDT", "5m")


def test_mobile_relay_uses_per_source_observation_at_boundary(tmp_path):
    path = tmp_path / "relay.json"
    now_ms = int(time.time() * 1000)
    delta_ms = 300_000
    boundary_ms = now_ms // delta_ms * delta_ms
    rows = [
        [boundary_ms - 2 * delta_ms, 10.0],
        [boundary_ms - delta_ms, 20.0],
        [boundary_ms, 30.0],
    ]
    payload = {
        "schema_version": 1,
        "generated_at_ms": boundary_ms - 1,
        "snapshot_completed_at_ms": now_ms,
        "source_observed_at_ms": {
            "BTC/USDT:USDT": {
                "binance": boundary_ms - 1,
                "bybit": now_ms,
            }
        },
        "timeframe": "5m",
        "markets": {
            "BTC/USDT:USDT": {
                "binance": rows,
                "bybit": rows,
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    relay = MobileRelayMarketData(path, max_age_seconds=600)

    binance = relay.fetch_volume("binance", "BTC/USDT:USDT", "5m", limit=10)
    bybit = relay.fetch_volume("bybit", "BTC/USDT:USDT", "5m", limit=10)

    assert binance.index[-1] == pd.to_datetime(boundary_ms - 2 * delta_ms, unit="ms", utc=True)
    assert bybit.index[-1] == pd.to_datetime(boundary_ms - delta_ms, unit="ms", utc=True)


def test_relay_change_wakes_server_without_waiting_for_poll_timeout(tmp_path):
    path = tmp_path / "mobile-market-relay.json"
    path.write_text("old", encoding="utf-8")
    previous = _relay_snapshot_revision(path)
    path.write_text("new-longer", encoding="utf-8")

    assert _wait_for_relay_change(previous, 10, path=path)


def test_relay_wait_keeps_poll_timeout_as_fallback(tmp_path):
    path = tmp_path / "mobile-market-relay.json"
    path.write_text("same", encoding="utf-8")
    previous = _relay_snapshot_revision(path)

    assert not _wait_for_relay_change(previous, 0, path=path)


def test_android_relay_is_wall_clock_aligned_and_boundary_safe():
    service = (
        ROOT
        / "android/app/src/main/java/com/nictunz/universalbacktester/MobileMarketRelayService.java"
    ).read_text(encoding="utf-8")

    assert "scheduleWithFixedDelay" not in service
    assert "millisUntilNextRelaySlot" in service
    assert "RELAY_PHASE_MILLIS = 1_000L" in service
    assert "NORMAL_INTERVAL_MILLIS = 30_000L" in service
    assert "PRE_BOUNDARY_INTERVAL_MILLIS = 5_000L" in service
    assert "POST_BOUNDARY_INTERVAL_MILLIS = 1_000L" in service
    assert "confirmedBoundaryOpenMs" not in service
    assert "if (elapsed < BOUNDARY_WINDOW_MILLIS)" in service
    assert "millisUntilNextRelaySlot(System.currentTimeMillis())" in service
    assert "적응형 경계동기" in service
    assert "newFixedThreadPool(4)" in service
    assert "ROLLOVER_RETRY_DELAYS_MS" in service
    assert "elapsed >= BOUNDARY_WINDOW_MILLIS" in service
    assert 'payload.put("source_observed_at_ms", sourceObservedAt)' in service
    assert 'payload.put("snapshot_completed_at_ms", Math.max(cycleStartedAt, System.currentTimeMillis()))' in service
