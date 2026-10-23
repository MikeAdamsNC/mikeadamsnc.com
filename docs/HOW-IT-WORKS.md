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

**The chat** (`/pitch`) is the main way in. An AI (Gemini 3.8 Flash, `web/bot.py`, through
`web/gemini.py`) asks the pitch questions one at a time and, when it has enough, shows a
summary the visitor sends or keeps editing. It says it's an AI, never promises anything,
quotes prices or agrees to terms, knows nothing private, and stays on ideas and site
suggestions ("site idea"). Its instructions are plain words in `content/bot.md`: edit
that file to change how it talks. The browser holds the conversation; nothing is saved
until the visitor sends the summary, and then the pitch is saved with the conversation
so Mike can read it on the dashboard. Limits: 30 messages per visitor per day, 600 bot
replies per day site-wide, 20 turns per conversation. If the AI is out or a limit is
hit, the chat points to the form. The AI's thinking is set to "low" (faster and steadier
on this model) and a reply that runs on is retried. A $5/month budget alert on Vertex AI
and the Gemini API emails Mike at 50, 90 and 100 percent.

**How the chat looks and waits.** The chat is a dark panel with the idea drawn beside it
(on a phone, a small card bar above the chat that opens to the full card). Before anyone
types it offers four starter prompts. The bot's reply streams in as the AI writes it
(`web/gemini.py` `stream_json`, sent to the page as server-sent events), so on a normal day
the first words show in a couple of seconds. While it waits, the page says what's going on:
"Reading your idea…", then "Thinking of a good question…", then after 15 seconds "The AI is
slow right now. Still working…" with a live count; after 30 seconds it offers "Keep waiting"
or "Finish with the form", and the form fills itself in with what was already said (kept in
that browser tab only). The three questions with fixed answers (app or website, who it's
for, who pays) are buttons. The AI asks the first one after the visitor types; after a tap,
the page asks the next one itself, with no AI wait. Small tags ("booking", "payments") appear
under each message right away, picked out by the page's own code. A microphone button uses
the browser's own speech-to-text where there is one. A wave across the top fills as the
pitch takes shape (what it is, type, for, who pays, features).

**The pitch card.** As the visitor talks (after their first answer, then every couple of
answers, and once more when the summary is ready), the AI draws the idea as an App Store
style listing beside the chat; changed parts glow briefly: a made-up product name, a one-line
tagline, three features, an icon, and the app's main screen on a phone with believable
sample content (`web/card.py`; its instructions are plain words in `content/card.md`). The
AI only writes words and picks from fixed lists (96 Lucide line icons in
`web/static/icons/`, five screen layouts: map, chart, calendar, photo, list); our own code
draws the card, so it always looks on-brand. The visitor can tap any words to change them,
ask for another, and choose to put their first name on it (off by default). Nothing is
saved until they send. On send, the card gets the same AI check comments get (spam, hate,
private details); if it passes it's saved in Firestore `cards` under a random, unguessable
id and the visitor lands on its own page, `/idea/<id>`, with Share, Save the image and a
"Pitch your own idea" button. Only people with the link can see it, and search engines are
told to skip it. `/idea/<id>.png` is the 1200 x 630 picture that link previews show (X,
LinkedIn, iMessage), drawn on the server with Pillow to match the page. If the card fails
the check, the pitch still reaches Mike with the card attached, but there's no page. Limits:
20 card drawings per visitor per day, 600 site-wide (it redraws as they talk). Icon masks for the picture are made by
`brand/build_card_icons.py` (run it after adding an icon).

**The form** (`/pitch/form`) saves each pitch to Firestore (database `mikeadamsnc`, collection `pitches`).
Spam protection: a hidden trap field, a check that a person took at least 3 seconds,
and at most 5 pitches per visitor per day. Mike sees and sorts pitches (new, maybe,
building, done, no) on the dashboard.

**Getting to Mike's phone:** Archer's `site_pitches` job asks the site's private address
`/api/pitches/unsent` every 5 minutes with a long secret token (Secret Manager
`mikeadamsnc-archer-token`; the same value is `MIKEADAMSNC_TOKEN` in Archer's
`secrets/archer.env`), pushes each new pitch, and marks it sent. Archer reaches out to
the site; the site can't reach Archer.

## Votes and comments

**Thumbs:** anyone can vote an experiment up or down without signing in: one vote per
visitor per day (the same anonymous daily code as analytics), stored in Firestore
`votes`; tapping the same thumb again takes the vote back. The browser remembers the
vote so the button stays lit.

**Ranking:** the Lab sorts Hot by default (`web/ranking.py`): the net score on a log
scale plus a head start for newer experiments (each experiment's `added` date in
`content/experiments.yaml`), Reddit's idea with one change so a single vote counts. New
and Top are the other tabs. The home page's experiment log is in Hot order too.

**Comments:** need Sign in with Google (the name on the account is shown; the email
never is). Each comment goes to an AI check first (`web/moderate.py`, Gemini 3.8 Flash
on Vertex AI's global endpoint). "ok" posts at once; spam, abuse or someone's private
details are held for Mike on the dashboard, where he approves or removes; if the AI
can't be reached the comment is held, never posted unchecked. Ten comments per person
per day. Archer's `site_pitches` job pushes every new comment to Mike's phone, and says
when one was held.

## The live lab

The home page's lab panel shows real signals from home (Archer locked item 31, amended
2026-10-22). Archer's `site_lab` job builds a small summary in plain code every 5
minutes and posts it to `/api/lab` with Archer's token; the site can't reach Archer.

- **Grill, two hours late** (the delay isn't labeled on the panel; the X-ray says it): on or off, the cut from a fixed list (never the typed cook
  name), the grill and meat temperatures.
- **Raleigh radar, now:** rain, bugs, birds or clear, with how many readings it sees.
- **Trail cams, yesterday:** the species tally; people, pets and vehicles never appear.
- **One photo a day:** the fridge's pick, with the camera's info stamp cropped off and
  every file detail removed before it leaves Archer. Served at `/lab-photo.jpg`.

The site keeps only the latest summary and photo (Firestore `lab`) and checks every
field it's sent; anything else is dropped. If the summary is over 30 minutes old, or
Archer's setting `site/live_lab` is `off`, the panel goes back to "quiet in the lab".

## What I'm reading

A shelf of AI and tech stories on the home page (six newest) and `/reading` (last 14
days). The list of publishers' RSS feeds and the instructions for choosing are in
`content/reading.yaml`. About hourly (riding on the keep-warm ping), the site reads the
feeds, offers Gemini 3.8 Flash the stories from the last day and a half it hasn't seen,
and saves up to four picks, each with one plain line of our own on why it's worth a
builder's time. Only the headline, the source and a link out are shown; feed summaries
are read to choose and never stored or shown; no article text or images are copied.
Stories it passed over are remembered so they aren't offered again. Firestore
collections `reading` and `reading_skipped`, pruned after 14 days.

## Analytics (ours, no cookies)

Every page view is recorded by the server, along with votes, comments and sign-ins; the
page's script adds scroll depth (25, 50, 75, 100%), X-ray opens, buttons pressed, links
clicked out, and the first keystroke in the idea form. Rows go to BigQuery table `site_analytics.events`. Bots, the keep-warm
ping and Mike's private pages aren't counted.

A visitor is a 16-character code made from the day's random salt (Firestore `salts`,
one per Eastern day, deleted after two days), the IP address and the browser. The same
person is one visitor today and a stranger tomorrow; IP addresses are never stored.

The dashboard reads the same table: views, visitors, pages, where people came from,
devices, scroll depth, the pitch funnel, experiments read, links clicked out.

## Site versions

The home page comes in versions, listed in `content/versions.yaml` and on `/versions`.
A visitor picks one (`/?v=terminal`, `/?v=talk`, `/?v=mountains`, `/?v=classic`); the
browser remembers it and the home page opens in that version next time. Every page view
records which version it was, so the dashboard can tell which ones people like. All
versions read the same content files.

- **Classic:** the lab layout (the default).
- **Terminal** (`web/static/terminal.js`): the site as a command line, reading
  `/api/site.json` (everything public on the site, in one file). `help` lists the
  commands; visitors can read experiments and vote from it. Each command typed is counted.
- **Talk to it** (`web/talk.py`, instructions in `content/talk.md`): an AI (Gemini 3.8
  Flash) answers questions using only the site's own content and links to real pages
  (links to anywhere else are dropped). 40 questions per visitor per day, sharing the
  pitch chat's site-wide daily cap.
- **Mountains to Sea** (`web/static/mountains.js`): scrolling flies a camera from Mount
  Mitchell to Cape Hatteras over real North Carolina elevation (Terrain Tiles, zoom 8,
  saved in `web/static/m2s/`), and the sea moves at the height and rhythm of NOAA buoy
  41025 off Cape Hatteras (`/api/buoy`, refreshed every 30 minutes). three.js is hosted
  on the site (`web/static/vendor/`). Phones get a lighter model; visitors who turn off
  motion get one still, overhead view instead of the flight.

## The X-ray view

The λ button in the corner (or the X key) turns the page into a blueprint. The home
page also has an "X-ray this page" button next to the other two up top, with a one-line
hint under it, so visitors find it (button presses count as `hero_xray` in analytics). Anything with a `data-x`
attribute in a template is outlined and labeled; the "How this page works" panel shows
the server, how long this page took to build, pages served today (from analytics,
cached five minutes), the version and the last deploy.

## Mike's sign-in

Sign-in is Sign in with Google, for commenters and for Mike; `/admin` lets in only
`ADMIN_EMAILS` (set in
`deploy/deploy.sh`). It needs a Google sign-in client, made once in the Cloud console
(no command line can make one): Google Auth Platform, client type "Web application",
redirect addresses `https://mikeadamsnc.com/auth/callback`,
`https://www.mikeadamsnc.com/auth/callback` and the preview's `/auth/callback`. Its id
and secret go in Secret Manager as `mikeadamsnc-google-client-id` and
`mikeadamsnc-google-client-secret`; the deploy script picks them up when they exist.
The sign-in cookie is the only cookie the site sets, and only for people who sign in.
While the Google sign-in app is in "testing" mode only its listed test users can sign
in; it must be switched to "In production" (Google Auth Platform, Audience) before
the public can comment.

## Scheduled jobs

| Job | When | What it does |
|---|---|---|
| `mikeadamsnc-keep-warm` | Every 10 minutes | Visits the site so it stays ready for visitors. |
| Archer `site_lab` | Every 5 minutes | Sends the live lab summary (and the day's photo once). |
| Archer `site_pitches` | Every 5 minutes | Pushes each new pitch and comment to Mike's phone, then marks it sent. |

## Changing the site

Every stylesheet and script link carries a fingerprint of the file's contents
(`/static/site.css?v=…`, the `asset()` helper in `web/app.py`), so after a deploy browsers fetch
the new files instead of mixing a saved old stylesheet with new code.

1. Edit on a branch; run the tests: `.venv/bin/python -m pytest -q web/tests`.
2. Merge. Then `PREVIEW=1 ./deploy/deploy.sh` puts it on a private preview address
   without touching the live site, and `./deploy/deploy.sh` makes it live (about two
   minutes either way).

## Cost

Expected under $1/month: Cloud Run, Firestore and BigQuery all stay inside Google's
free monthly allowances at this traffic; the scheduler job is one of three free ones.
The AI (pitch chat, pitch cards and comment checks) costs about 3 to 4 cents a pitch conversation and
fractions of a cent a comment, watched by the $5 budget alert.
