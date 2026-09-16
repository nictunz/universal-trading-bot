"""Priority state machine for the isolated PAPER runtime; no exchange port."""
import fcntl
import json
import math
from pathlib import Path
import sqlite3
from threading import RLock

import pandas as pd

from universal_bot.priority_signals import DualTimeframeSignals, PROFILES, profile_hash, utc


class PriorityJournal:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lockfile = open(str(path)+'.lock', 'a')
        try:
            fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.db = sqlite3.connect(path, check_same_thread=False)
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('CREATE TABLE IF NOT EXISTS priority_state(id INTEGER PRIMARY KEY, body TEXT)')
            self.db.commit()
        except Exception:
            self.lockfile.close()
            raise

    def load(self):
        row = self.db.execute('SELECT body FROM priority_state WHERE id=1').fetchone()
        return json.loads(row[0]) if row else dict(profile=profile_hash(), owner=None,
            position=None, history={}, pending=None, halted=None, watermark=None)

    def save(self, state):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO priority_state VALUES(1,?)',
                (json.dumps(state, allow_nan=False),))

    def close(self):
        self.db.close()
        self.lockfile.close()


class PriorityController:
    def __init__(self, port, journal, clock=lambda: pd.Timestamp.now(tz='UTC')):
        self.port, self.journal = port, journal
        self.clock = clock
        self.state = journal.load()
        self.signals = DualTimeframeSignals()
        self.lock = RLock()
        if self.state['profile'] != profile_hash():
            self.halt('profile changed; reconciliation required')
        elif self.state['pending']:
            self.halt('unfinished operation; no automatic retry')

    def halt(self, reason):
        self.state['halted'] = reason
        self.journal.save(self.state)
        return 'HALTED'

    def intent(self, operation):
        self.state['pending'] = operation
        self.journal.save(self.state)

    def _observe(self, now):
        p = self.port.snapshot()
        if p is not None:
            if not self.state['owner'] or self.state['position'] != p:
                raise RuntimeError('position ownership changed or unknown')
        elif self.state['owner']:
            self.state['history'].setdefault(self.state['owner'], {})['exit'] = utc(now).isoformat()
            self.state['owner'], self.state['position'] = None, None
            self.intent('cancel_after_external_exit')
            self.port.cancel()
            self.state['pending'] = None
            self.journal.save(self.state)
        return p

    def poll(self, now):
        """Reconcile on every scan, including between candle boundaries."""
        with self.lock:
            if self.state['halted']:
                return 'HALTED'
            try:
                self._observe(now)
                return 'RECONCILED'
            except Exception as exc:
                return self.halt(str(exc))

    def step(self, frames, volumes, boundary, now):
        with self.lock:
            b, now = utc(boundary), utc(now)
            if self.poll(now) == 'HALTED':
                return 'HALTED'
            if self.state['watermark'] and b <= utc(self.state['watermark']):
                return 'DUPLICATE_OR_OLD'
            # DataUnavailable propagates for retry; no watermark is consumed.
            candidates, _ = self.signals.evaluate(frames, volumes, b, now, self.state['history'])
            self.state['watermark'] = b.isoformat()
            self.journal.save(self.state)
            if not candidates:
                return 'NO_ELIGIBLE_SIGNAL'
            signal = candidates[0]  # evaluator always returns 5m first
            owner = self.state['owner']
            if owner == '5m' or (owner and signal.owner == '15m'):
                return 'BUSY'
            try:
                if utc(self.clock()) - b > pd.Timedelta(seconds=30):
                    return self.halt('signal expired before execution')
                if owner:
                    self.intent('close_15m')
                    self.port.close(signal.price)
                    if self.port.snapshot() is not None:
                        return self.halt('partial close; entry blocked')
                    self.state['history'].setdefault(owner, {})['exit'] = now.isoformat()
                    self.state['owner'], self.state['position'] = None, None
                self.intent('cancel_old_protection')
                self.port.cancel()
                if utc(self.clock()) - b > pd.Timedelta(seconds=30):
                    return self.halt('signal expired during transition; entry blocked')
                self.intent('open_' + signal.owner)
                self.port.open(signal)
                position = self.port.snapshot()
                if position is None or position['side'] != signal.side:
                    return self.halt('entry/protection unverified')
                self.state['owner'], self.state['position'] = signal.owner, position
                self.state['history'].setdefault(signal.owner, {})['entry'] = b.isoformat()
                self.state['pending'] = None
                self.journal.save(self.state)
                return 'OPENED_' + signal.owner
            except Exception as exc:
                return self.halt(str(exc))

