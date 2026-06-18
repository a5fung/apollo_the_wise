# #327 — 9M Day-2 ORB vs consolidation-entry replay (the #326 directional read)

**Status: DIRECTIONAL READ COMPLETE 2026-06-18.** Replay-first (live forward-shadow cannot
reach decision-grade N by the accelerated #326 ~7/7 call). Symmetric two-arm replay over the
historical `mi_9m_day2_candidates` cohort settles realized R on BOTH entries on the SAME 9M
names, same harvest, same forward window. **Read (two claims, different strength): (A SOLID) the
9M Day-2 ORB entry earns NO robust edge — break-even/outlier-carried — which alone carries the
#326 RETIRE half; (B PROMISING, selection-inflated → Phase-B-gated) the consolidation
(tightness→expansion) entry is the better replacement candidate. Operator decision (#326).**

Harness: `scripts/_327_replay.py` (Phases 1+3) · `scripts/_327_pull_minute.py` (Polygon pull)
· `scripts/_327_dump.py` (per-name audit). Data: `_327_cohort.tsv` (121 rows), `_327_daily.tsv`
(27,380 daily bars), `_327_minute.tsv` (94,796 Polygon 1-min bars, 103/105 tickers).

## The #326 question

Should the 9M Day-2 ORB entry be RETIRED in favour of a consolidation entry on the same 9M
names? (`memory:user_pradeep_9m_universe_methodology` — "all 9M EPs enter the flag-detector
universe; entry comes from tightness→expansion", not the Day-2 ORB.) #326 was pulled to ~7/7 to
move fast; a replay is the only thing that yields a clear read in that window.

## Method (advisor-locked 2026-06-18)

Two arms, **both** settled through `anticipation.SETTLE_RULE` (+1R/+3R ½-½ scale-out, day-5
time-stop) over the same forward window, realized R via the day-0-minute scale-out +
daily trail (`anticipation.simulate` / `simulate_first5` / `build_mixed_path` — MFE-free; **no
daily approximation of the intraday entry**, the error the #270 arc closed):

- **ARM 1 — Day-2 ORB** (incumbent): entry day = alert_date+1; entry = break of the Day-2
  opening-range (first-5-min) high; **STOP = prior day's low** (the 9M breakout-day low — the
  live `prepare_9m_day2_orb_order` rule, NOT the ORB low). Skip if stop >15% wide.
- **ARM 2 — consolidation**: the 9M day is the runup anchor; after a coil (tight/quiet base —
  `find_consolidation_breakout`, reusing `TIGHT_RANGE`/`VOL_CONTRACT`), take the intraday
  FIRST5-break on the first base-high breakout day; **STOP = first-5-min OR low** (tight).

Guards against this project's documented failure classes (advisor):
- **Full-universe expectancy** — a no-fill / never-consolidates name scores **0R**, never
  silently dropped (vs conditioning Arm 2 only on "a setup formed").
- **Replay both arms identically** — do NOT pull historical Day-2 ORB outcomes (IEX-paper
  contaminated per the Gate-3 finding; different live exits). Same bars, same rule.
- **Outlier-decompose** (the W2 skip-wide-open lesson): report median + ex-top-3 + top-3 share.
- **Universe both ways** — 9M-anchored (the 9M event is the qualifier) AND runup-canary-gated
  (≥1.15), so the detection-criterion fork stays explicit.

## Cohort funnel (Phase 1, daily)

```
cohort N=121 / 105 tickers · alert_date 2026-04-21..06-17 · daily back to 2025-05-12
anchor (9M day) found        : 121/121
ARM 1 settleable (≥5 fwd bars): 109
ARM 2 consolidation set up    : 37/121 (31%)  · settleable 35   [9M-anchored]
ARM 2 consolidation set up    : 28          [canary-gated ≥1.15]
```

**Finding #1 — the consolidation entry is SELECTIVE (~31% of 9M names coil+break in 15d).** It
is therefore a *complement/filter*, not a 1:1 blanket replacement for Day-2 ORB. The canary gate
drops only ~9 marginal names (median set-up runup 1.21), so that fork is low-stakes.

## Head-to-head (Phase 3, realized R)

```
                              filled-only                          full universe (0R no-fill)
ARM 1 Day-2 ORB    n=36  median −0.24R  win 47%  +3.2R   |  n=109  mean +0.03R  win 16%
   robustness: top-3 = 190% of total, ex-top-3 mean −0.09R  → the bulk LOSES; edge is 3 outliers
ARM 2 consolidation (9M-anchored)
                   n=17  median +2.00R  win 82%  +25.0R  |  n=108  mean +0.23R
   robustness: top-3 = 24% of total,  ex-top-3 mean +1.36R  → BROAD, not outlier-driven
ARM 2 consolidation (canary-gated ≥1.15)
                   n=14  median +2.00R  win 79%  +19.0R  |  n=89   mean +0.21R

PAIRED (N=108 both arms evaluable): per-name wins  Day-2 17  ·  consolidation 29  ·  tie 62
                                    mean delta (consol−Day2) +0.20R/name

WITHIN-NAME (N=17 names where consolidation FIRED — the apples-to-apples cut):
   ARM 1 Day-2 ORB on those same 17 : median +0.00R  mean −0.08R  win 18%  total −1.4R
      (10 of 17 had no Day-2 trigger = 0R; ex-top-3 −0.25R)
   ARM 2 consolidation              : median +2.00R  mean +1.47R  win 82%  total +25.0R
   per-name wins: consolidation 14  ·  Day-2 3      within-name delta median +2.00R / mean +1.55R
```

**Finding #4 — the edge survives the subset confound (advisor catch).** The paired 29-vs-17 is
diluted by 62 tie-at-0R names; the load-bearing cut is *within-name*: on the SAME 17 names where
consolidation fired, Day-2 ORB returned **−1.4R** (net negative, 10/17 didn't trigger). So
consolidation is not merely winning on an easier subset — on identical names, the incumbent
Day-2 entry was a net loser. That said, those 17 are still the daily-close-confirmed breakout
days (caveat #1) — the within-name cut removes the *which-names* confound, not the *which-days*
optimism.

**Finding #2 — the consolidation entry has a real, broad-based edge where it fires; Day-2 ORB is
break-even/outlier-carried.** Consolidation: +2.00R median, 82% win, +25R total, and crucially
NOT outlier-dependent (top-3 only 24%, ex-top-3 still +1.36R). Day-2 ORB: negative median on the
filled set (−0.24R), and its small +3.2R total is *entirely* 3 outliers (top-3 = 190% of total,
ex-top-3 negative) — the W2 artifact shape, here flagging the INCUMBENT as fragile.

**Finding #3 — the mechanism is stop tightness (the U&R paradox), audited per-name
(`_327_dump.py`).** Same harvest rule; the difference is the stop. Consolidation entries carry
tight first-5-min-low stops (~0.8–3.5%: APP 533/514, F 13.25/13.14, TXN 281/279) so the +3R
rung hits and winners bank the +2.00R ceiling. Day-2 ORB's prior-day-low stop is wide (~6–14%:
DELL 307/265, BABA 141/130) so +3R rarely hits → mostly −1R / partials. 17 distinct winners, no
single-ticker concentration — not a settlement bug.

## Caveats (this is DIRECTIONAL, not a ship verdict)

1. **Breakout-day selection is daily-close-confirmed → an OPTIMISTIC bias in Arm 2.** The replay
   takes the intraday FIRST5-break only on days the daily close confirmed the base-high break. A
   live intraday entry-watch would also fire on days that break intraday but **close weak**
   (failed breakouts → mostly −1R on the tight stop), which this replay excludes. So Arm 2's
   **magnitude is upward-biased by an unquantified amount** — I do not know the size of the
   excluded failed-breakout population, so I am NOT putting a number on the de-rated edge (any
   such number would be invented). The clean +2/−1 winner shape is itself a *symptom* of this
   selection — strong-close days are clean directional runs by construction. Honest statement:
   **the direction may survive largely because the incumbent is so weak (Finding #2), not
   because consolidation's measured magnitude is trustworthy.** Closing this is the Phase-B job:
   test FIRST5-break on EVERY post-coil day (not only confirmed-close days) — runnable offline
   with a wider minute pull, and the forward-shadow's whole point.
2. **Harvest CAPS the tail.** SETTLE_RULE banks ½ at +1R and ½ at +3R → winners cap at +2.00R;
   the fat tail (MNTS-class) is not captured. Deliberate "derisk fast" (#270). Both arms capped
   identically, so the comparison is fair, but neither arm's absolute R reflects tail capture.
3. **N is small** (17 consolidation fills, one ~2-month window) and in-sample. Read median +
   ex-top-3 (done), treat magnitudes as illustrative.
4. **Day-2 ORB replay uses a 5-min OR;** the live entry uses `get_first_bar` (1-min). A 1-min OR
   gives a slightly higher trigger / different stop distance — second-order vs the prior-day-low
   stop that drives Arm-1's weakness, but noted.

## Read for #326 — two claims of DIFFERENT evidential strength (do not weld them)

The decision splits into two claims; the *retire* half rests on the strong one.

- **CLAIM A (SOLID, self-standing) — the 9M Day-2 ORB entry earns no robust edge.** This needs
  nothing from Arm 2: filled median −0.24R, win 47%, and its only positive total (+3.2R) is
  *entirely* 3 outliers (top-3 = 190% of total, ex-top-3 negative); on the 17 names where
  consolidation fired it was net −1.4R. The wide prior-day-low stop is the mechanism. **This
  alone carries the RETIRE half of #326** — we are not displacing a positive base case.
- **CLAIM B (PROMISING but selection-inflated) — the consolidation entry is better.** +2.00R
  median, 82% win, broad (ex-top-3 +1.36R), within-name +2.00R delta — but the magnitude is
  upward-biased by the daily-close-confirmed breakout selection (caveat #1), unquantified.
  **GATE on Phase-B forward confirmation before any live sizing.**

So: the read supports **retiring/de-emphasising Day-2 ORB now** (Claim A), and **prioritising
the consolidation entry as the replacement candidate, shadow-first** (Claim B, confirmation-
gated). The accelerated #326 call asked for a directional read; this is it. GO is operator's.

**OPEN — a SCOPE call for the operator, not a data call:** consolidation fires on only ~⅓ of 9M
names. Retiring Day-2 ORB therefore *narrows the entered universe to that ⅓*. Claim A says the
other ⅔ weren't being profitably entered by Day-2 ORB anyway (so nothing of value is lost) — but
if #326 wants 9M names to retain *some* entry path, the ⅔ that never consolidate need a decision
(leave unentered / keep a de-sized Day-2 ORB for them / a different entry). Surface before cut-over.

## Phase B (live wiring) — separate, deferred (PLAN #327 follow-on)

Feed confirmed 9M names → Family-A consolidation universe → intraday entry-watch (reuse #94
flag-break) → shadow consolidation-entry → settle realized R forward. Produces the
forward-confirmation that closes caveat #1 and accrues out-of-sample N. Execution-side/split-
adjacent; does not serve the 7/7 read, so it is sequenced after this directional read.
