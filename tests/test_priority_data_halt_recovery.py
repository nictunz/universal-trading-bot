import fcntl
import json
import sqlite3
import time

import pytest

from scripts.recover_priority_data_halt import recover, RECOVERABLE_HALTS
from universal_bot.priority_signals import profile_hash


def write_relay(path, tf):
    now = int(time.time() * 1000)
    path.write_text(json.dumps({
        'schema_version': 1,
        'timeframe': tf,
        'generated_at_ms': now,
        'snapshot_completed_at_ms': now,
    }))


def write_state(path, **updates):
    state = dict(profile=profile_hash(), owner=None, position=None, history={},
                 pending=None, halted=next(iter(RECOVERABLE_HALTS)), watermark='2026-09-16T13:10:00+00:00')
    state.update(updates)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE priority_state(id INTEGER PRIMARY KEY, body TEXT)')
    db.execute('INSERT INTO priority_state VALUES(1,?)', (json.dumps(state),))
    db.commit(); db.close()
    return state


def read_state(path):
    db = sqlite3.connect(path)
    row = db.execute('SELECT body FROM priority_state WHERE id=1').fetchone()
    db.close()
    return json.loads(row[0])


def setup_files(tmp_path, **state_updates):
    state = tmp_path/'priority-live.sqlite'
    relay = tmp_path/'mobile-market-relay.json'
    write_state(state, **state_updates)
    write_relay(relay, '15m')
    write_relay(tmp_path/'mobile-market-relay-5m.json', '5m')
    return state, relay


def test_dry_run_never_changes_state(tmp_path):
    state, relay = setup_files(tmp_path)
    before = read_state(state)
    out = recover(state, relay, 90, False)
    assert out['ok'] and not out['changed']
    assert read_state(state) == before


def test_apply_clears_only_allowlisted_halt_and_preserves_watermark(tmp_path):
    state, relay = setup_files(tmp_path)
    out = recover(state, relay, 90, True)
    after = read_state(state)
    assert out['changed'] is True
    assert after['halted'] is None
    assert after['watermark'] == '2026-09-16T13:10:00+00:00'
    assert after['owner'] is None and after['position'] is None and after['pending'] is None
    backup = out['backup']
    assert backup
    assert read_state(backup)['halted'] in RECOVERABLE_HALTS


def test_refuses_when_priority_journal_lock_is_held(tmp_path):
    state, relay = setup_files(tmp_path)
    lock = open(str(state)+'.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(RuntimeError, match='journal is in use'):
            recover(state, relay, 90, True)
        assert read_state(state)['halted'] in RECOVERABLE_HALTS
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


@pytest.mark.parametrize('updates', [
    {'owner': '15m'},
    {'position': {'side': 'LONG'}},
    {'pending': 'open_5m'},
    {'halted': 'partial close; entry blocked'},
    {'profile': 'changed'},
])
def test_refuses_ambiguous_or_execution_state(tmp_path, updates):
    state, relay = setup_files(tmp_path, **updates)
    before = read_state(state)
    with pytest.raises(RuntimeError):
        recover(state, relay, 90, True)
    assert read_state(state) == before


def test_refuses_stale_or_missing_5m_relay(tmp_path):
    state, relay = setup_files(tmp_path)
    sidecar = tmp_path/'mobile-market-relay-5m.json'
    sidecar.unlink()
    with pytest.raises(RuntimeError, match='relay missing'):
        recover(state, relay, 90, True)
    assert read_state(state)['halted'] is not None
