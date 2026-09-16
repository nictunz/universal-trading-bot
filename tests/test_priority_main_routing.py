from types import SimpleNamespace
import sys

import pytest

sys.modules.setdefault('uvicorn', SimpleNamespace(run=lambda *a, **k: None))
import universal_bot.main as main


def settings(mode='LIVE', symbols=None):
    return SimpleNamespace(bot_mode=mode, symbol_list=symbols or ['BTC/USDT:USDT'],
        poll_seconds=1, timeframe='15m', exchange='bitget', bitget_execution_profile='elite')


def test_priority_flag_rejects_non_live(monkeypatch):
    monkeypatch.setenv('PRIORITY_LIVE_ENABLED', '1')
    with pytest.raises(RuntimeError, match='requires LIVE'):
        main._runtime_worker(SimpleNamespace(runtimes=[]), settings('PAPER'))


def test_priority_flag_rejects_multiple_symbols(monkeypatch):
    monkeypatch.setenv('PRIORITY_LIVE_ENABLED', '1')
    with pytest.raises(RuntimeError, match='exactly BTC'):
        main._runtime_worker(SimpleNamespace(runtimes=[]),
                             settings(symbols=['BTC/USDT:USDT', 'ETH/USDT:USDT']))
