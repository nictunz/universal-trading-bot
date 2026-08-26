# ETH and BTC one-year strategy optimization

## ETH

# ETH/USDT:USDT one-year strategy optimization

- Generated UTC: 2026-08-25T22:10:51.638983+00:00
- Market: ETH/USDT:USDT 5m
- Trials fully merged: 300

## Execution assumptions

- Initial capital: 1000.0 USDT
- Entry notional: 5.0x to 15.0x equity
- Exchange leverage: 50x
- Maximum entries: 1 to 3
- Fee: 0.02% per side
- Slippage: 0.01% per side

## Best result

- Trial: 173
- Entry multiplier: 14.0x
- Maximum entries: 1
- Net PnL: 5036.9640010910225 USDT
- Return: 503.6964001091023%
- Profit factor: 1.6679196729078418
- Win rate: 70.17543859649122%
- Max drawdown: 41.012717131489396%
- Trades: 57

## Parameters

~~~json
{
  "allow_long": true,
  "allow_short": true,
  "initial_capital": 1000.0,
  "leverage": 50,
  "backtest_fee_percent": 0.02,
  "backtest_slippage_percent": 0.01,
  "entry_multiplier": 14.0,
  "order_percent_of_equity": 1400.0,
  "max_pyramiding": 1,
  "volume_lookback": 91,
  "volume_break_multiplier": 12.89,
  "min_one_bar_vol": 0.31,
  "max_one_bar_vol": 0.84,
  "volatility_bars": 432,
  "tp_vol_multiplier": 0.77,
  "sl_vol_multiplier": 0.86,
  "min_tp_percent": 0.21,
  "max_tp_percent": 2.01,
  "min_sl_percent": 0.8,
  "max_sl_percent": 3.52,
  "use_nbar_volatility_block": true,
  "nbar_volatility_bars": 12,
  "max_nbar_volatility": 2.76,
  "use_adx_filter": false,
  "adx_length": 13,
  "adx_min": 15.5,
  "adx_max": 74.8,
  "use_rsi_filter": true,
  "rsi_length": 8,
  "rsi_oversold_min": 0.3,
  "rsi_oversold_max": 29.5,
  "rsi_overbought_min": 75.9,
  "rsi_overbought_max": 91.8,
  "cooldown_bars": 17,
  "reentry_bars": 8,
  "block_weekend": false,
  "excluded_hours": "00"
}
~~~

> Research only. Not automatically applied to PAPER or LIVE.

## BTC

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
