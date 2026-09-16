import pandas as pd
import pytest
import socket

from test_priority_signals import inputs, B
from universal_bot.priority_paper_runtime import PaperPriorityRuntime


@pytest.fixture
def paper(tmp_path, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('paper test attempted network access')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket.socket, 'connect_ex', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)
    monkeypatch.setattr('universal_bot.strategy.v15.rsi',
                        lambda close, n: pd.Series(30., index=close.index))
    runtime = PaperPriorityRuntime(tmp_path / 'paper.sqlite')
    yield runtime
    runtime.close()


def feed(runtime, at, active=()):
    f, v = inputs(at)
    for tf in active:
        f[tf].loc[f[tf].index[-1], ['open', 'close']] = [100.2, 100.]
        for series in v[tf].values():
            series.iloc[-1] = 10000
    return runtime.step(f, v, at, at)


def test_priority_and_fixed_prices(paper):
    assert feed(paper, B, ['5m', '15m']) == 'OPENED_5m'
    p = paper.snapshot()['position']
    assert p['size'] == pytest.approx(95.5)
    assert paper.snapshot()['equity'] == pytest.approx(997.135)
    assert paper.snapshot()['real_orders_enabled'] is False
    feed(paper, B + pd.Timedelta(minutes=5))
    assert paper.snapshot()['position'] == p


def test_preemption(paper):
    assert feed(paper, B, ['15m']) == 'OPENED_15m'
    assert feed(paper, B + pd.Timedelta(minutes=5), ['5m']) == 'OPENED_5m'
    assert [e['kind'] for e in paper.snapshot()['events']] == ['PAPER_OPEN', 'PAPER_CLOSE', 'PAPER_OPEN']


def test_restart_restores_position(paper):
    feed(paper, B, ['15m'])
    previous = paper.snapshot()
    path = paper.journal.db.execute('PRAGMA database_list').fetchone()[2]
    paper.close()
    other = PaperPriorityRuntime(path)
    assert other.snapshot() == previous
    assert feed(other, B, ['5m']) == 'DUPLICATE_OR_OLD'
    paper.journal = other.journal


def test_missing_candle_halts(paper):
    feed(paper, B, ['5m'])
    assert feed(paper, B + pd.Timedelta(minutes=10)) == 'HALTED'
    assert paper.snapshot()['position'] is not None


def test_missing_source_no_mutation(paper):
    f, v = inputs(B)
    del v['5m']['binance']
    with pytest.raises(ValueError):
        paper.step(f, v, B, B)
    assert not paper.snapshot()['events']


def test_same_candle_both_touch_sl_first(paper):
    feed(paper, B, ['5m'])
    at = B + pd.Timedelta(minutes=5)
    f, v = inputs(at)
    f['5m'].loc[B, ['high', 'low']] = [105., 95.]
    paper.step(f, v, at, at)
    assert paper.snapshot()['position'] is None
    assert paper.snapshot()['events'][-1]['reason'] == 'SL'
