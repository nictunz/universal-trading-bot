# Google Cloud Build Android CI setup

This repository uses Cloud Build for the signed Android build while keeping GitHub Actions as a manual fallback. Long optimization and deployment jobs continue to use the existing self-hosted `trading-bot` runner.

## Cost boundary

- Keep the default Cloud Build pool and `e2-standard-2` machine type. This is the machine type covered by the monthly promotional free build-minute allowance.
- Do not select `E2_HIGHCPU_8`, `E2_HIGHCPU_32`, or a private pool when the goal is zero compute charge.
- Set a Google Cloud billing budget and alerts. A budget alerts you; it is not a hard spending cap.

## One-time Google Cloud setup

Set the project and region from a terminal with `gcloud` already authenticated:

```bash
export PROJECT_ID='YOUR_GOOGLE_CLOUD_PROJECT_ID'
export REGION='asia-northeast3'
gcloud config set project "$PROJECT_ID"
gcloud services enable cloudbuild.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com storage.googleapis.com

gcloud artifacts repositories describe ci --location "$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create ci --repository-format docker --location "$REGION"

gcloud storage buckets describe "gs://${PROJECT_ID}-cloudbuild-cache" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${PROJECT_ID}-cloudbuild-cache" --location "$REGION" --uniform-bucket-level-access
gcloud storage buckets describe "gs://${PROJECT_ID}-cloudbuild-artifacts" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${PROJECT_ID}-cloudbuild-artifacts" --location "$REGION" --uniform-bucket-level-access
```

Create a dedicated build service account:

```bash
gcloud iam service-accounts describe "cloud-build-ci@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1 || \
  gcloud iam service-accounts create cloud-build-ci --display-name 'Cloud Build CI'

for role in roles/cloudbuild.builds.builder roles/logging.logWriter roles/artifactregistry.writer roles/storage.objectAdmin roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:cloud-build-ci@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role "$role"
done

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
gcloud iam service-accounts add-iam-policy-binding \
  "cloud-build-ci@${PROJECT_ID}.iam.gserviceaccount.com" \
  --member "serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com" \
  --role roles/iam.serviceAccountTokenCreator
```

Create these five Secret Manager secrets using the values already configured for the Android GitHub workflow:

| Secret Manager name | Existing GitHub secret |
|---|---|
| `android-keystore-base64` | `ANDROID_KEYSTORE_BASE64` |
| `android-keystore-password` | `ANDROID_KEYSTORE_PASSWORD` |
| `android-key-alias` | `ANDROID_KEY_ALIAS` |
| `android-key-password` | `ANDROID_KEY_PASSWORD` |
| `android-update-ssh-private-key` | `ANDROID_UPDATE_SSH_PRIVATE_KEY` |

For each value, create the secret and add a version without putting the value in the command line history:

```bash
gcloud secrets create SECRET_NAME --replication-policy automatic
printf '%s' 'PASTE_VALUE_HERE' | gcloud secrets versions add SECRET_NAME --data-file=-
```

Do not commit or upload the signing key, passwords, or SSH private key to the repository.

Build and store the reusable Android builder image once:

```bash
gcloud builds submit --config cloudbuild.builder.yaml --region "$REGION" .
```

## Connect GitHub and create the trigger

1. Open Google Cloud Console > Cloud Build > Repositories (2nd gen).
2. Select `asia-northeast3`, create a GitHub connection, install/authorize the Google Cloud Build GitHub App, and link `nictunz/universal-trading-bot`.
3. Create a push trigger for branch `^main$` using `cloudbuild.yaml`.
4. Choose `cloud-build-ci@PROJECT_ID.iam.gserviceaccount.com` as the service account.
5. Include these paths: `android/**`, `universal_bot/**`, `tests/**`, `pyproject.toml`, `cloudbuild.yaml`, `cloudbuild/**`.
6. Exclude `reports/**` so generated report commits cannot rebuild the APK.

The GitHub connection supplies the private source checkout automatically. The separate GitHub SSH deploy-key procedure is only required for manually submitted builds which clone another private repository during the build.

## Run and retrieve

- A relevant push to `main` starts Cloud Build automatically.
- A phone can start the same trigger from Google Cloud Console.
- Signed outputs and the log are stored at `gs://PROJECT_ID-cloudbuild-artifacts/android/REVISION/`.
- The verified APK and manifest are also atomically published to the existing private Android update server.

Manual smoke test after the trigger is configured:

```bash
gcloud builds triggers run TRIGGER_NAME --branch main --region "$REGION"
```
