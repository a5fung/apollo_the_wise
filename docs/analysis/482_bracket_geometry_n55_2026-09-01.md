# #482 — the 5-minute-ORB lane re-read at n=38 (not 55), and the 20-of-21 finding retested

**2026-09-01 · read-only · $0 (one prod SELECT capture) · probe: `scripts/probes/_482n55/`**

**FIRST LINE / THE ANSWER:** the n=14 "decisively worse" *level* did not survive, but its
*conclusion* did — on the same ticker-days the 5-minute basis still captures **less** than the
live 1-minute bracket (worse on 16 of 22 pairs; in the current exit era, worse on all 3 of 3) —
and **the 20-of-21 "stop shakes out winners" finding is an artifact of an MFE column**: measured
on settled prices, only ~2 of 19 current live-money losers ever offered the ≥4R the goal needs.
No geometry variant earns the operator's attention today.

---

## 1. The decision this serves

The operator ruled 2026-07-18: **KEEP the 1-minute ORB live** pending evidence from the shadow
lane. The revisit condition (N≥30 closed 5-minute shadow trades) was met and never read. This
document is that read. It decides nothing — it tells the operator whether the accrued evidence
argues for reopening the geometry question.

**What would change the decision:** the 5-minute lane beating the live bracket on the *same
ticker-days* in the current exit era, or the loser cohort showing a large recoverable tail
(stopped names that then offered ≥4R). Neither happened.

## 2. Method / population

- **5-minute lane**: `mi_orb_shadow_trades`, `bar_size_minutes=5`, `quarantined=false`,
  `signal_type='magna53'` only, status `closed`. Window 2026-04-29 → 2026-08-28.
  ⚠ The task header says "~55 closed" — the lane holds **58**, but **20 are `9m_day2` rows, a
  strategy deprecated 2026-08-02** (dead strategies are not evidence), and prior work showed 9M
  rows carry an identical stop in both lanes anyway. **The honest base is n=38.**
- **Live baseline**: `mi_live_trades`, `signal_type='magna53'`, status `closed`, `risk_dollars>0`.
  Live money (n=26) and paper (n=26) **never pooled** — paper is 100% pre-08-01 era anyway.
- **R** = `total_pnl / risk_dollars` (dollar-risk normalized; identical definition both lanes and
  both stop eras — dollar risk per trade was unchanged by the 08-16 stop change). Using
  `risk_dollars_actual` instead moves the live-money mean by 0.003R (2 rows differ) — immaterial.
- **Forward prices**: `mi_daily_closes` settled closes and highs (never `mi_ep_scan_log.gap_pct`,
  never `mi_ep_scan_outcomes` — see §4).
- **Era gating** follows the codebase convention (`system_review.py` #585):
  **A** <08-01 (no executable partial, ORB-low stop) · **B** 08-01→15 (partial live, ORB-low
  stop) · **C** ≥08-16 (partial + `entry−2R` half-size stop = **the current exit**). Population
  sub-eras inside C: score rework 08-22 (C2), RS slot ranking 08-30 (C3). Realized R is never
  pooled across the 08-16 line as evidence; period cuts state their population. Same-ticker-day
  **pairs** cancel the admission-population change by construction and are the primary
  comparison. **April–May rows are context, never evidence** (operator ruling: stale system).
- Excluded everywhere: 28 quarantined shadow rows (#216 fabrications), 3 open shadow rows,
  2 live rows still open at the broker.

## 3. The numbers

### 3a. Does the n=14 conclusion survive? (the lane, in-lane)

| cut | n | sum R | mean | median | winners | ≥4R |
|---|---|---|---|---|---|---|
| 5-min lane, all closed magna53 | 38 | +0.7R | +0.02R | −0.70R | 12 | 1 |
| · era A (<08-01, old exit) | 25 | −5.5R | −0.22R | −0.99R | 5 | 1 |
| · era B (08-01→15) | 10 | +5.9R | +0.59R | +0.14R | 5 | 0 |
| · era C (≥08-16, **current exit**) | 3 | +0.3R | +0.09R | +0.16R | 2 | 0 |
| · replayed-from-daily-bars only | 16 | +15.6R | +0.98R | +0.30R | 9 | 1 |
| · accrued-in-real-time only | 22 | −14.9R | −0.68R | −0.99R | 3 | 0 |

- The old headline "0 wins in 14, avg −0.89R" is gone: the lane now has 12 winners in 38. **But
  the entire positive side sits in the 16 daily-bar reconstructions** (+15.6R), led by AMBQ
  2026-05-12 +7.3R — a May replay, i.e. stale context twice over. The 22 rows the lane accrued
  in real time sum **−14.9R with a −0.99R median** — the same shape the n=14 read saw.
- **Once gated to the current exit rule, the comparable sample is 3, not 55** (AMLX +1.12R,
  CRWD +0.16R, SOLS −1.00R — all real-time). Too thin for any level claim; reported as n=3.

### 3b. Like-for-like — same ticker-day in both lanes (population cancels)

| pairs (5-min R − live R) | n | sum delta | median delta | 5-min better |
|---|---|---|---|---|
| all pairs | 22 | +0.93R | −0.16R | 6 of 22 |
| excluding SYRE (sim artifact¹) | 21 | −3.39R | −0.17R | 5 of 21 |
| era A pairs | 15 | +1.85R (−2.47R excl SYRE, n=14) | −0.14R | — |
| era B pairs | 4 | −0.50R | −0.12R | — |
| **era C pairs (current exit)** | **3** | **−0.41R** | **−0.17R** | **0 of 3** |

¹ SYRE 2026-06-22: live took a real −5.02R gap-through fill; the sim booked −0.69R at a price
the stock never traded — a +4.32R phantom, identified in the 08-18 read and still in the table.

**On the same names, the wider bar still captures less.** The direction is consistent in every
era; only the era-C cell is current-rules evidence and it is n=3 (worse on all 3, by −0.02R to
−0.22R — small losses, but nothing arguing for a reopen).

### 3c. The 20-of-21 finding, retested — it does not hold; it was mismeasured

The original #468b metric was `mi_ep_scan_outcomes.fwd_5d_pct` = **max HIGH of the next 5
sessions vs the day-0 close** — maximum favourable excursion, positive on nearly every row by
construction (`outcome_tracker.py` ~L490; the exact failure class the analysis standard
catalogues from the #233 read). Retested on today's closed losers under three definitions:

| losers (realized R < −0.05) | n | "rose" by ORIGINAL defn (MFE > day-0 close) | settled: +5d close > our entry | offered ≥2R past entry in 5d | offered ≥4R |
|---|---|---|---|---|---|
| live-money, era A+B pooled² | 19 | 19 (100%) | 4 | 7 | **2** |
| paper, era A | 20 | 19 | 6 | 7 | 1 |
| 5-min lane, era A+B | 25 | 24 | 7 | 4 | 1 |
| live-money, era C | 2 | 2 | 1 | 0 | 0 |

² Both era-A and era-B live-money losers ran the ORB-low stop, the geometry #468b indicted;
pooled here for that reason only, n stated.

- **By the original metric, TODAY's losers also "rose" 19 of 19 — the metric cannot fail.** It
  flagged 95% then and flags 100% now because a stopped stock that ticks once above its
  depressed day-0 close within a week counts as "rose". The finding was never about geometry.
- Measured honestly, the recoverable tail is real but ~10× smaller: **2 of 19** live-money
  losers offered ≥4R within 5 days (HUT 07-20, +7.6R available; QBTS 07-27, +4.3R) — both under
  the retired ORB-low stop. The 2026-08-16 `entry−2R` stop is the operator's already-signed
  response to exactly this class; it has n=4 closed live trades so far (−0.17R net: AMLX +1.29,
  MRVL −0.87, CRWD +0.38, SOLS −0.98).
- The 5-minute bar does not harvest that tail either: its own losers offered ≥4R on 1 of 25.

### 3d. Both directions (P14) — what each lane misses

| of 52 live closed ticker-days, the 5-min lane... | n | live R on those days | live winners among them |
|---|---|---|---|
| also entered (the pairs) | 22 | −5.6R | CRSR +1.7, QURE +0.5, PLTR +3.3, ABCL +2.7, AMLX +1.3 |
| refused: gate_blocked | 7 | −7.1R | none |
| refused: no_entry (never broke 5-min high) | 14 | −8.9R | none |
| no shadow row (lane not running) | 9 | −2.0R | BW +2.5, RCAT +1.3 |

- The 5-min bar's refusals dodged only losers (−16.0R of live outcomes over 21 refused days,
  zero winners refused) — **as a skip-signal it filtered well on this sample**; but on the days
  both entered it captured less (§3b), so the lane's edge, if any, is *selection-shaped, not
  geometry-shaped* — consistent with every prior read routing the residue to selection.
- The lane's unique catches (16 ticker-days live never filled) sum +5.4R, but that is **AMBQ's
  +7.3R replay minus −1.9R across the other 15** — one stale-era reconstruction carries the cell.

### 3e. The tail (P3)

- **Live lane: 0 of 52 closed trades have EVER realized ≥4R.** 5-min lane: 1 of 38 (AMBQ, May,
  replay). At a ~19% win rate the average winner must clear ~4R to break even; neither bracket
  has produced one on real fills. Geometry has now failed to move this in four consecutive reads.

### 3f. The other variants named in the task

| variant | real accrued data? | what exists |
|---|---|---|
| (b) re-entry after a stop | **n=6, all 2026-04/05 — stale context by ruling** (−1.09R mean, 0 wins); **zero accrual since 05-11** | offline #572 sim (era A) only |
| (c) wait-for-established-intraday-low | **none — no lane exists** | offline #572 sim only |
| (d) ATR/structure stop | **none — no lane exists** (`mi_pivot_stop_shadow` is an exit-trail candidate lane, inert 0-of-12, not an entry-stop variant) | offline #572 sim (era A) only |

No variant has current-era evidence. Reporting the table as data would be filling it.

## 4. What this does not answer

- **Whether the 5-minute basis wins under the CURRENT system** — the honest current-era sample
  is 3 pairs. It answers "has the accrued evidence overturned the 7/18 ruling?" (no), not "is
  the question settled forever" (n=3 settles nothing; the lane keeps accruing at ~5 real-time
  closes/month).
- **Exit management** (#306): only bracket geometry was compared; targets, trails, and partials
  were held at whatever each lane's era ran.
- **Delayed entry / the pivot ladder / proximity / 620** — the operator-named untested arms live
  in `docs/setups/delayed_ep_reentry.md` (the CONTEXT LEDGER) and are explicitly out of scope
  here; nothing in this read bears on them.
- **Replay-vs-reality calibration**: the 16 replayed shadow rows ran today's exit ladder on
  daily bars (no day-0 path, no gap-through, no slippage) — they are one-directionally
  optimistic and were never compared against real fills as if equivalent; conclusions above rest
  on the paired and real-time cuts.
- **Why the August live-money month was positive** (+1.8R over n=14 — era B n=10 +1.9R,
  era C1 n=2 +0.4R, era C2 n=2 −0.6R): it spans three rule eras and two admission populations,
  so it is a selection/regime question, not a geometry one, and every cell is too thin to
  attribute.

## 5. ⚖ THE LINE

Bracket geometry is entry/exit discipline — the operator's sole authority. Nothing was changed:
no thresholds, no lanes, no strategy state. This document is evidence for his fork:

- **(a) KEEP the 1-minute ORB + 2R stop and let era C accrue** — recommended: three consecutive
  prior reads plus this one agree the opening-bar width is not the edge lever, the strongest
  contrary finding (20-of-21) is now shown to be a measurement artifact, and the current-era
  pairs (n=3) still favour the live bracket.
- **(b) If he wants a geometry answer faster than the shadow lane accrues (~5 real closes a
  month), direct the raw-bar replay build** (re-score under today's rubric → re-admit under
  today's stack → reconstruct from `mi_intraday_bars`) that the retracted 08-29 analysis
  established as the only valid instrument. It is a build, not a query, and it competes with
  selection work (#533) for the same effort.
