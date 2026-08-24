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

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

echo "===== ELITE LIVE PREFLIGHT ====="
BOT_MODE=LIVE "$PY" -m universal_bot.preflight >"$TMP"
cat "$TMP"

READY="$($PY - "$TMP" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    data=json.load(f)
print('true' if data.get('ready') is True else 'false')
PY
)"

if [[ "$READY" != "true" ]]; then
  echo
  echo "LIVE 전환 차단: preflight ready=true가 아닙니다." >&2
  exit 3
fi

read -r -p "Preflight 통과. 실제 Elite 주문을 활성화하려면 LIVE 를 입력하세요: " CONFIRM
if [[ "$CONFIRM" != "LIVE" ]]; then
  echo "취소했습니다. .env는 PAPER 그대로입니다."
  exit 0
fi

cp .env ".env.bak-before-live-$(date +%Y%m%d-%H%M%S)"
python3 - <<'PY'
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
echo "LIVE 활성화 완료. 실제 주문은 전략 신호가 발생할 때 Elite Trading Portfolio API로 전송됩니다."
