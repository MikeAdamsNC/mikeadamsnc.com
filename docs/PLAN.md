# mikeadamsnc.com: plan

## Decided (2026-10-21)

**Hosting: a real server app on Cloud Run, the cheap way.** Not a static site.

- **Where:** Cloud Run in GCP project `macmanager-home`, region `us-east1`, next to the
  Cloud DNS zone `mikeadamsnc-com` that already holds the domain. GitHub Pages is
  retired when the new site goes live.
- **Shuts down when idle** (no always-on instance). A Cloud Scheduler job pings it every
  10 minutes so a visitor almost never waits for it to start. Google can still restart
  it now and then; the rare first visit after that waits about a second. Always on is
  one setting away (about $10-15/month) if that ever matters.
- **Domain:** connected straight to Cloud Run (domain mapping), the same way
  `startfishing.app` already works. No load balancer.
- **Storage:** Firestore for submitted ideas and their status.
- **Expected cost:** under $1/month. The ping is the account's 2nd of 3 free Scheduler
  jobs (the 1st is `noaa-cloud-job-every-15`); the pings fit inside Cloud Run's free
  monthly allowance; Firestore is free at this traffic.
- **Language:** Python (same as Archer), pages built on the server, little JavaScript.

Why: Mike's other small sites (Fuster Cluck Farm, DualSpend, Soma) already run idle-to-
zero on Cloud Run at about $0; his spend today is StartFishing's always-on API and
Cloud SQL database plus the Chesnick WordPress VM. $10-15/month more for always on was
not worth it for a personal site.

## Still being shaped

What the site actually is. First idea, not settled:

- A form anyone can use to send Mike an idea to build (what it is; app, website or other;
  personal, business or to sell; who pays whom; design and feature ideas; marketing;
  plus name and email so he can reply).
- A private queue only Mike can open (Sign in with Google) to sort those ideas.
- A showcase of things he has built (StartFishing, the fridge display, Archer).
- A count of what he is building right now.
