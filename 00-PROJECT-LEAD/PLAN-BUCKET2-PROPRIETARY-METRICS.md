# PLAN-BUCKET2-PROPRIETARY-METRICS — creating data the market doesn't have

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: 2026-09-18 by PROJECT-LEAD, from Matt's 2026-09-18 data-sources chat.

**PARKED.** Matt's ruling, 2026-09-18: "I think we get bucket 1 functional before we do
anything about bucket 2." Nothing in this document is scheduled. It is a findings record
so the thinking isn't lost and doesn't have to be redone.

**Gate to unpark:** `PLAN-BUCKET1-DATA-COVERAGE.md` stage B1-5 complete. B1-1 (loading the
staged sources) is a hard prerequisite for everything in section 1 below — those files are
the inputs.

**This is a plan doc, not a prompt.** Nothing here is shaped into acceptance criteria yet.
Each item becomes a `PROMPT-*.md` only after it is unparked and reshaped.

## Matt's framing (his words)

> "I also want to experiment with proprietary data and created our own datapoints,
> specifically related to offensive line play."

> "The computer vision data is an edge in itself as its data the market doesn't have."

> "The key to any model like this is to have as much data as possible and to have data
> the market doesn't have."

> "Bucket 2 is finding novel ways of creating new metrics with computer vision and
> creating new data points by aggregating existing publically available data."

Note the standing ruling this sits alongside (STATE.md, 2026-09-10): the offensive-line
hypothesis is a finished experiment, not the project's premise. Bucket 2 is OL work as one
line of experimentation on the platform, not a return to the original framing.

---

## 1. Buildable from files already on disk (after B1-1)

These need no new data source, no account and no video. They are the cheapest items in
bucket 2 and the only ones that could plausibly be pulled forward if a gap appears.

### 1a. Validate `ol_pressure_proxy_rate` against charted pressure — do this first

Three of the current features are OL pass protection: `ol_sack_rate`, `ol_qb_hit_rate`,
`ol_pressure_proxy_rate`. The third is a proxy inferred from play-by-play.
`pfr_weekly_qb_pressure_2018_2025.parquet` has PFR's own charted pressure counts at
per-game grain — an independent measurement of the same thing.

Regress one on the other. If the proxy tracks charted pressure, three features are earned
and everything downstream can build on them. If it doesn't, a third of the OL signal is
measuring something else, and that is worth knowing before investing in refining it.

Cheap, decisive, uses only staged data. This should be the first bucket 2 item run,
because its result changes how much the rest is worth.

### 1b. Pairwise adjacency continuity

`ol_depth_charts_2015_2025.parquet` carries real LT/LG/C/RG/RT labels, and
`ol_snap_counts_2013_2025.parquet` gives per-player per-game snaps. Together they make a
metric nobody publishes computable today.

Every public OL continuity metric counts how many of five starters are the usual five.
But blocking failures happen in the exchanges *between* linemen — LT/LG, LG/C, C/RG,
RG/RT. Track snaps played by each adjacent pair. Two new starters side by side breaks
three pairs; two at opposite ends breaks two. Same "3 of 5 returning" headline,
materially different unit.

### 1c. OL-fault sacks

`ftn_charting_2022_2025.parquet` carries `is_qb_fault_sack`, which separates sacks the QB
caused from sacks the protection lost. `ol_sack_rate` currently charges the line for all
of them. This is a direct quality upgrade to an existing production feature, free, and
already downloaded — as a new column, per the standing rule that existing feature columns
never change meaning.

### 1d. Other aggregation hypotheses, unranked

- **Interior vs edge decomposition.** QB play degrades far more under interior pressure
  than edge pressure. If the market prices "offensive line" as one scalar, a guard going
  down should be systematically underpriced against a tackle. Specific, testable, falsifiable.
- **Opponent-adjusted trench strength.** A mixed-effects or ridge fit with OL unit and
  pass-rush unit as the two effects gives a latent, schedule-free OL strength. Unglamorous;
  usually where edge actually is.
- **Situational leverage weighting.** An OL mismatch matters in proportion to how much the
  game script exposes it. The feature is "OL gap x expected dropbacks under pressure",
  an interaction with the spread and total, not a standalone.
- **Backup-quality-aware injury deltas.** The market moves on "starting LT is out" and
  probably under-differentiates on who replaces him. Depends on B1-3's point-in-time
  depth charts.
- **A RAS-equivalent athleticism composite.** `combine_2000_2025.parquet` has the raw
  testing numbers RAS is computed from, back to 2000. Computing an own composite with own
  position-group weighting is a modelling step, not a data gap.

---

## 2. Big Data Bowl tracking data — the unexploited free asset

Free, real, 10Hz x/y/speed/orientation for all 22 players with identities attached, on a
subset of plays. Access step is a Kaggle account, accepting competition rules, and an API
token for programmatic download. That is a real step for Matt, not a scraping problem.

Everything in section 3 below is computable on this data without touching a frame of
video: pocket area over time, time-to-first-defender-within-X-yards, get-off
synchronisation across the five, stunt and twist pickup, point-of-attack displacement.
Build the metrics here first, where ground truth is easy and no CV is involved, and find
out whether any of them predict anything before spending months on video.

**The second, better use.** Once true tracking-derived pocket geometry exists for those
plays, train a model that *predicts* it from inputs available for every season — play-by-play,
snap counts, FTN charting, NGS time-to-throw — and apply that model to 2015-2025. That
manufactures a tracking-grade metric for twenty years of games, using CV-grade truth as the
training label and free data as the input, without owning a single video file. That is
proprietary data the market doesn't have, at a fraction of the cost of section 3.

---

## 3. Computer vision on All-22 — season-length project

**Keep this out of bucket 1 permanently.** All-22 posts roughly a day after games, so
CV-derived metrics are slow-moving team-quality features and can never be late-breaking.
Bucket 1's architecture and this one have nothing in common. Matt's instinct to call them
two separate projects is the right call and should hold.

**Access, unresolved.** Coaches Film is an NFL+ Premium feature and NFL+ is US-only;
outside the US, NFL directs users to DAZN. Whether the NZ DAZN Game Pass carries Coaches
Film needs checking on Matt's own account before any of this is planned. NFL+ and DAZN
terms prohibit downloading and reproducing content; private frame-level analysis of a
paid stream is a grey area, and it stops being grey the moment derived footage or a
commercial product is involved.

**Why All-22 is tractable footage.** Fixed wide camera, all 22 players visible, and yard
lines and hashes give a reliable calibration target — so pixel-to-field homography is
solved-ish here in a way it is not for broadcast angles. Detection and multi-object
tracking are off-the-shelf. Snap detection from simultaneous motion onset is straightforward.

**The identity problem is avoidable for OL work.** Jersey number OCR at that resolution is
the hard part, but the five linemen can be labelled positionally by x-coordinate at the
snap and mapped to names afterwards using snap counts and depth charts as a soft
constraint. That removes the hardest sub-problem from the critical path.

**Candidate metrics, in rough order of how little anyone else has them:**

- Pocket geometry as a time series — convex hull area of the five relative to the QB every
  100ms, plus pocket depth and asymmetry. Public pressure stats are a binary event at a
  charter's threshold; this is the continuous thing underneath.
- Time-to-first-defender-within-X-yards — a survival curve per play instead of a flag, with
  the threshold owned rather than inherited.
- Get-off synchronisation — snap-to-first-movement per lineman and the variance across the
  five. Coachable, should predict false starts and blown protections, invisible everywhere.
- Stunt and twist pickup rate — DL crossing paths post-snap, and whether a rusher came free.
  The most proprietary item on this list and it maps onto something coaches actually say.
- Point-of-attack displacement — net movement of the line of scrimmage in the first second,
  by gap, in feet. Separates "did we win the line" from "did the back make someone miss".
- Double-team release timing — when the second lineman comes off to the second level.

**Scale, for planning only.** Roughly 285 games x ~130 plays x 2 angles x ~6s x 30fps is
on the order of 13M frames per angle-season. Doable on a GPU over weeks if restricted to
pass plays first. Not a weekend.

---

## 4. Blocked, and staying blocked

**ESPN Pass Block Win Rate / Run Block Win Rate.** `robots.txt` at espn.com disallows the
`anthropic-ai` user agent site-wide. That disallow is aimed at an agent, not at Matt, and
what he does in his own browser is his call — but no work in this repo should be built to
evade it. The better answer anyway: PBWR is derived from the same tracking data the Big
Data Bowl hands over for free, and ESPN changed the formula for 2026, so the historical
series isn't clean. Rebuilding it from tracking data means owning the definition.

**PFF, Sports Info Solutions.** Both paid and licensed. Status unchanged in
`docs/DATA_SOURCES.md`. Out of scope until someone decides to pay.

---

## 5. The constraint that governs all of it

272 regular-season games a season. Any game-level feature gets 272 observations a year to
prove itself, against a market where the effects are small. That arithmetic is why most
public OL work never demonstrates anything.

Two mitigations, and both are needed. Validate metrics at play level, where a season gives
40,000+ observations and it is possible to establish that a metric measures something real,
then aggregate to game level only for the betting decision. And frame the target as
*market error* rather than game outcome — a lower-variance target with far more signal per
observation than predicting who wins.
