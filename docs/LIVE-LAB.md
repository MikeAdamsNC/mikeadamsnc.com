# The live lab: proposal (not built; waiting on Mike)

The home page's lab panel would show a few real signals from home, so the site has a
pulse. This is the design to approve first. Nothing here is built, and no Archer locked
item changes until Mike says yes (his rule, 2026-10-22).

## What would show

| Signal | What visitors see | What never leaves home |
|---|---|---|
| **Grill** | "Cooking now: pork butt, phase 3 of 4" with the meat probe's temperature, or "Grill's off." | Finish time, start time, the grill's name or location. Shown **2 hours late** (see below). |
| **Radar** | Tonight's Raleigh-area radar call: "Rain," "Bugs and birds," or "Clear," and how many radar readings it sees. | The backyard rain gauge, the house's rain line, anything tied to the house. |
| **Trail cams** | The last day's tally ("Yesterday: 14 deer, 2 coyotes, 1 fox") and the AI's funniest miss of the week. | Photos (for now), camera names, times, the property, temperatures. A day late. |

Anything else in Archer (health, money, family, calendar, school, location, the pool,
the weather station, Plex) is not part of this and can't be added without a new decision.

**Why delays:** a live "grill is on" tells a stranger someone is home right now. Showing it
two hours late keeps the fun without that. Trail cam tallies are a day old by nature.

## How it would work

- **Archer pushes; nothing reaches in.** A new Archer job, `site_lab`, every 5 minutes
  builds the summary above in plain code (no AI), from a fixed list of fields, and sends it
  to the site's private address with the same kind of token `site_pitches` already uses.
  The site keeps only the latest summary.
- **The site never asks Archer for anything,** and no new door into the Mac Mini opens.
- **Off switch:** one setting in Archer stops it; the panel then says "Quiet in the lab."
  If Archer is down, the panel says the same after 30 minutes.
- **X-ray** labels it: "Pushed from Archer 3 minutes ago · grill delayed 2 hours."
- **Fails quietly but not silently:** if the push keeps failing, Archer tells Mike, like
  every job (locked item 16).

## The locked items it touches

- **Item 18** (only the AI connection is public): **unchanged.** No new public door; Archer
  only calls out, as `site_pitches` already does.
- **Item 17** (two ways in): **unchanged.** This is a way out, not in.
- **Item 26** (nothing personal on the fridge unless you choose): the same idea applies to
  the public web, and this is Mike choosing, field by field. No change needed to its text.
- **Item 31** (three controlled surfaces): **needs a dated amendment.** A public website
  showing Archer data is new. Proposed wording, added to item 31:

  > Archer may also publish a small, fixed summary to MikeAdamsNC.com: the grill's status
  > (two hours late), the regional radar call, and the trail cams' daily species tally.
  > Plain code builds it from a fixed list of fields; Archer sends it out and the site can't
  > reach in; one setting turns it off. Anything more needs its own decision.

## What Mike decides

1. The three signals: keep, drop or add any?
2. The grill's 2-hour delay: keep it, make it longer, or show it live?
3. Trail cam photos: keep them off, or allow one hand-picked photo a week (location data
   stripped)?
4. Approve the item 31 amendment as worded?

Once those are settled: the amendment goes into Archer's `LOCKED.md` and `DECISIONS.md` as
its own dated change, then `site_lab` is built, tested, and watched running once.
