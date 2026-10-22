# MikeAdamsNC.com: plan

## Decided (2026-10-21)

**Hosting: a real server app on Cloud Run, the cheap way.** Not a static site.

- **Where:** Cloud Run in GCP project `macmanager-home`, region `us-east1`, next to the
  Cloud DNS zone `mikeadamsnc-com` that already holds the domain. Live since
  2026-10-22 (GitHub Pages retired); see `docs/HOW-IT-WORKS.md`.
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

## What the site is (decided 2026-10-22)

MikeAdamsNC.com is Mike's personal brand, for anyone who lands there: what he makes, who he
is (day job never appears), and a place to pitch him ideas. The site is itself an
experiment: things are measured, versions are tried, flops are shown.

## Three kinds of things on the site

1. **Projects:** real things he keeps running (StartFishing, the fridge display, Archer).
2. **Experiments:** one-off tests and showcases, flops included. Each entry has: the
   question, what he used (tools, versions, dates), the result (video, image, demo or
   link), a verdict (worked, meh, flop) with one honest line, and a status (live, done,
   retired). Media lives in a Cloud Storage bucket.
3. **Site versions:** experiments where the site is the subject (Classic, Mountains to
   Sea, Terminal, Talk to it). All versions read the same content; a version is a new
   look, never a copy of the content. Visitors pick one from the menu or the X-ray panel;
   the choice sticks and can be shared as a link (`?v=mountains`).

## The home page (Classic version)

Layout "B, the lab" (mockup in `content-round1/`, kept out of git): headline, the lab
panel, projects as large rows, the experiment log, the pitch section, about, footer
with socials.

- Headline: "I build things with new tech. The good ones stick around."
- Under it: "I try new tools as they show up (Claude Code, Grok, iOS, APIs, whatever's
  next) and turn the best experiments into things people actually use."
- StartFishing: "For beginners and shore anglers: know when to go, and what to throw."
- About: "I'm Mike. I build things with technology as it shows up. Most of it starts as
  a weekend question, like 'could the fridge run the house?' A few turn into something
  I use every day. Some don't, and I'll tell you about those too."
- Socials: X @MikeAdamsNC, Instagram @mikeadamsnc, LinkedIn in/mikeadamsnc, Facebook
  /mikeadams, GitHub MikeAdamsNC.
- First experiments (from old Archer's public build list; never mention his employer,
  money, job search or the kids' names): the radar that tells rain from bugs, the grill
  autopilot, the trail cam AI, school email read for him, Archer fixing its own bugs,
  and the local AI model he killed (a flop).
- Fridge and Archer screenshots use demo data: nothing personal (family calendar,
  school, health, money) is ever published.

## Features

- **X-ray view (in):** a λ button turns the page into a blueprint; every part is
  outlined and tagged with what it is, what built it, and live facts (last change,
  cost, speed). A "How this page works" panel shows the server, tools, pages served
  today, cost this month and the last deploy, all from real numbers.
- **Votes and comments:** thumbs up/down with no sign-in (one per visitor per item,
  spam check, rate limits). Comments need Sign in with Google; an AI check holds spam or
  abuse, everything else posts at once and Mike can remove anything. Ranking is "hot":
  votes weighted by age; Mike can pin or hide. Needs a plain-language privacy page.
- **Pitch bot:** a chat that talks like Mike (Gemini 3.8 Flash on Vertex AI, no API key
  to store). Built from a written profile plus 20 to 30 of Mike's own answers from an
  interview. Says up front it's his AI; never promises to build, quotes prices or agrees
  to terms; knows nothing private. Asks the pitch questions one at a time, writes up the
  pitch, the visitor confirms, it lands in the queue and emails Mike. Also takes "I wish
  the site had..." suggestions, tagged "site idea." Spam check, conversation limits,
  daily cap, GCP budget alert. A plain form stays as the backup. About 2 to 3 cents a
  pitch.
- **Analytics on everything, owned by Mike:** our own, not Google Analytics; no
  tracking cookies (an anonymous visitor ID that resets daily), so no cookie banner.
  Counts page views, referrers, device, site version picked, X-ray opens, scroll depth,
  chats started and finished, pitches, votes, comments, and attention per experiment.
  Stored in BigQuery; shown on a private dashboard only Mike's Google account can open,
  beside the pitch queue. Later, Archer may pull a daily summary into his own data (a
  new Archer collector, built through Archer's normal loop).
- **Live lab:** real signals from home in the lab panel (grill cook, tonight's radar,
  latest trail cam animal). Archer would push a small approved summary out; no new door
  into Archer; nothing that reveals where he lives or when he's away. This changes
  Archer's locked items 18 and 26, so it waits for a clear design and its own dated
  decision first.
- **Mountains to Sea:** the 3D trip across North Carolina (real elevation, live buoy
  waves). A site version and brand piece, not the front door. Prototype in
  `content-round2/`. Needs a lighter version for phones and a calm one for reduced motion.

## Build order

Each step ships on its own.

1. **Core site:** Classic version with the real content, X-ray, the Lab with experiment
   entries, the plain idea form, analytics from day one, private dashboard and queue.
   Built 2026-10-22; on the preview address; goes live when Mike has looked. The
   dashboard waits for the Google sign-in client.
2. **Votes and comments:** Sign in with Google, AI moderation, privacy page. Built
   2026-10-22.
3. **Pitch bot** with site suggestions. Built 2026-10-22 with a generic voice (Mike's
   call); his own voice can come later from the interview.
4. **Live lab** (after the Archer locked-item decision).
5. **Site versions:** Mountains to Sea, then Terminal and Talk to it. Built 2026-10-22.
