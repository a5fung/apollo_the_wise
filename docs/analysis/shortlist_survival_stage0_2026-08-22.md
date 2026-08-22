# Stage 0 — Of the 16 real EPs attributed to the top-20-by-gap cap, how many does re-ranking the shortlist actually recover? (2026-08-22)

**MEASUREMENT ONLY. No cap, floor, weight or criterion is changed or proposed as decided —
selection is entry discipline and is the operator's sole authority (THE LINE). $0 — prod
read-only via psql (one capture), no LLM calls, no paid data.**

## The ask

Stage 0 of the shortlist plan (`crystalline-waddling-charm`): the retention study
(`real_ep_retention_562b_2026-08-22.md`) attributed **16 of 26 labelled real EPs** to the
top-20-by-gap admission cap. Before building a replacement ranking: of those 16, how many are
**actually recoverable by re-ranking the shortlist** — versus dying at the next gate anyway?
Replay each against the gates it never reached (RVOL/pace → cooldown → extension 75% → ADV$
≥ $1M → ATR% ≤ 15 → mcap ≥ $500M → score → catalyst), then ask whether the proposed
three-term shortlist (liquidity 15×3, flat gap 10×1, theme 10×1) would have ranked it into
the top 20 **that morning**. A name that clears every gate but ranks 25th is not recoverable
either.

## The headline

**At most 1 of 16 — SNOW 05-07 — and even that one is conditional on a catalyst grade that
was never assigned and cannot be reconstructed for $0. Demonstrably recoverable end-to-end:
ZERO.**

The decomposition (16 = 5 + 5 + 5 + 1):

| bucket | n | members |
|---|---|---|
| **never cap deaths at all** (562b's table was wrong on these) | 5 | ASX, IREN, NBIS (gap-floor kills — day high never crossed 9%; NBIS also in 60-day cooldown from its 03-16 HIGH alert) · ARM, UMC 05-06 (beat the cap at logged ranks 18/14, graded, killed by the **score**) |
| cap deaths that **rank OUT even under the proposed three-term shortlist** | 5 | USAR, AMKR, ALGM (best-case composite ranks 25/25/46 on the 99-name open board) · HUT, STRL (below the 9% floor at the open; by the time they crossed, the board had flooded and their best-case rank is 69+) |
| cap deaths the new shortlist **admits — which then have NO path to a HIGH alert** on their day (Correcting regime, HIGH bar 75; max reachable score ≤ 65 even with the top catalyst grade) | 5 | SNDK (rank 1–2), MU (3–13), BE (3–13) solidly in; APLD, QBTS on the rank-20 tie boundary |
| cap deaths the new shortlist admits **with a conditional path to entry** | **1** | **SNOW 05-07** — rank 3 by the new composite (logged gap-rank 22); every mechanical gate passes; reaches HIGH (72 ≥ 65, Bull) **only if** its never-graded catalyst would have graded game_changer at a ≥10%-gap tick; strong grade scores 48 < 50 and dies |

**The plan's Context must be corrected, not kept.** "The cap took 16 of 26" survives as "the
cap took at most 11 of 26, and re-ranking the shortlist recovers at most one of them to a
possible entry — the wall behind the cap is the score bar, exactly where ARM and UMC actually
died." The shortlist re-rank is still worth building — the liquidity axis puts the right names
in the room (MU/SNDK/BE/ARM/SNOW, the five biggest R-winners in the killed set, all rank
top-20 by the new composite where gap ranked them 20–100+) — but **it is not the retention
lever for these 16**.

## Data and provenance

- **Reused captures** (scratchpad, pulled once in #533/#562c, not re-run): `533_q2.psv`
  (open-gap boards 04-08/05-06/05-07 with 20-day ADV, prev close), `533_q3.psv` (day-high
  crossed boards, same fields), `533b_bars.psv` (full daily H/L/C history for every corpus
  ticker — ATR-14 and extension computed locally from it), `533_q1.psv` (scan-log boards for
  05-06/05-07 — the logged ranks), `562c_*.psv` (member funnel sweep).
- **New capture** (one pull): `stage0_prod.{sql,psv}` — `mi_themes` for the three event days
  (name/stage/tickers), `mi_market_caps` for the 16, `mi_ep_missed_outcomes` presence rows
  pre-05-08, `mi_ep_alerts` pre-05-08 (0 rows — purge confirmed), `mi_market_regime` for the
  three days, and the exact ADV$-gate value (30-day median close×volume) per member.
- **Analysis**: `stage0_analyze.py` / `stage0_analysis_out.txt` (same scratchpad).
- **Score basis**: the **committed** rubric at HEAD (`79e8e1c4`, operator-signed 2026-08-22)
  — liquidity ADV$-tiers (15/12/10/7/0 at $500M/$250M/$100M/$50M) replacing the RVOL ladder,
  neglect and prior-momentum **deleted**, gap tiers 25/20/15/10/0, catalyst 25/15/0,
  conviction floors unchanged, Bull ×1.2. RVOL gate basis: today's RVOL@T at **1.0×**
  minute-anchored (`minute_volume.py`), not the historical 2.0× that killed UMC 04-17.
- **Regimes** (from `mi_market_regime`): 04-08 = **Correcting** → HIGH threshold **75**,
  multiplier ×1.0. 05-06/05-07 = **Bull** → threshold 65, ×1.2. MODERATE bar 50 everywhere.
- **#583 / trap 2**: `mi_ep_missed_outcomes` is used ONLY as frozen presence evidence
  (did an alert/scan row exist — the cooldown check). **Every outcome column was dropped for
  every row, stale and fresh alike** — nothing here banks a return of any kind (traps 1/3).
- **Trap 4 — rank provenance, per name**: ARM 18, UMC 14, SNOW 22 are **logged** per-tick
  ranks (`mi_ep_scan_log`). All 04-08 ranks are **reconstructed** from official daily prints:
  the open-tick board (99 names with open gap ≥ 9%) is exact for the 9:31 tick; intra-window
  board membership at later ticks is unknowable, bounded above by the 370-name crossed board.
  Unlike gap-rank reconstruction (demonstrated 4× depth overstatement), **the liquidity rank
  is tick-stable** — ADV$ is fixed the night before — so the reconstruction risk here is
  board SIZE, not member order. Direction: a bigger board can only push a member's composite
  rank DOWN, so "ranks OUT on the open board" is conservative-proof, and "ranks IN" claims
  are made on the open board (the entry-relevant tick).

## Result 1 — the gates the cap "hid" kill almost nothing

Replayed for all 16 (live 9:31 basis — bars strictly before the event day):

| gate | result |
|---|---|
| extension ≥ 75% of 5-day min close | **0 of 16 die** — max is NBIS at 27.2% (04-08 was a crash-rebound morning; prev closes sat near the lows) |
| ADV$ ≥ $1M (30-day median close×vol) | **0 of 16 die** — min is ALGM at $52M, 52× the floor |
| ATR-14% ≤ 15 | **0 of 16 die** — max is BE at 10.2% (backtest basis incl. gap day: same verdict) |
| mcap ≥ $500M | **0 die.** 11 of 16 cached at $12B–$1.07T. ASX/ALGM/QBTS/USAR/IREN uncached: bounded pass (each printed $100M–$1.3B day-$vol; a sub-$500M name would need 20–50% single-day turnover) — and all five are floor-killed or rank-out anyway, so the gate is never decisive |
| cooldown (60d) | **1 dies: NBIS** (HIGH alert 03-16, frozen `high_unentered` row — 23 days before 04-08; gap 8.07% < 15% so no earnings bypass). Others: no prior-alert evidence; `mi_ep_alerts` pre-05-11 is purged, so this is evidence-of-absence from frozen rows, not proof |
| RVOL@T ≥ 1.0× (minute-anchored) | **unknowable for 04-08** — no minute data survives. Direction: SNDK (0.91×) and MU (0.96×) finished the day BELOW their own 20-day average volume, so the pace gate could genuinely have killed both — the same "real EPs run quiet" mechanism that killed UMC 04-17. SNOW's logged tick projected 2.9× → passes |

**The cap was not hiding a wall of mechanical kills — those gates pass nearly clean. What it
was hiding is the score.**

## Result 2 — the ranking: who the three-term shortlist admits, that morning

Composite = 3×liq_pts (ADV$-tiers) + 10 flat gap + theme (10 if in an
Accelerating/Mainstream `mi_themes` set on that `theme_date`, else 0), ranked on the
**open-tick board** (names with open gap ≥ today's 9% floor, prev close ≥ $5) — the board
that exists inside the 9:31–9:45 ORB window. Crossed-board (370-name) ranks shown as the
flooded-board bound.

⚠ Trap 5, confirmed and quantified: on 2026-04-08 only 4 themes were Accelerating/Mainstream,
covering **22 tickers** — the theme term is nearly signal-free on exactly the morning where
13 of the 16 died. The one exception cuts the other way: **SNDK was in "AI Memory & Storage"
(Accelerating) that day**, and its +10 is what lifts it to rank 1–2. ARM (Mainstream, Custom
AI Silicon) gets +10 on 05-06. No other member scores the term on their day.

| name (day) | ADV$ | composite | open-board rank (99 names 04-08) | crossed-board rank bound | in top-20? |
|---|---|---|---|---|---|
| SNDK 04-08 | $13.1B | 65 | **1–2** | 1–7 | **YES** |
| MU 04-08 | $19.2B | 55 | **3–13** | 8–35 | **YES** |
| BE 04-08 | $1.3B | 55 | **3–13** | 8–35 | **YES** |
| APLD 04-08 | $431M | 46 | 15–23 (9 names tied for the last 6 slots; continuous-ADV$ rank 14) | 39–67 | tie coin-flip |
| QBTS 04-08 | $278M | 46 | 15–23 (continuous-ADV$ rank **21** — one outside) | 39–67 | tie coin-flip |
| USAR 04-08 | $187M | 40 | best-case 25 | 69–140 | NO |
| AMKR 04-08 | $153M | 40 | best-case 25 | 69–140 | NO |
| ALGM 04-08 | $56M | 31 | best-case 46 | 141–190 | NO |
| HUT 04-08 | $213M | 40 | **not on the open board** (open gap 8.40%) | 69–140 when it crossed | NO |
| STRL 04-08 | $177M | 40 | not on the open board (8.20%) | 69–140 | NO |
| ASX / IREN / NBIS 04-08 | — | — | never candidates — day high < 9% | — | floor kill, not cap |
| ARM 05-06 | $1.8B | 65 | 1–3 | 1–5 | YES (but it beat the old cap too) |
| UMC 05-06 | $175M | 40 | 8–12 | 36–75 | YES at the open tick (it cracked the old cap too, logged 14) |
| SNOW 05-07 | $1.2B | 55 | **3** | 3–7 | **YES** (vs logged gap-rank 22) |

Board-composition note: 13 names on the 04-08 open board carry ADV$ ≥ $500M (liq=15) — the
index-heavyweight flood 533 predicted for a liquidity axis. The composite's top-20 cut at the
open tick lands at value 46 with a 9-way tie; any bucketing coarser than continuous ADV$
makes the boundary a tie-break lottery, which is itself a finding for the rubric build.

## Result 3 — the score wall: the admitted names have no path to an alert on their day

04-08 was **Correcting**: HIGH needs 75, multiplier ×1.0, and post-open scans zero the
vol-conviction term; every member's float > 50M zeroes the float term. Under the committed
rubric the maximum reachable score at the open tick, **granting the best possible catalyst
grade (game_changer, 25 pts + conviction floors)**:

| name | gap pts | liq | theme | + game_changer | conviction floor | max score | HIGH (≥75)? | MODERATE (≥50)? |
|---|---|---|---|---|---|---|---|---|
| SNDK | 15 | 15 | 10 | 25 | gap 10.3% → floor 60 | **65** | **NO** | yes (needs ≥ strong) |
| MU | 10 (open gap 9.94%) | 15 | 0 | 25 | no floor (gap < 10) | **50** | **NO** | only with game_changer |
| BE | 10 (9.93%) | 15 | 0 | 25 | no floor | **50** | **NO** | only with game_changer |
| APLD | 15 (12.97%) | 12 | 0 | 25 | floor 60 | **60** | **NO** | only with game_changer |
| QBTS | 15 (10.99%) | 12 | 0 | 25 | floor 60 | **60** | **NO** | only with game_changer |

**Zero of the five admitted 04-08 names can reach a HIGH alert at the open tick under ANY
catalyst grade** — and a HIGH alert inside 9:31–9:45 is the only thing that produces an
entry. MODERATE reaches the morning briefing only. With a routine grade (the modal grade for
a market-wide tariff-rebound morning, and the grade ARM actually received on its own flood
day) every one of them scores 25–40 and dies below 50 — the same death as QCOM/AMD/UMC/ARM,
the four graded real EPs the score already killed. The one theoretical exception: BE's day
high hit +15.4%, and gap ≥ 15 + game_changer floors at 80 ≥ 75 — but that stacks three
unknowables (a ≥15% tick before 9:45 · still top-20 on the by-then-flooded board · a
game_changer grade on rebound news) and is noted, not counted.

**SNOW 05-07 (Bull, threshold 65, ×1.2) is the single conditional recovery**: rank 3 by the
new composite (a grading shot the old cap denied at rank 22) · every mechanical gate passes
(ext 2.4%, ATR 5.2%, ADV$ $1.03B, mcap $97B, projected RVOL 2.9× ≥ 1.0×) · then — routine:
30, dies; **strong: 48, dies below 50 by two points**; game_changer at a ≥10%-gap tick
(day high 12.35%, open 9.80%): floor 60 ×1.2 = **72 → HIGH → entry plausible**. Its catalyst
was never graded; reconstructing the grade costs LLM spend ($0 rule) and is the operator's
call. That conditional is the entire recoverable population.

ARM and UMC 05-06, for completeness (score kills, not cap kills): under the committed rubric
ARM's historical routine grade scores 48 < 50 — it dies at the score **again** (the deleted
momentum penalty moves it from −12 to 48, still short; a strong grade would score 66 → HIGH,
so ARM's fate now hangs entirely on the catalyst tier). UMC (strong) scores 42 < 50 — dies
again.

## Per-name verdict table

| # | name (event) | died at (562b said) | actually died at (this replay) | new-rubric rank that morning | next wall if admitted | recoverable by re-ranking? |
|---|---|---|---|---|---|---|
| 1 | MU 04-08 | cap | cap (reconstructed) | 3–13 IN | RVOL@T 0.96× risk → score ≤ 50, HIGH impossible | grading shot only — **NO entry** |
| 2 | SNDK 04-08 | cap | cap (reconstructed) | 1–2 IN | RVOL@T 0.91× risk → score ≤ 65, HIGH impossible | grading shot only — **NO entry** |
| 3 | BE 04-08 | cap | cap (reconstructed) | 3–13 IN | score ≤ 50 (80-floor path = 3 stacked unknowables) | grading shot only — **NO entry** |
| 4 | APLD 04-08 | cap | cap (reconstructed) | 15–23 tie | score ≤ 60, HIGH impossible | tie coin-flip, no entry — **NO** |
| 5 | QBTS 04-08 | cap | cap (reconstructed) | 15–23 tie (ADV$ rank 21) | score ≤ 60 | **NO** |
| 6 | USAR 04-08 | cap | cap (reconstructed) | best 25 OUT | — | **NO** |
| 7 | AMKR 04-08 | cap | cap (reconstructed) | best 25 OUT | — | **NO** |
| 8 | ALGM 04-08 | cap | cap (reconstructed) | best 46 OUT | — | **NO** |
| 9 | HUT 04-08 | cap | cap+floor timing (open gap 8.4%) | OUT (69+ once crossed) | ORB window (its 05-06 HIGH fired 09:52 — window missed) | **NO** |
| 10 | STRL 04-08 | cap | cap+floor timing (8.2%) | OUT (69+) | also its class hits stop_too_wide (STRL 05-05 row) | **NO** |
| 11 | ASX 04-08 | cap | **9% gap floor** — day high never crossed | never a candidate | — | **NO — not a cap death** |
| 12 | IREN 04-08 | cap | **gap floor** (would have ranked top-5 by ADV$ if admitted — a floor cost, not a cap cost) | never a candidate | — | **NO — not a cap death** |
| 13 | NBIS 04-08 | cap | **gap floor + cooldown** (03-16 HIGH, 23 days prior) | never a candidate | — | **NO — not a cap death** |
| 14 | ARM 05-06 | cap | **score** (logged rank 18, graded, −12; re-scores 48 today on its routine grade) | 1–3 IN | catalyst tier | **NO — cap not the killer** |
| 15 | UMC 05-06 | cap | **score** (logged rank 14, graded, 21.6; re-scores 42) | 8–12 IN | score | **NO — cap not the killer** |
| 16 | SNOW 05-07 | cap | cap (logged rank 22 — the one demonstrated one-rank-outside kill) | **3 IN** | catalyst grade: strong→48 dies; game_changer→72 HIGH | **CONDITIONAL YES — the only one** |

## ⚠ What this does NOT answer

- **Catalyst grades for the never-graded 14** (all 04-08 members + SNOW). Every "score ≤ X"
  above is a ceiling under the most generous grade; the realized grades would likely be
  worse (562b: 5 of 7 graded real EPs scored < 50; 533: at most 1–2 of 7 got the top grade
  while 59% of ordinary alerts did). Retro-grading costs LLM spend — operator's call.
- **RVOL@T at the 04-08 entry ticks** — no minute data survives from April. SNDK/MU direction
  stated (day-total below 1.0×); it could kill the two best-ranked recoveries even before
  the score does.
- **Tick-level board membership and floor-cross times on 04-08** — whether HUT/STRL/BE
  crossed relevant thresholds before the 9:45 ORB close is unknowable from daily bars
  (per-tick truth unreconstructable; the open board is the only exact tick).
- **The delayed-feed board of 04-08** (533 Result 5): members within ~±8 gap-ranks of a
  boundary are feed-conditional; the liquidity axis is largely immune (ADV$ is prior-day
  data) but board membership at the floor is not — ASX/IREN/NBIS sit inside the ±4pp
  feed-disagreement band of the 9% floor.
- **Whether MODERATE-tier visibility has value** — MU/SNDK/BE reaching the morning briefing
  (with a strong-or-better grade) is not nothing, but it is not the automated retention 562b
  measured, and no MODERATE has ever become a trade in this system.
- **Anything about what to change.** The score bar, regime thresholds, cap axis and shortlist
  weights are detection criteria: CHANGE_PROCESS, N≥10, operator sign-off. This prices; it
  does not propose.

## Files

- This doc: `docs/analysis/shortlist_survival_stage0_2026-08-22.md`
- New capture + analysis (scratchpad, pulled once): `stage0_prod.{sql,psv}`,
  `stage0_analyze.py`, `stage0_analysis_out.txt`
- Reused captures: `533_q2.psv`, `533_q3.psv`, `533b_bars.psv`, `533_q1.psv`, `562c_*.psv`
- Anchors: `docs/analysis/real_ep_retention_562b_2026-08-22.md` (the 16-of-26 attribution
  this corrects) · `docs/analysis/selection_layer_533_2026-08-22.md` (logged ranks, floor
  kills, $vol axis) · `tests/fixtures/must_not_miss_eps.py` (#577 label) · plan
  `crystalline-waddling-charm` Stage 0 · method template
  `docs/analysis/adv_floor_556_2026-08-20.md`
