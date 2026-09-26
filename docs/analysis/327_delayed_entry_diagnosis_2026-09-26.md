# #327 — what the issue is: the delayed-entry lane's diagnosis

**2026-09-26 (Saturday build slot, after Block 5, its addendum and the leaders / management read).**
Operator, 2026-09-26: *"We should have a good cohort already, unsure collecting more will change, we need to
understand what the issue is."* This document does not test another rule. It asks four descriptive questions
of the same ~3,400 fires — how the trades fail, what the entry moment looks like against a random session of
the same stock, which stocks these are, and how the EP itself behaved before the fire — and ranks what it
finds by how much of the loss each explains. The Method section was committed before any Q1–Q4 number was
computed (`0f8fa521`; `p7_diagnosis.py`'s docstring is the pre-registration of record); nothing in it changed.
Two descriptive reads were ADDED after the tables were seen and are labelled as such wherever they appear.

> **THE ISSUE (one sentence):** the lane has been trading the wrong stocks — 98.5% of its fires are on names our
> own EP screen rejected on the gap day — and on those it buys a reclaim that hits its stop inside the session on
> 43% of fires and within two sessions on 73%, after which the stock keeps falling; the 51 fires on real EPs show
> the same shape.
>
> In numbers: 3,347 of the 3,398 fires with ten sessions of read (97% of all 3,767) sit on campaigns the screen
> rejected — 86% for a prior close under $5 — the 08-31 first-run population the 09-01 ruling voided; the fires
> stopped within two sessions carry 135% of the lane's loss while the rest net +0.51R a fire; 72% of the
> same-session-stopped stocks sit below the stop ten sessions later; the fire session is a slightly worse entry
> than a random session of the same stock at the same place; on the 51 real-EP fires a random session of the same
> stocks reached +2×ADR first three times as often (36% vs 12%).

## The decision it serves

His standing frame (2026-09-26): *"any EP related trades are low winrate by default, what we want is always to
catch big winners while limiting losses"* — and the question of the day: *"we need to understand what the issue
is."* The decision is what to do with the delayed-entry lane after three nulls: keep collecting, change what it
watches, change how it enters, or stop. **What would change it:** if the loss is concentrated in a path or a
moment the trigger itself creates (a same-session stop, a bounce into overhead supply), the issue is the trigger;
if it is concentrated in a kind of stock the lane admits, the issue is selection; if the fires lose about as
much as a random session of the same stocks, the lane is structurally a bad-moment buyer and nothing downstream
fixes it. **What would make this analysis wrong:** a population error (the one that voided the 09-01 numbers) —
which is why the first cut is what our own screen did on the gap day — or reading a day-0 stop as "never went
green" when the order inside that session is unknown, which the Q1 classes keep apart by construction.

## Method and population

**Committed before any Q1–Q4 number was computed.** The probe is `scripts/probes/_327_block5/p7_diagnosis.py`;
its docstring is the registration of record and this section mirrors it. Inputs are the Block 5 extract
(`extract_p0.sh`, `extract_p3.sh`) plus three new read-only pulls (`extract_p7.sh`: SPY / QQQ / IWM daily bars,
the EP scan log 2026-08-20 → 09-25, and `mi_ep_alerts` since July), P2's fire and control walks, P3's per-row
events and P6's runner list. $0 throughout; no toggle, table, deploy or PLAN.md line.

**Population.** Every fire in the extract with **≥ 10 sessions elapsed by 2026-09-25** (P2's `sessions_elapsed`;
n = 3,398), never settlement status.

**Its first cut — established during orientation, before this registration, and therefore declared here rather
than discovered later.** Each fired campaign is classified by what **our own EP screen did on the gap day**:
**EP-ALERT** = the (ticker, EP date) is a live-source row of `mi_ep_alerts` at any tier (the seed query's own
`LIVE_SOURCE_SQL`); **NOT-EP** = everything else, split by the furthest stage the scan log shows for that ticker-day
(universe floor — a prior close under the $5 `MIN_PREV_CLOSE` or prior-day volume under 50,000 shares — gap floor,
RVOL / pre-market volume, quality filter, extension, cooldown, scored below the bar, post-grade filter, no scan row;
`reject_stage` where stamped, else the `filter_reason` prefix). Seen before registration and disclosed: **22 of 941
fired campaigns are alerts (100 fires; 51 with ≥ 10 sessions elapsed); 855 campaigns — 3,460 fires, 92% — were
rejected at the universe floor, 783 of them for a prior close under $5**; the six 08-24 → 08-31 alerts (CHRN, CRWD,
DG, OKTA, SOLS, VEEV) reproduce the seed query's own docstring ("1,269 campaigns, SIX were EP alerts"); and 1,457
of the 3,075 settled stops in the population fell on the fire session itself (1,383 after the width floor). No other Q1–Q4 number was computed
before the registration commit. **Every table carries the two cohorts side by side**; the EP-ALERT cohort is small
and is reported as small, never pooled away.

**The outcome measure — the lane's own arm on the sessions-elapsed population.** `R10` = the incumbent stop plus
the lane's trail arm (a close below max(SMA10, SMA20)) read at session 10: −1.00R on a stop (house convention; P3
measured gap-charging at 0.03R on this cell and it is not applied), the exit close's R on a trail exit, else the
session-10 close marked to market; `R10_none` (no exit) beside it. Sources, in order: (1) production's recorded
settlement (`outcome`, `stop_hit_date`, `r_trail_s10`, `r_none_s10`, `mfe_r`) for settled rows — production walked
them with real minute bars at settle time, and they ARE the lane's own arm; (2) the 259 rows still open at the
extract are walked by the probe from the daily table with the real `sma_trail_line` (day 0 per P2's
`day0_bars_for_fire`; a day 0 that cannot be ordered abstains and is counted); (3) `unscoreable` rows are counted,
never scored. Fire-time prices are rescaled to the daily table's scale by P2's `scale_factor`; `entry_price` is
reported unscaled for the price buckets. **Anchors, printed before any table is read:** (a) the probe's walk on
settled rows with a resolvable day 0 must reproduce `stop_hit_date` and `r_trail_s10` (the P1/P2 number is
~99.8%); (b) the R10 mean on the ids P3 walked for its incumbent trail cell is printed beside P3's verified −0.29R
(n = 1,320) — a difference over 0.02R is stated before any other number is read.

**Q1 — how trades fail (the path), per pattern, both cohorts.** Path classes at session 10: **STOP-D0** (stopped
on the fire session; the order of "went green" vs "hit the stop" is unknown at daily grade — split green-first /
straight-down only where a post-fire minute source exists, otherwise "order unknown", never folded into
never-green); **NEVER-GREEN** (stopped at session ≥ 1 with no high above the entry strictly before the stop
session; a level fire's fire-day high counts, a minute fire's day-0 daily high never does — the `reached_4r`
rule); **GREEN-THEN-STOPPED** (a high above the entry before the stop session; sub-bucketed by that peak:
0–1R, 1–2R, 2–3R, > 3R); **OPEN-AT-S10** (trail-exited or marked; positive / negative). Sessions to stop:
0 · 1 · 2 · 3–5 · 6–10 · not by s10. The peak before the stop is reported twice: strict (before the stop
session) and recorded `mfe_r` (the stop session's own high folds in — the same-session caveat). Loss
contribution = the summed R10 of each class over the total summed R10.

**Q2 — the entry moment, fire vs P2's matched same-window non-fire control.** Rows are P2's own walks
(+2×ADR$ before −1×ADR$ at s10, pessimistic). Primary like-for-like read = the fire entered at the fire
session's **close** against the control's close entry (same convention on both sides, so the level-priced head
start P2 found cannot leak in); the recorded entry beside it. Pre-entry features in ADR$, identical for fires
and controls, t = the entry session: `drift3` (close[t−1] − close[t−4]), `drift1`, `bounce` (entry − min low over
[t−3, t] — the rise off the recent low into the entry, the dead-cat measure), `intraday` (entry − open[t]),
`overhead` (max high over [EP day, t−1] − entry — distance up to the campaign's running high; negative = above
every prior high), `dist_gap_high`, `pos_ep_close`, `pos_ep_low`, `prior_reclaims` (sessions in (EP day, t)
that already reclaimed the pattern's own level; for `ep_high_break`, prior sessions whose high reached the EP
high), `session_idx`; fires also carry `reentry_shape`. Strata = terciles cut on the pattern's **control**
distribution; the 2-D stratum = bounce tercile × overhead tercile. Decomposition: gap = [fire rate − control
reweighted to the fires' stratum shares] (within-stratum) + [reweighted control − raw control] (composition);
a stratum under 20 rows on either side is pooled into its neighbour and said so.

**Q3 — which stocks.** Per bucket: n · mean R10 · stopped-by-s10 rate · kept ≥ 3R · runner rate; both cohorts.
Buckets declared: cohort (and NOT-EP by rejection stage) · price at the fire (< $1, $1–5, $5–20, > $20) · EP
tier at the gap (alert HIGH · alert MODERATE incl. tier-'none' alerts · scored below the bar · rejected before
scoring) · `ep_score` terciles among scored · catalyst grade among graded (`catalyst_quality`, else
`llm_catalyst_quality`) · gap-size terciles (watch `gap_pct`) · sessions since EP (1 · 2 · 3–5 · 6–10 · 11+) ·
run-up into the EP by the screen's own formula ((prev close − MIN close over [EP − 10 calendar days, EP)) /
MIN close; < 10%, 10–25%, 25–50%, ≥ 50%) · active theme (scan-log flag; unknown reported as unknown) · market
on the fire day (SPY close-to-close up / down; the 5-session sign beside) · dollar-volume terciles (EP-day and
fire-day). **Runner labels:** primary = P6's campaign definition (EP date ≤ 09-04; highest high within 15
sessions ≥ +50% over the EP-day close — the definition behind the "9% of fires" fact; declared now: 0 of the
120 runner campaigns are alerts, so tier / score AUCs against it are degenerate by construction); secondary =
fire-anchored (highest high in sessions 1–10 after the fire ≥ +50% over the scaled entry; fully observed).
**AUC** = Mann-Whitney with ties at ½, Hanley-McNeil 95% CI, n_pos / n_neg, for every numeric pre-entry trait
against each label, on the whole population and within NOT-EP; a trait dark on more than half the rows is
reported as dark, not as a null.

**Q4 — the link to the EP itself.** Per fired campaign from daily bars, sessions 1–3 after the EP day:
**HELD** (every close ≥ the EP close), **FADED** (a close below the EP close, none below the EP low), **FAILED**
(a close below the EP low); depth = (EP close − min low over sessions 1–3) / ADR; the day-1 close move.
**Tautology declared:** `ep_low_reclaim` fires only after an undercut of the EP low and the two close-reclaim
patterns only after a dip under the EP close, so "did the EP fail" is partly the trigger's own precondition;
the read is how hard and how early, the fire's own position at entry (below the EP low · between EP low and
close · between EP close and high · above the EP high), the share of re-entry shapes, and the same
sessions-1–3 read on runner vs non-runner campaigns.

**Ranking the causes by loss.** A mechanism's share = the summed R10 of the fires it labels over the total
summed R10, within the cohort; overlapping labels are shown jointly and never summed across causes. The
population fact is the frame of the write-up, not a mechanism — a stock being rejected by the screen does not
make its fire lose.

**Applied at run time, stated here because the registration text did not spell it out:** Block 5's standing
**0.5% stop-width floor** is applied to every scored table (it is the rule the anchor cell is read on, and
without it 105 near-zero-stop rows — max +1,599R — turn the lane's total from −1,279R to +411R, the 09-22
artifact); unfloored n and sum are in `p7_summary.json` (`width_floor`). **Added after the tables were read,
labelled where used:** (i) a fire stopped at session 1 whose day 0 has no minute source has no observable bar
before its stop — it is classed "order unknown", like a day-0 stop, not "never green"; (ii) the HELD / FADED /
FAILED label is re-read on fires at session ≥ 4 only, where it is knowable at entry; (iii) after an early stop,
where the stock stood ten sessions later.

⚖ **THE LINE.** Nothing here picks a stop, target, exit, selection rule or population; nothing is deployed.

## Anchors — both hold

| anchor | result |
|---|---|
| (a) the probe's own walk vs production's recorded settlement, settled rows with a resolvable day 0 | **1,139 of 1,141 (99.8%)** reproduce both `stop_hit_date` and `r_trail_s10` (the 2 misses are the AIXI / NRSN reverse-split rows P1 found) |
| (b) this read on the ids P3 walked for its incumbent trail cell | **−0.283R, kept ≥ 3R 2.59% (n = 1,312)** vs P3's verified **−0.290R, 2.58% (n = 1,320)** — within 0.01R |
| population scored | 3,398 fires → 3,137 from the recorded settlement + 196 still-open rows walked; 62 abstain (46 day-0, 16 holes), 3 unscoreable; **3,228 after the width floor**, total **−1,278.6R, mean −0.40R**, 88.9% stopped by session 10, 2.26% kept ≥ 3R |

The whole population reads −0.40R where P3's walkable cell read −0.29R because the 2,042 fires P3 could not walk
(a minute fire whose day low reached its tight stop) are exactly the early-stop rows — P5 already measured that
direction (98.3% stopped); this read simply includes them.

## THE CAUSES, ranked by how much of the loss each explains

Total loss on the lane's own arm at ten sessions: **−1,278.6R over 3,228 fires**. Shares are of that total; the
classes below overlap and are never summed across rows (the joint table is at the end of this section).

### 1. The stop is hit inside the fire session — 43% of fires, 108% of the loss

| path at session 10 (all fires, both cohorts) | fires | share of fires | summed R10 | share of the loss | note |
|---|---:|---:|---:|---:|---|
| **stopped on the fire session** (STOP-D0) | **1,383** | **42.8%** | **−1,383.0** | **108.2%** | order unknown on 1,191 (no minute source); where minutes exist: 122 straight down, 70 went green first |
| stopped on session 1, no day-0 source (order unknown) | 506 | 15.7% | −174.0 | 13.6% | |
| never above the entry before a later stop | 62 | 1.9% | −40.3 | 3.2% | 52 never printed above the entry at all; 10 did only inside the stop session |
| went green 0–1R, then stopped | 474 | 14.7% | −243.3 | 19.0% | |
| went green 1–2R, then stopped | 179 | 5.5% | −55.0 | 4.3% | |
| went green 2–3R, then stopped | 88 | 2.7% | −19.0 | 1.5% | |
| went green > 3R, then stopped | 176 | 5.5% | **+160.2** | −12.5% | the trail arm banks part of these before the stop |
| open at session 10, negative | 157 | 4.9% | −50.7 | 4.0% | |
| open at session 10, positive | 203 | 6.3% | **+526.4** | −41.2% | |

| sessions to the stop | fires | share | summed R10 | share of the loss |
|---|---:|---:|---:|---:|
| session 0 (the fire session) | 1,383 | 42.8% | −1,383.0 | 108.2% |
| session 1 | 713 | 22.1% | −272.7 | 21.3% |
| session 2 | 250 | 7.7% | −74.4 | 5.8% |
| **sessions 0–2 together** | **2,346** | **72.7%** | **−1,730.1** | **135.3%** |
| sessions 3–5 | 327 | 10.1% | −37.7 | 2.9% |
| sessions 6–10 | 195 | 6.0% | +13.5 | −1.1% |
| not stopped by session 10 | 360 | 11.2% | +475.7 | −37.2% |
| **the 882 fires that survive two sessions** | 882 | 27.3% | **+451.5** | — (**+0.51R a fire**) |

The lane's entire loss is made in the first two sessions after a fire; everything that survives them nets
+0.51R a fire. Per pattern the same-session share is 42.7% (`ep_low_reclaim`, n = 1,097), 48.1%
(`ep_close_reclaim`, n = 834), 42.9% (`ep_close_620_prox`, n = 1,065) and 24.6% (`ep_high_break`, n = 232 —
the one pattern whose stop is a prior-session low, not a low printed minutes earlier).

**Is that a stop inside the noise, or a stock that keeps falling? (added after Q1 was read.)** Ten sessions
after a same-session stop, **72% of those stocks closed below the stop level and 21% above the entry** (n =
1,370; median session-10 close −3.7R); after a session-1 or -2 stop, 69% below the stop, 18% above the entry
(n = 954). The stop was right about direction on roughly seven fires in ten — the lane is not being shaken out
of stocks that then go up; it is buying stocks that then go down. (Block 5 had already shown the other half:
widening the stop to 1×ADR$ still gets hit on 68% of fires by session 10 and no cell turns positive.)

### 2. The entry moment is worse than a random session of the same stock — and not because of overhead supply or a dead-cat bounce

Like-for-like (fire entered at its session's close, control at its session's close), +2×ADR$ before −1×ADR$ at
session 10, pessimistic:

| pattern | fires (rate) | control sessions (rate) | gap | within-stratum (2-D bounce × overhead) | composition |
|---|---|---|---:|---:|---:|
| all four | 3,358 (15.4%) | 7,853 (17.4%) | **−1.9 pts** | −2.0 | +0.05 |
| `ep_low_reclaim` | 1,145 (14.8%) | 4,860 (15.7%) | −0.9 | −0.4 | −0.6 |
| `ep_close_reclaim` | 859 (16.9%) | 3,917 (19.0%) | −2.1 | −2.0 | −0.1 |
| `ep_high_break` | 239 (20.1%) | 1,200 (20.3%) | −0.3 | +0.2 | −0.5 |
| `ep_close_620_prox` | 1,115 (14.0%) | 4,507 (15.0%) | −1.1 | −0.6 | −0.4 |
| recorded entry instead of the close, all four | 3,140 (14.7%) | 7,853 (17.4%) | −2.7 | −2.4 | −0.3 |

The composition term is ~0 on every pattern: **the fires are not sitting at worse kinds of moment**. The fires DO
sit differently — median bounce into the entry 0.67×ADR vs 0.45 for a random session, median distance up to the
campaign's running high 0.53×ADR vs 1.61, median position +0.06×ADR above the EP close vs −0.51 — but in the
control none of that hurts: a random session with a big three-session bounce reaches +2×ADR first **more** often
(21.4% in the top bounce tercile vs 16.0% in the bottom, n = 2,618 each), and the control's rate is flat across
overhead distance (17.3% / 17.5% / 17.3%). Inside every tercile the fire session does worse than the random
session (bounce T1 11.6% vs 16.0%, T3 18.3% vs 21.4%). So the pattern is not "buying into supply" or "buying a
dead cat" in a way a random session at the same place would not — **the reclaim session itself is the worse
moment**: a day that dipped under the level and closed back above it predicts slightly worse ten sessions than
an ordinary day of the same stock. The size is modest on this population (−2 points on a 17% base); on the
real-EP cohort it is large (§5). Re-entry shapes: first attempts 14.5%, same-pattern re-entries 14.1%,
new-high-break re-entries 20.2% at the close (13.3% on the recorded level, the P2 head start).

### 3. Half the fires are re-entries into EPs that had already failed — 52% of fires, 73% of the loss — but the label is not usable at entry

| EP's sessions 1–3 (campaigns: 467 FAILED · 264 FADED · 200 HELD) | fires | mean R10 | stopped by s10 | kept ≥ 3R | in a +50% campaign |
|---|---:|---:|---:|---:|---:|
| FAILED — a close below the EP-day low within 3 sessions | 1,692 | −0.58 | 91.9% | 0.9% | 9.9% |
| FADED — below the EP close, never the low | 1,098 | −0.48 | 89.5% | 1.7% | 5.1% |
| HELD — every close ≥ the EP close | 604 | **+0.27** | 78.9% | 7.0% | 17.1% |

Half the campaigns closed below their EP-day low within three sessions (225 on session 1, 153 on session 2, 89
on session 3; on those 467 the low of sessions 1–3 sat a median 1.04×ADR under the EP close), and fires into them
carry 73% of the loss. **But the
HELD advantage is look-ahead:** for a fire at session 1–3 the label uses closes that had not printed yet.
Restricted to fires at session ≥ 4, where the label is known at entry (added after Q4 was read), it vanishes —
**HELD −0.46R (n = 210), FADED −0.40 (n = 326), FAILED −0.34 (n = 429)**, kept ≥ 3R 2.1 / 2.3 / 1.7%. And the
tautology declared in the Method holds: the reclaim patterns fire only after an undercut, so 797 of the 1,160
`ep_low_reclaim` fires are on FAILED campaigns by construction. Where the entry sits: 180 fires below the EP-day
low (97% stopped), 1,087 between the low and the close (95%), 1,695 between the close and the high (87%), 436
above the high (80%). Runner campaigns did hold more often (49 of 102 HELD, 48%, vs 149 of 823 non-runners, 18%),
which is what a runner looks like after the fact, not a signal available before it.

### 4. Which stocks: the population is sub-$5 rejects, the "runners" are volatile penny stocks, and nothing knowable at entry separates them

| bucket (all fires, floored n in brackets) | mean R10 | stopped by s10 | kept ≥ 3R | fires in a +50% campaign |
|---|---:|---:|---:|---:|
| price < $1 (1,151) | −0.32 | 89.1% | 2.4% | **15.3%** |
| $1–5 (1,630) | −0.42 | 89.1% | 2.2% | 6.5% |
| $5–20 (290) | −0.49 | 88.6% | 2.4% | 8.3% |
| > $20 (157) | −0.52 | 85.4% | 1.9% | 2.9% |
| rejected at the universe floor, prior close < $5 (2,827) | −0.38 | 89.1% | 2.2% | 10.1% |
| rejected, prior-day volume < 50k (190) | −0.46 | 87.9% | 2.6% | 5.2% |
| rejected at a quality / RVOL / extension / post-grade gate (132) | −0.16 to −0.84 | 77–100% | 0–10% | 0–21% (n ≤ 57 each) |
| scored by the screen but below the bar (27) | −0.39 | 81.5% | 3.7% | 0% |
| **EP alert, HIGH (42)** | **−0.82** | 88.1% | **0%** | **0%** |
| EP alert, MODERATE (2) | −0.75 | 100% | 0% | 0% |
| SPY up on the fire day (1,539) / down (1,689) | −0.27 / −0.52 | 87.0% / 90.5% | 2.9% / 1.7% | 10.8% / 8.5% |
| fire-day dollar volume, bottom / top tercile (1,081 / 1,074) | −0.51 / −0.30 | 92.5% / 86.1% | 1.6% / 3.5% | 5.1% / 13.5% |
| sessions since the EP: 1 / 2 / 3–5 / 6–10 / 11+ (1,291 / 621 / 843 / 416 / 57) | −0.34 / −0.49 / −0.47 / −0.30 / −0.30 | 93 / 94 / 88 / 75 / 74% | 2.9 / 1.9 / 1.4 / 2.4 / 1.8% | 10 / 9 / 9 / 10 / 15% |
| run-up into the EP: < 10% / 10–25% / 25–50% / ≥ 50% (2,452 / 496 / 185 / 95) | −0.40 / −0.40 / −0.27 / −0.40 | 90 / 85 / 86 / 93% | 1.9 / 3.4 / 3.2 / 4.2% | 9 / 11 / 9 / 19% |
| gap-size terciles (1,084 / 1,091 / 1,053) | −0.32 / −0.46 / −0.41 | 88 / 89 / 89% | 2.0 / 2.4 / 2.4% | 7 / 9 / 12% |
| `ep_score`, catalyst grade, theme membership | **DARK on 98% of fires** — the screen computes them only for names that reach grading; among the 82 graded fires (71 floored) no bucket is positive (best −0.12R, n = 15) | | | |

**Does any pre-entry trait separate the runners? (AUC, runner campaign label; 324 runner fires of 3,381 in the
label's population; the fire-anchored label — +50% within ten sessions of the fire, 215 of 3,328 — reads the same
way.)** `adr20_pct` **0.72** [0.69–0.75] · `stop_width_pct` 0.68 [0.65–0.71] · price 0.34 [0.31–0.37] (a low price
separates) · position vs the EP close 0.62 · fire-day dollar volume 0.62 · gap size 0.60 · bounce 0.57 · everything
else 0.44–0.52 (sessions since EP 0.50, run-up 0.49, EP-day dollar volume 0.50, SPY day 0.52, prior reclaims
0.47, overhead 0.44, drift 0.44). The three that separate are the same thing — a +50% run inside fifteen sessions
needs a volatile stock, and the volatile stocks here are the sub-$1 ones (183 of the 324 runner fires are under
$1; the runner campaigns' median base price is $1.12). No trait that is not a volatility proxy does better than
0.62, and **0 of the 324 runner fires are on an EP alert**.

### 5. The cohort the lane is for — 51 fires on 15 real EP alerts — shows the same shape, only worse

The 22 alert campaigns are the six from the 08-31 first run plus sixteen enrolled since the 09-01 population fix
(AGX, ALAB, ERO, HOOD, IONQ, PHVS, QCOM, ROIV, SEI and, after the ten-session cut-off, CIFR, DFTX, GNRC, INTC,
MSTR, SRRK, VICR). Ten sessions of read exist for 51 fires on 15 names (AGX, ALAB, CHRN, CRWD, DG, ERO, HOOD,
IONQ, OKTA, PHVS, QCOM, ROIV, SEI, SOLS, VEEV); 44 clear the width floor.

| real-EP fires (n = 44 floored, 51 raw) | value |
|---|---|
| mean R10 / median | **−0.81R** / −1.00 |
| stopped by session 10 | 39 of 44 (88.6%) |
| stopped on the fire session / on session 1 | 15 + 15 = **30 of 44 (68%)** |
| kept ≥ 3R at session 10 | **0** |
| recorded peak before the stop ≥ 1R / ≥ 3R (stopped fires) | 12 of 39 (31%) / 3 of 39 (SEI +15.6R, CHRN +6.0R, PHVS +4.1R, every one to −1R; QCOM +4.1R and ERO +3.4R sit on stops under 0.5% wide and are dropped by the floor) |
| after a session-1/-2 stop, above the entry ten sessions later | **13 of 19 (68%)** — the opposite of the gappers' 18% |
| fire vs matched control, +2×ADR before −1×ADR, both at the close | **6 of 51 (11.8%) vs 21 of 58 (36.2%)** — the same 15 / 14 names, the same windows |
| three-session move INTO the fire (drift3), fires vs control, median | **+1.49×ADR vs +0.06×ADR** (bounce into the entry 1.02 vs 0.59) |
| sessions since the EP at the fire: 1 / 2 / 3–5 / 6–10 | 20 / 13 / 13 / 5 fires: −0.93 / −0.70 / −0.75 / −0.84R |
| in a +50% campaign / fire-anchored runner | 0 / 0 |

On real EPs the lane fires after the stock has already bounced a session-and-a-half of range, is stopped within a
session on two fires in three, and — unlike the gappers — the stock then recovers above the entry two times in
three. A random non-fire session of the same fifteen stocks reached +2×ADR first three times as often as the
fires did. This is fifteen names and one month; it cannot carry a verdict, and it is the only read of the lane
on the population it was built for.

### The joint table — the classes overlap; nothing above is summed across rows

| same-session stop | EP failed within 3 sessions | re-entry shape | fires | summed R10 | share of the loss | mean R10 |
|---|---|---|---:|---:|---:|---:|
| yes | yes | no | 514 | −514.0 | 40.2% | −1.00 |
| yes | yes | yes | 298 | −298.0 | 23.3% | −1.00 |
| yes | no | no | 295 | −295.0 | 23.1% | −1.00 |
| yes | no | yes | 276 | −276.0 | 21.6% | −1.00 |
| no | yes | no | 332 | −65.0 | 5.1% | −0.20 |
| no | yes | yes | 477 | −59.4 | 4.6% | −0.12 |
| no | no | yes | 515 | −24.9 | 1.9% | −0.05 |
| **no** | **no** | **no** | **521** | **+253.8** | **−19.9%** | **+0.49** |

Same-session stops on already-failed EPs alone are 63.5% of the loss (812 fires). The one positive cell — a
first attempt, not stopped the same session, into an EP that had not closed below its low — is 16% of fires at
+0.49R each; but "not stopped the same session" is not knowable at entry, and "EP not failed" is look-ahead for
fires at sessions 1–3 (§3), so it is a description of where the money was, not a filter.

## What this does not answer

Declared with the Method; the run added the last four.

- **One month, one regime.** Fires 2026-08-25 → 09-11 at ten sessions; nothing here says what these patterns do
  in a different tape.
- **The EP-ALERT cohort is 22 campaigns and 51 fires at ten sessions (44 floored) on 15 names.** It is the
  lane's intended population and it is too small to judge on its own; its tables are read as "what these 51
  did", never as a rate.
- **Half the stops are same-session stops whose order is unknown at daily grade** (1,383 of 3,228 floored fires,
  1,191 without a minute source). Where no post-fire minute source exists the class says "order unknown"; it is
  never resolved by assumption. Where one exists (192 fires) 36% went green first.
- **The primary runner label is a campaign label** (the stock ran +50% from its EP close within 15 sessions,
  P6's definition); a fire can sit after the run. The fire-anchored label is beside it for that reason, and it
  is capped at ten sessions so the whole population is observed. The two labels agree on every AUC ranking.
- **Most pre-entry traits from the EP screen are dark for rejected names** (`ep_score`, catalyst grade, theme
  membership are computed only for names that reach grading — 98% of fires). A dark trait is reported as dark,
  not as a null.
- **The peak-before-stop reading rests on daily highs**; a same-session ordering caveat is stated wherever
  `mfe_r` (which folds in the stop session's high) is used.
- **Nothing here re-prices the EP alert itself, tests a new rule, or picks one.**
- **R is the incumbent stop's own unit, and on the reclaim patterns that stop is the dip low printed minutes
  earlier** (median width after the 0.5% floor: 3.7% of the price — 2.8–3.8% on the three pullback patterns, 7.8%
  on the high break), so "≥ 3R" is a move of about 11% on the median stock, and "−3.7R at session 10" about −14%. Every R figure here is on the lane's own arm; ADR$ figures (Q2) are the unit
  the stop cannot contaminate.
- **The HELD / FADED / FAILED label contains the future for fires at sessions 1–3**; the tradable read (fires at
  session ≥ 4) is given beside it and shows no separation. The whole-population table stays because it answers
  the question as asked (were these re-entries into failed EPs — yes, half of them).
- **The 09-22 tail read and both Block 5 documents measured this same population** — the 08-31 first-run cohort
  the 09-01 ruling voided — without applying that ruling. Their cells stand as measurements of that cohort; what
  they are not is a read of delayed entry on EPs. Nothing in them is retracted here; the population fact is
  recorded in `docs/setups/delayed_ep_reentry.md` — this document's row, and a one-line note on theirs.
- **Seven still-open rows walk to a stop within ten sessions on today's daily table** (FEED ×2, CTSO ×4, SFWL)
  although production has not settled them — a hole production hit that the table has since filled. They are
  scored as walked and counted in `p7_summary.json` (`open_walk`); 7 of 3,228.

## What it implies — for his ruling, stated neutrally

**"We should have a good cohort already."** We have 3,228 fires of the wrong thing and 51 of the right one. The
3,228 are re-entries into stocks our screen rejected on the gap day — 92% for a prior close under $5 — the
population he voided on 09-01 (*"delayed entry is only a trading entry/exit tactic, not a EP finding system"*). Every downstream
test since (the 09-22 read, Block 5's 1,176 cells, the addendum, P6's 244 cells) ran on it. On that population the
answer is now also *why*: the trigger buys a reclaim that fails inside the session on 43% of fires and within two
sessions on 73%; the stocks keep falling (72% below the stop ten sessions later); the fires are slightly worse
than random sessions of the same stocks at the same place; and nothing knowable at entry separates the few that
run except that they are the most volatile sub-$1 names. That is the profile of a structurally bad-moment buyer
on a population that should never have been in the lane — not of a harvest problem, not of a stop-width problem,
and not of a selection rule waiting to be found inside it.

**"Unsure collecting more will change."** More of the same population will not: n is 3,228 and every cut is
flat. The real-EP cohort is a different population that has 51 fires, and on those 51 the same early-stop shape
appears, with two differences that cut opposite ways — the stocks recover after the early stop (13 of 19), and a
random session of the same stocks did three times better than the fire did (36% vs 12%). At the current live
alert rate (19 alerts on 18 market days since 09-01, 4.5 fires per alert campaign) the real-EP cohort grows by
roughly 22 campaigns and 100 fires a month, and a fire needs two weeks to have ten sessions of read; **from 51
today it reaches about 150 fires at ten sessions around the first week of November** if nothing changes.

**The fork this determines — three readings, his to rule on (nothing is proposed as decided):**

1. **A selection fix.** Already made on 09-01 (the lane now enrolls alerts only); what it produced is the
   51-fire cohort above. There is no further selection rule inside the rejected population — the only
   separators are volatility proxies for sub-$1 names, and the screen's own traits are dark on 98% of it.
2. **A trigger fix.** The same-session stop is the trigger's own construction on three of the four patterns
   (buy a 5-minute reclaim; stop at the dip low printed minutes below). Block 5 showed widening the stop alone
   does not pay on the rejected population; on real EPs the early stops were mostly shake-outs (13 of 19
   recovered), which is the shape a wider stop or a later entry would change — on 19 fires.
3. **Structurally a bad-moment buyer.** On the rejected population the within-stratum gap against random
   sessions is small (−2 points) but present on every pattern; on the 51 real-EP fires it is large (−24 points).
   If that holds at n ≈ 150, the reclaim session itself is the wrong moment regardless of stop or selection.

What separates 2 from 3 is the real-EP cohort at ten sessions and n ≈ 150, which exists in about six weeks at $0.
Whether to wait for it, change the trigger before it, or stop the lane is his call under CHANGE_PROCESS.

⚖ **THE LINE.** This day produced a diagnosis, ranked by loss share, and the fork above. It picked no stop, no
target, no exit, no selection rule and no population; no toggle, table, deploy, PLAN.md line or strategy was
changed; the lane keeps observing exactly as it did yesterday.

## Files

- `scripts/probes/_327_block5/p7_diagnosis.py` — the probe; its docstring is the pre-registration of record
  (committed before any result in `0f8fa521`). Runs in ~4 s on the P0/P3/P7 pulls.
- `scripts/probes/_327_block5/extract_p7.sh` — the three supplementary read-only pulls (gitignored CSVs;
  `ep_scan_log.pulled_at` records the pull time, 2026-09-26T22:33:01Z).
- `p7_summary.json` (every table: cohorts, anchors, Q1 per pattern × cohort, the after-early-stop read, Q2 per
  pattern with every stratum, Q3 buckets and AUCs, Q4 with the session-≥4 re-read, loss shares and the joint
  table) — committed. `p7_rows.csv` (per fire) and `p7_q2_rows.csv` (per fire and control session with features)
  — gitignored, regenerable.
- Block 5's extract and README: `scripts/probes/_327_block5/README.md` §P7.
