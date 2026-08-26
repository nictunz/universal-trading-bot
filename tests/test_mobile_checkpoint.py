from __future__ import annotations

import json
from datetime import datetime, timezone

from universal_bot.local_cache_core import (
    _checkpoint_path,
    _chunk_key,
    _load_checkpoint,
    _save_checkpoint,
)


def test_checkpoint_round_trip_is_atomic(tmp_path):
    path = _checkpoint_path(
        tmp_path, "ETH/USDT:USDT", "5m", "2026-01-01", "2026-03-31"
    )
    key = _chunk_key(
        "okx",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 31, 23, 59, tzinfo=timezone.utc),
    )
    _save_checkpoint(
        path,
        {
            "version": 1,
            "stage": "CACHE_SYNC",
            "completed_chunks": [key],
        },
    )

    loaded = _load_checkpoint(path)
    assert loaded["stage"] == "CACHE_SYNC"
    assert loaded["completed_chunks"] == [key]
    assert loaded["updated_at"]
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_damaged_checkpoint_is_preserved_and_reset(tmp_path):
    path = _checkpoint_path(
        tmp_path, "BTC/USDT:USDT", "5m", "2026-01-01", "2026-03-31"
    )
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")

    loaded = _load_checkpoint(path)

    assert loaded == {"version": 1, "stage": "NEW", "completed_chunks": []}
    assert not path.exists()
    damaged = list(path.parent.glob(path.name + ".damaged-*"))
    assert len(damaged) == 1
    assert damaged[0].read_text(encoding="utf-8") == "{broken"


def test_checkpoint_identity_changes_with_range(tmp_path):
    first = _checkpoint_path(
        tmp_path, "ETH/USDT:USDT", "5m", "2026-01-01", "2026-03-31"
    )
    second = _checkpoint_path(
        tmp_path, "ETH/USDT:USDT", "5m", "2026-02-01", "2026-04-30"
    )
    assert first != second
