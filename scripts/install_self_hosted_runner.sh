#!/usr/bin/env bash
set -euo pipefail

# One-time setup helper for the user's Linux trading server.
# The short-lived GitHub runner registration token MUST be supplied interactively
# and must never be committed to the repository or pasted into chat.

REPO="nictunz/universal-trading-bot"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner-trading-bot}"
RUNNER_NAME="${RUNNER_NAME:-trading-bot-server}"
LABELS="${RUNNER_LABELS:-trading-bot}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: this helper currently supports Linux only." >&2
  exit 1
fi

case "$(uname -m)" in
  x86_64) ARCH="x64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  armv7l) ARCH="arm" ;;
  *) echo "ERROR: unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

command -v curl >/dev/null || { echo "ERROR: curl is required" >&2; exit 1; }
command -v tar >/dev/null || { echo "ERROR: tar is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "ERROR: jq is required (sudo apt-get install -y jq)" >&2; exit 1; }

if [[ -d "$RUNNER_DIR" && -f "$RUNNER_DIR/config.sh" ]]; then
  echo "Runner directory already exists: $RUNNER_DIR"
  echo "If this is an existing runner, do not re-register it."
  exit 0
fi

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

VERSION="$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest | jq -r .tag_name)"
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "ERROR: could not determine runner version" >&2; exit 1; }
TARBALL="actions-runner-linux-${ARCH}-${VERSION#v}.tar.gz"
URL="https://github.com/actions/runner/releases/download/${VERSION}/${TARBALL}"

curl -fL --retry 3 -o "$TARBALL" "$URL"

echo "Downloaded GitHub Actions runner ${VERSION} (${ARCH})."

tar xzf "$TARBALL"
rm -f "$TARBALL"

if [[ ! -x ./config.sh ]]; then
  echo "ERROR: runner config.sh was not extracted" >&2
  exit 1
fi

read -r -s -p "GitHub runner registration token (do not paste it into chat): " REG_TOKEN
printf '\n'
[[ -n "$REG_TOKEN" ]] || { echo "ERROR: registration token is empty" >&2; exit 1; }

./config.sh \
  --url "https://github.com/${REPO}" \
  --token "$REG_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$LABELS" \
  --work _work \
  --unattended

unset REG_TOKEN

if command -v sudo >/dev/null; then
  echo "Installing runner as a system service..."
  sudo ./svc.sh install
  sudo ./svc.sh start
  sudo ./svc.sh status
else
  echo "sudo is unavailable. Runner configured but not installed as a service."
  echo "Run ./run.sh to start it manually."
fi

echo
printf 'Runner setup complete.\n'
printf 'Runner directory: %s\n' "$RUNNER_DIR"
printf 'Runner name: %s\n' "$RUNNER_NAME"
printf 'Labels: %s\n' "$LABELS"
printf 'Next: GitHub repo -> Settings -> Actions -> Runners should show the runner as Idle/Online.\n'
