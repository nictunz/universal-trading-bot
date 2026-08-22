# Universal Trading Bot

Universal multi-asset trading bot based on **Volume Strategy FINAL Universal v15**.

TradingView is **not required** for live execution. The bot calculates indicators/signals itself, manages positions/orders, stores market/trade state, and exposes strategy state for a dashboard.

## Supported asset architecture

- Crypto: Binance / Bitget / OKX / Bybit adapters
- Stocks / ETFs: broker/data-provider adapter interface
- Arbitrary supported symbols and timeframes
- One strategy engine shared by all assets

## v15 strategy implemented

- Volume average lookback + volume breakout multiplier
- Four-exchange normalized crypto volume
- One-bar volatility min/max filter
- N-bar volatility based dynamic TP/SL
- N-bar extreme-volatility entry block
- ADX min/max range filter
- RSI oversold LONG / overbought SHORT ranges
- Candle direction confirmation
- LONG / SHORT enable switches
- Pyramiding limit
- Entry cooldown
- Re-entry cooldown after flat
- Start date / weekend / excluded-hour filters
- Fixed TP/SL per initial position
- Duplicate entry protection per bar
- Strategy statistics and dashboard state

## Important v15 semantic detail

The supplied Pine strategy is the source of truth. LONG is triggered by a bearish candle plus RSI oversold; SHORT is triggered by a bullish candle plus RSI overbought. TP/SL are calculated when the initial position is opened and remain fixed for that position.

## Configuration

Copy `.env.example` to `.env`. Never commit `.env`.

Default mode is paper trading.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
python -m universal_bot
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
python -m universal_bot
```

## Planned modules

`universal_bot/strategy/v15.py` is exchange/provider independent. Adapters translate market data and orders into a common model, so the strategy never knows whether the instrument is BTC, an altcoin, a stock, or an ETF.

Live trading is deliberately disabled by default. Before enabling it, validate symbol mapping, contract/lot size, leverage, fees, reduce-only behavior, and order reconciliation for the selected venue.
