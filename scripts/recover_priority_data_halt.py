#!/usr/bin/env python3
"""Clear only a known, recoverable Priority LIVE market-data HALT.

Fail closed. This script never places/cancels orders and never clears execution,
protection, ownership, profile, or unfinished-operation faults.

Run only while the Priority LIVE service is stopped. It requires:
- persisted owner/position/pending are empty;
- persisted HALT is an allow-listed mobile-relay data fault;
- both 15m and 5m relay snapshots are fresh and structurally readable;
- the current profile hash is unchanged.

Exchange FLAT must still be verified separately by the deployment/recovery
procedure before this script is invoked. This separation keeps this helper
read-only with respect to the exchange.
"""
from __future__ import annotations

import argparse
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


def recover(state_path: Path, relay_path: Path, max_age: int, apply: bool) -> dict:
    sidecar = relay_path.with_name("mobile-market-relay-5m.json")
    _fresh(relay_path, "15m", max_age)
    _fresh(sidecar, "5m", max_age)

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
        if apply:
            stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
            backup = state_path.with_name(f"priority-live-before-auto-recovery-{stamp}.sqlite")
            db.commit()
            shutil.copy2(state_path, backup)
            state["halted"] = None
            with db:
                db.execute("UPDATE priority_state SET body=? WHERE id=1", (json.dumps(state, allow_nan=False),))
            return {"ok": True, "changed": True, "backup": str(backup), "before": before, "after": state}
        return {"ok": True, "changed": False, "before": before, "after": state}
    finally:
        db.close()


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
