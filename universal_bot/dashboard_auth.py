from __future__ import annotations

import hashlib
import hmac
import html
import time
from collections import defaultdict, deque
from urllib.parse import parse_qs, quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from universal_bot.config import Settings

COOKIE_NAME = "utb_session"
MIN_SESSION_SECONDS = 7 * 24 * 60 * 60
_LOGIN_FAILURES: dict[str, deque[float]] = defaultdict(deque)


def _configured(settings: Settings) -> bool:
    return bool(
        settings.dashboard_auth_enabled
        and settings.dashboard_username.strip()
        and settings.dashboard_password
        and settings.dashboard_session_secret
    )


def _sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _session_seconds(settings: Settings) -> int:
    return max(MIN_SESSION_SECONDS, max(1, int(settings.dashboard_session_hours)) * 3600)


def _make_token(settings: Settings) -> str:
    exp = int(time.time()) + _session_seconds(settings)
    payload = f"{settings.dashboard_username}:{exp}"
    return f"{payload}:{_sign(settings.dashboard_session_secret, payload)}"


def _valid_token(settings: Settings, token: str | None) -> bool:
    if not token or not _configured(settings):
        return False
    try:
        username, exp_text, sig = token.rsplit(":", 2)
        exp = int(exp_text)
    except Exception:
        return False
    if username != settings.dashboard_username or exp < int(time.time()):
        return False
    payload = f"{username}:{exp}"
    return hmac.compare_digest(sig, _sign(settings.dashboard_session_secret, payload))


def _is_protected(request: Request) -> bool:
    path = request.url.path
    method = request.method.upper()
    if path.startswith("/strategy"):
        return True
    if path.startswith("/api/strategy-") or path == "/api/strategy-settings":
        return True
    if path.startswith("/api/live/"):
        return True
    if path == "/api/backtest" and method != "GET":
        return True
    return False


def _login_page(message: str = "", next_url: str = "/strategy") -> str:
    msg = f"<div class='msg'>{html.escape(message)}</div>" if message else ""
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Universal Trading Bot Login</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#0b0f14;color:#eef2f7;font-family:system-ui;display:grid;place-items:center;min-height:100vh;padding:18px}}
.card{{width:min(420px,100%);background:#17202c;border:1px solid #334155;border-radius:16px;padding:20px}}h1{{font-size:22px;margin-top:0}}label{{display:block;color:#9daabd;font-size:13px;margin:12px 0 5px}}input{{width:100%;padding:12px;border-radius:9px;border:1px solid #556579;background:#0b0f14;color:#eef2f7}}button{{width:100%;margin-top:16px;padding:12px;border:0;border-radius:9px;background:#2563a8;color:white;font-weight:800}}.msg{{color:#ffcc66;margin:10px 0}}a{{color:#7db7ff}}</style></head>
<body><div class='card'><h1>🔐 관리자 로그인</h1><div style='color:#9daabd'>전략 설정과 LIVE 제어는 로그인 후 사용할 수 있습니다.</div>{msg}
<form method='post' action='/login'><input type='hidden' name='next' value='{html.escape(next_url, quote=True)}'><label>아이디</label><input name='username' autocomplete='username' required><label>비밀번호</label><input name='password' type='password' autocomplete='current-password' required><button type='submit'>로그인</button></form><p><a href='/'>← 공개 대시보드로 돌아가기</a></p></div></body></html>"""


def install_dashboard_auth(app: FastAPI) -> None:
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        current = Settings()
        if _is_protected(request):
            if current.dashboard_auth_enabled and not _configured(current):
                if request.url.path.startswith("/api/"):
                    return JSONResponse({"detail": "dashboard authentication is enabled but credentials are not configured in .env"}, status_code=503)
                return HTMLResponse(_login_page("관리자 인증값이 아직 .env에 설정되지 않았습니다."), status_code=503)
            if _configured(current) and not _valid_token(current, request.cookies.get(COOKIE_NAME)):
                if request.url.path.startswith("/api/"):
                    return JSONResponse({"detail": "authentication required", "login": "/login"}, status_code=401)
                next_url = quote(request.url.path or "/strategy", safe="/")
                return RedirectResponse(f"/login?next={next_url}", status_code=303)

        response = await call_next(request)
        if request.url.path == "/" and response.headers.get("content-type", "").startswith("text/html"):
            try:
                body = b"".join([chunk async for chunk in response.body_iterator]).decode("utf-8")
                marker = "<span id='readyBadge' class='headerBadge muted'>LIVE READINESS 확인 중</span>"
                button = "<a href='/strategy' style='text-decoration:none'><button type='button'>⚙ 전략 수치 변경</button></a>"
                if button not in body and marker in body:
                    body = body.replace(marker, marker + button, 1)
                headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
                return HTMLResponse(body, status_code=response.status_code, headers=headers)
            except Exception:
                pass
        return response

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, next: str = "/strategy"):
        current = Settings()
        if _configured(current) and _valid_token(current, request.cookies.get(COOKIE_NAME)):
            return RedirectResponse(next if next.startswith("/") else "/strategy", status_code=303)
        message = "" if not current.dashboard_auth_enabled or _configured(current) else "관리자 인증값이 아직 .env에 설정되지 않았습니다."
        return HTMLResponse(_login_page(message, next if next.startswith('/') and not next.startswith('//') else '/strategy'))

    @app.post("/login")
    async def login(request: Request):
        raw = (await request.body()).decode("utf-8", errors="replace")
        form = parse_qs(raw, keep_blank_values=True)
        username = form.get("username", [""])[0]
        password = form.get("password", [""])[0]
        next_url = form.get("next", ["/strategy"])[0]
        current = Settings()
        if not _configured(current):
            return HTMLResponse(_login_page("관리자 인증값이 아직 .env에 설정되지 않았습니다."), status_code=503)
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        failures = _LOGIN_FAILURES[ip]
        while failures and failures[0] < now - 300:
            failures.popleft()
        if len(failures) >= 8:
            return HTMLResponse(_login_page("로그인 실패가 너무 많습니다. 잠시 후 다시 시도하세요."), status_code=429)
        ok = hmac.compare_digest(username, current.dashboard_username) and hmac.compare_digest(password, current.dashboard_password)
        if not ok:
            failures.append(now)
            time.sleep(min(1.5, 0.2 * len(failures)))
            return HTMLResponse(_login_page("아이디 또는 비밀번호가 올바르지 않습니다."), status_code=401)
        failures.clear()
        target = next_url if next_url.startswith("/") and not next_url.startswith("//") else "/strategy"
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            _make_token(current),
            max_age=_session_seconds(current),
            httponly=True,
            samesite="strict",
            secure=bool(current.dashboard_cookie_secure),
            path="/",
        )
        return response

    @app.get("/logout")
    def logout():
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(COOKIE_NAME, path="/")
        return response

    @app.get("/api/auth-status")
    def auth_status(request: Request):
        current = Settings()
        return {
            "enabled": bool(current.dashboard_auth_enabled),
            "configured": _configured(current),
            "authenticated": _valid_token(current, request.cookies.get(COOKIE_NAME)),
            "public_dashboard": current.dashboard_public_url,
        }
