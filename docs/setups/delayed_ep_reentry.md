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
  first-coiled entry): **keeps all 5 winners while dropping losers** — the real signal is this
  winner-retention (`caught` holds as `fired` falls 11→8), NOT the +R rise (which is partly
  mechanical: a higher gate just shrinks the set + excludes losers). Also lands entries closer to
  the breakout + **cuts outlier reliance** (top name 73%→40%).
  **⚠ R vs confirmation — MFE-vs-MFE, NOT a realized edge (advisor 6/14):** the parity numbers
  (anticipation 6.5R loose / 15.0R mature vs FIRST5 7.6R, N=4) are **perfect-foresight MFE
  ceilings on BOTH sides** — they rank entry *timing/price*, not harvested P&L. Run the
  anticipation win leg through the **same realized-exit rules** as Layer 3 (over the full N=8
  triggered cohort) and the +3.3R MFE net **collapses to realized median ≈ 0R (all-out +1R AND
  scale +1R/+3R; −1R on ½-trail), mean negative** — the −1R shake costs eat every harvest rule.
  That is **below FIRST5's matched-rule realized (+1R all-out, +2R scale): harvested, FIRST5
  edges anticipation on every rule — there is NO realized-R advantage for anticipation** (cohort
  caveat: FIRST5 N=15 day-0-minute single-entry no-shakes vs anticipation N=8 daily with re-entry
  shake costs → directional, not head-to-head). So anticipation's ONLY defensible edge is the
  **earlier/lower entry** (price capture: ~25% of the run, ~6% below FIRST5) + complementarity.
  ILLUSTRATIVE — N=8, threshold ≈3 in-sample; the DIRECTION (require maturity) is robust
  (winner-retention), the magnitude needs multi-window re-validation (data-blocked today).
- **CONFIRMATION PRIMARY — FIRST5-BREAK** (trigger day): break above the first-5-min high;
  **stop = first-5-min low**. Median stop **3%**, median **3.5R (intraday MFE/risk, NOT
  realized)**, fills 15/18. = the MNTS "first-minute high/low HELD". *Realized* under Layer 3
  harvest = median **+1R** all-out / **+2R** scale +1R/+3R (the load-bearing number).
- **CONFIRMATION FALLBACK — GDL-RECLAIM**: reclaim the gap-day-low; stop = gap-day-low. Median
  10% stop, 1.4R **(MFE/risk)**, fills 18/18 — covers the ~3 names where the 5-min break never
  clears the gap-day-low. The tighter FIRST5 stop (3% vs 10%) is 2.5× the R on the same move (U&R
  paradox). *(All Layer-2 entry R's are MFE/risk ceilings — the realized number lives in Layer 3.)*

## Layer 3 — EXIT / harvest (derisk FASTER — BACKTESTED 2026-06-14)

Now backtested (`scripts/_270_exit_replay.py`, gate-free): FIRST5 entry held CONSTANT to
isolate the exit; **realized R** (not MFE) under a speed spectrum; advisor methodology —
median + ex-top-2 (mean is outlier-dominated), intrabar opt/pess bracket, day-0 MINUTE +
day-1+ daily resolution, gap-through stop-fills `min(stop, bar_open)`. N=15 filled triggers.

| harvest rule | med R | ex-top2 R | win% |
|---|---|---|---|
| **hold to 10d close** | **−1.00** | −0.19 | 27% |
| all-out at +1R | +1.00 | +0.36 | 73% |
| scale +1R / +3R (½/½) | **+2.00** | +0.59 | 53% |
| (perfect-foresight MFE ceiling) | +7.62 | +6.66 | 100% |

**Findings (robust DIRECTION — not the magnitudes, which are in-sample):**
- **Buy-and-hold LOSES the median name** (−1R, 27% win). Its +1.6R *mean* is purely the
  HCAI/ASTI outliers — exactly the artifact the median exposes (W2 skip-wide-open lesson).
  **Derisk-fast is empirically necessary**, not a preference.
- **The harvest is a SAME-DAY (trigger-day) event**: opt==pess for every rule → the
  spike-and-give-back happens at minute resolution on the trigger day, so the daily
  intrabar ambiguity never bites. "Derisk fast" literally = **scale out into the
  trigger-day spike.**
- **The +137% fat tail is NOT systematically harvestable** by a stop rule — any held
  runner bleeds the median in this same-day-give-back cohort. It's a rare bonus, not a
  harvest target; a scale-out ladder caps it (e.g. at +3R) and that's the right trade.

**RULE (illustrative direction; deploy in SHADOW, size only after multi-window re-validation
+ the live forward data):** scale out FAST into the trigger-day spike — bank a floor tranche
at ~+1R + a spike tranche at ~+3R; do NOT buy-and-hold. The exact targets/fractions
(+1R/+3R, ½/½) are tuned on N=15 one window → an OPERATOR DECISION (see below), shadow first.
(W3 exits / P3 management-judge — this is that layer, built WITH the tactic.)

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
   entry path in the step-3 deployable? **Realized** (Layer-3 harvest, advisor 6/14, full N=8
   triggered cohort) it nets **median ≈ 0R (all-out AND scale +1R/+3R; −1R on ½-trail), mean
   negative** — *below FIRST5's matched-rule realized (+1R all-out, +2R scale), NOT the +2.9–15R
   the MFE ceilings implied.* So the honest case for inclusion is **price capture + complementarity**
   (it fires on the ~37% coil set the confirmation entry catches late), NOT a higher realized R —
   harvested, FIRST5 edges it. The **maturity gate (≥3-day base)** is the key knob — keeps all winners while
   cutting outlier reliance (top 73%→40%); confirm the threshold (≈3, in-sample). Decide over how
   many windows to re-validate before SIZING (the signal can ship shadow regardless; sizing is the
   gated decision). Re-entry discipline + the maturity chart-read surfacing must be supported.
5. **EXIT ladder targets/fractions** — the backtest (Layer 3) confirms derisk-FAST (don't hold)
   and that a scale-out ladder beats a single target in-sample (+1R/+3R ½/½ → median +2R). The
   exact targets/fractions are tuned on N=15 one window. Decide the shipped SHADOW ladder (default
   +1R/+3R ½/½) and how many windows to re-validate before SIZING; the rule ships shadow now
   (records realized R against the live forward path), sizing is the gated decision.

## Known limitations / caveats

- Cohort calibration is N=16 triggers over one ~3.5-month window — observational, not a
  multi-regime backtest. MFE is favorable-excursion, NOT realized P&L (no exit applied).
- Anticipation expectancy is N=8, **outlier-leveraged** (one name = 73% of total R; survives
  ex-top at +0.5R/name but the magnitude needs multi-window re-validation), and **conditional on
  re-entry discipline** (one-shot is −1R). The headline +2.9–15R figures are **MFE ceilings**;
  **realized (Layer-3 harvest, full N=8) median ≈ 0R (all-out and scale; −1R ½-trail), mean
  negative — below FIRST5's matched-rule realized (+1R/+2R)** — anticipation's edge is the
  earlier/lower ENTRY PRICE + complementarity, not a higher realized R than FIRST5 (advisor 6/14).
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
  claims. Parity vs confirmation was computed at min_base=1 (loose): FIRST5's tighter stop edges it
  7.6R vs 6.5R (after the advisor-caught MFE-parity fix — the first cut wrongly denied FIRST5 the
  breakout-day high). Anticipation's edge = the earlier/lower entry. ILLUSTRATIVE (N=8,
  outlier-leveraged, re-entry load-bearing). Decision #4 added. Gate-free.
- **2026-06-14 (later still — Layer 3)** — **EXIT/harvest BACKTESTED** (`_270_exit_replay.py`,
  operator: "go with 270"). FIRST5 entry held constant, realized R, advisor methodology
  (median+ex-top2, intrabar opt/pess bracket, day-0 minute / day-1+ daily, gap-through stops).
  N=15. RESULT: buy-and-hold loses the median name (−1R/27% win; its +1.6R mean is the
  HCAI/ASTI outlier artifact) → derisk-fast is EMPIRICALLY NECESSARY. Harvest is a same-day
  event (opt==pess everywhere). Scale-out +1R/+3R beats single-target in-sample (median +2R).
  +137% tail is NOT systematically harvestable (held runners bleed the median). Rule = scale
  out fast into the trigger-day spike; magnitudes illustrative (N=15) → operator decision #5,
  shadow-first. Gate-free.
- **2026-06-14 (e2e honesty pass — advisor holistic review)** — the advisor's whole-tactic review
  caught that the **entry-mode R ranking was MFE-vs-MFE**, not realized. Three fixes: **(a)** ran
  the ANTICIPATION win leg through the **same Layer-3 realized-exit harness** (`harvest_realized`
  in `_270_anticipation_replay.py`, full N=8 triggered cohort) — the +3.3R MFE net **collapses to
  realized median ≈ 0R (all-out and scale; −1R ½-trail), mean negative — below FIRST5's matched-rule
  realized (+1R/+2R)**, so **harvested FIRST5 edges it; no realized-R basis to prefer anticipation**
  (its edge is the earlier/lower entry PRICE + complementarity only); **(b)** **measured** the
  fill-day distribution in `_270_exit_replay.py` (was inferred from opt==pess) — confirms
  **same-day harvest: all-out banks 93% on the trigger day, scale +1R/+3R 87%**; **(c)** relabeled
  every Layer-2 entry R as an **MFE/risk ceiling** with the realized number adjacent. Verdict
  (absolute tactic) UNCHANGED: FIRST5 + derisk-fast = realized median +1–2R, positive; only the
  entry-mode *ranking* was corrected. Gate-free.
- **2026-06-14 (later still)** — **MATURITY gate** (operator: "wait for the coil to mature — this
  is where chart-reading helps"). Anticipate on a ≥3-day developed base, NOT the first quiet day.
  REAL evidence = **winner-retention** (advisor): `caught` holds at 5 while `fired` falls 11→8
  across min_base 1→3, clip at 4 → ≈3 = edge/ceiling; the +R-magnitude rise is partly mechanical
  selection (in-sample). Also: entry closer to breakout (7→5d), fewer attempts, **outlier reliance
  73%→40%**. **Parity RE-BASED at the maturity setting** (advisor — the min_base=1 number doesn't
  describe a min_base=3 cohort): @3 the tight mature coil matches FIRST5's 2% stop while keeping the
  lower entry → anticipation 15.0R vs 7.6R (N=4, illustrative; flips the loose result). Second
  window data-blocked (`mi_daily_closes` from 2025-05-12, SMA200 eats the lookback). Surfacing adds
  coil-maturity (day-N of base) for the chart-read. Gate-free.
