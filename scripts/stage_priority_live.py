"""Stage reviewed priority LIVE sources into an existing server checkout.

This script never edits service settings, restarts a process, or contacts an exchange.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import py_compile
import shutil


FILES = (
    'universal_bot/main.py',
    'universal_bot/dashboard.py',
    'universal_bot/priority_controller.py',
    'universal_bot/priority_runtime.py',
    'universal_bot/priority_signals.py',
    'universal_bot/providers/mobile_relay.py',
    'universal_bot/adapters/hybrid_ccxt_adapter.py',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    target = Path(args.target).resolve()
    if not (target / 'universal_bot/main.py').is_file():
        raise SystemExit('target is not a universal-trading-bot checkout')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = target / '.priority-live-backups' / stamp
    for relative in FILES:
        incoming = source / relative
        if not incoming.is_file():
            raise SystemExit('candidate missing: ' + relative)
        if (target / relative).exists():
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / relative, destination)
    for relative in FILES:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
        py_compile.compile(str(destination), doraise=True)
    print('STAGED_PRIORITY_LIVE_SOURCE')
    print('backup=' + str(backup))
    print('activation=NOT_PERFORMED')


if __name__ == '__main__':
    main()
