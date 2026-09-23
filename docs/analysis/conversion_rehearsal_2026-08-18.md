# Conversion rehearsal — the surfaced tail winners through TODAY'S stack (2026-08-18)

> 🗂 **DELAYED-ENTRY CONTEXT LEDGER — READ FIRST: `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`.** It carries the goal, every operator ruling, every study and its result, and the open questions. Two cards ran on this subject without it on 2026-08-29 and returned nothing new. Kept complete by `tests/test_delayed_entry_ledger_complete.py`.


**The question** (synthesis §4.4, operator-approved): *when next month's tail winner alerts, does
TODAY'S system convert it?* Answered directly: every tail winner we ALREADY surfaced live is
replayed through the current rules — alert gates, ORB window, era-C bracket, current exit ladder —
and the stage where each dies is recorded. The SAME replay runs on the surfaced LOSERS, because
selection is judged on both directions (GOAL section, operator 2026-08-18): a gate that kills
winners is only bad if it does not also kill losers.

⚖ **THE LINE — measure only.** Nothing here changes or proposes to change any gate, stop, size or
safeguard; the forks at the bottom are the operator's. **$0**: prod DB reads + bars already held;
no LLM calls. Probe: `scripts/probes/conversion_rehearsal_surfaced_tail.py` (reuses the
`geometry_sweep_572` exit engine with the era-C pinned target; capture SQL
`scripts/probes/_rehearsal_capture.sql`; derived loser set `_rehearsal_losers.psv`).

---

## THE ANSWER

**The synthesis's number was wrong in our favor and the conclusion is worse.** The real count:
**15 surfaced tail winners, 3 — not 2 — became trades, and all three lost** (INTC −$477,
SMCI −$639, **NRIX −$378, which the 08-16 attribution read missed** because NRIX sat in the
"caught" bucket nobody re-checked against `mi_live_trades`). 12 of 15 never traded.

**Replayed through TODAY'S full stack — era-C bracket included — the 15 convert to ≈ nothing:**

- **7 of 15 still die before the broker** (gap floor 1, cooldown 1, tier 2, slot cap 2, stop-width 1).
- **5 of 15 fill** (3 lived, 2 reconstructed). Under era-C management the five sum to **−2.0R**:
  three full −1R stops (INTC, HLIT, NRIX), two partial-then-breakeven at **+0.5R** (SMCI, VPG) —
  while those same five stocks went on to run **9.5–11.9× their own ADR**. Best single conversion:
  **+0.51R** against a target that needs ≈ **+6R** per converted winner.
- 3 of 15 are censored (no bars survive; fill unknowable).

**In the programme's currency:** the target is ~4 converted tail winners in 4½ months (~1/month at
≈+6R each ≈ +5.3R/month). Today's stack, run over the same 4½ months of names we DID surface,
delivers **≈ +1.0R of kept winner gains total (≈ +0.2R/month) — about 4% of the target**, and
−3R of full stops on the same names against it. **The conversion leak is measured and it is NOT
closed. Era C moves the fills from "all three lost dollars" to "net ≈ −0.1R across five" — it stops
the bleeding on SMCI-shaped paths but converts nobody, because these winners' EP day itself
routinely collapses (HLIT −11% open-to-close; INTC low was −5% under the fill) before the 8–12×ADR
run starts from a later base.**

---

## 1 · The verified count (correcting the synthesis)

| claim | synthesis said | verified |
|---|---|---|
| surfaced tail winners (of 78 in the #552 cohort) | ~15 | **15** ✓ (11 bucket-C + HLIT, VPG, ABVX, NRIX) |
| became trades | 2 (INTC, SMCI) | **3 — NRIX 06-08 also filled** (`mi_live_trades` id 201, closed −$378.24, stopped in 10 min) |
| the trades' outcome | both lost | **all three lost** while the stock ran ≥8×ADR |

Broad funnel over the same window for scale: 406 alerts → 95 trades (77% of surfaced names never
trade) — consistent, independently confirmed by the parent read.

## 2 · The winner funnel, with names — today's stack, stage of death

| # | name | date | tail | then (lived) | TODAY dies at | detail |
|---|---|---|---|---|---|---|
| 1 | FLY | 03-12 | 8.8× | HIGH, no pipeline row (March era) | **fill — CENSORED** | no ORB/bars survive |
| 2 | FLY | 03-20 | 11.7× | HIGH, no pipeline row | **cooldown** | surfaced 03-12, 8 days prior; gap 11.3% < 15% carve-out |
| 3 | YSS | 03-20 | 12.7× | HIGH, no pipeline row | **fill — CENSORED** | no ORB/bars survive |
| 4 | INTC | 04-24 | 10.9× | **TRADED −$477** | fills | era-C: **−1.00R** hard stop day 0 (day low 79.62 < 2R stop 80.04) |
| 5 | STX | 04-29 | 8.3× | blocked: 3-loss breaker | **fill — CENSORED** | today's 10-loss breaker would NOT trip; no bars to sim the rest |
| 6 | BAND | 04-30 | 12.3× | skipped: stop_too_wide | **spec** | same gate, unchanged: ORB 7.2% > 1.5×ATR (and bars show it never re-touched ORB high pre-10:00 anyway) |
| 7 | GTX | 04-30 | 12.9× | MODERATE (briefing) | **gap floor** | open gap 8.1% < 10% hard floor — crossed 10% intraday later (the zones question) |
| 8 | QCOM | 04-30 | 14.6× | MODERATE; the fade-skip was the 9M leg (retired #515) | **tier** | score 60.5 → MODERATE, no ORB. Footnote: even if promoted, recorded 09:31 price = 8.25% rt gap → the rt re-check kills it too |
| 9 | SMCI | 05-06 | 9.5× | **TRADED −$639** | fills | era-C: **+0.51R** — partial at target d1, breakeven stop d2 (hand-verified against bars) |
| 10 | FLNC | 05-07 | 8.0× | blocked: max_positions 5/5 | **slot cap** | cap unchanged today; same-day book was full |
| 11 | FTNT | 05-07 | 11.9× | blocked: max_positions 5/5 | **slot cap** | same |
| 12 | HLIT | 05-12 | 9.7× | infra skip (05-13 outage class, since fixed) | fills | era-C: **−1.00R** hard stop day 0 — EP day faded −11% open→close; the run came later |
| 13 | VPG | 05-12 | 11.6× | infra skip (same class) | fills | era-C: **+0.50R** — partial d0, breakeven-stopped d0; **next day VPG gapped 92→104.5 and the whole 11.6× run happened without us** |
| 14 | ABVX | 06-03 | 12.1× | MODERATE (briefing) | **tier** | score 50.4; routine catalyst, no earnings override |
| 15 | NRIX | 06-08 | 11.9× | **TRADED −$378** | fills | era-C: **−1.00R** hard stop day 1 (survives day 0 by 4 cents — daily-res, fragile) |

**Lived vs reconstructed:** INTC, SMCI, NRIX entries are real fills (their era-C exits are still
simulated). HLIT and VPG fills are simulated from captured minute bars. FLY×2, YSS, STX are
censored (no bars survive the purge era). QCOM/GTX/ABVX die before any fill is needed.

## 3 · The same funnel on the surfaced losers (163 name-days, same cohort frame)

Loser set: every cohort non-winner with live-surfacing evidence — 78 surviving alert rows
(05-11+), plus pre-05-11 pipeline/`mi_ep_missed_outcomes` evidence under the same
replay-contamination guard the 08-16 read used for HPE/QURE.

| stage of death (today's stack) | winners | losers | winner share of kills |
|---|---|---|---|
| gap floor (10% hard) | 1 | 25 | 3.8% |
| cooldown (60d) | 1 | 0 | — (see censoring note) |
| tier (score/MODERATE) | 2 | 25 | 7.4% |
| ORB window timing (HIGH after 09:44) | 0 | 4 | 0% |
| safeguards — **slot cap 5/5** | 2 | 4 | **33%** |
| spec (stop_too_wide / zero-range) | 1 | 10 | 9% |
| rt gap re-check at 09:31 (ON since 08-02) | 0 | 4 | 0% |
| no fill by 10:00 (bars-verified) | 0 | 20 | 0% |
| censored (no bars, purged era) | 3 | 30 | — |
| **FILLS** | **5** | **41** | **11%** |

Baseline for comparison: the whole surfaced pool is 8.4% winners (15/178). A gate killing at
well below 8% is earning its keep on this evidence; well above is killing winners preferentially.

- **Working as intended:** the 10% gap floor (3.8%), the 10:00 no-fill cancel (0% — it removed 20
  losers and zero winners), the 09:31 rt gap re-check (0%), the ORB-window cutoff (0%).
- **The one gate that kills winners without killing losers: the 5-position slot cap — 33% of its
  kills are tail winners** (FLNC 8.0×, FTNT 11.9×, both on 05-07 while the book held what became
  losers). n=6, so this is a flag, not a verdict — but it is the same slot-scarcity the operator
  named as the reason selection density matters.
- **Cooldown killed 1 winner (an 11.7×ADR second leg) and 0 losers — but its loser column is
  structurally censored**: the 60d cooldown already ran at alert time, so the losers it kills never
  surfaced and cannot appear in a surfaced-only replay. Same for the top-20 cap, extension and
  quality floors (0 kills both sides here): their kills live in the 63 never-surfaced misses (the
  08-16 attribution read), not in this table. **This replay measures the gates that CHANGED plus
  the entry/exit mechanics; unchanged gates are invisible on the loser side by construction.**

**Era-C outcomes on the loser fills** (41 fills, conservative daily ordering): **sum −3.4R, median
−1.00R**, 22 full stops, 19 kept some gain; 3 of the 41 are assumed-fill daily-resolution
reconstructions. Combined book (winners + losers filled): 46 fills, −5.4R — **on this cohort's
fills the era-C bracket is roughly breakeven-to-negative in conservative mode**; the 08-16 +11.4R
sim was a different population (all 43 HIGH fills incl. non-cohort names) and a [cons,opt]
midpoint. Consistent with "provisional, conditional on selection".

## 4 · Why the filled winners still do not convert

The five winners that fill all share the shape the program keeps re-finding: **the EP day itself is
violent and often finishes weak, and the 8–12×ADR run starts from a later, higher base.**

- INTC: fill 84.04, day low 79.62 (below even the 2R stop), closed 82.5; the run came later.
- HLIT: open 14.55 → close 12.95 (−11%); run later.
- NRIX: day-0 low one tick above the 2R stop, gone next morning; run later.
- VPG: the one that ran immediately — and the +2R partial → breakeven ladder banked +0.5R on
  day 0, then the breakeven stop surrendered the next-day gap to +11.6×ADR.
- SMCI: the good case — +0.51R kept, the only one where the era-C stop demonstrably beat the
  lived outcome (−$639 → +0.5R).

So even a perfect alert-side funnel feeding today's bracket converts these at ~+0.5R, not +6R.
On THIS cohort the binding constraint after the slot cap is the **exit ladder's day-0/day-1
geometry** (2R stop still inside the EP-day's collapse range; breakeven stop directly under the
first pullback) — which is era C's open question, not new evidence that any specific alternative
works. The delayed-entry work (#562) already measures the "later base" these names actually ran
from.

## 5 · Censoring, reconstruction and fragility — stated plainly

- **Right-censoring of outcomes: none** — every name-day (≤07-15) has a full 20-trading-day
  forward window inside the captured dailies (≤08-17).
- **Fill/bars censoring: 3 of 15 winners, 30 of 163 losers** (pre-05-11 purge era, no minute
  bars) — every conversion share above is a FLOOR only in their direction.
- **Tier stage is replay-of-record**: catalyst grades/scores are the recorded values. Today's
  grounded-Sonnet grader + the holistic judge (toggle ON since 06-10) could grade differently in
  either direction; re-running them is paid and was out of scope ($0).
- **Gap/rank gates use the daily open as proxy** for the scanner's per-tick delayed/rt gap; the
  top-20 rank is a cohort-based floor.
- **NRIX's era-C day-0 survival margin is 4 cents at daily resolution** — the −1R could as easily
  be a day-0 stop; either way it is −1R.
- **Equal-risk R units assume sizing at 1% risk.** Where the 20% position cap binds (it did on
  INTC: 237 shares was the cap, not the risk), era C's doubled stop distance doubles the dollar
  loss on a full stop — the synthesis §4.1 R→dollar distortion, observed here concretely.
- One regime, 4½ months, no holdout; the winner side is n=15 (5 measurable fills). Everything is
  provisional per the GOAL-section rule and re-opens if selection changes.

## 6 · The forks this hands the operator (measure-only; no recommendation is pre-decided)

1. **Slot cap**: the only gate whose kill pool is one-third tail winners (n=6). Whether 5 slots is
   the right number, or whether slot allocation should see score/rank, is his call — the rank
   shadow is accruing exactly the evidence that would inform it.
2. **Cooldown carve-out**: FLY's second 11.7× leg died 8 days into a 60d cooldown; the carve-out
   (gap ≥15 + earnings) did not reach it. The re-alert-as-signal question (#170 class) is his.
3. **Day-0/day-1 exit geometry on filled winners**: era C converts these five at +0.5R best; the
   tail starts later. This is era C's live accrual + the #562 delayed-entry lane — nothing new to
   decide today, but the rehearsal says conversion will not appear in the era-C ledger from names
   shaped like these five.

**Provenance:** probe + captures listed at top; funnel output archived in the session scratchpad
(`rehearsal_final.txt`); cohort = `scripts/probes/_552_cohort.psv` (unchanged); trades =
`mi_live_trades` capture `live_all.csv` (2026-08-18). Stack parameters verified in code and prod
state on 2026-08-18 (gates, toggles, era-C sizing/stop in `order_manager.py`, fade-guard tiering,
rt re-check ON, 9M Day 2 retired).
