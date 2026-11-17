#!/bin/sh
# One time: makes the drop box's private storage and lets the site use it (docs/HOW-IT-WORKS.md,
# "The drop box"). Safe to run again. After it, deploy as usual: deploy.sh turns the drop box
# on when it sees the bucket.
set -e
PROJECT=macmanager-home
BUCKET=mikeadamsnc-drop
SITE=mikeadamsnc-web@macmanager-home.iam.gserviceaccount.com

# Signing download links goes through this Google service.
gcloud services enable iamcredentials.googleapis.com storage.googleapis.com --project "$PROJECT"

# A private bucket next to the site. Nothing in it can ever be made public, and a deleted
# file is gone at once (no 7-day shadow copy).
if ! gcloud storage buckets describe "gs://$BUCKET" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT" --location us-east1 \
    --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=0
fi

# Google lets every "editor" and "viewer" on the project into a new bucket. Take those
# away: only Mike, as the project's owner, and the site keep access.
for pair in "projectEditor roles/storage.legacyBucketOwner" "projectEditor roles/storage.legacyObjectOwner" \
            "projectViewer roles/storage.legacyBucketReader" "projectViewer roles/storage.legacyObjectReader"; do
  set -- $pair
  gcloud storage buckets remove-iam-policy-binding "gs://$BUCKET" --project "$PROJECT" \
    --member "$1:$PROJECT" --role "$2" >/dev/null 2>&1 || true
done

# The site may add, read and delete files in this one bucket, and nothing wider.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --project "$PROJECT" \
  --member "serviceAccount:$SITE" --role roles/storage.objectAdmin >/dev/null

# The site may sign as itself: that is how Mike's ten-minute download links are made
# (Cloud Run has no key file to sign with).
gcloud iam service-accounts add-iam-policy-binding "$SITE" --project "$PROJECT" \
  --member "serviceAccount:$SITE" --role roles/iam.serviceAccountTokenCreator >/dev/null

echo "Drop box storage is ready: gs://$BUCKET. Now deploy: PREVIEW=1 ./deploy/deploy.sh"
