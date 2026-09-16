"""Single-engine priority execution integration, not enabled by main.py.

Caller must supply an initialized engine and ensure exclusive account/symbol
ownership. This module never starts a service or configures an account itself.
"""
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


class EngineExecutionPort:
    """Use one real runtime engine; never two engines trading the same symbol."""
    def __init__(self, engine):
        if not engine.live or not engine._live_initialized:
            raise ValueError('caller must initialize the engine before attaching')
        if engine.settings.symbol != 'BTC/USDT:USDT':
            raise ValueError('selected profiles are BTC-only')
        if engine.settings.live_max_entries_per_position != 1:
            raise ValueError('exactly one entry per position required')
        self.engine, self.adapter = engine, engine.adapter
        self.symbol = engine.settings.symbol

    def check(self):
        if self.engine.safety.halted:
            raise RuntimeError('engine halted: ' + self.engine.safety.reason)

    def snapshot(self):
        self.check()
        p = self.adapter.position(self.symbol)
        side, qty = p.get('side'), float(p.get('size') or 0)
        if side == 'FLAT' and qty == 0:
            # Require a second read before treating FLAT as an exit.
            p = self.adapter.position(self.symbol)
            side, qty = p.get('side'), float(p.get('size') or 0)
            if side == 'FLAT' and qty == 0:
                if not self.engine.position.flat:
                    self.engine._reconcile_live()
                    self.check()
                    if not self.engine.position.flat:
                        raise RuntimeError('internal exit not reconciled')
                return None
        entry = float(p.get('entry_price') or 0)
        if side not in ('LONG', 'SHORT') or not all(math.isfinite(x) and x > 0 for x in (qty, entry)):
            raise RuntimeError('invalid exchange position')
        internal = self.engine.position
        if internal.side != side or not math.isclose(abs(internal.size), qty, rel_tol=1e-9, abs_tol=1e-12):
            raise RuntimeError('internal/exchange position mismatch')
        status = self.adapter.protection_status(self.symbol)
        if status.get('ok') is not True or len(status.get('orders', [])) != 2:
            raise RuntimeError('protection pair not verified')
        prices = {'tp': internal.tp, 'sl': internal.sl}
        legs = set()
        for order in status['orders']:
            leg = self.adapter._protection_leg(order)
            if leg not in prices or prices[leg] is None:
                raise RuntimeError('fixed protection price unavailable')
            wanted_price = float(self.adapter._price(self.symbol, prices[leg]))
            size = next((order[k] for k in ('size','sizeQty','qty') if order.get(k) not in (None,'')), 0)
            if (not math.isclose(float(size), qty, rel_tol=1e-9, abs_tol=1e-12)
                or float(order.get('triggerPrice') or 0) != wanted_price
                or order.get('side') != ('sell' if side == 'LONG' else 'buy')):
                raise RuntimeError('protection does not cover fixed position')
            legs.add(leg)
        if legs != {'tp','sl'}:
            raise RuntimeError('TP/SL legs missing')
        return dict(side=side, size=qty, entry=entry, tp=float(prices['tp']), sl=float(prices['sl']))

    def cancel(self):
        result = self.adapter.cancel_protection(self.symbol)
        if not isinstance(result, dict) or result.get('ok') is not True or result.get('remaining'):
            raise RuntimeError('protection cancellation unconfirmed')

    def close(self, reference_price):
        self.engine._close(reference_price, 'PREEMPTED_BY_5M')
        self.check()

    def open(self, signal):
        if self.snapshot() is not None:
            raise RuntimeError('entry while position exists')
        # Parameters are explicit; fixed protection comes from the selected signal.
        self.engine.settings.timeframe = signal.owner
        self.engine.settings.live_entry_multiplier = PROFILES[signal.owner]['live_entry_multiplier']
        self.engine.current_bar_time = signal.opened_at.isoformat()
        self.engine.bar_number += 1
        self.engine._open(signal.side, signal.price, signal.tp_percent, signal.sl_percent)
        self.check()


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
