"""Scanner-facing integration: both timeframes feed one initialized engine.

Not registered by main.py. Do not run the existing scanner's engine.step in
parallel with this worker. The deployment owner must replace that route, not
append a second account trader.
"""
import pandas as pd

from universal_bot.priority_controller import EngineExecutionPort, PriorityController, PriorityJournal
from universal_bot.priority_signals import DataUnavailable


class PriorityRuntime:
    def __init__(self, engine, journal_path, clock=lambda: pd.Timestamp.now(tz='UTC')):
        self.engine, self.clock = engine, clock
        self.journal = PriorityJournal(journal_path)
        try:
            self.controller = PriorityController(EngineExecutionPort(engine), self.journal, clock=clock)
        except Exception:
            self.journal.close()
            raise
        self.last_status = 'ATTACHED'

    def scan_once(self):
        now = self.clock()
        c = self.controller
        if c.poll(now) == 'HALTED':
            self.last_status = 'HALTED'
            return self.last_status
        boundary = now.floor('5min')
        if now-boundary > pd.Timedelta(seconds=30):
            self.last_status = 'WAITING_FOR_BOUNDARY'
            return self.last_status
        if c.state['watermark'] and boundary <= pd.Timestamp(c.state['watermark']):
            self.last_status = 'DUPLICATE_OR_OLD'
            return self.last_status
        frames, volumes = {}, {}
        try:
            for tf in c.signals.due(boundary):
                frames[tf] = self.engine.adapter.fetch_ohlcv(self.engine.settings.symbol,tf,limit=500)
                volumes[tf] = self.engine.adapter.fetch_volume_sources(self.engine.settings.symbol,tf,limit=500)
            self.last_status = c.step(frames,volumes,boundary,self.clock())
        except DataUnavailable as exc:
            self.last_status = 'DATA_BLOCKED: ' + str(exc)
        except Exception as exc:
            # No ordering calls precede the completed data batch in this scope.
            # Unexpected controller failures also remain blocked for inspection.
            self.last_status = c.halt(type(exc).__name__ + ': ' + str(exc))
        return self.last_status

    def snapshot(self):
        return dict(mode='PRIORITY_RUNTIME', status=self.last_status,
            owner=self.controller.state['owner'], pending=self.controller.state['pending'],
            halted=self.controller.state['halted'],
            profiles=self.controller.state['profile'],
            multipliers={'5m':9.55,'15m':5.0})

    def close(self):
        self.journal.close()
