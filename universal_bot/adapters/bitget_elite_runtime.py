from __future__ import annotations

import time

from universal_bot.adapters.bitget_elite import BitgetEliteAdapter as _ClassicBitgetEliteAdapter


class BitgetEliteAdapter(_ClassicBitgetEliteAdapter):
    """Runtime wrapper for the Classic v2 Elite adapter.

    Keeps the proven Classic v2 order/account implementation, but adds an
    explicit leverage synchronisation step for LIVE trading. Preflight remains
    read-only: ``configure_live`` only verifies leverage equality, while the
    runtime calls ``ensure_leverage`` before arming a symbol.
    """

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        leverage = int(leverage)
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        contract = self._contract(symbol)
        max_leverage = int(float(contract.get("maxLever") or 0))
        if max_leverage and leverage > max_leverage:
            raise RuntimeError(
                f"requested leverage {leverage} exceeds Bitget maximum {max_leverage} for {self._symbol_id(symbol)}"
            )
        data = self._request(
            "POST",
            "/api/v2/mix/account/set-leverage",
            body={
                "symbol": self._symbol_id(symbol),
                "productType": self.PRODUCT_TYPE,
                "marginCoin": self.MARGIN_COIN,
                "leverage": str(leverage),
            },
        )
        return dict(data or {}) if isinstance(data, dict) else {"result": data}

    @staticmethod
    def _account_leverage(account: dict) -> float:
        return float(
            account.get("crossedMarginLeverage")
            or account.get("crossedLever")
            or account.get("leverage")
            or 0.0
        )

    def ensure_leverage(self, symbol: str, leverage: int) -> dict:
        leverage = int(leverage)
        before_account = self.account_info(symbol)
        before = self._account_leverage(before_account)
        if abs(before - leverage) < 1e-9:
            return {
                "ok": True,
                "symbol": self._symbol_id(symbol),
                "requested_leverage": leverage,
                "before": before,
                "after": before,
                "changed": False,
            }

        self.set_leverage(symbol, leverage)
        time.sleep(0.25)
        after_account = self.account_info(symbol)
        after = self._account_leverage(after_account)
        ok = abs(after - leverage) < 1e-9
        return {
            "ok": ok,
            "symbol": self._symbol_id(symbol),
            "requested_leverage": leverage,
            "before": before,
            "after": after,
            "changed": True,
            "reason": None if ok else f"Bitget leverage remained {after} after requesting {leverage}",
        }

    def configure_live(
        self,
        symbol: str,
        leverage: int,
        margin_mode: str,
        require_one_way: bool = False,
    ) -> dict:
        result = super().configure_live(symbol, leverage, margin_mode, require_one_way)
        if not result.get("ok"):
            return result
        actual = float(result.get("account_leverage") or 0.0)
        requested = float(leverage)
        if abs(actual - requested) >= 1e-9:
            return {
                **result,
                "ok": False,
                "reason": f"Bitget leverage mismatch: account={actual:g}x requested={requested:g}x",
            }
        return result
