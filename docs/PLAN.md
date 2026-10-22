# MikeAdamsNC.com: plan

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

## What the site is (2026-10-22, draft)

MikeAdamsNC.com is Mike's personal brand, with his personality baked in. For anyone who
lands there. In order of weight:

1. **Here's what I make.** The things he has built lead the page.
2. **This is Mike.** Who he is outside of work. His day job stays completely off the site.
3. **Got an idea?** A form anyone can use to pitch something for him to build. No
   commitment: he reads everything and picks the occasional one he can get behind.

A great year: a couple of fun projects he believes in and helps bring to life. Making
money, building cool things and helping people all count.

Behind the form: a private queue only Mike can open (Sign in with Google), and a public
count of what he is building right now.

## Next

Brand first (logo, colors, type, voice), made in Claude Design from `docs/BRAND-BRIEF.md`.
Then the site.
