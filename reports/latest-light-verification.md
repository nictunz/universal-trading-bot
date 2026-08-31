# Latest light self-hosted verification

- Generated UTC: 2026-08-31T13:56:33Z
- Source commit: 1dcec9638d40830a92bf4e109c7bb1b431cb9299
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | failure |
| Dashboard HTTP smoke | success |
| Provider mapping | success |

## Pytest
```text
.....................................................F.......F.......... [ 98%]
.                                                                        [100%]
=================================== FAILURES ===================================
_____________ test_mobile_risk_profiles_use_mdd_and_search_ranges ______________

    def test_mobile_risk_profiles_use_mdd_and_search_ranges():
        aggressive = RISK_PROFILES["공격형"]
        assert aggressive == {
            "mdd_limit_percent": 40.0,
            "entry_multiplier_min": 1,
            "entry_multiplier_max": 25,
            "max_entries_values": [1, 2],
        }
    
        balanced = RISK_PROFILES["중간형"]
        assert balanced == {
            "mdd_limit_percent": 25.0,
            "entry_multiplier_min": 1,
            "entry_multiplier_max": 15,
            "max_entries_values": [1, 2],
        }
    
        split = RISK_PROFILES["3봉 분할형"]
>       assert split == {
            "mdd_limit_percent": 40.0,
            "entry_multiplier_min": 1,
            "entry_multiplier_max": 3,
            "max_entries_values": [1, 2, 3, 4, 5],
            "first_entry_consecutive_candles": 3,
        }
E       AssertionError: assert {'mdd_limit_p...3, 4, 5], ...} == {'mdd_limit_p...3, 4, 5], ...}
E         
E         Omitting 4 identical items, use -vv to show
E         Differing items:
E         {'mdd_limit_percent': 70.0} != {'mdd_limit_percent': 40.0}
E         
E         Full diff:
E           {
E         -     'mdd_limit_percent': 40.0,
E         ?                          ^
E         +     'mdd_limit_percent': 70.0,
E         ?                          ^
E               'entry_multiplier_min': 1,
E               'entry_multiplier_max': 3,
E               'max_entries_values': [
E                   1,
E                   2,
E                   3,
E                   4,
E                   5,
E               ],
E               'first_entry_consecutive_candles': 3,
E           }

tests/test_mobile_risk_profiles.py:29: AssertionError
_________ test_android_exposes_staged_and_fully_automatic_optimization _________

    def test_android_exposes_staged_and_fully_automatic_optimization():
        from pathlib import Path
    
        root = Path(__file__).resolve().parents[1]
        activity = (root / "android/app/src/main/java/com/nictunz/universalbacktester/MainActivity.java").read_text(encoding="utf-8")
        service = (root / "android/app/src/main/java/com/nictunz/universalbacktester/BacktestForegroundService.java").read_text(encoding="utf-8")
        bridge = (root / "android/app/src/main/python/mobile_bridge.py").read_text(encoding="utf-8")
        for label in ("1차 전체 탐색", "상위 후보 정밀 탐색", "3개월 롤링 + 최종 선정", "전체 자동 실행"):
            assert label in activity
        assert 'intent.putExtra("optimization_stage", optimizationStage)' in activity
        assert 'request.optString("optimization_stage", "broad")' in service
        assert "def _refine_top_candidates(" in bridge
        assert "def _rolling_validate_candidates(" in bridge
>       assert '"target_900_hits"' in bridge
E       assert '"target_900_hits"' in 'from __future__ import annotations\n\nimport gc\nimport hashlib\nimport statistics\nimport json\nimport os\nimport ra...(),\n            username.strip(),\n            remote_dir.strip(),\n            key_path.strip(),\n        )\n    )\n'

tests/test_mobile_risk_profiles.py:136: AssertionError
=========================== short test summary info ============================
FAILED tests/test_mobile_risk_profiles.py::test_mobile_risk_profiles_use_mdd_and_search_ranges - AssertionError: assert {'mdd_limit_p...3, 4, 5], ...} == {'mdd_limit_p...3, 4, 5], ...}
  
  Omitting 4 identical items, use -vv to show
  Differing items:
  {'mdd_limit_percent': 70.0} != {'mdd_limit_percent': 40.0}
  
  Full diff:
    {
  -     'mdd_limit_percent': 40.0,
  ?                          ^
  +     'mdd_limit_percent': 70.0,
  ?                          ^
        'entry_multiplier_min': 1,
        'entry_multiplier_max': 3,
        'max_entries_values': [
            1,
            2,
            3,
            4,
            5,
        ],
        'first_entry_consecutive_candles': 3,
    }
FAILED tests/test_mobile_risk_profiles.py::test_android_exposes_staged_and_fully_automatic_optimization - assert '"target_900_hits"' in 'from __future__ import annotations\n\nimport gc\nimport hashlib\nimport statistics\nimport json\nimport os\nimport ra...(),\n            username.strip(),\n            remote_dir.strip(),\n            key_path.strip(),\n        )\n    )\n'
2 failed, 71 passed in 24.12s
```
## Dashboard
```text
{"health": {"status": "ok", "strategy": "Volume Strategy FINAL Universal v15", "symbols": 1, "errors": [], "live_halted": []}, "state_symbols": 1, "html_bytes": 21203}
```
## Provider
```text
binance_eth= BINANCEFTS_PERP_ETH_USDT
bybit_sol= BYBIT_PERP_SOL_USDT
period_5m= 5MIN
```
