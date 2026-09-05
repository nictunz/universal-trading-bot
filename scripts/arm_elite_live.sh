#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${DASHBOARD_VENV:-$HOME/.cache/universal-trading-bot-dashboard-venv}/bin/python"
SERVICE="universal-trading-bot-dashboard.service"

if [[ ! -x "$PY" ]]; then
  echo "Dashboard Python not found: $PY" >&2
  exit 2
fi

echo "===== ELITE LIVE PROFILE CHECK ====="
"$PY" - <<'PY'
from universal_bot.config import Settings
s = Settings()
expected = {
    'BITGET_EXECUTION_PROFILE': (s.bitget_execution_profile, 'elite'),
    'LEVERAGE': (s.leverage, 15),
    'MARGIN_MODE': (s.margin_mode, 'crossed'),
    'LIVE_REQUIRE_ONE_WAY_MODE': (s.live_require_one_way_mode, True),
    'MAX_PYRAMIDING': (s.max_pyramiding, 1),
    'LIVE_ENTRY_MULTIPLIER': (s.live_entry_multiplier, 8.6),
    'LIVE_MAX_ENTRIES_PER_POSITION': (s.live_max_entries_per_position, 1),
    'LIVE_MAX_TOTAL_MULTIPLIER': (s.live_max_total_multiplier, 15.0),
}
bad=[]
for name,(actual,wanted) in expected.items():
    ok = actual == wanted
    print(f'{name}={actual} expected={wanted} ok={ok}')
    if not ok: bad.append(name)
if bad:
    raise SystemExit('LIVE profile mismatch: ' + ', '.join(bad))
PY

TMP_BTC="$(mktemp)"
trap 'rm -f "$TMP_BTC"' EXIT

echo
echo "===== BTC ELITE LIVE PREFLIGHT ====="
BOT_MODE=LIVE SYMBOL='BTC/USDT:USDT' "$PY" -m universal_bot.preflight >"$TMP_BTC"
cat "$TMP_BTC"


READY="$($PY - "$TMP_BTC" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    data=json.load(f)
ok = data.get('ready') is True and data.get('api_family') == 'classic-v2'
print('true' if ok else 'false')
PY
)"

if [[ "$READY" != "true" ]]; then
  echo
  echo "LIVE 전환 차단: BTC ready=true가 아닙니다." >&2
  exit 3
fi

read -r -p "BTC Preflight 통과. 실제 Elite 주문을 활성화하려면 LIVE 를 입력하세요: " CONFIRM
if [[ "$CONFIRM" != "LIVE" ]]; then
  echo "취소했습니다. .env는 PAPER 그대로입니다."
  exit 0
fi

cp .env ".env.bak-before-live-$(date +%Y%m%d-%H%M%S)"
"$PY" - <<'PY'
from pathlib import Path
p=Path('.env')
lines=p.read_text(encoding='utf-8').splitlines()
out=[]; done=False
for line in lines:
    if line.split('=',1)[0].strip() == 'BOT_MODE' and '=' in line and not line.lstrip().startswith('#'):
        out.append('BOT_MODE=LIVE'); done=True
    else:
        out.append(line)
if not done:
    out.append('BOT_MODE=LIVE')
p.write_text('\n'.join(out).rstrip()+'\n', encoding='utf-8')
PY
chmod 600 .env

sudo systemctl restart "$SERVICE"
sleep 7

echo
echo "===== SERVICE ====="
systemctl is-active "$SERVICE"

echo
echo "===== HEALTH ====="
curl -sS -m 10 http://127.0.0.1:8000/health; echo

echo
echo "===== LIVE READINESS ====="
curl -sS -m 15 http://127.0.0.1:8000/api/live-readiness; echo

echo
echo "LIVE 활성화 완료. BTC는 15x 계정 레버리지 상한, JSON 기준 8.6x 진입, 최대 1회으로 동작합니다."
