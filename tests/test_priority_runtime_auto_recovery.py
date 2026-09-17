from types import SimpleNamespace

from universal_bot.priority_runtime import PriorityRuntime


class Adapter:
    def __init__(self, position=None, fail_data=False):
        self._position = position or {'side': 'FLAT', 'size': 0.0}
        self.fail_data = fail_data

    def fetch_ohlcv(self, symbol, timeframe, limit=500):
        if self.fail_data:
            raise RuntimeError('mobile relay is stale: age=120s max=90s')
        return object()

    def fetch_volume_sources(self, symbol, timeframe, limit=500):
        if self.fail_data:
            raise RuntimeError('mobile relay is stale: age=120s max=90s')
        return object()

    def position(self, symbol):
        return dict(self._position)


def make_runtime(reason, *, position=None, safety_reason=None, owner=None, pending=None):
    runtime = PriorityRuntime.__new__(PriorityRuntime)
    saved = []
    notifications = []
    safety = SimpleNamespace(
        halted=bool(safety_reason), reason=safety_reason or '',
        consecutive_errors=0, protection_ok=True,
    )
    runtime.engine = SimpleNamespace(
        settings=SimpleNamespace(symbol='BTC/USDT:USDT'),
        adapter=Adapter(position), safety=safety,
        _notify_live=lambda *args, **kwargs: notifications.append((args, kwargs)),
    )
    state = {'halted': reason, 'owner': owner, 'position': None, 'pending': pending}
    runtime.controller = SimpleNamespace(
        state=state,
        journal=SimpleNamespace(save=lambda value: saved.append(dict(value))),
    )
    runtime._data_recovery_confirmations = 0
    runtime._data_blocked_count = 0
    runtime._data_blocked_since = None
    runtime._alert_key = None
    return runtime, saved, notifications


def test_running_data_halt_requires_three_healthy_flat_confirmations():
    reason = 'data unavailable for 25.0s: mobile relay is stale: age=146.9s max=90s'
    mirrored = 'PRIORITY_RUNTIME_HALTED: ' + reason
    runtime, saved, notifications = make_runtime(reason, safety_reason=mirrored)

    assert runtime._recover_running_data_halt() is False
    assert runtime._recover_running_data_halt() is False
    assert runtime.controller.state['halted'] == reason
    assert runtime.engine.safety.halted is True

    assert runtime._recover_running_data_halt() is True
    assert runtime.controller.state['halted'] is None
    assert runtime.engine.safety.halted is False
    assert runtime.engine.safety.reason == ''
    assert saved[-1]['halted'] is None
    assert notifications[-1][0][0] == '🟢 LIVE 데이터 HALT 자동복구'


def test_running_data_halt_never_recovers_with_live_position():
    reason = 'data unavailable for 25.0s: mobile relay is stale: age=146.9s max=90s'
    runtime, saved, _ = make_runtime(
        reason,
        position={'side': 'LONG', 'size': 0.01},
        safety_reason='PRIORITY_RUNTIME_HALTED: ' + reason,
    )

    for _ in range(5):
        assert runtime._recover_running_data_halt() is False
    assert runtime.controller.state['halted'] == reason
    assert saved == []


def test_running_data_halt_never_clears_unrelated_safety_halt():
    reason = 'data unavailable for 25.0s: mobile relay is stale: age=146.9s max=90s'
    runtime, saved, _ = make_runtime(reason, safety_reason='POSITION_MISMATCH')

    for _ in range(5):
        assert runtime._recover_running_data_halt() is False
    assert runtime.controller.state['halted'] == reason
    assert runtime.engine.safety.reason == 'POSITION_MISMATCH'
    assert saved == []


def test_running_data_halt_never_recovers_pending_operation():
    reason = 'data unavailable for 25.0s: mobile relay is stale: age=146.9s max=90s'
    runtime, saved, _ = make_runtime(
        reason,
        safety_reason='PRIORITY_RUNTIME_HALTED: ' + reason,
        pending='open_5m',
    )

    for _ in range(5):
        assert runtime._recover_running_data_halt() is False
    assert runtime.controller.state['halted'] == reason
    assert saved == []
