#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-ubuntu}"
RUN_GROUP="$(id -gn "$RUN_USER")"

SERVICE_PATH="/etc/systemd/system/tia-n8n-backup.service"
TIMER_PATH="/etc/systemd/system/tia-n8n-backup.timer"

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Tia n8n production backup
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$DEPLOY_DIR
ExecStart=/usr/bin/bash $DEPLOY_DIR/backup-production.sh
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
EOF

cat > "$TIMER_PATH" <<'EOF'
[Unit]
Description=Daily Tia n8n production backup

[Timer]
OnCalendar=*-*-* 03:15:00 Africa/Cairo
Persistent=true
RandomizedDelaySec=5m
Unit=tia-n8n-backup.service

[Install]
WantedBy=timers.target
EOF

chmod 644 "$SERVICE_PATH" "$TIMER_PATH"
systemctl daemon-reload
systemctl enable --now tia-n8n-backup.timer

echo
echo "Backup timer installed."
systemctl list-timers tia-n8n-backup.timer --no-pager

echo
echo "Service definition: $SERVICE_PATH"
echo "Timer definition: $TIMER_PATH"
echo "Daily schedule: around 03:15 Africa/Cairo (up to 5 minutes randomized delay)."
echo "Missed runs execute after the VM comes back because Persistent=true."
