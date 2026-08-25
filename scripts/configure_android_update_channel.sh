#!/usr/bin/env bash
set -euo pipefail

REPO="nictunz/universal-trading-bot"
ROOT="${HOME}/.config/universal-trading-bot/android-release"
KEYSTORE="$ROOT/universal-release.jks"
DEPLOY_KEY="$ROOT/github-actions-android-update"
ALIAS="universal"

mkdir -p "$ROOT" "$HOME/.ssh"
chmod 700 "$ROOT" "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"

for cmd in gh keytool ssh-keygen base64; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: required command is missing: $cmd" >&2
    if [[ "$cmd" == "gh" ]]; then
      echo "Install GitHub CLI first, then run: gh auth login" >&2
    elif [[ "$cmd" == "keytool" ]]; then
      echo "Install Java/keytool first (OpenJDK 17 is recommended)." >&2
    fi
    exit 2
  fi
done

if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: GitHub CLI is not authenticated." >&2
  echo "Run: gh auth login" >&2
  echo "Then rerun this script. Do not paste any token into ChatGPT." >&2
  exit 3
fi

printf 'Android stable signing password: '
IFS= read -r -s PASS1
echo
printf 'Password again: '
IFS= read -r -s PASS2
echo
if [[ -z "$PASS1" || "$PASS1" != "$PASS2" ]]; then
  echo "ERROR: passwords are empty or do not match." >&2
  exit 4
fi
if (( ${#PASS1} < 12 )); then
  echo "ERROR: use at least 12 characters." >&2
  exit 5
fi

if [[ ! -f "$KEYSTORE" ]]; then
  echo "Creating stable Android signing keystore..."
  keytool -genkeypair \
    -keystore "$KEYSTORE" \
    -storepass "$PASS1" \
    -keypass "$PASS1" \
    -alias "$ALIAS" \
    -keyalg RSA \
    -keysize 4096 \
    -validity 10000 \
    -dname "CN=Universal Trading Bot Android,O=nictunz,C=KR" \
    >/dev/null
  chmod 600 "$KEYSTORE"
else
  echo "Existing signing keystore found; verifying password..."
  keytool -list -keystore "$KEYSTORE" -storepass "$PASS1" -alias "$ALIAS" >/dev/null
fi

if [[ ! -f "$DEPLOY_KEY" ]]; then
  echo "Creating dedicated GitHub Actions -> update-server SSH key..."
  ssh-keygen -q -t ed25519 -N '' -C 'github-actions-android-update' -f "$DEPLOY_KEY"
  chmod 600 "$DEPLOY_KEY"
  chmod 644 "$DEPLOY_KEY.pub"
fi

PUB="$(cat "$DEPLOY_KEY.pub")"
if ! grep -Fqx "$PUB" "$HOME/.ssh/authorized_keys"; then
  printf '%s\n' "$PUB" >> "$HOME/.ssh/authorized_keys"
fi

TMP_B64="$(mktemp)"
trap 'rm -f "$TMP_B64"; unset PASS1 PASS2' EXIT
base64 -w0 "$KEYSTORE" > "$TMP_B64"

echo "Writing GitHub Actions secrets without printing secret values..."
gh secret set ANDROID_KEYSTORE_BASE64 --repo "$REPO" < "$TMP_B64"
printf '%s' "$PASS1" | gh secret set ANDROID_KEYSTORE_PASSWORD --repo "$REPO"
printf '%s' "$ALIAS" | gh secret set ANDROID_KEY_ALIAS --repo "$REPO"
printf '%s' "$PASS1" | gh secret set ANDROID_KEY_PASSWORD --repo "$REPO"
gh secret set ANDROID_UPDATE_SSH_PRIVATE_KEY --repo "$REPO" < "$DEPLOY_KEY"

unset PASS1 PASS2
rm -f "$TMP_B64"
trap - EXIT

echo
echo "===== ANDROID UPDATE CHANNEL ====="
echo "SIGNING_KEYSTORE          = SET"
echo "SIGNING_SECRETS           = SET"
echo "UPDATE_SERVER_SSH_SECRET  = SET"
echo "SERVER_AUTHORIZED_KEY     = SET"
echo "BOT_MODE                   = unchanged"
echo
echo "Triggering a fresh verified Android build..."
gh workflow run build-android-backtester.yml --repo "$REPO"
echo "Triggered. The signed APK will be published only if tests + Android build succeed."
