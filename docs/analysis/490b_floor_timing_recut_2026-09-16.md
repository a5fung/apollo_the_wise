# #490b — floor timing on never-alerted crossers, re-cut on COMPLETE forward windows (2026-09-16)

**Answer first: relaxing the 09:45 floor still buys nothing. Uncensored, the reachable-and-gated
class produces 1 tail winner in 65 — and that one died on the 60-day cooldown, so under the selector
we actually run it is ZERO. The 2026-08-18 findings hold.**

MEASURE-ONLY, $0, read-only, no threshold proposed. Admission is entry discipline = THE LINE.

## Population — declared before the first measuring query

| | |
|---|---|
| **Cohort** | the 138 never-alerted ticker-days that **faded below +10% at the open and then crossed intraday**, 2026-07-27 → 2026-08-18 — the class the 08-18 read could not settle |
| **Timed subset** | 121 have session minute bars; 17 crossed only on the daily high (sparse prints) and are kept in outcome sets, excluded from timing |
| **Statistic** | `tailx` = 20-session-forward max high vs the EP-day close, in own-ADR units; a tail winner is **≥8×ADR** |
| **Primary rule** | pre-registered on 08-18: ORB-**reachable** = high-water ≥ +10% inside 09:30–09:45 |

**WHAT CHANGED — the censoring, and only the censoring.** On 2026-08-18 every forward window was
incomplete (median 8 of 20 sessions) and every share was explicitly a FLOOR. Now **`fwd_n` median is
20 and 0 of 107 are censored.** Same probe, same captures, matured bars.

**ERA CHECK.** `tailx` is price-only — it asks what the stock did, never how we would have exited —
so the 2026-09-06 exit flip cannot reach it. The cohort closes 08-18, before the 08-19 `MIN_GAP_PCT`
move. Single-era on both axes.

## The result

| set | n | ≥8×ADR | median tailx |
|---|---|---|---|
| reachable (crossed by 09:45), pre-gates | 107 | 4 (3.7%) | 1.70× |
| **reachable AND passing the replayed mechanical gates** | **65** | **1 (1.5%)** | 1.71× |
| unreachable (crossed after 09:45) | 14 | 1 (7.1%) | 3.89× |

**And the one that passed everything died on a gate that has nothing to do with timing.** The class's
**five** winners, each stopped by a different thing:

| | what actually excluded it |
|---|---|
| **ALOY** 07-29, 9.8× | passed every mechanical gate — **killed by the 60-day EP cooldown** (alerted 06-01, 58 days prior) |
| **BCAR** 07-29, 14.7× | market cap $227M, under the $500M floor |
| **MASS** 07-29, 8.5× | market cap $410M, under the $500M floor |
| **AMRC** 07-30, 8.8× | crossed at **09:49** — after the ORB window, so a floor change cannot reach it |
| **FCUV** 08-10, 11.7× | fails **three** gates at once: dollar volume **$0.06M/day**, ATR **53%**, market cap **$8M** |

⚠ **This table said "four winners" when first written, on 2026-09-16. It was five** — I read the
probe's gate-fates block as four rows and stopped one short, and FCUV is the row I dropped. The
probe's own §4 says `winners so far: 5` and its PRIZE line lists FCUV among the not-reachable-and-gated.
Corrected the same evening after an advisor pass. [[check-what-the-system-already-did]]

> **So the prize under the selector we actually run is 0.0 per month, against the alerted book's
> 2 winners over the same window.** Moving the floor-timing rule buys nothing; **three of the five
> winners are a market-cap question, one is a cooldown question, and one crossed too late to reach.**
> **FCUV is the clearest case FOR the floors, not against them**: a $60k-a-day, $8M microcap is
> exactly what the liquidity floors exist to exclude, and he confirmed on 2026-09-16 that they stay.

## Relaxing the boundary dilutes, and it does so monotonically

Every cell pre-registered on 08-18. Moving the cutoff later admits more names and the winner share
stays flat at 3–5% — it never concentrates:

| boundary | no gap floor | ≥3% | ≥5% | ≥8% |
|---|---|---|---|---|
| 09:35 | 3/65 (5%) | 1/56 (2%) | 1/39 (3%) | 0/14 (0%) |
| **09:45 (live)** | **4/107 (4%)** | 2/78 (3%) | 1/48 (2%) | 0/14 (0%) |
| 10:00 | 5/118 (4%) | 3/84 (4%) | 2/51 (4%) | 0/14 (0%) |
| close | 5/121 (4%) | 3/86 (3%) | 2/51 (4%) | 0/14 (0%) |

## Separability at 09:45 is chance — and four of six features are WORSE than chance

Do decision-time features rank the eventual winners above the class? AUC over 121 names, 5 winners:

| feature | AUC |
|---|---|
| ADR% | 0.58 |
| position in ORB | 0.44 |
| open gap | 0.42 |
| extension % | 0.19 |
| relative volume at 09:45 | 0.18 |
| prior close vs 20-day max | 0.12 |

**An AUC below 0.5 means the feature ranks the winners BELOW the class.** Three of them are far
below. There is no decision-time signal here to build an earlier admission on — which is the same
conclusion 08-18 reached at AUC 0.47–0.52, now on complete data and with the sign made explicit.

## What this does not answer

- **The 08-18 read's own upper bound stands:** the catalyst grade, RVOL pace and top-20 rank cap were
  never replayed ($0 limit), so 65 is a ceiling on would-have-alerted and the real number is smaller.
  Zero out of a ceiling is zero out of every subset, so this strengthens the conclusion.
- ⚠ **Two probes disagree on the alerted book and neither is corrected here.** This one reports **2**
  tail winners for the alerted population over the window; `490_delayed_screen_cost_recut_2026-09-15`
  reports **3 of 103**. The cohorts are built differently (this counts the crosser-alerted subset,
  that one all live alerts on the cohort dates). **Stated rather than reconciled — do not quote one
  against the other without rebuilding both denominators.**
- **The market-cap floor and the 60-day cooldown are now the live questions for this class**, and
  neither is what this review was gated on. **Three of five** winners failed `mcap` (BCAR, MASS,
  FCUV), one failed cooldown, one crossed post-ORB. FCUV additionally failed the ADV and ATR floors,
  so it is not a market-cap question alone.
  Both are detection criteria = THE LINE; nothing is proposed here.
- `tailx` says what the stock did, not what we would have made. No entry, exit or size is modelled.
