"""Exercise chart application with the modules actually packaged in the APK."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_chart_workspace import database  # shared 4-exchange DB fixture
from universal_bot.chart_workspace import V19, apply_strategy

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("model", ["v19", "signal_close", "next_open"])
def test_packaged_android_strategy_application_and_audit(database, model):
    before = database.read_bytes()
    parameters = dict(V19, backtest_execution_model=model,
                      volume_break_multiplier=.5, use_rsi_filter=False,
                      use_nbar_volatility_block=False, order_percent_of_equity=100.)
    if model == "v19":
        parameters = dict(V19)
    code = '''
import importlib.util, sys, json
from pathlib import Path
for name in ('config', 'historical'):
    spec=importlib.util.spec_from_file_location('universal_bot.'+name, Path('android/compat')/(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
from universal_bot.chart_workspace import apply_strategy, audit_page
response=json.loads(apply_strategy(sys.argv[1], 'BTC/USDT:USDT', '15m', sys.argv[2]))
page=json.loads(audit_page(response['result_path'], 0, 9999999999999))
assert page['rows'] and len(page['rows'][-1]['exchanges'])==4
print(json.dumps(response))
'''
    run = subprocess.run([sys.executable, "-c", code, str(database), json.dumps(parameters)],
                         cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    actual = json.loads(Path(json.loads(run.stdout)["result_path"]).read_text())
    expected_path = json.loads(apply_strategy(str(database), "BTC/USDT:USDT", "15m", json.dumps(parameters)))["result_path"]
    expected = json.loads(Path(expected_path).read_text())
    assert actual["trades_log"] == expected["trades_log"]
    if model != "v19":
        assert actual["trades_log"]
    assert actual["return_percent"] == expected["return_percent"]
    assert actual["effective_parameters"] == expected["effective_parameters"]
    assert database.read_bytes() == before


@pytest.mark.parametrize("values", [{"volume_lookback": 1.5}, {"use_rsi_filter": "maybe"},
                                    {"max_tp_percent": float("inf")}, {"excluded_hours": None}])
def test_android_settings_reject_invalid_types(values):
    spec = importlib.util.spec_from_file_location("android_settings", ROOT / "android/compat/config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError):
        module.Settings.model_validate(values)
