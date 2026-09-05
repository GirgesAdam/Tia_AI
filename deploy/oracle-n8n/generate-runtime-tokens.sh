#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

secrets_dir=".runtime-secrets"
secrets_file="${secrets_dir}/tia-runtime.env"

mkdir -p "$secrets_dir"
chmod 700 "$secrets_dir"

if [[ -f "$secrets_file" ]]; then
  echo "Refusing to overwrite existing runtime secrets at $secrets_file" >&2
  echo "Move or remove that file only if you intentionally want to rotate both tokens." >&2
  exit 1
fi

automation_token="tia_auto_$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')"
channel_token="tia_ch_$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')"

automation_hash="$(printf '%s' "$automation_token" | sha256sum | awk '{print $1}')"
channel_hash="$(printf '%s' "$channel_token" | sha256sum | awk '{print $1}')"

umask 077
cat > "$secrets_file" <<EOF
TIA_AUTOMATION_TOKEN=${automation_token}
TIA_CHANNEL_TOKEN=${channel_token}
EOF
chmod 600 "$secrets_file"

unset automation_token channel_token

echo "Runtime tokens generated and stored locally on the Oracle VM."
echo "Raw tokens are NOT printed."
echo
echo "AUTOMATION_TOKEN_SHA256=${automation_hash}"
echo "CHANNEL_TOKEN_SHA256=${channel_hash}"
echo
echo "Secrets file: $secrets_file"
echo "Permissions: $(stat -c '%a' "$secrets_file")"
