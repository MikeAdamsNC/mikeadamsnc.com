# How MikeAdamsNC.com works

Plain language. Update this in the same change as anything it describes.

## The pieces

- **The app** (`web/`) is one small Python program (FastAPI). Each page is built from a
  template in `web/templates/`; the words come from `content/` (`site.yaml`,
  `projects.yaml`, `experiments.yaml`), so changing copy never means touching code. The
  logo and icons are served from `brand/`; the stylesheet and the page's small script
  are in `web/static/`.
- **Pages:** home, the Lab (`/lab`) and one page per experiment (`/lab/<name>`), one page
  per project (`/projects/<name>`), the idea form (`/pitch`), privacy, and Mike's private
  dashboard (`/admin`).
- **Where it runs:** Google Cloud Run, service `mikeadamsnc`, project `macmanager-home`,
  region us-east1, as its own identity `mikeadamsnc-web` (allowed to use the site's
  database, write analytics and read its two secrets, nothing else). It shuts down when
  idle and costs about nothing.
- **Keeping it warm:** the scheduler job `mikeadamsnc-keep-warm` visits `/health` every
  10 minutes so a visitor rarely waits for it to start.
- **The address:** DNS is in Cloud DNS (zone `mikeadamsnc-com`). `mikeadamsnc.com` and
  `www` point at Cloud Run; Google renews the HTTPS certificate. The same zone holds
  the Mailgun email records (MX, SPF, DKIM): leave those alone.

## Ideas people pitch

The form saves each pitch to Firestore (database `mikeadamsnc`, collection `pitches`).
Spam protection: a hidden trap field, a check that a person took at least 3 seconds,
and at most 5 pitches per visitor per day. Mike sees and sorts pitches (new, maybe,
building, done, no) on the dashboard.

**Getting to Mike's phone:** Archer's `site_pitches` job asks the site's private address
`/api/pitches/unsent` every 5 minutes with a long secret token (Secret Manager
`mikeadamsnc-archer-token`; the same value is `MIKEADAMSNC_TOKEN` in Archer's
`secrets/archer.env`), pushes each new pitch, and marks it sent. Archer reaches out to
the site; the site can't reach Archer.

## Analytics (ours, no cookies)

Every page view is recorded by the server; the page's script adds scroll depth (25, 50,
75, 100%), X-ray opens, buttons pressed, links clicked out, and the first keystroke in
the idea form. Rows go to BigQuery table `site_analytics.events`. Bots, the keep-warm
ping and Mike's private pages aren't counted.

A visitor is a 16-character code made from the day's random salt (Firestore `salts`,
one per Eastern day, deleted after two days), the IP address and the browser. The same
person is one visitor today and a stranger tomorrow; IP addresses are never stored.

The dashboard reads the same table: views, visitors, pages, where people came from,
devices, scroll depth, the pitch funnel, experiments read, links clicked out.

## The X-ray view

The λ button (or the X key) turns the page into a blueprint. Anything with a `data-x`
attribute in a template is outlined and labeled; the "How this page works" panel shows
the server, how long this page took to build, pages served today (from analytics,
cached five minutes), the version and the last deploy.

## Mike's sign-in

`/admin` uses Sign in with Google and lets in only `ADMIN_EMAILS` (set in
`deploy/deploy.sh`). It needs a Google sign-in client, made once in the Cloud console
(no command line can make one): Google Auth Platform, client type "Web application",
redirect addresses `https://mikeadamsnc.com/auth/callback`,
`https://www.mikeadamsnc.com/auth/callback` and the preview's `/auth/callback`. Its id
and secret go in Secret Manager as `mikeadamsnc-google-client-id` and
`mikeadamsnc-google-client-secret`; the deploy script picks them up when they exist.
The sign-in cookie is the only cookie the site sets.

## Scheduled jobs

| Job | When | What it does |
|---|---|---|
| `mikeadamsnc-keep-warm` | Every 10 minutes | Visits the site so it stays ready for visitors. |
| Archer `site_pitches` | Every 5 minutes | Pushes each new pitch to Mike's phone, then marks it sent. |

## Changing the site

1. Edit on a branch; run the tests: `.venv/bin/python -m pytest -q web/tests`.
2. Merge. Then `PREVIEW=1 ./deploy/deploy.sh` puts it on a private preview address
   without touching the live site, and `./deploy/deploy.sh` makes it live (about two
   minutes either way).

## Cost

Expected under $1/month: Cloud Run, Firestore and BigQuery all stay inside Google's
free monthly allowances at this traffic; the scheduler job is one of three free ones.
