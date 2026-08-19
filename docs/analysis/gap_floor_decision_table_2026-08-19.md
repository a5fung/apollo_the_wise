# MIN_GAP_PCT — "loosen to what though?" The decision table (2026-08-19)

**⚖ THE LINE: `MIN_GAP_PCT` is entry discipline and the operator's sole authority. This document
measures and prices the options; it proposes nothing, changes nothing, and no toggle moved.**

Trigger: the #577 must-not-miss fixture found **15 of the 25 evidence-labelled ≥10R winners are
excluded today by the 10.0% gap floor** (all gapped 8.1–9.9% at the open; no other gate excludes
them at the universe stage). Operator's reply to "loosening is your call": *"losen to what though?"*
This prices the candidate floors AND the band+trigger shape he pointed at (P2).

Sources (all pre-existing captures or one-shot read-only prod pulls, $0):
`scripts/probes/_552_cohort.psv` (tier-A real-stock cohort 2026-03-01..07-15: 749 gap days, 92
sessions, 78 ≥8×ADR winners — the programme's standard cohort) ·
`docs/analysis/winner_r_available_2026-08-16.txt` (the ≥10R set, geometry 1 = our live stop) ·
`scripts/probes/_577gap_prod_capture.txt` (prod: scan-log 8.0-floor-era volumes 04-13..05-15, tick
detail, minute-bar coverage) · probe: `scripts/probes/gap_floor_sweep_577.py` (reproduces every
number below; asserts the known cohort counts on load).

Gap basis, stated once and carried everywhere: cohort gap = **session open vs prior close** (the
fixture's basis). The live scanner admits per ~5-min tick on the ~15-min-delayed snapshot — **a name
under 10% at the open that reads ≥10% on a later tick is ALREADY admitted today**. So the floor
binds hardest on names that **never print 10% at all**, and "winners recovered" below means
**universe ADMISSION recovered** (a scan row, a score, a trace — P1's requirement), not alerts.

---

## 1. Recall first (P1): what each floor recovers

| floor | ≥10R winners recovered (of 15) | ≥8×ADR winners recovered (of 25 in band) | who comes back |
|---|---|---|---|
| **10.0 (today)** | 0 | 0 | — |
| **9.5** | **4** | 4 | MU 49R · MRVL 35R · SNOW 25R · BE 16R |
| **9.0** | **8** | 11 | + ALGM 23R · AMKR 20R · UMC 18R · USAR 16R |
| **8.5** | **9** | 12 | + QCOM 14R |
| **8.0** | **15 (all)** | 25 (all) | + STRL 38R · ASX 32R · NBIS 21R · HUT 12R · SMTC 11R · IREN 11R |
| band+trigger @10% | ≤ 11 | ≤ 19 | can NEVER recover NBIS/SMTC/ASX/IREN (8.1–8.3%, never printed 10% all day — 73R) |

**The ≥10R winners sit at BOTH edges of the band, not spread evenly:** six at 8.0–8.4% (incl. STRL
38R, ASX 32R), one at 8.5–9.0%, four at 9.0–9.4%, four at 9.5–9.9% (incl. MU 49R). The 8.5–9.0
slice is nearly empty — **8.5 buys almost nothing over 9.0** (56 extra gap-days for 1 winner).

**Geometry-1 R-available carried (P3, the SUM):** today's ≥10% pool holds **174R** across its 10
≥10R names; the excluded 8–10 band holds **337R** across its 15. **Two-thirds of the ≥10R
R-available in the whole cohort sits below the current floor.** (Partly mechanical — a modest gap
means a tighter day-1 range and so a bigger R per move — but that IS our live stop geometry, and
the effect survives at a fixed-ADR stop: Spearman(gap, R-geo2) = −0.226, gap vs days-to-peak =
−0.524, per the winner_r file. The INTC-shaped winner that grinds for weeks is a modest gap.)

## 2. Both directions (P5): the cost side, and density of the slot pool (P4)

| floor | pool (gap-days) | non-winners added | pool ≥8×ADR density | pool ≥10R density | extra candidates/day (live scanner, avg/med) |
|---|---|---|---|---|---|
| **10.0 (today)** | 497 | — | 10.7% | 2.0% | baseline ≈ 26–30 names/day |
| **9.5** | 542 | +41 | 10.5% | 2.6% | **+3.3 / +2.5** (≈ +11%) |
| **9.0** | 603 | +95 | 10.6% | 3.0% | **+7.7 / +6.0** (≈ +25%) |
| **8.5** | 659 | +150 | 9.9% | 2.9% | +14.0 / +12.0 (≈ +50%) |
| **8.0** | 749 | +227 | 10.4% | **3.3%** | **+22.8 / +18.5** (≈ +75%) |
| band+trigger @10% | 497+206 | +187 | 10.2% | 3.0% | +2.2/day tier-A (its trigger half already runs live) |

- Live extra-candidates/day = the 8.0-floor era's own scan log (04-13..05-15, 24 sessions), counting
  only names that **never crossed 10% intraday** — names that DID cross are already in today's pool.
- **At the ≥8×ADR family level the band is a wash** (9.9% density vs the pool's 10.7%): loosening
  does not meaningfully dilute. **At the ≥10R level the band is 3× RICHER than today's pool** (6.0%
  vs 2.0%) — every loosening IMPROVES the density of what the 5 slots compete for, on the tail
  measure that actually pays (P3).
- Robustness, ex-2026-04-08 (the macro-bounce session carries 10 of the 15): band ≥10R density 2.5%
  vs pool 1.5% — the tail enrichment **survives, at 1.7× instead of 3×**. The family-level read
  turns mildly dilutive ex-04-08 (6.1% vs 10.4%). Concentration is real; the direction is not an
  04-08 artifact.

## 3. The band+trigger shape (P2) — priced, and where it actually lands

- **The trigger half already exists.** The scanner re-evaluates every ~5 min and admits any name
  whose gap reading reaches 10% before the scan cutoff — verified in the 8.0-era ticks (SNOW read
  10.28 at 09:40 **inside the ORB window**; UMC 10.64 at 09:30; QCOM 10.27). #490's RT overlay is
  the in-window-accurate version of the same thing, already dark-built. **As an admission rule,
  "watch 8–10, trade the 10-cross" ≈ today's behavior plus a watch state.**
- **What it can never do:** recover the four ≥10R winners at 8.1–8.3% that never printed 10% all
  day (NBIS, SMTC, ASX, IREN — 73R). The never-crossers are the RICHEST slice of the band (≥10R
  density 8.7% vs 5.3% among crossers) — the grind-up shape, again.
- **What its watch state IS worth (orthogonal to the floor):** pre-arming. A late in-window cross
  (SE 08-11: skipped at 9.2%, reclaimed 10.5% four minutes later) currently loses the ORB entry to
  latency — admission recovers, entry can't once 9:45 passes. Pre-computing score/catalyst for an
  8–10 watch list is a latency fix, not a selection change, and pairs with ANY floor choice.
- **The 09:30–09:44-only cross rate is NOT measurable for 12 of the 15** — zero minute bars
  persisted (never alerted → never captured; prod Q1 = 0 rows). Stated, not estimated.

## 4. The P8 conditional — what a floor change alone does NOT do

- **Historically these 15 were lost to OTHER gates, because the floor WAS 8.0 until 2026-05-17.**
  The three in the scan-log era all passed the then-floor and were dropped downstream: SNOW and UMC
  by the **top-20 gap cap**, QCOM by **score 32 < 50 (catalyst=routine)**. Ten of the fifteen are
  2026-04-08, where the top-20 cap dropped winners at gap ranks 97–347.
- So each floor's "winners recovered" converts to admission + a scan row + gradability — **the
  top-20 cap and the score gate still stand between admission and an alert**, and on the evidence
  they, not the floor, were the binding gates whenever we can check. Those are separate decisions,
  separately priced (top-20 cap is #552's named leak; score<50 is the steadiest per-session leak).
- Provenance of today's 10.0: ADR 0003 R2 (2026-05-17) lifted 8.0→10.0 on **0-for-8 win rate in the
  8–10 bucket** — an alert-level, win-rate-led read on 8 names, pre-P3. The evidence now on the
  other side: 15 evidence ≥10R winners and 252 measured band-days. ADR 0003 itself offered the
  alternative "keep 8% as watchlist and 10% as ORB entry trigger" — the band+trigger shape, priced
  above.

## 5. What the data cannot answer

- In-window (09:30–09:44) cross timing for 12 of the 15 — no minute bars exist for never-alerted
  names. (The #490 RT overlay + #567 keep-forever fix this class going forward.)
- Whether recovered admissions become ALERTS under the current score/top-20 funnel — the three
  verifiable cases did not, then. A floor change fixes visibility (P1); conversion is the funnel's.
- One 4½-month window, descriptive, with 04-08 concentration (ex-04-08 robustness shown in §2).
- Cohort screens (close ≥ $10, $vol ≥ $50M) vs live universe floors (prev close ≥ $5, 50k shares):
  live per-day adds are the scanner's own tick-basis counts; cohort densities are open-basis. Both
  bases stated where used.

## 6. My read (measurement, not proposal — the ruling is his)

- **9.0 is the defensible line if a line is wanted:** recovers 8 of 15 ≥10R (all of the 9.0–9.4
  cluster), +6–8 names/day (≈ +25%), pool ≥10R density improves 2.0% → 3.0%, family density flat.
- **8.0 is defensible only as a recall-complete choice with open eyes:** all 15 back (incl. STRL
  38R / ASX 32R / NBIS 21R, unreachable by any trigger shape), but ~+75% daily candidates, and the
  family-level density turns mildly dilutive ex-04-08. It is what P1 taken literally implies.
- **8.5 is NOT defensible:** 56 extra gap-days over 9.0 buy exactly 1 winner.
- **9.5 is the timid version of 9.0** — half the recall for a third of the volume; nothing in the
  data favors it over 9.0 except operational caution.
- **The band+trigger @10% is NOT a floor substitute:** its trigger already runs live, and it
  structurally forfeits the four richest-shape winners (73R). Its watch-state half (pre-arming
  8–10 names so a late cross still makes the 9:45 deadline) is worth having under ANY floor.
- P2 note: whatever the ruling, the ≥10R winners clustering at BOTH band edges (8.0–8.4 and
  9.5–9.9) with a hollow middle is itself evidence that a single line is a blunt instrument here;
  the shape-based selector (#519 vision lane) is where "some gap, judged in context" ultimately lives.

*Probe: `scripts/probes/gap_floor_sweep_577.py` · capture: `scripts/probes/_577gap_prod_capture.txt`
· not committed, not deployed; measurement only.*
