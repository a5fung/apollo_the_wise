# W2 Entry Study #1 — OR-window + skip-wide-open (2026-06-12)

**⚠ VERDICT (corrected same-day): skip-wide-open REFUTED on the honest window —
the initially-reported +49% lift was a coverage artifact. 5-min OR refuted
cleanly. NO live change proposed. Read §Artifact before citing anything here.**

**Cohort:** the #268 Phase B judged candidates (2025-06-09 → 2026-05-04,
1,307 graded+judged). Same selection, same exit model — only entry geometry
varies. Harness: `selection_replay_268.py --simulate --or-window N
--wide-open-atr X` (knobs added `17c1883`; defaults = live behavior).

## Finding 1 — 5-min OR is harmful (VALID result)

| Geometry (judge-HIGH arm) | n | exp/trade | win% | sum R |
|---|---|---|---|---|
| Baseline: 1-min ORB (live) | 399 | +0.95R | 30% | +378.2R |
| 5-min OR | 300 | +0.15R | 37% | +44.8R |

Win rate rises (fewer noise stop-outs) but expectancy collapses: the wider
range raises the entry and deepens the stop, crushing R-multiples on the
winners that pay for everything. This comparison is calendar-fair (both arms
span the full year identically). **Dead — do not revisit without a different
stop model** (5-min OR entry + non-OR stop = a different study, Monday's
stop-geometry slot).

## Finding 2 — skip-wide-open: REFUTED after artifact correction

**The naive result looked spectacular** (+0.95R → +1.42–1.52R across the whole
K=0.20–0.35 sweep, "robust plateau"). It was an artifact:

**§Artifact.** `compute_atr_14` reads OHLC from `mi_daily_closes`, whose
high/low columns were backfilled 2026-04-25 **with limited depth** — H/L (and
therefore ATR) exist only from ~2025-10 onward. Before that, ATR=None and the
filter SILENTLY NO-OPS (pass-through by design). Monthly pass rates at K=0.30:
100/100/100/96% (Jun–Sep, filter inert) → 61/24/31/21/25/20/20% (Oct+, filter
operating). So every sweep arm kept ALL of the strong early months' trades
and only cut trades in the weak later months — manufacturing "lift" at every
threshold. The plateau across K was the same artifact, not robustness.
(The baseline 1.5×ATR rule fired 0× all year for the same reason + looseness.)

**Honest re-measure on the ATR-covered window (2025-10-01+, judge-HIGH arm):**

| Cohort | n | exp/trade | win% | sum R |
|---|---|---|---|---|
| Baseline (Oct+) | 249 | +0.32R | 29% | +79.1R |
| K=0.30 kept (Oct+) | 67 | **+0.25R** | 22% | +16.8R |
| Removed by filter (their baseline R) | 182 | **+0.34R** | 31% | +62.3R |

Where the filter actually operated, the trades it removed were BETTER than
the ones it kept. Refuted on this window.

**Corroborating live read:** of the last 25 live MAGNA53 submissions (45d),
only 3 had OR range ≤ 0.30×ATR — at K=0.30 the filter is effectively a
"don't trade at all in chop" switch, which the Oct+ numbers say is not
edge-positive at the trade level.

**Full-year honest test (run same evening — operator-approved OHLC backfill
to 2025-05, 1.24M rows / 111 dates, then full rerun):**

| Cohort (judge-HIGH arm, full ATR coverage) | n | exp/trade | $/trade | total $ |
|---|---|---|---|---|
| Baseline (re-run post-backfill) | 386 | +1.00R | +$324 | +$125,194 |
| K=0.30 kept | 73 | +3.63R | +$1,036 | +$75,614 |

The headline lift LOOKS spectacular but decomposes badly:

- **Median kept trade = −1.00R** (most are full stops); win rate 29%.
- **Top-5 trades carry 91% of the R** (+241.9R of +265.0R: ZEPP +128.5R,
  BE +43.1R, PRG +26.7R, MATV +24.4R, METC +19.2R) and **85% of the dollars**.
  Excluding them: +0.34R/trade — below baseline.
- Total P&L is 40% LOWER (slot capacity isn't the binding constraint at this
  trade frequency — 73 trades/yr ≈ 1.4/week never saturates the 5-slot cap,
  so per-trade concentration buys nothing structurally).
- The mechanism cuts both ways: ultra-tight ORBs produce monster R-multiples
  in sim, but live they are the LYG one-cent-ORB class — paper-trigger
  failures, tick-noise stop-outs the 1-min-bar sim cannot see, and notional
  caps that shrink dollars-per-R. The sim is most flattering exactly where
  the filter concentrates.
- The strategy's character transforms: ~7% of trades carry the year. The
  signed kill/scale bands (calibrated on the baseline profile: 15-loss
  streaks, trailing-20 p5 −0.63R) would mis-fire constantly on a
  median−1R/monster-tail profile.

**FINAL VERDICT: NOT SHIPPABLE.** n=5 outliers over 12 months is undecidable
evidence for a change of this magnitude. Parked — revisit only inside a
broader entry-technique redesign (e.g. as a sizing/conviction INPUT rather
than a hard skip), or with materially more data. The Gemini 0.25–0.30×ATR
prior is neither confirmed nor refuted; it selects a real structural class
whose payoff is too tail-concentrated to gate on.

## Finding 3 — methodology lessons (the real yield of the day)

1. **Coverage-check before celebrating a filter backtest**: a conditional
   filter must be verified to have OPERATED across the whole cohort (count
   its skip events by month/segment) before its arm is compared to baseline.
   A filter that no-ops on the good segment and operates on the bad one
   manufactures lift mechanically. Same family as
   `feedback_validate_metric_before_decision` (2026-05-18 rel_volume_floor)
   and the 2026-05-21 polluted-cohort retraction.
2. **A "robust plateau" across thresholds is NOT sufficient evidence of a
   real effect** — a coverage artifact produces exactly the same plateau.
3. The 1.5×ATR `validate_orb_entry` rule has effectively never fired in
   replay (0/1307) and rarely live — it's a tail guard, fine, but don't cite
   it as active protection.

## Caveats on the valid finding (5-min OR)

Same recall/fidelity caveats as Phase B (scan ≈47% recall, IEX-bar sim,
single pass). Directionally strong (n=300 vs 399, −0.80R/trade delta).

## Follow-ups

- ~~OHLC backfill to 2025-05 + sweep rerun~~ — **DONE same evening**
  (operator-approved; 1.24M rows / 111 dates). ATR coverage is now full-year
  — `validate_orb_entry` is honest in replay and Monday's stop study is
  unblocked.
- Monday (per runway): stop-geometry study (ORB-low vs ATR-floor vs day-low
  by gap bucket) — same harness, coverage now clean. Carry the lesson:
  decompose any winner-cohort for outlier concentration BEFORE proposing.
- Possible future shape for the wide-open signal: a CONTEXT INPUT (sizing /
  judge payload / briefing tag), never a hard skip — the class is real, the
  gate is wrong.
