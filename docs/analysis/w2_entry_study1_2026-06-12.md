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

**What remains open (not refuted, untested):** the hypothesis on the FULL
year. The strong-month cohort was never tested against the filter. Path to a
real answer: backfill `mi_daily_closes` OHLC to 2025-05, rerun the sweep —
then both regimes are covered. Until then: NO change, and the Gemini
amendment's 0.25–0.30×ATR prior stands unvalidated either way.

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

- **OHLC backfill to 2025-05 + sweep rerun** — the full-year test of
  skip-wide-open (also fixes ATR coverage for any future entry study and
  makes `validate_orb_entry` honest in replay). Filed under W2.
- Monday (per runway): stop-geometry study (ORB-low vs ATR-floor vs day-low
  by gap bucket) — uses the same harness; ATR coverage caveat applies there
  too → do the backfill FIRST.
