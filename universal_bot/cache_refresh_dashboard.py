from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from universal_bot.cache_refresh import refresh_cached_symbol
from universal_bot.fast_backtest import cache_available


def install_cache_refresh_dashboard(app: FastAPI) -> None:
    @app.post("/api/strategy-cache-refresh")
    def strategy_cache_refresh(symbol: str = "ETH/USDT:USDT", timeframe: str = "5m"):
        try:
            if not cache_available(symbol, timeframe):
                raise ValueError("완성된 캐시가 없습니다. 최초 1년 캐시 생성이 먼저 필요합니다.")
            return refresh_cached_symbol(symbol, timeframe)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/strategy/cache", response_class=HTMLResponse)
    def cache_refresh_page():
        return HTMLResponse(_HTML)


_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cache Refresh</title><style>*{box-sizing:border-box}body{margin:0;padding:16px;background:#0b0f14;color:#eef2f7;font-family:system-ui}.wrap{max-width:760px;margin:auto}.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:16px;margin:12px 0}.row{display:flex;flex-wrap:wrap;gap:8px}input,button{padding:11px;border-radius:8px;border:1px solid #556579;background:#0b0f14;color:#eef2f7}input{flex:1;min-width:180px}button{background:#2563a8;font-weight:800}.muted{color:#9daabd}.ok{color:#42e887}.bad{color:#ff6677}.warn{color:#ffcc66}pre{white-space:pre-wrap;overflow:auto;font-size:12px}a{color:#7db7ff}</style></head><body><div class="wrap"><h1>최신 확정봉 캐시 갱신</h1><div class="card"><div class="muted">기존 1년 데이터를 다시 받지 않고 캐시 끝 이후의 누락 구간만 추가합니다. Bitget/OKX는 최신 확정봉까지, 미국 서버에서 직접 차단되는 Binance/Bybit은 거래소 공식 일별 아카이브가 공개된 범위까지만 갱신됩니다.</div><div class="row" style="margin-top:12px"><input id="symbol" value="ETH/USDT:USDT"><input id="tf" value="5m"><button onclick="refreshCache()">⚡ 최신 확정봉만 갱신</button></div><div id="status" class="warn" style="margin-top:12px"></div><pre id="result"></pre><p><a href="/strategy">← 전략 수치 변경</a> · <a href="/">메인 대시보드</a></p></div></div><script>async function refreshCache(){status.textContent='갱신 중... 기존 과거 데이터는 재다운로드하지 않습니다.';result.textContent='';let q=new URLSearchParams({symbol:symbol.value,timeframe:tf.value});let t=performance.now(),r=await fetch('/api/strategy-cache-refresh?'+q,{method:'POST'}),d=await r.json(),sec=(performance.now()-t)/1000;if(!r.ok){status.textContent='오류: '+d.detail;status.className='bad';return}status.textContent=`완료 · ${sec.toFixed(1)}초 · 신규 ${d.inserted}봉`;status.className='ok';result.textContent=JSON.stringify(d,null,2)}</script></body></html>'''
