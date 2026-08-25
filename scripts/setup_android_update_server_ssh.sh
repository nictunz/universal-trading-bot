#!/usr/bin/env bash
set -euo pipefail

REPO="nictunz/universal-trading-bot"
DEPLOY_DIR="${ANDROID_UPDATE_DEPLOY_DIR:-$HOME/.config/universal-trading-bot/android-update-deploy}"
PRIVATE_KEY="$DEPLOY_DIR/github-actions-ed25519"
PUBLIC_KEY="$PRIVATE_KEY.pub"
AUTHORIZED_KEYS="$HOME/.ssh/authorized_keys"

mkdir -p "$DEPLOY_DIR" "$HOME/.ssh"
chmod 700 "$DEPLOY_DIR" "$HOME/.ssh"
touch "$AUTHORIZED_KEYS"
chmod 600 "$AUTHORIZED_KEYS"

if ! command -v ssh-keygen >/dev/null 2>&1; then
  echo "ERROR: ssh-keygen not found. Install openssh-client first." >&2
  exit 2
fi

if [[ ! -s "$PRIVATE_KEY" || ! -s "$PUBLIC_KEY" ]]; then
  rm -f "$PRIVATE_KEY" "$PUBLIC_KEY"
  ssh-keygen -q -t ed25519 -N "" -C "github-actions-android-update" -f "$PRIVATE_KEY"
fi
chmod 600 "$PRIVATE_KEY"
chmod 644 "$PUBLIC_KEY"

PUB="$(cat "$PUBLIC_KEY")"
grep -qxF "$PUB" "$AUTHORIZED_KEYS" || printf '%s\n' "$PUB" >> "$AUTHORIZED_KEYS"
unset PUB

echo "===== ANDROID UPDATE SERVER SSH ====="
echo "Dedicated GitHub Actions deployment key is ready."
echo "The public key is installed in $AUTHORIZED_KEYS."
echo "Private key contents are NOT printed."
echo "private_key_secret_file=$PRIVATE_KEY"
echo

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is authenticated. Registering ANDROID_UPDATE_SSH_PRIVATE_KEY..."
  gh secret set ANDROID_UPDATE_SSH_PRIVATE_KEY --repo "$REPO" < "$PRIVATE_KEY"
  echo "GITHUB_ACTIONS_UPDATE_SERVER_SECRET=SET"
else
  echo "GITHUB_ACTIONS_UPDATE_SERVER_SECRET=NOT_SET"
  echo "GitHub CLI is not authenticated on this server."
  echo "In GitHub: repository Settings -> Secrets and variables -> Actions -> New repository secret"
  echo "Create this secret using the local file:"
  echo "  ANDROID_UPDATE_SSH_PRIVATE_KEY <- $PRIVATE_KEY"
  echo "Do not paste the private key into ChatGPT."
fi

echo
echo "After the secret is set, re-run Build Android Backtester APK."
