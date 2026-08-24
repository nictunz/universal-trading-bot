#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${DASHBOARD_VENV:-$HOME/.cache/universal-trading-bot-dashboard-venv}"
SERVICE="universal-trading-bot-dashboard.service"
NGINX_SITE="universal-trading-bot-dashboard"
PUBLIC_IP="${DASHBOARD_PUBLIC_IP:-34.132.172.40}"
USER_NAME="${SUDO_USER:-$USER}"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Dashboard venv missing: $VENV" >&2
  exit 1
fi
cd "$ROOT"

touch .env
python3 - "$ROOT/.env" "$PUBLIC_IP" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]); ip=sys.argv[2]
updates={"DASHBOARD_HOST":"127.0.0.1","DASHBOARD_PORT":"8000","DASHBOARD_PUBLIC_URL":f"http://{ip}","DASHBOARD_AUTH_ENABLED":"true"}
lines=path.read_text(encoding="utf-8").splitlines() if path.exists() else []
out=[]; seen=set()
for line in lines:
    key=line.split("=",1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
    if key in updates:
        out.append(f"{key}={updates[key]}"); seen.add(key)
    else: out.append(line)
for key,value in updates.items():
    if key not in seen: out.append(f"{key}={value}")
path.write_text("\n".join(out).rstrip()+"\n", encoding="utf-8")
PY

sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx >/dev/null

sudo tee "/etc/systemd/system/$SERVICE" >/dev/null <<EOF
[Unit]
Description=Universal Trading Bot Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$ROOT
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV/bin/python -m universal_bot.main
Restart=always
RestartSec=5
Nice=-5
IOSchedulingClass=best-effort
IOSchedulingPriority=0
CPUAccounting=true
MemoryAccounting=true
CPUWeight=10000
IOWeight=10000
MemoryLow=220M
OOMScoreAdjust=-500

[Install]
WantedBy=multi-user.target
EOF

sudo tee "/etc/nginx/sites-available/$NGINX_SITE" >/dev/null <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 2m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
EOF

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sfn "/etc/nginx/sites-available/$NGINX_SITE" "/etc/nginx/sites-enabled/$NGINX_SITE"
sudo nginx -t
pkill -f "$VENV/bin/python -m universal_bot.main" 2>/dev/null || true
sleep 2
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE"
sudo systemctl restart nginx

for _ in $(seq 1 30); do
  if curl --connect-timeout 1 --max-time 3 -fsS http://127.0.0.1:8000/health >/tmp/utb-health.json 2>/dev/null; then break; fi
  sleep 2
done
if ! curl --connect-timeout 1 --max-time 5 -fsS http://127.0.0.1:8000/health; then
  echo; echo "Dashboard failed health check." >&2
  sudo systemctl --no-pager --full status "$SERVICE" || true
  exit 2
fi

echo
echo "Dashboard service installed with reserved CPU/IO/memory priority."
echo "Public:   http://$PUBLIC_IP"
echo "Internal: http://127.0.0.1:8000"
echo "Strategy: http://$PUBLIC_IP/strategy"
echo "Service:  $SERVICE"
sudo ss -ltnp | grep -E ':80 |:8000 ' || true
