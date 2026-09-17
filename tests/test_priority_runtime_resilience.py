from types import SimpleNamespace

import pandas as pd

from universal_bot.priority_runtime import PriorityRuntime


class FakeController:
    def __init__(self):
        self.state = {'halted': None, 'owner': None, 'pending': None}

    def halt(self, reason):
        self.state['halted'] = reason
        return 'HALTED'


def runtime_stub():
    runtime = PriorityRuntime.__new__(PriorityRuntime)
    runtime.engine = SimpleNamespace(
        settings=SimpleNamespace(symbol='BTC/USDT:USDT'),
        _notify_live=lambda *args, **kwargs: None,
    )
    runtime.controller = FakeController()
    runtime.last_status = 'ATTACHED'
    runtime._data_blocked_count = 0
    runtime._data_blocked_since = None
    runtime._alert_key = None
    return runtime


def test_mobile_relay_missing_is_transient_data_error():
    exc = RuntimeError(
        'mobile relay snapshot not found: /tmp/mobile-market-relay-5m.json'
    )
    assert PriorityRuntime._is_transient_data_error(exc)


def test_transient_gap_blocks_without_immediate_halt():
    runtime = runtime_stub()
    start = pd.Timestamp('2026-09-17T01:00:00Z')

    status = runtime._data_blocked('mobile relay snapshot not found: /tmp/relay.json', start)
    assert status.startswith('DATA_BLOCKED:')
    assert runtime.controller.state['halted'] is None

    status = runtime._data_blocked(
        'mobile relay snapshot not found: /tmp/relay.json',
        start + pd.Timedelta(seconds=14),
    )
    assert status.startswith('DATA_BLOCKED:')
    assert runtime.controller.state['halted'] is None


def test_persistent_gap_halts_after_safety_window():
    runtime = runtime_stub()
    start = pd.Timestamp('2026-09-17T01:00:00Z')
    reason = 'mobile relay snapshot not found: /tmp/relay.json'

    runtime._data_blocked(reason, start)
    status = runtime._data_blocked(reason, start + pd.Timedelta(seconds=15))

    assert status == 'HALTED'
    assert runtime.controller.state['halted'].startswith('data unavailable for 15.0s:')


def test_healthy_data_resets_gap_state():
    runtime = runtime_stub()
    start = pd.Timestamp('2026-09-17T01:00:00Z')
    runtime._data_blocked('missing completed OHLCV bars', start)

    runtime._healthy('NO_ELIGIBLE_SIGNAL')

    assert runtime._data_blocked_count == 0
    assert runtime._data_blocked_since is None
