"""Deploy an explicitly reviewed source snapshot without changing LIVE settings.

Run only on the existing trading-bot runner. Position checks are read-only;
this script does not submit, cancel, or alter any exchange order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

SOURCE_FILES = (
    'universal_bot/config.py', 'universal_bot/engine.py', 'universal_bot/main.py',
    'universal_bot/runtime_engine.py', 'universal_bot/adapters/bitget_elite.py',
    'universal_bot/providers/mobile_relay.py', 'universal_bot/trade_history.py',
    'universal_bot/dashboard.py',
)
SERVICE = 'universal-trading-bot-dashboard.service'


def hashes(root):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def atomic_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.reviewed-upload')
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def check_runtime(before, after, expected, commit):
    assert after['health']['status'] == 'ok', 'health is not OK'
    assert after['ready'].get('ready') is True, 'LIVE is not ready'
    info = after['runtime']
    assert info.get('source_files') == expected, 'running source hashes differ'
    assert info.get('source_matches_disk') is True, 'process/disk source mismatch'
    assert info.get('deployment_verified') is True, 'deployment manifest mismatch'
    assert info.get('deployment_commit') == commit, 'wrong deployment commit'
    assert info['process_started_at'] != before['runtime'].get('process_started_at'), 'process did not restart'
    assert info.get('runtimes') == before['runtime'].get('runtimes'), 'runtime strategy or execution settings changed'


CAPTURE = r'''
import json, requests
from universal_bot.config import Settings
s=Settings()
assert s.dashboard_auth_enabled and s.dashboard_username and s.dashboard_password
session=requests.Session()
r=session.post('http://127.0.0.1:8000/login', data={'username':s.dashboard_username,'password':s.dashboard_password,'next':'/'}, allow_redirects=False, timeout=10)
assert r.status_code == 303, 'login failed'
out={}
for key,path in [('health','/health'),('ready','/api/live-readiness'),('runtime','/api/runtime-info'),('state','/api/state')]:
 r=session.get('http://127.0.0.1:8000'+path,timeout=10); r.raise_for_status(); out[key]=r.json()
print(json.dumps(out))
'''
FLAT = r'''
import json
from universal_bot.config import Settings
from universal_bot.main import build_adapter
s=Settings()
assert s.bot_mode.upper() == 'LIVE', 'expected existing LIVE runtime'
a=build_adapter(s)
for symbol in s.symbol_list:
 p=a.position(symbol)
 assert p.get('side')=='FLAT' and float(p.get('size') or 0)<=1e-9, 'open position: deployment postponed'
print('READ_ONLY_FLAT_CONFIRMED')
'''


def deploy(source, app, python, commit):
    expected = hashes(source)
    def run_runtime(code, capture=False):
        result = subprocess.run([str(python), '-c', code], cwd=app, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        if result.returncode:
            # Raw output may include account details; retain it off the CI log.
            raise RuntimeError('runtime read-only check failed (details withheld)')
        return json.loads(result.stdout.strip().splitlines()[-1]) if capture else None
    def service(action):
        subprocess.run(['sudo', 'systemctl', action, SERVICE], check=True, timeout=90)
    relay = Path('/home/kpj3669/.cache/universal-trading-bot/mobile-market-relay.json')
    assert relay.is_file() and time.time()-relay.stat().st_mtime <= 90, 'market relay stale; deployment postponed'
    before = run_runtime(CAPTURE, True)
    assert before['health']['status'] == 'ok' and before['ready'].get('ready') is True, 'existing runtime is not ready'
    assert before['runtime'].get('runtimes'), 'no running symbols'
    run_runtime(FLAT)
    backup = app / 'data/deploy-backups' / commit
    backup.mkdir(parents=True, exist_ok=False)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=app, text=True, capture_output=True, check=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--short'], cwd=app, text=True, capture_output=True, check=True).stdout
    (backup / 'before.json').write_text(json.dumps({'head':head,'dirty':dirty,'runtime':before['runtime'],'files':hashes(app)},indent=2))
    print(json.dumps({'server_head_before':head,'source_before':before['runtime'].get('source_fingerprint'),'target_commit':commit}),flush=True)
    manifest_path = app / 'data/deployment-manifest.json'
    backup_files = list(SOURCE_FILES) + ['data/deployment-manifest.json', '.env', 'data/dashboard-strategy-settings.json']
    for name in backup_files:
        if (app / name).exists():
            atomic_copy(app / name, backup / name)
    changed = False
    try:
        service('stop')
        run_runtime(FLAT)  # Repeat after stopping to close the signal race.
        for name in SOURCE_FILES:
            changed = True
            atomic_copy(source / name, app / name)
        manifest_path.write_text(json.dumps({'commit':commit,'files':expected,'created_at':time.time()},indent=2))
        service('start')
        deadline = time.monotonic() + 180
        last_error = 'runtime did not start'
        while time.monotonic() < deadline:
            try:
                after = run_runtime(CAPTURE, True)
                check_runtime(before, after, expected, commit)
                (backup / 'after.json').write_text(json.dumps(after['runtime'],indent=2))
                print(json.dumps({'deployment':'verified','server_head':after['runtime']['server_commit'],
                                  'deployment_commit':commit,'source_fingerprint':after['runtime']['source_fingerprint'],
                                  'source_matches_disk':True,'settings_preserved':True}),flush=True)
                return
            except Exception as exc:
                last_error = str(exc)
                time.sleep(2)
        raise RuntimeError(last_error)
    except Exception:
        if changed:
            service('stop')
            try:
                run_runtime(FLAT)
            except Exception:
                # Never swap runtime code around an open/unknown position.
                service('start')
                print('Rollback withheld: exchange is not confirmed flat; existing new runtime restarted.',flush=True)
                raise
            for name in SOURCE_FILES:
                atomic_copy(backup / name, app / name)
            if (backup / 'data/deployment-manifest.json').exists():
                atomic_copy(backup / 'data/deployment-manifest.json', manifest_path)
            else:
                manifest_path.unlink(missing_ok=True)
            print('Previous runtime files restored.',flush=True)
        service('start')
        raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--app',type=Path,default=Path('/home/kpj3669/universal-trading-bot'))
    parser.add_argument('--python',type=Path,default=Path('/home/kpj3669/.cache/universal-trading-bot-dashboard-venv/bin/python'))
    parser.add_argument('--commit',required=True)
    args=parser.parse_args()
    deploy(args.source.resolve(),args.app.resolve(),args.python,args.commit)
