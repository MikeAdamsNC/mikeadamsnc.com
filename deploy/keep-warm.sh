#!/bin/sh
# Creates (or updates) the scheduler job that visits the site every 10 minutes,
# so Cloud Run keeps it ready and visitors rarely wait for a cold start.
set -e
URL="https://mikeadamsnc-656071931218.us-east1.run.app/health"
gcloud scheduler jobs describe mikeadamsnc-keep-warm --project macmanager-home --location us-east1 >/dev/null 2>&1 \
  && gcloud scheduler jobs update http mikeadamsnc-keep-warm --project macmanager-home --location us-east1 \
       --schedule="*/10 * * * *" --time-zone=America/New_York --uri="$URL" --http-method=GET --attempt-deadline=30s \
  || gcloud scheduler jobs create http mikeadamsnc-keep-warm --project macmanager-home --location us-east1 \
       --schedule="*/10 * * * *" --time-zone=America/New_York --uri="$URL" --http-method=GET --attempt-deadline=30s \
       --description="Visits MikeAdamsNC.com every 10 minutes so it stays warm."
