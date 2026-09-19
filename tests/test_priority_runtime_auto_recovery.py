from types import SimpleNamespace

from universal_bot.priority_runtime import PriorityRuntime


class Adapter:
    def __init__(self, position=None, fail_data=False, api_family='classic-v2'):
        self._position = position or {'side': 'FLAT', 'size': 0.0}
        self.fail_data = fail_data
        self.API_FAMILY = api_family

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


def make_runtime(reason, *, position=None, safety_reason=None, owner=None, pending=None, api_family='classic-v2'):
    runtime = PriorityRuntime.__new__(PriorityRuntime)
    saved = []
    notifications = []
    safety = SimpleNamespace(halted=bool(safety_reason), reason=safety_reason or '',
                             consecutive_errors=0, protection_ok=True)
    runtime.engine = SimpleNamespace(
        settings=SimpleNamespace(symbol='BTC/USDT:USDT'), adapter=Adapter(position, api_family=api_family), safety=safety,
        _notify_live=lambda *args, **kwargs: notifications.append((args, kwargs)),
    )
    state = {'halted': reason, 'owner': owner, 'position': None, 'pending': pending}
    runtime.controller = SimpleNamespace(state=state,
        journal=SimpleNamespace(save=lambda value: saved.append(dict(value))))
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
    assert saved[-1]['halted'] is None
    assert notifications[-1][0][0] == '🟢 LIVE 데이터 HALT 자동복구'


def test_running_data_halt_never_recovers_with_live_position():
    reason = 'data unavailable for 25.0s: mobile relay is stale: age=146.9s max=90s'
    runtime, saved, _ = make_runtime(reason, position={'side': 'LONG', 'size': 0.01},
                                     safety_reason='PRIORITY_RUNTIME_HALTED: ' + reason)
    for _ in range(5): assert runtime._recover_running_data_halt() is False
    assert runtime.controller.state['halted'] == reason
    assert saved == []


def test_running_data_halt_never_clears_unrelated_safety_halt():
    reason = 'data unavailable for 25.0s: mobile relay is stale: age=146.9s max=90s'
    runtime, saved, _ = make_runtime(reason, safety_reason='POSITION_MISMATCH')
    for _ in range(5): assert runtime._recover_running_data_halt() is False
    assert runtime.controller.state['halted'] == reason
    assert runtime.engine.safety.reason == 'POSITION_MISMATCH'
    assert saved == []


def test_running_data_halt_never_recovers_pending_operation():
    reason = 'data unavailable for 25.0s: mobile relay is stale: age=146.9s max=90s'
    runtime, saved, _ = make_runtime(reason, safety_reason='PRIORITY_RUNTIME_HALTED: ' + reason,
                                     pending='open_5m')
    for _ in range(5): assert runtime._recover_running_data_halt() is False
    assert runtime.controller.state['halted'] == reason
    assert saved == []


def market_timeout_reason():
    return ('RequestTimeout: bitget GET https://api.bitget.com/api/v2/mix/market/candles?'
            'symbol=BTCUSDT&granularity=5m&limit=500&productType=USDT-FUTURES')


def test_bitget_market_candles_request_timeout_is_transient_data_error():
    assert PriorityRuntime._is_transient_data_error(RuntimeError(market_timeout_reason())) is True


def test_legacy_market_timeout_halt_is_recoverable_reason():
    assert PriorityRuntime._is_recoverable_data_halt_reason(market_timeout_reason()) is True


def test_legacy_market_timeout_requires_three_healthy_flat_confirmations():
    reason = market_timeout_reason()
    runtime, saved, _ = make_runtime(reason, safety_reason='PRIORITY_RUNTIME_HALTED: ' + reason)
    assert runtime._recover_running_data_halt() is False
    assert runtime._recover_running_data_halt() is False
    assert runtime.controller.state['halted'] == reason
    assert runtime._recover_running_data_halt() is True
    assert runtime.controller.state['halted'] is None
    assert saved[-1]['halted'] is None


def test_order_request_timeout_remains_fail_closed():
    reason = 'RequestTimeout: bitget POST https://api.bitget.com/api/v2/mix/order/place-order'
    assert PriorityRuntime._is_transient_data_error(RuntimeError(reason)) is False
    assert PriorityRuntime._is_recoverable_data_halt_reason(reason) is False


def test_position_request_timeout_remains_fail_closed():
    reason = 'RequestTimeout: bitget GET https://api.bitget.com/api/v2/mix/position/single-position'
    assert PriorityRuntime._is_transient_data_error(RuntimeError(reason)) is False
    assert PriorityRuntime._is_recoverable_data_halt_reason(reason) is False


def test_account_request_timeout_remains_fail_closed():
    reason = 'RequestTimeout: bitget GET https://api.bitget.com/api/v2/mix/account/account'
    assert PriorityRuntime._is_transient_data_error(RuntimeError(reason)) is False
    assert PriorityRuntime._is_recoverable_data_halt_reason(reason) is False


def classic_40037_reason():
    return 'Bitget Elite API error HTTP 400 40037: Apikey does not exist'


def test_persisted_classic_40037_recovers_only_on_uta_v3_flat():
    runtime, saved, _ = make_runtime(classic_40037_reason(), api_family='uta-v3')
    assert runtime._recover_persisted_data_halt() is True
    assert runtime.controller.state['halted'] is None
    assert saved[-1]['halted'] is None


def test_persisted_classic_40037_stays_halted_on_classic_adapter():
    runtime, saved, _ = make_runtime(classic_40037_reason(), api_family='classic-v2')
    assert runtime._recover_persisted_data_halt() is False
    assert runtime.controller.state['halted'] == classic_40037_reason()
    assert saved == []


def test_persisted_classic_40037_stays_halted_with_position_or_pending():
    runtime, saved, _ = make_runtime(
        classic_40037_reason(), api_family='uta-v3',
        position={'side': 'LONG', 'size': 0.01}
    )
    assert runtime._recover_persisted_data_halt() is False
    assert saved == []

    runtime, saved, _ = make_runtime(
        classic_40037_reason(), api_family='uta-v3', pending='open_5m'
    )
    assert runtime._recover_persisted_data_halt() is False
    assert saved == []
