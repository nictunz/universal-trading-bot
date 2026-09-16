"""Offline OHLC replay using the production priority controller and signal evaluator.

No exchange clients or credentials are constructed. Not an IOC/tick fill simulator.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from universal_bot.backtest import run_backtest
from universal_bot.paper import normalize_exchange_volume
from universal_bot.priority_controller import PriorityController
from universal_bot.priority_signals import DualTimeframeSignals, COMMON, PROFILES, profile_hash, profile_settings


class MemoryJournal:
    def load(self):
        return dict(profile=profile_hash(), owner=None, position=None, history={},
                    pending=None, halted=None, watermark=None)

    def save(self, state):
        if state['halted']:
            raise RuntimeError(state['halted'])


class ReplaySignals:
    def __init__(self, candidates):
        self.candidates = candidates

    def evaluate(self, frames, volumes, boundary, now, history):
        eligible = []
        for candidate in self.candidates.get(boundary, []):
            settings = PROFILES[candidate.owner]
            events = history.get(candidate.owner, {})
            if all(key not in events or int((boundary - pd.Timestamp(events[key])) /
                   pd.Timedelta(candidate.owner)) >= settings[limit]
                   for key, limit in [('entry', 'cooldown_bars'), ('exit', 'reentry_bars')]):
                eligible.append(candidate)
        return eligible, {}


class ReplayPort:
    def __init__(self, initial, cost):
        self.initial = self.equity = initial
        self.cost = cost
        self.position = None
        self.trades = []
        self.now = None

    def snapshot(self):
        return self.position.copy() if self.position else None

    def cancel(self):
        if self.position:
            raise RuntimeError('old position still exists')

    def open(self, signal):
        if self.position or self.equity <= 0:
            raise RuntimeError('invalid replay entry')
        sign = 1 if signal.side == 'LONG' else -1
        notional = self.equity * signal.multiplier
        self.entry_equity = self.equity
        self.entry_cost = notional * self.cost
        self.equity -= self.entry_cost
        self.owner, self.entry_time = signal.owner, self.now
        self.position = dict(side=signal.side, size=notional / signal.price,
            entry=signal.price, tp=signal.price * (1 + sign * signal.tp_percent / 100),
            sl=signal.price * (1 - sign * signal.sl_percent / 100))

    def marked(self, price):
        p = self.position
        if not p:
            return self.equity
        sign = 1 if p['side'] == 'LONG' else -1
        return self.equity + sign * p['size'] * (price - p['entry'])

    def close(self, price, reason='PREEMPTED_BY_5M'):
        p = self.position
        gross = self.marked(price) - self.equity
        exit_cost = p['size'] * price * self.cost
        self.equity += gross - exit_cost
        self.trades.append(dict(owner=self.owner, side=p['side'], entry_time=str(self.entry_time),
            exit_time=str(self.now), entry_price=p['entry'], exit_price=price,
            tp=p['tp'], sl=p['sl'], qty=p['size'], reason=reason, gross_pnl=gross,
            estimated_cost=self.entry_cost + exit_cost, pnl=gross-self.entry_cost-exit_cost,
            equity=self.equity))
        self.position = None


def load_data(path):
    with sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro', uri=True) as db:
        frame = pd.read_sql_query("SELECT exchange,timestamp,open,high,low,close,volume FROM ohlcv "
            "WHERE asset_class='crypto' AND symbol='BTC/USDT:USDT' AND timeframe='5m' "
            "ORDER BY timestamp", db)
    prices, sources, audit = {}, {}, {}
    expected = None
    for ex in ('binance', 'bitget', 'okx', 'bybit'):
        part = frame[frame.exchange == ex].copy()
        part.index = pd.to_datetime(part.timestamp, unit='ms', utc=True)
        part = part[['open', 'high', 'low', 'close', 'volume']]
        if part.empty or part.index.has_duplicates:
            raise ValueError(ex + ': empty or duplicate data')
        if expected is None:
            expected = pd.date_range(part.index[0], part.index[-1], freq='5min')
        if not part.index.equals(expected):
            raise ValueError(ex + ': missing or misaligned 5m candles')
        values = part.to_numpy()
        if (not np.isfinite(values).all() or (part.volume < 0).any()
            or (part[['open','high','low','close']] <= 0).any().any()
            or (part.high < part[['open','close','low']].max(axis=1)).any()
            or (part.low > part[['open','close','high']].min(axis=1)).any()):
            raise ValueError(ex + ': invalid OHLCV')
        sources[ex] = part.volume
        if ex == 'bitget':
            prices['5m'] = part
        audit[ex] = dict(rows=len(part), first=str(part.index[0]), last=str(part.index[-1]))
    prices['15m'] = prices['5m'].resample('15min', label='left', closed='left').agg(
        dict(open='first', high='max', low='min', close='last', volume='sum'))
    counts = prices['5m'].close.resample('15min').count()
    prices['15m'] = prices['15m'].loc[counts == 3]
    volumes = {'5m': sources, '15m': {ex: v.resample('15min').sum().loc[prices['15m'].index]
                                     for ex, v in sources.items()}}
    return prices, volumes, audit


def prepare_candidates(frames, volumes):
    evaluator = DualTimeframeSignals()
    possible = set()
    for tf in PROFILES:
        ratio = normalize_exchange_volume(volumes[tf], PROFILES[tf]['volume_lookback'], required_sources=4)
        possible.update(ratio.index[ratio >= PROFILES[tf]['volume_break_multiplier']] + pd.Timedelta(tf))
    start = max(frames[tf].index[199] + pd.Timedelta(tf) for tf in PROFILES)
    end = frames['5m'].index[-1] + pd.Timedelta('5m')
    result = {}
    for b in sorted(possible):
        if b < start or b > end:
            continue
        slices, sources = {}, {}
        for tf in evaluator.due(b):
            stop = frames[tf].index.searchsorted(b - pd.Timedelta(tf), side='right')
            # Same 500-bar data budget as PriorityRuntime; only completed rows.
            slices[tf] = frames[tf].iloc[max(0, stop-500):stop]
            sources[tf] = {ex: v.reindex(slices[tf].index) for ex, v in volumes[tf].items()}
        candidates, _ = evaluator.evaluate(slices, sources, b, b, {})
        if candidates:
            result[b] = candidates
    return result, start


def replay(frame, candidates, start, initial=1000., cost=0.0003):
    port = ReplayPort(initial, cost)
    controller = PriorityController(port, MemoryJournal(), clock=lambda: port.now)
    controller.signals = ReplaySignals(candidates)
    peak, max_dd = initial, 0.
    curve = []
    previous_day = None
    for row in frame.loc[start-pd.Timedelta('5m'):].itertuples():
        b = row.Index + pd.Timedelta('5m')
        port.now = b
        p = port.snapshot()
        if p:
            long = p['side'] == 'LONG'
            sl = row.low <= p['sl'] if long else row.high >= p['sl']
            tp = row.high >= p['tp'] if long else row.low <= p['tp']
            # Adverse opening gaps worsen SL; favourable TP gaps stay capped at TP.
            stop_fill = min(row.open, p['sl']) if long else max(row.open, p['sl'])
            worst = stop_fill if sl else (row.low if long else row.high)
            marked = port.marked(worst)
            max_dd = max(max_dd, (peak - marked) / peak * 100)
            if sl or tp:
                port.close(stop_fill if sl else p['tp'], 'SL' if sl else 'TP')
                controller.poll(b)
        if b in candidates:
            controller.step({}, {}, b, b)
        marked = port.marked(row.close)
        peak = max(peak, marked)
        max_dd = max(max_dd, (peak-marked) / peak * 100)
        if marked <= 0:
            raise RuntimeError('non-positive account equity; liquidation modelling required')
        if previous_day != b.date():
            curve.append(dict(time=str(b), equity=marked))
            previous_day = b.date()
    if port.snapshot():
        port.close(float(frame.close.iloc[-1]), 'END_OF_DATA')
    max_dd = max(max_dd, (peak-port.equity)/peak*100)
    curve.append(dict(time=str(port.now), equity=port.equity))
    pnl = [t['pnl'] for t in port.trades]
    gain, loss = sum(x for x in pnl if x >= 0), -sum(x for x in pnl if x < 0)
    summary = dict(initial_capital=initial, final_equity=port.equity,
        return_percent=(port.equity/initial-1)*100, max_drawdown_percent=max_dd,
        trades=len(pnl), win_rate=sum(x>=0 for x in pnl)/len(pnl)*100 if pnl else 0,
        profit_factor=gain/loss if loss else None,
        estimated_costs=sum(t['estimated_cost'] for t in port.trades),
        owners=dict(Counter(t['owner'] for t in port.trades)),
        exits=dict(Counter(t['reason'] for t in port.trades)))
    return dict(summary=summary, trades=port.trades, equity_curve=curve)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    frames, volumes, audit = load_data(args.db)
    print('DB validated: ' + str(audit), flush=True)
    candidates, start = prepare_candidates(frames, volumes)
    print('Production evaluator candidate boundaries: ' + str(len(candidates)), flush=True)
    result = replay(frames['5m'], candidates, start)
    repeat = replay(frames['5m'], candidates, start)
    if result != repeat:
        raise RuntimeError('determinism verification failed')
    single = {}
    for tf in PROFILES:
        s = profile_settings(tf)
        s.initial_capital = 1000
        s.backtest_fee_percent = .02
        s.backtest_slippage_percent = .01
        s.backtest_compounding_enabled = True
        s.backtest_execution_model = 'signal_close'
        s.backtest_max_total_multiplier = 15
        ratio = normalize_exchange_volume(volumes[tf], s.volume_lookback, required_sources=4)
        r = asdict(run_backtest(frames[tf], s, ratio, include_details=False))
        single[tf] = {k:v for k,v in r.items() if k not in ('trades_log','equity_curve')}
    sha = hashlib.sha256()
    with open(args.db, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            sha.update(chunk)
    payload = dict(source_commit=args.source_commit,
        db_sha256=sha.hexdigest(), profile_sha256=profile_hash(), data=audit,
        common=COMMON, profiles=PROFILES, deterministic_replay=True, warmup_end=str(start),
        model='Production signal evaluator + production PriorityController + OHLC reference fills',
        assumptions=['15m aggregated from three complete Bitget 5m candles and each source volume',
            '500 completed bars per signal evaluation; live snapshots can include a forming bar',
            'Signal-close entries; fixed signal-price TP/SL; SL first; adverse SL gaps applied',
            'Compounding; fee 0.02% + slippage 0.01% per side; end-of-data close',
            'No funding, order book, IOC partial fills, live latency or mark-price liquidation reproduction',
            'MDD uses adverse OHLC excursion before exit; intrabar ordering is unknown',
            'Exit cooldown timestamps use candle-close observation, not live intrabar polling',
            'Database is supplied OHLCV: exchange provenance and historical revisions are not independently verified'],
        priority=result, single_timeframe_vector=single)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    print(json.dumps(dict(priority=result['summary'], single=single), indent=2), flush=True)


if __name__ == '__main__':
    main()
