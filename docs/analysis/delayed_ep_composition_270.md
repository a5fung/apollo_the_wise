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
- **Expectancy (triggered, N=8), stop-and-reenter:** median **+3.3R**, mean **+2.9R**/name,
  **62% eventually caught** the breakout (avg 1.9 attempts/name). vs one-shot −1.0R.
- **Parity three-way (won names, common daily endpoint, endpoint-symmetric MFE):** ANTICIPATION
  **6.5R** vs FIRST5 **7.6R**. On a parity-clean basis (both MFE credit their OWN entry-day high —
  the first cut wrongly denied FIRST5 the breakout-day high it exists to capture, advisor 6/14),
  **FIRST5's much tighter 2% stop EDGES anticipation on R** despite anticipation's far-lower entry
  + wider 5% coiled stop. **Anticipation does NOT win on R** — its edge is the lower entry
  PRICE / earlier positioning (the price-capture below), not R expectancy. (N=4, conditioned on
  anticipation having won; NOT comparable to the intraday 3.5R — re-based horizon.)
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

**A 3-day base keeps ALL 5 winners** while dropping 3 immature/false entries, lands the entry
**closer to the breakout** (7→5d), needs **fewer attempts** (1.7→1.2), and **collapses the
outlier reliance** (top name 73%→40%, ex-top mean **+0.5→+4.8R**). The improvement is *monotonic
1→2→3 across multiple independent metrics* (the signature of a real effect, not a fit); min_base=4
over-tightens (loses a winner, concentration rebounds → too close to confirmation). **The maturity
gate de-risks the outlier problem WITHOUT a second time window** — which matters because the data
can't supply one (see below). DISCIPLINE: min_base=3 is selected on N=8 (in-sample) → the
DIRECTION (require maturity) is the robust finding; the exact threshold is illustrative, re-validate.

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
3. **MFE ceilings, not harvested R** (symmetric across all three entries, so the comparison
   holds; the absolute R's are optimistic — the W3 exit layer sets realized harvest).

**Verdict:** anticipation is a real, positive-expectancy THIRD entry mode (+2.9R/name stop-and-
reenter) that validates both of Pradeep's claims — **conditional on re-entry discipline**. It does
NOT beat confirmation on parity-clean R (FIRST5's tighter 2% stop edges it, 7.6R vs 6.5R); its
distinct value is the **lower / earlier entry** — you're positioned BELOW the gap instead of
chasing the first-5 high, which is exactly Pradeep's "capture the bulk on a gap up". And it does
NOT replace confirmation (fast runners don't coil). So the entry layer is **complementary**:
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
  Stop-and-reenter (the faithful model — one-shot is a strawman) = **+2.9R mean/name on
  triggered, 62% caught**; comparable to FIRST5 (does NOT beat it on parity-clean R — FIRST5's
  tighter stop edges 7.6R vs 6.5R; anticipation's edge is the lower/earlier entry). Validates
  both his claims (25% earlier capture, 2% fast-fail). ILLUSTRATIVE not ship: N=8, outlier-leveraged (RLMD =
  73% of total, survives ex-top at +0.5R/name), MFE ceilings. Re-entry discipline LOAD-BEARING.
  Complementary to confirmation (only ~37% of armed names coil). Full writeup ↑ "Step 2c".
- ⏸ Step 3 — deployable SHADOW tactic = readiness state table + scheduler job +
  intraday entry-watch + `/`-board + alerts. GATED post-#277 (new job + CREATE TABLE run
  in COMBINED = §C rollback target). Branch + staging-validate, merge post-gate.
- ⏸ Paired — W3 EXIT/harvest layer (derisk-fast) — built WITH step 3, same tactic.

## Step 3 build spec (TURNKEY — execute post-#277-gate, mechanical not design)

Everything below is decided; the post-gate build is wiring, not design. All of it runs in
`combined` (new job + CREATE TABLE) → GATED. Build on a branch, staging-validate, merge after
the Monday gate closes.

**1. State table** `mi_delayed_ep_lifecycle` (add to `db.py::initialize_schema()`):
`ticker TEXT, gap_day DATE, gap_day_low NUMERIC, gap_day_vol BIGINT, sma200_at_gap NUMERIC,`
`state TEXT (watched|armed|coiled|ready|triggered|expired), armed_date DATE, coiled_date DATE,`
`ready_date DATE, triggered_date DATE, entry_tactic TEXT (anticipation|first5_break|gdl_reclaim),`
`entry_price NUMERIC, stop_price NUMERIC, reenter_count INT, fwd_mfe_pct NUMERIC, last_eval DATE,`
`created_at/updated_at TIMESTAMPTZ.` PK `(ticker, gap_day)`. Mirrors the replay() event fields
1:1 — no new logic. `coiled`/`reenter_count` carry the anticipation path (step 2c).

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

**6. Paired W3 exit/harvest** — derisk-fast partial ladder (earlier/more partials than the
standard EP ladder; the cohort's fat-MFE / weak-close gap is the evidence). Built WITH step 3.

**Acceptance:** shadow run writes lifecycle rows; an ARMED transition fires exactly one Telegram;
the intraday watch proposes entries with the FIRST5 stop; staging-validated before merge.

## Gate

The replay + calibration (read-only scripts + this doc) are gate-safe. The deployable
tactic (Step 3) is sequenced post-#277, same discipline as #258 step 2.
