# BTC/USDT:USDT one-year strategy optimization

- Generated UTC: 2026-08-26T04:30:56.772689+00:00
- Market: BTC/USDT:USDT 5m
- Trials fully merged: 300

## Execution assumptions

- Initial capital: 1000.0 USDT
- Entry notional: 5.0x to 15.0x equity
- Exchange leverage: 50x
- Maximum entries: 1 to 3
- Fee: 0.02% per side
- Slippage: 0.01% per side

## Best result

- Trial: 203
- Entry multiplier: 10.5x
- Maximum entries: 3
- Net PnL: 2812.0544839094546 USDT
- Return: 281.20544839094543%
- Profit factor: 2.0876794154268583
- Win rate: 63.63636363636363%
- Max drawdown: 55.16045065125987%
- Trades: 33

## Parameters

~~~json
{
  "allow_long": true,
  "allow_short": true,
  "initial_capital": 1000.0,
  "leverage": 50,
  "backtest_fee_percent": 0.02,
  "backtest_slippage_percent": 0.01,
  "entry_multiplier": 10.5,
  "order_percent_of_equity": 1050.0,
  "max_pyramiding": 3,
  "volume_lookback": 20,
  "volume_break_multiplier": 5.85,
  "min_one_bar_vol": 0.25,
  "max_one_bar_vol": 1.23,
  "volatility_bars": 200,
  "tp_vol_multiplier": 0.73,
  "sl_vol_multiplier": 0.73,
  "min_tp_percent": 0.34,
  "max_tp_percent": 2.95,
  "min_sl_percent": 1.04,
  "max_sl_percent": 2.17,
  "use_nbar_volatility_block": true,
  "nbar_volatility_bars": 144,
  "max_nbar_volatility": 5.66,
  "use_adx_filter": true,
  "adx_length": 12,
  "adx_min": 12.2,
  "adx_max": 62.2,
  "use_rsi_filter": true,
  "rsi_length": 16,
  "rsi_oversold_min": 19.8,
  "rsi_oversold_max": 30.1,
  "rsi_overbought_min": 67.7,
  "rsi_overbought_max": 78.8,
  "cooldown_bars": 28,
  "reentry_bars": 4,
  "block_weekend": false,
  "excluded_hours": "00,13,15,16,17,18,23"
}
~~~

> Research only. Not automatically applied to PAPER or LIVE.
