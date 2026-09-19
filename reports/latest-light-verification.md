# Latest light self-hosted verification

- Generated UTC: 2026-09-19T02:51:33Z
- Source commit: 09600ce8bd9f35fb0eb7712b4a279bc561dbd1d8
- Runner: trading-bot-new

| Check | Outcome |
|---|---|
| Compile | success |
| Pytest | failure |
| Dashboard HTTP smoke | success |
| Provider mapping | success |

## Pytest
```text
..................................................F..................... [ 25%]
........................................................................ [ 50%]
........................................................................ [ 76%]
...................................................................      [100%]
=================================== FAILURES ===================================
___________ test_uta_ensure_leverage_initializes_empty_symbol_config ___________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x79ae327446d0>

    def test_uta_ensure_leverage_initializes_empty_symbol_config(monkeypatch):
        adapter = _adapter()
        settings_reads = 0
        set_body = {}
    
        def fake_request(method, path, params=None, body=None):
            nonlocal settings_reads
            if path == "/api/v3/account/settings":
                settings_reads += 1
                configured = settings_reads >= 2
                return {
                    "accountMode": "unified",
                    "accountLevel": "basic",
                    "holdMode": "hedge_mode",
                    "symbolConfigList": ([{
                        "category": "USDT-FUTURES",
                        "symbol": "BTCUSDT",
                        "marginMode": "crossed",
                        "leverage": "15",
                    }] if configured else []),
                }
            if path == "/api/v3/market/instruments":
                return [{"symbol": "BTCUSDT", "maxLeverage": "150"}]
            if path == "/api/v3/account/set-leverage":
                set_body.update(body)
                return "success"
            raise AssertionError(path)
    
        monkeypatch.setattr(adapter, "_request", fake_request)
        monkeypatch.setattr(adapter, "_public_get", lambda path, params: [{
            "symbol": "BTCUSDT", "maxLeverage": "150"
        }])
>       result = adapter.ensure_leverage("BTC/USDT:USDT", 15)

tests/test_bitget_uta_adapter.py:319: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
universal_bot/adapters/bitget_uta_runtime.py:197: in ensure_leverage
    self.set_leverage(symbol, leverage)
universal_bot/adapters/bitget_uta_runtime.py:165: in set_leverage
    contract = self._contract(symbol)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <universal_bot.adapters.bitget_uta_runtime.BitgetUtaAdapter object at 0x79ae32744670>
symbol = 'BTC/USDT:USDT'

    def _contract(self, symbol: str) -> dict[str, Any]:
        sid = self._symbol_id(symbol)
        cached = self._contract_cache.get(sid)
        if cached is not None:
            return cached
        rows = self._public_get(
            "/api/v3/market/instruments",
            {"category": self.CATEGORY, "symbol": sid},
        ) or []
        if not rows:
            raise RuntimeError(f"Bitget UTA instrument not found: {sid}")
        contract = dict(rows[0])
        status = str(contract.get("status") or "").lower()
        if status not in {"online", "normal"}:
>           raise RuntimeError(f"Bitget UTA instrument is not API-tradable: {sid} status={status}")
E           RuntimeError: Bitget UTA instrument is not API-tradable: BTCUSDT status=

universal_bot/adapters/bitget_uta_runtime.py:38: RuntimeError
=========================== short test summary info ============================
FAILED tests/test_bitget_uta_adapter.py::test_uta_ensure_leverage_initializes_empty_symbol_config - RuntimeError: Bitget UTA instrument is not API-tradable: BTCUSDT status=
1 failed, 282 passed in 189.48s (0:03:09)
```
## Dashboard
```text
{"health": {"status": "ok", "strategy": "Volume Strategy FINAL Universal v15", "symbols": 1, "errors": [], "live_halted": []}, "state_symbols": 1, "html_bytes": 24764}
```
## Provider
```text
binance_eth= BINANCEFTS_PERP_ETH_USDT
bybit_sol= BYBIT_PERP_SOL_USDT
period_5m= 5MIN
```
