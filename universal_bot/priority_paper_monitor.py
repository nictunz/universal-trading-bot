"""Public market data to isolated PAPER account, with no account credentials."""
import argparse
import json
import time
from pathlib import Path

import pandas as pd

from universal_bot.priority_paper_runtime import PaperPriorityRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal', required=True)
    parser.add_argument('--boundaries', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.boundaries <= 288:
        parser.error('boundaries must be 1..288')
    path = Path(args.journal)
    if path.name in ('shadow.sqlite', 'priority.sqlite'):
        parser.error('use a separate paper-only journal filename')
    from universal_bot.adapters.hybrid_ccxt_adapter import HybridCCXTAdapter
    data = HybridCCXTAdapter('bitget', '', '', '', community_fallback=False,
                             fallback_exchanges=['binance', 'bybit'])
    runtime = PaperPriorityRuntime(path)
    boundary = pd.Timestamp.now(tz='UTC').floor('5min') + pd.Timedelta(minutes=5)
    print(json.dumps(dict(mode='PAPER_ONLY', real_orders_enabled=False,
                          next_boundary=str(boundary))), flush=True)
    try:
        for _ in range(args.boundaries):
            while pd.Timestamp.now(tz='UTC') < boundary:
                time.sleep(0.5)
            error = ''
            while pd.Timestamp.now(tz='UTC') - boundary <= pd.Timedelta(seconds=30):
                try:
                    frames, volumes = {}, {}
                    for tf in runtime.controller.signals.due(boundary):
                        frames[tf] = data.fetch_ohlcv('BTC/USDT:USDT', tf, limit=500)
                        volumes[tf] = data.fetch_volume_sources('BTC/USDT:USDT', tf, limit=500)
                    status = runtime.step(frames, volumes, boundary, pd.Timestamp.now(tz='UTC'))
                    print(json.dumps(dict(status=status, boundary=str(boundary),
                                          **runtime.snapshot()), allow_nan=False), flush=True)
                    if status == 'HALTED':
                        return
                    break
                except Exception as exc:
                    error = type(exc).__name__ + ': ' + str(exc)
                    if runtime.controller.state['pending']:
                        runtime.controller.halt(error)
                        print(json.dumps(dict(status='HALTED', reason=error)), flush=True)
                        return
                    time.sleep(1)
            else:
                print(json.dumps(dict(status='DATA_BLOCKED', boundary=str(boundary), reason=error)), flush=True)
            boundary += pd.Timedelta(minutes=5)
    finally:
        runtime.close()


if __name__ == '__main__':
    main()
