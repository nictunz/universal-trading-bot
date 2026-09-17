"""Scanner-facing integration: both timeframes feed one initialized engine.

Not registered by main.py. Do not run the existing scanner's engine.step in
parallel with this worker. The deployment owner must replace that route, not
append a second account trader.
"""
import pandas as pd

from universal_bot.priority_controller import EngineExecutionPort, PriorityController, PriorityJournal
from universal_bot.priority_signals import DataUnavailable, PROFILES


class PriorityRuntime:
    DATA_ALERT_THRESHOLD = 3
    DATA_HALT_SECONDS = 15.0
    TRANSIENT_DATA_ERRORS = (
        'mobile relay snapshot not found:',
        'mobile relay is stale:',
        'mobile relay source is stale:',
        'mobile relay has no completed candles',
    )

    def __init__(self, engine, journal_path, clock=lambda: pd.Timestamp.now(tz='UTC')):
        self.engine, self.clock = engine, clock
        self.journal = PriorityJournal(journal_path)
        try:
            self.controller = PriorityController(EngineExecutionPort(engine), self.journal, clock=clock)
        except Exception:
            self.journal.close()
            raise
        self.last_status = 'ATTACHED'
        self._data_blocked_count = 0
        self._data_blocked_since = None
        self._alert_key = None

    def _notify(self, title, **fields):
        """Best-effort only: Discord must never affect trading or safety state."""
        try:
            notify = getattr(self.engine, '_notify_live', None)
            if callable(notify):
                notify(title, **fields)
        except Exception:
            pass

    def _alert_once(self, key, title, **fields):
        if key == self._alert_key:
            return
        self._alert_key = key
        self._notify(title, **fields)

    def _healthy(self, status):
        self._data_blocked_count = 0
        self._data_blocked_since = None
        if self._alert_key and str(self._alert_key).startswith('DATA_BLOCKED:'):
            previous = self._alert_key.split(':', 1)[1]
            self._alert_key = None
            self._notify(
                '🟢 LIVE 데이터 장애 복구',
                심볼=self.engine.settings.symbol,
                상태=status,
                이전오류=previous,
                안내='Priority Runtime 데이터 수신이 정상화되었습니다.',
            )

    def _halt_alert(self):
        reason = str(self.controller.state.get('halted') or 'unknown')
        self._alert_once(
            'HALTED:' + reason,
            '🔴 LIVE Priority Runtime HALT',
            심볼=self.engine.settings.symbol,
            오류=reason,
            owner=self.controller.state.get('owner'),
            pending=self.controller.state.get('pending'),
            안내='신규 진입이 차단되었습니다. 서버 상태를 확인하세요.',
        )

    @classmethod
    def _is_transient_data_error(cls, exc):
        text = str(exc)
        return any(marker in text for marker in cls.TRANSIENT_DATA_ERRORS)

    def _data_blocked(self, reason, now):
        now = pd.Timestamp(now)
        if now.tzinfo is None:
            now = now.tz_localize('UTC')
        else:
            now = now.tz_convert('UTC')
        if self._data_blocked_since is None:
            self._data_blocked_since = now
        self._data_blocked_count += 1
        elapsed = max(0.0, (now - self._data_blocked_since).total_seconds())
        self.last_status = 'DATA_BLOCKED: ' + reason
        if self._data_blocked_count >= self.DATA_ALERT_THRESHOLD:
            self._alert_once(
                'DATA_BLOCKED:' + reason,
                '🟠 LIVE 데이터 연속 장애',
                심볼=self.engine.settings.symbol,
                오류=reason,
                연속횟수=self._data_blocked_count,
                지속초=f'{elapsed:.1f}',
                안내='순간 지연은 무시하고 연속 장애만 알립니다. 신규 신호 처리는 데이터 정상화까지 차단됩니다.',
            )
        if elapsed >= self.DATA_HALT_SECONDS:
            self.last_status = self.controller.halt(
                f'data unavailable for {elapsed:.1f}s: {reason}'
            )
            self._halt_alert()
        return self.last_status

    def scan_once(self):
        now = self.clock()
        c = self.controller
        if c.poll(now) == 'HALTED':
            self.last_status = 'HALTED'
            self._halt_alert()
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
            if self.last_status == 'HALTED':
                self._halt_alert()
            else:
                self._healthy(self.last_status)
        except DataUnavailable as exc:
            self._data_blocked(str(exc), now)
        except Exception as exc:
            # Relay snapshots are replaced asynchronously by the Android writer.
            # A short missing/stale window is data unavailability, not an
            # execution fault. Keep entries blocked and HALT only if it persists.
            if self._is_transient_data_error(exc):
                self._data_blocked(str(exc), now)
            else:
                # No ordering calls precede the completed data batch in this scope.
                # Unexpected controller failures remain fail-closed for inspection.
                self.last_status = c.halt(type(exc).__name__ + ': ' + str(exc))
                self._halt_alert()
        return self.last_status

    def snapshot(self):
        return dict(mode='PRIORITY_RUNTIME', status=self.last_status,
            owner=self.controller.state['owner'], pending=self.controller.state['pending'],
            halted=self.controller.state['halted'],
            profiles=self.controller.state['profile'],
            multipliers={tf: values['live_entry_multiplier'] for tf, values in PROFILES.items()},
            position=self.controller.state['position'],
            watermark=self.controller.state['watermark'])

    def close(self):
        self.journal.close()
