from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from universal_bot.backtest_service import run_symbol_backtest
from universal_bot.config import Settings
from universal_bot.fast_backtest import cache_available, default_cache_path, run_cached_symbol_backtest
from universal_bot.strategy import UniversalV15Strategy
from universal_bot.trade_history import TradeHistoryStore

STORE = Path("data/dashboard-strategy-settings.json")
FIELDS = (
    "volume_lookback", "volume_break_multiplier", "min_one_bar_vol", "max_one_bar_vol",
    "volatility_bars", "tp_vol_multiplier", "sl_vol_multiplier", "min_tp_percent",
    "max_tp_percent", "min_sl_percent", "max_sl_percent", "use_nbar_volatility_block",
    "nbar_volatility_bars", "max_nbar_volatility", "use_adx_filter", "adx_length",
    "adx_min", "adx_max", "use_rsi_filter", "rsi_length", "rsi_oversold_min",
    "rsi_oversold_max", "rsi_overbought_min", "rsi_overbought_max", "allow_long",
    "allow_short", "max_pyramiding", "cooldown_bars", "reentry_bars",
    "block_weekend", "excluded_hours", "order_percent_of_equity", "initial_capital", "backtest_fee_percent",
    "backtest_slippage_percent",
)


class StrategyUpdate(BaseModel):
    values: dict[str, Any]


class StrategyBacktest(BaseModel):
    symbol: str
    asset_class: str = "crypto"
    exchange: str = "bitget"
    timeframe: str = "5m"
    start: str | None = None
    end: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)


def _defaults() -> dict[str, Any]:
    s = Settings()
    return {k: getattr(s, k) for k in FIELDS}


def _load() -> dict[str, Any]:
    values = _defaults()
    if STORE.exists():
        try:
            saved = json.loads(STORE.read_text(encoding="utf-8"))
            values.update({k: v for k, v in saved.items() if k in FIELDS})
        except Exception:
            pass
    return values


def _validate(raw: dict[str, Any]) -> dict[str, Any]:
    unknown = set(raw) - set(FIELDS)
    if unknown:
        raise ValueError("unsupported setting(s): " + ", ".join(sorted(unknown)))
    base = Settings()
    candidate = base.model_copy(update={**_load(), **raw})
    out = {k: getattr(candidate, k) for k in FIELDS}
    if out["min_one_bar_vol"] > out["max_one_bar_vol"]:
        raise ValueError("1-bar min must be <= max")
    if out["min_tp_percent"] > out["max_tp_percent"]:
        raise ValueError("TP min must be <= max")
    if out["min_sl_percent"] > out["max_sl_percent"]:
        raise ValueError("SL min must be <= max")
    if out["adx_min"] > out["adx_max"]:
        raise ValueError("ADX min must be <= max")
    if out["rsi_oversold_min"] > out["rsi_oversold_max"]:
        raise ValueError("RSI oversold min must be <= max")
    if out["rsi_overbought_min"] > out["rsi_overbought_max"]:
        raise ValueError("RSI overbought min must be <= max")
    return out


def _apply(scanner, values: dict[str, Any]) -> None:
    for runtime in scanner.runtimes:
        new_settings = runtime.engine.settings.model_copy(update=values)
        runtime.engine.settings = new_settings
        runtime.engine.strategy = UniversalV15Strategy(new_settings)


def install_strategy_dashboard(app, scanner) -> None:
    _apply(scanner, _load())
    history = TradeHistoryStore()

    @app.get("/api/strategy-settings")
    def get_strategy_settings():
        return {"strategy": "Volume Strategy FINAL Universal v15", "values": _load(), "fields": list(FIELDS)}

    @app.get("/api/strategy-cache-status")
    def strategy_cache_status(symbol: str = "ETH/USDT:USDT", timeframe: str = "5m"):
        path = default_cache_path(symbol, timeframe)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "available": cache_available(symbol, timeframe),
            "database": str(path),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }

    @app.post("/api/strategy-settings")
    def save_strategy_settings(req: StrategyUpdate):
        try:
            values = _validate(req.values)
            STORE.parent.mkdir(parents=True, exist_ok=True)
            STORE.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
            _apply(scanner, values)
            return {"status": "ok", "values": values, "applied_runtimes": len(scanner.runtimes)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/strategy-backtest")
    def strategy_backtest(req: StrategyBacktest):
        try:
            overrides = _validate(req.values)
            if req.asset_class.lower() == "crypto" and cache_available(req.symbol, req.timeframe):
                result = run_cached_symbol_backtest(
                    req.symbol,
                    req.asset_class,
                    req.exchange,
                    req.timeframe,
                    req.start,
                    req.end,
                    overrides=overrides,
                )
                result["backtest_mode"] = "CACHE_ONLY"
                result["network_download"] = False
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                run_id = f"BT-{req.symbol}-{req.timeframe}-{stamp}"
                history.record_backtest(result, run_id=run_id, params=req.model_dump())
                result["run_id"] = run_id
                return result

            result = run_symbol_backtest(
                req.symbol,
                req.asset_class,
                req.exchange,
                req.timeframe,
                req.start,
                req.end,
                overrides=overrides,
            )
            result["backtest_mode"] = "SYNC_AND_BACKTEST"
            result["network_download"] = bool(result.get("inserted", 0))
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            run_id = f"BT-{req.symbol}-{req.timeframe}-{stamp}"
            history.record_backtest(result, run_id=run_id, params=req.model_dump())
            result["run_id"] = run_id
            return result
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/strategy", response_class=HTMLResponse)
    def strategy_page():
        return HTMLResponse(_HTML)


_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V15 Strategy Settings</title><style>*{box-sizing:border-box}body{margin:0;padding:14px;background:#0b0f14;color:#eef2f7;font-family:system-ui}.wrap{max-width:1200px;margin:auto}.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:14px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}.f{display:flex;flex-direction:column;gap:5px;color:#9daabd;font-size:12px}input,button{padding:10px;border-radius:8px;border:1px solid #556579;background:#0b0f14;color:#eef2f7}input[type=checkbox]{width:22px;height:22px}button{background:#2563a8;font-weight:800;cursor:pointer}.green{background:#1d8f5a}.muted{color:#9daabd}.status{padding:10px 0}.ok{color:#42e887}.bad{color:#ff6677}.warn{color:#ffcc66}a{color:#7db7ff}.result{white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:12px;overflow:auto}.pill{display:inline-block;padding:5px 8px;border-radius:999px;background:#0b0f14;border:1px solid #334155;margin:4px 4px 4px 0}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:8px;margin:12px 0}.metric{background:#0b0f14;border:1px solid #334155;border-radius:9px;padding:9px}.big{font-size:18px;font-weight:800}.chartWrap{height:430px;background:#07101d;border:1px solid #334155;border-radius:10px;overflow:hidden}.chartWrap canvas{width:100%;height:100%;touch-action:none}.good{color:#42e887}.tradebad{color:#ff6677}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:8px;border-bottom:1px solid #334155;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}</style></head><body><div class="wrap"><h1>V15 전략 설정</h1><div class="muted">저장 즉시 PAPER/LIVE 런타임에 적용 · 재시작 후에도 유지</div><div class="card"><div id="grid" class="grid"></div><div class="status" id="status"></div><button class="green" onclick="save()">전략 설정 저장 / 즉시 적용</button> <button onclick="resetDefaults()">기본값 불러오기</button> <a href="/">메인 대시보드</a></div><div class="card"><b>빠른 재백테스트</b><div class="muted" style="margin-top:6px">완성된 1년 캐시가 있으면 인터넷 재다운로드 없이 전체 5분봉으로 즉시 재계산합니다. 요청 종료일이 캐시보다 최신이면 결과의 실제 데이터 종료시각을 확인하세요.</div><div class="grid" style="margin-top:10px"><label class="f">심볼<input id="symbol" value="ETH/USDT:USDT" oninput="cacheStatus()"></label><label class="f">거래소<input id="exchange" value="bitget"></label><label class="f">타임프레임<input id="tf" value="5m" oninput="cacheStatus()"></label><label class="f">시작일<input id="start" type="date"></label><label class="f">종료일<input id="end" type="date"></label></div><div id="cache" class="status"></div><div class="status" id="btstatus"></div><button onclick="backtest()">현재 화면 값으로 빠른 재백테스트</button><div id="result" class="result"></div><div id="btmetrics" class="metrics"></div><div class="chartWrap"><canvas id="btchart"></canvas></div><div class="muted" style="margin-top:7px">마우스 휠/버튼으로 확대·축소 · 좌우 드래그 · ▲ LONG · ▼ SHORT · ● TP/SL 청산</div><div class="row" style="margin:9px 0"><button onclick="btZoom(.8)">＋ 확대</button><button onclick="btZoom(1.25)">－ 축소</button><button onclick="btLatest()">최신 구간</button></div><div style="overflow:auto;max-height:440px"><table><thead><tr><th>거래</th><th>진입</th><th>청산</th><th>방향</th><th>평균진입</th><th>청산가</th><th>수량</th><th>비용</th><th>순손익</th><th>수익률</th><th>사유</th></tr></thead><tbody id="bttrades"></tbody></table></div></div></div><script>let defaults={},types={};const labels={volume_lookback:'거래량 SMA 기간',volume_break_multiplier:'거래량 폭등 배수',min_one_bar_vol:'1봉 변동 최소 %',max_one_bar_vol:'1봉 변동 최대 %',volatility_bars:'변동성 기준 봉',tp_vol_multiplier:'TP 변동성 배수',sl_vol_multiplier:'SL 변동성 배수',min_tp_percent:'TP 최소 %',max_tp_percent:'TP 최대 %',min_sl_percent:'SL 최소 %',max_sl_percent:'SL 최대 %',use_nbar_volatility_block:'N-bar 필터 사용',nbar_volatility_bars:'N-bar 봉 수',max_nbar_volatility:'N-bar 최대 변동 %',use_adx_filter:'ADX 필터 사용',adx_length:'ADX 길이',adx_min:'ADX 최소',adx_max:'ADX 최대',use_rsi_filter:'RSI 필터 사용',rsi_length:'RSI 길이',rsi_oversold_min:'RSI 과매도 최소',rsi_oversold_max:'RSI 과매도 최대',rsi_overbought_min:'RSI 과매수 최소',rsi_overbought_max:'RSI 과매수 최대',allow_long:'LONG 허용',allow_short:'SHORT 허용',max_pyramiding:'최대 피라미딩',cooldown_bars:'쿨다운 봉',reentry_bars:'재진입 봉',block_weekend:'주말 차단',excluded_hours:'제외 시간 UTC',order_percent_of_equity:'진입 비중 %',initial_capital:'백테스트 초기자본',backtest_fee_percent:'수수료 %/side',backtest_slippage_percent:'슬리피지 %/side'};function render(v){defaults=v;let h='';for(const[k,x]of Object.entries(v)){types[k]=typeof x;if(typeof x==='boolean')h+=`<label class=f>${labels[k]||k}<input id="p_${k}" type=checkbox ${x?'checked':''}></label>`;else h+=`<label class=f>${labels[k]||k}<input id="p_${k}" type="${typeof x==='number'?'number':'text'}" ${typeof x==='number'?'step=any':''} value="${x}"></label>`}grid.innerHTML=h}function values(){let o={};for(const k of Object.keys(defaults)){let e=document.getElementById('p_'+k);o[k]=types[k]==='boolean'?e.checked:types[k]==='number'?Number(e.value):e.value}return o}async function cacheStatus(){try{let q=new URLSearchParams({symbol:symbol.value,timeframe:tf.value});let r=await fetch('/api/strategy-cache-status?'+q),d=await r.json();cache.textContent=d.available?`✅ CACHE ONLY 사용 가능 · ${(d.size_bytes/1024/1024).toFixed(1)} MB · ${d.database}`:`⚠️ 완성 캐시 없음 · 최초 백테스트는 데이터 수집이 필요함`;cache.className='status '+(d.available?'ok':'warn')}catch(e){cache.textContent='캐시 상태 확인 실패';cache.className='status bad'}}async function load(){let d=await(await fetch('/api/strategy-settings')).json();render(d.values);let e=new Date(),s=new Date(e);s.setUTCFullYear(s.getUTCFullYear()-1);end.value=e.toISOString().slice(0,10);start.value=s.toISOString().slice(0,10);cacheStatus()}async function save(){status.textContent='저장 중...';let r=await fetch('/api/strategy-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values:values()})}),d=await r.json();status.textContent=r.ok?'저장 완료 · 실시간 전략에 즉시 적용됨':'오류: '+d.detail;status.className='status '+(r.ok?'ok':'bad')}async function resetDefaults(){location.reload()}let btCandles=[],btTrades=[],btVisible=140,btEnd=0,btDrag=false,btDragX=0,btDragEnd=0;function mbox(n,v,cl=''){return `<div class="metric"><div class="muted">${n}</div><div class="big ${cl}">${v}</div></div>`}async function loadBtCandles(){const q=new URLSearchParams({symbol:symbol.value,exchange:exchange.value,timeframe:tf.value,asset_class:'crypto',start:start.value,end:end.value,max_points:'5000'});const r=await fetch('/api/candles?'+q),d=await r.json();btCandles=d.candles||[];btEnd=btCandles.length;drawBtChart()}function btViewport(){const e=Math.max(0,Math.min(btEnd||btCandles.length,btCandles.length)),s=Math.max(0,e-btVisible);return {s,e,a:btCandles.slice(s,e)}}function btZoom(x){btVisible=Math.max(30,Math.min(500,Math.round(btVisible*x)));drawBtChart()}function btLatest(){btEnd=btCandles.length;drawBtChart()}function drawBtChart(){const c=document.getElementById('btchart'),d=devicePixelRatio||1,w=c.clientWidth||900,h=c.clientHeight||430;c.width=w*d;c.height=h*d;const g=c.getContext('2d');g.setTransform(d,0,0,d,0,0);g.clearRect(0,0,w,h);const v=btViewport(),a=v.a;if(!a.length){g.fillStyle='#9daabd';g.fillText('차트 데이터 없음',18,30);return}const L=58,R=16,T=18,B=32,hh=h-T-B,lo=Math.min(...a.map(x=>+x.low)),hi=Math.max(...a.map(x=>+x.high)),sp=Math.max(1e-9,hi-lo),py=p=>T+(hi-p)/sp*hh,step=(w-L-R)/a.length,body=Math.max(1,Math.min(8,step*.68));g.font='11px system-ui';for(let k=0;k<=4;k++){let y=T+hh*k/4,p=hi-sp*k/4;g.strokeStyle='#263445';g.beginPath();g.moveTo(L,y);g.lineTo(w-R,y);g.stroke();g.fillStyle='#9daabd';g.fillText(p.toFixed(p>100?1:3),3,y+4)}a.forEach((x,i)=>{const xx=L+(i+.5)*step,up=+x.close>=+x.open,col=up?'#42e887':'#ff6677';g.strokeStyle=col;g.fillStyle=col;g.beginPath();g.moveTo(xx,py(+x.high));g.lineTo(xx,py(+x.low));g.stroke();let yo=py(+x.open),yc=py(+x.close);g.fillRect(xx-body/2,Math.min(yo,yc),body,Math.max(1,Math.abs(yc-yo)))});const t0=Date.parse(a[0].timestamp),t1=Date.parse(a[a.length-1].timestamp),mx=t=>L+(Date.parse(t)-t0)/Math.max(1,t1-t0)*(w-L-R);btTrades.forEach(t=>{let x=mx(t.entry_time);if(x>=L&&x<=w-R){let y=py(+(t.avg_entry_price||t.entry_price));g.fillStyle=t.side==='LONG'?'#42e887':'#ff6677';g.beginPath();if(t.side==='LONG'){g.moveTo(x,y-9);g.lineTo(x-6,y+3);g.lineTo(x+6,y+3)}else{g.moveTo(x,y+9);g.lineTo(x-6,y-3);g.lineTo(x+6,y-3)}g.closePath();g.fill()}x=mx(t.exit_time);if(x>=L&&x<=w-R){let y=py(+t.exit_price);g.fillStyle=t.reason==='TP'?'#42e887':'#ffcc66';g.beginPath();g.arc(x,y,5,0,Math.PI*2);g.fill()}})}function renderBt(d){btTrades=d.trades_log||[];const pf=d.profit_factor==null?'-':Number(d.profit_factor).toFixed(2);btmetrics.innerHTML=mbox('거래',d.trades)+mbox('승률',Number(d.win_rate).toFixed(2)+'%')+mbox('PF',pf)+mbox('순손익',Number(d.pnl).toFixed(2),Number(d.pnl)>=0?'good':'tradebad')+mbox('수익률',Number(d.return_percent).toFixed(3)+'%')+mbox('MDD',Number(d.max_drawdown_percent).toFixed(3)+'%','tradebad')+mbox('비용',Number(d.estimated_costs).toFixed(2))+mbox('봉',d.bars);bttrades.innerHTML=btTrades.slice().reverse().map(t=>`<tr><td>${t.trade||'-'}</td><td>${t.entry_time||'-'}</td><td>${t.exit_time||'-'}</td><td>${t.side}</td><td>${Number(t.avg_entry_price||0).toFixed(4)}</td><td>${Number(t.exit_price||0).toFixed(4)}</td><td>${Number(t.qty||0).toFixed(6)}</td><td>${Number(t.estimated_cost||0).toFixed(2)}</td><td class="${Number(t.pnl)>=0?'good':'tradebad'}">${Number(t.pnl||0).toFixed(2)}</td><td>${Number(t.pnl_percent||0).toFixed(3)}%</td><td>${t.reason||''}</td></tr>`).join('');result.textContent=`Run ${d.run_id||'-'} · ${d.backtest_mode||'-'} · 실제 데이터 ${d.data_start} ~ ${d.data_end}`;loadBtCandles()}function installBtGestures(){const c=document.getElementById('btchart');c.addEventListener('pointerdown',e=>{btDrag=true;btDragX=e.clientX;btDragEnd=btEnd;c.setPointerCapture?.(e.pointerId)});c.addEventListener('pointermove',e=>{if(!btDrag)return;e.preventDefault();btEnd=Math.max(btVisible,Math.min(btCandles.length,btDragEnd-Math.round((e.clientX-btDragX)/Math.max(3,c.clientWidth/btVisible))));drawBtChart()});const stop=e=>{btDrag=false;try{c.releasePointerCapture?.(e.pointerId)}catch(_){}};c.addEventListener('pointerup',stop);c.addEventListener('pointercancel',stop);c.addEventListener('wheel',e=>{e.preventDefault();btZoom(e.deltaY<0?.85:1.18)},{passive:false})}installBtGestures();window.addEventListener('resize',drawBtChart);async function backtest(){btstatus.textContent='백테스트 중...';btstatus.className='status warn';result.textContent='';let q={symbol:symbol.value,asset_class:'crypto',exchange:exchange.value,timeframe:tf.value,start:start.value||null,end:end.value||null,values:values()};let t=performance.now(),r=await fetch('/api/strategy-backtest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)}),d=await r.json();let sec=(performance.now()-t)/1000;if(!r.ok){btstatus.textContent='오류: '+d.detail;btstatus.className='status bad';return}btstatus.textContent=`완료 · ${sec.toFixed(1)}초 · ${d.backtest_mode||'-'}`;btstatus.className='status ok';renderBt(d)`}load();</script></body></html>'''
