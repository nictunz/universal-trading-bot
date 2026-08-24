from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

PUBLIC_DASHBOARD_URL = "http://34.132.172.40/"
PUBLIC_STRATEGY_URL = "http://34.132.172.40/strategy"


def install_dashboard_navigation(app: FastAPI) -> None:
    """Inject canonical navigation into the public dashboard."""

    @app.get("/api/dashboard-info")
    def dashboard_info():
        return {
            "dashboard_url": PUBLIC_DASHBOARD_URL,
            "strategy_url": PUBLIC_STRATEGY_URL,
            "strategy_path": "/strategy",
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
    <button type='button' onclick=\"location.href='/strategy/cache'\">⚡ 최신 캐시 갱신</button>
    <button type='button' class='ghost' onclick=\"location.href='/'\">대시보드 홈</button>
  </div>
</div>"""
        body = body.replace(marker, nav, 1)
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return HTMLResponse(body, status_code=response.status_code, headers=headers)
