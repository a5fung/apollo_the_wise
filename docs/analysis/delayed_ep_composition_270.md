# #270 — delayed-EP re-entry composition: step 1 (logic validated vs MNTS)

**Status: STEP 1 DONE 2026-06-14 — the composition state machine reproduces the known
MNTS lifecycle (gate-free replay). Calibration (cohort) + the deployable shadow
detector are next; the detector is GATED (see "Gate").**

## What #270 is

Per the MNTS case study (`docs/analysis/mnts_delayed_ep_case_study_2026-06-11.md`) +
`memory:user-delayed-ep-reentry-template`: the fragments already fire (EP gap, flag
WATCH, 9M pings) but nothing ASSEMBLES them. #270 is the missing **composition state
machine** for a tiny-cap delayed-EP re-entry, from daily bars:

```
WATCHED   gap day: close >= (1+GAP)*prev_close, close > SMA200, vol >= VOLX*ADV20.
          Records gap_day_low (the U&R reference) + gap_day_vol.
ARMED     within ARM_WINDOW days: low < gap_day_low (UNDERCUT of the gap-day low —
          the exact event the flag detector wrongly INVALIDATES on), vol < burst.
TRIGGERED after armed: close > gap_day_low AND close > SMA20 (reclaim BOTH refs) AND
          vol > EXPANSION * avg(pullback vol) (the explosive R-leg volume signature).
```

The undercut-is-the-arming-event (not invalidation) is the irony at the heart of #270:
the flag-rule universe and the delayed-EP universe need separate state tracks.

## Step 1 — replay validated vs MNTS (gate-free)

`scripts/_270_delayed_ep_replay.py` runs the state machine over a pulled daily-bar
snapshot. Against MNTS (2025-05..2026-06):

```
2026-05-26  WATCHED   gap +110% close 15.48 > SMA200 12.51; vol 79.8M = 12.7x ADV20; gap_day_low=11.86
2026-06-08  ARMED     UNDERCUT gap_day_low 11.86: low 11.80; vol 6.5M < burst 80M (contraction)
2026-06-11  TRIGGERED RECLAIM close 16.30 > gap_day_low 11.86 & > SMA20 12.12 & > EMA21; vol 21.4M = 2.1x pullback-avg
RESULT: PASS — reproduces WATCHED 5/26 / ARMED 6/08 / TRIGGERED 6/11 (the +43% day).
```

This proves the composition LOGIC reproduces the known case. It is N=1 validation of
the logic — NOT a calibration verdict (single-case; the methodology anti-overfit rule
applies). Reproduce:
```bash
ssh apollo@<box> 'docker exec apollo-postgres psql -U apollo -d apollo -tAF "\t" \
  -c "SELECT trade_date,open_price,high_price,low_price,close,volume FROM mi_daily_closes \
      WHERE ticker='"'"'MNTS'"'"' ORDER BY trade_date;"' > scripts/_270_bars_mnts.tsv
python scripts/_270_delayed_ep_replay.py
```

## Thresholds (TEMPLATE-grounded defaults — OPERATOR to calibrate, not self-certified)

| Param | Default | MNTS actual | Note |
|---|---|---|---|
| GAP | +40% | +110% | gap-day close vs prior close |
| VOLX | 3x ADV20 | 12.7x | mirrors the 9M 3x-ADV gate |
| ARM_WINDOW | 15d | undercut 9d after gap | undercut must land within window |
| EXPANSION | 1.5x pullback-avg vol | 2.1x | the R-leg volume signature |

Reclaim requires close > BOTH gap_day_low AND SMA20 (the two-fold U&R); EMA21 is
reported as confirmation. Universe deliberately INCLUDES sub-$500M (the live scanner's
`mcap_too_small` floor is kept for auto-trading, dropped for this watch/observe lane).

## Step 2 — cohort calibration (2026-06-14, gate-free)

Cohort SEEDED FROM PRICE ACTION (not the live scanner — that's the point; its
`mcap_too_small` floor excluded MNTS): huge-gap fast-runner days, 2026-03-01..05-15
(window leaves room for the lifecycle to complete by mid-June). Seed SQL =
`mi_daily_closes` where close ≥ 1.4·prev_close AND vol ≥ 3·ADV20 AND close ≥ $5 AND
prev_close ≥ $2 AND vol·close ≥ $20M → 134 distinct tickers. Replay run per ticker:
`scripts/_270_cohort_run.py` (imports the validated `replay()`).

**Funnel:** WATCHED 62 → ARMED 30 (48% of watched) → TRIGGERED 16 (26% of watched,
17 events). 72 of 134 seed names failed WATCHED (gapped below their 200d MA — correctly
filtered). **The lifecycle completes on only 26% of huge-gap names = SELECTIVE**, the
right shape for a rare setup (not noisy).

**Forward outcome (MFE over next 10 trading days, N=17 trigger events):** median
**+8%**, **≥+20% MFE on 5/17 (29%)**, best **+137%** (HCAI), then ASTI +83%, MXL +54%,
TRT +52%. The fat right tail the template is about IS present. BUT the 10-day *close*
returns are weak/negative (HCAI +137% MFE → −41% close; SILO +37% → −13%) →
**empirically confirms the template's "tiny-cap fast runners must DERISK FASTER"
nuance**: the edge is in the excursion, harvested with early partials, NOT buy-and-hold.
That is a management/exit finding (W3 exits / P3 management-judge), not a detector flaw.
MFE is favorable-excursion, NOT realized P&L (no exit rule applied) — read it as "did
the reclaim run," not "what you'd have made."

**Calibration knobs surfaced (for OPERATOR — not self-applied):**
1. EXPANSION ratio is UNSTABLE on near-zero pullback baselines (HCAI 86×, RLYB 104×
   are artifacts of a tiny denominator) → floor the pullback-avg volume or cap the ratio.
2. Thin TRIGGER days slip through despite the $20M gap-day liquidity (SILO/KFRC/CAMP
   < 0.5M shares) → add a min absolute volume / dollar-volume floor on the trigger bar.
3. GAP +40% / VOLX 3× / ARM 15d are reasonable starting points (the funnel is
   selective); the operator decides whether to tighten for fewer/higher-quality flags.

Reproduce: the two seed queries are in `_270_cohort_*.tsv` headers / this doc; then
`python scripts/_270_cohort_run.py`.

## REFRAME (operator 2026-06-14): this is ONE e2e trade tactic, not a detector

`memory:user-sip-setup-is-one-e2e-tactic`. "READY/TRIGGERED" from the daily state
machine means the name is SET UP — it is **NOT the entry**. The full tactic = three
layers, scoped + built as ONE unit (not fragments):

1. **Readiness** (daily) — WATCHED → ARMED → READY. = #270 steps 1-2 (DONE). The daily
   reclaim is the *confirmation* of readiness, known at EOD.
2. **ENTRY** (intraday, TO TUNE) — once a name is ARMED/READY it goes on an intraday
   entry-watch; the actual fill comes from a **tuned intraday entry tactic** (first-
   minute high/low HELD — the MNTS confirmation — / ORB above the reclaimed gap-day-low
   / volume-confirmed U&R, from `memory:user-tight-range-entry-techniques`). Entry is
   **as important as the exit** and is the layer that actually gets you in — the daily
   state does not. NEEDS CALIBRATION against the cohort (which intraday trigger, what
   first-N-minute hold, volume confirm).
3. **EXIT / harvest** (= W3 exits / P3 management-judge) — derisk FASTER. The cohort
   proved why: fat MFE (best +137%) but weak close-returns → the edge is only realized
   with early partials. **Paired with #270 as one workstream, not separate.**

### Surfacing (operator question 6/14: "will I be alerted for ready stocks?")

YES, and deliberately — a READY/ARMED transition is RARE (~16 in 3.5 months ≈ 1/week
in the cohort) and actionable, so it is NOT the #168 per-tick-noise class
(`memory:feedback_alert_vs_audit` — Telegram = terminal/actionable events). Design:
- **ARMED (EOD)** → name joins the intraday entry-watch; surfaced in a `/`-board
  (current watched/armed/ready) + the EOD digest.
- **ENTRY (intraday)** → the tuned entry tactic fires live → a real-time alert with the
  structural stop (the reclaimed gap-day-low) + the harvest-fast note.
- Shadow = informational (operator acts); graduates to an actionable/auto candidate only
  after forward-outcome data + the exit layer exist (the #168 actionability gate).

## Step 2c — ANTICIPATION entry (Pradeep's third entry mode, 2026-06-14, gate-free)

Operator (6/14, reading Pradeep): a third entry — **anticipation**. Enter at the **CLOSE of a
quiet, tight, low-volume day when the name has reclaimed the pivot and is COILED** ("set up /
nearing ready, tightening"), betting the breakout comes next day. Two payoffs: (1) you're in
BELOW any gap-up = capture the bulk; (2) the coiled-day low is the stop = you know fast if it
failed. `scripts/_270_anticipation_replay.py` (daily-bar replay + the pulled minute bars).

**COILED day (forward-computable, no lookahead)** = the trigger conditions MINUS the volume
burst: close > gap_day_low AND > SMA20 (reclaimed both refs) + tight range (≤7%) + quiet vol
(≤1× ADV20). By construction it lands pre-breakout, never "the day before the known trigger".

**The model is STOP-AND-REENTER, not one-shot** (advisor-flagged strawman): a tight coiled-low
stop entered before the breakout gets shaken in a still-consolidating name almost every time —
**one-shot = −1.0R median (it always fails)**. Pradeep RE-ENTERS while the setup is intact: each
shake is a small ~2% (−1R) loss, the eventual hold-into-breakout is a tight-stop = big-R capture.
**Re-entry discipline is LOAD-BEARING** — without it anticipation is negative.

**Findings (cohort, daily bars):**
- **FIRE:** 11 of 30 ARMED names presented a distinct coiled day (37%); 8 later triggered, 3
  never did (the false set). The WINNING coiled entry lands a median **7d before the breakout**.
  The other ~63% (incl. fast MNTS-style undercut→trigger runs) have NO coiled day → anticipation
  is **complementary**: anticipate when a coiled day forms, else use confirmation (FIRST5).
- **Claim #1 (capture the gap) — CONFIRMED:** anticipation enters a median **6% below the
  FIRST5 price = 25% of the whole run to the window high captured earlier** (N=4 w/ minute bars).
- **Claim #2 (fail fast/small) — CONFIRMED:** shaken attempts lose a median **2%** (the coiled
  stop), small and fast by design.
- **Expectancy (triggered, N=8), stop-and-reenter:** median **+3.3R**, mean **+2.9R**/name
  **(MFE ceiling — win leg credited full favorable excursion)**, **62% eventually caught** the
  breakout (avg 1.9 attempts/name). vs one-shot −1.0R. **REALIZED (Layer-3 harvest, advisor 6/14,
  full N=8 triggered cohort): the win leg run through the same exit rules nets median ≈ 0R
  (all-out +1R AND scale +1R/+3R; −1R on ½-trail), mean negative** — the −1R shake costs eat every
  harvest rule. So the +3.3R is a perfect-foresight upper bound (~3× the harvested expectancy), and
  realized this is **below FIRST5's matched-rule realized (+1R all-out, +2R scale).**
- **Parity vs FIRST5 (won names, endpoint-symmetric MFE) is MATURITY-DEPENDENT — re-based at each
  setting (advisor 6/14: do NOT compare a maturity number to a min_base=1 FIRST5).** At the LOOSE
  setting (min_base=1, this section) FIRST5 **7.6R** edges anticipation **6.5R** — anticipation's
  loose-coil stop is wider (5% vs 2%). **At the MATURE setting it flips** (see maturity section): a
  tight mature coil drops anticipation's stop to 2% (= FIRST5) while keeping the lower/earlier entry
  → anticipation **15.0R** vs FIRST5 7.6R. So whether anticipation wins on R **depends on coil
  maturity** (it needs the tight mature coil to match confirmation's stop). N=4, in-sample,
  outlier-influenced → illustrative DIRECTION (maturity tightens the stop → lifts anticipation's R),
  NOT a clean beats/loses verdict. Its horizon-free edge stays the lower entry PRICE (price-capture
  above). (NOT comparable to the intraday 3.5R — re-based horizon.)
- **Full cohort (all 11, incl. the false set):** mean **+1.7R**/name, total +19R, caught 45%.

**MATURITY GATE (operator 6/14: "wait for the coil to mature — this is where chart-reading helps").**
The loose model entered the FIRST coiled day — immature; the *winning* entry was a median 7d
later. Added a maturity gate: require a **≥N-day developed base** (held above the pivot in a
contained range) before the coiled entry qualifies. Sweep (the daily timing, an EOD signal —
WHEN to anticipate, the operator's exact question):

| min_base | fired | caught | entry d-before | attempts/nm | trig meanR | full meanR | top% | ex-top meanR |
|---|---|---|---|---|---|---|---|---|
| 1 (loose, first coiled) | 11 | 5 | 7 | 1.7 | +2.9 | +1.7 | 73% | +0.5 |
| 2 | 9 | 5 | 7 | 1.7 | +4.3 | +3.0 | 52% | +1.6 |
| **3 (mature)** | **8** | **5** | **5** | **1.2** | **+9.6** | **+7.0** | **40%** | **+4.8** |
| 4 (over-tight) | 8 | 4 | 2 | 1.4 | +5.9 | +4.2 | 69% | +1.5 |

**The REAL evidence is WINNER-RETENTION, not the mean-R magnitudes** (advisor 6/14). Raising
min_base shrinks the qualifying set to a subset and drops losers first, so mean-R rises **partly
MECHANICALLY** (smaller denominator + losers excluded) — the +1.7→+7.0R full-mean is in-sample and
leveraged (the top name's own R ~doubled 13.9→~22R purely from the tighter mature stop). The
genuine signal is the **ASYMMETRY: `caught` holds at 5 while `fired` falls 11→8 across min_base
1→3** (winners survive the gate, losers are dropped), and only at min_base=4 does a winner clip. A
purely mechanical filter would drop winners proportionally; this gate **keeps every winner through
~3** — that asymmetry, with the clip at 4, is what marks ≈3 as the edge/ceiling (NOT the monotonic
mean-R, which is mostly selection arithmetic). Maturity also lands entries closer to the breakout
(7→5d), needs fewer attempts (1.7→1.2), and cuts outlier reliance (top 73%→40%). **It de-risks the
outlier problem WITHOUT a second time window** — which matters because the data can't supply one
(see below). DISCIPLINE: ≈3 is selected in-sample on N=8 → the DIRECTION (require maturity) is the
robust finding; the threshold + the R magnitudes are illustrative, re-validate on fresh data.

**CHART-VISION integration (#267, operator 6/14: "we have an item to implement chart-reading, it
should integrate with this").** Coil maturity is fundamentally a VISUAL judgment ("developed / at
the apex / ready" vs "still loose") — exactly what **#267** builds: a **point-in-time matplotlib
renderer from `mi_daily_closes`** (no lookahead — bars only up to the decision day) + a VLM
**chart-structure axis** in `grade_holistic`. The integration: **build #267's renderer as SHARED
infra with TWO consumers** (the EP grade judge AND this anticipation maturity read), not judge-only.
Then `base_run ≥ N` is the cheap EOD **pre-filter** (narrow ARMED names to mature-ish coils) and
#267's chart-vision is the **richer read** on each surfaced candidate (the codification of the
operator's chart-read; advisory first → can graduate to a maturity score). NOTE: today's
`charts.py` is a Finviz *live-mosaic* fetcher = lookahead-unsafe → unusable for point-in-time
maturity; #267's `mi_daily_closes` renderer is the right tool (same no-lookahead discipline as this
replay). #270 anticipation should be wired in #267's scope (Wed 6/17 build) as the 2nd consumer.

**CAVEATS (this is ILLUSTRATIVE, not a ship verdict):**
0. **Second time-window is DATA-BLOCKED** — `mi_daily_closes` starts 2025-05-12; the SMA200 gate
   needs ~200 trading days of lookback, so the earliest valid gap window (~late-Feb 2026) overlaps
   the first. A true multi-window re-validation needs more history backfilled (gated follow-up).
   The maturity sweep is the in-window robustness substitute.
1. **N is small** — 8 triggered, 4 with minute bars for price-capture, one ~3.5-month window.
2. **Outlier-leveraged at the loose setting** (the W2 skip-wide-open lesson, applied): the single
   best name (RLMD +13.9R) = **73% of the total** at min_base=1. Ex-top still +0.5R/name (survives
   removal, unlike the W2 study that went median −1R). **The maturity gate above materially
   mitigates this** (top share 40%, ex-top +4.8R at min_base=3) — but on the same N=8, so it is
   not independent confirmation; a multi-window cohort is still owed before trusting the magnitude.
3. **MFE ceilings, not harvested R — and the symmetry does NOT survive harvest (advisor 6/14,
   MEASURED).** The first cut argued the MFE comparison "holds because it's symmetric across all
   three entries." Running anticipation's win leg through the actual Layer-3 exit harness (full N=8
   triggered cohort) disproves that: anticipation's +3.3R MFE collapses to **realized median ≈ 0R
   (all-out and scale; −1R ½-trail), mean negative** (the −1R shake costs are realized but the win
   leg no longer gets full MFE), landing it **below FIRST5's matched-rule realized (+1R all-out,
   +2R scale) — harvested, FIRST5 edges it on every rule.** The MFE numbers (6.5/7.6/15.0R) rank
   entry timing/price ONLY; the realized harness is the load-bearing comparison and it shows **no
   realized-R edge** for anticipation — its case is price-capture + complementarity. (Cohort caveat:
   FIRST5 N=15 day-0-minute single-entry no-shakes vs anticipation N=8 daily with re-entry shakes →
   directional, not strictly head-to-head; a same-N/same-resolution parity harvest is the
   truly-clean version, deferred as disproportionate for a gate-free/shadow-first read.)

**Verdict:** anticipation is a real, positive-expectancy THIRD entry mode that validates both of
Pradeep's claims — **conditional on re-entry discipline**. **Realized (harvested, full N=8
triggered cohort) it nets median ≈ 0R (all-out and scale +1R/+3R; −1R on ½-trail), mean negative —
below FIRST5's matched-rule realized (+1R all-out, +2R scale), NOT the +2.9–15R the MFE ceilings
implied** (those rank entry timing/price only). So there is **no realized-R basis to prefer
anticipation over confirmation — harvested, FIRST5 edges it**; the maturity-dependent MFE flip
(loose FIRST5 7.6 vs 6.5; mature anticipation 15.0 vs 7.6 — N=4, MFE, do not over-read) is an
entry-price/stop-tightness story, not a harvested-edge story. Anticipation's real, defensible
edge is the **lower / earlier entry** — positioned BELOW the gap instead of chasing
the first-5 high, exactly Pradeep's "capture the bulk on a gap up". And it does NOT replace
confirmation (fast runners don't coil). So the entry layer is **complementary**:
anticipation-on-a-MATURE-coil (≥3-day base, re-enter on a shake) + FIRST5-BREAK confirmation (fast
runners) + GDL-RECLAIM fallback. **WHEN to anticipate = on a mature coil, not the first quiet day**
— the maturity gate is the quantitative proxy for the chart-read the operator described; the
deployable surfaces ARMED names + their coil maturity (day-N of base) and the operator does the
final chart-read (Pradeep uses discretion too — the gate narrows the candidates, the human
confirms). OPERATOR decisions: include anticipation in the step-3 deployable; the maturity
threshold (≈3, illustrative); and how many windows to re-validate the magnitude before sizing.

## Sequencing (the e2e tactic)

- ✅ Step 1 — readiness composition, validated vs MNTS. Gate-free.
- ✅ Step 2 — cohort calibration: selective funnel + fat-MFE tail + knobs. Gate-free.
- ✅ Step 2b — **intraday ENTRY tuning DONE** (2026-06-14, gate-free, `scripts/_270_entry_replay.py`
  on Polygon minute bars for the 17 triggers + MNTS). Two template-aligned entries replayed
  per trigger day:
  - **FIRST5-BREAK** (break above the first-5-min high; stop = first-5-min low): fills
    15/18, **median stop 3%**, median MFE +12%, **median 3.5R**. = the MNTS "first-minute
    high/low HELD" entry (MNTS 9.6R).
  - **GDL-RECLAIM** (reclaim the gap-day-low; stop = gap-day-low): fills 18/18, median stop
    10%, median MFE +12%, median 1.4R.
  - **VERDICT:** same MFE, but FIRST5-BREAK delivers **2.5× the R** purely on the tighter
    stop (3% vs 10%) — the U&R-paradox "tightest stop + biggest cushion" confirmed
    empirically. **Tuned entry = FIRST5-BREAK primary + GDL-RECLAIM fallback** (the 3 names
    where the 5-min break never cleared the gap-day-low) → tight stops with full coverage.
  - `mi_intraday_bars` was too sparse (scattered single days, 8/16 names absent) → pulled
    from Polygon (the existing provider); the deployable tactic uses the live bar stream.
- ✅ Step 2c — **ANTICIPATION entry (third mode) evaluated** (2026-06-14, gate-free,
  `scripts/_270_anticipation_replay.py`). Pradeep's EOD entry on a COILED day (pre-breakout).
  Stop-and-reenter (the faithful model — one-shot is a strawman) = **+2.9R mean/name MFE on
  triggered, 62% caught**; **REALIZED through the Layer-3 harness (full N=8) = median ≈ 0R
  (all-out and scale; −1R ½-trail), mean negative — below FIRST5's matched-rule realized (+1R/+2R):
  no realized-R edge, FIRST5 edges it** (advisor 6/14; the +2.9–15R figures are MFE ceilings,
  anticipation's edge is the lower/earlier entry PRICE + complementarity). Validates both his
  claims (25% earlier capture, 2% fast-fail). ILLUSTRATIVE
  not ship: N=8, outlier-leveraged (RLMD = 73% of total, survives ex-top at +0.5R/name). Re-entry
  discipline LOAD-BEARING. Complementary (only ~37% of armed names coil). Full writeup ↑ "Step 2c".
- ⏸ Step 3 — deployable SHADOW tactic = readiness state table + scheduler job +
  intraday entry-watch + `/`-board + alerts. GATED post-#277 (new job + CREATE TABLE run
  in COMBINED = §C rollback target). Branch + staging-validate, merge post-gate.
- ✅ Step 2d — **EXIT/harvest BACKTESTED** (2026-06-14, gate-free, `scripts/_270_exit_replay.py`).
  FIRST5 entry held constant, realized R under a speed spectrum (advisor methodology:
  median+ex-top2, intrabar opt/pess bracket, day-0 minute / day-1+ daily, gap-through stops),
  N=15. **Buy-and-hold loses the median name (−1R/27% win — its +1.6R mean is the HCAI/ASTI
  outlier artifact) → derisk-fast is EMPIRICALLY NECESSARY.** Harvest is a SAME-DAY event —
  now **MEASURED** (advisor 6/14, not just inferred from opt==pess): the fill-day distribution
  shows **all-out banks 93% of position on the trigger day (day0), scale +1R/+3R banks 87%**.
  Scale-out +1R/+3R beats single-target in-sample (median +2R vs +1R).
  +137% tail is NOT systematically harvestable (any held runner bleeds the median). Rule =
  scale out fast into the trigger-day spike; magnitudes illustrative (N=15, one window) →
  operator decision #5, shadow-first. Full evidence: SSoT `delayed_ep_reentry.md` Layer 3.
- ⏸ Paired — W3 EXIT/harvest DEPLOYABLE (the backtested ladder, shadow-first) — built WITH step 3.

## Step 3 build spec (TURNKEY — execute post-#277-gate, mechanical not design)

Everything below is decided; the post-gate build is wiring, not design. All of it runs in
`combined` (new job + CREATE TABLE) → GATED. Build on a branch, staging-validate, merge after
the Monday gate closes.

**1. State table** `mi_delayed_ep_lifecycle` (add to `db.py::initialize_schema()`):
`ticker TEXT, gap_day DATE, gap_day_low NUMERIC, gap_day_vol BIGINT, sma200_at_gap NUMERIC,`
`state TEXT (watched|armed|coiled|ready|triggered|expired), armed_date DATE, coiled_date DATE,`
`ready_date DATE, triggered_date DATE, entry_tactic TEXT (anticipation|first5_break|gdl_reclaim),`
`entry_price NUMERIC, stop_price NUMERIC, reenter_count INT, fwd_mfe_pct NUMERIC,`
`realized_r NUMERIC, last_eval DATE, created_at/updated_at TIMESTAMPTZ.` PK `(ticker, gap_day)`.
Mirrors the replay() event fields 1:1 — no new logic. `coiled`/`reenter_count` carry the
anticipation path (step 2c). **`realized_r` = the HARVESTED R (Layer-3 rules: derisk-fast
+1R/+3R ladder, stop-fills), NOT MFE** — `fwd_mfe_pct` is the upper bound only. If a single
column can't capture it, store the exit-fill/forward-bar data needed to DERIVE realized R offline.
**↳ GRADUATION/CALIBRATION TRIGGER — REALIZED R, not MFE (do at table-ship, advisor 6/14):** the
`delayed_ep_270_shadow_graduation` + `delayed_ep_270_calibration_revalidation` entries auto-surface
in the Sunday digest. ⚠ **Their actions compare REALIZED R** (this whole tactic's lesson is
MFE ≠ realized R) — but the seed predicates count `fwd_mfe_pct IS NOT NULL` (MFE-settled) because
the table is unbuilt. **At table-ship: (1) ensure `realized_r` is captured or derivable, NOT just
`fwd_mfe_pct`; (2) REPOINT the predicates to `realized_r IS NOT NULL`** so the trigger fires only
when the number the review actually needs exists. Verify column names match too — until verified
the predicate errors silently = not-ready, so a mismatch means the trigger never fires. (Leaving
the predicate on `fwd_mfe_pct` would recreate, inside the deployable, the exact MFE-vs-realized
gap this session closed.)
**↳ CALIBRATION RE-VALIDATION (operator 6/14 — "include these findings in the regular reviews"):**
the two calibration knobs (EXPANSION floor + trigger-volume floor) were set on N=17 illustrative.
Two recurring-review hooks are registered: (1) `data_gated_reviews.yaml::delayed_ep_270_calibration_revalidation`
(N≥30, deep tune/confirm — does the SILO-class thin WINNER hold, or do thin triggers now fail?) +
a cross-ref in the N≥5 graduation peek; (2) **at table-ship, ALSO wire `_270_calibration_probe.py`
(adapted to live data) into the Monthly backward-check sweep** (the `#50/#53/#54/#77` family, ~Monthly
1st 8 AM ET) so the conclusion is re-confirmed between data-gated surfacings — the methodology-
revalidation discipline (memory `feedback_methodology_insights_need_periodic_revalidation`).

**2. Daily readiness job** `_delayed_ep_readiness_job` (APScheduler, ~17:35 ET, mon-fri — AFTER
the 17:00 data pull lands `mi_daily_closes`). Lift the validated `replay()` from
`scripts/_270_delayed_ep_replay.py` into a real module (`agents/market_intelligence/
delayed_ep.py`). Per run: (a) seed new WATCHED from today's daily closes using the cohort seed
predicate (close ≥ 1.4·prev_close ∧ vol ≥ 3·ADV20 ∧ close ≥ $5 ∧ vol·close ≥ $20M); (b)
re-eval every open (non-expired) lifecycle row for ARMED/READY/EXPIRED transitions; (c) UPSERT.
On a NEW ARMED → Telegram (rare, ~1/wk) + add to the intraday watch set. Apply the two operator
decisions from the SSoT (EXPANSION pullback-vol floor; trigger-bar dollar-vol floor) HERE. Also
(d) flag a **MATURE COILED** day (reclaimed gap_day_low & SMA20 + tight + quiet, no expansion,
AND a ≥3-day developed base — `base_run`) → the EOD **anticipation** entry candidate (step 2c);
emit the anticipation alert with stop = coiled low + the coil-maturity (day-N of base) for the
operator's chart-read + the re-enter-on-shake note (re-entry discipline is load-bearing — see 2c).

**3. Entry-watch — TWO paths (anticipation is complementary, not a replacement):**
 - **ANTICIPATION (EOD, on a MATURE coil — ≥3-day base):** entry = coiled close, stop = coiled
   low; re-enter at the next mature coil if shaken (track `reenter_count`). Surface the coil
   maturity (day-N of base) for the operator's chart-read. Surfaced by the daily job (no intraday
   stream needed for the signal itself).
 - **CONFIRMATION (intraday, the fast runners that never coil):** reuse the existing flag-break
   scan harness (9:35–15:55 ET / 5 min, mon-fri) — **FIRST5-BREAK primary** (break above
   first-5-min high, stop = first-5-min low) then **GDL-RECLAIM fallback** on live bars.
 - On fire → set `triggered` + entry_tactic/entry/stop, emit the entry alert. **The intraday path
   is execution-adjacent (reads the live bar stream); in the split it lives on EXECUTION or calls
   back via the facade. Wire BOTH as SHADOW first (alert only, no submit).**

**4. Alerts** (`feedback_alert_vs_audit` — terminal/actionable only): ARMED (EOD) → board +
EOD digest; ENTRY (intraday) → real-time Telegram with the structural stop + the harvest-fast
note. No per-tick pings (the #168 noise class).

**5. Board command** `/sip` (watched/armed/ready) — 3-place slash-command update (handler in
`agent.py` + dispatch dict + `BotCommand` in `telegram.py`, same commit, per CLAUDE.md).

**6. Paired W3 exit/harvest** — the BACKTESTED derisk-fast scale-out ladder (Step 2d /
`_270_exit_replay.py`): bank a +1R floor + a +3R spike tranche into the TRIGGER-DAY spike
(the harvest is a same-day event), NOT buy-and-hold (which loses the median name). Ship the
ladder in SHADOW recording realized R; the targets/fractions are operator decision #5 (N=15
in-sample), sized only after multi-window re-validation. Built WITH step 3.

**Acceptance:** shadow run writes lifecycle rows; an ARMED transition fires exactly one Telegram;
the intraday watch proposes entries with the FIRST5 stop; staging-validated before merge.

## Ship timeline (discipline — SHADOW ETA tied to the 6/22 launch DoD; LIVE is evidence-gated)

**Anchor:** "#270 delayed-EP composed [in shadow]" is **launch DoD #4** (`docs/roadmap/launch-2026-06-22.md`)
— the ETA ties to that existing commitment, not a fresh date. **START is gated to AFTER the Mon
6/15 #277 live-ORB gate closes clean** (step 3 runs in `combined` = the §C rollback target).

- **3a — minimal shadow (EOD-only, no live stream): readiness state table + daily job +
  ANTICIPATION EOD path + maturity gate + `/sip` board + ARMED alert.** Branch → staging-validate
  (pipeline exists) → merge post-gate. **ETA Tue–Wed 6/16–6/17** (first build slot after the gate
  lifts). This is the bulk of the DoD — all EOD-computable, lowest risk.
- **3b — intraday CONFIRMATION entry-watch** (FIRST5/GDL on the live bar stream; execution-adjacent,
  shadow/alert-only). **ETA ~6/17–6/18**, rides the bar-stream wiring.
- **3c — chart-vision maturity read** = 2nd consumer of **#267** (renderer build Wed 6/17, eval
  Thu 6/18) → layered **~6/18+**; `base_run` ships in 3a without it (enhancement, not a blocker).
- **Paired W3 exit/harvest** rides the roadmap W3 exits workstream (~6/17–6/19).
- **VERIFIED-LIVE composed-in-shadow by the 6/22 launch DoD** (Acceptance above met in prod).

**LIVE / SIZED (real money on this setup): NO committed date — evidence-gated.** Gated on (1)
forward-outcome data the shadow must first collect (the #168 actionability gate), (2) multi-window
magnitude re-validation (DATA-BLOCKED today — needs `mi_daily_closes` history backfilled), (3) the
W3 exit layer realized, (4) operator decision #4 (include + maturity threshold + sizing) + the
HARD-gate sign-off. Weeks out, post-launch — do NOT attach a date; ship the SHADOW now, gate live
on the evidence (the bias-to-action "ship the safe subset" rule).

## ANTICIPATION UNIVERSE — Pradeep shortlist diagnosis (operator 2026-06-16)

Operator shared Pradeep's 6/15 anticipation shortlist ($COO $HYLN $ALHC $APPS $NTAP — "multiple
tight days") and asked: does our system pick these up? Checked vs the LIVE continuation-flag
detector (`flag_detector.py`; the right correspondent — these are post-runup tight bases, NOT
post-+40%-gap tiny-caps, so #270's gap-seed wouldn't catch any). Result: **1 of 5 caught (NTAP
TIGHTENING), 1 partial (HYLN WATCH; RMV saw it tight, rmv_5d=0 on 6/10–12 = the #54 divergence
live), 3 missed (COO/ALHC/APPS).** All five DO have prior runups (COO +15%, ALHC +52%, NTAP +71%,
APPS +259%, HYLN +352%) — operator corrected an earlier wrong framing: Pradeep REQUIRES the runup,
he is not screening random tight stocks.

**Why we miss them — the exact gate per name (current thresholds):**
- `_RUNUP_MIN_RATIO = 1.50` (runup ≥50%): **COO fails** (+15–23%). To catch it we'd drop the floor
  to ~15% → admits THOUSANDS of names up 15%/60d. COO isn't special at +15%; **Pradeep picked it by
  DISCRETION** (tight base + catalyst + Twitter-buzz read) **on a LOOSE universe**. The runup number
  is not his edge — his SELECTION is. A threshold drop adds noise, not his shortlist.
- `_BASE_AGE_MIN_WATCH = 3`: **ALHC fails** (base_age 2 — a fresh +25% thrust 6/09 then 2–3 tight
  days). Our maturity floor is stricter than his "enters on multiple (2–3) tight days." Measured:
  base_age 3→2 adds ~30–90 raw fresh-base names/day (real WATCH addition is the subset clearing
  runup+tightness) — modest, NOT a flood, but base_age=2 is the freshest base → forward-evidence
  before a live flip (shadow-variant candidate).
- APPS: +259% runup but recent days 7–12% wide → not actually tight → reject defensible.

**THE INSIGHT (reshapes the #270 anticipation detector):** Pradeep = **LOOSE universe (any
post-runup tight base, incl. modest +15% on quality names) + DISCRETIONARY QUALITY SELECTION**
(multiple tight days + catalyst + buzz). Our flag detector = **TIGHT universe (≥50% runup) surfaced
wholesale**. Reproducing "COO makes the shortlist, the other 2000 up-15% names don't" is a
**SELECTION/RANKING problem, not a threshold drop**: run a loose post-runup universe → RANK by
tight-base quality (RMV + base maturity + catalyst materiality) → surface the top-N. That ranking
layer is exactly the #270 anticipation + RMV-telemetry direction.

**DESIGN DIRECTION for #270 Step 3 (anticipation detector):** seed a LOOSE post-runup universe and
add a RANKING pass (RMV + base_age maturity + catalyst), surfacing top-N — record in shadow, watch
whether its top-ranked names match Pradeep's shortlists over ~2 weeks before any live promotion.
**OPEN (operator/advisor decision before building the readiness job):** universe breadth — keep the
+40%-gap tiny-cap seed for the delayed-EP SUBSET (the MNTS template) AND add a separate
loose-universe general-anticipation ranker? Or unify? Don't lock the readiness-job seed until decided.
NO live threshold change on COO/ALHC alone (N=2, one tweet — the parabolic ship→revert→restore +
the operator's N≥30 anti-overfit rule). Telemetry-first, gate the live flip on the evidence.

## Gate

The replay + calibration (read-only scripts + this doc) are gate-safe. The deployable
tactic (Step 3) is sequenced post-#277, same discipline as #258 step 2.
