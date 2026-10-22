# How MikeAdamsNC.com works

Plain language. Update this in the same change as anything it describes.

## The pieces

- **The app** (`web/`) is one small Python program (FastAPI). It builds each page from a
  template in `web/templates/` and serves the logo and icons from `brand/`. Today it has
  one page, the coming-soon page.
- **Where it runs:** Google Cloud Run, service `mikeadamsnc`, in project
  `macmanager-home`, region us-east1 (South Carolina). Cloud Run starts the app when
  someone visits and shuts it down when nobody has for a while, so it costs about
  nothing when idle.
- **Keeping it warm:** a Cloud Scheduler job, `mikeadamsnc-keep-warm`, visits `/health`
  every 10 minutes so the app is usually already running when a real visitor arrives.
  Without it, the first visitor after a quiet spell waits a second or two. Google can
  still restart it now and then.
- **The address:** the domain's DNS lives in Cloud DNS (zone `mikeadamsnc-com`, same
  project). `mikeadamsnc.com` and `www.mikeadamsnc.com` point at Cloud Run through
  domain mappings; Google issues and renews the HTTPS certificate automatically. The
  same zone holds the Mailgun email records (MX, SPF, DKIM): leave those alone.

## Scheduled jobs

| Job | When | What it does |
|---|---|---|
| `mikeadamsnc-keep-warm` | Every 10 minutes | Visits the site so it stays ready for visitors. |

## Changing the site

1. Edit on a branch; run the tests: `.venv/bin/python -m pytest -q web/tests`.
2. Merge, then deploy: `./deploy/deploy.sh` (builds the app and puts it live, about two
   minutes). The keep-warm job is set up by `./deploy/keep-warm.sh`.

## Cost

Expected under $1/month: Cloud Run's free monthly allowance covers this traffic and the
pings; the scheduler job is one of the account's three free jobs.

## Before 2026-10-22

The site was a single page on GitHub Pages. That was switched off when it moved to
Cloud Run.
