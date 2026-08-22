from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from universal_bot.backtest_service import run_symbol_backtest

def _one(runtime):
    s = runtime.engine.last_state
    if s is None:
        return {"symbol": runtime.symbol, "status": "WAITING", "error": runtime.last_error}
    p = s.position
    return {"symbol": s.symbol, "timeframe": s.timeframe, "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            "position": {"side": p.side, "size": p.size, "entry": p.entry_price, "tp": p.tp, "sl": p.sl, "entries": p.entries},
            "signal": s.signal.side if s.signal else None, "signal_reason": s.signal.reason if s.signal else None,
            "values": s.values, "stats": s.stats, "error": runtime.last_error}

class BacktestRequest(BaseModel):
    symbol: str
    asset_class: str = "crypto"
    exchange: str = "bitget"
    timeframe: str = "5m"
    start: str | None = None
    end: str | None = None

def create_dashboard(scanner) -> FastAPI:
    app = FastAPI(title="Universal Trading Bot Dashboard")
    @app.get("/api/state")
    def state():
        return {"strategy": "Volume Strategy FINAL Universal v15", "symbols": [_one(r) for r in scanner.runtimes]}
    @app.get("/api/summary")
    def summary():
        return scanner.snapshot()
    @app.post("/api/backtest")
    def backtest(req: BacktestRequest):
        try:
            return run_symbol_backtest(req.symbol, req.asset_class, req.exchange, req.timeframe, req.start, req.end)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    @app.get("/", response_class=HTMLResponse)
    def index():
        return """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Universal Trading Bot</title><style>body{font-family:system-ui;background:#0c1016;color:#eee;margin:18px}.bar,.card{background:#192332;border:1px solid #354354;border-radius:12px;padding:14px;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}.muted{color:#aab5c5}input,select,button{padding:9px;margin:4px;border-radius:7px;border:1px solid #566477;background:#0c1016;color:#eee}</style></head><body><h1>Universal Trading Bot</h1><div class='muted'>Volume Strategy FINAL Universal v15 · TradingView independent</div><div class='bar'><b>백테스트</b><br><input id='symbol' value='BTC/USDT:USDT' placeholder='심볼'><select id='asset'><option value='crypto'>Crypto</option><option value='stock'>Stock</option><option value='etf'>ETF</option></select><input id='exchange' value='bitget' placeholder='거래소'><select id='tf'><option>5m</option><option>15m</option><option>1h</option><option>4h</option><option>1d</option></select><input id='start' type='date' value='2024-01-01'><input id='end' type='date'><button onclick='runBT()'>데이터 수집 + 백테스트</button><pre id='result'></pre></div><div id='grid' class='grid'></div><script>async function runBT(){const q={symbol:document.getElementById('symbol').value,asset_class:document.getElementById('asset').value,exchange:document.getElementById('exchange').value,timeframe:document.getElementById('tf').value,start:document.getElementById('start').value||null,end:document.getElementById('end').value||null};document.getElementById('result').textContent='실행 중...';const r=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)});const d=await r.json();document.getElementById('result').textContent=JSON.stringify(d,null,2)}async function refresh(){const r=await fetch('/api/state');const d=await r.json();document.getElementById('grid').innerHTML=d.symbols.map(x=>{const v=x.values||{},p=x.position||{};return `<div class='card'><h2>${x.symbol}</h2><div>POSITION: ${p.side||'FLAT'}</div><div>SIGNAL: ${x.signal||'NO SIGNAL'}</div><div>Volume x${v.volume_ratio?.toFixed?.(2)??'-'} / TP ${v.final_tp_percent??'-'}% / SL ${v.final_sl_percent??'-'}%</div><div>ADX ${v.adx?.toFixed?.(2)??'-'} · RSI ${v.rsi?.toFixed?.(2)??'-'}</div><div>Win ${x.stats?.win_rate?.toFixed?.(2)??'0'}% · PF ${x.stats?.profit_factor??'-'} · PnL ${x.stats?.realized_pnl?.toFixed?.(2)??'0'}</div></div>`}).join('')}refresh();setInterval(refresh,2000)</script></body></html>"""
    return app
