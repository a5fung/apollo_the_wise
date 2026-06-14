# Setup SSoT — Delayed-EP Re-entry (tiny-cap fast-runner) · #270

**Status: PRE-DEPLOY SPEC (shadow-first). Analysis + tuning COMPLETE 2026-06-14 (gate-free);
deployable wiring is the first post-#277-gate build. This file is the canonical definition
the deployment references — read it + `docs/setups/CHANGE_PROCESS.md` before any change.**

One **end-to-end trade tactic**, three layers, built as one unit (memory
`user-sip-setup-is-one-e2e-tactic`). NOT five fragments. Blueprint: the MNTS case
(`docs/analysis/mnts_delayed_ep_case_study_2026-06-11.md`); evidence + replay:
`docs/analysis/delayed_ep_composition_270.md` + `scripts/_270_*` (replay / cohort / entry).

## What it catches

The tiny-cap fast-runner "one-pays-for-ten-losers" tail the live auto-scanner FILTERS OUT
(`mcap_too_small < $500M`): a huge EP gap, a low-volume pullback that UNDERCUTS the gap-day
low, then an explosive volume-confirmed RECLAIM. Universe deliberately INCLUDES sub-$500M
for this WATCH/observe lane (the mcap floor stays only on the auto-trade lane).

## Layer 1 — READINESS (daily state machine)

From daily OHLCV (validated reproducing MNTS: WATCHED 5/26 → ARMED 6/08 → TRIGGERED 6/11):

| State | Criterion (defaults — see DECIDE) |
|---|---|
| WATCHED | gap day: close ≥ (1+GAP)·prev_close, close > SMA200, vol ≥ VOLX·ADV20. Record gap_day_low. |
| ARMED | within ARM_WINDOW days: low < gap_day_low (UNDERCUT — the arming event, NOT invalidation), vol < burst. |
| READY | close > gap_day_low AND close > SMA20 (two-fold U&R) AND vol > EXPANSION·avg(pullback vol). |

Defaults GAP +40% / VOLX 3× / ARM_WINDOW 15d / EXPANSION 1.5×. Cohort (134 huge-gap names,
2026-03..05): funnel WATCHED 62 → ARMED 30 (48%) → READY 16 (26% of watched) = SELECTIVE.

## Layer 2 — ENTRY (the layer that gets you in; READY ≠ entry). THREE modes.

Two are CONFIRMATION (fire on the trigger day, tuned on minute bars over 17 triggers + MNTS,
`_270_entry_replay.py`); one is ANTICIPATION (EOD, the day before, `_270_anticipation_replay.py`).
They are COMPLEMENTARY — anticipation fires only on the ~37% of armed names that coil; the fast
runners (MNTS-style undercut→trigger) never coil and take a confirmation entry.

- **ANTICIPATION (EOD, on a MATURE COILED day)** — Pradeep's "enter the day before, anticipating
  the breakout". COILED = reclaimed gap_day_low & SMA20 + tight range + quiet volume, no expansion
  (= the trigger minus the volume burst). **WHEN: not the first quiet day — wait for the coil to
  MATURE** (a ≥3-day developed base = the cheap EOD proxy for the operator's chart-read; the richer
  visual maturity read integrates with **#267 chart-vision** — see Known limitations).
  Entry = coiled close; **stop = coiled low**; **RE-ENTER at the next mature coil if shaken**
  (re-entry discipline is LOAD-BEARING — one-shot is −1R, the strawman). Captures ~25% of the run
  earlier (≈6% below the FIRST5 price) + fails small/fast (~2% stops). Maturity gate (vs the loose
  first-coiled entry): keeps all winners, lands entries closer to the breakout, **+2.9R → +7.0R
  full-cohort mean**, and **cuts outlier reliance** (top name 73%→40%). NOT an R-win vs
  confirmation — FIRST5's tighter 2% stop edges parity-clean R (7.6R vs 6.5R); anticipation's edge
  is the **earlier/lower entry** (below the gap, not chasing). ILLUSTRATIVE — N=8, the maturity
  threshold (≈3) is in-sample, MFE ceilings; the DIRECTION (require maturity) is robust (monotonic
  1→3), the magnitude needs multi-window re-validation (operator decision; data-blocked today).
- **CONFIRMATION PRIMARY — FIRST5-BREAK** (trigger day): break above the first-5-min high;
  **stop = first-5-min low**. Median stop **3%**, median **3.5R**, fills 15/18. = the MNTS
  "first-minute high/low HELD".
- **CONFIRMATION FALLBACK — GDL-RECLAIM**: reclaim the gap-day-low; stop = gap-day-low. Median
  10% stop, 1.4R, fills 18/18 — covers the ~3 names where the 5-min break never clears the
  gap-day-low. The tighter FIRST5 stop (3% vs 10%) is 2.5× the R on the same move (U&R paradox).

## Layer 3 — EXIT / harvest (derisk FASTER)

Tiny-cap fast runners: partials EARLIER + more often than the standard ladder. PROVEN
necessary by the cohort: fat MFE tail (median +8% / best +137% over 10d) but WEAK close-
returns → the edge is the excursion, only realized by early harvest, not buy-and-hold.
(W3 exits / P3 management-judge — built WITH this tactic, not separately.)

## Surfacing

A READY/ARMED transition is RARE (~1/week in the cohort) + actionable → operator ALERT
(NOT the #168 per-tick-noise class; `memory:feedback_alert_vs_audit`). ARMED → name joins
the intraday entry-watch + a `/`-board (watched/armed/ready) + EOD digest; ENTRY (intraday
tactic fires) → real-time alert with the structural stop (the reclaimed gap-day-low) + the
harvest-fast note. Shadow = informational; graduates to actionable only with forward-outcome
data + the exit layer (the #168 actionability gate).

## ⚠ OPERATOR DECISIONS — set BEFORE the deployable wiring (step 3)

1. **EXPANSION floor** — the ratio is unstable on near-zero pullback baselines (HCAI 86×,
   RLYB 104× are tiny-denominator artifacts) → floor the pullback-avg volume or cap the ratio.
2. **Trigger-volume floor** — thin trigger days slip through despite the $20M gap-day
   liquidity (SILO/KFRC/CAMP < 0.5M shares) → add a min absolute / dollar-volume floor on the
   trigger bar.
3. (Optional) tighten GAP/VOLX/ARM for fewer/higher-quality flags — the funnel is already selective.
4. **ANTICIPATION inclusion + maturity threshold + re-validation** — include the anticipation EOD
   entry path in the step-3 deployable? It's +EV in this cohort but ILLUSTRATIVE (N=8). The
   **maturity gate (≥3-day base)** is the key knob — it keeps all winners while cutting the outlier
   reliance (top 73%→40%); confirm the threshold (≈3, in-sample). Decide over how many windows to
   re-validate the magnitude before SIZING it (the signal can ship shadow regardless; sizing is the
   gated decision). Re-entry discipline + the maturity chart-read surfacing must be supported.

## Known limitations / caveats

- Cohort calibration is N=16 triggers over one ~3.5-month window — observational, not a
  multi-regime backtest. MFE is favorable-excursion, NOT realized P&L (no exit applied).
- Anticipation expectancy is N=8, **outlier-leveraged** (one name = 73% of total R; survives
  ex-top at +0.5R/name but the magnitude needs multi-window re-validation), MFE-ceiling, and
  **conditional on re-entry discipline** (one-shot is −1R).
- Readiness is EOD (daily); the intraday confirmation entry-watch needs the live bar stream
  (execution-side). The anticipation signal is EOD-computable (no intraday stream needed).
- **Chart-vision maturity (#267 integration, operator 6/14):** the `base_run` gate is a cheap
  numeric proxy; the real maturity judgment is visual. **#267** builds a point-in-time
  `mi_daily_closes` renderer (no-lookahead) + a VLM chart-structure axis for the EP grade judge —
  it should be built as SHARED infra so the #270 anticipation maturity read is a 2nd consumer
  (`base_run` = pre-filter; chart-vision = the richer read, advisory→scored). Today's `charts.py`
  (Finviz live mosaic) is lookahead-unsafe and NOT usable for this. Wire #270 into #267's scope.
- Deployable wiring (scheduler job + lifecycle state table + entry-watch + alerts) is GATED
  post-#277 (it runs in `combined` = the §C rollback target).

## Change log

- **2026-06-14** — Setup SPEC created. Readiness validated vs MNTS + cohort-calibrated;
  entry tuned (FIRST5-BREAK 3.5R); exit characterized (derisk-fast). All gate-free analysis.
  Deployable wiring sequenced post-#277. Operator decisions (above) pending before wiring.
- **2026-06-14 (later)** — **ANTICIPATION entry added as Layer-2 third mode** (`_270_anticipation_replay.py`,
  step 2c). Pradeep's EOD coiled-day entry: +2.9R mean/name stop-and-reenter, validates both his
  claims. Does NOT beat confirmation on parity-clean R (FIRST5's tighter stop edges it 7.6R vs
  6.5R after the advisor-caught MFE-parity fix — the first cut wrongly denied FIRST5 the
  breakout-day high); anticipation's edge is the earlier/lower entry. ILLUSTRATIVE (N=8,
  outlier-leveraged, re-entry load-bearing). Decision #4 added. Gate-free analysis.
- **2026-06-14 (later still)** — **MATURITY gate** (operator: "wait for the coil to mature — this
  is where chart-reading helps"). Anticipate on a ≥3-day developed base, NOT the first quiet day.
  Sweep: keeps all 5 winners, entry closer to breakout (7→5d), fewer attempts (1.7→1.2), full-mean
  +1.7→+7.0R, **outlier reliance 73%→40% / ex-top +0.5→+4.8R** — de-risks the outlier WITHOUT a
  second window (which is data-blocked: `mi_daily_closes` starts 2025-05-12, SMA200 lookback eats
  the gap). DIRECTION robust (monotonic 1→3); threshold in-sample. Surfacing adds coil-maturity
  (day-N of base) for the chart-read. Gate-free.
