import copy
import pandas as pd
import pytest

from universal_bot.priority_signals import DualTimeframeSignals, DataUnavailable, EXCHANGES, profile_settings
from universal_bot.priority_shadow import PriorityShadowMonitor, ShadowJournal

B = pd.Timestamp('2026-09-16T00:15:00Z')


def inputs(boundary=B):
    frames, volumes = {}, {}
    for tf in ('5m', '15m'):
        index = pd.date_range(end=boundary-pd.Timedelta(tf), periods=240, freq=pd.Timedelta(tf))
        closes = [100 + (0.03 if i % 2 else -0.03) for i in range(240)]
        frames[tf] = pd.DataFrame(dict(open=100., high=100.5, low=99.5,
            close=closes, volume=100.), index=index)
        volumes[tf] = {ex: pd.Series(100., index=index) for ex in EXCHANGES}
    return frames, volumes


def test_profile_isolates_server_settings(monkeypatch):
    monkeypatch.setenv('VOLUME_LOOKBACK', '41')
    monkeypatch.setenv('BOT_MODE', 'LIVE')
    monkeypatch.setenv('REENTRY_BARS', '7')
    s = profile_settings('15m')
    assert (s.volume_lookback, s.reentry_bars, s.max_nbar_volatility,
            s.rsi_oversold_max, s.live_entry_multiplier, s.bot_mode) == (40, 5, 6.3, 42., 5., 'PAPER')
    assert profile_settings('5m').live_entry_multiplier == 9.55


def test_both_confirmed_and_future_rows_ignored():
    frames, volumes = inputs()
    evaluator = DualTimeframeSignals()
    before = evaluator.evaluate(frames, volumes, B, B)
    for tf in frames:
        for offset in (0, 1):
            frames[tf].loc[B+pd.Timedelta(tf)*offset] = [1, 2, 0.1, 1, 1e12]
    assert evaluator.evaluate(frames, volumes, B, B) == before
    assert set(before[1]) == {'5m', '15m'}


@pytest.mark.parametrize('fault', ['missing_exchange','missing_volume_bar','negative_volume',
    'nan_volume','missing_price_bar','duplicate_price','bad_high','naive_index','infinite_price'])
def test_bad_data_blocks_entire_boundary(fault):
    frames, volumes = inputs()
    # A 15m defect must also withhold 5m evaluation at a shared boundary.
    f, v = frames['15m'], volumes['15m']
    if fault == 'missing_exchange': del v['okx']
    elif fault == 'missing_volume_bar': v['okx'] = v['okx'].iloc[:-1]
    elif fault == 'negative_volume': v['okx'].iloc[-1] = -1
    elif fault == 'nan_volume': v['okx'].iloc[-1] = float('nan')
    elif fault == 'missing_price_bar': frames['15m'] = f.drop(f.index[-20])
    elif fault == 'duplicate_price': frames['15m'] = pd.concat([f, f.iloc[-1:]])
    elif fault == 'bad_high': f.loc[f.index[-1], 'high'] = 99
    elif fault == 'naive_index': f.index = f.index.tz_localize(None)
    else: f.loc[f.index[-1], 'close'] = float('inf')
    with pytest.raises(DataUnavailable): DualTimeframeSignals().evaluate(frames, volumes, B, B)


@pytest.mark.parametrize('seconds', [-1, 31])
def test_unconfirmed_or_late_boundary(seconds):
    f, v = inputs()
    with pytest.raises(DataUnavailable):
        DualTimeframeSignals().evaluate(f, v, B, B+pd.Timedelta(seconds=seconds))


def test_five_only_boundary():
    b = B+pd.Timedelta(minutes=5)
    f, v = inputs(b)
    candidates, diagnostics = DualTimeframeSignals().evaluate({'5m': f['5m']}, {'5m': v['5m']}, b, b)
    assert list(diagnostics) == ['5m']


def test_real_strategy_candidates_and_cooldown(monkeypatch):
    f, v = inputs()
    # RSI is fixed only to isolate signal-boundary wiring; all other calculations
    # use the real v15 strategy and four independently normalized volumes.
    monkeypatch.setattr('universal_bot.strategy.v15.rsi', lambda close, n: pd.Series(30., index=close.index))
    for tf in f:
        f[tf].loc[f[tf].index[-1], 'close'] = 99.8
        for s in v[tf].values(): s.iloc[-1] = 10000
    evaluator = DualTimeframeSignals()
    candidates, _ = evaluator.evaluate(f, v, B, B)
    assert [(s.owner, s.side, s.multiplier) for s in candidates] == [('5m','LONG',9.55),('15m','LONG',5.)]
    assert [s.opened_at for s in candidates] == [B-pd.Timedelta('5min'), B-pd.Timedelta('15min')]
    history = {'5m': {'entry': B-pd.Timedelta(minutes=5)}, '15m': {'exit': B}}
    assert evaluator.evaluate(f, v, B, B, history)[0] == []


class PublicData:
    def __init__(self, f, v): self.f, self.v, self.calls = f, v, []
    def fetch_ohlcv(self, symbol, tf, limit):
        self.calls.append(('prices', tf)); return self.f[tf]
    def fetch_volume_sources(self, symbol, tf, limit):
        self.calls.append(('volume', tf)); return self.v[tf]


def test_journal_restart_deduplicates_without_fetch(tmp_path):
    f, v = inputs()
    data = PublicData(f, v)
    path = tmp_path/'shadow.sqlite'
    journal = ShadowJournal(path)
    monitor = PriorityShadowMonitor(data, journal, clock=lambda:B)
    assert monitor.scan(B)['status'] == 'OBSERVED'
    journal.close()
    count = len(data.calls)
    journal = ShadowJournal(path)
    assert PriorityShadowMonitor(data, journal, clock=lambda:B).scan(B)['status'] == 'DUPLICATE'
    assert len(data.calls) == count
    journal.close()


def test_missing_data_can_retry_same_boundary(tmp_path):
    f, v = inputs()
    removed = v['15m'].pop('okx')
    journal = ShadowJournal(tmp_path/'shadow.sqlite')
    monitor = PriorityShadowMonitor(PublicData(f,v), journal, clock=lambda:B)
    with pytest.raises(DataUnavailable): monitor.scan(B)
    assert not journal.contains(B)
    v['15m']['okx'] = removed
    assert monitor.scan(B)['status'] == 'OBSERVED'
    journal.close()


def test_fetch_finishing_too_late_never_records(tmp_path):
    f, v = inputs()
    times = iter([B, B, B+pd.Timedelta(seconds=31)])
    journal = ShadowJournal(tmp_path/'shadow.sqlite')
    monitor = PriorityShadowMonitor(PublicData(f,v), journal, clock=lambda:next(times))
    with pytest.raises(DataUnavailable): monitor.scan(B)
    assert not journal.contains(B)
    journal.close()
