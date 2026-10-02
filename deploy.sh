#!/bin/bash
# Deploy wt-analytics-alerts as a Cloud Run Job.
#
# First-time setup (run once — creates secrets in Secret Manager):
#   bash deploy.sh --setup
#
# Build and deploy:
#   bash deploy.sh
#
# Trigger a manual run:
#   bash deploy.sh --run

set -euo pipefail

PROJECT_ID="wt-bigquery"
REGION="us-central1"
JOB_NAME="wt-analytics-alerts"
IMAGE="gcr.io/${PROJECT_ID}/${JOB_NAME}"
SERVICE_ACCOUNT="812284996719-compute@developer.gserviceaccount.com"

# Not a secret, just config — every deployed alert DMs all of these (see
# DM_RECIPIENT_ENV_VARS in alerts/slack_notifier.py). Add an entry here (and the
# matching env var in --set-env-vars below) for anyone else who should get every
# alert.
DEV_SLACK_DM_USER_ID="U0AQKF6Q125"
NICK_SLACK_DM_USER_ID="U075LJ7MGG1"

# ---------------------------------------------------------------------------
# Secret names in Secret Manager
# ---------------------------------------------------------------------------
SECRETS=(
    "wt-analytics-alerts-slack-bot-token:SLACK_BOT_TOKEN"
    "wt-analytics-alerts-groq-api-key:GROQ_API_KEY"
)

setup_secrets() {
    echo "=== First-time secret setup ==="
    echo "Creating secrets in Secret Manager and granting service account access."
    echo ""

    for entry in "${SECRETS[@]}"; do
        secret_name="${entry%%:*}"
        env_var="${entry##*:}"

        if gcloud secrets describe "$secret_name" --project="$PROJECT_ID" &>/dev/null; then
            echo "[SKIP] $secret_name already exists"
        else
            gcloud secrets create "$secret_name" \
                --project="$PROJECT_ID" \
                --replication-policy="automatic"
            echo "[CREATED] $secret_name"
        fi

        echo "  Paste value for ${env_var} (${secret_name}), then Enter:"
        read -r secret_val
        echo -n "$secret_val" | gcloud secrets versions add "$secret_name" \
            --project="$PROJECT_ID" --data-file=-

        gcloud secrets add-iam-policy-binding "$secret_name" \
            --project="$PROJECT_ID" \
            --member="serviceAccount:${SERVICE_ACCOUNT}" \
            --role="roles/secretmanager.secretAccessor" \
            --quiet
    done

    echo ""
    echo "=== Setup complete. Run bash deploy.sh to build and deploy. ==="
}

build_set_secrets_flags() {
    local flags=""
    for entry in "${SECRETS[@]}"; do
        secret_name="${entry%%:*}"
        env_var="${entry##*:}"
        flags+="${env_var}=${secret_name}:latest,"
    done
    echo "${flags%,}"  # strip trailing comma
}

deploy() {
    echo "Building container image ..."
    gcloud builds submit \
        --tag "$IMAGE" \
        --project "$PROJECT_ID" \
        .

    SECRETS_FLAGS=$(build_set_secrets_flags)

    echo "Creating/updating Cloud Run Job ..."
    gcloud run jobs create "$JOB_NAME" \
        --image "$IMAGE" \
        --project "$PROJECT_ID" \
        --region "$REGION" \
        --service-account "$SERVICE_ACCOUNT" \
        --set-secrets "$SECRETS_FLAGS" \
        --set-env-vars "DEV_SLACK_DM_USER_ID=${DEV_SLACK_DM_USER_ID},NICK_SLACK_DM_USER_ID=${NICK_SLACK_DM_USER_ID}" \
        --memory 512Mi \
        --cpu 1 \
        --max-retries 1 \
        --task-timeout 300 \
        2>/dev/null \
    || gcloud run jobs update "$JOB_NAME" \
        --image "$IMAGE" \
        --project "$PROJECT_ID" \
        --region "$REGION" \
        --service-account "$SERVICE_ACCOUNT" \
        --set-secrets "$SECRETS_FLAGS" \
        --set-env-vars "DEV_SLACK_DM_USER_ID=${DEV_SLACK_DM_USER_ID},NICK_SLACK_DM_USER_ID=${NICK_SLACK_DM_USER_ID}" \
        --memory 512Mi \
        --cpu 1 \
        --max-retries 1 \
        --task-timeout 300

    echo ""
    echo "Deployed. To trigger a run: bash deploy.sh --run"
    echo ""
    echo "Scheduler job (create once — this is what's currently live, once daily):"
    echo "  # 7am WAT / 9am EAT (Kenya) — the upstream marts finish rebuilding by ~05:00 UTC"
    echo "  # (wt-ga4-events-daily-betika), so this runs a little after. A second daily trigger"
    echo "  # was tried and removed 2026-09-29 — the mart only rebuilds once a day, so a second"
    echo "  # run just re-checks the same data and double-sends any alert."
    echo "  gcloud scheduler jobs create http ${JOB_NAME}-daily-betika \\"
    echo "      --project=${PROJECT_ID} --location=${REGION} \\"
    echo "      --schedule=\"0 7 * * *\" --time-zone=\"Africa/Lagos\" \\"
    echo "      --uri=\"https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run\" \\"
    echo "      --http-method=POST --oauth-service-account-email=${SERVICE_ACCOUNT}"
}

run_job() {
    echo "Triggering Cloud Run Job: ${JOB_NAME} ..."
    gcloud run jobs execute "$JOB_NAME" \
        --region "$REGION" \
        --project "$PROJECT_ID"
}

# ---------------------------------------------------------------------------

case "${1:-}" in
    --setup) setup_secrets ;;
    --run)   run_job ;;
    *)       deploy ;;
esac
