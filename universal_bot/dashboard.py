from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from universal_bot.backtest_service import run_symbol_backtest
from universal_bot.preflight import check_live_readiness


def _one(runtime):
    state = runtime.engine.last_state
    safety = runtime.engine.safety
    source_status = {}
    getter = getattr(runtime.engine.adapter, "volume_source_status", None)
    if callable(getter):
        try:
            source_status = getter()
        except Exception:
            source_status = {}
    if state is None:
        return {"symbol": runtime.symbol, "status": "WAITING", "error": runtime.last_error, "volume_sources": source_status, "live_safety": safety.__dict__}
    p = state.position
    return {
        "symbol": state.symbol,
        "timeframe": state.timeframe,
        "timestamp": state.timestamp.isoformat() if state.timestamp else None,
        "position": {"side": p.side, "size": p.size, "entry": p.entry_price, "tp": p.tp, "sl": p.sl, "entries": p.entries},
        "signal": state.signal.side if state.signal else None,
        "signal_reason": state.signal.reason if state.signal else None,
        "values": state.values,
        "stats": state.stats,
        "error": runtime.last_error,
        "volume_sources": source_status,
        "live_safety": {
            "enabled": safety.enabled,
            "halted": safety.halted,
            "reason": safety.reason,
            "consecutive_errors": safety.consecutive_errors,
            "protection_ok": safety.protection_ok,
            "last_reconciliation": safety.last_reconciliation.isoformat() if safety.last_reconciliation else None,
            "last_data": safety.last_data.isoformat() if safety.last_data else None,
            "exchange_position": safety.exchange_position,
            "internal_position": safety.internal_position,
        },
    }


class BacktestRequest(BaseModel):
    symbol: str
    asset_class: str = "crypto"
    exchange: str = "bitget"
    timeframe: str = "5m"
    start: str | None = None
    end: str | None = None


def create_dashboard(scanner) -> FastAPI:
    app = FastAPI(title="Universal Trading Bot Dashboard", version="v15")

    @app.get("/health")
    def health():
        runtimes = scanner.runtimes
        errors = [r.last_error for r in runtimes if r.last_error]
        halted = [r.engine.safety.reason for r in runtimes if r.engine.safety.halted]
        return {
            "status": "halted" if halted else ("degraded" if errors else "ok"),
            "strategy": "Volume Strategy FINAL Universal v15",
            "symbols": len(runtimes),
            "errors": errors,
            "live_halted": halted,
        }

    @app.get("/api/live-readiness")
    def live_readiness():
        try:
            return check_live_readiness()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"readiness check failed: {type(exc).__name__}: {exc}") from exc

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
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"backtest failed: {type(exc).__name__}: {exc}") from exc

    @app.get("/", response_class=HTMLResponse)
    def index():
        return """<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Universal Trading Bot</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;background:#0b0f14;color:#eef2f7;margin:0;padding:14px}.wrap{max-width:1380px;margin:auto}.top{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.bar,.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:14px;margin-bottom:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.muted{color:#9daabd}.metric{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid #2b3747;padding:6px 0}.good{color:#42e887}.bad{color:#ff6677}.warn{color:#ffcc66}.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}input,select,button{box-sizing:border-box;padding:10px;border-radius:8px;border:1px solid #556579;background:#0b0f14;color:#eef2f7}button{cursor:pointer;background:#2563a8;border-color:#3780cf;font-weight:700}.metricbox{background:#0f1620;border-radius:9px;padding:10px}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:8px}.big{font-size:20px;font-weight:800}.status{margin-left:auto}.error{color:#ff6677}.ok{color:#42e887}.pill{display:inline-block;padding:4px 9px;border-radius:99px;background:#263445}.section{margin-top:22px}.nowrap{white-space:nowrap}table{width:100%;border-collapse:collapse}th,td{text-align:right;padding:7px;border-bottom:1px solid #2b3747}th:first-child,td:first-child{text-align:left}.headerBadge{font-size:13px;font-weight:800;padding:5px 9px;border-radius:99px;background:#263445}
</style></head>
<body><div class='wrap'>
<div class='top'><div><h1 style='margin-bottom:4px'>Universal Trading Bot</h1><div class='muted'>Volume Strategy FINAL Universal v15 · TradingView independent</div></div><span id='healthBadge' class='headerBadge muted'>HEALTH 확인 중</span><span id='readyBadge' class='headerBadge muted'>LIVE READINESS 확인 중</span></div>

<div class='bar section'><b>서버 / LIVE 사전점검</b><div class='row' style='margin-top:9px'><button onclick='refreshHealth()'>Health 새로고침</button><button onclick='refreshReadiness()'>Bitget Readiness 점검</button><span id='diagStatus' class='muted'></span></div><div id='diagnostics' class='metrics' style='margin-top:10px'></div></div>

<div class='bar'><b>백테스트 / 과거 데이터</b><div class='muted' style='margin-top:4px'>Crypto: 4개 선물거래소 정규화 거래량 · Stock/ETF: 종목 자체 거래량 · 수수료/슬리피지 반영</div><div class='row' style='margin-top:9px'><input id='symbol' value='ETH/USDT:USDT' placeholder='심볼'><select id='asset'><option value='crypto'>Crypto</option><option value='stock'>Stock</option><option value='etf'>ETF</option></select><input id='exchange' value='bitget' placeholder='거래소'><select id='tf'><option>5m</option><option>15m</option><option>1h</option><option>4h</option><option>1d</option></select></div><div class='row' style='margin-top:8px'><label>시작 <input id='start' type='date'></label><label>종료 <input id='end' type='date'></label><button onclick='runBT()'>데이터 수집 + 백테스트</button><span id='status' class='status muted'></span></div></div>

<div id='bt' style='display:none'><div class='metrics' id='metrics'></div><div class='card'><b>Equity Curve (비용 반영)</b><canvas id='equity' style='width:100%;height:280px'></canvas></div><div class='card'><b>거래 내역</b><div style='overflow:auto'><table><thead><tr><th>방향</th><th>평균 진입</th><th>청산</th><th>수량</th><th>총손익</th><th>비용</th><th>순손익</th><th>순손익%</th><th>사유</th></tr></thead><tbody id='trades'></tbody></table></div></div></div>

<div class='section'><h2>실시간 전략 상태</h2><div id='grid' class='grid'></div></div>
<script>
const esc=s=>String(s??'-').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
let lastEquity=[];
function metric(n,v,cls=''){return `<div class='metricbox'><div class='muted'>${n}</div><div class='big ${cls}'>${v}</div></div>`}
function sourceText(src){const names=['binance','bitget','okx','bybit'];return names.map(n=>{const s=src?.[n];return `${n.toUpperCase()}:${s?(s.status==='OK'?s.mode:'FAIL'):'-'}`}).join(' · ')}
function setDefaultDates(){const end=new Date(),start=new Date(end);start.setUTCFullYear(start.getUTCFullYear()-1);const f=d=>d.toISOString().slice(0,10);document.getElementById('start').value=f(start);document.getElementById('end').value=f(end)}
function drawEquity(data){lastEquity=data||[];const c=document.getElementById('equity'),dpr=devicePixelRatio||1,w=c.clientWidth||900,h=280;c.width=w*dpr;c.height=h*dpr;const x=c.getContext('2d');x.scale(dpr,dpr);x.clearRect(0,0,w,h);if(!data||data.length<2){x.fillStyle='#9daabd';x.fillText('Equity 데이터 없음',15,30);return}const vals=data.map(a=>Number(a.equity??0)).filter(Number.isFinite);if(vals.length<2)return;const min=Math.min(...vals),max=Math.max(...vals),pad=25;const px=i=>pad+i*(w-pad*2)/(vals.length-1),py=v=>h-pad-(v-min)*(h-pad*2)/Math.max(1,max-min);x.strokeStyle='#556579';x.beginPath();x.moveTo(pad,pad);x.lineTo(pad,h-pad);x.lineTo(w-pad,h-pad);x.stroke();x.strokeStyle='#42e887';x.lineWidth=2;x.beginPath();vals.forEach((v,i)=>i?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v)));x.stroke()}
async function refreshHealth(){const badge=document.getElementById('healthBadge');try{const r=await fetch('/health'),d=await r.json();badge.textContent='HEALTH '+String(d.status||'unknown').toUpperCase();badge.className='headerBadge '+(d.status==='ok'?'good':d.status==='degraded'?'warn':'bad');document.getElementById('diagStatus').textContent=(d.errors||[]).join(' | ')||''}catch(e){badge.textContent='HEALTH ERROR';badge.className='headerBadge bad'}}
async function refreshReadiness(){const badge=document.getElementById('readyBadge'),box=document.getElementById('diagnostics');try{const r=await fetch('/api/live-readiness'),d=await r.json();badge.textContent=d.ready?'LIVE READY':'LIVE NOT READY';badge.className='headerBadge '+(d.ready?'good':'warn');box.innerHTML=(d.checks||[]).map(c=>metric(esc(c.name),c.ok?'PASS':'FAIL',c.ok?'good':'bad')).join('')}catch(e){badge.textContent='READINESS ERROR';badge.className='headerBadge bad';box.innerHTML=metric('오류',esc(e.message),'bad')}}
async function runBT(){const status=document.getElementById('status');status.textContent='데이터 수집/백테스트 중...';status.className='status muted';const q={symbol:document.getElementById('symbol').value,asset_class:document.getElementById('asset').value,exchange:document.getElementById('exchange').value,timeframe:document.getElementById('tf').value,start:document.getElementById('start').value||null,end:document.getElementById('end').value||null};try{const r=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)});const d=await r.json();if(!r.ok)throw Error(d.detail||'백테스트 오류');document.getElementById('bt').style.display='block';const cls=v=>Number(v)>0?'good':Number(v)<0?'bad':'';document.getElementById('metrics').innerHTML=metric('심볼',esc(d.symbol))+metric('봉 수',esc(d.bars))+metric('거래',esc(d.trades))+metric('승률',Number(d.win_rate||0).toFixed(2)+'%',cls(d.win_rate-50))+metric('PF',d.profit_factor==null?'-':Number(d.profit_factor).toFixed(2))+metric('총손익',Number(d.gross_pnl||0).toFixed(2),cls(d.gross_pnl))+metric('추정비용',Number(d.estimated_costs||0).toFixed(2),'warn')+metric('순손익',Number(d.pnl||0).toFixed(2),cls(d.pnl))+metric('순수익률',Number(d.return_percent||0).toFixed(2)+'%',cls(d.return_percent))+metric('MDD',Number(d.max_drawdown_percent||0).toFixed(2)+'%','bad')+metric('Fee/side',Number(d.fee_percent_per_side||0).toFixed(3)+'%')+metric('Slip/side',Number(d.slippage_percent_per_side||0).toFixed(3)+'%')+metric('Data Sources',esc(sourceText(d.volume_source_status||{})));drawEquity(d.equity_curve||[]);document.getElementById('trades').innerHTML=(d.trades_log||[]).slice().reverse().map(t=>`<tr><td>${esc(t.side)}</td><td>${esc(t.avg_entry_price)}</td><td>${esc(t.exit_price)}</td><td>${esc(t.qty)}</td><td>${Number(t.gross_pnl||0).toFixed(2)}</td><td class='warn'>${Number(t.estimated_cost||0).toFixed(2)}</td><td class='${Number(t.pnl)>=0?'good':'bad'}'>${Number(t.pnl||0).toFixed(2)}</td><td>${Number(t.pnl_percent||0).toFixed(3)}%</td><td>${esc(t.reason)}</td></tr>`).join('');status.textContent=`완료 · ${esc(d.data_start||'')} ~ ${esc(d.data_end||'')} · 4거래소 ${d.four_exchange_volume?'ON':'OFF'}`;status.className='status ok'}catch(e){status.textContent='오류: '+e.message;status.className='status error'}}
async function refresh(){try{const r=await fetch('/api/state'),d=await r.json();document.getElementById('grid').innerHTML=d.symbols.map(x=>{const v=x.values||{},p=x.position||{},st=x.stats||{},s=x.live_safety||{};const liveEnabled=!!s.enabled;return `<div class='card'><h2>${esc(x.symbol)} <span class='pill'>${esc(x.timeframe||'')}</span></h2><div class='metric'><span>POSITION</span><b>${esc(p.side||'FLAT')}</b></div><div class='metric'><span>SIGNAL</span><b>${esc(x.signal||'NO SIGNAL')}</b></div><div class='metric'><span>Volume</span><b>x${esc(v.volume_ratio?.toFixed?.(2)??'-')}</b></div><div class='metric'><span>Volume Sources</span><b style='font-size:11px;text-align:right'>${esc(sourceText(x.volume_sources||{}))}</b></div><div class='metric'><span>ADX / RSI</span><b>${esc(v.adx?.toFixed?.(2)??'-')} / ${esc(v.rsi?.toFixed?.(2)??'-')}</b></div><div class='metric'><span>TP / SL</span><b>${esc(v.final_tp_percent??'-')}% / ${esc(v.final_sl_percent??'-')}%</b></div><div class='metric'><span>Realized / Open PnL</span><b>${esc(st.realized_pnl?.toFixed?.(2)??'0')} / ${esc(st.open_pnl?.toFixed?.(2)??'0')}</b></div><div class='metric'><span>Data time</span><b class='nowrap'>${esc(x.timestamp||'-')}</b></div><div class='metric'><span>LIVE SAFETY</span><b class='${s.halted?'bad':liveEnabled?'good':'muted'}'>${liveEnabled?(s.halted?'HALTED':'OK'):'PAPER'}</b></div><div class='metric'><span>Protection</span><b class='${!liveEnabled?'muted':s.protection_ok?'good':'bad'}'>${!liveEnabled?'N/A':s.protection_ok?'VERIFIED':'NOT VERIFIED'}</b></div><div class='metric'><span>Reconciliation</span><b class='nowrap'>${esc(s.last_reconciliation||'-')}</b></div><div class='muted'>${esc(s.reason||x.signal_reason||'')}${x.error?`<div class='error'>${esc(x.error)}</div>`:''}</div></div>`}).join('')}catch(e){document.getElementById('grid').innerHTML=`<div class='card error'>Dashboard API 오류: ${esc(e.message)}</div>`}}
setDefaultDates();refreshHealth();refreshReadiness();refresh();setInterval(refresh,2000);setInterval(refreshHealth,10000);window.addEventListener('resize',()=>drawEquity(lastEquity));
</script></div></body></html>"""

    return app
