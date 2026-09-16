"""Separate public-data observer. Never constructs an execution engine.

Run manually: python -m universal_bot.priority_shadow --boundaries 3
This does not change the existing dashboard, strategy, account or service.
"""
import argparse
from dataclasses import asdict
import json
import sqlite3
import time
from pathlib import Path

import pandas as pd

from universal_bot.priority_signals import DualTimeframeSignals, DataUnavailable, profile_hash


class ShadowJournal:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS priority_observations '
            '(profile TEXT, boundary TEXT, payload TEXT, PRIMARY KEY(profile,boundary))')
        self.db.commit()

    def contains(self, boundary):
        return self.db.execute('SELECT 1 FROM priority_observations WHERE profile=? AND boundary=?',
            (profile_hash(), boundary.isoformat())).fetchone() is not None

    def record(self, boundary, payload):
        with self.db:
            cursor = self.db.execute('INSERT OR IGNORE INTO priority_observations VALUES(?,?,?)',
                (profile_hash(), boundary.isoformat(), json.dumps(payload, default=str, allow_nan=False)))
        return cursor.rowcount == 1

    def close(self):
        self.db.close()


class PriorityShadowMonitor:
    def __init__(self, market_data, journal, clock=lambda: pd.Timestamp.now(tz='UTC')):
        self.data, self.journal, self.clock = market_data, journal, clock
        self.signals = DualTimeframeSignals()

    def scan(self, boundary):
        if self.journal.contains(boundary):
            return {'status': 'DUPLICATE', 'boundary': boundary.isoformat()}
        if self.clock() < boundary or self.clock() - boundary > pd.Timedelta(seconds=30):
            return {'status': 'STALE', 'boundary': boundary.isoformat()}
        frames, volumes = {}, {}
        for tf in self.signals.due(boundary):
            frames[tf] = self.data.fetch_ohlcv('BTC/USDT:USDT', tf, limit=500)
            volumes[tf] = self.data.fetch_volume_sources('BTC/USDT:USDT', tf, limit=500)
        candidates, diagnostics = self.signals.evaluate(frames, volumes, boundary, self.clock())
        payload = {'status': 'OBSERVED', 'mode': 'SHADOW_SIGNALS_ONLY',
            'boundary': boundary.isoformat(), 'profile_hash': profile_hash(),
            'candidates': [asdict(s) for s in candidates], 'diagnostics': diagnostics,
            'note': 'Raw candidates; no position, cooldown history, fills or orders simulated.'}
        if not self.journal.record(boundary, payload):
            return {'status': 'DUPLICATE', 'boundary': boundary.isoformat()}
        return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boundaries', type=int, default=3)
    parser.add_argument('--journal', default='data/priority-shadow.sqlite')
    args = parser.parse_args()
    if not 1 <= args.boundaries <= 288:
        parser.error('boundaries must be between 1 and 288')
    # Explicit empty credentials: does not load .env or instantiate TradingEngine.
    from universal_bot.adapters.hybrid_ccxt_adapter import HybridCCXTAdapter
    public = HybridCCXTAdapter('bitget', '', '', '', community_fallback=False,
        fallback_exchanges=['binance', 'bybit'])
    path = Path(args.journal)
    path.parent.mkdir(parents=True, exist_ok=True)
    journal = ShadowJournal(path)
    monitor = PriorityShadowMonitor(public, journal)
    boundary = pd.Timestamp.now(tz='UTC').floor('5min') + pd.Timedelta(minutes=5)
    print(json.dumps({'mode': 'SHADOW_SIGNALS_ONLY', 'next_boundary': str(boundary),
        'profile_hash': profile_hash(), 'boundaries': args.boundaries}), flush=True)
    try:
        for _ in range(args.boundaries):
            while pd.Timestamp.now(tz='UTC') < boundary:
                time.sleep(min(1, max(0, (boundary-pd.Timestamp.now(tz='UTC')).total_seconds())))
            last_error = ''
            while pd.Timestamp.now(tz='UTC') - boundary <= pd.Timedelta(seconds=30):
                try:
                    result = monitor.scan(boundary)
                    if result['status'] in {'OBSERVED', 'DUPLICATE'}:
                        print(json.dumps(result, default=str, allow_nan=False), flush=True)
                        break
                    last_error = result['status']
                except Exception as exc:
                    last_error = type(exc).__name__ + ': ' + str(exc)
                time.sleep(2)
            else:
                print(json.dumps({'status': 'BLOCKED', 'boundary': str(boundary),
                    'reason': last_error or 'data deadline expired'}), flush=True)
            boundary += pd.Timedelta(minutes=5)
    finally:
        journal.close()


if __name__ == '__main__':
    main()
