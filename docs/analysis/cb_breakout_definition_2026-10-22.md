# #705 — was our breakout trigger early, and does a REAL base-high / expansion breakout follow through? (2017–21 and 2022–24; read 2026-10-22)

**MEASUREMENT ONLY. $0, local data, no network. Nothing here changes or proposes to change a strategy, an entry or exit rule,
a stop, a size, a safeguard or any live trade state — those are the operator's (THE LINE). Every number describes what the
stocks did around fixed, pre-stated definitions; no definition below is picked over another.**

**The sealed 2025–26 table is untouched.** No 2025–26 file was opened; bars after 2024-12-31 were dropped at load, before any computation, and no post-cut value enters
any number (asserted; every window that does not fit before the cut is flagged incomplete and excluded from
that horizon's number). The registered RS-leadership read on 2025–26 stays unspent.

His ruling, verbatim (2026-10-22): *"'When a big move comes, it starts 5–6 weeks after entry' this points to wrong entry, the whole
point of breakout is that it has broken the consolidation period and enter the expansion phase, if this is happening 5-6 weeks
after then the entry is not a breakout by definition."* Earlier: *"on breakout day, we're not looking for tightness, we're looking
for the opposite, range expansion (up)"*; breakouts *"can happen anytime"* in the day.

> **⚠ SCOPE (updated 2026-10-22, after the stop / re-entry read):** the breakout-vs-ordinary-stock comparisons on this page
> measure the stock's DRIFT over 5–60 sessions. Risk / reward AT THE ENTRY with the stop was measured the same night in
> `cb_entry_stop_retry_2026-10-22.md`. On daily bars, entered at the breakout close with the same stop on both sides, the breakout
> reaches +5R before its stop no more often than matched ordinary stocks: 17.8% vs 18.7% (1-ADR stop, 2017–21), 13.6% vs 13.7%
> (2022–24), and 14.8% vs 14.9% / 10.4% vs 10.4% at 1.5 ADR. What is NOT measured: the intraday (opening-range) entry against a
> control, and any FILTERED subset (his A+ / graded picks). So the plain-words lead below means "on daily bars, the unfiltered
> breakout entry carries no drift or race edge over ordinary stocks" — not "breakouts have no edge" (his 10-22 correction).

## 0. The answer, in plain words (rewritten 2026-10-22 after two independent verifiers and a main-loop check; §V lists every correction; the definitions in §D were frozen before the build)

- **(1) Was our trigger early? Yes, by his definition.**
  - Our fill sits a median 1.16 / 1.26 ADR BELOW the base high (8% of fills are at or above it).
  - The stock then closes above the base high within 60 sessions on 76% / 70% of fills: a median 6 sessions after our fill, and
    on average about 2 weeks (10.6 / 12.2 sessions).
  - For the stocks that made a +5 ADR move, the +5 ADR mark came on average about 3.5 weeks after that close (17.6 / 17.0
    sessions; medians do not add, so the means carry the split). Most of the "5–6 weeks" is travel time after the base high is
    cleared, not waiting for it.
  - That big movers cleared the base high first is close to forced by the geometry. The +5 ADR mark sits about 4 ADR above the
    base high, so it is not evidence either way.
- **(2) Does a REAL breakout, by his definition, follow through more than ordinary stocks? On daily bars and unfiltered, no — not in
  the direction that pays** (and no race edge at the same stop, per the scope note above; filtered subsets are untested). Every row below is the finer match (same day, same volatility decile, same prior 3-month strength).
  - **R1, a close above the base high, entered at that close:**
    - the share reaching +5 ADR within 60 sessions is +1.1 / +0.6 points over the matched control, intervals spanning zero;
    - mean returns are no different at 1 / 5 / 20 sessions;
    - the next open reads the same.

    As an ENTRY, clearing the base high adds nothing over matched ordinary stocks.
  - **R2, that close on an expansion day** (range ≥ 1 ADR, close in the top 30%, volume ≥ 1.5× the 50-day). These stocks move
    MORE IN BOTH DIRECTIONS, not more up (main-loop check `05_main_loop_two_sided.py`, from the entry close, within 60 sessions):

    | Era | Up +5 ADR: R2 vs control | Down −3 ADR | Down −5 ADR | Mean 60-session return |
    |---|---|---|---|---|
    | 2017–21 (n = 1,564) | 44.9% vs 41.1% | 58.1% vs 51.9% | 31.7% vs 28.0% | +0.92 vs +0.92 |
    | 2022–24 (n = 922) | 35.5% vs 34.6% | 61.9% vs 60.7% | 38.4% vs 35.5% | +0.09 vs −0.02 |

    The extra early up-movers (+5 ADR within 5 sessions 4.6% vs 2.3%) are matched by extra down-movers, and the mean is flat.
    It is volatility, not follow-through.
  - **R3, our own fills whose trigger day is an expansion day** (n = 531 / 376): the same shape, thinner.
  - **The level variants** (k5 / k10 / full / tl / com): all within +0.5 to +1.5 points of the control at +5 ADR. The intraday
    push over the base high (`full`) reads like the close over it (R1).
- **So:** our trigger does fire before the base breaks, as he says. But on daily bars, neither our trigger nor a breakout that
  meets his definition — the base high cleared, even on a wide, high-volume up day — picks stocks that go UP more than ordinary
  stocks of the same volatility and the same prior strength. The breakout event adds no direction beyond the strength the stock
  already had. The only small drift is the prior strength itself: +0.31 ADR over 60 sessions in 2017–21 against a
  volatility-only match, gone once strength is matched (the R decomposition doc §2).
- **Action: none from this data (THE LINE).** What the entry IS stays his call; nothing was flipped and no definition is picked.
  Two things decide next:
  - selection by Qullamaggie's own stream grades (bought / best vs "needs a few more days"; PLAN #705, outcome-free extraction
    first, then a registered read);
  - the held RS-alone read on the sealed 2025–26, which ranks picks on our early trigger and waits on this result.

## D. Definitions — FIXED BEFORE ANY OUTCOME WAS COMPUTED (this section is frozen; results sit below it)

The four questions of the standard, answered first:
1. **Decision served:** whether the C0 `tl` ORH5 trigger is the breakout his definition names, or an earlier point in the base —
   and whether an entry that meets his definition (a close above the base high, a range-expansion day) follows through more than
   ordinary stocks. The decision itself (what the entry IS) is his.
2. **What would change it:** if the stocks clear the base high soon after our fill and the +5 ADR moves come a long time AFTER that
   clearing, the 5–6 weeks is the travel time of a +5 ADR threshold, not an early entry; if the clearing itself comes weeks after
   our fill, his reading holds. If R1/R2 entries beat their matched control on the tail (+5 / +10 ADR within 60) with intervals
   clear of zero and our fills do not, the entry definition is the lever; if neither does, selection is.
3. **Population:** below (§M). 4. **What would make this wrong:** an entry that CONDITIONS on an up day (R1/R2) is compared with a
   control that does not — a same-day effect that matching at t−1 cannot remove; the "from t+1's close" rows are the check.

**Sessions.** The session calendar is SPY's. D = the watch night; **E = D+1 = session 0** of our trade. "Within k sessions after E" =
sessions 1..k. "E itself" = session 0, always its own row.

**Base high** = `pivot_full` of the watch row at D (`explain_watch`: the highest high of the base sessions (P, D]); fixed at D,
never updated. ADR20 at D = the watch row's `adr20` (mean (high − low)/close over the 20 sessions ending D, a fraction).

**Question A (our fills).** Population = the published C0 `tl` ORH5 `pp` MATURE fills (13,363 / 8,984), retrigger rows included
as published. Per fill: **distance** = (pivot_full − fill) / (ADR20_D × fill), negative when the fill is already above the base
high. **s_c** = the first session s ∈ 0..60 (from E) whose CLOSE > pivot_full (strict); "never" = no such close by session 60
(and the window complete). **s\*** = yesterday's `first_5adr` / `first_10adr` (the first session 1..60 whose HIGH ≥ fill × (1 + T ×
ADR20_D)). For the big movers (s\* exists): s_c ≤ s\* = the base high was cleared on a close at or before the move's start; s_c > s\*
= the move started before any close above the base high; no s_c = never cleared on a close within 60. Reported: the
distribution of s_c, of s\* − s_c, and of s_c vs s\* (a tie s_c = s\* counts as "at or before").

**Question B — the entries (ALL reported, NONE picked).**
- **R1 base-high close:** on the same bases (one row per published fill), the first session t in E..D+60 (sessions 0..59 from E)
  whose CLOSE > pivot_full (strict). Entry = that close c_t; beside it, the next open o_{t+1}. ADR unit for every R1/R2 number =
  **ADR20 at t−1** (what the control is matched on). The next-open variant measures (c_{t+k} − o_{t+1}) / (ADR × o_{t+1}) with the
  horizons still counted from t, and reports the gap (o_{t+1} − c_t) / (ADR × c_t) beside.
- **R2 expansion breakout:** R1's day t also has (high_t − low_t)/close_t ≥ 1.0 × ADR20_{t−1}; (close_t − low_t)/(high_t − low_t) ≥
  0.70 (fails when high = low); volume_t ≥ 1.5 × mean volume over the 50 sessions [t−50, t−1] (requires all 50 bars). R2 = all
  three; the R1 rows failing R2 are reported beside; each sub-test's pass share is composition.
- **R3 our own trigger day, split:** our fills whose E day meets the same three tests — (high_E − low_E)/close_E ≥ 1.0 × ADR20_D,
  close location ≥ 0.70, volume_E ≥ 1.5 × mean volume over [E−50, E−1] — vs those that do not. Entry = E's close (the control's
  base); ADR unit = ADR20_D.
- **K level variants:** the entry tables' ORH5 `filled` rows with `C0 = 1`, `retrigger = 0` (the spec key's first break) for
  K = k5 / k10 / full / tl (2022–24, `entries_discovery.tsv.gz`); 2017–21 holds only `tl` (= the population) and `com`
  (`entries_pre_tl_com.tsv.gz`), said so. Entry = E's close; ADR unit = ADR20_D (the watch row's).
- **Dedup:** every NEW entry set (R1, R2, each K) is one row per (ticker, entry day); the count removed is stated. Question A keeps
  the published rows.
- **Forward measures from the entry close c_t** (control identical): close return at +1 / +5 / +20 / +60 sessions = (c_{t+k} − c_t) /
  (ADR × c_t); the share whose HIGH reached c_t × (1 + 5 × ADR) / (1 + 10 × ADR) within (t, t+60]; the first such session (s\*);
  the cumulative share reaching +5 ADR by sessions 5 / 20 / 60 (the additive "how soon"); the median s\* (entries directly; the
  control's pooled over the matched cells, weighted by the entries' cell counts — never an average of cell medians). A horizon
  counts only when t+k ≤ the last readable session (complete flags).
- **The matched control** (built exactly like yesterday's `02_build_paths.py`): on each entry day t, every export ticker with — at
  t−1 — adjusted close ≥ $5, 20-session median close × volume ≥ $10M, 130 consecutive sessions, ticker `^[A-Z]{1,5}$`; tickers in
  ANY entry set on t or with a watch row at t−1 excluded. One pass per era over the union of entry dates. Matching: each entry's
  control value = the control's mean in its own (t, ADR20 decile) cell — deciles cut on THAT entry set — and, as the second control,
  (t, decile, 63-session-return quintile at t−1); an empty cell falls back to (t, decile), then to t. Intervals: month-block
  bootstrap of the per-entry (entry − matched control) difference, calendar month of t, 2,000 resamples, seed 702.
- **Composition before any rate:** n, era, entry-date count, ADR20 mix (median, decile cuts), 63-session return, dollar volume,
  dedup counts, split flags (2022–24 `cb702_splits.psv`: entries with a split inside [t−50, t] are counted and R2 is shown without them).
- **Tail first, then mean:** every table lists +5 / +10 ADR shares before the close returns.

## 1. Question A — was our trigger early? (n on every row; generated by `03_report.py`)

| era | n fills | fill distance below the base high (ADR20 at D): median | quartiles | p10 / p90 | fill already at/above the base high | E's own close above it (s_c = 0) | trendline level below the base high, median (ADR) |
|---|---|---|---|---|---|---|---|
| 2017-21 | n = 13,363 | 1.16 | 0.41 .. 2.14 | 0.03 / 3.13 | 1,098 (8.2%) | 1,548 (11.6%) | 1.35 |
| 2022-24 | n = 8,956 | 1.26 | 0.46 .. 2.23 | 0.05 / 3.25 | 703 (7.8%) | 1,016 (11.3%) | 1.45 |

First CLOSE above the base high (E = session 0; cumulative; "never" needs the 60-session window complete):

| era | n (window complete) | on E itself | by session 5 | by session 20 | by session 60 | never within 60 | window cut (unknown) |
|---|---|---|---|---|---|---|---|
| 2017-21 | n = 13,363 | 1,548 (11.6%) | 4,989 (37.3%) | 8,110 (60.7%) | 10,214 (76.4%) | 3,149 (23.6%) | 0 |
| 2022-24 | n = 8,047 | 890 (11.1%) | 2,633 (32.7%) | 4,289 (53.3%) | 5,627 (69.9%) | 2,420 (30.1%) | 909 |

Sessions from our fill to that first close above the base high (where it happened within 60): 2017–21 n = 10,214, median 6,
quartiles 1..17, p90 33, 48.8% within 5 sessions, 79.4% within 20; 2022–24 n = 5,627, median 6, quartiles 1..19, p90 38, 46.8% / 76.2%.

The big movers (s\* = yesterday's first session 1..60 whose HIGH reached fill + T × ADR20; window complete):

| era / threshold | n big movers | closed above the base high at or before s\* | move started before any close above it | never closed above it within 60 | fill → first close above the base high (s_c): median / quartiles | that close → the move (s\* − s_c): median / quartiles | fill → move (s\*): median | s_c ≤ 5 | s_c ≤ 20 |
|---|---|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR | n = 5,756 | 5,675 (98.6%) | 57 (1.0%) | 24 (0.4%) | 6 / 2 .. 15 | 13 / 5 .. 27 | 26 | 49.6% | 82.1% |
| 2017-21, +10 ADR | n = 1,855 | 1,855 (100.0%) | 0 | 0 | 5 / 1 .. 12 | 30 / 16 .. 41 | 40 | 52.9% | 87.3% |
| 2022-24, +5 ADR | n = 2,829 | 2,773 (98.0%) | 36 (1.3%) | 20 (0.7%) | 7 / 2 .. 18 | 13 / 4 .. 26 | 28 | 44.5% | 77.6% |
| 2022-24, +10 ADR | n = 808 | 807 (99.9%) | 1 (0.1%) | 0 | 6 / 2 .. 16 | 25 / 14 .. 38 | 38 | 48.1% | 82.8% |

The fills that never made a +5 ADR move still closed above the base high within 60 on 4,482 of 7,607 (58.9%, 2017–21) and 2,818 of
5,218 (54.0%, 2022–24). By how far below the base high the fill sat (quartiles cut per era), the +5 ADR rate is flat — 2017–21:
43.2 / 44.5 / 44.9 / 39.6% (n = 3,341 each); 2022–24: 34.7 / 33.6 / 36.0 / 36.3% (n = 2,012 each) — while the share that later
clears the base high falls from 94% / 90% (nearest quarter) to 53% / 47% (deepest quarter). The generated table is at the end.

## 2. Question B — does a REAL breakout follow through? (finer match: same day × ADR20 decile × 63-session-return quintile; the ADR-only match and every other row are in the generated tables)

Tail first. "+5 by 5" = the share whose high reached +5 ADR within 5 sessions of the entry (the additive "how soon"); the 60-session
shares need a complete window (smaller n in 2022–24 where the window crosses the 2024-12-31 cut). Intervals: month-block bootstrap,
seed 702, 2,000. Composition of every set (n, entry days, ADR20, 63-session return, dollar volume, dedup, the sub-tests' pass
shares, splits) is in the generated composition tables; the volume test is the binding one (passes 11.5% of our E days, 28% / 32% of
R1 days).

**2017–21**

| entry | n | ≥ 5 ADR within 60: entry vs control (diff, interval) | ≥ 10 ADR within 60 | +5 ADR by session 5 | by session 20 | mean close return +1 (ADR) | +5 | +20 | +60 | median start of the +5 ADR move (big movers; control pooled) |
|---|---|---|---|---|---|---|---|---|---|---|
| our fills (from E's close) | n = 13,363 | 43.2% vs 42.4% (+0.9, −0.8..+2.6) | 13.9% vs 13.4% (+0.5, −0.4..+1.6) | 1.7% vs 1.9% (−0.1, −0.5..+0.2) | 16.0% vs 15.9% (+0.1) | −0.013 (−0.028..+0.001) | −0.015 (−0.059..+0.029) | +0.03 (−0.09..+0.14) | +0.16 (−0.03..+0.36) | 27 vs 26 (n = 5,776) |
| R3: E is an expansion day | n = 531 | 43.1% vs 38.0% (+5.1, +1.1..+9.3) | 14.9% vs 12.4% (+2.5, −0.9..+5.7) | 3.6% vs 2.3% (+1.3, −0.7..+3.4) | 17.3% vs 15.4% (+1.9, −2.1..+5.9) | −0.112 (−0.231..+0.001) | +0.010 (−0.26..+0.29) | −0.06 (−0.42..+0.30) | +0.19 (−0.34..+0.73) | 25 vs 26 (n = 229) |
| R3: E is not | n = 12,832 | 43.2% vs 42.5% (+0.8, −0.9..+2.5) | 13.8% vs 13.4% (+0.4, −0.4..+1.5) | 1.7% vs 1.8% (−0.2) | 15.9% vs 15.9% (+0.0) | −0.008 | −0.014 | +0.04 | +0.17 (−0.03..+0.37) | 27 vs 26 (n = 5,547) |
| R1 base-high close, entry at that close | n = 9,281 | 43.6% vs 42.6% (+1.1, −0.7..+2.9) | 14.8% vs 13.3% (+1.5, +0.6..+2.5) | 2.5% vs 1.8% (+0.7, +0.2..+1.3) | 16.4% vs 15.2% (+1.2, −0.6..+2.8) | +0.003 (−0.015..+0.022) | +0.017 (−0.03..+0.07) | +0.03 (−0.07..+0.14) | +0.18 (+0.00..+0.39) | 26 vs 27 (n = 4,050) |
| R1, entry at the next open | n = 9,281 | 42.8% vs 42.0% (+0.8, −1.1..+2.8) | 14.6% vs 13.1% (+1.5, +0.6..+2.4) | 1.9% vs 1.5% (+0.4, −0.1..+0.8) | 15.5% vs 14.7% (+0.9, −1.0..+2.6) | −0.012 (−0.027..+0.005) | +0.003 | +0.02 | +0.16 (−0.01..+0.38) | 27 vs 28 (n = 3,972) |
| R1, measured from the NEXT close | n = 9,281 | 43.6% vs 42.7% (+0.9, −1.0..+2.6) | 14.9% vs 13.3% (+1.5, +0.5..+2.7) | 2.3% vs 1.8% (+0.5, +0.1..+1.0) | 16.5% vs 15.2% (+1.3, −0.3..+2.7) | −0.017 | +0.024 | +0.04 | +0.15 (−0.03..+0.36) | 26 vs 27 (n = 4,044) |
| **R2 expansion breakout, entry at that close** | n = 1,582 | **44.9% vs 41.8% (+3.1, +0.6..+5.5)** | **16.6% vs 14.1% (+2.4, +0.5..+4.5)** | **4.6% vs 2.3% (+2.3, +0.9..+3.7)** | **18.6% vs 15.5% (+3.1, +0.5..+5.7)** | −0.054 (−0.107..+0.003) | +0.030 (−0.10..+0.15) | −0.02 (−0.22..+0.20) | −0.01 (−0.34..+0.34) | 25 vs 26 (n = 710) |
| R2, entry at the next open | n = 1,582 | 43.8% vs 41.4% (+2.4, −0.2..+4.8) | 16.4% vs 13.7% (+2.8, +1.1..+4.6) | 3.4% vs 1.9% (+1.5, +0.5..+2.6) | 18.2% vs 15.0% (+3.2, +0.7..+5.6) | −0.063 (−0.110..−0.012) | +0.022 | −0.02 | −0.02 (−0.34..+0.33) | 24 vs 27 (n = 693) |
| R2, measured from the NEXT close | n = 1,582 | 44.4% vs 42.1% (+2.3, −0.6..+4.9) | 16.4% vs 13.9% (+2.6, +0.8..+4.3) | 3.6% vs 2.0% (+1.6, +0.6..+2.8) | 18.3% vs 15.3% (+3.0, +0.7..+5.0) | −0.035 (−0.107..+0.030) | +0.065 (−0.04..+0.17) | +0.03 | +0.03 (−0.30..+0.37) | 25 vs 27 (n = 702) |
| R1 but NOT R2, entry at that close | n = 7,699 | 43.4% vs 42.7% (+0.7, −1.3..+2.7) | 14.5% vs 13.1% (+1.4, +0.4..+2.4) | 2.0% vs 1.7% (+0.3, −0.2..+0.9) | 15.9% vs 15.1% (+0.8, −1.0..+2.6) | +0.015 (−0.003..+0.035) | +0.018 | +0.05 | +0.22 (+0.02..+0.45) | 27 vs 27 (n = 3,340) |
| K = tl, ORH5 first break (= the population + 5 non-mature) | n = 13,368 | 43.2% vs 42.4% (+0.9) | 13.9% vs 13.4% (+0.5) | 1.7% vs 1.9% (−0.1) | 16.0% vs 15.9% (+0.1) | −0.013 | −0.015 | +0.03 | +0.16 (−0.03..+0.36) | 27 vs 26 |
| K = com, ORH5 first break (2017–21 holds no k5 / k10 / full) | n = 15,630 | 43.9% vs 42.4% (+1.5, −0.3..+3.2) | 14.4% vs 13.4% (+1.0, +0.1..+1.9) | 1.8% vs 1.8% (+0.1) | 16.3% vs 15.8% (+0.5) | −0.012 | −0.029 | +0.08 | +0.20 (+0.04..+0.38) | 26 vs 27 (n = 6,860) |

**2022–24**

| entry | n (60-window / 5-window) | ≥ 5 ADR within 60 | ≥ 10 ADR within 60 | +5 ADR by session 5 | by session 20 | mean close return +1 | +5 | +20 | +60 | median start of the +5 ADR move |
|---|---|---|---|---|---|---|---|---|---|---|
| our fills (from E's close) | n = 8,047 / 8,889 | 35.2% vs 34.7% (+0.5, −0.9..+2.2) | 10.2% vs 9.8% (+0.4, −0.5..+1.6) | 1.9% vs 1.5% (+0.4, +0.1..+0.8) | 13.5% vs 13.5% (+0.1) | +0.002 | +0.011 | −0.00 | +0.18 (−0.06..+0.45) | 28 vs 27 (n = 2,832) |
| R3: E is an expansion day | n = 338 / 375 | 36.1% vs 32.7% (+3.4, −1.5..+8.6) | 11.2% vs 9.2% (+2.1, −1.8..+6.9) | 4.3% vs 1.8% (+2.5, +0.7..+4.6) | 16.7% vs 12.9% (+3.7, +0.0..+7.5) | −0.020 (−0.109..+0.081) | −0.051 | +0.15 (−0.17..+0.51) | +0.09 (−0.76..+1.16) | 22 vs 27 (n = 122) |
| R3: E is not | n = 7,709 / 8,514 | 35.2% vs 34.7% (+0.4) | 10.1% vs 9.8% (+0.4) | 1.8% vs 1.5% (+0.3, −0.1..+0.7) | 13.4% vs 13.5% (−0.1) | +0.002 | +0.013 | −0.01 | +0.19 (−0.05..+0.45) | 28 vs 27 (n = 2,710) |
| R1 base-high close, entry at that close | n = 4,934 / 5,510 | 35.2% vs 34.6% (+0.6, −1.0..+2.8) | 10.7% vs 10.1% (+0.6, −0.5..+1.8) | 2.3% vs 1.8% (+0.5, −0.0..+0.9) | 15.4% vs 14.1% (+1.3, +0.3..+2.2) | −0.012 (−0.035..+0.008) | −0.050 (−0.091..−0.007) | +0.02 | +0.04 (−0.24..+0.35) | 26 vs 26 (n = 1,736) |
| R1, entry at the next open | n = 4,934 / 5,510 | 35.0% vs 34.4% (+0.7, −1.2..+3.0) | 10.6% vs 9.9% (+0.7, −0.3..+1.8) | 1.9% vs 1.6% (+0.4, −0.0..+0.8) | 15.1% vs 13.8% (+1.3, +0.3..+2.3) | −0.008 | −0.045 (−0.084..−0.003) | +0.03 | +0.05 | 26 vs 27 (n = 1,728) |
| R1, measured from the NEXT close | n = 4,928 / 5,508 | 35.6% vs 34.6% (+1.0, −0.8..+3.1) | 10.5% vs 10.1% (+0.4, −0.6..+1.6) | 2.4% vs 1.8% (+0.6, +0.1..+1.1) | 15.5% vs 13.9% (+1.6, +0.4..+2.6) | −0.010 | −0.044 (−0.091..+0.009) | +0.02 | +0.05 | 26 vs 27 (n = 1,754) |
| **R2 expansion breakout, entry at that close** | n = 927 / 1,073 | 35.6% vs 34.5% (+1.1, −1.7..+3.8) | 12.5% vs 10.7% (+1.8, −0.3..+4.1) | **3.8% vs 2.1% (+1.7, +0.5..+3.0)** | **17.4% vs 14.4% (+3.0, +1.0..+5.2)** | −0.061 (−0.159..+0.027) | −0.062 (−0.17..+0.06) | +0.10 (−0.07..+0.28) | +0.13 (−0.31..+0.63) | 23 vs 27 (n = 330) |
| R2, entry at the next open | n = 927 / 1,073 | 35.8% vs 34.3% (+1.5, −1.7..+4.7) | 12.5% vs 10.5% (+2.0, +0.0..+4.1) | 3.2% vs 1.7% (+1.5, +0.4..+2.6) | 17.8% vs 13.9% (+3.8, +1.7..+6.0) | −0.022 | −0.024 | +0.14 (−0.04..+0.32) | +0.15 (−0.27..+0.63) | 22 vs 27 (n = 332) |
| R2, measured from the NEXT close | n = 926 / 1,072 | 37.5% vs 34.2% (+3.3, +0.6..+6.0) | 11.9% vs 10.4% (+1.5, −0.5..+3.4) | 3.1% vs 1.7% (+1.4, +0.3..+2.5) | 17.5% vs 13.7% (+3.8, +1.9..+6.1) | +0.017 | −0.020 | +0.18 (+0.01..+0.37) | +0.08 (−0.40..+0.61) | 24 vs 27 (n = 347) |
| R2 without the 2 rows with a split in the volume window (15 R1 rows flagged) | n = 925 / 1,071 | 35.6% vs 34.5% (+1.1) | 12.4% vs 10.7% (+1.8) | 3.8% vs 2.1% (+1.8, +0.5..+3.0) | 17.4% vs 14.3% (+3.1, +1.0..+5.3) | −0.060 | −0.058 | +0.11 | +0.13 | 23 vs 27 |
| R1 but NOT R2, entry at that close | n = 4,007 / 4,437 | 35.1% vs 34.7% (+0.4, −1.4..+2.5) | 10.3% vs 9.8% (+0.5, −0.6..+1.7) | 1.9% vs 1.8% (+0.1) | 14.9% vs 14.0% (+0.9, −0.3..+2.1) | −0.000 | −0.053 (−0.093..−0.008) | +0.03 | +0.01 | 26 vs 27 (n = 1,406) |
| K = full, ORH5 first break (fill at/above the base high by construction) | n = 3,671 / 4,078 | 35.5% vs 34.6% (+0.9, −0.9..+3.0) | 10.4% vs 10.1% (+0.2, −0.9..+1.5) | 1.8% vs 1.5% (+0.3, −0.2..+0.8) | 14.1% vs 13.7% (+0.4) | +0.003 | −0.007 | +0.02 | +0.14 (−0.17..+0.46) | 27 vs 27 (n = 1,303) |
| K = k10 | n = 6,636 / 7,226 | 36.6% vs 35.1% (+1.5, +0.1..+3.2) | 10.5% vs 9.7% (+0.8, −0.1..+2.0) | 1.8% vs 1.5% (+0.3, −0.1..+0.6) | 14.7% vs 14.1% (+0.6) | −0.006 | −0.023 | −0.01 | +0.23 (−0.05..+0.55) | 27 vs 26 (n = 2,428) |
| K = k5 | n = 8,133 / 8,941 | 36.0% vs 34.8% (+1.2, −0.0..+2.5) | 10.4% vs 9.6% (+0.8, +0.0..+1.8) | 1.7% vs 1.5% (+0.2) | 13.9% vs 13.5% (+0.4) | +0.000 | +0.005 | +0.05 | +0.27 (+0.04..+0.52) | 27 vs 27 (n = 2,930) |
| K = tl (= the population + 5 non-mature) | n = 8,050 / 8,894 | 35.2% vs 34.7% (+0.5) | 10.2% vs 9.8% (+0.4) | 2.0% vs 1.5% (+0.4, +0.1..+0.8) | 13.5% vs 13.4% (+0.1) | +0.003 | +0.013 | −0.00 | +0.18 (−0.06..+0.45) | 28 vs 27 |

**Reading the tables, tail first.** The only rows whose tail intervals clear zero in BOTH eras are R2's early shares (+5 ADR by
session 5 and by session 20). R2's 60-session tail clears zero in 2017–21 only; R1's +10 ADR share clears zero in 2017–21 only
(+1.5 points) and reads +0.6 in 2022–24. No row has a mean close return above its control with an interval clear of zero except
R2 from the next close at +20 in 2022–24 (+0.18, +0.01..+0.37) and the +60 drifts that our own fills already show; R2's own next
day reads slightly NEGATIVE (−0.05 / −0.06 ADR, intervals touching zero). The big movers' +5 ADR mark arrives a median 22–25
sessions after an R2 entry against 26–27 for the control — R2 adds early movers at the margin; it does not change when the typical
big move lands. The level variants cannot be told from the control (k10 at +5 ADR is the one interval clear of zero, +1.5 points,
on a different population from `tl`).

## M. Method and population

**Population:** the PUBLISHED C0 row — `trades_pre_exitpb.tsv.gz` (2017–21) and `trades_discovery_exitpb.tsv.gz` (2022–24), rows
`arm = pp`, `entry = orh5`, `K = tl`, `C0 = 1`, `mature = 1`: **n = 13,363 and n = 8,984** (watch nights 2017-03-01..2021-12-31,
fills 2017-03-02..2022-01-03; watch nights 2022-03-28..2024-12-31, fills 2022-04-01..2025-01-02), reproduced first with the
published mean R (+0.0254 / −0.1691) and ≥ 10R counts (165 / 85) to the printed digit (`01_reproduce.txt`: MATCH both eras), then
taken from yesterday's per-fill table (`r_decomp_fills_<era>.tsv.gz`, 13,363 / 8,956 rows with a readable E bar; the 28 fills of
2025-01-02 have none). Retrigger rows are in, as published (2,352 / 1,658). The watch row joins 1:1 on (ticker, D) for every fill;
`pivot_full` ≥ `pivot_tl` ≥ … holds on every row; the watch row's `adr20` equals the trade table's within 1e-5 (6-digit text) and
is the full-precision value used. The K-variant populations are the entry tables' ORH5 `filled` rows with `C0 = 1`, `retrigger = 0`
(`entries_discovery.tsv.gz`: k5 9,034 / k10 7,280 / full 4,100 / tl 8,989 — tl equals the population plus the 5 non-mature fills;
`entries_pre_tl_com.tsv.gz`: tl 13,368 / com 15,630; 2017–21 holds no k5 / k10 / full), minus the 62 rows whose E lies after the
cut; no duplicate (ticker, E) in any K.

**Bars and windows** (`02_build.py`): each era's `daily_closes_all.csv.gz` (Alpaca split-adjusted daily bars; 2017–21:
2016-01-04..2022-06-30; 2022–24: cut to ≤ 2024-12-31 at load, asserted). Session calendar = SPY's dates. ONE function measures
every entry set and the control (`Frame.measure`): from the base price, the window (t, t+60] in sessions, returns at t+1 / 5 / 20
/ 60, the running max of the highs for the +5 / +10 ADR shares and the first session reaching them, complete flags per horizon.
Applied to our fills from E's close with ADR20 at D it reproduces yesterday's `ret5/20/60_adr_close` and `mfe60_adr_close` to the
6-digit text rounding (max abs diff 5e-5 .. 4e-4) and `complete_60` exactly. Exact ties (a close equal to the base high) are
compared at the bar frame's float32 precision so that strict `>` is strict (a first build read 1–1.3% of sampled fills' ties as
"above"; fixed, rebuilt). s_c, R1, R2, R3 and the K rows are as §D defines them; the R1 scan window is sessions 0..59 from E;
`r1_scan_complete` / `sc_complete` flag fills whose window crosses the cut (909 / 384 in 2022–24; 0 in 2017–21).

**The control** (`02_build.py`, the same conventions as yesterday's `02_build_paths.py`): one pass per era over the union of entry
days (1,236 / 684 days); on each day t every export ticker with — at t−1 — adjusted close ≥ $5, 20-session median dollar volume
≥ $10M, 130 consecutive sessions, ticker `^[A-Z]{1,5}$`; tickers in ANY entry set on t or with a watch row at t−1 excluded
(193,821 / 129,971 ticker-days). On yesterday's E dates the rows are yesterday's rows minus the 1,603 / 1,120 tickers now excluded
as an R1 / K entry, and the shared rows' numbers agree to the text rounding. Deviations from the setup's own filter are yesterday's
(adjusted close in place of the raw close; security type not in the export). Matching: each entry's control value = the control's
mean in its own (t, ADR20 decile) cell, deciles cut on THAT entry set, and (t, decile, 63-session-return quintile at t−1); an empty
cell falls back to (t, decile) (the "fell back" column; none fell back to the day alone). The ADR unit of every R1 / R2 number is
ADR20 at t−1 — the control's; our fills, R3 and the K rows use ADR20 at D = t−1, the same thing. Intervals: month-block bootstrap
of the per-entry (entry − matched control) difference, calendar month of the entry day, 2,000 resamples, seed 702. The control's
median start session is pooled over the entries' (t, decile, quintile) cells, weighted by the entries' cell counts (a weighted
median over control rows, never an average of cell medians).

**Files.** Probes: `scripts/probes/_702_breakout_definition_1022/01_reproduce.py` (+ `.txt`), `02_build.py` (+
`02_build_checks*.txt`, `02_build_run_*.log`), `03_report.py` (+ `03_report.md` = every table, `03_numbers.json`, `03_report_run.log`),
`04_main_loop_checks.py` (+ `.txt`). Tables: `apollo_data/cb702_pre/out/bdef_{fills,r1,kvar,control}_2017-21.tsv.gz` and
`apollo_data/cb702/out/bdef_{fills,r1,kvar,control}_2022-24.tsv.gz`. Nothing pinned was written or moved; the runner and the
once-only stages were neither run nor imported; no 2025–26 file was opened; no network.

## L. What this does not answer

- **Whether an R2 entry makes money as a trade.** No stop, size or exit was walked on R1 / R2 (the measures are the stock's path from
  the entry close, as yesterday's). An entry's R needs its own stop, and the stop is his (`analysis_standard.md`, "a new setup's
  entry and exit are undetermined"). A registered read of R2 with a stated stop would answer it; this doc does not draft one.
- **The same-day conditioning is only partly removed.** R1 / R2 condition on an up close; the control does not. The 63-session-return
  match at t−1 and the "from the next open / next close" rows bound the effect (the R2 lift survives both), but a residual
  same-week momentum effect in the control's favour or against cannot be excluded.
- **R2's three thresholds (1.0 ADR, top 30%, 1.5× volume) are the brief's, not tuned, and not his** — a looser or tighter expansion
  test was not run; the volume test is the binding one (28–32% of R1 days pass it) and 2017–21 has no splits file (the 2022–24 split
  flag removes 2 R2 rows and changes nothing).
- **Selection beyond C0.** Every set is the C0 population or derived from it; C1 and the stricter cells are not re-read.
- **Anything about 2025–26.** Unread by design (the sealed table).
- **Day-0 intraday moves** are invisible to daily bars (as yesterday); the R3 flags read E's whole day, including the part before the
  fill.
- **The K rows are different populations, not the same bases under four levels** (1,487 / 3,322 / 4,860 bases shared with `tl`); a
  tl-vs-k5 difference is the level AND the population.
- **The com row (2017–21)** is the center-of-mass level, not a `PIVOT_KEYS` level; reported because the era's entry table holds it.

## N. What decides next (a read, not a rule) — ⚖ THE LINE

Nothing here is a rule change or a recommendation to change the entry, the stop, the exit, the sizing or the strategy; what the
breakout entry IS is the operator's call, and no definition above is picked. The registered read that decides next is the pending
**RS-leadership-alone read on the sealed 2025–26** (selection; `cb_rs_alone_prereg_2026-10-22.md`, PLAN #705). An entry-definition
read — R2 as the trigger, with a stop he states, scored in ADR and account percent on these two eras — has no registration; whether
to write one is his.

## V. Verification (2026-10-22)

- **Two defects found and fixed before any number was read as final:** (1) the first R1 table carried the fills' E-close measure
  columns under the same `cl_*` names as R1's own, so the first "R1 at that close" row read a measure conditioned on a future event
  (56% at +5 ADR); every table now asserts unique columns and the R1 table has one set (13). (2) exact ties at the base high read as
  "above" through a float32/float64 mismatch; fixed to a float32 comparison and rebuilt (s_c changed on about 1% of rows).
- **Main loop, own code** (`04_main_loop_checks.py`, from the raw export, no builder import): `pivot_full` equals the max high over
  (P, D] on 300 random fills per era (0 mismatches); s_c and the +5 ADR share recomputed from raw closes / highs on 300 random
  fills per era (0 / 0); ADR20 at t−1, the R2 flag and the +5 ADR share recomputed on 300 random R1 rows per era (0 / 0); the R2
  finer-matched difference at +5 ADR within 60 recomputed by a merge: +3.10 / +1.07 points (report +3.10 / +1.07); R2 by session 5:
  4.62% vs 2.32% / 3.85% vs 2.09% (report 4.61 vs 2.31 / 3.82 vs 2.08).
- **Two independent verifiers (2026-10-22, recount + adversarial logic), both `holds_with_corrections`, every number reproduced;
  corrections applied above:**
  - (material) R2's lift is two-sided — the lead now says volatility, not follow-through, with the downside rows (main-loop
    `05_main_loop_two_sided.py` / `.txt`);
  - (material) the 98.6% / 98.0% "cleared before the move" is mechanical (the +5 ADR mark sits about 4 ADR above the base high) —
    no longer cited as evidence; strictly before (not a same-session tie) it is about 6.7% / 9.2% lower;
  - (material) the 5–6-week split is stated with means (10.6 / 12.2 then 17.6 / 17.0 sessions), since medians do not add;
  - (material) "not a selector" now rests on Question B (R1 vs control), not on the never-moved share;
  - (minor) the median-start-session row is uninformative (a capped first-reach time) and is dropped from the lead;
  - (minor) the exclusion counts are corrected (193,821 / 129,971; 1,603 / 1,120);
  - (minor) the header's export wording;
  - (minor) `04_main_loop_checks.py`'s hardcoded comparison values were stale (the recount itself matches).
- **Reproduction of yesterday:** the fills' close-based measures and the control rows on the shared dates agree to the text rounding
  (`02_build_checks.txt`); the population, the watch join and the K counts are in `01_reproduce.txt`.

---

## Generated tables (`03_report.py`, verbatim; n on every row)

### 2017-21

#### A. Was our trigger early? (2017-21; n = 13,363 published fills with a readable E bar)

| era | n fills | fill distance below the base high (ADR20 at D): median | quartiles | p10 / p90 | fill already at/above the base high | E's own close above it (s_c = 0) | trendline level below the base high, median (ADR) |
|---|---|---|---|---|---|---|---|
| 2017-21 | n = 13,363 | 1.16 | 0.41 .. 2.14 | 0.03 / 3.13 | 1,098 (8.2%) | 1,548 (11.6%) | 1.35 |

First CLOSE above the base high (E = session 0; cumulative; 'never' needs the 60-session window complete):

| era | n (window complete) | on E itself | by session 5 | by session 20 | by session 60 | never within 60 | window cut (unknown) |
|---|---|---|---|---|---|---|---|
| 2017-21 | n = 13,363 | 1,548 (11.6%) | 4,989 (37.3%) | 8,110 (60.7%) | 10,214 (76.4%) | 3,149 (23.6%) | 0 |

Sessions from our fill (E) to that first close above the base high, where it happened within 60:

| era | n | median | quartiles | p90 | share at s_c <= 5 | <= 20 |
|---|---|---|---|---|---|---|
| 2017-21 | n = 10,214 | 6 | 1 .. 17 | 33 | 48.8% | 79.4% |

The big movers (s\* = yesterday's first session 1..60 whose HIGH reached fill + T x ADR20; 60-session window complete): did the stock clear the base high on a close first, and how long from that close to the move?

| era / threshold | n big movers | closed above the base high at or before s\* (s_c <= s\*) | move started before any close above it (s_c > s\*) | never closed above it within 60 | fill -> first close above base high (s_c): median / quartiles | that close -> the move (s\* - s_c): median / quartiles | fill -> move (s\*): median | s_c <= 5 | s_c <= 20 |
|---|---|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR | n = 5,756 | 5,675 (98.6%) | 57 (1.0%) | 24 (0.4%) | 6 / 2 .. 15 | 13 / 5 .. 27 | 26 | 49.6% of those | 82.1% |
| 2017-21, +10 ADR | n = 1,855 | 1,855 (100.0%) | 0 (0.0%) | 0 (0.0%) | 5 / 1 .. 12 | 30 / 16 .. 41 | 40 | 52.9% of those | 87.3% |

Same, for the fills that never made the move (A bin): how often did they still clear the base high on a close?

| era | n fills with no +5 ADR move within 60 | closed above the base high within 60 | never |
|---|---|---|---|
| 2017-21 | n = 7,607 | 4,482 (58.9%) | 3,125 (41.1%) |

Where the fill sat vs the move rate (distance below the base high in ADR20 at D, quartiles cut on this era; from the fill, yesterday's columns):

| era | distance quartile | n (window complete) | >= 5 ADR within 60 | >= 10 ADR | mean R | closed above the base high within 60 |
|---|---|---|---|---|---|---|
| 2017-21 | Q1 <= 0.41 (at/near the base high) | n = 3,341 | 43.2% | 14.3% | -0.092 | 93.8% |
| 2017-21 | Q2 0.41-1.16 | n = 3,341 | 44.5% | 14.0% | +0.139 | 84.7% |
| 2017-21 | Q3 1.16-2.14 | n = 3,340 | 44.9% | 14.5% | +0.076 | 74.2% |
| 2017-21 | Q4 > 2.14 (deep in the base) | n = 3,341 | 39.6% | 12.6% | -0.021 | 53.0% |

#### B. Does a REAL breakout follow through? (2017-21; every entry against its matched control; tail first)

Composition of the entry sets (one row per (ticker, entry day) for the new sets):

| era | entry set | n | entry days | median ADR20 (unit) | median 63-session return at t-1 | median 20-session dollar volume | notes |
|---|---|---|---|---|---|---|---|
| 2017-21 | our fills (C0 tl ORH5, from E's close) | n = 13,363 | 1176 | 0.0412 | +0.204 | $38M | published rows; retrigger_chain = 1: 2,352 |
| 2017-21 | R3 — E meets the expansion test | n = 531 | 356 | 0.0450 | +0.203 | $41M | range >= 1 ADR: 4,762 (35.6%); close in top 30%: 5,810 (43.5%); volume >= 1.5x: 1,540 (11.5%) |
| 2017-21 | R3 — E does NOT meet it | n = 12,832 | 1172 | 0.0411 | +0.204 | $38M | |
| 2017-21 | R1 base-high close (ADR20 at t-1) | n = 9,281 | 1102 | 0.0379 | +0.221 | $38M | from 10,192 fills reaching a close above the base high in sessions 0..59; dedup removed 911; R1 day = E itself 1,351 (14.6%); median s_c 6; close over the base high median 0.33 ADR; next-open gap median +0.04 ADR; splits in the volume window unknown |
| 2017-21 | R2 expansion breakout (R1 + range/close/volume) | n = 1,582 | 696 | 0.0400 | +0.209 | $34M | range >= 1 ADR: 5,690 (61.3%); close in top 30%: 6,647 (71.6%); volume >= 1.5x: 2,605 (28.1%); R2 day = E itself 219 |
| 2017-21 | R1 but NOT R2 | n = 7,699 | 1054 | 0.0375 | +0.224 | $39M | |
| 2017-21 | K = com (ORH5 first break, from E's close) | n = 15,630 | 1189 | 0.0409 | +0.192 | $38M | fill below the base high: median 1.20 ADR; fill at/above it 4.6%; includes the 5 non-mature fills |
| 2017-21 | K = tl (ORH5 first break, from E's close) | n = 13,368 | 1177 | 0.0412 | +0.204 | $38M | fill below the base high: median 1.16 ADR; fill at/above it 8.2%; includes the 5 non-mature fills |

**our fills (from E's close) — composition.** n = 13,363 over 1176 entry days; control rows on those days 2,232,143. ADR20 (the entry's unit): median 0.0412, decile cuts [0.025, 0.0298, 0.0336, 0.0374, 0.0412, 0.0455, 0.0511, 0.0593, 0.0744]; 63-session return quintile cuts [0.01, 0.15, 0.259, 0.428] (entries' median +0.204 vs the pooled control's +0.020).

| 2017-21: our fills (from E's close) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 13,363 | 43.22% | 42.07% | 1.15% | -0.63% .. 2.84% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 13,363 | 13.85% | 13.10% | 0.75% | -0.19% .. 1.85% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 13,363 | 1.74% | 1.77% | -0.03% | -0.35% .. 0.27% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 13,363 | 15.97% | 15.75% | 0.21% | -0.79% .. 1.38% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 13,362 | +0.008 | +0.017 | -0.009 | -0.027 .. +0.008 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 13,357 | +0.151 | +0.147 | +0.004 | -0.055 .. +0.062 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 13,342 | +0.477 | +0.426 | +0.051 | -0.085 .. +0.181 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 13,260 | +1.229 | +0.917 | +0.311 | +0.112 .. +0.539 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 13,363 | 43.22% | 42.35% | 0.87% | -0.80% .. 2.60% | 171 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 13,363 | 13.85% | 13.35% | 0.50% | -0.35% .. 1.55% | 171 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 13,363 | 1.74% | 1.86% | -0.12% | -0.47% .. 0.20% | 171 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 13,363 | 15.97% | 15.87% | 0.09% | -0.98% .. 1.29% | 171 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 13,362 | +0.008 | +0.021 | -0.013 | -0.028 .. +0.001 | 171 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 13,357 | +0.151 | +0.166 | -0.015 | -0.059 .. +0.029 | 171 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 13,342 | +0.477 | +0.446 | +0.031 | -0.086 .. +0.141 | 172 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 13,260 | +1.229 | +1.066 | +0.163 | -0.026 .. +0.364 | 181 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 5,776 entries / 185,045 control rows | 27 | 26 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 1,851 / 57,332 | 40 | 39 | - | - | - |

**R3: E meets the expansion test — composition.** n = 531 over 356 entry days; control rows on those days 671,784. ADR20 (the entry's unit): median 0.0450, decile cuts [0.0268, 0.0324, 0.037, 0.04, 0.045, 0.0509, 0.0572, 0.067, 0.0858]; 63-session return quintile cuts [0.026, 0.152, 0.256, 0.457] (entries' median +0.203 vs the pooled control's +0.020).

| 2017-21: R3: E meets the expansion test | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 531 | 43.13% | 39.35% | 3.77% | -0.47% .. 7.99% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 531 | 14.88% | 13.32% | 1.56% | -1.59% .. 4.60% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 531 | 3.58% | 2.28% | 1.30% | -0.76% .. 3.46% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 531 | 17.33% | 15.63% | 1.69% | -2.45% .. 5.84% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 531 | -0.084 | +0.035 | -0.119 | -0.245 .. -0.000 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 531 | +0.086 | +0.101 | -0.016 | -0.278 .. +0.248 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 531 | +0.175 | +0.336 | -0.161 | -0.506 .. +0.179 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 529 | +0.565 | +0.330 | +0.235 | -0.278 .. +0.741 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 531 | 43.13% | 38.04% | 5.08% | 1.12% .. 9.31% | 10 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 531 | 14.88% | 12.39% | 2.49% | -0.86% .. 5.74% | 10 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 531 | 3.58% | 2.30% | 1.28% | -0.73% .. 3.39% | 10 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 531 | 17.33% | 15.40% | 1.92% | -2.06% .. 5.87% | 10 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 531 | -0.084 | +0.028 | -0.112 | -0.231 .. +0.001 | 10 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 531 | +0.086 | +0.076 | +0.010 | -0.258 .. +0.286 | 10 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 531 | +0.175 | +0.234 | -0.059 | -0.419 .. +0.298 | 10 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 529 | +0.565 | +0.378 | +0.187 | -0.336 .. +0.725 | 11 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 229 entries / 9,980 control rows | 25 | 26 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 79 / 3,168 | 32 | 36 | - | - | - |

**R3: E does not meet it — composition.** n = 12,832 over 1172 entry days; control rows on those days 2,224,603. ADR20 (the entry's unit): median 0.0411, decile cuts [0.025, 0.0297, 0.0335, 0.0372, 0.0411, 0.0453, 0.0508, 0.059, 0.0738]; 63-session return quintile cuts [0.01, 0.15, 0.259, 0.428] (entries' median +0.204 vs the pooled control's +0.020).

| 2017-21: R3: E does not meet it | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 12,832 | 43.23% | 42.14% | 1.08% | -0.65% .. 2.77% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 12,832 | 13.81% | 13.07% | 0.74% | -0.21% .. 1.83% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 12,832 | 1.66% | 1.74% | -0.08% | -0.37% .. 0.19% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 12,832 | 15.91% | 15.74% | 0.18% | -0.78% .. 1.31% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 12,831 | +0.012 | +0.016 | -0.005 | -0.023 .. +0.013 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 12,826 | +0.154 | +0.147 | +0.007 | -0.049 .. +0.061 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 12,811 | +0.489 | +0.426 | +0.064 | -0.077 .. +0.198 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 12,731 | +1.256 | +0.937 | +0.319 | +0.119 .. +0.545 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 12,832 | 43.23% | 42.45% | 0.78% | -0.89% .. 2.52% | 160 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 12,832 | 13.81% | 13.39% | 0.42% | -0.44% .. 1.47% | 160 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 12,832 | 1.66% | 1.83% | -0.17% | -0.50% .. 0.14% | 160 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 12,832 | 15.91% | 15.87% | 0.05% | -1.00% .. 1.22% | 160 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 12,831 | +0.012 | +0.019 | -0.008 | -0.023 .. +0.008 | 160 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 12,826 | +0.154 | +0.168 | -0.014 | -0.055 .. +0.025 | 160 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 12,811 | +0.489 | +0.450 | +0.039 | -0.080 .. +0.153 | 161 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 12,731 | +1.256 | +1.087 | +0.169 | -0.025 .. +0.373 | 170 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 5,547 entries / 181,592 control rows | 27 | 26 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 1,772 / 56,188 | 40 | 39 | - | - | - |

**R1 base-high close — entry at that close — composition.** n = 9,281 over 1102 entry days; control rows on those days 2,096,517. ADR20 (the entry's unit): median 0.0379, decile cuts [0.0228, 0.0272, 0.0309, 0.0343, 0.0379, 0.0419, 0.0467, 0.0542, 0.0652]; 63-session return quintile cuts [0.051, 0.172, 0.268, 0.41] (entries' median +0.221 vs the pooled control's +0.020).

| 2017-21: R1 base-high close — entry at that close | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 9,281 | 43.64% | 42.52% | 1.12% | -1.21% .. 3.31% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 9,281 | 14.84% | 13.34% | 1.49% | 0.68% .. 2.49% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 9,281 | 2.47% | 1.77% | 0.69% | 0.20% .. 1.24% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 9,281 | 16.39% | 15.37% | 1.01% | -0.89% .. 2.78% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 9,281 | +0.024 | +0.019 | +0.005 | -0.015 .. +0.024 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 9,279 | +0.131 | +0.101 | +0.030 | -0.020 .. +0.084 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 9,258 | +0.352 | +0.327 | +0.024 | -0.114 .. +0.165 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 9,191 | +1.250 | +0.960 | +0.290 | +0.074 .. +0.540 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 9,281 | 43.64% | 42.55% | 1.09% | -0.69% .. 2.92% | 100 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 9,281 | 14.84% | 13.34% | 1.50% | 0.64% .. 2.47% | 100 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 9,281 | 2.47% | 1.78% | 0.69% | 0.18% .. 1.26% | 100 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 9,281 | 16.39% | 15.21% | 1.18% | -0.56% .. 2.80% | 100 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 9,281 | +0.024 | +0.021 | +0.003 | -0.015 .. +0.022 | 100 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 9,279 | +0.131 | +0.113 | +0.017 | -0.030 .. +0.071 | 101 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 9,258 | +0.352 | +0.319 | +0.033 | -0.072 .. +0.141 | 101 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 9,191 | +1.250 | +1.075 | +0.175 | +0.001 .. +0.390 | 104 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 4,050 entries / 132,931 control rows | 26 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 1,377 / 40,841 | 39 | 39 | - | - | - |

**R1 — entry at the next open — composition.** n = 9,281 over 1102 entry days; control rows on those days 2,096,517. ADR20 (the entry's unit): median 0.0379, decile cuts [0.0228, 0.0272, 0.0309, 0.0343, 0.0379, 0.0419, 0.0467, 0.0542, 0.0652]; 63-session return quintile cuts [0.051, 0.172, 0.268, 0.41] (entries' median +0.221 vs the pooled control's +0.020).

| 2017-21: R1 — entry at the next open | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 9,281 | 42.80% | 41.99% | 0.81% | -1.57% .. 3.19% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 9,281 | 14.55% | 13.07% | 1.48% | 0.59% .. 2.51% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 9,281 | 1.87% | 1.49% | 0.38% | -0.01% .. 0.82% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 9,281 | 15.52% | 14.80% | 0.72% | -1.43% .. 2.64% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 9,281 | -0.040 | -0.024 | -0.016 | -0.029 .. -0.001 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 9,279 | +0.067 | +0.059 | +0.009 | -0.043 .. +0.066 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 9,258 | +0.290 | +0.285 | +0.004 | -0.141 .. +0.152 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 9,191 | +1.185 | +0.916 | +0.269 | +0.049 .. +0.521 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 9,281 | 42.80% | 41.97% | 0.82% | -1.08% .. 2.78% | 100 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 9,281 | 14.55% | 13.09% | 1.45% | 0.62% .. 2.44% | 100 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 9,281 | 1.87% | 1.50% | 0.37% | -0.05% .. 0.83% | 100 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 9,281 | 15.52% | 14.66% | 0.86% | -1.03% .. 2.58% | 100 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 9,281 | -0.040 | -0.028 | -0.012 | -0.027 .. +0.005 | 100 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 9,279 | +0.067 | +0.065 | +0.003 | -0.046 .. +0.058 | 101 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 9,258 | +0.290 | +0.270 | +0.019 | -0.090 .. +0.132 | 101 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 9,191 | +1.185 | +1.024 | +0.161 | -0.014 .. +0.382 | 104 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 3,972 entries / 131,570 control rows | 27 | 28 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 1,350 / 40,101 | 39 | 40 | - | - | - |

**R1 — measured from the NEXT close (same-day-effect check) — composition.** n = 9,281 over 1102 entry days; control rows on those days 2,096,517. ADR20 (the entry's unit): median 0.0379, decile cuts [0.0228, 0.0272, 0.0309, 0.0343, 0.0379, 0.0419, 0.0467, 0.0542, 0.0652]; 63-session return quintile cuts [0.051, 0.172, 0.268, 0.41] (entries' median +0.221 vs the pooled control's +0.020).

| 2017-21: R1 — measured from the NEXT close (same-day-effect check) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 9,281 | 43.57% | 42.56% | 1.02% | -1.36% .. 3.30% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 9,281 | 14.87% | 13.36% | 1.51% | 0.50% .. 2.67% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 9,281 | 2.28% | 1.79% | 0.50% | 0.07% .. 0.98% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 9,281 | 16.49% | 15.37% | 1.11% | -0.73% .. 2.75% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 9,280 | +0.019 | +0.032 | -0.013 | -0.041 .. +0.015 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 9,277 | +0.132 | +0.096 | +0.036 | -0.020 .. +0.094 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 9,256 | +0.362 | +0.327 | +0.035 | -0.118 .. +0.185 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 9,191 | +1.220 | +0.959 | +0.261 | +0.036 .. +0.516 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 9,281 | 43.57% | 42.72% | 0.85% | -0.98% .. 2.59% | 100 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 9,281 | 14.87% | 13.33% | 1.54% | 0.53% .. 2.65% | 100 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 9,281 | 2.28% | 1.80% | 0.48% | 0.06% .. 0.98% | 100 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 9,281 | 16.49% | 15.19% | 1.29% | -0.32% .. 2.74% | 100 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 9,280 | +0.019 | +0.036 | -0.017 | -0.044 .. +0.010 | 101 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 9,277 | +0.132 | +0.108 | +0.024 | -0.023 .. +0.077 | 100 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 9,256 | +0.362 | +0.319 | +0.043 | -0.068 .. +0.157 | 101 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 9,191 | +1.220 | +1.072 | +0.148 | -0.025 .. +0.362 | 105 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 4,044 entries / 133,276 control rows | 26 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 1,380 / 41,202 | 39 | 39 | - | - | - |

**R2 expansion breakout — entry at that close — composition.** n = 1,582 over 696 entry days; control rows on those days 1,319,411. ADR20 (the entry's unit): median 0.0400, decile cuts [0.0248, 0.0292, 0.033, 0.0366, 0.04, 0.0445, 0.0508, 0.0593, 0.0737]; 63-session return quintile cuts [0.052, 0.162, 0.262, 0.423] (entries' median +0.209 vs the pooled control's +0.020).

| 2017-21: R2 expansion breakout — entry at that close | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 1,582 | 44.88% | 41.66% | 3.22% | 0.32% .. 5.96% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 1,582 | 16.56% | 14.03% | 2.53% | 0.62% .. 4.45% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 1,582 | 4.61% | 2.27% | 2.34% | 0.85% .. 3.73% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 1,582 | 18.58% | 15.70% | 2.89% | 0.19% .. 5.57% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 1,582 | -0.030 | +0.016 | -0.045 | -0.104 .. +0.013 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 1,582 | +0.117 | +0.080 | +0.037 | -0.087 .. +0.159 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 1,580 | +0.330 | +0.346 | -0.016 | -0.217 .. +0.194 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 1,569 | +0.922 | +0.836 | +0.086 | -0.259 .. +0.457 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 1,582 | 44.88% | 41.78% | 3.10% | 0.55% .. 5.54% | 25 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 1,582 | 16.56% | 14.13% | 2.43% | 0.52% .. 4.46% | 25 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 1,582 | 4.61% | 2.31% | 2.31% | 0.87% .. 3.71% | 25 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 1,582 | 18.58% | 15.47% | 3.11% | 0.50% .. 5.70% | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 1,582 | -0.030 | +0.024 | -0.054 | -0.107 .. +0.003 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 1,582 | +0.117 | +0.087 | +0.030 | -0.095 .. +0.153 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 1,580 | +0.330 | +0.346 | -0.016 | -0.217 .. +0.200 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 1,569 | +0.922 | +0.933 | -0.011 | -0.338 .. +0.344 | 26 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 710 entries / 33,199 control rows | 25 | 26 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 262 / 10,770 | 38 | 39 | - | - | - |

**R2 — entry at the next open — composition.** n = 1,582 over 696 entry days; control rows on those days 1,319,411. ADR20 (the entry's unit): median 0.0400, decile cuts [0.0248, 0.0292, 0.033, 0.0366, 0.04, 0.0445, 0.0508, 0.0593, 0.0737]; 63-session return quintile cuts [0.052, 0.162, 0.262, 0.423] (entries' median +0.209 vs the pooled control's +0.020).

| 2017-21: R2 — entry at the next open | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 1,582 | 43.81% | 41.38% | 2.43% | -0.49% .. 5.12% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 1,582 | 16.43% | 13.71% | 2.73% | 1.04% .. 4.49% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 1,582 | 3.41% | 1.89% | 1.53% | 0.43% .. 2.64% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 1,582 | 18.20% | 15.13% | 3.08% | 0.49% .. 5.66% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 1,582 | -0.080 | -0.017 | -0.063 | -0.110 .. -0.013 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 1,582 | +0.069 | +0.049 | +0.020 | -0.101 .. +0.133 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 1,580 | +0.281 | +0.313 | -0.032 | -0.224 .. +0.166 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 1,569 | +0.871 | +0.801 | +0.070 | -0.276 .. +0.435 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 1,582 | 43.81% | 41.40% | 2.41% | -0.23% .. 4.84% | 25 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 1,582 | 16.43% | 13.67% | 2.76% | 1.08% .. 4.55% | 25 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 1,582 | 3.41% | 1.90% | 1.51% | 0.50% .. 2.58% | 25 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 1,582 | 18.20% | 14.98% | 3.23% | 0.67% .. 5.58% | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 1,582 | -0.080 | -0.017 | -0.063 | -0.110 .. -0.012 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 1,582 | +0.069 | +0.047 | +0.022 | -0.096 .. +0.140 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 1,580 | +0.281 | +0.305 | -0.024 | -0.226 .. +0.179 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 1,569 | +0.871 | +0.889 | -0.018 | -0.340 .. +0.327 | 26 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 693 entries / 33,093 control rows | 24 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 260 / 10,629 | 38 | 39 | - | - | - |

**R2 — measured from the NEXT close (same-day-effect check) — composition.** n = 1,582 over 696 entry days; control rows on those days 1,319,411. ADR20 (the entry's unit): median 0.0400, decile cuts [0.0248, 0.0292, 0.033, 0.0366, 0.04, 0.0445, 0.0508, 0.0593, 0.0737]; 63-session return quintile cuts [0.052, 0.162, 0.262, 0.423] (entries' median +0.209 vs the pooled control's +0.020).

| 2017-21: R2 — measured from the NEXT close (same-day-effect check) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 1,582 | 44.37% | 41.82% | 2.56% | -0.66% .. 5.59% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 1,582 | 16.43% | 13.95% | 2.48% | 0.72% .. 4.15% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 1,582 | 3.60% | 2.11% | 1.49% | 0.40% .. 2.68% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 1,582 | 18.27% | 15.64% | 2.63% | 0.38% .. 4.86% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 1,581 | -0.015 | +0.017 | -0.032 | -0.108 .. +0.037 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 1,582 | +0.147 | +0.086 | +0.060 | -0.058 .. +0.166 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 1,580 | +0.376 | +0.352 | +0.023 | -0.158 .. +0.212 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 1,569 | +0.910 | +0.814 | +0.096 | -0.258 .. +0.472 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 1,582 | 44.37% | 42.13% | 2.25% | -0.59% .. 4.87% | 25 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 1,582 | 16.43% | 13.85% | 2.58% | 0.83% .. 4.30% | 25 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 1,582 | 3.60% | 1.96% | 1.64% | 0.59% .. 2.80% | 25 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 1,582 | 18.27% | 15.32% | 2.95% | 0.65% .. 5.02% | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 1,581 | -0.015 | +0.021 | -0.035 | -0.107 .. +0.030 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 1,582 | +0.147 | +0.081 | +0.065 | -0.044 .. +0.165 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 1,580 | +0.376 | +0.348 | +0.028 | -0.164 .. +0.222 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 1,569 | +0.910 | +0.884 | +0.026 | -0.304 .. +0.372 | 26 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 702 entries / 33,646 control rows | 25 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 260 / 10,866 | 37 | 39 | - | - | - |

**R1 but NOT R2 — entry at that close — composition.** n = 7,699 over 1054 entry days; control rows on those days 2,003,729. ADR20 (the entry's unit): median 0.0375, decile cuts [0.0226, 0.0268, 0.0304, 0.0338, 0.0375, 0.0415, 0.0461, 0.053, 0.0638]; 63-session return quintile cuts [0.05, 0.175, 0.269, 0.408] (entries' median +0.224 vs the pooled control's +0.020).

| 2017-21: R1 but NOT R2 — entry at that close | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 7,699 | 43.38% | 42.68% | 0.71% | -1.73% .. 3.12% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 7,699 | 14.48% | 13.26% | 1.22% | 0.33% .. 2.32% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 7,699 | 2.03% | 1.67% | 0.35% | -0.10% .. 0.91% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 7,699 | 15.94% | 15.33% | 0.61% | -1.36% .. 2.44% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 7,699 | +0.035 | +0.019 | +0.016 | -0.005 .. +0.035 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 7,697 | +0.134 | +0.103 | +0.030 | -0.015 .. +0.080 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 7,678 | +0.356 | +0.322 | +0.035 | -0.116 .. +0.191 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 7,622 | +1.317 | +0.989 | +0.329 | +0.096 .. +0.601 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 7,699 | 43.38% | 42.72% | 0.66% | -1.27% .. 2.70% | 91 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 7,699 | 14.48% | 13.11% | 1.37% | 0.44% .. 2.44% | 91 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 7,699 | 2.03% | 1.71% | 0.32% | -0.19% .. 0.90% | 91 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 7,699 | 15.94% | 15.13% | 0.80% | -1.03% .. 2.59% | 91 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 7,699 | +0.035 | +0.019 | +0.015 | -0.003 .. +0.035 | 91 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 7,697 | +0.134 | +0.115 | +0.018 | -0.026 .. +0.072 | 92 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 7,678 | +0.356 | +0.307 | +0.049 | -0.072 .. +0.178 | 92 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 7,622 | +1.317 | +1.100 | +0.217 | +0.024 .. +0.451 | 96 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 3,340 entries / 111,142 control rows | 27 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 1,115 / 33,589 | 39 | 40 | - | - | - |

**K = com (ORH5 first break, from E's close) — composition.** n = 15,630 over 1189 entry days; control rows on those days 2,258,904. ADR20 (the entry's unit): median 0.0409, decile cuts [0.0252, 0.0298, 0.0335, 0.037, 0.0409, 0.0453, 0.0506, 0.0585, 0.0722]; 63-session return quintile cuts [0.004, 0.137, 0.246, 0.407] (entries' median +0.192 vs the pooled control's +0.020).

| 2017-21: K = com (ORH5 first break, from E's close) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 15,630 | 43.89% | 41.97% | 1.92% | -0.02% .. 3.68% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 15,630 | 14.36% | 13.12% | 1.24% | 0.32% .. 2.37% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 15,630 | 1.81% | 1.69% | 0.12% | -0.18% .. 0.41% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 15,630 | 16.31% | 15.63% | 0.68% | -0.31% .. 1.79% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 15,628 | +0.012 | +0.022 | -0.010 | -0.027 .. +0.008 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 15,621 | +0.111 | +0.122 | -0.011 | -0.078 .. +0.052 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 15,604 | +0.450 | +0.356 | +0.094 | -0.043 .. +0.223 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 15,508 | +1.316 | +0.955 | +0.362 | +0.169 .. +0.571 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 15,630 | 43.89% | 42.37% | 1.52% | -0.27% .. 3.17% | 192 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 15,630 | 14.36% | 13.41% | 0.95% | 0.12% .. 1.89% | 192 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 15,630 | 1.81% | 1.76% | 0.05% | -0.25% .. 0.35% | 192 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 15,630 | 16.31% | 15.81% | 0.50% | -0.54% .. 1.61% | 192 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 15,628 | +0.012 | +0.024 | -0.012 | -0.027 .. +0.002 | 192 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 15,621 | +0.111 | +0.140 | -0.029 | -0.085 .. +0.023 | 192 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 15,604 | +0.450 | +0.369 | +0.081 | -0.038 .. +0.191 | 196 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 15,508 | +1.316 | +1.112 | +0.204 | +0.041 .. +0.377 | 201 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 6,860 entries / 210,362 control rows | 26 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 2,244 / 64,716 | 40 | 39 | - | - | - |

**K = tl (ORH5 first break, from E's close) — composition.** n = 13,368 over 1177 entry days; control rows on those days 2,234,202. ADR20 (the entry's unit): median 0.0412, decile cuts [0.025, 0.0298, 0.0336, 0.0374, 0.0412, 0.0455, 0.0511, 0.0593, 0.0744]; 63-session return quintile cuts [0.01, 0.15, 0.259, 0.428] (entries' median +0.204 vs the pooled control's +0.020).

| 2017-21: K = tl (ORH5 first break, from E's close) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 13,368 | 43.22% | 42.07% | 1.14% | -0.65% .. 2.83% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 13,368 | 13.85% | 13.10% | 0.75% | -0.19% .. 1.84% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 13,368 | 1.74% | 1.77% | -0.03% | -0.35% .. 0.27% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 13,368 | 15.97% | 15.76% | 0.22% | -0.78% .. 1.38% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 13,367 | +0.008 | +0.017 | -0.009 | -0.027 .. +0.008 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 13,360 | +0.151 | +0.147 | +0.005 | -0.055 .. +0.062 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 13,343 | +0.477 | +0.425 | +0.052 | -0.085 .. +0.182 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 13,260 | +1.229 | +0.917 | +0.312 | +0.112 .. +0.539 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 13,368 | 43.22% | 42.36% | 0.86% | -0.82% .. 2.59% | 172 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 13,368 | 13.85% | 13.36% | 0.49% | -0.37% .. 1.54% | 172 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 13,368 | 1.74% | 1.86% | -0.13% | -0.47% .. 0.20% | 172 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 13,368 | 15.97% | 15.87% | 0.10% | -0.97% .. 1.31% | 172 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 13,367 | +0.008 | +0.021 | -0.013 | -0.028 .. +0.001 | 172 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 13,360 | +0.151 | +0.166 | -0.015 | -0.059 .. +0.030 | 172 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 13,343 | +0.477 | +0.446 | +0.032 | -0.086 .. +0.143 | 173 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 13,260 | +1.229 | +1.068 | +0.161 | -0.029 .. +0.363 | 182 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 5,777 entries / 185,039 control rows | 27 | 26 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 1,851 / 57,336 | 40 | 39 | - | - | - |

### 2022-24

#### A. Was our trigger early? (2022-24; n = 8,956 published fills with a readable E bar)

| era | n fills | fill distance below the base high (ADR20 at D): median | quartiles | p10 / p90 | fill already at/above the base high | E's own close above it (s_c = 0) | trendline level below the base high, median (ADR) |
|---|---|---|---|---|---|---|---|
| 2022-24 | n = 8,956 | 1.26 | 0.46 .. 2.23 | 0.05 / 3.25 | 703 (7.8%) | 1,016 (11.3%) | 1.45 |

First CLOSE above the base high (E = session 0; cumulative; 'never' needs the 60-session window complete):

| era | n (window complete) | on E itself | by session 5 | by session 20 | by session 60 | never within 60 | window cut (unknown) |
|---|---|---|---|---|---|---|---|
| 2022-24 | n = 8,047 | 890 (11.1%) | 2,633 (32.7%) | 4,289 (53.3%) | 5,627 (69.9%) | 2,420 (30.1%) | 909 |

Sessions from our fill (E) to that first close above the base high, where it happened within 60:

| era | n | median | quartiles | p90 | share at s_c <= 5 | <= 20 |
|---|---|---|---|---|---|---|
| 2022-24 | n = 5,627 | 6 | 1 .. 19 | 38 | 46.8% | 76.2% |

The big movers (s\* = yesterday's first session 1..60 whose HIGH reached fill + T x ADR20; 60-session window complete): did the stock clear the base high on a close first, and how long from that close to the move?

| era / threshold | n big movers | closed above the base high at or before s\* (s_c <= s\*) | move started before any close above it (s_c > s\*) | never closed above it within 60 | fill -> first close above base high (s_c): median / quartiles | that close -> the move (s\* - s_c): median / quartiles | fill -> move (s\*): median | s_c <= 5 | s_c <= 20 |
|---|---|---|---|---|---|---|---|---|---|
| 2022-24, +5 ADR | n = 2,829 | 2,773 (98.0%) | 36 (1.3%) | 20 (0.7%) | 7 / 2 .. 18 | 13 / 4 .. 26 | 28 | 44.5% of those | 77.6% |
| 2022-24, +10 ADR | n = 808 | 807 (99.9%) | 1 (0.1%) | 0 (0.0%) | 6 / 2 .. 16 | 25 / 14 .. 38 | 38 | 48.1% of those | 82.8% |

Same, for the fills that never made the move (A bin): how often did they still clear the base high on a close?

| era | n fills with no +5 ADR move within 60 | closed above the base high within 60 | never |
|---|---|---|---|
| 2022-24 | n = 5,218 | 2,818 (54.0%) | 2,400 (46.0%) |

Where the fill sat vs the move rate (distance below the base high in ADR20 at D, quartiles cut on this era; from the fill, yesterday's columns):

| era | distance quartile | n (window complete) | >= 5 ADR within 60 | >= 10 ADR | mean R | closed above the base high within 60 |
|---|---|---|---|---|---|---|
| 2022-24 | Q1 <= 0.47 (at/near the base high) | n = 2,012 | 34.7% | 9.7% | -0.266 | 90.1% |
| 2022-24 | Q2 0.47-1.28 | n = 2,012 | 33.6% | 9.5% | -0.190 | 77.8% |
| 2022-24 | Q3 1.28-2.25 | n = 2,011 | 36.0% | 10.2% | -0.190 | 64.8% |
| 2022-24 | Q4 > 2.25 (deep in the base) | n = 2,012 | 36.3% | 10.7% | -0.176 | 47.0% |

#### B. Does a REAL breakout follow through? (2022-24; every entry against its matched control; tail first)

Composition of the entry sets (one row per (ticker, entry day) for the new sets):

| era | entry set | n | entry days | median ADR20 (unit) | median 63-session return at t-1 | median 20-session dollar volume | notes |
|---|---|---|---|---|---|---|---|
| 2022-24 | our fills (C0 tl ORH5, from E's close) | n = 8,956 | 668 | 0.0400 | +0.160 | $37M | published rows; retrigger_chain = 1: 1,653 |
| 2022-24 | R3 — E meets the expansion test | n = 376 | 235 | 0.0459 | +0.157 | $35M | range >= 1 ADR: 3,502 (39.1%); close in top 30%: 3,993 (44.6%); volume >= 1.5x: 1,027 (11.5%) |
| 2022-24 | R3 — E does NOT meet it | n = 8,580 | 666 | 0.0398 | +0.160 | $37M | |
| 2022-24 | R1 base-high close (ADR20 at t-1) | n = 5,530 | 641 | 0.0376 | +0.200 | $37M | from 6,137 fills reaching a close above the base high in sessions 0..59; dedup removed 607; R1 day = E itself 886 (16.0%); median s_c 6; close over the base high median 0.34 ADR; next-open gap median +0.00 ADR; splits in the volume window 15 |
| 2022-24 | R2 expansion breakout (R1 + range/close/volume) | n = 1,076 | 445 | 0.0407 | +0.174 | $35M | range >= 1 ADR: 3,578 (64.7%); close in top 30%: 4,053 (73.3%); volume >= 1.5x: 1,749 (31.6%); R2 day = E itself 150 |
| 2022-24 | R1 but NOT R2 | n = 4,454 | 610 | 0.0370 | +0.206 | $37M | |
| 2022-24 | K = full (ORH5 first break, from E's close) | n = 4,096 | 613 | 0.0381 | +0.223 | $39M | fill below the base high: median -0.04 ADR; fill at/above it 100.0%; includes the 5 non-mature fills |
| 2022-24 | K = k10 (ORH5 first break, from E's close) | n = 7,268 | 640 | 0.0395 | +0.160 | $37M | fill below the base high: median 0.86 ADR; fill at/above it 26.7%; includes the 5 non-mature fills |
| 2022-24 | K = k5 (ORH5 first break, from E's close) | n = 9,016 | 658 | 0.0398 | +0.154 | $37M | fill below the base high: median 1.25 ADR; fill at/above it 13.0%; includes the 5 non-mature fills |
| 2022-24 | K = tl (ORH5 first break, from E's close) | n = 8,961 | 668 | 0.0400 | +0.160 | $37M | fill below the base high: median 1.26 ADR; fill at/above it 7.8%; includes the 5 non-mature fills |

**our fills (from E's close) — composition.** n = 8,956 over 668 entry days; control rows on those days 1,530,755. ADR20 (the entry's unit): median 0.0400, decile cuts [0.0242, 0.0286, 0.0324, 0.0359, 0.04, 0.0451, 0.0511, 0.0587, 0.072]; 63-session return quintile cuts [-0.005, 0.111, 0.206, 0.335] (entries' median +0.160 vs the pooled control's +0.002).

| 2022-24: our fills (from E's close) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 8,047 | 35.19% | 36.04% | -0.84% | -2.35% .. 0.84% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 8,047 | 10.18% | 10.43% | -0.25% | -1.06% .. 0.86% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 8,889 | 1.92% | 1.57% | 0.35% | -0.04% .. 0.76% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 8,711 | 13.50% | 14.00% | -0.50% | -1.44% .. 0.46% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 8,944 | -0.023 | -0.022 | -0.000 | -0.017 .. +0.016 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 8,886 | -0.120 | -0.129 | +0.009 | -0.043 .. +0.062 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 8,689 | -0.171 | -0.185 | +0.014 | -0.090 .. +0.117 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 7,973 | +0.073 | -0.004 | +0.078 | -0.156 .. +0.319 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 8,047 | 35.19% | 34.66% | 0.53% | -0.93% .. 2.16% | 28 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 8,047 | 10.18% | 9.78% | 0.40% | -0.51% .. 1.62% | 28 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 8,889 | 1.92% | 1.52% | 0.40% | 0.05% .. 0.78% | 35 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 8,711 | 13.50% | 13.45% | 0.05% | -0.85% .. 0.98% | 35 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 8,944 | -0.023 | -0.024 | +0.002 | -0.016 .. +0.019 | 36 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 8,886 | -0.120 | -0.131 | +0.011 | -0.036 .. +0.061 | 35 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 8,689 | -0.171 | -0.167 | -0.004 | -0.100 .. +0.100 | 35 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 7,973 | +0.073 | -0.108 | +0.181 | -0.061 .. +0.450 | 29 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 2,832 entries / 102,452 control rows | 28 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 819 / 31,203 | 38 | 38 | - | - | - |

**R3: E meets the expansion test — composition.** n = 376 over 235 entry days; control rows on those days 534,450. ADR20 (the entry's unit): median 0.0459, decile cuts [0.0274, 0.0329, 0.0374, 0.041, 0.0459, 0.0509, 0.0567, 0.0654, 0.081]; 63-session return quintile cuts [0.002, 0.11, 0.199, 0.336] (entries' median +0.157 vs the pooled control's +0.002).

| 2022-24: R3: E meets the expansion test | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 338 | 36.09% | 35.47% | 0.63% | -3.11% .. 4.85% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 338 | 11.24% | 10.55% | 0.69% | -2.73% .. 4.84% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 375 | 4.27% | 1.75% | 2.51% | 0.73% .. 4.59% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 366 | 16.67% | 13.58% | 3.09% | -0.27% .. 6.76% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 376 | +0.015 | +0.024 | -0.008 | -0.098 .. +0.091 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 375 | -0.144 | -0.121 | -0.023 | -0.173 .. +0.140 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 366 | -0.005 | -0.158 | +0.153 | -0.142 .. +0.482 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 337 | -0.060 | +0.086 | -0.146 | -0.863 .. +0.765 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 338 | 36.09% | 32.68% | 3.42% | -1.45% .. 8.64% | 4 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 338 | 11.24% | 9.15% | 2.09% | -1.83% .. 6.90% | 4 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 375 | 4.27% | 1.79% | 2.47% | 0.66% .. 4.63% | 6 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 366 | 16.67% | 12.94% | 3.73% | 0.03% .. 7.54% | 6 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 376 | +0.015 | +0.036 | -0.020 | -0.109 .. +0.081 | 6 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 375 | -0.144 | -0.092 | -0.051 | -0.202 .. +0.118 | 6 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 366 | -0.005 | -0.150 | +0.145 | -0.166 .. +0.506 | 6 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 337 | -0.060 | -0.151 | +0.090 | -0.764 .. +1.162 | 4 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 122 entries / 5,034 control rows | 22 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 38 / 1,506 | 34 | 37 | - | - | - |

**R3: E does not meet it — composition.** n = 8,580 over 666 entry days; control rows on those days 1,526,537. ADR20 (the entry's unit): median 0.0398, decile cuts [0.0241, 0.0285, 0.0323, 0.0357, 0.0398, 0.0448, 0.0509, 0.0584, 0.0716]; 63-session return quintile cuts [-0.005, 0.112, 0.206, 0.335] (entries' median +0.160 vs the pooled control's +0.002).

| 2022-24: R3: E does not meet it | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 7,709 | 35.15% | 36.04% | -0.89% | -2.47% .. 0.88% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 7,709 | 10.13% | 10.42% | -0.29% | -1.05% .. 0.72% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 8,514 | 1.82% | 1.56% | 0.26% | -0.14% .. 0.68% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 8,345 | 13.36% | 14.02% | -0.65% | -1.61% .. 0.33% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 8,568 | -0.024 | -0.024 | -0.000 | -0.016 .. +0.016 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 8,511 | -0.119 | -0.130 | +0.011 | -0.042 .. +0.067 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 8,323 | -0.179 | -0.187 | +0.008 | -0.098 .. +0.110 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 7,636 | +0.079 | -0.007 | +0.086 | -0.144 .. +0.323 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 7,709 | 35.15% | 34.71% | 0.45% | -1.08% .. 2.11% | 21 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 7,709 | 10.13% | 9.77% | 0.36% | -0.53% .. 1.50% | 21 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 8,514 | 1.82% | 1.52% | 0.30% | -0.06% .. 0.68% | 25 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 8,345 | 13.36% | 13.45% | -0.09% | -1.02% .. 0.85% | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 8,568 | -0.024 | -0.026 | +0.002 | -0.016 .. +0.019 | 26 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 8,511 | -0.119 | -0.132 | +0.013 | -0.035 .. +0.066 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 8,323 | -0.179 | -0.169 | -0.010 | -0.105 .. +0.088 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 7,636 | +0.079 | -0.107 | +0.186 | -0.048 .. +0.445 | 22 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 2,710 entries / 100,124 control rows | 28 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 781 / 30,437 | 38 | 38 | - | - | - |

**R1 base-high close — entry at that close — composition.** n = 5,530 over 641 entry days; control rows on those days 1,469,399. ADR20 (the entry's unit): median 0.0376, decile cuts [0.0229, 0.0268, 0.0302, 0.0338, 0.0376, 0.042, 0.0477, 0.055, 0.0663]; 63-session return quintile cuts [0.055, 0.158, 0.243, 0.362] (entries' median +0.200 vs the pooled control's +0.002).

| 2022-24: R1 base-high close — entry at that close | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 4,934 | 35.18% | 36.90% | -1.71% | -3.77% .. 0.70% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 4,934 | 10.72% | 10.78% | -0.06% | -1.20% .. 1.16% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 5,510 | 2.29% | 1.80% | 0.49% | 0.10% .. 0.90% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 5,420 | 15.37% | 15.41% | -0.05% | -1.81% .. 1.61% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 5,526 | -0.019 | -0.009 | -0.010 | -0.028 .. +0.006 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 5,506 | -0.114 | -0.052 | -0.062 | -0.099 .. -0.020 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 5,399 | -0.038 | -0.021 | -0.017 | -0.160 .. +0.141 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 4,871 | -0.091 | +0.065 | -0.156 | -0.442 .. +0.148 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 4,934 | 35.18% | 34.55% | 0.64% | -1.03% .. 2.75% | 28 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 4,934 | 10.72% | 10.12% | 0.60% | -0.46% .. 1.79% | 28 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 5,510 | 2.29% | 1.82% | 0.47% | -0.00% .. 0.91% | 30 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 5,420 | 15.37% | 14.10% | 1.26% | 0.31% .. 2.18% | 30 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 5,526 | -0.019 | -0.007 | -0.012 | -0.035 .. +0.008 | 30 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 5,506 | -0.114 | -0.065 | -0.050 | -0.091 .. -0.007 | 30 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 5,399 | -0.038 | -0.061 | +0.023 | -0.102 .. +0.153 | 29 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 4,871 | -0.091 | -0.134 | +0.043 | -0.241 .. +0.349 | 28 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 1,736 entries / 73,611 control rows | 26 | 26 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 529 / 22,805 | 38 | 38 | - | - | - |

**R1 — entry at the next open — composition.** n = 5,530 over 641 entry days; control rows on those days 1,469,399. ADR20 (the entry's unit): median 0.0376, decile cuts [0.0229, 0.0268, 0.0302, 0.0338, 0.0376, 0.042, 0.0477, 0.055, 0.0663]; 63-session return quintile cuts [0.055, 0.158, 0.243, 0.362] (entries' median +0.200 vs the pooled control's +0.002).

| 2022-24: R1 — entry at the next open | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 4,934 | 35.02% | 36.76% | -1.74% | -4.05% .. 0.90% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 4,934 | 10.62% | 10.71% | -0.09% | -1.25% .. 1.13% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 5,510 | 1.92% | 1.52% | 0.41% | 0.08% .. 0.78% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 5,420 | 15.09% | 15.08% | 0.01% | -1.93% .. 1.77% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 5,526 | -0.020 | -0.011 | -0.009 | -0.023 .. +0.006 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 5,506 | -0.116 | -0.055 | -0.060 | -0.096 .. -0.019 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 5,399 | -0.039 | -0.024 | -0.015 | -0.155 .. +0.137 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 4,871 | -0.085 | +0.067 | -0.152 | -0.434 .. +0.148 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 4,934 | 35.02% | 34.37% | 0.65% | -1.15% .. 2.97% | 28 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 4,934 | 10.62% | 9.93% | 0.69% | -0.32% .. 1.84% | 28 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 5,510 | 1.92% | 1.56% | 0.37% | -0.04% .. 0.79% | 30 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 5,420 | 15.09% | 13.78% | 1.31% | 0.25% .. 2.29% | 30 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 5,526 | -0.020 | -0.012 | -0.008 | -0.023 .. +0.006 | 30 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 5,506 | -0.116 | -0.070 | -0.045 | -0.084 .. -0.003 | 30 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 5,399 | -0.039 | -0.067 | +0.029 | -0.097 .. +0.150 | 29 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 4,871 | -0.085 | -0.135 | +0.050 | -0.230 .. +0.351 | 28 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 1,728 entries / 73,011 control rows | 26 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 524 / 22,413 | 38 | 38 | - | - | - |

**R1 — measured from the NEXT close (same-day-effect check) — composition.** n = 5,530 over 641 entry days; control rows on those days 1,469,399. ADR20 (the entry's unit): median 0.0376, decile cuts [0.0229, 0.0268, 0.0302, 0.0338, 0.0376, 0.042, 0.0477, 0.055, 0.0663]; 63-session return quintile cuts [0.055, 0.158, 0.243, 0.362] (entries' median +0.200 vs the pooled control's +0.002).

| 2022-24: R1 — measured from the NEXT close (same-day-effect check) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 4,928 | 35.59% | 36.92% | -1.33% | -3.64% .. 1.25% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 4,928 | 10.53% | 10.86% | -0.33% | -1.46% .. 0.86% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 5,508 | 2.36% | 1.78% | 0.58% | 0.14% .. 1.08% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 5,408 | 15.50% | 15.30% | 0.20% | -1.48% .. 1.89% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 5,520 | -0.028 | -0.016 | -0.012 | -0.036 .. +0.014 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 5,503 | -0.117 | -0.058 | -0.060 | -0.108 .. -0.005 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 5,387 | -0.043 | -0.016 | -0.027 | -0.158 .. +0.132 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 4,865 | -0.088 | +0.075 | -0.164 | -0.456 .. +0.153 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 4,928 | 35.59% | 34.64% | 0.95% | -0.82% .. 3.10% | 28 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 4,928 | 10.53% | 10.12% | 0.41% | -0.59% .. 1.56% | 28 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 5,508 | 2.36% | 1.81% | 0.55% | 0.07% .. 1.08% | 30 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 5,408 | 15.50% | 13.93% | 1.57% | 0.42% .. 2.64% | 30 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 5,520 | -0.028 | -0.018 | -0.010 | -0.035 .. +0.016 | 30 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 5,503 | -0.117 | -0.073 | -0.044 | -0.091 .. +0.009 | 30 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 5,387 | -0.043 | -0.060 | +0.017 | -0.106 .. +0.149 | 29 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 4,865 | -0.088 | -0.136 | +0.048 | -0.237 .. +0.356 | 28 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 1,754 entries / 73,539 control rows | 26 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 519 / 22,863 | 38 | 38 | - | - | - |

**R2 expansion breakout — entry at that close — composition.** n = 1,076 over 445 entry days; control rows on those days 1,013,376. ADR20 (the entry's unit): median 0.0407, decile cuts [0.0246, 0.0282, 0.0325, 0.0364, 0.0407, 0.0448, 0.0513, 0.0579, 0.0728]; 63-session return quintile cuts [0.026, 0.122, 0.222, 0.347] (entries' median +0.174 vs the pooled control's +0.002).

| 2022-24: R2 expansion breakout — entry at that close | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 927 | 35.60% | 36.88% | -1.28% | -4.09% .. 1.61% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 927 | 12.51% | 11.28% | 1.24% | -1.11% .. 3.76% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 1,073 | 3.82% | 2.14% | 1.68% | 0.49% .. 2.88% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 1,048 | 17.37% | 15.55% | 1.81% | -0.20% .. 4.19% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 1,075 | -0.032 | +0.013 | -0.045 | -0.125 .. +0.031 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 1,072 | -0.119 | -0.049 | -0.070 | -0.163 .. +0.040 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 1,045 | +0.036 | -0.024 | +0.059 | -0.148 .. +0.284 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 918 | +0.099 | +0.139 | -0.040 | -0.497 .. +0.502 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 927 | 35.60% | 34.53% | 1.07% | -1.70% .. 3.84% | 5 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 927 | 12.51% | 10.70% | 1.81% | -0.31% .. 4.12% | 5 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 1,073 | 3.82% | 2.08% | 1.74% | 0.51% .. 2.97% | 7 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 1,048 | 17.37% | 14.40% | 2.97% | 0.98% .. 5.17% | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 1,075 | -0.032 | +0.029 | -0.061 | -0.159 .. +0.027 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 1,072 | -0.119 | -0.057 | -0.062 | -0.167 .. +0.060 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 1,045 | +0.036 | -0.066 | +0.102 | -0.073 .. +0.284 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 918 | +0.099 | -0.030 | +0.130 | -0.310 .. +0.625 | 5 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 330 entries / 20,333 control rows | 23 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 116 / 6,722 | 34 | 38 | - | - | - |

**R2 — entry at the next open — composition.** n = 1,076 over 445 entry days; control rows on those days 1,013,376. ADR20 (the entry's unit): median 0.0407, decile cuts [0.0246, 0.0282, 0.0325, 0.0364, 0.0407, 0.0448, 0.0513, 0.0579, 0.0728]; 63-session return quintile cuts [0.026, 0.122, 0.222, 0.347] (entries' median +0.174 vs the pooled control's +0.002).

| 2022-24: R2 — entry at the next open | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 927 | 35.81% | 36.72% | -0.91% | -4.01% .. 2.23% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 927 | 12.51% | 11.19% | 1.32% | -0.96% .. 3.71% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 1,073 | 3.17% | 1.78% | 1.39% | 0.32% .. 2.44% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 1,048 | 17.75% | 15.15% | 2.60% | 0.50% .. 4.71% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 1,075 | -0.013 | +0.004 | -0.017 | -0.064 .. +0.025 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 1,072 | -0.101 | -0.058 | -0.044 | -0.138 .. +0.061 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 1,045 | +0.059 | -0.033 | +0.092 | -0.122 .. +0.314 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 918 | +0.115 | +0.136 | -0.021 | -0.479 .. +0.503 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 927 | 35.81% | 34.33% | 1.48% | -1.68% .. 4.74% | 5 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 927 | 12.51% | 10.51% | 2.00% | 0.01% .. 4.12% | 5 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 1,073 | 3.17% | 1.65% | 1.52% | 0.37% .. 2.58% | 7 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 1,048 | 17.75% | 13.91% | 3.84% | 1.71% .. 6.04% | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 1,075 | -0.013 | +0.009 | -0.022 | -0.079 .. +0.030 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 1,072 | -0.101 | -0.077 | -0.024 | -0.132 .. +0.097 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 1,045 | +0.059 | -0.086 | +0.144 | -0.035 .. +0.323 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 918 | +0.115 | -0.038 | +0.153 | -0.269 .. +0.629 | 5 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 332 entries / 20,195 control rows | 22 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 116 / 6,675 | 34 | 39 | - | - | - |

**R2 — measured from the NEXT close (same-day-effect check) — composition.** n = 1,076 over 445 entry days; control rows on those days 1,013,376. ADR20 (the entry's unit): median 0.0407, decile cuts [0.0246, 0.0282, 0.0325, 0.0364, 0.0407, 0.0448, 0.0513, 0.0579, 0.0728]; 63-session return quintile cuts [0.026, 0.122, 0.222, 0.347] (entries' median +0.174 vs the pooled control's +0.002).

| 2022-24: R2 — measured from the NEXT close (same-day-effect check) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 926 | 37.47% | 36.59% | 0.88% | -1.59% .. 3.57% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 926 | 11.88% | 11.30% | 0.58% | -1.65% .. 2.72% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 1,072 | 3.08% | 1.96% | 1.12% | -0.01% .. 2.30% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 1,046 | 17.50% | 15.07% | 2.42% | 0.31% .. 4.64% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 1,073 | -0.017 | -0.021 | +0.004 | -0.051 .. +0.060 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 1,071 | -0.125 | -0.084 | -0.041 | -0.177 .. +0.099 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 1,043 | +0.091 | -0.036 | +0.127 | -0.084 .. +0.356 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 917 | +0.070 | +0.113 | -0.043 | -0.511 .. +0.491 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 926 | 37.47% | 34.15% | 3.32% | 0.64% .. 6.03% | 5 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 926 | 11.88% | 10.39% | 1.49% | -0.50% .. 3.39% | 5 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 1,072 | 3.08% | 1.71% | 1.37% | 0.25% .. 2.48% | 7 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 1,046 | 17.50% | 13.68% | 3.82% | 1.86% .. 6.09% | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 1,073 | -0.017 | -0.034 | +0.017 | -0.046 .. +0.081 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 1,071 | -0.125 | -0.105 | -0.020 | -0.151 .. +0.122 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 1,043 | +0.091 | -0.092 | +0.183 | +0.008 .. +0.367 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 917 | +0.070 | -0.011 | +0.081 | -0.397 .. +0.605 | 5 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 347 entries / 20,108 control rows | 24 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 110 / 6,694 | 32 | 38 | - | - | - |

**R1 but NOT R2 — entry at that close — composition.** n = 4,454 over 610 entry days; control rows on those days 1,397,581. ADR20 (the entry's unit): median 0.0370, decile cuts [0.0226, 0.0266, 0.0298, 0.0332, 0.037, 0.041, 0.0467, 0.0542, 0.0653]; 63-session return quintile cuts [0.064, 0.166, 0.247, 0.364] (entries' median +0.206 vs the pooled control's +0.002).

| 2022-24: R1 but NOT R2 — entry at that close | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 4,007 | 35.09% | 36.95% | -1.86% | -4.07% .. 0.66% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 4,007 | 10.31% | 10.63% | -0.32% | -1.50% .. 1.01% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 4,437 | 1.92% | 1.73% | 0.19% | -0.22% .. 0.60% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 4,372 | 14.89% | 15.37% | -0.48% | -2.35% .. 1.40% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 4,451 | -0.015 | -0.014 | -0.001 | -0.022 .. +0.021 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 4,434 | -0.113 | -0.051 | -0.063 | -0.108 .. -0.011 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 4,354 | -0.056 | -0.015 | -0.041 | -0.190 .. +0.122 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 3,953 | -0.136 | +0.046 | -0.181 | -0.486 .. +0.144 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 4,007 | 35.09% | 34.70% | 0.38% | -1.41% .. 2.49% | 21 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 4,007 | 10.31% | 9.83% | 0.48% | -0.62% .. 1.74% | 21 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 4,437 | 1.92% | 1.79% | 0.13% | -0.32% .. 0.58% | 22 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 4,372 | 14.89% | 13.98% | 0.91% | -0.26% .. 2.07% | 22 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 4,451 | -0.015 | -0.015 | -0.000 | -0.020 .. +0.021 | 22 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 4,434 | -0.113 | -0.061 | -0.053 | -0.093 .. -0.008 | 22 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 4,354 | -0.056 | -0.080 | +0.025 | -0.117 .. +0.166 | 22 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 3,953 | -0.136 | -0.146 | +0.010 | -0.288 .. +0.328 | 23 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 1,406 entries / 58,169 control rows | 26 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 413 / 17,098 | 39 | 38 | - | - | - |

**R2 without the rows with a split in the volume window — composition.** n = 1,074 over 445 entry days; control rows on those days 1,013,376. ADR20 (the entry's unit): median 0.0407, decile cuts [0.0246, 0.0282, 0.0326, 0.0364, 0.0407, 0.0448, 0.0513, 0.0579, 0.0728]; 63-session return quintile cuts [0.026, 0.122, 0.222, 0.346] (entries' median +0.174 vs the pooled control's +0.002).

| 2022-24: R2 without the rows with a split in the volume window | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 925 | 35.57% | 36.89% | -1.32% | -4.14% .. 1.58% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 925 | 12.43% | 11.29% | 1.14% | -1.16% .. 3.61% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 1,071 | 3.83% | 2.14% | 1.68% | 0.49% .. 2.89% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 1,046 | 17.40% | 15.57% | 1.83% | -0.19% .. 4.22% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 1,073 | -0.032 | +0.013 | -0.044 | -0.125 .. +0.032 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 1,070 | -0.117 | -0.050 | -0.067 | -0.160 .. +0.041 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 1,043 | +0.040 | -0.022 | +0.061 | -0.148 .. +0.288 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 916 | +0.092 | +0.144 | -0.052 | -0.510 .. +0.481 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 925 | 35.57% | 34.49% | 1.08% | -1.69% .. 3.87% | 5 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 925 | 12.43% | 10.66% | 1.77% | -0.28% .. 4.04% | 5 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 1,071 | 3.83% | 2.08% | 1.75% | 0.51% .. 2.98% | 7 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 1,046 | 17.40% | 14.34% | 3.06% | 1.00% .. 5.29% | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 1,073 | -0.032 | +0.029 | -0.060 | -0.158 .. +0.028 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 1,070 | -0.117 | -0.059 | -0.058 | -0.162 .. +0.063 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 1,043 | +0.040 | -0.066 | +0.106 | -0.074 .. +0.293 | 7 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 916 | +0.092 | -0.038 | +0.130 | -0.305 .. +0.628 | 5 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 329 entries / 20,309 control rows | 23 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 115 / 6,725 | 34 | 38 | - | - | - |

**K = full (ORH5 first break, from E's close) — composition.** n = 4,096 over 613 entry days; control rows on those days 1,401,417. ADR20 (the entry's unit): median 0.0381, decile cuts [0.0231, 0.0274, 0.0308, 0.0342, 0.0381, 0.0428, 0.0482, 0.0554, 0.0679]; 63-session return quintile cuts [0.076, 0.181, 0.264, 0.386] (entries' median +0.223 vs the pooled control's +0.002).

| 2022-24: K = full (ORH5 first break, from E's close) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 3,671 | 35.49% | 36.50% | -1.00% | -3.43% .. 1.46% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 3,671 | 10.35% | 10.62% | -0.27% | -1.50% .. 1.19% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 4,078 | 1.84% | 1.63% | 0.21% | -0.27% .. 0.72% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 4,005 | 14.08% | 14.89% | -0.81% | -2.56% .. 0.82% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 4,092 | -0.031 | -0.040 | +0.008 | -0.015 .. +0.031 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 4,076 | -0.083 | -0.076 | -0.007 | -0.066 .. +0.051 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 3,993 | -0.105 | -0.116 | +0.011 | -0.153 .. +0.187 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 3,633 | -0.052 | -0.043 | -0.009 | -0.348 .. +0.343 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 3,671 | 35.49% | 34.59% | 0.90% | -0.91% .. 2.96% | 31 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 3,671 | 10.35% | 10.13% | 0.22% | -0.89% .. 1.53% | 31 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 4,078 | 1.84% | 1.54% | 0.30% | -0.17% .. 0.79% | 35 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 4,005 | 14.08% | 13.74% | 0.35% | -0.80% .. 1.41% | 33 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 4,092 | -0.031 | -0.034 | +0.003 | -0.024 .. +0.027 | 35 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 4,076 | -0.083 | -0.076 | -0.007 | -0.054 .. +0.041 | 35 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 3,993 | -0.105 | -0.124 | +0.019 | -0.137 .. +0.179 | 31 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 3,633 | -0.052 | -0.192 | +0.140 | -0.169 .. +0.461 | 29 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 1,303 entries / 47,641 control rows | 27 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 380 / 14,312 | 38 | 38 | - | - | - |

**K = k10 (ORH5 first break, from E's close) — composition.** n = 7,268 over 640 entry days; control rows on those days 1,464,810. ADR20 (the entry's unit): median 0.0395, decile cuts [0.0237, 0.0282, 0.032, 0.0355, 0.0395, 0.0445, 0.0505, 0.0582, 0.0707]; 63-session return quintile cuts [0.0, 0.112, 0.206, 0.33] (entries' median +0.160 vs the pooled control's +0.002).

| 2022-24: K = k10 (ORH5 first break, from E's close) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 6,636 | 36.59% | 36.63% | -0.04% | -1.61% .. 1.70% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 6,636 | 10.50% | 10.60% | -0.09% | -1.01% .. 1.09% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 7,226 | 1.79% | 1.54% | 0.25% | -0.12% .. 0.61% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 7,112 | 14.72% | 14.84% | -0.12% | -1.16% .. 0.95% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 7,256 | -0.030 | -0.026 | -0.003 | -0.028 .. +0.019 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 7,221 | -0.113 | -0.094 | -0.019 | -0.078 .. +0.044 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 7,092 | -0.046 | -0.060 | +0.014 | -0.106 .. +0.133 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 6,577 | +0.109 | +0.015 | +0.094 | -0.196 .. +0.408 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 6,636 | 36.59% | 35.08% | 1.51% | 0.12% .. 3.18% | 23 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 6,636 | 10.50% | 9.69% | 0.82% | -0.09% .. 2.04% | 23 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 7,226 | 1.79% | 1.51% | 0.28% | -0.06% .. 0.61% | 24 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 7,112 | 14.72% | 14.13% | 0.59% | -0.49% .. 1.67% | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 7,256 | -0.030 | -0.023 | -0.006 | -0.030 .. +0.015 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 7,221 | -0.113 | -0.090 | -0.023 | -0.083 .. +0.035 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 7,092 | -0.046 | -0.035 | -0.012 | -0.131 .. +0.100 | 24 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 6,577 | +0.109 | -0.118 | +0.226 | -0.051 .. +0.549 | 24 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 2,428 entries / 79,734 control rows | 27 | 26 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 697 / 23,621 | 37 | 37 | - | - | - |

**K = k5 (ORH5 first break, from E's close) — composition.** n = 9,016 over 658 entry days; control rows on those days 1,507,850. ADR20 (the entry's unit): median 0.0398, decile cuts [0.0238, 0.0284, 0.0321, 0.0359, 0.0398, 0.0448, 0.051, 0.0588, 0.0717]; 63-session return quintile cuts [-0.005, 0.107, 0.2, 0.329] (entries' median +0.154 vs the pooled control's +0.002).

| 2022-24: K = k5 (ORH5 first break, from E's close) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 8,133 | 36.03% | 36.26% | -0.23% | -1.64% .. 1.26% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 8,133 | 10.43% | 10.47% | -0.05% | -0.79% .. 0.91% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 8,941 | 1.74% | 1.53% | 0.21% | -0.16% .. 0.61% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 8,783 | 13.94% | 14.13% | -0.19% | -1.24% .. 0.89% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 9,003 | -0.017 | -0.016 | -0.001 | -0.021 .. +0.018 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 8,938 | -0.138 | -0.147 | +0.009 | -0.052 .. +0.073 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 8,758 | -0.090 | -0.159 | +0.069 | -0.045 .. +0.178 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 8,060 | +0.123 | -0.004 | +0.127 | -0.117 .. +0.372 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 8,133 | 36.03% | 34.79% | 1.23% | -0.03% .. 2.51% | 21 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 8,133 | 10.43% | 9.64% | 0.79% | 0.02% .. 1.77% | 21 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 8,941 | 1.74% | 1.53% | 0.21% | -0.13% .. 0.56% | 23 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 8,783 | 13.94% | 13.53% | 0.40% | -0.64% .. 1.43% | 23 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 9,003 | -0.017 | -0.017 | +0.000 | -0.018 .. +0.019 | 25 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 8,938 | -0.138 | -0.143 | +0.005 | -0.050 .. +0.059 | 23 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 8,758 | -0.090 | -0.141 | +0.051 | -0.059 .. +0.150 | 23 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 8,060 | +0.123 | -0.150 | +0.273 | +0.041 .. +0.524 | 21 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 2,930 entries / 94,297 control rows | 27 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 848 / 28,208 | 37 | 38 | - | - | - |

**K = tl (ORH5 first break, from E's close) — composition.** n = 8,961 over 668 entry days; control rows on those days 1,530,755. ADR20 (the entry's unit): median 0.0400, decile cuts [0.0242, 0.0286, 0.0325, 0.0359, 0.04, 0.0451, 0.0512, 0.0588, 0.0721]; 63-session return quintile cuts [-0.005, 0.111, 0.206, 0.335] (entries' median +0.160 vs the pooled control's +0.002).

| 2022-24: K = tl (ORH5 first break, from E's close) | matching | measure | n | entries | matched control | difference | 95% month-block interval | fell back to decile / to the day |
|---|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 | n = 8,050 | 35.19% | 36.04% | -0.84% | -2.36% .. 0.84% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 | n = 8,050 | 10.17% | 10.43% | -0.26% | -1.07% .. 0.85% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 5 | n = 8,894 | 1.95% | 1.57% | 0.37% | -0.02% .. 0.78% | 0 / 0 |
| ADR decile | share reaching +5 ADR by session 20 | n = 8,716 | 13.52% | 14.00% | -0.48% | -1.43% .. 0.47% | 0 / 0 |
| ADR decile | mean close return +1 (ADR) | n = 8,948 | -0.021 | -0.022 | +0.001 | -0.016 .. +0.018 | 0 / 0 |
| ADR decile | mean close return +5 (ADR) | n = 8,890 | -0.118 | -0.129 | +0.011 | -0.041 .. +0.064 | 0 / 0 |
| ADR decile | mean close return +20 (ADR) | n = 8,692 | -0.170 | -0.185 | +0.015 | -0.090 .. +0.120 | 0 / 0 |
| ADR decile | mean close return +60 (ADR) | n = 7,973 | +0.073 | -0.005 | +0.078 | -0.156 .. +0.320 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 | n = 8,050 | 35.19% | 34.65% | 0.54% | -0.91% .. 2.19% | 28 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 | n = 8,050 | 10.17% | 9.78% | 0.40% | -0.50% .. 1.60% | 28 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 5 | n = 8,894 | 1.95% | 1.52% | 0.42% | 0.06% .. 0.81% | 35 / 0 |
| ADR decile x 63-session return quintile | share reaching +5 ADR by session 20 | n = 8,716 | 13.52% | 13.44% | 0.08% | -0.84% .. 1.03% | 35 / 0 |
| ADR decile x 63-session return quintile | mean close return +1 (ADR) | n = 8,948 | -0.021 | -0.025 | +0.003 | -0.015 .. +0.022 | 36 / 0 |
| ADR decile x 63-session return quintile | mean close return +5 (ADR) | n = 8,890 | -0.118 | -0.131 | +0.013 | -0.035 .. +0.064 | 35 / 0 |
| ADR decile x 63-session return quintile | mean close return +20 (ADR) | n = 8,692 | -0.170 | -0.169 | -0.001 | -0.098 .. +0.104 | 35 / 0 |
| ADR decile x 63-session return quintile | mean close return +60 (ADR) | n = 7,973 | +0.073 | -0.107 | +0.180 | -0.060 .. +0.448 | 29 / 0 |
| the move's start (+5 ADR), big movers only | - | median first session reaching +5 ADR | n = 2,833 entries / 102,517 control rows | 28 | 27 (pooled over the entries' cells, weighted) | - | - | - |
| the move's start (+10 ADR), big movers only | - | median first session reaching +10 ADR | n = 819 / 31,224 | 38 | 38 | - | - | - |

