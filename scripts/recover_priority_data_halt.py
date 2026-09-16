#!/usr/bin/env python3
"""Clear only a known, recoverable Priority LIVE market-data HALT.

Fail closed. This helper never contacts the exchange and never places/cancels
orders. Exchange FLAT/stale-plan checks must be completed separately first.
It additionally requires exclusive ownership of the Priority journal lock, so
it cannot mutate state while the LIVE controller is running.
"""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import shutil
import sqlite3
import time

from universal_bot.priority_signals import profile_hash
from universal_bot.providers.mobile_relay import MobileRelayMarketData

DEFAULT_STATE = Path.home() / ".local/state/universal-trading-bot/priority-live.sqlite"
DEFAULT_RELAY = MobileRelayMarketData.DEFAULT_PATH
RECOVERABLE_HALTS = {
    "RuntimeError: mobile relay 5m sidecar missing; Android dual-timeframe update required",
    "mobile relay 5m sidecar missing; Android dual-timeframe update required",
}


def _fresh(path: Path, expected_tf: str, max_age: int) -> None:
    if not path.is_file():
        raise RuntimeError(f"relay missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("schema_version") or 0) != 1:
        raise RuntimeError(f"unsupported relay schema: {path.name}")
    if str(payload.get("timeframe") or "") != expected_tf:
        raise RuntimeError(f"relay timeframe mismatch: {path.name}")
    completed_ms = int(payload.get("snapshot_completed_at_ms") or payload.get("generated_at_ms") or 0)
    if completed_ms <= 0:
        raise RuntimeError(f"relay completion time missing: {path.name}")
    age = time.time() - completed_ms / 1000.0
    if age < -5 or age > max_age:
        raise RuntimeError(f"relay not fresh: {path.name} age={age:.1f}s")


def _lock_exclusive(state_path: Path):
    lock_path = Path(str(state_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RuntimeError("priority journal is in use; stop LIVE service before recovery")
    return handle


def recover(state_path: Path, relay_path: Path, max_age: int, apply: bool) -> dict:
    state_path = Path(state_path)
    relay_path = Path(relay_path)
    lock = _lock_exclusive(state_path)
    try:
        sidecar = relay_path.with_name("mobile-market-relay-5m.json")
        _fresh(relay_path, "15m", max_age)
        _fresh(sidecar, "5m", max_age)
        if not state_path.is_file():
            raise RuntimeError("priority state missing")

        db = sqlite3.connect(state_path)
        try:
            row = db.execute("SELECT body FROM priority_state WHERE id=1").fetchone()
            if not row:
                raise RuntimeError("priority state missing")
            state = json.loads(row[0])
            if state.get("profile") != profile_hash():
                raise RuntimeError("profile changed; recovery refused")
            if state.get("owner") is not None or state.get("position") is not None:
                raise RuntimeError("persisted position/owner exists; recovery refused")
            if state.get("pending") is not None:
                raise RuntimeError("unfinished operation exists; recovery refused")
            if state.get("halted") not in RECOVERABLE_HALTS:
                raise RuntimeError(f"HALT is not allow-listed: {state.get('halted')!r}")
            before = dict(state)
            if not apply:
                return {"ok": True, "changed": False, "before": before, "after": state}

            stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
            backup = state_path.with_name(f"priority-live-before-auto-recovery-{stamp}.sqlite")
            backup_db = sqlite3.connect(backup)
            try:
                db.backup(backup_db)
            finally:
                backup_db.close()

            state["halted"] = None
            with db:
                db.execute("UPDATE priority_state SET body=? WHERE id=1", (json.dumps(state, allow_nan=False),))
            check = json.loads(db.execute("SELECT body FROM priority_state WHERE id=1").fetchone()[0])
            if check.get("halted") is not None or check.get("owner") is not None or check.get("position") is not None or check.get("pending") is not None:
                raise RuntimeError("post-recovery state verification failed")
            return {"ok": True, "changed": True, "backup": str(backup), "before": before, "after": check}
        finally:
            db.close()
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    ap.add_argument("--relay", type=Path, default=DEFAULT_RELAY)
    ap.add_argument("--max-age", type=int, default=90)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    result = recover(args.state.expanduser(), args.relay.expanduser(), args.max_age, args.apply)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
