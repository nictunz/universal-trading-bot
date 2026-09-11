# Close-bar reentry and offline candles

The backtest continues to use its existing event order and settings: the signal
on an exit candle uses the previous exit's cooldown; subsequent candles use the
new exit's seven-bar cooldown. This is an explicit exception, not a seven-bar
delay on every exit. Pine v19 already represents that order.

LIVE now allows the same exception only after exchange FLAT confirmation and an
exact protection fill with a timestamp in the completed signal candle. Protection
tags in the exchange fill distinguish it from a manual/emergency close inferred
only by its price. Unknown or untagged fills retain the normal cooldown. Entry
cooldown, position limits, freshness, safety halt and persistent signal claims
remain enforced. A heartbeat can observe the exit before candle processing;
the exchange fill timestamp, rather than poll timing, identifies the candle.
No heartbeat retries a consumed candle's signal. Real fill prices, partial fills,
missing market data, restarts and exchange constraints still prevent a promise
of identical backtest and live returns.

Android: open “코인 DB 차트” in the local backtester. It discovers downloaded
crypto SQLite files under UniversalTradingBotCache, plus the selected result DB.
Choose the file, coin, exchange and timeframe. Drag to move, pinch to zoom,
tap/hold for OHLCV, use Date/Recent to navigate and Trades to jump to an entry.
Results must match DB path, coin, exchange and timeframe before markers appear.
This is an offline native chart, not embedded TradingView or a server dashboard.
Only 30–600 visible candles are fetched at once on a worker; old queued requests
are discarded. Candles remain available without a backtest result.

New backtest trades include the original `tp_price` and `sl_price`. Old saved
trades retain their entry/exit markers but need a rerun for both protection lines;
the chart never guesses those lines from the exit price. Summary, equity and
trade details are consolidated under the existing report; strategy editing,
optimization, export and server management are preserved.

Validation: seven new LIVE close-bar tests plus existing LIVE/runtime tests pass
(16 total), plus a timestamp-resolution regression (17 total). Pandas 3's
millisecond indexes are normalized to nanoseconds before start-date comparison.
The new native chart/activity and existing report compile against Android API
stubs with Java 17 (full APK and device rendering are separate checks).
Same 2021-08-26–2026-08-25 BTC DB, 41/6.4 volume, N200/6.1,
RSI10/20–41.5, 890% compound orders and 0.02%+0.01% costs reproduce 182 trades,
549681.611724% return, 42.766215% app MDD. Protection prices are present for all
182 trades. These are historical simulation outputs, not a forecast.

Server rollout is separate from an APK install. Preserve the existing server's
local edits and settings before integrating engine.py/runtime_engine.py; use an
exchange-flat deployment window. This change does not restart the live server.
