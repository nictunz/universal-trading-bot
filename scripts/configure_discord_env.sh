#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${DASHBOARD_VENV:-$HOME/.cache/universal-trading-bot-dashboard-venv}/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

touch .env
cp .env ".env.bak-discord-$(date +%Y%m%d-%H%M%S)"
chmod 600 .env

echo "Discord webhook 설정"
echo "Webhook URL은 화면에 다시 출력하지 않습니다."
read -r -s -p "기존 Discord Webhook URL: " DISCORD_WEBHOOK_URL; echo

if [[ -z "$DISCORD_WEBHOOK_URL" ]]; then
  echo "오류: Discord Webhook URL이 비어 있습니다." >&2
  exit 2
fi

export DISCORD_WEBHOOK_URL
"$PY" - <<'PY'
from pathlib import Path
import json
import os

p = Path('.env')
updates = {
    'DISCORD_NOTIFICATIONS_ENABLED': 'true',
    'DISCORD_WEBHOOK_URL': os.environ['DISCORD_WEBHOOK_URL'],
    'DISCORD_TIMEOUT': '5',
}

def encode(key: str, value: str) -> str:
    if key in {'DISCORD_NOTIFICATIONS_ENABLED', 'DISCORD_TIMEOUT'}:
        return value
    return json.dumps(value, ensure_ascii=False)

lines = p.read_text(encoding='utf-8').splitlines() if p.exists() else []
out = []
seen = set()
for line in lines:
    stripped = line.lstrip()
    if not stripped or stripped.startswith('#') or '=' not in line:
        out.append(line)
        continue
    key = line.split('=', 1)[0].strip()
    if key in updates:
        out.append(f"{key}={encode(key, updates[key])}")
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={encode(key, value)}")
p.write_text('\n'.join(out).rstrip() + '\n', encoding='utf-8')
p.chmod(0o600)
PY
unset DISCORD_WEBHOOK_URL

echo
echo "===== REDACTED DISCORD CHECK ====="
"$PY" - <<'PY'
from universal_bot.config import Settings
s = Settings()
print('DISCORD_NOTIFICATIONS_ENABLED =', s.discord_notifications_enabled)
print('DISCORD_WEBHOOK_URL           =', 'SET' if bool(s.discord_webhook_url) else 'MISSING')
print('DISCORD_TIMEOUT               =', s.discord_timeout)
PY

echo
echo "===== TEST MESSAGE ====="
"$PY" - <<'PY'
from universal_bot.config import Settings
from universal_bot.discord_notifier import DiscordNotifier
s = Settings()
n = DiscordNotifier(s.discord_webhook_url, enabled=s.discord_notifications_enabled, timeout=s.discord_timeout)
result = n.send('✅ Universal Trading Bot Discord 연결 테스트 · PAPER 상태 · 실제 주문 없음')
print('DISCORD_TEST_OK=' + ('true' if result.get('ok') else 'false'))
print('HTTP_STATUS=' + str(result.get('status')))
print('REASON=' + str(result.get('reason')))
PY

echo
echo "완료. .env의 BOT_MODE는 변경하지 않았습니다."
