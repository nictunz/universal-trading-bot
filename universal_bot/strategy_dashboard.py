from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from universal_bot.backtest_service import run_symbol_backtest
from universal_bot.config import Settings
from universal_bot.strategy import UniversalV15Strategy

STORE = Path("data/dashboard-strategy-settings.json")
FIELDS = (
    "volume_lookback", "volume_break_multiplier", "min_one_bar_vol", "max_one_bar_vol",
    "volatility_bars", "tp_vol_multiplier", "sl_vol_multiplier", "min_tp_percent",
    "max_tp_percent", "min_sl_percent", "max_sl_percent", "use_nbar_volatility_block",
    "nbar_volatility_bars", "max_nbar_volatility", "use_adx_filter", "adx_length",
    "adx_min", "adx_max", "use_rsi_filter", "rsi_length", "rsi_oversold_min",
    "rsi_oversold_max", "rsi_overbought_min", "rsi_overbought_max", "allow_long",
    "allow_short", "max_pyramiding", "cooldown_bars", "reentry_bars",
    "block_weekend", "excluded_hours", "order_percent_of_equity", "backtest_fee_percent",
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
    values: dict[str, Any] = {}

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
    if out["min_one_bar_vol"] > out["max_one_bar_vol"]: raise ValueError("1-bar min must be <= max")
    if out["min_tp_percent"] > out["max_tp_percent"]: raise ValueError("TP min must be <= max")
    if out["min_sl_percent"] > out["max_sl_percent"]: raise ValueError("SL min must be <= max")
    if out["adx_min"] > out["adx_max"]: raise ValueError("ADX min must be <= max")
    if out["rsi_oversold_min"] > out["rsi_oversold_max"]: raise ValueError("RSI oversold min must be <= max")
    if out["rsi_overbought_min"] > out["rsi_overbought_max"]: raise ValueError("RSI overbought min must be <= max")
    return out

def _apply(scanner, values: dict[str, Any]) -> None:
    for runtime in scanner.runtimes:
        new_settings = runtime.engine.settings.model_copy(update=values)
        runtime.engine.settings = new_settings
        runtime.engine.strategy = UniversalV15Strategy(new_settings)

def install_strategy_dashboard(app, scanner) -> None:
    # Apply saved controls on startup, so dashboard changes survive restarts.
    _apply(scanner, _load())

    @app.get("/api/strategy-settings")
    def get_strategy_settings():
        return {"strategy": "Volume Strategy FINAL Universal v15", "values": _load(), "fields": list(FIELDS)}

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
            return run_symbol_backtest(req.symbol, req.asset_class, req.exchange, req.timeframe, req.start, req.end, overrides=overrides)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/strategy", response_class=HTMLResponse)
    def strategy_page():
        return HTMLResponse(_HTML)

_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V15 Strategy Settings</title><style>*{box-sizing:border-box}body{margin:0;padding:14px;background:#0b0f14;color:#eef2f7;font-family:system-ui}.wrap{max-width:1200px;margin:auto}.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:14px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}.f{display:flex;flex-direction:column;gap:5px;color:#9daabd;font-size:12px}input,button{padding:10px;border-radius:8px;border:1px solid #556579;background:#0b0f14;color:#eef2f7}input[type=checkbox]{width:22px;height:22px}button{background:#2563a8;font-weight:800;cursor:pointer}.green{background:#1d8f5a}.muted{color:#9daabd}.status{padding:10px 0}.ok{color:#42e887}.bad{color:#ff6677}a{color:#7db7ff}.result{white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:12px;overflow:auto}</style></head><body><div class="wrap"><h1>V15 전략 설정</h1><div class="muted">저장 즉시 PAPER/LIVE 런타임에 적용 · 재시작 후에도 유지 · 백테스트는 저장된 OHLCV 캐시를 재사용</div><div class="card"><div id="grid" class="grid"></div><div class="status" id="status"></div><button class="green" onclick="save()">전략 설정 저장 / 즉시 적용</button> <button onclick="resetDefaults()">기본값 불러오기</button> <a href="/">메인 대시보드</a></div><div class="card"><b>빠른 재백테스트</b><div class="grid" style="margin-top:10px"><label class="f">심볼<input id="symbol" value="ETH/USDT:USDT"></label><label class="f">거래소<input id="exchange" value="bitget"></label><label class="f">타임프레임<input id="tf" value="5m"></label><label class="f">시작일<input id="start" type="date"></label><label class="f">종료일<input id="end" type="date"></label></div><div class="status" id="btstatus"></div><button onclick="backtest()">현재 화면 값으로 백테스트</button><div id="result" class="result"></div></div></div><script>let defaults={},types={};const labels={volume_lookback:'거래량 SMA 기간',volume_break_multiplier:'거래량 폭등 배수',min_one_bar_vol:'1봉 변동 최소 %',max_one_bar_vol:'1봉 변동 최대 %',volatility_bars:'변동성 기준 봉',tp_vol_multiplier:'TP 변동성 배수',sl_vol_multiplier:'SL 변동성 배수',min_tp_percent:'TP 최소 %',max_tp_percent:'TP 최대 %',min_sl_percent:'SL 최소 %',max_sl_percent:'SL 최대 %',use_nbar_volatility_block:'N-bar 필터 사용',nbar_volatility_bars:'N-bar 봉 수',max_nbar_volatility:'N-bar 최대 변동 %',use_adx_filter:'ADX 필터 사용',adx_length:'ADX 길이',adx_min:'ADX 최소',adx_max:'ADX 최대',use_rsi_filter:'RSI 필터 사용',rsi_length:'RSI 길이',rsi_oversold_min:'RSI 과매도 최소',rsi_oversold_max:'RSI 과매도 최대',rsi_overbought_min:'RSI 과매수 최소',rsi_overbought_max:'RSI 과매수 최대',allow_long:'LONG 허용',allow_short:'SHORT 허용',max_pyramiding:'최대 피라미딩',cooldown_bars:'쿨다운 봉',reentry_bars:'재진입 봉',block_weekend:'주말 차단',excluded_hours:'제외 시간 UTC',order_percent_of_equity:'진입 비중 %',backtest_fee_percent:'수수료 %/side',backtest_slippage_percent:'슬리피지 %/side'};function render(v){defaults=v;let h='';for(const[k,x]of Object.entries(v)){types[k]=typeof x;if(typeof x==='boolean')h+=`<label class=f>${labels[k]||k}<input id="p_${k}" type=checkbox ${x?'checked':''}></label>`;else h+=`<label class=f>${labels[k]||k}<input id="p_${k}" type="${typeof x==='number'?'number':'text'}" ${typeof x==='number'?'step=any':''} value="${x}"></label>`}grid.innerHTML=h}function values(){let o={};for(const k of Object.keys(defaults)){let e=document.getElementById('p_'+k);o[k]=types[k]==='boolean'?e.checked:types[k]==='number'?Number(e.value):e.value}return o}async function load(){let d=await(await fetch('/api/strategy-settings')).json();render(d.values);let e=new Date(),s=new Date(e);s.setUTCFullYear(s.getUTCFullYear()-1);end.value=e.toISOString().slice(0,10);start.value=s.toISOString().slice(0,10)}async function save(){status.textContent='저장 중...';let r=await fetch('/api/strategy-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values:values()})}),d=await r.json();status.textContent=r.ok?'저장 완료 · 실시간 전략에 즉시 적용됨':'오류: '+d.detail;status.className='status '+(r.ok?'ok':'bad')}async function resetDefaults(){location.reload()}async function backtest(){btstatus.textContent='백테스트 중...';result.textContent='';let q={symbol:symbol.value,asset_class:'crypto',exchange:exchange.value,timeframe:tf.value,start:start.value||null,end:end.value||null,values:values()};let r=await fetch('/api/strategy-backtest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)}),d=await r.json();if(!r.ok){btstatus.textContent='오류: '+d.detail;btstatus.className='status bad';return}btstatus.textContent='완료';btstatus.className='status ok';result.textContent=`거래 ${d.trades} | 승률 ${Number(d.win_rate).toFixed(2)}% | PF ${d.profit_factor==null?'-':Number(d.profit_factor).toFixed(2)} | 순손익 ${Number(d.pnl).toFixed(2)} | 수익률 ${Number(d.return_percent).toFixed(3)}% | MDD ${Number(d.max_drawdown_percent).toFixed(3)}% | 신규수집 ${d.inserted}봉\n데이터 ${d.data_start} ~ ${d.data_end}`}load();</script></body></html>'''
