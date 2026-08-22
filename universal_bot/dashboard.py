from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


def create_dashboard(engine) -> FastAPI:
    app = FastAPI(title="Universal Trading Bot Dashboard")

    @app.get("/api/state")
    def state():
        s = engine.last_state
        if s is None:
            return {"status": "WAITING"}
        p = s.position
        return {
            "symbol": s.symbol,
            "timeframe": s.timeframe,
            "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            "position": {"side": p.side, "size": p.size, "entry": p.entry_price, "tp": p.tp, "sl": p.sl, "entries": p.entries},
            "signal": s.signal.side if s.signal else None,
            "signal_reason": s.signal.reason if s.signal else None,
            "values": s.values,
            "stats": s.stats,
        }

    @app.get("/", response_class=HTMLResponse)
    def index():
        return """<!doctype html><html><head><meta charset='utf-8'><title>Universal Trading Bot</title><style>body{font-family:system-ui;background:#0c1016;color:#eee;margin:24px}pre{background:#192332;padding:18px;border-radius:10px;overflow:auto}h1{margin-bottom:4px}</style></head><body><h1>Universal Trading Bot</h1><div>Volume Strategy FINAL Universal v15</div><pre id='state'>loading...</pre><script>async function refresh(){const r=await fetch('/api/state');document.getElementById('state').textContent=JSON.stringify(await r.json(),null,2)}refresh();setInterval(refresh,1000)</script></body></html>"""
    return app
