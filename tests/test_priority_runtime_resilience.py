from types import SimpleNamespace

import pandas as pd

from universal_bot.priority_runtime import PriorityRuntime


class FakeController:
    def __init__(self):
        self.state = {'halted': None, 'owner': None, 'position': None, 'pending': None}

    def halt(self, reason):
        self.state['halted'] = reason
        return 'HALTED'


def runtime_stub():
    runtime = PriorityRuntime.__new__(PriorityRuntime)
    runtime.notifications = []
    runtime.engine = SimpleNamespace(
        settings=SimpleNamespace(symbol='BTC/USDT:USDT'),
        _notify_live=lambda *args, **kwargs: runtime.notifications.append((args, kwargs)),
    )
    runtime.controller = FakeController()
    runtime.last_status = 'ATTACHED'
    runtime._data_blocked_count = 0
    runtime._data_blocked_since = None
    runtime._alert_key = None
    return runtime


def recovery_runtime(reason, snapshot=None, owner=None, position=None, pending=None):
    runtime = runtime_stub()
    saved = []
    runtime.controller.state.update(
        halted=reason, owner=owner, position=position, pending=pending
    )
    runtime.controller.port = SimpleNamespace(snapshot=lambda: snapshot)
    runtime.controller.journal = SimpleNamespace(save=lambda state: saved.append(dict(state)))
    return runtime, saved


def test_mobile_relay_missing_is_transient_data_error():
    exc = RuntimeError(
        'mobile relay snapshot not found: /tmp/mobile-market-relay-5m.json'
    )
    assert PriorityRuntime._is_transient_data_error(exc)


def test_normal_rollover_lag_stays_silent_and_does_not_halt():
    runtime = runtime_stub()
    start = pd.Timestamp('2026-09-17T01:00:00Z')
    reason = '5m: missing completed OHLCV bars'

    runtime._data_blocked(reason, start)
    status = runtime._data_blocked(reason, start + pd.Timedelta(seconds=12))

    assert status.startswith('DATA_BLOCKED:')
    assert runtime.controller.state['halted'] is None
    assert runtime.notifications == []


def test_extended_gap_alerts_after_grace_but_stays_fail_closed():
    runtime = runtime_stub()
    start = pd.Timestamp('2026-09-17T01:00:00Z')
    reason = '5m: missing completed OHLCV bars'

    runtime._data_blocked(reason, start)
    status = runtime._data_blocked(reason, start + pd.Timedelta(seconds=15))

    assert status.startswith('DATA_BLOCKED:')
    assert runtime.controller.state['halted'] is None
    assert len(runtime.notifications) == 1
    assert runtime.notifications[0][0][0] == '🟠 LIVE 데이터 연속 장애'


def test_persistent_gap_blocks_boundary_without_account_halt():
    runtime = runtime_stub()
    start = pd.Timestamp('2026-09-17T01:00:00Z')
    reason = 'mobile relay snapshot not found: /tmp/relay.json'

    runtime._data_blocked(reason, start)
    status = runtime._data_blocked(reason, start + pd.Timedelta(seconds=25))

    assert status.startswith('DATA_BLOCKED:')
    assert runtime.controller.state['halted'] is None


def test_healthy_data_resets_gap_state():
    runtime = runtime_stub()
    start = pd.Timestamp('2026-09-17T01:00:00Z')
    runtime._data_blocked('missing completed OHLCV bars', start)

    runtime._healthy('NO_ELIGIBLE_SIGNAL')

    assert runtime._data_blocked_count == 0
    assert runtime._data_blocked_since is None


def test_stale_boundary_clears_transient_data_block_state():
    """A transient data fault must not leak into the next 5m boundary."""
    runtime = runtime_stub()

    runtime._data_blocked_count = 3
    runtime._data_blocked_since = pd.Timestamp("2026-09-17T01:00:05Z")
    runtime._alert_key = "DATA_BLOCKED:temporary"

    # scan_once() polls the controller before checking the 5m boundary.
    runtime.controller.poll = lambda now: "RUNNING"

    now = pd.Timestamp("2026-09-17T01:05:31Z")
    runtime.clock = lambda: now

    status = runtime.scan_once()

    assert status == "WAITING_FOR_BOUNDARY"
    assert runtime._data_blocked_count == 0
    assert runtime._data_blocked_since is None
    assert runtime._alert_key is None


def test_persisted_data_halt_recovers_only_after_confirmed_flat_snapshot():
    runtime, saved = recovery_runtime(
        'data unavailable for 300.4s: 5m: missing completed OHLCV bars'
    )

    assert runtime._recover_persisted_data_halt() is True
    assert runtime.controller.state['halted'] is None
    assert saved and saved[-1]['halted'] is None


def test_persisted_data_halt_stays_closed_if_position_exists():
    live_position = {'side': 'LONG', 'size': 0.01, 'entry': 60000.0}
    runtime, saved = recovery_runtime(
        'data unavailable for 300.4s: 5m: missing completed OHLCV bars',
        snapshot=live_position,
    )

    assert runtime._recover_persisted_data_halt() is False
    assert runtime.controller.state['halted'] is not None
    assert saved == []


def test_non_data_halt_never_auto_recovers():
    runtime, saved = recovery_runtime('position ownership changed or unknown')

    assert runtime._recover_persisted_data_halt() is False
    assert runtime.controller.state['halted'] == 'position ownership changed or unknown'
    assert saved == []


def test_data_halt_with_pending_operation_never_auto_recovers():
    runtime, saved = recovery_runtime(
        'data unavailable for 300.4s: 5m: missing completed OHLCV bars',
        pending='open',
    )

    assert runtime._recover_persisted_data_halt() is False
    assert runtime.controller.state['halted'] is not None
    assert saved == []


def test_boundary_completed_bar_lag_retries_then_processes(monkeypatch):
    runtime = runtime_stub()
    boundary = pd.Timestamp('2026-09-19T03:30:00Z')
    ticks = iter([
        boundary + pd.Timedelta(seconds=1),
        boundary + pd.Timedelta(seconds=1),
        boundary + pd.Timedelta(seconds=2),
        boundary + pd.Timedelta(seconds=2),
    ])
    runtime.clock = lambda: next(ticks, boundary + pd.Timedelta(seconds=2))
    runtime.controller.poll = lambda now: 'RUNNING'
    runtime.controller.state['watermark'] = None
    runtime.controller.signals = SimpleNamespace(due=lambda b: ('5m',))
    calls = {'ohlcv': 0}

    def fetch_ohlcv(symbol, tf, limit):
        calls['ohlcv'] += 1
        return object()

    runtime.engine.adapter = SimpleNamespace(
        fetch_ohlcv=fetch_ohlcv,
        fetch_volume_sources=lambda symbol, tf, limit: object(),
    )

    def step(frames, volumes, b, now):
        if calls['ohlcv'] == 1:
            raise __import__('universal_bot.priority_signals', fromlist=['DataUnavailable']).DataUnavailable(
                '5m: missing completed OHLCV bars'
            )
        return 'NO_ELIGIBLE_SIGNAL'

    runtime.controller.step = step
    monkeypatch.setattr('universal_bot.priority_runtime.time.sleep', lambda seconds: None)

    assert runtime.scan_once() == 'NO_ELIGIBLE_SIGNAL'
    assert calls['ohlcv'] == 2
    assert runtime.controller.state['halted'] is None


def test_boundary_completed_bar_lag_never_retries_past_admission(monkeypatch):
    runtime = runtime_stub()
    boundary = pd.Timestamp('2026-09-19T03:30:00Z')
    runtime.clock = lambda: boundary + pd.Timedelta(seconds=29.9)
    runtime.controller.poll = lambda now: 'RUNNING'
    runtime.controller.state['watermark'] = None
    runtime.controller.signals = SimpleNamespace(due=lambda b: ('5m',))
    runtime.engine.adapter = SimpleNamespace(
        fetch_ohlcv=lambda symbol, tf, limit: object(),
        fetch_volume_sources=lambda symbol, tf, limit: object(),
    )
    runtime.controller.step = lambda *args: (_ for _ in ()).throw(
        __import__('universal_bot.priority_signals', fromlist=['DataUnavailable']).DataUnavailable(
            '5m: missing completed OHLCV bars'
        )
    )
    mono = iter([100.0, 100.2, 100.2, 100.2])
    monkeypatch.setattr(
        'universal_bot.priority_runtime.time.monotonic',
        lambda: next(mono, 100.2),
    )
    monkeypatch.setattr('universal_bot.priority_runtime.time.sleep', lambda seconds: None)

    status = runtime.scan_once()
    assert status.startswith('DATA_BLOCKED:')
    assert runtime.controller.state['halted'] is None
