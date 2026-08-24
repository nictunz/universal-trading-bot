from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from universal_bot.backtest_service import run_symbol_backtest
from universal_bot.dashboard_data import DashboardDataService
from universal_bot.preflight import check_live_readiness
from universal_bot.trade_history import TradeHistoryStore


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
        return {
            "symbol": runtime.symbol,
            "status": "WAITING",
            "error": runtime.last_error,
            "volume_sources": source_status,
            "live_safety": safety.__dict__,
        }
    p = state.position
    return {
        "symbol": state.symbol,
        "timeframe": state.timeframe,
        "timestamp": state.timestamp.isoformat() if state.timestamp else None,
        "position": {
            "side": p.side,
            "size": p.size,
            "entry": p.entry_price,
            "tp": p.tp,
            "sl": p.sl,
            "entries": p.entries,
        },
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
    history = TradeHistoryStore()
    dashboard_data = DashboardDataService(history)

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

    @app.get("/api/candles")
    def candles(
        symbol: str,
        exchange: str = "bitget",
        timeframe: str = "5m",
        asset_class: str = "crypto",
        start: str | None = None,
        end: str | None = None,
        max_points: int = Query(1400, ge=100, le=5000),
    ):
        try:
            return dashboard_data.candles(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                asset_class=asset_class,
                start=start,
                end=end,
                max_points=max_points,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"chart data failed: {type(exc).__name__}: {exc}") from exc

    @app.get("/api/candles-page")
    def candles_page(
        symbol: str,
        exchange: str = "bitget",
        timeframe: str = "5m",
        asset_class: str = "crypto",
        start: str | None = None,
        before: str | None = None,
        page_size: int = Query(600, ge=100, le=2000),
    ):
        try:
            return dashboard_data.candles_page(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                asset_class=asset_class,
                start=start,
                before=before,
                page_size=page_size,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"paged chart data failed: {type(exc).__name__}: {exc}") from exc

    @app.get("/api/trades")
    def trades(
        symbol: str,
        mode: str = "ALL",
        start: str | None = None,
        end: str | None = None,
        limit: int = Query(2000, ge=1, le=10000),
    ):
        try:
            return dashboard_data.history_payload(symbol=symbol, mode=mode, start=start, end=end, limit=limit)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"trade history failed: {type(exc).__name__}: {exc}") from exc

    @app.post("/api/backtest")
    def backtest(req: BacktestRequest):
        try:
            result = run_symbol_backtest(req.symbol, req.asset_class, req.exchange, req.timeframe, req.start, req.end)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            run_id = f"BT-{req.symbol}-{req.timeframe}-{stamp}"
            history.record_backtest(result, run_id=run_id, params=req.model_dump())
            result["run_id"] = run_id
            return result
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
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,sans-serif;background:#0b0f14;color:#eef2f7;margin:0;padding:14px}.wrap{max-width:1480px;margin:auto}.top{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.bar,.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:14px;margin-bottom:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.muted{color:#9daabd}.metric{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid #2b3747;padding:6px 0}.good{color:#42e887}.bad{color:#ff6677}.warn{color:#ffcc66}.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}input,select,button{padding:10px;border-radius:8px;border:1px solid #556579;background:#0b0f14;color:#eef2f7;font-size:14px}button{cursor:pointer;background:#2563a8;border-color:#3780cf;font-weight:700}.ghost{background:#17202c}.metricbox{background:#0f1620;border-radius:9px;padding:10px}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:8px}.big{font-size:20px;font-weight:800}.status{margin-left:auto}.error{color:#ff6677}.ok{color:#42e887}.pill{display:inline-block;padding:4px 9px;border-radius:99px;background:#263445}.section{margin-top:22px}.nowrap{white-space:nowrap}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:right;padding:7px;border-bottom:1px solid #2b3747;white-space:nowrap}th:first-child,td:first-child{text-align:left}.headerBadge{font-size:13px;font-weight:800;padding:5px 9px;border-radius:99px;background:#263445}.chartWrap{position:relative;width:100%;height:430px;background:#0d141d;border-radius:10px;overflow:hidden}.chartWrap canvas{width:100%;height:100%;display:block;touch-action:pan-y;cursor:grab}.chartWrap canvas.dragging{cursor:grabbing}.toolbar{display:flex;flex-wrap:wrap;gap:7px;margin:9px 0}.toolbar button.active{background:#1d8f5a;border-color:#42e887}.chartControls{display:flex;gap:6px;align-items:center;margin:8px 0;flex-wrap:wrap}.chartControls button{padding:7px 10px}.sectionHint{font-size:12px;color:#9daabd}.split{display:grid;grid-template-columns:minmax(0,2fr) minmax(300px,1fr);gap:12px}@media(max-width:900px){.split{grid-template-columns:1fr}.chartWrap{height:360px}}@media(max-width:520px){body{padding:8px}.chartWrap{height:320px}.status{margin-left:0;width:100%}input{max-width:100%}}
</style></head>
<body><div class='wrap'>
<div class='top'><div><h1 style='margin-bottom:4px'>Universal Trading Bot</h1><div class='muted'>Volume Strategy FINAL Universal v15 · TradingView independent</div></div><span id='healthBadge' class='headerBadge muted'>HEALTH 확인 중</span><span id='readyBadge' class='headerBadge muted'>LIVE READINESS 확인 중</span></div>

<div class='bar section'><b>서버 / LIVE 사전점검</b><div class='row' style='margin-top:9px'><button onclick='refreshHealth()'>Health 새로고침</button><button onclick='refreshReadiness()'>Bitget Readiness 점검</button><span id='diagStatus' class='muted'></span></div><div id='diagnostics' class='metrics' style='margin-top:10px'></div></div>

<div class='bar'>
<b>시장 차트 / 거래 기록</b><div class='muted' style='margin-top:4px'>최신 봉부터 즉시 표시 · 차트를 과거 방향으로 밀면 저장된 이전 봉을 자동 로딩</div>
<div class='row' style='margin-top:10px'><input id='symbol' value='ETH/USDT:USDT' placeholder='심볼'><select id='asset'><option value='crypto'>Crypto</option><option value='stock'>Stock</option><option value='etf'>ETF</option></select><select id='exchange'><option>bitget</option><option>binance</option><option>okx</option><option>bybit</option></select><select id='tf'><option>5m</option><option>15m</option><option>1h</option><option>4h</option><option>1d</option></select><select id='mode'><option value='ALL'>전체 거래</option><option value='BACKTEST'>BACKTEST</option><option value='PAPER'>PAPER</option><option value='LIVE'>LIVE</option></select></div>
<div class='row' style='margin-top:8px'><label>시작 <input id='start' type='date'></label><label>종료 <input id='end' type='date'></label><button onclick='loadMarket()'>차트/기록 불러오기</button><span id='chartStatus' class='status muted'></span></div>
<div class='toolbar'><button class='ghost' onclick='periodDays(1,this)'>1D</button><button class='ghost' onclick='periodDays(7,this)'>7D</button><button class='ghost' onclick='periodDays(30,this)'>30D</button><button class='ghost' onclick='periodDays(90,this)'>3M</button><button class='ghost active' onclick='periodDays(365,this)'>1Y</button></div>
<div class='chartControls'><button class='ghost' onclick='zoomChart(0.8)'>＋ 확대</button><button class='ghost' onclick='zoomChart(1.25)'>－ 축소</button><button class='ghost' onclick='goLatest()'>최신으로</button><span class='sectionHint'>모바일/PC: 차트를 좌우로 드래그 · 과거 끝에 가까워지면 다음 봉 자동 로딩</span></div>
<div id='historyMetrics' class='metrics' style='margin-bottom:10px'></div>
<div class='chartWrap'><canvas id='marketChart'></canvas></div>
<div class='muted' id='chartLegend' style='margin-top:7px'>▲ LONG 진입 · ▼ SHORT 진입 · ● TP/SL/청산</div>
</div>

<div class='card'><b>통합 거래 기록</b><div class='muted' style='margin:4px 0 8px'>시작일 기준 저장 기록 · BACKTEST/PAPER/LIVE 필터 가능</div><div style='overflow:auto;max-height:430px'><table><thead><tr><th>모드</th><th>진입 시각</th><th>청산 시각</th><th>방향</th><th>평균 진입</th><th>청산</th><th>수량</th><th>비용</th><th>순손익</th><th>수익률</th><th>사유</th></tr></thead><tbody id='historyTrades'></tbody></table></div></div>

<div class='bar'><b>백테스트 / 과거 데이터</b><div class='muted' style='margin-top:4px'>Crypto: 4개 선물거래소 정규화 거래량 · Stock/ETF: 종목 자체 거래량 · 수수료/슬리피지 반영</div><div class='row' style='margin-top:9px'><button onclick='runBT()'>현재 선택 조건으로 백테스트</button><span id='status' class='status muted'></span></div></div>

<div id='bt' style='display:none'><div class='metrics' id='metrics'></div><div class='card'><b>Equity Curve (비용 반영)</b><canvas id='equity' style='width:100%;height:280px'></canvas></div><div class='card'><b>이번 백테스트 거래 내역</b><div style='overflow:auto'><table><thead><tr><th>진입</th><th>청산</th><th>방향</th><th>평균 진입</th><th>청산가</th><th>총손익</th><th>비용</th><th>순손익</th><th>순손익%</th><th>사유</th></tr></thead><tbody id='trades'></tbody></table></div></div></div>

<div class='section'><h2>실시간 전략 상태</h2><div id='grid' class='grid'></div></div>
<script>
const esc=s=>String(s??'-').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
let lastEquity=[],lastCandles=[],lastHistory=[];
let viewEnd=0,visibleBars=110,hasOlder=false,nextBefore=null,loadingOlder=false;
let dragStartX=0,dragStartY=0,dragStartEnd=0,dragging=false,horizontalDrag=false;
const PAGE_SIZE=600;
function metric(n,v,cls=''){return `<div class='metricbox'><div class='muted'>${n}</div><div class='big ${cls}'>${v}</div></div>`}
function sourceText(src){const names=['binance','bitget','okx','bybit'];return names.map(n=>{const s=src?.[n];return `${n.toUpperCase()}:${s?(s.status==='OK'?s.mode:'FAIL'):'-'}`}).join(' · ')}
function setDefaultDates(){const end=new Date(),start=new Date(end);start.setUTCFullYear(start.getUTCFullYear()-1);const f=d=>d.toISOString().slice(0,10);document.getElementById('start').value=f(start);document.getElementById('end').value=f(end)}
function periodDays(days,btn){document.querySelectorAll('.toolbar button').forEach(b=>b.classList.remove('active'));if(btn)btn.classList.add('active');const e=new Date(),s=new Date(e);s.setUTCDate(s.getUTCDate()-days);document.getElementById('end').value=e.toISOString().slice(0,10);document.getElementById('start').value=s.toISOString().slice(0,10);loadMarket()}
function drawEquity(data){lastEquity=data||[];const c=document.getElementById('equity'),dpr=devicePixelRatio||1,w=c.clientWidth||900,h=280;c.width=w*dpr;c.height=h*dpr;const x=c.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,w,h);if(!data||data.length<2){x.fillStyle='#9daabd';x.fillText('Equity 데이터 없음',15,30);return}const vals=data.map(a=>Number(a.equity??0)).filter(Number.isFinite);if(vals.length<2)return;const min=Math.min(...vals),max=Math.max(...vals),pad=25;const px=i=>pad+i*(w-pad*2)/(vals.length-1),py=v=>h-pad-(v-min)*(h-pad*2)/Math.max(1,max-min);x.strokeStyle='#556579';x.beginPath();x.moveTo(pad,pad);x.lineTo(pad,h-pad);x.lineTo(w-pad,h-pad);x.stroke();x.strokeStyle='#42e887';x.lineWidth=2;x.beginPath();vals.forEach((v,i)=>i?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v)));x.stroke()}
function viewport(){const end=Math.max(0,Math.min(viewEnd||lastCandles.length,lastCandles.length));const start=Math.max(0,end-visibleBars);return {start,end,data:lastCandles.slice(start,end)}}
function drawMarket(){const c=document.getElementById('marketChart'),dpr=devicePixelRatio||1,w=c.clientWidth||1000,h=c.clientHeight||430;c.width=w*dpr;c.height=h*dpr;const x=c.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,w,h);const vp=viewport(),data=vp.data;if(!data.length){x.fillStyle='#9daabd';x.font='14px system-ui';x.fillText('저장된 차트 데이터가 없습니다.',18,30);return}const padL=58,padR=18,padT=18,padB=34,chartH=h-padT-padB;const lows=data.map(a=>+a.low),highs=data.map(a=>+a.high),lo=Math.min(...lows),hi=Math.max(...highs),span=Math.max(1e-9,hi-lo);const py=v=>padT+(hi-v)/span*chartH,step=(w-padL-padR)/Math.max(1,data.length),body=Math.max(1,Math.min(8,step*.68));x.strokeStyle='#263445';x.fillStyle='#9daabd';x.font='11px system-ui';for(let k=0;k<=4;k++){const y=padT+chartH*k/4,p=hi-span*k/4;x.beginPath();x.moveTo(padL,y);x.lineTo(w-padR,y);x.stroke();x.fillText(p.toFixed(p>100?1:3),3,y+4)}data.forEach((a,i)=>{const cx=padL+(i+.5)*step,up=+a.close>=+a.open,col=up?'#42e887':'#ff6677';x.strokeStyle=col;x.fillStyle=col;x.beginPath();x.moveTo(cx,py(+a.high));x.lineTo(cx,py(+a.low));x.stroke();const yo=py(+a.open),yc=py(+a.close);x.fillRect(cx-body/2,Math.min(yo,yc),body,Math.max(1,Math.abs(yc-yo)))});const first=Date.parse(data[0].timestamp),last=Date.parse(data[data.length-1].timestamp),range=Math.max(1,last-first);function mx(t){return padL+(Date.parse(t)-first)/range*(w-padL-padR)}lastHistory.forEach(t=>{const et=t.entry_time,xt=t.exit_time;if(et){const xx=mx(et);if(xx>=padL&&xx<=w-padR){const yy=py(+(t.avg_entry_price||t.entry_price||lo));x.fillStyle=t.side==='LONG'?'#42e887':'#ff6677';x.beginPath();if(t.side==='LONG'){x.moveTo(xx,yy-8);x.lineTo(xx-5,yy+2);x.lineTo(xx+5,yy+2)}else{x.moveTo(xx,yy+8);x.lineTo(xx-5,yy-2);x.lineTo(xx+5,yy-2)}x.closePath();x.fill()}}if(xt){const xx=mx(xt);if(xx>=padL&&xx<=w-padR){const yy=py(+(t.exit_price||lo));x.fillStyle=t.reason==='TP'?'#42e887':t.reason==='SL'?'#ffcc66':'#eef2f7';x.beginPath();x.arc(xx,yy,4,0,Math.PI*2);x.fill()}}});x.fillStyle='#9daabd';x.fillText(new Date(first).toLocaleString(),padL,h-9);const label=new Date(last).toLocaleString(),tw=x.measureText(label).width;x.fillText(label,w-padR-tw,h-9);updateChartStatus()}
function updateChartStatus(){const s=document.getElementById('chartStatus'),vp=viewport();if(!lastCandles.length)return;const a=vp.data[0]?.timestamp,b=vp.data[vp.data.length-1]?.timestamp;s.textContent=`로드 ${lastCandles.length}봉 · 화면 ${vp.data.length}봉 · ${a?new Date(a).toLocaleString():''} → ${b?new Date(b).toLocaleString():''}${hasOlder?' · 과거 자동로딩':' · 시작일 도달'}`;s.className='status ok'}
function chartQuery(before){const q=new URLSearchParams({symbol:document.getElementById('symbol').value,exchange:document.getElementById('exchange').value,timeframe:document.getElementById('tf').value,asset_class:document.getElementById('asset').value,start:document.getElementById('start').value,page_size:String(PAGE_SIZE)});if(before)q.set('before',before);return q}
async function fetchCandlePage(before){const r=await fetch('/api/candles-page?'+chartQuery(before));const d=await r.json();if(!r.ok)throw Error(d.detail||'차트 오류');return d}
async function loadOlderPage(){if(loadingOlder||!hasOlder||!nextBefore)return;loadingOlder=true;const oldCount=lastCandles.length,oldEnd=viewEnd;try{const d=await fetchCandlePage(nextBefore),seen=new Set(lastCandles.map(c=>c.timestamp)),older=(d.candles||[]).filter(c=>!seen.has(c.timestamp));if(older.length){lastCandles=older.concat(lastCandles);viewEnd=oldEnd+older.length}else viewEnd=oldEnd;hasOlder=!!d.has_more;nextBefore=d.next_before||null;drawMarket()}catch(e){const s=document.getElementById('chartStatus');s.textContent='과거 봉 로딩 오류: '+e.message;s.className='status error'}finally{loadingOlder=false;if(lastCandles.length===oldCount&&hasOlder&&nextBefore)setTimeout(loadOlderPage,50)}}
function maybeLoadOlder(){const vp=viewport();if(hasOlder&&vp.start<Math.max(30,Math.floor(visibleBars*.35)))loadOlderPage()}
function goLatest(){viewEnd=lastCandles.length;drawMarket()}
function zoomChart(mult){visibleBars=Math.max(35,Math.min(320,Math.round(visibleBars*mult)));drawMarket();maybeLoadOlder()}
async function loadMarket(){const s=document.getElementById('chartStatus');s.textContent='최신 봉 로딩...';s.className='status muted';lastCandles=[];viewEnd=0;hasOlder=false;nextBefore=null;const tq=new URLSearchParams({symbol:document.getElementById('symbol').value,mode:document.getElementById('mode').value,start:document.getElementById('start').value,end:document.getElementById('end').value,limit:'3000'});try{const before=document.getElementById('end').value||null;const [cdResp,trResp]=await Promise.all([fetchCandlePage(before),fetch('/api/trades?'+tq)]),td=await trResp.json();if(!trResp.ok)throw Error(td.detail||'거래기록 오류');lastCandles=cdResp.candles||[];viewEnd=lastCandles.length;hasOlder=!!cdResp.has_more;nextBefore=cdResp.next_before||null;lastHistory=td.trades||[];const sm=td.summary||{},pf=sm.profit_factor==null?'-':Number(sm.profit_factor).toFixed(2);document.getElementById('historyMetrics').innerHTML=metric('거래',sm.trades||0)+metric('승리',sm.wins||0)+metric('승률',Number(sm.win_rate||0).toFixed(2)+'%')+metric('누적 순손익',Number(sm.pnl||0).toFixed(2),Number(sm.pnl)>=0?'good':'bad')+metric('PF',pf)+metric('로드된 봉',lastCandles.length)+metric('화면 봉',Math.min(visibleBars,lastCandles.length));document.getElementById('historyTrades').innerHTML=lastHistory.map(t=>`<tr><td>${esc(t.mode)}</td><td>${esc(t.entry_time||'-')}</td><td>${esc(t.exit_time||'-')}</td><td>${esc(t.side)}</td><td>${Number(t.avg_entry_price||t.entry_price||0).toFixed(4)}</td><td>${Number(t.exit_price||0).toFixed(4)}</td><td>${Number(t.qty||0).toFixed(6)}</td><td class='warn'>${Number(t.cost||0).toFixed(2)}</td><td class='${Number(t.pnl)>=0?'good':'bad'}'>${Number(t.pnl||0).toFixed(2)}</td><td>${Number(t.pnl_percent||0).toFixed(3)}%</td><td>${esc(t.reason||'')}</td></tr>`).join('');drawMarket()}catch(e){s.textContent='오류: '+e.message;s.className='status error';lastCandles=[];drawMarket()}}
async function refreshHealth(){const badge=document.getElementById('healthBadge');try{const r=await fetch('/health'),d=await r.json();badge.textContent='HEALTH '+String(d.status||'unknown').toUpperCase();badge.className='headerBadge '+(d.status==='ok'?'good':d.status==='degraded'?'warn':'bad');document.getElementById('diagStatus').textContent=(d.errors||[]).join(' | ')||''}catch(e){badge.textContent='HEALTH ERROR';badge.className='headerBadge bad'}}
async function refreshReadiness(){const badge=document.getElementById('readyBadge'),box=document.getElementById('diagnostics');try{const r=await fetch('/api/live-readiness'),d=await r.json();badge.textContent=d.ready?'LIVE READY':'LIVE NOT READY';badge.className='headerBadge '+(d.ready?'good':'warn');box.innerHTML=(d.checks||[]).map(c=>metric(esc(c.name),c.ok?'PASS':'FAIL',c.ok?'good':'bad')).join('')}catch(e){badge.textContent='READINESS ERROR';badge.className='headerBadge bad';box.innerHTML=metric('오류',esc(e.message),'bad')}}
async function runBT(){const status=document.getElementById('status');status.textContent='데이터 수집/백테스트 중...';status.className='status muted';const q={symbol:document.getElementById('symbol').value,asset_class:document.getElementById('asset').value,exchange:document.getElementById('exchange').value,timeframe:document.getElementById('tf').value,start:document.getElementById('start').value||null,end:document.getElementById('end').value||null};try{const r=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)}),d=await r.json();if(!r.ok)throw Error(d.detail||'백테스트 오류');document.getElementById('bt').style.display='block';const cls=v=>Number(v)>0?'good':Number(v)<0?'bad':'';document.getElementById('metrics').innerHTML=metric('심볼',esc(d.symbol))+metric('봉 수',esc(d.bars))+metric('거래',esc(d.trades))+metric('승률',Number(d.win_rate||0).toFixed(2)+'%',cls(d.win_rate-50))+metric('PF',d.profit_factor==null?'-':Number(d.profit_factor).toFixed(2))+metric('총손익',Number(d.gross_pnl||0).toFixed(2),cls(d.gross_pnl))+metric('추정비용',Number(d.estimated_costs||0).toFixed(2),'warn')+metric('순손익',Number(d.pnl||0).toFixed(2),cls(d.pnl))+metric('순수익률',Number(d.return_percent||0).toFixed(2)+'%',cls(d.return_percent))+metric('MDD',Number(d.max_drawdown_percent||0).toFixed(2)+'%','bad')+metric('Data Sources',esc(sourceText(d.volume_source_status||{})));drawEquity(d.equity_curve||[]);document.getElementById('trades').innerHTML=(d.trades_log||[]).slice().reverse().map(t=>`<tr><td>${esc(t.entry_time||'-')}</td><td>${esc(t.exit_time||'-')}</td><td>${esc(t.side)}</td><td>${Number(t.avg_entry_price||0).toFixed(4)}</td><td>${Number(t.exit_price||0).toFixed(4)}</td><td>${Number(t.gross_pnl||0).toFixed(2)}</td><td class='warn'>${Number(t.estimated_cost||0).toFixed(2)}</td><td class='${Number(t.pnl)>=0?'good':'bad'}'>${Number(t.pnl||0).toFixed(2)}</td><td>${Number(t.pnl_percent||0).toFixed(3)}%</td><td>${esc(t.reason)}</td></tr>`).join('');status.textContent=`완료 · Run ${esc(d.run_id||'')} · ${esc(d.data_start||'')} ~ ${esc(d.data_end||'')}`;status.className='status ok';await loadMarket()}catch(e){status.textContent='오류: '+e.message;status.className='status error'}}
async function refresh(){try{const r=await fetch('/api/state'),d=await r.json();document.getElementById('grid').innerHTML=d.symbols.map(x=>{const v=x.values||{},p=x.position||{},st=x.stats||{},s=x.live_safety||{};const liveEnabled=!!s.enabled;return `<div class='card'><h2>${esc(x.symbol)} <span class='pill'>${esc(x.timeframe||'')}</span></h2><div class='metric'><span>POSITION</span><b>${esc(p.side||'FLAT')}</b></div><div class='metric'><span>SIGNAL</span><b>${esc(x.signal||'NO SIGNAL')}</b></div><div class='metric'><span>Volume</span><b>x${esc(v.volume_ratio?.toFixed?.(2)??'-')}</b></div><div class='metric'><span>Volume Sources</span><b style='font-size:11px;text-align:right'>${esc(sourceText(x.volume_sources||{}))}</b></div><div class='metric'><span>ADX / RSI</span><b>${esc(v.adx?.toFixed?.(2)??'-')} / ${esc(v.rsi?.toFixed?.(2)??'-')}</b></div><div class='metric'><span>TP / SL</span><b>${esc(v.final_tp_percent??'-')}% / ${esc(v.final_sl_percent??'-')}%</b></div><div class='metric'><span>Realized / Open PnL</span><b>${esc(st.realized_pnl?.toFixed?.(2)??'0')} / ${esc(st.open_pnl?.toFixed?.(2)??'0')}</b></div><div class='metric'><span>Data time</span><b class='nowrap'>${esc(x.timestamp||'-')}</b></div><div class='metric'><span>LIVE SAFETY</span><b class='${s.halted?'bad':liveEnabled?'good':'muted'}'>${liveEnabled?(s.halted?'HALTED':'OK'):'PAPER'}</b></div><div class='metric'><span>Protection</span><b class='${!liveEnabled?'muted':s.protection_ok?'good':'bad'}'>${!liveEnabled?'N/A':s.protection_ok?'VERIFIED':'NOT VERIFIED'}</b></div><div class='muted'>${esc(s.reason||x.signal_reason||'')}${x.error?`<div class='error'>${esc(x.error)}</div>`:''}</div></div>`}).join('')}catch(e){document.getElementById('grid').innerHTML=`<div class='card error'>Dashboard API 오류: ${esc(e.message)}</div>`}}
function installChartGestures(){const c=document.getElementById('marketChart');c.addEventListener('pointerdown',e=>{dragging=true;horizontalDrag=false;dragStartX=e.clientX;dragStartY=e.clientY;dragStartEnd=viewEnd;c.classList.add('dragging')});c.addEventListener('pointermove',e=>{if(!dragging)return;const dx=e.clientX-dragStartX,dy=e.clientY-dragStartY;if(!horizontalDrag&&Math.abs(dx)>8&&Math.abs(dx)>Math.abs(dy)*1.2){horizontalDrag=true;c.setPointerCapture?.(e.pointerId)}if(!horizontalDrag)return;e.preventDefault();const barPx=Math.max(3,Math.min(12,c.clientWidth/Math.max(40,visibleBars))),delta=Math.round(-dx/barPx);viewEnd=Math.max(Math.min(visibleBars,lastCandles.length),Math.min(lastCandles.length,dragStartEnd+delta));drawMarket();maybeLoadOlder()});const stop=e=>{dragging=false;horizontalDrag=false;c.classList.remove('dragging');try{c.releasePointerCapture?.(e.pointerId)}catch(_){}};c.addEventListener('pointerup',stop);c.addEventListener('pointercancel',stop);c.addEventListener('wheel',e=>{e.preventDefault();zoomChart(e.deltaY<0?0.85:1.18)},{passive:false})}
setDefaultDates();installChartGestures();refreshHealth();refreshReadiness();refresh();loadMarket();setInterval(refresh,2000);setInterval(refreshHealth,10000);window.addEventListener('resize',()=>{drawEquity(lastEquity);drawMarket()});
</script></div></body></html>"""

    return app
