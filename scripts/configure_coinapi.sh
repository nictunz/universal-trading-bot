#!/usr/bin/env bash
set -euo pipefail

ROOT="${BOT_ROOT:-$HOME/universal-trading-bot}"
ENV_FILE="${BOT_ENV_FILE:-$ROOT/.env}"
EXAMPLE="$ROOT/.env.example"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$EXAMPLE" ]]; then
    cp "$EXAMPLE" "$ENV_FILE"
  else
    touch "$ENV_FILE"
  fi
fi
chmod 600 "$ENV_FILE"

read -rsp "CoinAPI API key (input is hidden): " key
echo
if [[ -z "$key" ]]; then
  echo "No key entered; nothing changed."
  exit 1
fi

python3 - "$ENV_FILE" "$key" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
key = sys.argv[2]
lines = path.read_text().splitlines() if path.exists() else []
out = []
found = False
for line in lines:
    if line.startswith("COINAPI_API_KEY="):
        out.append("COINAPI_API_KEY=" + key)
        found = True
    else:
        out.append(line)
if not found:
    out.append("COINAPI_API_KEY=" + key)
path.write_text("\n".join(out) + "\n")
PY

chmod 600 "$ENV_FILE"
echo "CoinAPI key saved to $ENV_FILE with mode 600."
echo "The key was not printed."
