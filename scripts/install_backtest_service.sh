#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${BACKTEST_VENV:-$HOME/.cache/universal-trading-bot-ci-venv}"
USER_NAME="${SUDO_USER:-$USER}"
SERVICE="universal-trading-bot-backtest@.service"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Backtest venv missing: $VENV" >&2
  exit 1
fi

sudo tee "/etc/systemd/system/$SERVICE" >/dev/null <<EOF
[Unit]
Description=Universal Trading Bot Backtest (%i)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$ROOT
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$ROOT/.env
EnvironmentFile=-$ROOT/.backtest-%i.env
ExecStart=$VENV/bin/python $ROOT/scripts/run_one_year_backtest.py
Restart=no
Nice=19
IOSchedulingClass=idle
CPUAccounting=true
MemoryAccounting=true
CPUQuota=35%
MemoryHigh=300M
MemoryMax=420M
MemorySwapMax=768M
OOMScoreAdjust=500
StandardOutput=append:%h/.cache/universal-trading-bot/%i-one-year-backtest.log
StandardError=append:%h/.cache/universal-trading-bot/%i-one-year-backtest.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload

echo "Installed $SERVICE"
echo "CPUQuota=35%, MemoryHigh=300M, MemoryMax=420M, MemorySwapMax=768M"
echo "This affects future systemd-managed backtests only; it does not interrupt a currently running nohup backtest."
