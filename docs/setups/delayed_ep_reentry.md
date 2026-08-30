# Setup SSoT — Delayed-EP Re-entry (tiny-cap fast-runner) · #270

> 📜 **THE PRINCIPLES (P1-P10) + THE GOAL live in `docs/roadmap/ep_profitability_program.md` § THE PRINCIPLES.** Read them before any analysis, card or proposal here — they are the operator's own rules, in precedence order, and they govern this document. Cite by name (P1, P2…). ⚖ THE LINE sits above all of them.


**Status: PRE-DEPLOY SPEC (shadow-first). Analysis + tuning COMPLETE 2026-06-14 (gate-free);
deployable wiring is the first post-#277-gate build. This file is the canonical definition
the deployment references — read it + `docs/setups/CHANGE_PROCESS.md` before any change.**

> ⚠ **2026-08-16 — THE LONG-WAIT VARIANT OF THIS SETUP CONVERGES INTO FAMILY A.** Measured: of the
> names caught by a 20-day reclaim window with a ≥5R outcome, **81% were already on the Family A
> candidate detector** — though NONE reached its tradeable entry signal. So a long-wait delayed-EP
> re-entry is a **promotion problem inside the consolidation play**, not a separate setup. The
> short-wait variants (3–10 days, reclaim of the EP-day low or close) remain genuinely distinct.
> Evidence + caveats: `docs/roadmap/ep_profitability_program.md` (2026-08-16 sections);
> Family A reference: `docs/decisions/0013-consolidation-plays-post-runup.md` §2026-08-16.

One **end-to-end trade tactic**, three layers, built as one unit (memory
`user-sip-setup-is-one-e2e-tactic`). NOT five fragments. Blueprint: the MNTS case
(`docs/analysis/mnts_delayed_ep_case_study_2026-06-11.md`); evidence + replay:
`docs/analysis/delayed_ep_composition_270.md` + `scripts/_270_*` (replay / cohort / entry).

## 🗂 THE CONTEXT LEDGER — read this before ANY delayed-entry work (operator 2026-08-29)

> *"i don't want delay entry to be re-discussed everytime with no context, make sure everything
> is saved 100%, history, convo, context and linked everywhere we have delay entries, all tasks,
> etc. and whatever finding when we're done."*

**Why this exists.** On 2026-08-29 I ran two cards on delayed entry with no context loaded. Both
returned his own methodology restated back to him: *"these 'detectors' are stuff I already told
you about... you didn't discover anything."* The context was all here — this file, the pivot
principles, the #562 study — and I did not read it. **This ledger is the fix: one place that
carries the goal, his rulings, every study and its result, and the open questions.** Anything
below is a pointer, not a copy — the linked doc stays the SSoT for its own numbers.

🔒 **Mechanically held:** `tests/test_delayed_entry_ledger_complete.py` FAILS the build when a
delayed-entry analysis or design document exists that this ledger does not reference. A finding
cannot become orphaned by inertia, which is how this context was lost the first time.

### Why delayed entry exists at all

**P1 — a real EP must never be missed.** When a real EP gets past us on day 1 (infra skip,
cooldown, a gate we have since changed, or we were simply stopped out), **the EP is still real
and the tail is still there.** Missing day 1 must not mean missing the name. With **1–3 real EPs
a quarter**, one recovered name is a material fraction of the whole objective.
**THE GOAL it serves:** ~4 converted tail winners in 4½ months. At a ~20% win rate the average
winner must exceed **4R just to break even** — so judge every arm by **P3 (hunt the tail, not
the average)**, never by win rate alone.

### His rulings — verbatim, because they keep getting re-derived

| date | ruling |
|---|---|
| 2026-06-11 | A **pivot is any reasonable reference point for risk management** — it locates the ENTRY and IS the STOP. MAs and gap-day lows are merely the EASY ones; congestion, volume shelves, swing levels count equally. |
| 2026-06-11 | **Pivots are conditioned on the stock's own character** — some names pull back to the 10MA, some the 20MA, some habitually undercut before resuming. ⚠ *"Do NOT implement as one global pullback-MA parameter tuned on aggregate data — that erases the per-stock character that IS the principle."* |
| 2026-06-16 | The undercut is **ONE shape, not the requirement**. The core signal is a constructive tightening pullback. |
| 2026-08-16 | The **pivot ladder**: EP-day LOW · EP-day CLOSE · EP-day HIGH · prior-day high · MA10 — each with its own entry and stop. Plus **proximity-not-touch**: switch to the intraday **620 chart** when price NEARS a pivot; a rigid touch test is the wrong instrument (P2). |
| 2026-08-29 | **Day 1 geometry does not transfer.** *"day 2 shouldn't use any ORB entry, delay entries always look for some base and/or reclaim pivots; not just day 2, it's day 2+ can be any subsequent days up to a point."* An opening range is a **day-1 construct**. |
| 2026-08-29 | 🔑 **"NEAR" IS A BEHAVIOUR, NOT A DISTANCE.** *"near by default is not numerical, it's an approximation, if it's a hard rule then we wouldn't call it near... when I see a chart and see it dropping towards a pivot then it slows down, stops dropping, consolidates, then turn back up, then this is the near point for that particular stock for that particular instance."* → **approach → deceleration → cessation → consolidation → turn.** Self-scaling per stock and per instance; no percentage. ⚠ #562's `pivot ± 0.5×ADR` is the rigid instrument this ruling replaces. |
| 2026-08-29 | 🔑 **THE PIVOT IS THE FILTER, NOT THE TRIGGER.** Follows from the ruling above: the behaviour gets you in, the pivot only says whether this turn is worth taking. **A tool alone is worthless** — *"you can't take 620 on its own, there's going to be dozens and hundreds of 620 turns over 20 sessions... you couple 620 with pivots."* Measured: 620-ANY **+0.04R**, 620@EPC **+0.21R**. |
| 2026-08-29 | **Innovate, do not just check his list.** *"the tactics I shared are ideas, there may be more, this is where your analysis needs to add value beyond just mechanically check my ideas, innovate."* |

### The studies — what each one established

| study | population | what it established |
|---|---|---|
| `docs/analysis/mnts_delayed_ep_case_study_2026-06-11.md` | MNTS, one name | **The blueprint.** The **two-fold U&R** — 21EMA/20MA reclaim AND gap-day-low reclaim resolving in ONE move. Two pivots agreeing ⇒ a tight honest stop with the whole consolidation as cushion. **Confluence is the original idea and it has still never been measured as its own arm.** |
| `docs/analysis/delayed_ep_composition_270.md` · `delayed_ep_rmv_step0_270.md` | 134 huge-gap names, 03–05 | The Layer-1 state machine (WATCHED → ARMED → READY) and its funnel: 62 → 30 (48%) → 16 (26% of watched). Selective. |
| `docs/analysis/pivot_ladder_delayed_entry_562_2026-08-18.md` | DECLINED names, daily proxy | First ladder sweep. **Superseded** by the study below — wrong population, daily-grain proxy. |
| `docs/analysis/conversion_rehearsal_2026-08-18.md` | surfaced tail winners | **The mechanism that motivates all of this:** our tail winners' runs start **7–21 sessions AFTER** the EP day, and in 3 of 5 measurable cases the launching base formed later and **BELOW** the EP-day low. The day-1 entry is structurally the wrong moment. |
| **`docs/analysis/delayed_entry_562_2026-08-22.md`** | **44 stopped-out magna53 episodes, minute bars, pre-registered** | **The load-bearing study.** Eight triggers priced. Only positive arm: **620 turn near the EP-day CLOSE, +0.21R (31/44 fire, 39% win)**. Everything else negative: EPL-UR −0.56 · 620@EPL −0.44 · 620@MA10 −0.40 · 620@PDH −0.34 · EPC-REC −0.06 · EPH-BRK −0.03 · 620-ANY +0.04. ⚠ **Its positive sum is TWO STILL-OPEN AUGUST MARKS (SMCI, TEAM); closed-only it is −3.74R.** Settles ~mid-September. |
| **`docs/analysis/pivot_proximity_2026-08-16.txt`** | **99 HIGH-tier EP alerts, 60 forward sessions** | 🔴 **THE TENSION AT THE HEART OF THE WHOLE LADDER, and it was sitting orphaned in a .txt until 2026-08-29.** Split by whether price ever came near the EP-day low: **TOUCHED** the pivot → median **+7.5**, only **43%** reach ≥8×ADR. **NEVER APPROACHED it** → median **+11.1**, and **66–83%** reach ≥8×ADR (rising with the window). **The strongest names never come back to the pivot at all.** So a pivot-touch requirement systematically selects the WEAKER half of the cohort, and the best outcomes are structurally *uncapturable* by any pivot-reclaim entry. ⚠ This does not kill the ladder — a delayed entry must reference *something*, and the names we MISS on day 1 may be a different mix — but any ladder result must be read against it, and the "never approached" group is a standing argument for a **breakout-side** delayed entry (buy strength) alongside the pullback-side one. |
| `docs/analysis/real_ep_retention_562b_2026-08-22.md` | — | Companion retention read. |
| **`docs/analysis/missed_ep_population_327_2026-08-29.md`** | **55 real EPs that got past us on day 1** | **The population the ladder was never measured on**, built because #562 only ever ran on names we ENTERED and were stopped out of. Causes: **top-20-by-gap cap 22** · old grading/score 7 · RVOL 3 · entry-blocked 3 · silent floors 3 · infra 3 · extension 3 · mcap 2 · M&A 1 · unknowable 4 · misc 4 · provisional 6. 🔑 **THE COHORTS DIFFER MATERIALLY, so #562's ranking does NOT transfer:** the ≥10R missed EPs gapped **8.7–11.1%** against the stopped cohort's **12.1–20.9%**, and the stopped 44 were **~93% tail-free**. We were stopped out of names that had no tail; we MISSED the ones that did. Also settles half the 620@EPC band: **SMCI closed +4.19R** (verified against the study's +5.45 mark), giving **+0.45R over n=30 settled — about zero per trade, median −1.00R** — through +8.18R with TEAM's open mark. **TEAM settles 09-08; no conclusion from the open mark.** ⚠ Its own stated weakness: the label is outcome-conditioned, so real EPs that FAILED are invisible to it. |
| `docs/design/delayed_entry_definitions_327_2026-08-29.md` | 237 EP names | Base and reclaim criteria. **Measured: a valid daily base forms for only 9 of 237 names (4%)** — 8 filled, 4 up / 4 down. **EP-low reclaim fires for 92 (39%)**, 46 volume-confirmed, of which 25 (54%) made a new post-EP high within 10 sessions. The depth rule alone killed 3,252 basing days — it is the binding constraint and may be too strict. ⚠ Otherwise it restated known methodology; the operator rejected it on that basis. |
| `docs/analysis/482_geometry_counterfactual_2026-08-29.md` | — | ⛔ **RETRACTED — do not cite.** Kept as the record of a population failure. |

### Open questions — what is genuinely NOT known

1. **The whole ladder has only ever been priced on names we ENTERED AND WERE STOPPED OUT OF.** Nothing measures the names we never touched — which is the operator's actual question. (Stage 1, in flight 2026-08-29.)
2. **620@EPC's sign is undetermined** until SMCI and TEAM settle (~mid-Sept).
3. **Confluence has never been an arm** — the MNTS two-fold shape, the original blueprint.
4. **Per-stock character has never been applied.** Every arm measured to date is the global rule the 06-11 ruling names as the anti-pattern; a −0.40R aggregate may be two populations averaged into mush.
5. **"Near" as behaviour has never been implemented** — every existing measurement used the `±0.5×ADR` proximity test the 08-29 ruling replaces.
6. **Nothing has been innovated beyond his list.** Candidate hypotheses (approach quality · the same-session spring · test-count decay · volume dry-up floor · higher-low sequence · relative strength on the pullback · gap-fill refusal · the P13 unpriced residual) are pre-registered in the plan and unmeasured.

### Where the work lives

`PLAN.md` **#327** is the active task. Related: **#270** (composition), **#562** (pivot ladder),
**#482** (geometry, retracted), **#354** (Family A merge). Plan of record:
`~/.claude/plans/crystalline-waddling-charm.md`.
⚠ **The long-wait variant converges into Family A** (`docs/decisions/0013-consolidation-plays-post-runup.md`) — 81% of ≥5R 20-day-reclaim names were already on the Family A detector. Short-wait (3–10 day) variants stay distinct.

---

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

> **⚠ GENERALIZATION IN PROGRESS (operator 2026-06-16) — the undercut is ONE shape, NOT the
> requirement.** The core signal is a *constructive tightening pullback*; the gap-low UNDERCUT is
> one way it tightens, alongside MA-pullback, range-low test, and low-volume rest (the 5
> entry-techniques, `user_tight_range_entry_techniques`). **Stage A (shipped 6/16, shadow):** a
> broad RECORDER persists the tightening telemetry + `pullback_shape`/`armed_shape`
> (`fresh_tightening`/`fresh_2bar_tr_pct`/`atr14_pct`, reusing `flag_detector._compute_fresh_tightening`
> + RMV) on EVERY post-thrust name — incl. watched names that tighten into an MA/rest WITHOUT
> undercutting the gap-low. The ARMED state/alert is UNCHANGED (still the narrow gap-low undercut)
> so the table above still holds. **Stage B (gated):** flip ARMED to fire on the generalized
> tightening gate — a DETECTION-CRITERION change, gated on the Stage-A recorded-cohort evidence
> (does broadening capture continuations the undercut-only gate misses, without flooding?) +
> operator sign-off on the criteria (HARD-gate rule) + CHANGE_PROCESS. #15 ("general-anticipation
> sister") folds into this generalized lane. (advisor 6/16: don't swap one un-calibrated hard gate
> for another — record broad, gate/alert narrow, certify nothing until the cohort gives the numbers.)

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

| harvest rule | med R | mean R | ex-top2 R | win% |
|---|---|---|---|---|
| **hold to 10d close** | **−1.00** | +1.64 | −0.19 | 27% |
| all-out at +1R | +1.00 | +0.45 | +0.36 | 73% |
| scale +1R / +3R (½/½) | **+2.00** | +0.78 | +0.59 | 53% |
| Pradeep two-phase (day-0 trail → hold survivors to d5) | +0.52 | +0.71 | +0.16 | **73%** |
| (perfect-foresight MFE ceiling) | +7.62 | +8.99 | +6.66 | 100% |

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
- **Pradeep TWO-PHASE exit tested (operator 2026-06-15, from his anticipation tweets):**
  day-0 aggressive intraday giveback-trail that activates ONLY once up ≥+1R ("protect profit
  if it gaps/breaks out fast") → hold the survivors to a day-5 time stop ("genuine breakouts
  don't fade"). Result: **median +0.52R, mean +0.71R, 73% win** — a high-win-rate, derisk-fast
  rule, but **NOT superior to the +1R/+3R scale here** (scale median +2.0 / mean +0.78). The
  per-name detail confirms the operator's hypothesis PARTIALLY: it **DOES capture tail the +3R
  cap throws away** — MXL **+5.8R** (vs scale +2.0), STRL **+2.8R** — the genuine multi-day
  runners it held. But the day-0 trail is double-edged: it **stops out dip-then-rip names early**
  (ASTI +0.4R despite a +35R MFE — trailed out on a day-0 dip, missed the run). Net = it trades
  the reliable +2R names for the occasional held runner → mean ≈ scale, median lower, win higher.
  **No free lunch: chasing the tail (two-phase) costs the reliable middle; the scale's guaranteed
  +2R median is robust.** N=15 in-sample; two-phase params (giveback 0.5/0.33, +1R activation, d5
  cap) tunable. (`_270_exit_replay.py` rules `twophase_g50`/`g33`.)
- **Catalyst-conditional leash — TESTED, but INCONCLUSIVE (confounded by UNSOURCED catalysts;
  operator caught it 2026-06-15).** First read said "refuted" (MXL ran +5.8 on a "routine"
  catalyst, TRT lost on "game_changer") — but checking the catalyst SOURCE invalidates that: the
  cohort's grades are mostly **historical-backfill PLACEHOLDERS** — MXL's "routine" catalyst text
  is literally `"Historical scan: 57.7% gap, 26.0x rvol"` (no catalyst sourced; `catalyst_type` /
  `fire_status` = None), ditto CNTA/TRT/ASTI; and 9/17 names carry no EP row at all. A 57.7% gap
  on 26× vol HAD a real catalyst — **we never found it** (an *unknown* catalyst, not a weak one).
  The ONE properly-sourced name — **STRL = "blowout Q1 earnings" (strong) → ran +2.8R** — is
  CONSISTENT with the leash. **So the leash is NOT refuted; it is UNTESTABLE on this cohort** until
  the catalysts are properly sourced. This gates it on the **#210/#211 catalyst-sourcing backbone**
  (direct primary sources, unknown-rate KPI) — and flags a DATA-QUALITY caveat on ALL
  catalyst-conditioned #270 analysis: the backfill cohort's grades are not real reads. The
  technical-breakout reading ("the breakout IS the catalyst", `user_flagbreak_universe_and_judging`)
  remains a plausible explanation but **can't be confirmed against unknown catalysts.**
  **EXIT CONCLUSION (sourcing-independent):** scale-out (+1R/+3R, median +2R) = robust PRIMARY
  shadow; two-phase = SECONDARY shadow (73% win, captures clean runners). The catalyst-leash =
  REOPEN + re-test once #210/#211 source the cohort properly (filed follow-up).

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
   **▶ DATA PROBE (2026-06-14, `scripts/_270_calibration_probe.py`, N=17, ILLUSTRATIVE —
   PENDING OPERATOR SIGN-OFF, not self-certified):** the **1.5× gate is NOT the problem** —
   every real trigger passes it on the true base, and the ratio magnitude does **not** predict
   outcome (HCAI 4/30 86× → +137% WINNER, but RLYB 104× → +8% dud). Tiny-denominator inflation
   only corrupts the ratio as a DISPLAY/ranking number. **RECOMMEND: floor `base` at 0.5×ADV20**
   (caps the displayed ratio at ~36×, drops zero triggers) + **keep the gate at 1.5×**. Cosmetic
   stability, no selectivity change — the knob is low-stakes.
2. **Trigger-volume floor** — thin trigger days slip through despite the $20M gap-day
   liquidity (SILO/KFRC/CAMP < 0.5M shares) → add a min absolute / dollar-volume floor on the
   trigger bar. **▶ DATA PROBE (2026-06-14, N=17, ILLUSTRATIVE — PENDING SIGN-OFF): the cohort
   REFUTES a trigger-bar floor.** The two thinnest $-vol names TIE at $2M with OPPOSITE outcomes
   — CAMP +6% (dud) vs **SILO +37% (WINNER)** — so no $-floor separates them; the gentlest
   meaningful floor ($5M) sacrifices SILO, and $20M also drops ASTI (+83%). Same by shares (SILO
   0.27M/+37%). The **$20M gap-day liquidity SEED (the WATCHED gate) already ensures the NAME is
   liquid**; a thin trigger BAR does not predict failure here. **RECOMMEND: NO trigger-bar floor**
   — the seed suffices; revisit only if a larger cohort shows thin-trigger failures.

   **♻ RE-VALIDATION REGISTERED (operator 6/14 — don't let an N=17 finding silently go stale):**
   both knob conclusions are wired into the recurring reviews — `data_gated_reviews.yaml::delayed_ep_270_calibration_revalidation`
   (N≥30 deep tune/confirm; THE re-test = does the SILO-class thin WINNER hold or do thin triggers
   now fail?) + a cross-ref eyeball in the N≥5 graduation peek, and `_270_calibration_probe.py`
   joins the Monthly backward-check sweep when live data flows. Tuning a threshold = CHANGE_PROCESS
   + N≥30 + sign-off; the review re-bumps each cycle (recurring, not one-shot).
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
- **2026-06-16 — GENERALIZATION Stage A (tightening recorder), operator: "undercut is one shape
  not necessary".** The lifecycle was U&R-overfit (ARMED hard-gated on the gap-low undercut, so
  coil→breakout / MA-pullback / low-vol-rest could never arm). Stage A ships a BROAD shadow
  RECORDER: `anticipation.tightening_telemetry` (+ `detect_pullback_shape`, the daily-bar EOD
  analog of `flag_detector.compute_entry_technique_annotations` which is snapshot-bound) persists
  `pullback_shape`/`pullback_shapes`/`armed_shape`/`fresh_tightening`/`fresh_2bar_tr_pct`/`atr14_pct`
  on every post-thrust row — reusing `_compute_fresh_tightening` + RMV (search-before-build;
  volume-extended adapter `bars_to_ft_rows`, equality-pinned in `test_anticipation_tightening.py`).
  The ARMED state machine + alert are UNCHANGED (narrow gap-low undercut) — the recorder gates
  NOTHING; its cohort is the calibration set for the gated Stage B (generalize the ARMED gate;
  CHANGE_PROCESS + sign-off). `replay()` stays frozen (golden test intact). Shadow; gate-free.
  TODO: slot the operator's exact "bar % range" formula (from the 6/15 tweet) into the recorder
  alongside `atr14_pct`/`fresh_2bar_tr_pct` (pluggable placeholder until confirmed).

---

## 2026-08-16 — THE ENTRY ARCHITECTURE (operator) — a PIVOT LADDER plus an intraday trigger

> *"we need proper buy points and we need to define it ahead of time. EP day low and EP close are two
> that i'm familiar with. We can have multiple entry pivots as long as we clearly know how we enter
> and exit and any one of them can trigger and work. This also couples with finer grain entries like
> looking at the 620 chart intraday when it's near one of those pivots — for example, when it is
> closing in on the EP day low we switch to looking at intraday chart for an entry even if it doesn't
> touch the EP low, there may be a 620 turn near it. The main thing is there's no rigid hard rule
> here, but we have tactics and tools to help us get into EP with proper risk management."*

**This is the entry model for the whole delayed-EP family. Three parts, and the third is the one we
did not have:**

1. **A PIVOT LADDER, defined in advance.** Named price levels fixed at the EP event, not chosen
   later: **EP-day LOW · EP-day CLOSE · EP-day HIGH / ORB high · prior-day high · the reclaim levels
   · the 10-day MA.** Multiple pivots are fine and expected — **any one may trigger.**
2. **Each pivot carries its OWN entry and stop, stated up front** (CLAUDE.md SETUP vs FAMILY: no buy
   point + no stop = not a setup). A pivot without a stop is not on the ladder.
3. 🔴 **PROXIMITY, NOT TOUCH — the part that was missing.** When price *approaches* a pivot, we
   switch to the intraday chart (the **620**, his 08-07 share) and take a turn **near** it. **The
   pivot does not have to be touched.** A hard limit at the pivot is the wrong instrument: it is a
   rigid rule where he explicitly wants a zone plus a trigger.

**⚠ The INTC 2026-04-24 case shows exactly why this matters** (plan §2026-08-16): a limit at the
EP-day low of **$79.62 NEVER FILLED** — the stock bottomed at **$80.80**, about **1.5% above the
pivot**, and then ran to $130.57. A limit missed a +14R name by a percent and a half. **Under the
proximity model, $80.80 is an approach to the pivot and the 620 turn is the entry.** The EP-day
CLOSE pivot at $82.54 DID fill (04-28) and returned **+9.18R** — which is the same lesson from the
other side: more pivots on the ladder = more ways to be in the trade.

### What this makes measurable, and it is the next step

**"Approached but never touched" is currently invisible to every test we have run**, because every
entry rule modelled so far requires a touch. **Size it:** over the delayed-EP cohort, how often does
price come within a defined band of a pivot (say 0.25–0.5×ADR) WITHOUT tagging it, and what did
those names go on to do? **That number is the value of the proximity model over a hard limit** — and
it cannot be recovered from any existing result.

⚠ **The 620 trigger itself needs the intraday bars**, which we now persist for alert ticker-days
(#567, 08-15) but NOT for arbitrary later dates. A proximity+620 backtest needs a targeted minute
pull for the approach days — cheap, but it is a prerequisite, not a given.

🛑 Buy points and stops are entry discipline = THE LINE. This records the ARCHITECTURE he specified;
no rule is proposed or changed.

---

## 2026-08-16 — THE EP-DAY LOW IS AN INVALIDATION LINE (operator), and the data is emphatic

> *"shallower pull back means stronger — that is why EP low is the lowest pivot. If it drops below
> and can't reclaim, the EP failed. It may setup some other time or a different setup, but for a real
> EP it has failed, or shown weakness and not strength after EP."*

Tested directly on 99 HIGH-tier names with 60 forward sessions (60-day max excursion, ADR units):

| | n | median MFE/ADR | **≥8×ADR** | **≥15×ADR** |
|---|---|---|---|---|
| **never breached the EP-day low** | 16 | **10.5×** | **68.8%** | **25.0%** |
| breached, RECLAIMED within a week | 67 | 5.2× | 25.4% | 1.5% |
| breached, NEVER reclaimed | 16 | 4.3× | 18.8% | 6.2% |

### ✅ His framing holds, with ONE refinement the data insists on

- **Never giving back the EP-day low is the dominant signal on the board.** 68.8% reach ≥8×ADR
  against ~20–25% for anything that breaches, and **25% reach ≥15×ADR against 1.5% / 6.2%** — a
  sixteen-fold difference at the far tail.
- 🔴 **The refinement: the BREACH is the damage, not the failure to reclaim.** Breached-and-reclaimed
  (25.4% ≥8×ADR) is only marginally better than breached-and-never-reclaimed (18.8%), and at the far
  tail reclaiming is actually *worse* (1.5% vs 6.2%, on 67 vs 16 names). **A reclaim does not restore
  the name to strength** — it makes it an ordinary candidate, not a strong one.
- 📌 **So "the EP failed" is right, and it fails at the breach.** The reclaim buys a tradeable setup
  (that is what T1 measures) but not the original thesis.

### How this is usable — a MANAGEMENT signal, not an entry filter

The classification is only knowable AFTER the fact, so it cannot rank alerts on the morning. **What
it can do is grade a position you already hold:** once price breaches the EP-day low, the expected
tail collapses by roughly two-thirds and the ≥15×ADR case all but disappears. That is a
size/conviction input, and it is computable from daily bars with no new capture.

⚠ n=16 in each of the two extreme buckets; one regime (April–May); max excursion, not realized R.
🛑 Position sizing and management are entry/exit discipline = THE LINE. Measurement only.
