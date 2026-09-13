import sqlite3
from datetime import datetime, timezone

import pytest

from universal_bot import local_cache_core as core
from universal_bot.historical import HistoricalDataManager


def source(root):
    path=root/'imported.db'
    manager=HistoricalDataManager('sqlite:///'+str(path),fallback_exchanges=[])
    first=int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp()*1000)
    with sqlite3.connect(path) as db:
        for ex in core.EXCHANGES:
            db.executemany('INSERT INTO ohlcv VALUES(?,?,?,?,?,?,?,?,?,?)',
                [('crypto',ex,'BTC/USDT:USDT','1h',first+i*3600000,100,101,99,100,10) for i in range(24)])
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    db.close()
    return path


def test_reuse_complete_db_without_network_or_source_changes(tmp_path,monkeypatch):
    original=source(tmp_path);before=original.read_bytes()
    monkeypatch.setattr(core,'_sync_with_retry',lambda *args:pytest.fail('Complete DB must not download'))
    path,_,summary=core.build_cache_and_backtest('BTC/USDT:USDT','1h','2025-01-01','2025-01-01',tmp_path,lambda _:None,run_backtest=False,reuse_existing=True)
    assert path!=original and summary['bars']==96
    assert original.read_bytes()==before


def test_incomplete_cached_edges_are_not_marked_complete(tmp_path,monkeypatch):
    original=source(tmp_path)
    with sqlite3.connect(original) as db:
        db.execute("DELETE FROM ohlcv WHERE exchange='okx' AND timestamp=(SELECT max(timestamp) FROM ohlcv)")
    calls=[]
    def unavailable(manager,request,log):
        calls.append(request.exchange)
        return 0,manager.read(request)
    monkeypatch.setattr(core,'_sync_with_retry',unavailable)
    with pytest.raises(RuntimeError,match='요청 기간 데이터 부족'):
        core.build_cache_and_backtest('BTC/USDT:USDT','1h','2025-01-01','2025-01-01',tmp_path,lambda _:None,run_backtest=False,reuse_existing=True)
    assert calls==['okx']
