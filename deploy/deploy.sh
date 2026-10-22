#!/bin/sh
# Builds the site from this repo and puts it on Cloud Run.
#   ./deploy/deploy.sh           -> live at mikeadamsnc.com
#   PREVIEW=1 ./deploy/deploy.sh -> a private preview address; the live site is untouched
# Shuts down when idle (min instances 0); the keep-warm ping holds it ready.
set -e
cd "$(dirname "$0")/.."
SECRETS="SESSION_KEY=mikeadamsnc-session-key:latest,ARCHER_TOKEN=mikeadamsnc-archer-token:latest"
# Google sign-in for Mike's dashboard, once its client exists (see docs/HOW-IT-WORKS.md)
if gcloud secrets describe mikeadamsnc-google-client-id --project macmanager-home >/dev/null 2>&1; then
  SECRETS="$SECRETS,GOOGLE_CLIENT_ID=mikeadamsnc-google-client-id:latest,GOOGLE_CLIENT_SECRET=mikeadamsnc-google-client-secret:latest"
fi
TRAFFIC=""
[ -n "$PREVIEW" ] && TRAFFIC="--tag preview --no-traffic"
gcloud run deploy mikeadamsnc \
  --project macmanager-home --region us-east1 \
  --source . \
  --service-account mikeadamsnc-web@macmanager-home.iam.gserviceaccount.com \
  --allow-unauthenticated \
  --min-instances 0 --max-instances 2 \
  --memory 512Mi --cpu 1 --concurrency 80 \
  --cpu-boost \
  --set-env-vars "^|^SITE_BACKEND=cloud|ADMIN_EMAILS=triangleharbor@gmail.com,mikeadamsnc85@gmail.com|BUILD_TIME=$(TZ=America/New_York date '+%b %-d, %-I:%M %p')" \
  --set-secrets "$SECRETS" \
  $TRAFFIC --quiet
# A preview deploy pins live traffic to the old version; a live deploy sends it all to the newest.
if [ -z "$PREVIEW" ]; then
  gcloud run services update-traffic mikeadamsnc --to-latest --project macmanager-home --region us-east1 --quiet
fi
