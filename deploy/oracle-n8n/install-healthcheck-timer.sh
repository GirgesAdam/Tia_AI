#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SERVICE_PATH="/etc/systemd/system/tia-n8n-healthcheck.service"
TIMER_PATH="/etc/systemd/system/tia-n8n-healthcheck.timer"

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Tia n8n production health check and recovery
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
WorkingDirectory=$DEPLOY_DIR
ExecStart=/usr/bin/bash $DEPLOY_DIR/healthcheck-production.sh
TimeoutStartSec=120
EOF

cat > "$TIMER_PATH" <<'EOF'
[Unit]
Description=Periodic Tia n8n production health check

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true
Unit=tia-n8n-healthcheck.service

[Install]
WantedBy=timers.target
EOF

chmod 644 "$SERVICE_PATH" "$TIMER_PATH"
systemctl daemon-reload
systemctl reset-failed tia-n8n-healthcheck.service 2>/dev/null || true
systemctl enable --now tia-n8n-healthcheck.timer

# Run once now so installation also verifies the current production state.
systemctl start tia-n8n-healthcheck.service

echo
echo "Healthcheck timer installed."
systemctl list-timers tia-n8n-healthcheck.timer --no-pager

echo
echo "Latest healthcheck result:"
systemctl status tia-n8n-healthcheck.service --no-pager -l | tail -20

echo
echo "Schedule: 2 minutes after boot, then every 5 minutes."
echo "Recovery scope: Docker containers only; production database contents are never reset."
