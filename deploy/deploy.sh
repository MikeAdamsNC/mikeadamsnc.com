#!/bin/sh
# Builds the site from this repo and puts it live on Cloud Run.
# Shuts down when idle (min instances 0); the keep-warm ping holds it ready.
set -e
cd "$(dirname "$0")/.."
gcloud run deploy mikeadamsnc \
  --project macmanager-home --region us-east1 \
  --source . \
  --allow-unauthenticated \
  --min-instances 0 --max-instances 2 \
  --memory 256Mi --cpu 1 --concurrency 80 \
  --cpu-boost \
  --quiet
