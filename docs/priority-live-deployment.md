# Priority LIVE deployment candidate

The candidate replaces the legacy scanner loop only when the systemd process
has `PRIORITY_LIVE_ENABLED=1`. The default remains the legacy scanner. Priority
mode requires LIVE, one BTC/USDT perpetual symbol and one initialized execution
engine. It uses 5m 9.55x first and 15m 5.0x when idle.

The live controller persists intent, owner, fixed TP/SL and signal watermark in
`~/.local/state/universal-trading-bot/priority-live.sqlite`. A file lock prevents
two priority controllers. An unknown exchange position, incomplete prior intent,
protection mismatch, partial close, cancellation failure, stale transition or
data defect halts new entries. It never retries an ambiguous order automatically.

`scripts/stage_priority_live.py` backs up and installs only the reviewed source
files. It does not touch `.env`, the locally repaired elite runtime adapter,
systemd or the exchange. Activation is a separate systemd environment override.

The candidate regression suite passed 151 tests locally. The LIVE transition
tests use a fake Bitget transport; no real order was sent. Production activation
still requires a current FLAT check, source staging, service restart and the
health/readiness/state verification endpoints.
