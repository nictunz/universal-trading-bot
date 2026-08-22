from __future__ import annotations
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

def _one(runtime):
    s = runtime.engine.last_state
    if s is None:
        return {"symbol": runtime.symbol, "status": "WAITING", "error": runtime.last_error}
    p = s.position
    return {"symbol": s.symbol, "timeframe": s.timeframe, "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            "position": {"side": p.side, "size": p.size, "entry": p.entry_price, "tp": p.tp, "sl": p.sl, "entries": p.entries},
            "signal": s.signal.side if s.signal else None, "signal_reason": s.signal.reason if s.signal else None,
            "values": s.values, "stats": s.stats, "error": runtime.last_error}

def create_dashboard(scanner) -> FastAPI:
    app = FastAPI(title="Universal Trading Bot Dashboard")
    @app.get("/api/state")
    def state():
        return {"strategy": "Volume Strategy FINAL Universal v15", "symbols": [_one(r) for r in scanner.runtimes]}
    @app.get("/api/summary")
    def summary():
        return scanner.snapshot()
    @app.get("/", response_class=HTMLResponse)
    def index():
        return """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Universal Trading Bot</title><style>body{font-family:system-ui;background:#0c1016;color:#eee;margin:18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}.card{background:#192332;border:1px solid #354354;border-radius:12px;padding:14px}.ok{color:#55ee99}.bad{color:#ff4b5a}.muted{color:#aab5c5}pre{white-space:pre-wrap;font-size:12px}</style></head><body><h1>Universal Trading Bot</h1><div class='muted'>Volume Strategy FINAL Universal v15 · TradingView independent</div><div id='grid' class='grid'></div><script>async function refresh(){const r=await fetch('/api/state');const d=await r.json();document.getElementById('grid').innerHTML=d.symbols.map(x=>{const v=x.values||{},p=x.position||{};return `<div class='card'><h2>${x.symbol}</h2><div>POSITION: <b class='${p.side==='LONG'?'ok':p.side==='SHORT'?'bad':''}'>${p.side||'FLAT'}</b></div><div>SIGNAL: ${x.signal||'NO SIGNAL'}</div><div>Volume x${v.volume_ratio?.toFixed?.(2)??'-'} / TP ${v.final_tp_percent??'-'}% / SL ${v.final_sl_percent??'-'}%</div><div>ADX ${v.adx?.toFixed?.(2)??'-'} · RSI ${v.rsi?.toFixed?.(2)??'-'}</div><div>Win ${x.stats?.win_rate?.toFixed?.(2)??'0'}% · PF ${x.stats?.profit_factor??'-'} · PnL ${x.stats?.realized_pnl?.toFixed?.(2)??'0'}</div><pre>${x.error||''}</pre></div>`}).join('')}refresh();setInterval(refresh,1000)</script></body></html>"""
    return app
