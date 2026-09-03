#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${2:-asia-northeast3}"
REPO_ROOT="${BOT_ROOT:-$HOME/universal-trading-bot}"
SIGN_DIR="${ANDROID_SIGN_DIR:-$HOME/.config/universal-trading-bot/android-signing}"
DEPLOY_DIR="${ANDROID_UPDATE_DEPLOY_DIR:-$HOME/.config/universal-trading-bot/android-update-deploy}"
BUILD_ACCOUNT="cloud-build-ci@${PROJECT_ID}.iam.gserviceaccount.com"

if ! command -v gcloud >/dev/null 2>&1; then
  echo 'ERROR: gcloud CLI is not installed.' >&2
  exit 2
fi
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == '(unset)' ]]; then
  echo 'ERROR: pass the Google Cloud project ID as the first argument.' >&2
  exit 3
fi

KEYSTORE_B64="$SIGN_DIR/ANDROID_KEYSTORE_BASE64.txt"
KEYSTORE_PASSWORD="$SIGN_DIR/keystore-password.txt"
UPDATE_SSH_KEY="$DEPLOY_DIR/github-actions-ed25519"
for required_file in "$KEYSTORE_B64" "$KEYSTORE_PASSWORD" "$UPDATE_SSH_KEY"; do
  if [[ ! -s "$required_file" ]]; then
    echo "ERROR: required existing secret file is missing: $required_file" >&2
    exit 4
  fi
done

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com

gcloud artifacts repositories describe ci --location "$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create ci --repository-format docker --location "$REGION"

for bucket_suffix in cloudbuild-cache cloudbuild-artifacts; do
  bucket="gs://${PROJECT_ID}-${bucket_suffix}"
  gcloud storage buckets describe "$bucket" >/dev/null 2>&1 || \
    gcloud storage buckets create "$bucket" --location "$REGION" --uniform-bucket-level-access
done

gcloud iam service-accounts describe "$BUILD_ACCOUNT" >/dev/null 2>&1 || \
  gcloud iam service-accounts create cloud-build-ci --display-name 'Cloud Build CI'

for role in \
  roles/cloudbuild.builds.builder \
  roles/logging.logWriter \
  roles/artifactregistry.writer \
  roles/storage.objectAdmin \
  roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${BUILD_ACCOUNT}" \
    --role "$role" \
    --condition=None >/dev/null
done

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
gcloud beta services identity create --service cloudbuild.googleapis.com --project "$PROJECT_ID" >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$BUILD_ACCOUNT" \
  --member "serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com" \
  --role roles/iam.serviceAccountTokenCreator >/dev/null

add_secret_version() {
  local secret_name="$1"
  local source_file="$2"
  gcloud secrets describe "$secret_name" >/dev/null 2>&1 || \
    gcloud secrets create "$secret_name" --replication-policy automatic >/dev/null
  gcloud secrets versions add "$secret_name" --data-file="$source_file" >/dev/null
}

add_text_secret_version() {
  local secret_name="$1"
  local secret_value="$2"
  gcloud secrets describe "$secret_name" >/dev/null 2>&1 || \
    gcloud secrets create "$secret_name" --replication-policy automatic >/dev/null
  printf '%s' "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=- >/dev/null
}

add_secret_version android-keystore-base64 "$KEYSTORE_B64"
add_secret_version android-keystore-password "$KEYSTORE_PASSWORD"
add_text_secret_version android-key-alias universal
add_secret_version android-key-password "$KEYSTORE_PASSWORD"
add_secret_version android-update-ssh-private-key "$UPDATE_SSH_KEY"

cd "$REPO_ROOT"
gcloud builds submit --config cloudbuild.builder.yaml --region "$REGION" .

echo 'GOOGLE_CLOUD_BUILD_BASE_READY=true'
echo "project=$PROJECT_ID"
echo "region=$REGION"
echo "service_account=$BUILD_ACCOUNT"
echo 'Next: connect nictunz/universal-trading-bot in Cloud Build Repositories (2nd gen), then create the main push trigger from cloudbuild.yaml.'

