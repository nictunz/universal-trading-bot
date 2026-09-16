# Isolated PAPER integration

Run `bash scripts/run_priority_paper.sh` from a separate worktree. It observes
three completed 5m boundaries, including one 15m boundary, then exits.
It does not modify main.py, .env, systemd, the LIVE service or exchange orders.
The runtime has no LIVE option and receives no exchange adapter or credentials.
The monitor uses public prices and the existing mobile volume relay only.

The account starts with 1000 simulated USDT. Position, equity, history and
strategy ownership persist in a separate paper-only.sqlite journal. A 5m
signal takes priority; a 15m paper position is closed before opening 5m.
Fixed TP/SL uses completed 5m high/low with SL first if both are touched.
Reference-price fills and a 0.03% per-side combined cost are approximations,
not exchange fill, spread, liquidation, funding or latency validation.

If a held position spans an unprocessed candle, processing halts instead of
inventing the missing exit path. An interrupted transition also halts on restart.
Keep this limitation in mind when running only three boundaries per session.
This is not the production scanner or a dashboard integration.

Local restored-candidate regression suite: 149 tests passed, including six new
paper-runtime tests. This count is not the GitHub whole-repository CI count.
