#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${DASHBOARD_VENV:-$HOME/.cache/universal-trading-bot-dashboard-venv}/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

touch .env
cp .env ".env.bak-$(date +%Y%m%d-%H%M%S)"
chmod 600 .env

echo "Bitget Elite LIVE용 .env 설정"
echo "실제 키/비밀번호는 화면에 다시 표시하지 않습니다."
echo "이 스크립트는 안전을 위해 BOT_MODE=PAPER로 저장합니다."
echo

read -r -p "대시보드 관리자 아이디: " DASH_USER
read -r -s -p "대시보드 관리자 비밀번호: " DASH_PASS; echo

echo
read -r -s -p "일반 Bitget API Key (없으면 Enter): " BITGET_STANDARD_KEY; echo
if [[ -n "$BITGET_STANDARD_KEY" ]]; then
  read -r -s -p "일반 Bitget API Secret: " BITGET_STANDARD_SECRET; echo
  read -r -s -p "일반 Bitget API Passphrase: " BITGET_STANDARD_PASSPHRASE; echo
else
  BITGET_STANDARD_SECRET=""
  BITGET_STANDARD_PASSPHRASE=""
fi

echo
read -r -s -p "Elite Trading API Key: " BITGET_ELITE_KEY; echo
read -r -s -p "Elite Trading API Secret(HMAC Key): " BITGET_ELITE_SECRET; echo
read -r -s -p "Elite Trading API Passphrase: " BITGET_ELITE_PASSPHRASE; echo

if [[ -z "$DASH_USER" || -z "$DASH_PASS" ]]; then
  echo "오류: 대시보드 관리자 아이디/비밀번호가 필요합니다." >&2
  exit 2
fi
if [[ -z "$BITGET_ELITE_KEY" || -z "$BITGET_ELITE_SECRET" || -z "$BITGET_ELITE_PASSPHRASE" ]]; then
  echo "오류: Elite API Key/Secret/Passphrase 세 값이 모두 필요합니다." >&2
  exit 2
fi

SESSION_SECRET="$($PY -c 'import secrets; print(secrets.token_urlsafe(64))')"
export DASH_USER DASH_PASS SESSION_SECRET
export BITGET_STANDARD_KEY BITGET_STANDARD_SECRET BITGET_STANDARD_PASSPHRASE
export BITGET_ELITE_KEY BITGET_ELITE_SECRET BITGET_ELITE_PASSPHRASE

$PY - <<'PY'
from pathlib import Path
import json
import os

path = Path('.env')
updates = {
    'BOT_MODE': 'PAPER',
    'EXCHANGE': 'bitget',
    'ASSET_CLASS': 'crypto',
    'BITGET_EXECUTION_PROFILE': 'elite',
    'BITGET_API_FAMILY': 'classic-first',
    'LEVERAGE': '15',
    'MARGIN_MODE': 'crossed',
    'LIVE_REQUIRE_ONE_WAY_MODE': 'true',
    'MAX_PYRAMIDING': '1',
    'LIVE_ENTRY_MULTIPLIER': '8.6',
    'LIVE_MAX_ENTRIES_PER_POSITION': '1',
    'LIVE_MAX_TOTAL_MULTIPLIER': '15',
    'REQUIRE_EXCHANGE_PROTECTION': 'true',
    'DASHBOARD_HOST': '127.0.0.1',
    'DASHBOARD_PORT': '8000',
    'DASHBOARD_PUBLIC_URL': 'http://34.132.172.40',
    'DASHBOARD_AUTH_ENABLED': 'true',
    'DASHBOARD_USERNAME': os.environ['DASH_USER'],
    'DASHBOARD_PASSWORD': os.environ['DASH_PASS'],
    'DASHBOARD_SESSION_SECRET': os.environ['SESSION_SECRET'],
    'DASHBOARD_SESSION_HOURS': '12',
    'DASHBOARD_COOKIE_SECURE': 'false',
    'BITGET_STANDARD_API_KEY': os.environ['BITGET_STANDARD_KEY'],
    'BITGET_STANDARD_API_SECRET': os.environ['BITGET_STANDARD_SECRET'],
    'BITGET_STANDARD_API_PASSPHRASE': os.environ['BITGET_STANDARD_PASSPHRASE'],
    'BITGET_ELITE_API_KEY': os.environ['BITGET_ELITE_KEY'],
    'BITGET_ELITE_API_SECRET': os.environ['BITGET_ELITE_SECRET'],
    'BITGET_ELITE_API_PASSPHRASE': os.environ['BITGET_ELITE_PASSPHRASE'],
    'BITGET_API_KEY': '',
    'BITGET_API_SECRET': '',
    'BITGET_API_PASSPHRASE': '',
}

def encode(value: str) -> str:
    if value.lower() in {'true', 'false'} or value.replace('.', '', 1).isdigit():
        return value
    return json.dumps(value, ensure_ascii=False)

old = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
out = []
seen = set()
for line in old:
    if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
        out.append(line)
        continue
    key = line.split('=', 1)[0].strip()
    if key in updates:
        out.append(f'{key}={encode(updates[key])}')
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f'{key}={encode(value)}')
path.write_text('\n'.join(out).rstrip() + '\n', encoding='utf-8')
PY

unset DASH_USER DASH_PASS SESSION_SECRET
unset BITGET_STANDARD_KEY BITGET_STANDARD_SECRET BITGET_STANDARD_PASSPHRASE
unset BITGET_ELITE_KEY BITGET_ELITE_SECRET BITGET_ELITE_PASSPHRASE
chmod 600 .env

echo
echo "===== REDACTED CONFIG CHECK ====="
$PY - <<'PY'
from universal_bot.config import Settings
s = Settings()
print('BOT_MODE                    =', s.bot_mode)
print('EXCHANGE                    =', s.exchange)
print('BITGET_EXECUTION_PROFILE    =', s.bitget_execution_profile)
print('LEVERAGE                    =', s.leverage)
print('MARGIN_MODE                 =', s.margin_mode)
print('LIVE_REQUIRE_ONE_WAY_MODE   =', s.live_require_one_way_mode)
print('MAX_PYRAMIDING              =', s.max_pyramiding)
print('LIVE_ENTRY_MULTIPLIER       =', s.live_entry_multiplier)
print('LIVE_MAX_ENTRIES            =', s.live_max_entries_per_position)
print('LIVE_MAX_TOTAL_MULTIPLIER   =', s.live_max_total_multiplier)
print('DASHBOARD_AUTH              =', 'SET' if s.dashboard_username and s.dashboard_password and s.dashboard_session_secret else 'MISSING')
print('BITGET_STANDARD_API         =', 'SET' if all(s.bitget_standard_credentials) else 'NOT SET (optional)')
print('BITGET_ELITE_API            =', 'SET' if all(s.bitget_elite_credentials) else 'MISSING')
PY

echo
echo "저장 완료. 아직 PAPER 모드입니다."
echo "다음 단계: Elite 레버리지 동기화 후 LIVE preflight"
