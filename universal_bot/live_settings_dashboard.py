from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from universal_bot.config import Settings
from universal_bot.strategy_dashboard import STORE as STRATEGY_STORE
from universal_bot.trade_history import TradeHistoryStore

ENV_PATH = Path('.env')


class LiveSettingsUpdate(BaseModel):
    leverage: int = Field(ge=1, le=150)
    live_entry_multiplier: float = Field(gt=0, le=50)
    live_max_entries_per_position: int = Field(ge=1, le=5)


class RuntimeModeUpdate(BaseModel):
    mode: Literal["PAPER", "LIVE"]
    confirmation: str = ""


def _snapshot(scanner) -> dict[str, Any]:
    settings = Settings()
    runtimes = []
    for runtime in scanner.runtimes:
        engine = runtime.engine
        account_leverage = None
        try:
            if hasattr(engine.adapter, 'account_info'):
                info = engine.adapter.account_info(runtime.symbol)
                account_leverage = float(
                    info.get('crossedMarginLeverage')
                    or info.get('crossedLever')
                    or info.get('leverage')
                    or 0.0
                )
        except Exception:
            account_leverage = None
        runtimes.append({
            'symbol': runtime.symbol,
            'mode': engine.settings.bot_mode.upper(),
            'position_side': engine.position.side,
            'entries': engine.position.entries,
            'account_leverage': account_leverage,
        })
    return {
        'execution_profile': settings.bitget_execution_profile,
        'margin_mode': settings.margin_mode,
        'leverage': settings.leverage,
        'live_entry_multiplier': settings.live_entry_multiplier,
        'live_max_entries_per_position': settings.live_max_entries_per_position,
        'live_max_total_multiplier': settings.live_max_total_multiplier,
        'require_exchange_protection': settings.require_exchange_protection,
        'live_require_one_way_mode': settings.live_require_one_way_mode,
        'discord_notifications_enabled': settings.discord_notifications_enabled,
        'discord_configured': bool(settings.discord_webhook_url),
        'bot_mode': settings.bot_mode.upper(),
        'runtimes': runtimes,
    }


def _write_env(values: dict[str, str]) -> None:
    ENV_PATH.touch(exist_ok=True)
    lines = ENV_PATH.read_text(encoding='utf-8').splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith('#') or '=' not in line:
            out.append(line)
            continue
        key = line.split('=', 1)[0].strip()
        if key in values:
            out.append(f'{key}={values[key]}')
            seen.add(key)
        else:
            out.append(line)
    for key, value in values.items():
        if key not in seen:
            out.append(f'{key}={value}')
    ENV_PATH.write_text('\n'.join(out).rstrip() + '\n', encoding='utf-8')
    ENV_PATH.chmod(0o600)


def _sync_strategy_pyramiding(total_entries: int) -> None:
    STRATEGY_STORE.parent.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Any] = {}
    if STRATEGY_STORE.exists():
        try:
            saved = json.loads(STRATEGY_STORE.read_text(encoding='utf-8'))
        except Exception:
            saved = {}
    saved['max_pyramiding'] = int(total_entries)
    STRATEGY_STORE.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')


def _start_iso(value: str | None) -> str | None:
    if not value:
        return None
    return value + 'T00:00:00+00:00' if len(value) == 10 else value


def _end_iso(value: str | None) -> str | None:
    if not value:
        return None
    return value + 'T23:59:59.999999+00:00' if len(value) == 10 else value


def install_live_settings_dashboard(app, scanner) -> None:
    history = TradeHistoryStore()

    @app.get('/api/trade-events')
    def trade_events(
        symbol: str,
        mode: str = 'ALL',
        start: str | None = None,
        end: str | None = None,
        limit: int = Query(5000, ge=1, le=10000),
    ):
        return {
            'symbol': symbol,
            'mode': mode.upper(),
            'events': history.list_events(
                symbol=symbol,
                mode=mode,
                start=_start_iso(start),
                end=_end_iso(end),
                limit=limit,
            ),
        }

    @app.get('/api/live/settings')
    def get_live_settings():
        return _snapshot(scanner)

    @app.post('/api/live/settings')
    def save_live_settings(req: LiveSettingsUpdate):
        active = [
            runtime.symbol
            for runtime in scanner.runtimes
            if not runtime.engine.position.flat
        ]
        if active:
            raise HTTPException(
                status_code=409,
                detail='포지션 보유 중에는 LIVE 레버리지/진입배수/진입횟수를 변경할 수 없습니다: ' + ', '.join(active),
            )

        total_multiplier = float(req.live_entry_multiplier) * int(req.live_max_entries_per_position)
        if total_multiplier > 150:
            raise HTTPException(status_code=400, detail='진입 배수 × 총 진입 횟수는 150을 초과할 수 없습니다.')

        # Protection and one-way mode are intentionally not editable here.
        # They stay fail-closed for the verified Classic v2 Elite account.
        env_values = {
            'LEVERAGE': str(int(req.leverage)),
            'LIVE_ENTRY_MULTIPLIER': str(float(req.live_entry_multiplier)).rstrip('0').rstrip('.'),
            'LIVE_MAX_ENTRIES_PER_POSITION': str(int(req.live_max_entries_per_position)),
            'LIVE_MAX_TOTAL_MULTIPLIER': str(total_multiplier).rstrip('0').rstrip('.'),
            'MAX_PYRAMIDING': str(int(req.live_max_entries_per_position)),
            'REQUIRE_EXCHANGE_PROTECTION': 'true',
            'LIVE_REQUIRE_ONE_WAY_MODE': 'true',
        }
        _write_env(env_values)
        _sync_strategy_pyramiding(req.live_max_entries_per_position)

        leverage_sync: list[dict[str, Any]] = []
        for runtime in scanner.runtimes:
            engine = runtime.engine
            update = {
                'leverage': int(req.leverage),
                'live_entry_multiplier': float(req.live_entry_multiplier),
                'live_max_entries_per_position': int(req.live_max_entries_per_position),
                'live_max_total_multiplier': total_multiplier,
                'max_pyramiding': int(req.live_max_entries_per_position),
                'require_exchange_protection': True,
                'live_require_one_way_mode': True,
            }
            engine.settings = engine.settings.model_copy(update=update)
            engine.strategy.s = engine.settings
            if engine.live:
                engine._live_initialized = False
                if hasattr(engine.adapter, 'ensure_leverage'):
                    try:
                        result = engine.adapter.ensure_leverage(runtime.symbol, int(req.leverage))
                    except Exception as exc:
                        result = {'ok': False, 'reason': f'{type(exc).__name__}: {exc}'}
                    leverage_sync.append({'symbol': runtime.symbol, **result})

        return {
            'status': 'ok',
            'saved': _snapshot(scanner),
            'leverage_sync': leverage_sync,
            'note': '총 진입 횟수에는 최초 진입이 포함됩니다. 예: 2 = 최초 1회 + 추가 1회.',
        }

    @app.get('/api/runtime-mode')
    def get_runtime_mode():
        snapshot = _snapshot(scanner)
        return {
            'mode': snapshot['bot_mode'],
            'runtimes': snapshot['runtimes'],
            'restart_managed_by': 'systemd',
        }

    @app.post('/api/runtime-mode')
    def set_runtime_mode(req: RuntimeModeUpdate):
        target = req.mode.upper()
        current = Settings().bot_mode.upper()
        active = [
            runtime.symbol
            for runtime in scanner.runtimes
            if not runtime.engine.position.flat
        ]
        if active:
            raise HTTPException(
                status_code=409,
                detail='포지션 보유 중에는 PAPER/LIVE 모드를 변경할 수 없습니다: ' + ', '.join(active),
            )
        if target == 'LIVE' and req.confirmation.strip() != 'ENABLE LIVE':
            raise HTTPException(
                status_code=400,
                detail='LIVE 전환 확인 문구 ENABLE LIVE가 필요합니다.',
            )
        if target == current:
            return {'status': 'ok', 'mode': current, 'restarting': False}
        _write_env({'BOT_MODE': target})

        def restart_after_response() -> None:
            # The systemd unit uses Restart=always, so exiting reloads .env and
            # reconstructs all runtimes in the selected mode.
            os._exit(0)

        timer = threading.Timer(1.0, restart_after_response)
        timer.daemon = True
        timer.start()
        return {
            'status': 'ok',
            'mode': target,
            'previous_mode': current,
            'restarting': True,
            'note': '서버가 새 모드로 안전 재시작됩니다.',
        }

    @app.get('/strategy/runtime', response_class=HTMLResponse)
    def runtime_mode_page():
        return HTMLResponse(_MODE_HTML)

    @app.get('/strategy/live', response_class=HTMLResponse)
    def live_settings_page():
        return HTMLResponse(_HTML)


_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Elite LIVE Settings</title><style>*{box-sizing:border-box}body{margin:0;padding:14px;background:#0b0f14;color:#eef2f7;font-family:system-ui}.wrap{max-width:900px;margin:auto}.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:16px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}.f{display:flex;flex-direction:column;gap:6px;color:#9daabd;font-size:12px}input,button{padding:11px;border-radius:8px;border:1px solid #556579;background:#0b0f14;color:#eef2f7;font-size:14px}button{background:#2563a8;font-weight:800;cursor:pointer}.muted{color:#9daabd}.ok{color:#42e887}.bad{color:#ff6677}.warn{color:#ffcc66}.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.metric{background:#0f1620;border-radius:9px;padding:10px}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}.big{font-size:20px;font-weight:800}</style></head><body><div class="wrap"><h1>Bitget Elite LIVE 설정</h1><div class="muted">변경 가능: 계정 레버리지 · 1회 진입 배수 · 총 진입 횟수. 포지션 보유 중에는 변경이 차단되며, 거래소 TP/SL 보호와 One-way 요구는 안전상 고정됩니다.</div><div class="card"><div class="grid"><label class="f">계정 레버리지<input id="leverage" type="number" min="1" max="150"></label><label class="f">1회 진입 배수<input id="mult" type="number" min="0.1" max="50" step="0.1"></label><label class="f">총 진입 횟수<input id="entries" type="number" min="1" max="5"></label></div><div id="explain" class="muted" style="margin:12px 0"></div><div class="row"><button onclick="save()">저장 / 즉시 적용</button><button onclick="location.href='/strategy'">전략 설정</button><button onclick="location.href='/'">대시보드 홈</button></div><div id="status" style="margin-top:12px"></div></div><div class="card"><b>현재 LIVE 프로필</b><div id="metrics" class="metrics" style="margin-top:10px"></div><div id="runtime" class="muted" style="margin-top:10px"></div></div></div><script>let current={};function metric(n,v){return `<div class=metric><div class=muted>${n}</div><div class=big>${v}</div></div>`}function explain(){const m=Number(mult.value||0),e=Number(entries.value||0);document.getElementById('explain').textContent=`1회 ${m}배 × 총 ${e}회 = 최대 ${m*e}배 상한 · ${e===2?'최초 1회 + 추가 1회':`최초 1회 + 추가 ${Math.max(0,e-1)}회`}`;}async function load(){const r=await fetch('/api/live/settings'),d=await r.json();current=d;leverage.value=d.leverage;mult.value=d.live_entry_multiplier;entries.value=d.live_max_entries_per_position;explain();metrics.innerHTML=metric('모드',d.bot_mode)+metric('프로필',d.execution_profile)+metric('마진',d.margin_mode)+metric('레버리지',d.leverage+'x')+metric('1회 진입',d.live_entry_multiplier+'x')+metric('총 진입',d.live_max_entries_per_position+'회')+metric('최대 상한',d.live_max_total_multiplier+'x')+metric('TP/SL 보호',d.require_exchange_protection?'고정 ON':'OFF')+metric('One-way',d.live_require_one_way_mode?'고정 요구':'OFF')+metric('Discord',d.discord_notifications_enabled&&d.discord_configured?'ON':'OFF');runtime.innerHTML=(d.runtimes||[]).map(x=>`${x.symbol}: ${x.mode} · 포지션 ${x.position_side} · 진입 ${x.entries}회 · 계정 레버리지 ${x.account_leverage==null?'-':x.account_leverage+'x'}`).join('<br>');}async function save(){status.textContent='저장 중...';status.className='warn';const body={leverage:Number(leverage.value),live_entry_multiplier:Number(mult.value),live_max_entries_per_position:Number(entries.value)};const r=await fetch('/api/live/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();if(!r.ok){status.textContent='오류: '+(d.detail||'저장 실패');status.className='bad';return}status.textContent='저장 완료 · 런타임 즉시 적용됨';status.className='ok';await load();}mult.oninput=explain;entries.oninput=explain;load();</script></body></html>'''


_MODE_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Runtime Mode</title><style>*{box-sizing:border-box}body{margin:0;padding:16px;background:#0b0f14;color:#eef2f7;font-family:system-ui}.wrap{max-width:720px;margin:auto}.card{background:#17202c;border:1px solid #334155;border-radius:14px;padding:16px;margin:12px 0}button,input{width:100%;padding:12px;margin-top:10px;border-radius:9px;border:1px solid #556579;background:#0b0f14;color:#eef2f7}button{font-weight:800;background:#2563a8}.paper{background:#1d8f5a}.live{background:#b45309}.muted{color:#9daabd}.ok{color:#42e887}.bad{color:#ff6677}.warn{color:#ffcc66}a{color:#7db7ff}</style></head><body><div class="wrap"><h1>PAPER / LIVE 모드</h1><div class="card"><div id="current" class="muted">확인 중...</div><button class="paper" onclick="changeMode('PAPER')">PAPER 모드로 전환</button><div class="muted" style="margin-top:16px">LIVE 전환은 아래에 <b>ENABLE LIVE</b>를 정확히 입력해야 하며, 포지션 보유 중에는 차단됩니다.</div><input id="confirm" placeholder="ENABLE LIVE"><button class="live" onclick="changeMode('LIVE')">LIVE 실거래 모드로 전환</button><div id="status" style="margin-top:12px"></div></div><p><a href="/strategy/live">Elite LIVE 설정</a> · <a href="/strategy">전략 설정</a> · <a href="/">홈</a></p></div><script>async function load(){const r=await fetch('/api/runtime-mode'),d=await r.json();current.textContent='현재 서버 모드: '+(d.mode||'?')+' · '+(d.runtimes||[]).map(x=>x.symbol+':'+x.position_side).join(' / ')}async function changeMode(mode){if(mode==='LIVE'&&!window.confirm('실거래 주문이 활성화될 수 있습니다. LIVE로 전환할까요?'))return;status.textContent='변경 요청 중...';status.className='warn';const r=await fetch('/api/runtime-mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,confirmation:confirm.value})}),d=await r.json();if(!r.ok){status.textContent='오류: '+(d.detail||'변경 실패');status.className='bad';return}status.textContent=d.restarting?'저장 완료 · 서버 재시작 중...':('이미 '+d.mode+' 모드입니다.');status.className='ok';if(d.restarting)setTimeout(()=>location.reload(),7000)}load();</script></body></html>'''
