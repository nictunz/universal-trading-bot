from copy import deepcopy
from pathlib import Path
import importlib.util

import pytest

from universal_bot import dashboard

spec = importlib.util.spec_from_file_location('reviewed_deploy', Path(__file__).resolve().parents[1] / 'scripts/deploy_reviewed_runtime.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def test_deployment_requires_new_process_exact_source_and_unchanged_settings():
    before = {'runtime': {'process_started_at': 'old', 'runtimes': [{'mode': 'LIVE', 'execution': {'multiplier': 8.9}}]}}
    after = {'health': {'status': 'ok'}, 'ready': {'ready': True}, 'runtime': {
        'source_files': {'a.py': 'hash'}, 'source_matches_disk': True,
        'deployment_verified': True, 'deployment_commit': 'commit',
        'process_started_at': 'new', 'runtimes': deepcopy(before['runtime']['runtimes'])}}
    deploy.check_runtime(before, after, {'a.py': 'hash'}, 'commit')
    for key, value in [('source_matches_disk', False), ('deployment_commit', 'wrong'),
                       ('process_started_at', 'old'), ('source_files', {'a.py': 'wrong'}),
                       ('runtimes', [{'mode': 'PAPER'}])]:
        wrong = deepcopy(after)
        wrong['runtime'][key] = value
        with pytest.raises(AssertionError):
            deploy.check_runtime(before, wrong, {'a.py': 'hash'}, 'commit')


def test_runtime_fingerprint_detects_disk_change_without_relabelling_boot(monkeypatch):
    class Scanner:
        runtimes = []
    boot = deepcopy(dashboard.BOOT_SOURCE)
    monkeypatch.setattr(dashboard, '_source_snapshot', lambda: {'fingerprint': 'changed', 'files': {}})
    info = dashboard._runtime_info(Scanner())
    assert info['source_fingerprint'] == boot['fingerprint']
    assert info['source_matches_disk'] is False
    assert info['source_files'] == boot['files']


def test_deploy_hash_inventory_matches_runtime_inventory():
    assert set(deploy.SOURCE_FILES) == set(dashboard.SOURCE_FILES)
