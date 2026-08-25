#!/usr/bin/env bash
set -euo pipefail

REPO="nictunz/universal-trading-bot"
ROOT="${BOT_ROOT:-$HOME/universal-trading-bot}"
SIGN_DIR="${ANDROID_SIGN_DIR:-$HOME/.config/universal-trading-bot/android-signing}"
KEYSTORE="$SIGN_DIR/universal-release.p12"
PASSFILE="$SIGN_DIR/keystore-password.txt"
B64FILE="$SIGN_DIR/ANDROID_KEYSTORE_BASE64.txt"

mkdir -p "$SIGN_DIR"
chmod 700 "$SIGN_DIR"

if ! command -v keytool >/dev/null 2>&1; then
  echo "ERROR: keytool not found. Install a JDK first." >&2
  exit 2
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "ERROR: openssl not found." >&2
  exit 2
fi

if [[ ! -f "$KEYSTORE" ]]; then
  PASS="$(openssl rand -hex 24)"
  printf '%s' "$PASS" > "$PASSFILE"
  chmod 600 "$PASSFILE"
  keytool -genkeypair \
    -keystore "$KEYSTORE" \
    -storetype PKCS12 \
    -alias universal \
    -keyalg RSA \
    -keysize 3072 \
    -validity 3650 \
    -dname "CN=Universal Trading Bot Android,O=nictunz,C=KR" \
    -storepass "$PASS" \
    -keypass "$PASS" \
    >/dev/null 2>&1
  chmod 600 "$KEYSTORE"
else
  if [[ ! -s "$PASSFILE" ]]; then
    echo "ERROR: keystore exists but password file is missing: $PASSFILE" >&2
    echo "Do not replace the keystore; the same signing key is required for future app updates." >&2
    exit 3
  fi
fi

base64 -w0 "$KEYSTORE" > "$B64FILE"
printf '\n' >> "$B64FILE"
chmod 600 "$B64FILE"

echo "===== ANDROID UPDATE SIGNING ====="
echo "Stable signing key ready. Secret values are NOT printed."
echo "keystore_backup=$KEYSTORE"
echo "password_backup=$PASSFILE"
echo "base64_secret_file=$B64FILE"
echo

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is authenticated. Registering repository Actions secrets..."
  gh secret set ANDROID_KEYSTORE_BASE64 --repo "$REPO" < "$B64FILE"
  gh secret set ANDROID_KEYSTORE_PASSWORD --repo "$REPO" < "$PASSFILE"
  echo "GITHUB_ACTIONS_SIGNING_SECRETS=SET"
  echo "The Android workflow can now publish signed self-update releases after tests/build pass."
else
  echo "GITHUB_ACTIONS_SIGNING_SECRETS=NOT_SET"
  echo "GitHub CLI is not authenticated on this server."
  echo "In GitHub: repository Settings -> Secrets and variables -> Actions -> New repository secret"
  echo "Create exactly these two secrets using the local files above:"
  echo "  ANDROID_KEYSTORE_BASE64      <- $B64FILE"
  echo "  ANDROID_KEYSTORE_PASSWORD    <- $PASSFILE"
  echo "Do not paste either secret into ChatGPT."
fi

echo
echo "IMPORTANT: back up the keystore and password somewhere private."
echo "Losing this signing key means future APKs cannot update an installed signed app in place."
