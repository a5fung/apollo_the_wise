# High-break stop bases + the stopped-out-day-1 population cut — the operator's two questions on the backfill

> 🛑 **ITS POPULATION SPLIT IS SUPERSEDED — and one of its inputs was measured at the wrong level.**
> **(a) The ORB level was wrong.** This study tested "did price break the ORB high" against the
> **9:30–9:45 range**. Our live entry uses the **FIRST 1-MINUTE BAR** (`entry_pipeline.py:99`,
> `alpaca_client.get_first_bar`). Against the correct level only **12 of 157** qualifying EPs never
> trigger — the "94 never broke the ORB high" figure below is mostly an artifact of the wrong level.
> **(b) The split itself mixed two things.** ⚖ Operator, same day: *"the names we didn't enter can be
> for reasons beyond the stock itself, like we hit our cap, or the window beyond 9:45… we should just
> look at all EPs that meet our criteria."* 71% of the non-fills were OUR constraints, not the stock's.
> **(c) So its ranking is INVERTED by the successor**: simulated stopped-out-on-day-1 holds the
> biggest tail, not the smallest, and the "aim delayed entry away from knocked-out names"
> recommendation drawn from this doc is **WITHDRAWN**.
> ✅ **WHAT SURVIVES:** the Q1 stop-basis work is untouched and stands — winners gap over the EP-day
> high, bar-anchored stops kill 21 of 48 fires including both winners, and only ADR-anchored or
> EP-close bases tighten without killing fires.
> ▶ Superseded by `docs/analysis/delayed_entry_theoretical_day1_2026-09-01.md`.


**Date:** 2026-09-01 · **Read-only replay** — no prod writes, no thresholds, no strategy changed.
**Acting-rules source:** `live_rules_2026-09-01.txt` (0 drift findings).
**Extends** `docs/analysis/delayed_entry_backfill_2026-09-01.md` (the 267-caught-EP replay) —
same population, same instrument (the lane's own pure functions), same maturity discipline.
Probe + captured data: `scripts/probes/_562_stop_population_probe.py` + `_562sp_*.tsv`
(full tables: `_562sp_stops_report.txt`, `_562sp_classify_report.txt`, `_562sp_table_report.txt`).

---

## The decision this serves

Two operator directions after reading the backfill's per-signal table, verbatim:

1. *"stop for high break needs to be tighter"* — that is DIRECTION, not a chosen value. This
   measures several stop bases side by side on the identical 48 recorded high-break fires so he
   can pick one (or none).
2. *"another to look at is scope to EPs that we entered on first day but stopped out, those are
   the ones that broke ORB high vs those that didn't"* — the population cut: does delayed entry
   pay specifically on the names that knocked us out on day 1?

**What would change the answer:** (Q1) a stop basis that keeps the movers, doesn't kill fires at
birth, and improves expectancy net of the fires it stops out of runs; (Q2) a positive-expectancy
per-signal table on the stopped-out-day-1 group would make that group the delayed-entry target
population.

## Method / population

- **Population:** the same 267 live-source `mi_ep_alerts` campaigns (May 74 · Jun 53 · Jul 41 ·
  Aug 99, window 2026-05-01..08-31) and the same 602 recorded first-attempt fires as the
  backfill. The walk was re-run and **reproduces the recorded trigger population exactly (602
  fires; 48 high-break)** before anything was varied.
- **Q1 instrument:** identical fires (same entry = the EP-day high, same fire date/minute); only
  the stop changes. Every variant settles through the lane's own `compute_settlement`, both arms
  (M-none hard stop / M-trail = stop + MAX(SMA10,20) close-below exit). **R is HARVESTED R in
  each variant's OWN units** (risk = entry − that variant's stop) — analysis_standard §4. A stop
  at/above the entry **kills the fire and is counted** (real cost, shown with what the incumbent
  made on that fire). A stop basis that cannot be established from stored bars **abstains and is
  counted** — never guessed. Daily-grade fires had their first-touch bar derived from minute bars
  only when the 5-min series is gap-free from 9:30 through the touch (all 48 fire days had minute
  bars: 41 from the backfill capture + 7 pulled once, read-only).
- **Q2 instrument:** `mi_live_trades` magna53 rows for the 267 pairs (the acting lane per pair:
  live row if one exists, else paper — no live/paper P&L pooled, mode reported), plus the ORB
  read from `mi_intraday_bars`: ORB high = max high 9:30–9:45 ET, break = any 9:45+ high at/above
  it. Where post-9:45 minute bars are absent (37 pairs), the daily-bar fallback is **validated
  before use**: over 215 full-coverage pairs the daily high never exceeds the RTH minute max by
  more than 0.2% (n=215, 0 exceedances), so daily-high ≤ ORB-high proves "never broke" and >
  proves a post-window break.
- **Maturity discipline inherited:** every expectancy number is MATURE fires only (20 post-fire
  sessions existed by 08-31). August's settled fires are stops by construction (winners still
  open) — counted, never pooled. **Era split by month on every table.**
- Dead strategies (`9m_day2`, `fishhook_v3`, `flag_continuation`) contribute nothing; the trade
  join takes `signal_type='magna53'` only.

## The numbers — Q1: the high-break stop bases (48 identical fires; 32 mature)

| stop basis | killed at birth | med stop width | M-none mean / med (n) | M-trail mean / med (n) | ≥4R harvested (none/trail) | sum R (M-none) |
|---|---|---|---|---|---|---|
| **(a) prior session low — incumbent** | 0 | 10.8% | −0.41 / −1.00 (n=32) | −0.12 / −0.39 (n=32) | 2 / 0 | −13.1 |
| (b) breakout bar's own low | **21 (12 mature, incl. VPG & ARM)** | 1.4% | −1.00 / −1.00 (n=20) | −0.72 / −1.00 (n=20) | 0 / 1 | −20.0 |
| (c) low-of-day-so-far at fire (TEAM basis) | **21 (12 mature, incl. VPG & ARM)** | 2.2% | −0.82 / −1.00 (n=20) | −0.72 / −1.00 (n=20) | 0 / 0 | −16.5 |
| (d) entry − 0.25×ADR | 0 | 1.4% | **+1.66** / −1.00 (n=32) | +1.18 / −1.00 (n=32) | 2 / 3 | **+53.2** |
| (d) entry − 0.50×ADR | 0 | 2.8% | +0.36 / −1.00 (n=32) | +0.23 / −1.00 (n=32) | 2 / 3 | +11.6 |
| (d) entry − 0.75×ADR | 0 | 4.3% | +0.12 / −1.00 (n=32) | +0.10 / −1.00 (n=32) | 3 / 3 | +3.9 |
| (d) entry − 1.00×ADR | 0 | 5.7% | +0.04 / −1.00 (n=32) | +0.03 / −1.00 (n=32) | 3 / 2 | +1.2 |
| (e) EP-day close | 0 | 2.2% | **+1.63** / −1.00 (n=32) | +0.88 / −1.00 (n=32) | 2 / 3 | +52.3 |

Win rate is a descriptive column here (selection owns it, not the stop): 6–12% M-none across the
surviving variants, 0–5% for (b)/(c). Every settle-abstain in every variant is an immature
August open-window row — the mature n=32 read is the same fires for (a)/(d)/(e).

**Plain words, both sides:**

- **The operator's own TEAM stop basis does not transfer to this rung.** 21 of 48 fires — and
  both of the rung's only big winners, VPG (+6.2R incumbent) and ARM (+4.5R) — **gap over the
  EP-day high**, so the breakout bar's low and the low-of-day sit AT/ABOVE the buy level: no
  stop exists below the entry, the fire is killed at birth (under the lane's buy-the-level
  convention). The 20 fires that survive go 0-for-20 (b) / 1-for-20 (c). Worse than the
  incumbent on every measure.
- **An ADR-fraction stop (or the EP-day close) tightens without killing anything**: 0 fires
  killed, recall intact, and the sum flips from −13R to +53R at 0.25×ADR — because the SAME two
  winners, which never pull back at all, pay 8× more R when the risk unit is 5–8× smaller
  (VPG +6.2R → +49.5R; ARM +4.5R → +33.8R; verified by hand from raw daily bars).
- ⚠ **The entire positive is those two May fires.** Ex-VPG/ARM, every variant is negative on the
  identical remaining 30 mature fires: incumbent −23.7R, 0.25×ADR −30.0R (all 30 are full
  stop-outs), EP-close −25.7R. June and July have **no winner under any stop basis** (0.25×ADR:
  17 of 17 fires −1.00R; incumbent salvages partial time-exits worth ~+6R of less-bad). A
  tighter stop buys nothing on the bleed — it converts the two gap-over monsters into more R and
  everything else into a faster full loss. **n(winners)=2 decides the whole ranking: too thin to
  pick a value, strong enough to rank the FAMILIES of basis.**
- **Sizing reality check (context only — sizing is THE LINE):** at live sizing (1% risk, 20%
  notional cap) a stop tighter than ~5% of entry truncates the position, scaling realized
  dollars by width/5. Dollar-adjusted: incumbent −13.0R-eq · 0.25×ADR **+14.2R-eq** · EP-close
  +10.9R-eq. The tight-stop advantage survives the cap but shrinks ~4×.
- **Caught-not-kept (MFE, reported separately):** under 0.25×ADR, 11 of 32 mature fires touch
  ≥4R in their own units but only 2 harvest it (9 round-trip to the stop; M-none holds to
  session 20 by design). A tighter stop makes the harvest layer bind harder — M-trail keeps 3.

## The numbers — Q2: the population cut he asked for

**Classification of the 267 (from `mi_live_trades` + validated ORB read):**

| group | n | what it is |
|---|---|---|
| **A — entered day 1, knocked out at the stop** | **41** (33 pure stop, 8 partial-then-stop; 25 live / 16 paper; May 9 · Jun 7 · Jul 12 · Aug 13) | the operator's target population |
| **B — never entered; the ORB high never broke** | **94** | no day-1 entry existed |
| C — entered day 1, NOT stopped | 4 | 2 still open, 1 trail exit, 1 partial-complete |
| **D — never entered, but the ORB high DID break** | **124** (19 order-cancelled-unfilled, 105 no order) | real, and outside his three buckets — blocked/skipped/unfilled names; reported separately, never guessed into A or B |
| U — unclassifiable | 4 | ALAB, DYN, GH 05-20 (no trade row AND no EP-day minute bars); CRMD 05-14 (manual emergency close — the incident row) |

**Per-group family expectancy (all four rungs, first attempts, MATURE settled fires):**

| group | fires (mature n) | M-none mean / med | M-trail mean / med | ≥4R (none/trail) | monthly M-none mean (n) |
|---|---|---|---|---|---|
| **A — knocked out** | 60 | **−0.71 / −1.00** | −0.39 / −1.00 | **1** / 2 | May −0.83 (24) · Jun −0.32 (15) · Jul −0.87 (21) · Aug unreadable (30 immature) |
| A, strict cut — fires AFTER the day-1 stop date | 44 | −0.61 / −1.00 | −0.23 / −1.00 | 1 / 2 | (24 in-trade-overlap fires excluded) |
| **B — ORB never broke** | 124 | **−0.29 / −1.00** | **+0.01 / −1.00** | **9** / 8 | May −0.06 (55) · Jun −0.48 (45) · Jul −0.46 (24) · Aug unreadable (75 immature) |
| D — broke, no entry | 179 | −0.58 / −1.00 | −0.28 / −1.00 | 6 / 5 | May −0.34 (90) · Jun −0.69 (53) · Jul −1.00 (36) · Aug unreadable (109 immature) |
| C — entered, not stopped | 3 | −1.00 | −0.16 | 0 / 0 | n=3 — too thin, no claim |

Per-rung tables for each group are in `_562sp_table_report.txt`; no rung inside group A is
positive on either arm (best: high-break −0.44, n=5 — too thin for any claim).

**Plain words — the answer to his question is NO:**

- **Delayed entry pays WORST on the names that knocked us out.** Group A is the worst readable
  population on the board: −0.71R per fire, one ≥4R harvest in 60 mature fires (NAVN; M-trail
  adds FTNT +5.5 and KLAR +4.1). Cutting to fires strictly after the stop date (the true
  re-entry read) improves it to −0.61 — still worse than either no-entry group, in every month.
- **The tail lives where day 1 never filled.** B (ORB never broke) is the least bad — M-trail is
  water-line (+0.01) and 9 of the backfill's 18 ≥4R fires are there (TE, GO, BHVN, MMYT, DFTX,
  FET, VPG…). D holds most of the rest (STUB, ANF, ABVX, FPS, ARM). This is the pivot-proximity
  tension measured from the other side: **being knocked out on day 1 is evidence the name has no
  tail, not evidence the tail is still ahead** — consistent with the 08-29 missed-EP finding
  (the stopped cohort was ~93% tail-free), now on a non-outcome-conditioned population 3× the size.
- **His three buckets cover 139 of 267.** The biggest group (D, 124 names — 46% of caught EPs)
  broke its ORB high with no entry existing: MODERATE-tier alerts that never route to entry,
  plus skips/caps/unfilled orders. Not this card's question, but the split he asked for cannot
  be read without knowing that class exists.
- ⚠ **The U hole is not neutral:** ALAB 05-20 — the single biggest winner of the whole backfill
  (+33.9R settled across its two fires) — is one of the three unclassifiable names (no trade
  row, no EP-day minute bars). It belongs to B or D but the bars to decide do not exist; wherever
  it belongs, that group's family sum improves by ~+34R (B's would go from −36R to ≈−2R). Stated,
  not guessed.

## What this says (and the fork)

Q1: **"tighter" is directionally right, but only the bases that survive a gap-over do it.** The
bar-low bases (b, c) are structurally wrong for this rung — the winners gap over the level, so a
low-derived stop kills exactly them. An ADR-fraction below entry (or the EP-day close) keeps
every fire, multiplies the rare gap-over runner, and loses nothing measurable on the bleed —
but the entire case is two May fires, and the operator has ruled May stale.

Q2: **the stopped-out-day-1 population is the wrong target for delayed entry**, on this data —
the worst of the four groups, in every month, on both arms, under a strict after-the-stop cut.

Fork for the operator (evidence only, his call — nothing flipped):

- **(1) High-break stop basis** — if the watch lane's recorded stop should change, the ADR-family
  (0.25–0.50×ADR) or the EP-day close is the candidate set; prior-session-low and the bar-low
  bases are dominated. n(winners)=2 says: change the RECORDED basis in the shadow lane (or record
  both, the schema carries stop width first-class) and let the forward lane accrue — not a live
  value pick. Any rung change is CHANGE_PROCESS + sign-off.
- **(2) Population** — stop pointing delayed-entry design at the knocked-out names; the no-entry
  groups (B and D) are where the recorded tail is. If a selection layer gets built (the
  backfill's fork (b)), group membership is computable on day 1 and this split says B/D-not-A is
  the first cut worth stamping.

## What this does not answer

- **Whether the tight-stop advantage is real or two lucky May fires.** n(winners)=2; June/July
  produced no winner under ANY basis; August is unreadable until ~late September. Only forward
  accrual (or a longer backfill) separates "gap-over monsters recur" from "May regime".
- **The gap-over entry itself.** Under the lane's buy-the-level convention, a killed (b)/(c) fire
  means "no stop exists below the booked entry" — a live trader buying the gap-over OPEN with a
  bar-low stop is a DIFFERENT entry definition (entry above the level), not measured here.
- **August, at all** — 16 of the 48 high-break fires and 32 of group A's 92 fires are immature;
  settled August rows are stops by construction.
- **Whether ALAB/DYN/GH belong to B or D** — no EP-day minute bars exist; the ±34R ambiguity on
  B/D group sums is stated above.
- **Same-day re-entry and the bounded re-entry shapes** — out of the lane's scope, so out of
  this replay's; group A's strict cut covers only day-2+ first attempts.
- **Any management layer beyond the two arms** — the +2R-partial live shape is deliberately not
  an arm (operator 08-30).

## ⚖ THE LINE

Stops, entry/exit discipline, selection rules and sizing are the operator's sole authority. He
said the high-break stop "needs to be tighter" — this document measures bases and brings a
recommendation; it changes no rung, no threshold, no live code. Prod access was read-only
SELECTs captured once to `scripts/probes/_562sp_*.tsv`; the live lane and its tables were not
touched.

---
*Population: the backfill's 267 campaigns / 602 fires (walk reproduced exactly before varying
anything). Q1 rows: `_562sp_stopvariants.tsv` (384 = 48 fires × 8 bases). Q2 rows:
`_562sp_classification.tsv` (267). Hand-verified: VPG +49.45R and ARM +33.75R/+54.72R
reproduced from raw daily bars; entered-pair count ties to `mi_live_trades` (46 = A 41 + C 4 +
CRMD). Related: PLAN #562/#327; `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER` needs
its row for this doc — ledger edit deliberately left to the main session (this card is scoped to
`scripts/probes/` + `docs/analysis/`).*
