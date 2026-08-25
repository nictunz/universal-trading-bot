from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

PUBLIC_DASHBOARD_URL = "http://34.132.172.40/"
PUBLIC_STRATEGY_URL = "http://34.132.172.40/strategy"


def install_dashboard_navigation(app: FastAPI) -> None:
    """Inject canonical navigation and richer trade labels into the dashboard."""

    @app.get("/api/dashboard-info")
    def dashboard_info():
        return {
            "dashboard_url": PUBLIC_DASHBOARD_URL,
            "strategy_url": PUBLIC_STRATEGY_URL,
            "strategy_path": "/strategy",
            "live_settings_path": "/strategy/live",
            "runtime_mode_path": "/strategy/runtime",
            "cache_refresh_path": "/strategy/cache",
        }

    @app.middleware("http")
    async def dashboard_navigation(request: Request, call_next):
        response = await call_next(request)
        if request.url.path != "/" or "text/html" not in response.headers.get("content-type", ""):
            return response

        chunks = [chunk async for chunk in response.body_iterator]
        body = b"".join(chunks).decode("utf-8", errors="replace")
        marker = "<body><div class='wrap'>"
        if marker not in body:
            headers = dict(response.headers)
            headers.pop("content-length", None)
            return HTMLResponse(body, status_code=response.status_code, headers=headers)

        nav = """<body><div class='wrap'>
<div class='bar' style='display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between'>
  <div>
    <b>고정 대시보드</b>
    <div class='muted' style='margin-top:3px'>http://34.132.172.40</div>
  </div>
  <div class='row'>
    <button type='button' onclick=\"location.href='/strategy'\">⚙ 전략 수치 변경</button>
    <button type='button' onclick=\"location.href='/strategy/live'\">🚀 Elite LIVE 설정</button>
    <button type='button' onclick=\"location.href='/strategy/runtime'\">🛡 PAPER/LIVE 전환</button>
    <button type='button' onclick=\"location.href='/strategy/cache'\">⚡ 최신 캐시 갱신</button>
    <button type='button' class='ghost' onclick=\"location.href='/'\">대시보드 홈</button>
  </div>
</div>"""
        body = body.replace(marker, nav, 1)

        # The base chart already draws candles and simple entry/exit symbols.
        # This overlay adds readable TradingView-style labels and, for runtime
        # trades recorded after this feature, shows each pyramiding entry (1/2)
        # separately instead of only the aggregate closed trade marker.
        overlay = r"""
<script>
(()=>{
  let utbTradeEvents=[];
  const originalDrawMarket=drawMarket;
  const originalLoadMarket=loadMarket;

  function tag(ctx,text,x,y,bg,above=true){
    ctx.save();
    ctx.font='bold 11px system-ui';
    const pad=5,h=20,w=Math.ceil(ctx.measureText(text).width)+pad*2;
    const left=Math.max(2,Math.min(x-w/2,(ctx.canvas.clientWidth||1000)-w-2));
    const top=above?y-h-9:y+9;
    ctx.fillStyle=bg;
    ctx.fillRect(left,top,w,h);
    ctx.fillStyle='#ffffff';
    ctx.textBaseline='middle';
    ctx.fillText(text,left+pad,top+h/2);
    ctx.restore();
  }

  function drawTradeEventOverlay(){
    const c=document.getElementById('marketChart');
    if(!c||!utbTradeEvents.length||!lastCandles.length)return;
    const vp=viewport(),data=vp.data;
    if(!data.length)return;
    const dpr=devicePixelRatio||1,w=c.clientWidth||1000,h=c.clientHeight||430;
    const ctx=c.getContext('2d');
    ctx.setTransform(dpr,0,0,dpr,0,0);
    const padL=58,padR=18,padT=18,padB=34,chartH=h-padT-padB;
    const lows=data.map(a=>+a.low),highs=data.map(a=>+a.high);
    const lo=Math.min(...lows),hi=Math.max(...highs),span=Math.max(1e-9,hi-lo);
    const py=v=>padT+(hi-v)/span*chartH;
    const first=Date.parse(data[0].timestamp),last=Date.parse(data[data.length-1].timestamp),range=Math.max(1,last-first);
    const mx=t=>padL+(Date.parse(t)-first)/range*(w-padL-padR);

    utbTradeEvents.forEach(ev=>{
      const ts=Date.parse(ev.event_time||'');
      const price=Number(ev.price);
      if(!Number.isFinite(ts)||!Number.isFinite(price)||ts<first||ts>last)return;
      const xx=mx(ev.event_time),yy=py(price);
      if(xx<padL||xx>w-padR||yy<padT-30||yy>h-padB+30)return;
      if(String(ev.event_type).toUpperCase()==='ENTRY'){
        const side=String(ev.side||'').toUpperCase();
        const n=Number(ev.entry_no||1);
        const bg=side==='LONG'?'#178f5c':'#c73f4f';
        tag(ctx,`${side} ${n} · ${price.toFixed(price>100?1:3)}`,xx,yy,bg,side==='LONG');
      }else if(String(ev.event_type).toUpperCase()==='EXIT'){
        const pct=Number(ev.pnl_percent||0);
        const reason=String(ev.reason||'EXIT').toUpperCase();
        const bg=pct>=0?'#2563a8':'#8f3441';
        tag(ctx,`${reason} ${pct>=0?'+':''}${pct.toFixed(2)}%`,xx,yy,bg,false);
      }
    });
  }

  drawMarket=function(){
    originalDrawMarket();
    drawTradeEventOverlay();
  };

  loadMarket=async function(){
    await originalLoadMarket();
    try{
      const q=new URLSearchParams({
        symbol:document.getElementById('symbol').value,
        mode:document.getElementById('mode').value,
        start:document.getElementById('start').value,
        end:document.getElementById('end').value,
        limit:'5000'
      });
      const r=await fetch('/api/trade-events?'+q),d=await r.json();
      utbTradeEvents=r.ok?(d.events||[]):[];
    }catch(_){utbTradeEvents=[];}
    const legend=document.getElementById('chartLegend');
    if(legend)legend.textContent='LONG/SHORT 1 = 최초 진입 · LONG/SHORT 2 = 추가 진입 · TP/SL/EXIT = 청산 · 과거 기록은 ▲/▼/● 표시';
    drawMarket();
  };
})();
</script>
"""
        if "</body>" in body:
            body = body.replace("</body>", overlay + "</body>", 1)

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return HTMLResponse(body, status_code=response.status_code, headers=headers)
