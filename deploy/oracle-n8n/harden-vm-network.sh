#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_DROPIN="/etc/ssh/sshd_config.d/99-tia-hardening.conf"
SSH_BACKUP="/etc/ssh/sshd_config.d/99-tia-hardening.conf.before-tia"

export DEBIAN_FRONTEND=noninteractive

echo "Installing UFW if needed..."
apt-get update -qq
apt-get install -y -qq ufw >/dev/null

# Preserve the current Tia drop-in if this script is ever rerun after manual edits.
if [[ -f "$SSH_DROPIN" && ! -f "$SSH_BACKUP" ]]; then
  cp "$SSH_DROPIN" "$SSH_BACKUP"
  chmod 600 "$SSH_BACKUP"
fi

cat > "$SSH_DROPIN" <<'EOF'
# Tia production SSH hardening.
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
EOF
chmod 644 "$SSH_DROPIN"

echo "Validating SSH configuration before reload..."
if ! sshd -t; then
  echo "SSH configuration validation failed. Restoring previous drop-in if available." >&2
  if [[ -f "$SSH_BACKUP" ]]; then
    cp "$SSH_BACKUP" "$SSH_DROPIN"
  else
    rm -f "$SSH_DROPIN"
  fi
  sshd -t || true
  exit 1
fi

# Allow SSH before enabling the firewall so the current session is not locked out.
echo "Configuring host firewall..."
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp comment 'SSH' >/dev/null
ufw allow 80/tcp comment 'HTTP' >/dev/null
ufw allow 443/tcp comment 'HTTPS' >/dev/null
ufw --force enable >/dev/null

# Reload SSH only after validation and after confirming port 22 is allowed.
systemctl reload ssh

echo
echo "VM network hardening applied."
echo "SSH effective settings:"
sshd -T | grep -E '^(permitrootlogin|passwordauthentication|pubkeyauthentication) '

echo
echo "UFW status:"
ufw status verbose

echo
echo "Listening production ports:"
ss -lntup | grep -E ':(22|80|443|5432|5678)\b' || true

echo
echo "Running Tia health check..."
cd "$DEPLOY_DIR"
bash ./healthcheck-production.sh
