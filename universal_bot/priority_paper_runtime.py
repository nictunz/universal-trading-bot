"""Offline priority execution. Accepts data frames, never exchange adapters.

No LIVE switch, credentials, network client, service restart or real orders.
Fills use reference prices; cost is 0.03% per side, not an exchange simulation.
"""
import json
import math

import pandas as pd

from universal_bot.priority_paper_core import PriorityController, PriorityJournal
from universal_bot.priority_signals import PROFILES, utc


class PaperPort:
    def __init__(self, journal, initial_equity):
        if not math.isfinite(initial_equity) or initial_equity <= 0:
            raise ValueError('positive finite initial equity required')
        self.db = journal.db
        self.db.execute('CREATE TABLE IF NOT EXISTS paper_account(id INTEGER PRIMARY KEY, body TEXT)')
        row = self.db.execute('SELECT body FROM paper_account WHERE id=1').fetchone()
        self.account = json.loads(row[0]) if row else dict(
            equity=initial_equity, position=None, events=[], entry_boundary=None)
        self.save()

    def save(self):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO paper_account VALUES(1,?)',
                            (json.dumps(self.account, allow_nan=False),))

    def snapshot(self):
        p = self.account['position']
        return dict(p) if p else None

    def cancel(self):
        # Protection consists only of numbers in the simulated position.
        if self.account['position']:
            raise RuntimeError('cannot cancel protection while paper position exists')

    def open(self, signal):
        if self.snapshot():
            raise RuntimeError('paper position already open')
        if signal.side not in ('LONG', 'SHORT') or signal.owner not in PROFILES:
            raise ValueError('invalid paper signal')
        if not all(math.isfinite(x) and x > 0 for x in
                   (signal.price, signal.tp_percent, signal.sl_percent, self.account['equity'])):
            raise ValueError('invalid paper numbers')
        sign = 1 if signal.side == 'LONG' else -1
        notional = self.account['equity'] * PROFILES[signal.owner]['live_entry_multiplier']
        p = dict(side=signal.side, size=notional / signal.price, entry=signal.price,
                 tp=signal.price * (1 + sign * signal.tp_percent / 100),
                 sl=signal.price * (1 - sign * signal.sl_percent / 100))
        self.account['equity'] -= notional * 0.0003
        self.account['position'] = p
        self.account['entry_boundary'] = (
            utc(signal.opened_at) + pd.Timedelta(signal.owner)).isoformat()
        self.account['events'].append(dict(kind='PAPER_OPEN', owner=signal.owner, **p))
        self.save()

    def close(self, reference_price, reason='PREEMPTED_BY_5M'):
        if not math.isfinite(reference_price) or reference_price <= 0:
            raise ValueError('invalid close price')
        p = self.snapshot()
        if p is None:
            return
        sign = 1 if p['side'] == 'LONG' else -1
        pnl = sign * p['size'] * (reference_price - p['entry'])
        self.account['equity'] += pnl - p['size'] * reference_price * 0.0003
        self.account['events'].append(dict(kind='PAPER_CLOSE', reason=reason,
                                          price=reference_price, gross_pnl=pnl))
        self.account['position'] = None
        self.account['entry_boundary'] = None
        self.save()


class PaperPriorityRuntime:
    """Feed complete data batches through step; construction has no network effects."""
    def __init__(self, journal_path, initial_equity=1000.0):
        self.journal = PriorityJournal(journal_path)
        try:
            self.port = PaperPort(self.journal, initial_equity)
            self.now = pd.Timestamp.now(tz='UTC')
            self.controller = PriorityController(self.port, self.journal, clock=lambda: self.now)
            self.controller.poll(self.now)
        except Exception:
            self.journal.close()
            raise

    def step(self, frames, volumes, boundary, now):
        b, self.now = utc(boundary), utc(now)
        c = self.controller
        if c.state['halted']:
            return 'HALTED'
        if c.state['watermark'] and b <= utc(c.state['watermark']):
            return 'DUPLICATE_OR_OLD'
        if self.port.snapshot() and c.state['watermark'] and b - utc(c.state['watermark']) != pd.Timedelta(minutes=5):
            return c.halt('missing paper candle; exit path cannot be reconstructed')
        # Validate the entire batch before simulated exits or entries.
        c.signals.evaluate(frames, volumes, b, self.now, c.state['history'])
        p = self.port.snapshot()
        if p and b - pd.Timedelta(minutes=5) >= utc(self.port.account['entry_boundary']):
            row = frames['5m'].loc[b - pd.Timedelta(minutes=5)]
            sl = row.low <= p['sl'] if p['side'] == 'LONG' else row.high >= p['sl']
            tp = row.high >= p['tp'] if p['side'] == 'LONG' else row.low <= p['tp']
            if sl or tp:
                # Completed-candle model, SL first; no intrabar fill claim.
                c.intent('paper_touch_exit')
                self.port.close(p['sl'] if sl else p['tp'], 'SL' if sl else 'TP')
                c.state['pending'] = None
                self.journal.save(c.state)
        return c.step(frames, volumes, b, self.now)

    def snapshot(self):
        return dict(mode='PAPER_ONLY', real_orders_enabled=False,
                    owner=self.controller.state['owner'], halted=self.controller.state['halted'],
                    equity=self.port.account['equity'], position=self.port.snapshot(),
                    events=list(self.port.account['events']))

    def close(self):
        self.journal.close()
