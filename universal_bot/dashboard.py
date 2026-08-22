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
    return {
        "symbol": s.symbol,
        "timeframe": s.timeframe,
        "timestamp": s.timestamp.isoformat() if s.timestamp else None,
        "position": {"side": p.side, "size": p.size, "entry": p.entry_price, "tp": p.tp, "sl": p.sl, "entries": p.entries},
        "signal": s.signal.side if s.signal else None,
        "signal_reason": s.signal.reason if s.signal else None,
        "values": s.values,
        "stats": s.stats,
        "error": runtime.last_error,
    }


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
        return """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Universal Trading Bot</title><style>
body{font-family:system-ui,-apple-system,sans-serif;background:#0c1016;color:#eee;margin:0;padding:12px}.wrap{max-width:1200px;margin:auto}.bar,.card{background:#192332;border:1px solid #354354;border-radius:12px;padding:14px;margin-bottom:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}.muted{color:#aab5c5}.row{display:flex;flex-wrap:wrap;gap:7px;align-items:center}input,select,button{box-sizing:border-box;padding:10px;border-radius:7px;border:1px solid #566477;background:#0c1016;color:#eee}button{cursor:pointer;background:#1d6fa5;border-color:#338dcc;font-weight:700}.metric{display:flex;justify-content:space-between;border-bottom:1px solid #303b4b;padding:5px 0}.good{color:#39eb7d}.bad{color:#ff4b5a}.chart{width:100%;height:280px;background:#0c1016;border-radius:8px}.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:7px;border-bottom:1px solid #303b4b;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}.section{margin-top:16px}.pill{display:inline-block;padding:4px 8px;border-radius:99px;background:#263244}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px}.metricbox{background:#101722;border-radius:8px;padding:10px}.big{font-size:20px;font-weight:800}.status{margin-left:auto}.error{color:#ff4b5a}</style></head><body><div class='wrap'>
<h1>Universal Trading Bot</h1><div class='muted'>Volume Strategy FINAL Universal v15 · TradingView independent</div>
<div class='bar section'><b>백테스트 / 과거 데이터</b><div class='row' style='margin-top:9px'><input id='symbol' value='BTC/USDT:USDT' placeholder='심볼'><select id='asset'><option value='crypto'>Crypto</option><option value='stock'>Stock</option><option value='etf'>ETF</option></select><input id='exchange' value='bitget' placeholder='거래소'><select id='tf'><option>5m</option><option>15m</option><option>1h</option><option>4h</option><option>1d</option></select></div><div class='row' style='margin-top:8px'><label>시작 <input id='start' type='date' value='2024-01-01'></label><label>종료 <input id='end' type='date'></label><button onclick='runBT()'>데이터 수집 + 백테스트</button><span id='status' class='status muted'></span></div></div>
<div id='bt' style='display:none'><div class='metrics' id='metrics'></div><div class='card section'><b>Equity Curve</b><canvas id='equity' class='chart'></canvas></div><div class='card section'><b>거래 내역</b><div class='tablewrap'><table><thead><tr><th>시간</th><th>방향</th><th>진입</th><th>청산</th><th>수량</th><th>손익</th><th>손익%</th><th>사유</th></tr></thead><tbody id='trades'></tbody></table></div></div></div>
<div class='section'><h2>실시간 전략 상태</h2><div id='grid' class='grid'></div></div>
<script>
const esc=s=>String(s??'-').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
function metric(n,v,cls=''){return `<div class='metricbox'><div class='muted'>${n}</div><div class='big ${cls}'>${v}</div></div>`}
function drawEquity(data){const c=document.getElementById('equity'),dpr=devicePixelRatio||1,w=c.clientWidth,h=280;c.width=w*dpr;c.height=h*dpr;const x=c.getContext('2d');x.scale(dpr,dpr);x.clearRect(0,0,w,h);if(!data||data.length<2){x.fillStyle='#aab5c5';x.fillText('Equity 데이터 없음',15,30);return}const vals=data.map(a=>Number(a.equity??a.value??a[1]??0));const min=Math.min(...vals),max=Math.max(...vals),pad=25;const px=i=>pad+i*(w-pad*2)/(vals.length-1),py=v=>h-pad-(v-min)*(h-pad*2)/Math.max(1,max-min);x.strokeStyle='#566477';x.beginPath();x.moveTo(pad,pad);x.lineTo(pad,h-pad);x.lineTo(w-pad,h-pad);x.stroke();x.strokeStyle='#39eb7d';x.lineWidth=2;x.beginPath();vals.forEach((v,i)=>i?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v)));x.stroke();x.fillStyle='#aab5c5';x.fillText(max.toFixed(2),pad+4,14);x.fillText(min.toFixed(2),pad+4,h-5)}
async function runBT(){const status=document.getElementById('status');status.textContent='데이터 수집/백테스트 중...';const q={symbol:document.getElementById('symbol').value,asset_class:document.getElementById('asset').value,exchange:document.getElementById('exchange').value,timeframe:document.getElementById('tf').value,start:document.getElementById('start').value||null,end:document.getElementById('end').value||null};try{const r=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)});const d=await r.json();if(!r.ok)throw Error(d.detail||'백테스트 오류');document.getElementById('bt').style.display='block';const cls=v=>Number(v)>0?'good':Number(v)<0?'bad':'';document.getElementById('metrics').innerHTML=metric('심볼',esc(d.symbol))+metric('봉 수',esc(d.bars))+metric('거래',esc(d.trades))+metric('승률',Number(d.win_rate||0).toFixed(2)+'%',cls(d.win_rate-50))+metric('PF',d.profit_factor==null?'-':Number(d.profit_factor).toFixed(2))+metric('수익률',Number(d.return_percent||0).toFixed(2)+'%',cls(d.return_percent))+metric('MDD',Number(d.max_drawdown_percent||0).toFixed(2)+'%', 'bad')+metric('수집 봉',esc(d.inserted));drawEquity(d.equity_curve||[]);document.getElementById('trades').innerHTML=(d.trades_log||[]).slice().reverse().map(t=>`<tr><td>${esc(t.exit_time||t.time||t.timestamp)}</td><td>${esc(t.side)}</td><td>${esc(t.entry_price)}</td><td>${esc(t.exit_price)}</td><td>${esc(t.size)}</td><td class='${Number(t.pnl)>=0?'good':'bad'}'>${esc(t.pnl)}</td><td>${esc(t.pnl_percent??'-')}</td><td>${esc(t.reason)}</td></tr>`).join('');status.textContent=`완료 · ${d.start||''} ~ ${d.end||'현재'}`;status.className='status good'}catch(e){status.textContent='오류: '+e.message;status.className='status error'}}
async function refresh(){try{const r=await fetch('/api/state');const d=await r.json();document.getElementById('grid').innerHTML=d.symbols.map(x=>{const v=x.values||{},p=x.position||{},st=x.stats||{};return `<div class='card'><h2>${esc(x.symbol)} <span class='pill'>${esc(x.timeframe||'')}</span></h2><div class='metric'><span>POSITION</span><b>${esc(p.side||'FLAT')}</b></div><div class='metric'><span>SIGNAL</span><b>${esc(x.signal||'NO SIGNAL')}</b></div><div class='metric'><span>Volume</span><b>x${esc(v.volume_ratio?.toFixed?.(2)??'-')}</b></div><div class='metric'><span>1봉 변동</span><b>${esc(v.one_bar_volatility?.toFixed?.(2)??'-')}%</b></div><div class='metric'><span>TP / SL</span><b>${esc(v.final_tp_percent??'-')}% / ${esc(v.final_sl_percent??'-')}%</b></div><div class='metric'><span>ADX / RSI</span><b>${esc(v.adx?.toFixed?.(2)??'-')} / ${esc(v.rsi?.toFixed?.(2)??'-')}</b></div><div class='metric'><span>Win Rate</span><b>${esc(st.win_rate?.toFixed?.(2)??'0')}%</b></div><div class='metric'><span>Profit Factor</span><b>${esc(st.profit_factor??'-')}</b></div><div class='metric'><span>Realized PnL</span><b>${esc(st.realized_pnl?.toFixed?.(2)??'0')}</b></div><div class='muted'>${esc(x.signal_reason||'')}</div></div>`}).join('')}catch(e){}}refresh();setInterval(refresh,2000);window.addEventListener('resize',()=>{const d=window.lastEquity;if(d)drawEquity(d)});
</script></div></body></html>"""
    return app
