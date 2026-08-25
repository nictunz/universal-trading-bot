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
echo "웹훅 주소는 입력 중 화면에 표시되지 않고, 완료 후에도 출력하지 않습니다."
read -r -s -p "기존 Discord Webhook URL 입력: " DISCORD_WEBHOOK; echo

if [[ -z "$DISCORD_WEBHOOK" ]]; then
  echo "오류: Discord Webhook URL이 비어 있습니다." >&2
  exit 2
fi
if [[ "$DISCORD_WEBHOOK" != https://discord.com/api/webhooks/* && "$DISCORD_WEBHOOK" != https://discordapp.com/api/webhooks/* ]]; then
  echo "오류: Discord webhook URL 형식이 아닙니다." >&2
  exit 2
fi

export DISCORD_WEBHOOK
"$PY" - <<'PY'
from pathlib import Path
import json
import os

p = Path('.env')
updates = {
    'DISCORD_NOTIFICATIONS_ENABLED': 'true',
    'DISCORD_WEBHOOK_URL': os.environ['DISCORD_WEBHOOK'],
    'DISCORD_TIMEOUT': '5',
}

def enc(key: str, value: str) -> str:
    if key != 'DISCORD_WEBHOOK_URL':
        return value
    return json.dumps(value)

lines = p.read_text(encoding='utf-8').splitlines() if p.exists() else []
out=[]; seen=set()
for line in lines:
    if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
        out.append(line); continue
    key=line.split('=',1)[0].strip()
    if key in updates:
        out.append(f'{key}={enc(key, updates[key])}')
        seen.add(key)
    else:
        out.append(line)
for key,value in updates.items():
    if key not in seen:
        out.append(f'{key}={enc(key, value)}')
p.write_text('\n'.join(out).rstrip()+'\n', encoding='utf-8')
p.chmod(0o600)
PY
unset DISCORD_WEBHOOK

echo
echo "===== REDACTED DISCORD CHECK ====="
"$PY" - <<'PY'
from universal_bot.config import Settings
from universal_bot.discord_notifier import DiscordNotifier
s=Settings()
n=DiscordNotifier(s.discord_webhook_url, enabled=s.discord_notifications_enabled, timeout=s.discord_timeout)
print('DISCORD_NOTIFICATIONS_ENABLED =', s.discord_notifications_enabled)
print('DISCORD_WEBHOOK               =', 'SET' if n.configured else 'MISSING')
print('WEBHOOK_VALUE_PRINTED         = NO')
PY

echo
echo "저장 완료. BOT_MODE은 변경하지 않았습니다."
