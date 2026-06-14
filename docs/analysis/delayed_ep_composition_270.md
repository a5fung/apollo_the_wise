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

## Sequencing (the e2e tactic)

- ✅ Step 1 — readiness composition, validated vs MNTS. Gate-free.
- ✅ Step 2 — cohort calibration: selective funnel + fat-MFE tail + knobs. Gate-free.
- ⏸ Step 2b — **intraday ENTRY tactic tuning** (gate-free analysis): for the cohort's
  ARMED/READY names, replay candidate intraday entries (first-min hold / ORB-of-reclaim
  / U&R) on intraday bars → which entry tactic best captures the MFE with the tightest
  stop. (Needs intraday bars — `mi_intraday_bars` / a Polygon pull.)
- ⏸ Step 3 — deployable SHADOW tactic = readiness state table + scheduler job +
  intraday entry-watch + `/`-board + alerts. GATED post-#277 (new job + CREATE TABLE run
  in COMBINED = §C rollback target). Branch + staging-validate, merge post-gate.
- ⏸ Paired — W3 EXIT/harvest layer (derisk-fast) — built WITH step 3, same tactic.

## Gate

The replay + calibration (read-only scripts + this doc) are gate-safe. The deployable
tactic (Step 3) is sequenced post-#277, same discipline as #258 step 2.
