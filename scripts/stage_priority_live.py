"""Stage reviewed priority LIVE sources into an existing server checkout.

This script never edits service settings, restarts a process, or contacts an exchange.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import py_compile
import shutil
import time


FILES = (
    'universal_bot/main.py',
    'universal_bot/dashboard.py',
    'universal_bot/priority_controller.py',
    'universal_bot/priority_runtime.py',
    'universal_bot/priority_signals.py',
    'universal_bot/providers/mobile_relay.py',
    'universal_bot/adapters/hybrid_ccxt_adapter.py',
)
INVENTORY = (
    'universal_bot/preflight.py', 'universal_bot/config.py', 'universal_bot/engine.py',
    'universal_bot/main.py', 'universal_bot/runtime_engine.py',
    'universal_bot/priority_controller.py', 'universal_bot/priority_runtime.py',
    'universal_bot/priority_signals.py', 'universal_bot/adapters/bitget_elite.py',
    'universal_bot/providers/mobile_relay.py', 'universal_bot/trade_history.py',
    'universal_bot/dashboard.py',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    target = Path(args.target).resolve()
    if not (target / 'universal_bot/main.py').is_file():
        raise SystemExit('target is not a universal-trading-bot checkout')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = target / '.priority-live-backups' / stamp
    manifest = target / 'data/deployment-manifest.json'
    for relative in FILES:
        incoming = source / relative
        if not incoming.is_file():
            raise SystemExit('candidate missing: ' + relative)
        if (target / relative).exists():
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / relative, destination)
    if manifest.exists():
        destination = backup / 'data/deployment-manifest.json'
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifest, destination)
    for relative in FILES:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
        py_compile.compile(str(destination), doraise=True)
    hashes = {name: hashlib.sha256((target / name).read_bytes()).hexdigest()
              for name in INVENTORY}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(dict(commit=args.commit, files=hashes,
                                         created_at=time.time()), indent=2))
    print('STAGED_PRIORITY_LIVE_SOURCE')
    print('backup=' + str(backup))
    print('activation=NOT_PERFORMED')


if __name__ == '__main__':
    main()
