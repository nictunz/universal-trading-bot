# Operating modes

## BACKTEST
Historical OHLCV is replayed bar by bar through the same v15 strategy and engine used by paper/live.
No exchange order is sent.

## PAPER
Live market data may be used, but orders are simulated. This is the required validation stage before LIVE.

## LIVE
Real orders are allowed only when `BOT_MODE=LIVE` and the explicit live confirmation guard is enabled. Exchange API keys must come from `.env` and must never be committed.

## Universal symbols
The strategy is asset-class neutral. Select crypto symbols through a CCXT exchange adapter and stocks/ETFs through a market-data/broker adapter. Each symbol receives an independent engine/position state.

## v15 dashboard
The dashboard receives the same decision state used for execution: normalized volume ratio, one-bar volatility, N-bar range, dynamic TP/SL, N-bar block, ADX range, RSI direction, cooldown/entry readiness, position, and performance statistics.
