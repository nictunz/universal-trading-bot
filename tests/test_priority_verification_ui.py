import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from universal_bot.dashboard import _one
from universal_bot.live_safety import LiveSafety
from universal_bot.priority_signals import Candidate, COMMON, PROFILES


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1]/path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_priority_position_shown_without_legacy_state():
    safety = LiveSafety(enabled=True)
    verified = dict(side='LONG', size=2, entry=100, tp=103, sl=99)
    runtime = SimpleNamespace(symbol='BTC/USDT:USDT', last_error='', engine=SimpleNamespace(
        last_state=None, safety=safety, adapter=object(), priority_snapshot=dict(
            owner='5m', position=verified, status='OPENED_5m', halted=None,
            watermark='2026-09-16T00:00:00Z')))
    payload = _one(runtime)
    assert payload['position'] == verified
    assert payload['timeframe'] == '5m + 15m'
    runtime.engine.priority_snapshot.update(position=None, halted='position mismatch')
    payload = _one(runtime)
    assert payload['position']['side'] == 'UNKNOWN'
    assert payload['live_safety']['halted'] is True
    assert payload['live_safety']['reason'] == 'position mismatch'


def test_profile_presets_follow_production_settings():
    bridge = module('android/app/src/main/python/mobile_bridge.py', 'priority_mobile_bridge')
    for tf, values in PROFILES.items():
        payload = json.loads(bridge.priority_profile_preset(tf))
        params = payload['items'][0]['parameters']
        for key, value in dict(COMMON, **values).items():
            assert params[key] == value
        assert params['entry_multiplier'] == values['live_entry_multiplier']
        assert payload['execution_model'] == 'signal_close'
        assert payload['items'][0]['source_context']['scope'] == 'single_timeframe_only'
    with pytest.raises(ValueError):
        bridge.priority_profile_preset('1m')


def test_replay_preemption_costs_and_no_same_bar_exit():
    replay = module('scripts/verify_priority_backtest.py', 'priority_replay')
    start = pd.Timestamp('2026-01-01T00:00Z')
    idx = pd.date_range(start, periods=4, freq='5min')
    frame = pd.DataFrame(dict(open=100., high=100.1, low=99.9, close=100., volume=1.), index=idx)
    a, b = idx[1], idx[2]
    candidates = {a: [Candidate('15m', a-pd.Timedelta('15m'), 'LONG', 100, 3, 2, 5)],
                  b: [Candidate('5m', b-pd.Timedelta('5m'), 'SHORT', 100, 3, 2, 9.55)]}
    # Entry candle crosses both protection prices: neither existed before entry.
    frame.loc[idx[0], ['high','low']] = [110, 90]
    result = replay.replay(frame, candidates, a)
    assert [t['owner'] for t in result['trades']] == ['15m','5m']
    assert [t['reason'] for t in result['trades']] == ['PREEMPTED_BY_5M','END_OF_DATA']
    assert result['summary']['final_equity'] == pytest.approx(1000*(1-5*.0006)*(1-9.55*.0006))


def test_replay_sl_first_and_adverse_gap():
    replay = module('scripts/verify_priority_backtest.py', 'priority_replay_gap')
    idx = pd.date_range('2026-01-01', periods=2, freq='5min', tz='UTC')
    frame = pd.DataFrame(dict(open=[100.,97.], high=[101.,104.], low=[99.,96.],
                              close=[100.,100.], volume=1.), index=idx)
    b = idx[1]
    candidates = {b:[Candidate('5m',idx[0],'LONG',100,3,2,9.55)]}
    result = replay.replay(frame,candidates,b)
    assert result['trades'][0]['reason'] == 'SL'
    assert result['trades'][0]['exit_price'] == 97
