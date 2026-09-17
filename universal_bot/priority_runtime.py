"""Scanner-facing integration: both timeframes feed one initialized engine.

Not registered by main.py. Do not run the existing scanner's engine.step in
parallel with this worker. The deployment owner must replace that route, not
append a second account trader.
"""
import pandas as pd

from universal_bot.priority_controller import EngineExecutionPort, PriorityController, PriorityJournal
from universal_bot.priority_signals import DataUnavailable, PROFILES


class PriorityRuntime:
    DATA_ALERT_SECONDS = 15.0
    DATA_HALT_SECONDS = 25.0
    DATA_RECOVERY_CONFIRMATIONS = 3
    TRANSIENT_DATA_ERRORS = (
        'mobile relay snapshot not found:',
        'mobile relay is stale:',
        'mobile relay source is stale:',
        'mobile relay has no completed candles',
    )
    DATA_HALT_PREFIX = 'data unavailable for '

    def __init__(self, engine, journal_path, clock=lambda: pd.Timestamp.now(tz='UTC')):
        self.engine, self.clock = engine, clock
        self.journal = PriorityJournal(journal_path)
        try:
            self.controller = PriorityController(EngineExecutionPort(engine), self.journal, clock=clock)
            self._recover_persisted_data_halt()
        except Exception:
            self.journal.close()
            raise
        self.last_status = 'ATTACHED'
        self._data_blocked_count = 0
        self._data_blocked_since = None
        self._alert_key = None
        self._data_recovery_confirmations = 0

    def _recover_persisted_data_halt(self):
        """Clear only a stale data-only HALT after proving the account is flat."""
        c = self.controller
        reason = str(c.state.get('halted') or '')
        if not reason.startswith(self.DATA_HALT_PREFIX):
            return False
        if c.state.get('owner') is not None or c.state.get('position') is not None or c.state.get('pending') is not None:
            return False
        if c.port.snapshot() is not None:
            return False
        c.state['halted'] = None
        c.journal.save(c.state)
        return True

    def _recover_running_data_halt(self):
        """Recover a transient data-only HALT without restarting the service.

        Recovery is deliberately stricter than the normal scan: only the exact
        data-unavailable HALT is eligible, no controller-owned/pending position
        may exist, both 5m and 15m market-data batches must be readable, and the
        exchange must report FLAT twice for three consecutive recovery probes.
        Execution/reconciliation/protection/profile halts are never cleared.
        """
        c = self.controller
        reason = str(c.state.get('halted') or '')
        if not reason.startswith(self.DATA_HALT_PREFIX):
            self._data_recovery_confirmations = 0
            return False
        if c.state.get('owner') is not None or c.state.get('position') is not None or c.state.get('pending') is not None:
            self._data_recovery_confirmations = 0
            return False
        safety = self.engine.safety
        mirrored = 'PRIORITY_RUNTIME_HALTED: ' + reason
        if safety.halted and str(safety.reason or '') != mirrored:
            self._data_recovery_confirmations = 0
            return False
        try:
            symbol = self.engine.settings.symbol
            for tf in ('5m', '15m'):
                self.engine.adapter.fetch_ohlcv(symbol, tf, limit=500)
                self.engine.adapter.fetch_volume_sources(symbol, tf, limit=500)
            first = self.engine.adapter.position(symbol)
            second = self.engine.adapter.position(symbol)
            for position in (first, second):
                if str(position.get('side') or 'FLAT') != 'FLAT' or float(position.get('size') or 0.0) > 1e-9:
                    self._data_recovery_confirmations = 0
                    return False
        except Exception:
            self._data_recovery_confirmations = 0
            return False
        self._data_recovery_confirmations += 1
        if self._data_recovery_confirmations < self.DATA_RECOVERY_CONFIRMATIONS:
            return False
        c.state['halted'] = None
        c.journal.save(c.state)
        if safety.halted and str(safety.reason or '') == mirrored:
            safety.halted = False
            safety.reason = ''
            safety.consecutive_errors = 0
            safety.protection_ok = True
        self._data_recovery_confirmations = 0
        self._data_blocked_count = 0
        self._data_blocked_since = None
        self._alert_key = None
        self._notify(
            '🟢 LIVE 데이터 HALT 자동복구',
            심볼=self.engine.settings.symbol,
            이전오류=reason,
            확인='5m/15m 데이터 정상 · Bitget FLAT 2회 × 3연속 확인',
        )
        return True

    def _notify(self, title, **fields):
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
        if elapsed >= self.DATA_ALERT_SECONDS:
            self._alert_once(
                'DATA_BLOCKED:' + reason,
                '🟠 LIVE 데이터 연속 장애',
                심볼=self.engine.settings.symbol,
                오류=reason,
                연속횟수=self._data_blocked_count,
                지속초=f'{elapsed:.1f}',
                안내='경계 동기화 유예시간을 초과했습니다. 신규 신호 처리는 데이터 정상화까지 차단됩니다.',
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
        if str(c.state.get('halted') or '').startswith(self.DATA_HALT_PREFIX):
            if not self._recover_running_data_halt():
                self.last_status = 'HALTED'
                self._halt_alert()
                return self.last_status
        if c.poll(now) == 'HALTED':
            self.last_status = 'HALTED'
            self._halt_alert()
            return self.last_status
        boundary = now.floor('5min')
        if now-boundary > pd.Timedelta(seconds=30):
            self._data_blocked_count = 0
            self._data_blocked_since = None
            if self._alert_key and str(self._alert_key).startswith('DATA_BLOCKED:'):
                self._alert_key = None
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
            self.last_status = c.step(frames,volumes,boundary,now)
            if self.last_status == 'HALTED':
                self._halt_alert()
            else:
                self._healthy(self.last_status)
        except DataUnavailable as exc:
            self._data_blocked(str(exc), now)
        except Exception as exc:
            if self._is_transient_data_error(exc):
                self._data_blocked(str(exc), now)
            else:
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
