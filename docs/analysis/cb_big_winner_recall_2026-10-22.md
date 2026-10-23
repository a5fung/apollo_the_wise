# #705 — of the big winners, how many had a measurable breakout, and how many did we catch? (recall read; 2017–21 and 2022–24; 2026-10-22)

**MEASUREMENT ONLY. $0, local data, no network. Nothing here changes or proposes to change a strategy, an entry or exit rule,
a stop, a size, a safeguard or any live trade state — those are the operator's (THE LINE). Every number describes what the
stocks did around fixed, pre-stated definitions and what the published backtest tables did on them; no definition below is
picked over another.**

**The sealed 2025–26 table is untouched.** No `*_holdout*` file was opened; the 2022–24 export AND the 2022–24 watch / entry /
trade tables were cut at 2024-12-31 at load (asserted — the watch table on disk runs to 2026-10-16); every episode whose
qualifying window crosses the cut is excluded and counted.

His ask, verbatim (2026-10-22): *"We need to check of the big winners in a period, how many have a measurable breakout and how
many do we catch"*; *"False breakout happen, that's why we take tight stop losses"*. His definition of a breakout (same day):
the stock *"has broken the consolidation period and enter the expansion phase"*; on the breakout day *"range expansion (up)"*;
breakouts *"can happen anytime"* in the day. This is a RECALL / DETECTION read, outcome-first: it starts from the winners, not
from our trades.

## 0. The answer, in plain words (the +100% set: a close that at least doubled from its trough within 63 sessions; §D was frozen before any of this was computed)

- **How many big winners had a measurable breakout — about half in 2017–21, nearly two thirds in 2022–24.**
  - 2017–21: **994** big winners (751 of them troughed in 2020 — the crash recovery; the table without 2020 is in §1). **489 (49%)** began with a
    measurable breakout: a 10–60 session base, then a daily close above its highest high before a quarter of the move was made. **89 (9%)**
    started with an EP-style gap (≥ 10% on ≥ 3× volume). **408 (41%)** only closed above their base's high after about half the move
    was already made (median 51%) — deep bases (median depth 33%; only 33% of them contain the trough, so most are a decline then a
    recovery through an old high), not breakout starts by his definition. 4 had no consolidation at all.
  - 2022–24: **414** big winners. **260 (63%)** measurable breakout; **45 (11%)** EP-gap start; **107 (26%)** late base (the high cleared at
    46% of the move; here 76% of these bases contain the trough — recoveries out of deep bases); 2 no consolidation.
  - The expansion-day version of his definition (range ≥ 1 ADR, close in the top 30%, volume ≥ 1.5× the 50-day) holds on only **33% / 34%**
    of those breakout days; volume is the binding test (51% / 55% pass it). The breakout close sits a median 0.4–0.5 ADR above the base high.
  - Sensitivity: a tighter span (≤ 4 ADR) reads 50% / 70%; a looser one (≤ 7 ADR) 42% / 48%; the SHORTEST qualifying base instead of the longest
    (added after the first build, said so) 58% / 81% — the late-base group is mostly a question of which high counts as "the base high".
- **How many did we catch — we SAW under half, TRIGGERED on about 2 in 5 after the low, about AT the breakout day, and the tight stop ended 3 in 4 of those before half the move; 2 / 1 kept half of it.** (Corrected after verification: the first build counted fills made while the stock was still falling INTO its low — see the trough-start column.)
  Of the measurable breakouts whose base nights our watch tables cover (481 / 258):

  | step | 2017–21 | 2022–24 |
  |---|---|---|
  | measurable breakouts covered | n = 481 | n = 258 |
  | WATCHED — a C0 watch row on some base night | n = 240 (50%) | n = 115 (45%) |
  | TRIGGERED — a trendline ORH5 fill in the catch window (base + early run)¹ | n = 237 (49%) | n = 112 (43%) |
  | triggered within 5 sessions of the breakout day | n = 83 (17%) | n = 43 (17%) |
  | still in the trade when the stock had made HALF its gain | n = 25 (5%) | n = 14 (5%) |
  | kept at least half of the episode's gain | n = 3 (1%) | n = 0 (0%) |
  | kept at least a quarter of it | n = 20 (4%) | n = 12 (5%) |

  **Trough-start funnel (verifier 1; the catch window started at the LOW, so a fill made during the decline into the low does not count
  as a catch):** watched on a base night on or after the low 215 (45%) / 102 (40%); triggered 204 (42%) / 98 (38%); first fill a
  median **1 session before** the breakout day (118 / 54 before, 25 / 13 on, 61 / 31 after); stopped before the breakout day 81 (40%) /
  40 (41%); stopped before half the move 152 (75%) / 72 (73%); still in at half-way 28 / 17; kept at least half 2 / 1. **This is the
  funnel to quote.** The base-start rows above include 71 / 26 first fills bought while the stock was still falling to its low (67 / 25
  of them out before the low itself).

  ¹ Not nested in WATCHED: 197 / 90 of the triggered were watched on a base night; the other 40 / 22 are late fills from a watch night
  after the base (E a median 12 / 16 sessions after the breakout day). The rows below TRIGGERED are subsets of TRIGGERED.

- **Where we lost them (same 481 / 258):**
  - **Never watched: 241 (50%) / 143 (55%).** The furthest any base night got through our gates: **closed below the 50-day** 118 / 75 — these
    winners start from a decline (the median 63-session return into the trough is −31% / −24% over ALL big winners, about −30% / −31% for this never-watched group, so the 50-day sits above the base); **no 30%
    prior move** 80 / 47 (no pole to measure a flag against); **the base already "resolved"** (a close above the pole high) 35 / 16; the
    universe (raw close under $5, under $10M) 7 / 5. On the night before the breakout day itself the first failing gate is `prior_move`
    on 119 / 73.
  - **Watched but no trigger in the window: 43 (9%) / 25 (10%)** — a trendline level existed on every one of them; a fill came later in the run
    on 27 / 15, another level (com / k5 / k10 / full) filled in the window on 19 / 16.
  - **Triggered: 237 / 112 from the base's first night (204 / 98 from the low — quote these; after the low the first fill comes a median 1
    session before the breakout day).** From the base's first night the first fill sits a median **6 / 4 sessions BEFORE** the
    measurable breakout day (161 / 72 before, 21 / 13 on it, 55 / 27 after); at the fill the stock had made 10% / 12% of its eventual gain.
    The original stop fired before the half-way point on **190 (80%) / 89 (79%)** — on **127 / 60 before the breakout day had even come** (we
    bought the base, the base shook us out, then it broke out); the exit rule (trail / day-3 third) ended 22 / 9 more before half-way;
    **25 / 14 rode it to half-way**, every one of them trailed out at a median **+15R / +10R**, keeping a median **34% / 35%** of the episode's
    gain in dollars. Counting every fill in the window (not just the first), 49 / 20 episodes had some fill still in at half-way. Mean
    realized R of the catches +1.66 / +1.62 (median −1.00): the catches are the setup's tail.
- **Reverse view:** of our 13,368 / 7,791 judgeable trendline fills, **3.6% / 2.3%** were inside a future +100% winner's catch window (11% /
  7% anywhere between its trough − 20 sessions and its peak); for +50% winners 10.5% / 7.9% (40% / 31%).
- **The +50% set reads the same shape, lower:** 4,182 / 2,381 winners, 45% / 48% with a measurable breakout, watched 39% / 28% of the covered
  ones, triggered 33% / 23%, still in at half-way 2% / 2%, kept half 5 / 1 episodes.
- **Action: none from this data (THE LINE).** Recall is capped twice: half the big winners do not start with a breakout our rules can
  see (they start under the 50-day, or without a 30% pole), and of the ones we trigger on after the low, about three in four are stopped out before half the
  move (40% before the breakout day itself). Which of those is a rule question is his; nothing was flipped and no definition is picked.

## D. Definitions — FIXED BEFORE ANY OUTCOME OR CATCH NUMBER WAS COMPUTED (frozen; results sit below it)

The four questions of the standard, answered first:
1. **Decision served:** whether the setup's detection (the C0 watch + the `tl` ORH5 trigger) SEES the big winners of a period —
   and where it loses them: before the watch (a gate), at the trigger (never fired / fired late), or after (stopped, exited
   early). What to do about any of it is his.
2. **What would change it:** if most big winners begin with a measurable consolidation breakout and we watched few of them, the
   loss is in the gates (and the first failing gate names which); if we watched them but did not trigger, the loss is the
   level / trigger; if we triggered and the stop took us out before the run, the loss is the stop / exit. If most big winners
   have NO measurable consolidation at the start, recall of this setup is capped by the population, not by the detector.
3. **Population:** below. 4. **What would make this wrong:** the consolidation rule — a rule that is too loose makes every run a
   "breakout" (then "measurable breakout" means nothing), one that is too tight makes real bases read as V-shapes; the two
   sensitivity spans and the ADR-denominator sensitivity are there for this. And survivorship: the export holds tickers that
   existed in the Alpaca universe at export time; delisted names are under-represented (stated, not fixable here).

**Sessions and bars.** Session calendar = SPY's dates in each era's `daily_closes_all.csv.gz` (Alpaca split-adjusted daily
bars; 2017–21 export 2016-01-04..2022-06-30; 2022–24 export 2021-09-27.., cut to ≤ 2024-12-31 at load, asserted). All prices
are the adjusted ones (deviation from the setup's RAW-close floor, as yesterday). ADR20 at a session = mean (high − low) / close
over the 20 sessions ending there (a fraction); ADR60 likewise over 60 sessions. **AMENDED after the first build, before any catch
number was read as final:** the universe's price floor is the RAW close (2017–21 from `daily_raw_close.csv.gz`; 2022–24 adjusted × the
runner's split factor) and the security type is the runner's `resolve_sectype` (CS / ADRC / unknown; no test symbol) — the adjusted floor
written above admitted leveraged ETFs and sub-$5 raw closes (628 gate-attribution disagreements against the watch table, §V). Bars and
returns stay adjusted.

**1. Big-winner episode (the +100% set; the +50% set is the same code with the factor 1.5).** Per ticker, scanning sessions in
order: a session t is an episode's TROUGH when (a) the universe passes AT t — close ≥ $5 (AMENDED, see above: the RAW close, and the
runner's security type), 20-session median close × volume ≥ $10M, 130 consecutive readable sessions ending at t, ticker `^[A-Z]{1,5}$`; (b) the highest close over (t, t+63]
is ≥ 2.0 × close(t) (the qualifying window; it must fit before the cut, else the candidate is excluded and counted); (c) close(t)
is the lowest close over [t, p], p = the session of that highest close (so the trough IS the lowest close of the run before its
peak; a lower close that fails the universe just before t is counted as composition, not an episode). **Peak extension:** from p,
while a HIGHER close arrives within the next 20 sessions, p moves to it (hard cap t + 126 sessions; an extension window that
crosses the cut is marked truncated); episodes whose peak moved are counted. **Gain** = close(p) / close(t) − 1 (≥ 1.0 by
construction). **Non-overlapping:** the next scan starts at p + 1; one episode per ticker per run. **Era** by the trough date:
2017–21 = 2017-03-01..2021-12-31; 2022–24 = 2022-03-28..2024-12-31 (the two windows our watch tables cover; stated under
"coverage" below). **s25 / s50** = the first session after t whose close ≥ close(t) × (1 + 0.25 × gain / 0.5 × gain).
**Data-artifact exclusion (counted):** a one-session close jump ≥ +50% on volume < 2× the mean of the prior 20 sessions anywhere
in [t − 60, p] (the setup's own pole-artifact rule), or (2017–21) a `symbol_guard.tsv` identity break dated inside [t − 60, p];
a 2022–24 split (`cb702_splits.psv`) inside [t − 60, p] is flagged and reported, not excluded (the bars are adjusted).
**Composition before any rate:** n per era and per trough year; close at the trough (quartiles); ADR20 at the trough; gain and
sessions trough → peak; the EP-gap-start count; the extension count.

**EP-gap start** = a session g in (t, t + 5] with open(g) ≥ 1.10 × close(g − 1) and volume(g) ≥ 3 × the mean volume over the
50 sessions before g (all 50 readable). Reported as its own count regardless of class.

**2. Measurable breakout (detector-independent; NO prior-move requirement — that is what lets `prior_move` show up as a loss
in step 3).** A consolidation = a window of L sessions [b − L, b − 1], 10 ≤ L ≤ 60, that is
  - **contained:** (highest high − lowest low) over the window ≤ 5 × ADR60(b − 1) × close(b − 1), and
  - **sideways:** |mean close of its first 5 sessions − mean close of its last 5 sessions| ≤ 2 × ADR60(b − 1) × close(b − 1)
    (rules out a V-shaped decline or a straight run inside the window);
  the base is the LONGEST such L (a breakout clears the whole base's high, not a tight pocket inside it). The **breakout day b** =
  the first session in (t, s25] whose CLOSE > the base's highest high (strict, float32) and whose prior close(b − 1) <
  close(t) × (1 + 0.25 × gain) — the break happens before the stock had made 25% of the episode's gain. The window may contain
  the trough (a base whose shakeout low is the trough); reported how often it does. **Why ADR60 at b − 1 as the unit:** ADR20 at
  b − 1 is compressed inside a contracting base, so a span in ADR20 units reads LARGE on exactly the bases Qullamaggie describes
  (*"tightening range"*); ADR60 spans the base and the move before it. **Sensitivities (all reported, none picked):** span ≤ 4 and
  ≤ 7 ADR60; ADR20(b − 1) as the unit with span ≤ 5; the contained test alone (no sideways rule).
  **Expansion-day version** (his "range expansion (up)"): the breakout day b also has (high − low) / close ≥ 1.0 × ADR20(b − 1),
  close in the top 30% of its range ((close − low) / (high − low) ≥ 0.70), volume ≥ 1.5 × the mean of the 50 sessions before b.
  **Classes (one per episode, precedence stated):** `ep_gap` when an EP-gap start exists and (no base breakout, or b is on or
  after the gap day — the gap started the run); `measurable_breakout` otherwise when b exists; `late_base` when a qualifying
  base breakout exists only AFTER s25 (and ≤ p); `no_consolidation` when no qualifying window exists anywhere in [t − 60, p]
  (V-shape or straight run); `other` = a qualifying window exists before s25 but its high is never closed above before s25
  (the run left the base without clearing its high, or the base's high is the pre-trough lip). The overlap (a base breakout AND
  a gap start) is counted.

**3. What we did** — the published tables of the frozen backtest, never re-run:
  - **Coverage.** The watch tables hold nights 2017-03-01..2021-12-31 (`watch_tl_com.tsv.gz`) and 2022-03-31..2024-12-31
    (`watch.tsv.gz` + `watch_com.tsv.gz`, cut). An episode's base nights [b − L, b − 1] (no base: [t − 20, s25]) are
    `covered` when every night lies inside the era's watch window; else `partly outside` — an unwatched night outside coverage
    is UNKNOWABLE, not "not watched", and the funnel is also given on the covered subset.
  - **WATCHED** = the watch table holds (ticker, night) for any night in the base window — the watch row exists only when every
    C0 structural gate AND the universe passed that night (the runner's funnel). Beside it: `C0_tl = 1` on some base night (a
    down-sloping line existed, the level the trigger uses) and `C0_com = 1`. **Not watched → which gate:** on the night b − 1
    (and on every base night, for "any night passes"), the universe first (AMENDED as above: RAW close ≥ $5, 20-session median $vol ≥
    $10M, 130 sessions, the runner's security type from `small_pulls.psv` then `cb702_sic.psv`), then `explain_watch` from the module on the ticker's own
    contiguous bars — the FIRST failing gate in `WATCH_GATES` order (`history`, `prior_move`, `close_above_pole_high`, `sma50`,
    `deal_pin_median`, `fresh_pin`, `pole_artifact`, `adr_unusable`). Validation: on covered base nights where the ticker IS in
    the watch table my rebuilt call must return features; where it is NOT, it must fail a gate or the universe — both counted.
  - **TRIGGERED** = a `pp` / `orh5` / `tl` / `C0 = 1` row of `trades_pre_exitpb.tsv.gz` (2017–21) or
    `trades_discovery_exitpb.tsv.gz` (2022–24; E ≤ 2024-12-31) — mature or not, retrigger rows included (this is a recall read, so
    every fill counts) — with E inside the catch window [b − L + 1, s25] (no base: [t − 20, s25]). The FIRST such fill is the
    catch; fills per episode are counted. Reported: E − b (signed sessions; negative = before the breakout day), the share of the
    episode's gain already made at the fill = (fill − close(t)) / (close(p) − close(t)), and the same for any K (the entry
    tables' ORH5 `filled`, `C0 = 1` rows: 2022–24 k5 / k10 / full / tl + com / comb; 2017–21 tl / com only — said so).
    "Near the breakout" = E within [b − 5, b + 5].
  - **KEPT** — the catch's own row: realized R (the `pp` arm: a third sold at the close of session 3 only in profit, the stop to
    cost after it, the rest trailed on the 10-day), exit session (E = session 0), status. In the trade row's own ADR unit (ADR20 at
    D × fill): the episode's gain (close(p) − close(t)), the gain available from the fill (close(p) − fill), and the trade's P&L
    (`pnl_adr`); kept share of the episode = pnl_adr / gain_adr, kept share of the available = pnl_adr / avail_adr. **Still in**
    at b, at s25 and at s50 = the exit session's calendar index ≥ that session's (the trade had not exited before it); the
    headline uses **s50** ("the run's big part"); "stopped before b" for fills inside the base. **Kept ≥ half** = kept share of
    the episode's gain ≥ 0.5 (headline) and of the available gain ≥ 0.5 (beside).
  - **Reverse view:** of the same `pp` / `orh5` / `tl` / `C0` fills in the era (E inside the watch window and E ≤ the last
    session − 83, so that any episode it could belong to is judgeable), the share whose (ticker, E) lies inside a +100% (then
    +50%) episode's catch window.

**Headline funnel per era (tail first: the +100% set, then +50%):** n big winners → with a measurable breakout → covered →
watched → triggered → near the breakout → still in at s50 → kept ≥ half. Then where we lost them: not watched (by first gate),
watched but no trigger, triggered but stopped before s50, exited before s50, kept < half.

## 1. Results (n on every row; the full generated tables, both sets and both eras, sit at the end)

**Composition first (+100% set).** 2017–21: 994 episodes over 739 tickers; trough years 2017: 26, 2018: 48, 2019: 40, **2020: 751**, 2021: 129;
close at the trough median $17 (quartiles $8–36); ADR20 at the trough 8.2% (6.2–10.8%); gain median +142% (+114% to +197%), 239 at ≥ +200%;
trough → peak median 56 sessions; 343 peaks extended past the 63-session window; EP-gap start 94 (9%). 2022–24: 414 episodes over 289
tickers; 2022: 136, 2023: 142, 2024: 136; close $14 ($7.5–26); ADR20 6.9%; gain +131% (+114% to +168%), 70 at ≥ +200%; trough → peak 59;
EP-gap start 45 (11%); 15 candidates whose qualifying window crossed the 2024-12-31 cut were excluded. Exclusions: 21 episodes in 2017–21 (18 artifact jumps, 11 identity
breaks, overlapping), 0 in 2022–24. Both eras are survivorship-shaped (the export is the Alpaca universe at export time).

**2017–21 by trough year (measurable breakouts covered → watched → triggered → still in at half-way → kept ≥ half):**

| year | big winners | measurable breakouts covered | watched | triggered | still in at s50 | kept ≥ half |
|---|---|---|---|---|---|---|
| 2017 | n = 26 | n = 18 | n = 6 | n = 8 | n = 0 | n = 0 |
| 2018 | n = 48 | n = 33 | n = 16 | n = 12 | n = 2 | n = 1 |
| 2019 | n = 40 | n = 29 | n = 13 | n = 15 | n = 3 | n = 0 |
| 2020 | n = 751 | n = 323 | n = 157 | n = 157 | n = 20 | n = 2 |
| 2021 | n = 129 | n = 78 | n = 48 | n = 45 | n = 0 | n = 0 |

Without 2020: 243 big winners, 166 (68%) with a measurable breakout, 158 covered; watched 83 (53%), triggered 80 (51%), near the breakout 30
(19%), still in at half-way 5 (3%), kept ≥ half 1 (1%). The 2020 share of measurable breakouts is lower (43%) because the crash-recovery
winners are the late-base / recovery shape.

**The catches that worked (the setup's tail on these winners).** 2017–21: the 25 still in at half-way were all trailed out, median +15.1R
(mean +18.1R), keeping a median 34% of the dollar gain; the 3 that kept ≥ half: ONCE (fill 4 sessions before the breakout day, +25.9R, 61%),
DDOG (5 after, +18.6R, 50%), NXH (35 after, +54.1R, 64%). 2022–24: the 14 still in at half-way (13 trailed, 1 stopped after the half-way
point), median +10.3R (mean +15.9R), median 35% of the gain kept; none kept half. Of the catches, 30 / 14 made ≥ 3R and 15 / 7 made ≥ 10R.

**Any level (K) — does another level trigger where the trendline does not?** 2022–24 covered measurable breakouts (n = 258): tl 122 (47%,
first fill a median 5 sessions before b), k5 126 (49%, −6), k10 122 (47%, −4), com 130 (50%, −6), comb 89 (34%, −8), **full 76 (29%, median
ON the breakout day)** — the full-base-high level is the one that fires at the measurable breakout, on fewer names. 2017–21 (tl and com only):
tl 237 (49%, −6), com 252 (52%, −7). Across all classes, any K triggered on 36% / 46% of covered episodes.

**Six named episodes, recomputed from the raw export (`04_main_loop_checks.txt`):** MSTR 2020 (+817%): base 2020-08-11..09-14, breakout
close 09-15; we triggered 09-02 (8 sessions early) and were stopped at −1R the next session. SMCI 2023 (+296%): breakout 03-21; triggered
03-15 (4 early), trailed out at +2.0R after 17 sessions, 3% of the gain kept. APP 2023 (+251%): triggered 6 early, stopped on day 0. TSLA
2019 (+282%): triggered 41 sessions AFTER the breakout day, +40.7R, 37% of the gain kept. GME 2024 and NVDA 2023–24: never watched —
`prior_move` (no 30% pole). PLUG 2020: never watched — raw close under $5 on the night before the breakout. ZM 2019–20: `prior_move`.

## M. Method and population

**Population:** the big-winner EPISODES of §D, derived from each era's `daily_closes_all.csv.gz` (Alpaca split-adjusted daily bars; SPY's
session calendar). 2017–21: export 2016-01-04..2022-06-30, troughs 2017-03-01..2021-12-31 → **n = 994** (+100%) / **4,182** (+50%) after
exclusions (21 / 28 artifact or identity-break episodes dropped and counted). 2022–24: export 2021-09-27.., **cut at ≤ 2024-12-31 at load
(asserted)**, troughs 2022-03-28..2024-12-31 → **n = 414 / 2,381** (0 / 4 excluded; 15 / 60 candidates whose 63-session qualifying window
crossed the cut excluded and counted; 31 / 134 peak extensions truncated at the cut). The universe at the trough is the setup's: RAW close
≥ $5 (2017–21 from `daily_raw_close.csv.gz`; 2022–24 = adjusted × the product of the ratios of splits executing after the session, the
runner's `load_splits` rule, `f[3] / f[2]`), 20-session median adjusted dollar volume ≥ $10M, 130 consecutive readable sessions, ticker
`^[A-Z]{1,5}$`, security type CS / ADRC / unknown from `small_pulls.psv` then `cb702_sic.psv` (the runner's `resolve_sectype`; this removed the
leveraged ETFs a first build had admitted — 1,175 → 994 episodes in 2017–21, said so), no exchange test symbol. 6,622 / 10,508 tickers
pass the static filters. Every count in §0/§1 is on the kept episodes.

**What we did — the PUBLISHED tables, never re-run:** watch nights from `watch_tl_com.tsv.gz` (2017-03-01..2021-12-31; 192,897 rows) and
`watch.tsv.gz` + `watch_com.tsv.gz` (2022-03-31..2024-12-31 after the cut; 129,985 of 239,946 rows — **the file on disk runs to 2026-10-16 and
was cut at load, asserted**); fills from `trades_pre_exitpb.tsv.gz` / `trades_discovery_exitpb.tsv.gz`, rows `arm = pp`, `entry = orh5`,
`K = tl`, `C0 = 1` — **13,368 / 8,961** (E ≤ 2024-12-31; 8,989 before the cut), retrigger rows (2,352 / 1,654) and the 5 / 5 non-mature rows
included, since this is a recall read; the K view from `entries_pre_tl_com.tsv.gz` (tl / com) and `entries_discovery.tsv.gz` +
`entries_discovery_com_comb.tsv.gz` (k5 / k10 / full / tl / com / comb), ORH5 `filled`, `C0 = 1`, E ≤ cut. **Coverage:** an episode's base
nights [b − L, b − 1] (no measurable breakout: [t − 20, s25 − 1]) are `covered` when all lie inside the era's watch window — 481 of 489 / 258
of 260 measurable breakouts; every funnel share is of the covered set. **The catch window for E** = [b − L + 1, s25] (no base: [t − 20, s25]).

**The gate attribution** is my rebuild of the runner's funnel: the universe tests above, then the frozen module's own `explain_watch` on the
ticker's contiguous readable bars (`daily_bars_from_arrays`), the first failing gate in `WATCH_GATES` order. Validated against the watch
table on every covered base night: 2017–21 +100% — of 4,284 nights with a watch row my call passes on 4,284 and of 23,491 without one it fails
on 23,491 (0 + 0 disagreements); 2022–24 — 1,684 / 1,686 and 10,502 / 10,509 (2 + 7 disagreements, 0.07%; the raw-close reconstruction at a
split boundary). The +50% sets: 0 + 30 of 115,821 and 10 + 45 of 65,871. A first build had 628 disagreements, all leveraged ETFs and raw
closes under $5 — fixed by using the runner's universe, which is why the episode counts above changed before any number was read as final.

**Units.** "Kept" is in the trade row's own ADR unit (ADR20 at D × fill): the episode's gain (close(p) − close(t)), the gain available from the
fill (close(p) − fill) and the trade's published `pnl_adr` all divided by the same number; the `pp` arm sells a third at the close of session 3
only in profit, moves the stop to cost after it and trails the 10-day. "Still in at s50" = the exit session's calendar index ≥ s50's (the trade
had not exited before the session the close first reached half the gain); "stopped before b" = status `stopped` / `stopped_day0` with the exit
before the breakout day. s25 / s50 are times to REACH a share of the gain, never the move's start.

**Files.** Probes: `scripts/probes/_702_winner_recall_1022/01_episodes.py` (+ `01_episodes_<era>.txt`, `01_run_<era>.log`), `02_catch.py`
(+ `02_catch_<era>.txt`, `02_reverse_<era>.txt`, `02_run_<era>.log`), `03_report.py` (+ `03_report.md` = every table, `03_numbers.json`,
`03_report_run.log`), `04_main_loop_checks.py` (+ `.txt`). Tables: `apollo_data/cb702_pre/out/wrecall_{episodes,catch,nights}_2017-21_x{200,150}.tsv.gz`
and `apollo_data/cb702/out/wrecall_{episodes,catch,nights}_2022-24_x{200,150}.tsv.gz`. Nothing pinned was written or moved; the runner and the
once-only stages were neither run nor imported (the module `consolidation_breakout.py` was imported for `explain_watch`, `daily_bars_from_arrays`
and `is_test_symbol` only); no `*_holdout*` file was opened; no network; no subagent.

## L. What this does not answer

- **Whether a different trigger would have caught them.** The read measures the published `tl` ORH5 trigger and the published `pp` exit on these
  episodes; the any-K row shows which LEVEL filled, not what a trade at the measurable breakout day would have returned with his stop. That is
  a registered read with a stated stop, and the stop is his (`analysis_standard.md`: a new entry's returns measure its placeholder stop).
- **Whether loosening a gate pays.** 50–55% of the measurable-breakout winners were never watched, most under the 50-day or without a 30%
  pole — but the same gates also keep out every loser that looks like them. Recall of winners is one side; the precision side (what a gate
  admits) is not measured here and is not implied. No gate is proposed to move (THE LINE).
- **Survivorship.** The export holds the tickers Alpaca served at export time; delisted names (many of the 2020–21 winners that later failed)
  are under-represented in both the winners and our fills. The direction of the bias on the catch SHARE is not known.
- **The consolidation rule is one reading of his and Qullamaggie's words.** Six variants are reported; the late-base group (41% / 26%) moves
  with the choice of which high counts as the base high (58% / 81% measurable under the shortest-window reading). None is picked.
- **2017–21 is 76% a 2020 story** (751 of 994 troughs). The by-year table and the no-2020 funnel are given; 2017–19 alone has 114 winners and
  draws no conclusion of its own.
- **The +100%-within-63-sessions definition misses slower doublers** (a +100% over 6 months with no 63-session doubling inside it) and
  stocks whose trough sat under the universe floor (182 / 81 episodes had a lower close in the 10 sessions before the admitted trough).
- **Not the sealed 2025–26.** Nothing after 2024-12-31 was read; the registered RS-leadership read stays unspent.

## V. Verification (2026-10-22)

- **Two independent verifiers (recount + logic audit), both `holds_with_corrections`; every funnel count reproduced to the integer.
  Corrections applied:**
  - (material) The catch window began at the base's first night, and 82% / 89% of bases contain the trough. So 71 / 26 "first fills"
    were bought while the stock was still falling into its low. The trough-start funnel is now given and is the one quoted.
  - (material) The trough rule as frozen in §D says the trough is the lowest close of the run. The code instead keeps the admitted
    trough when a lower close inside the run fails the universe (a raw close under $5): 92 / 53 of the +100% episodes, 310 / 197 of the
    +50%. That is the rule as applied. Under the literal rule (verifier 2, own code):
    - 970 / 379 big winners;
    - 2017–21: 473 measurable breakouts → 466 covered → 240 watched → 234 triggered → 26 still in at half-way → 2 kept half
      (DDOG, ONCE);
    - 2022–24: 230 → 228 → 107 → 103 → 14 → 0;
    - the shares move by at most about 2 points. NXH drops out of "kept half" under the literal rule, and DDOG keeps exactly 0.500.
  - (minor) The −31% / −24% median is labelled as the all-winner figure.
  - (minor) 2022–24 has no identity-break screen: BHVN 2022-10-04 (a takeover plus spin-off) is one of the two "no consolidation"
    episodes and touches no breakout row.
  - (minor) Two +50% episodes flip class at the 25%-of-the-move boundary on float rounding (BYD, NSP).


- **Main loop, own code** (`04_main_loop_checks.py`, no import of the build scripts): the +100% funnel recounted by a pandas merge of the
  published trades onto the episode windows — covered 481 / 258, triggered 237 / 112, still in at s50 25 / 14, kept ≥ half 3 / 0, near b
  83 / 43, stopped before s50 190 / 89, mean R +1.656 / +1.618 — every number equal to the report's. Six named episodes per era recomputed
  from the raw export: base span, sideways test, base high, breakout close and s50 all agree with the tables.
- **The 40 / 22 episodes "triggered but not watched on a base night"** are all late fills (E > b, median 12 / 16 sessions after the
  breakout day, from a watch night after the base) — the two statuses are consistent.
- **Gate rebuild vs the watch table:** 0 + 0 / 2 + 7 disagreements on the +100% covered nights (above).
- **Vectorised base finder vs a naive loop:** 0 mismatches on 9,000 random windows (incl. NaN sessions).
- **Two defects found and fixed before any number was read as final:** (1) the first build admitted leveraged ETFs and adjusted closes under
  the RAW $5 floor (628 attribution disagreements) — the universe now follows the runner's `resolve_sectype` and raw-close rule; (2) the split
  ratio was read `split_to / split_from` where the runner reads `f[3] / f[2]` (NVDA 2024-06-10 `1|10` → 10), which mis-priced SMCI / MSTR /
  CVNA bases — fixed, rebuilt, disagreements fell from 85 to 7.
- **Post hoc, labelled:** the `shortL` classifier variant was added after the first build (the longest-window rule reads deep-base recoveries
  as late bases); it is reported beside, never used in a headline.

---

## Generated tables (`03_report.py`, verbatim; n on every row)

## the +100% set (close at least doubled from the trough within 63 sessions)

### 2017-21, x200 — composition (n = 994 episodes after exclusions)

| item | value |
|---|---|
| episodes by trough year | 2017: n = 26, 2018: n = 48, 2019: n = 40, 2020: n = 751, 2021: n = 129 |
| tickers | n = 739 (episodes per ticker max 5) |
| close at the trough, $ (median, quartiles) | 17.26 (8.38 .. 36.49) (n = 994) |
| ADR20 at the trough (median, quartiles) | 0.082 (0.062 .. 0.108) (n = 994) |
| 63-session return into the trough (median, quartiles) | -0.31 (-0.59 .. 0.03) (n = 994) |
| gain trough → peak (median, quartiles) | 1.42 (1.14 .. 1.97) (n = 994); >= +200% n = 239 |
| sessions trough → peak (median, quartiles) | 56 (49 .. 73); peak extended past the 63-session window n = 343; extension truncated at the cut n = 0 |
| sessions trough → s25 / s50 (median) | 11 / 30 (n = 994) |
| EP-gap start (a >= 10% gap on >= 3x volume within 5 sessions of the trough) | n = 94 (9%) |
| trough moved to a lower close inside the run / a lower universe-failing close just before it / a lower close in the 10 sessions before | n = 579 / 182 (see log for the universe-fail count) |
| split inside [trough − 60, peak] (flag only) | n = 0 |

| breakout class (one per episode) | primary: longest window, span <= 5 ADR60, sideways | span <= 4 ADR60 | span <= 7 ADR60 | unit ADR20(b-1), span <= 5 | no sideways rule | SHORTEST window (post hoc, added after the first build) |
|---|---|---|---|---|---|---|
| measurable_breakout | 489 (49%) | 495 (50%) | 420 (42%) | 472 (47%) | 490 (49%) | 575 (58%) |
| ep_gap | 89 (9%) | 91 (9%) | 88 (9%) | 87 (9%) | 90 (9%) | 86 (9%) |
| late_base | 408 (41%) | 394 (40%) | 462 (46%) | 431 (43%) | 406 (41%) | 328 (33%) |
| no_consolidation | 4 (0%) | 6 (1%) | 1 (0%) | 1 (0%) | 4 (0%) | 4 (0%) |
| other | 4 (0%) | 8 (1%) | 23 (2%) | 3 (0%) | 4 (0%) | 1 (0%) |

A base breakout AND a gap start (overlap, primary rule): n = 89.

The measurable breakouts under the primary rule (n = 489): breakout day b − trough median (quartiles) 13 (7 .. 20) sessions; base length L 25 (17 .. 39); the base contains the trough 403 (82%); base span 4.5 (4.1 .. 4.8) ADR60 = 4.3 (3.7 .. 4.9) ADR20; base depth 0.26 (0.21 .. 0.32); share of the episode's gain made at the close BEFORE b 0.11 (0.05 .. 0.16) and at b's close 0.18 (0.12 .. 0.25); the breakout close over the base high 0.38 (0.16 .. 0.89) ADR20; b opened with a gap of 1.8 (0.5 .. 4.6)%.
The expansion-day version (range >= 1 ADR20, close in the top 30%, volume >= 1.5x the 50-day) holds on 161 (33%) of them — range ok 347 (71%), close location ok 361 (74%), volume ok 251 (51%).
The late-base episodes (n = 408): the first close above the longest base's high came when 0.51 (0.42 .. 0.62) of the gain was already made, b − trough 22 (15 .. 29) sessions, base depth 0.33 (0.28 .. 0.41), the base contains the trough 133 (33%).

### 2017-21, x200 — what we did

**2017-21, x200** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 994 | 100% of 994 |
| with a measurable breakout (primary rule) | n = 489 | 49% of 994 |
| … whose base nights our watch covers | n = 481 | 98% of 489 |
| … WATCHED (a watch row on some base night) | n = 240 | 50% of 481 |
| … watched with a trendline level (C0_tl) on some base night | n = 240 | 50% of 481 |
| … watched on the night before the breakout day | n = 160 | 33% of 481 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 237 | 49% of 481 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 83 | 17% of 481 |
| … triggered and STILL IN at s50 (half the gain made) | n = 25 | 5% of 481 |
| … near the breakout and still in at s50 | n = 15 | 3% of 481 |
| … triggered and KEPT >= half of the episode's gain | n = 3 | 1% of 481 |
| … near the breakout and kept >= half of the episode's gain | n = 2 | 0% of 481 |
| … triggered and kept >= half of the gain available from the fill | n = 6 | 1% of 481 |

All 994 big winners, any class (covered n = 986): watched 390 (40%); triggered (tl fill in the catch window) 310 (31%); still in at s50 33 (3%); kept >= half of the episode's gain 5 (1%); a tl fill ANYWHERE in [trough − 20, peak] 756 (77%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 355 (36%).

**2017-21, x200** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 481)

- NOT WATCHED on any base night: n = 241 (50% of 481). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - close below the 50-day (`sma50`): n = 118 (49% of 241)
  - prior move < 30% (no pole) (`prior_move`): n = 80 (33% of 241)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 35 (15% of 241)
  - raw close under $5 (`universe_price`): n = 5 (2% of 241)
  - under $10M median dollar volume (`universe_dv`): n = 2 (1% of 241)
  - pole data artifact (`pole_artifact`): n = 1 (0% of 241)
  - on the night before the breakout day alone: `prior_move` n = 119; `sma50` n = 62; `universe_dv` n = 26; `close_above_pole_high` n = 26; `universe_price` n = 8
- WATCHED BUT NO TRIGGER in the catch window: n = 43 (9%); of them a trendline level existed on some base night (C0_tl) n = 43, watched on the night before the breakout n = 18, a tl fill came later anywhere before the peak n = 27, some other K filled in the window n = 19
- TRIGGERED: n = 237 (49%). Fills per episode in the window: median 1, max 7; retrigger rows as the first fill n = 19; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -6 (-23 .. 0); before b n = 161, on b n = 21, 1–5 after n = 20, later n = 35; share of the episode's gain already made at the fill: median (quartiles) 0.10 (0.05 .. 0.16)
  - the original STOP fired before s50: n = 190 (80% of 237) — of which before the breakout day itself n = 127; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 22 (9%); still in at s50: n = 25 (11%); status split: stopped n = 97, stopped_day0 n = 93, trailed n = 39, time_exit n = 8
  - realized R of the catch: mean +1.66, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 30, >= 10R n = 15; sessions held median 1
  - kept, in the trade's ADR unit: the episode's gain = 23.7 (17.7 .. 31.0) ADR, the gain available from the fill = 21.2 (14.8 .. 28.4) ADR, the trade's P&L = -0.23 (-0.46 .. 0.28) ADR; kept share of the episode's gain median (quartiles) -0.010 (-0.020 .. 0.009), mean 0.030; kept share of the available gain median -0.011 (-0.023 .. 0.010); kept >= half of the episode's gain n = 3, >= half of the available n = 6, >= a quarter of the episode's gain n = 20
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 49; best fill's kept share of the episode's gain median 0.004 (-0.015 .. 0.049), >= half n = 5

Any-K view on the covered measurable breakouts (n = 481; the entry tables' ORH5 filled C0 rows, E in the catch window): com: 252 (52%), E − b median -7; tl: 237 (49%), E − b median -6.

#### 2017-21 without the 2020 troughs (2020 holds 751 of 994 episodes)

**2017-21 excluding 2020, x200** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 243 | 100% of 243 |
| with a measurable breakout (primary rule) | n = 166 | 68% of 243 |
| … whose base nights our watch covers | n = 158 | 95% of 166 |
| … WATCHED (a watch row on some base night) | n = 83 | 53% of 158 |
| … watched with a trendline level (C0_tl) on some base night | n = 83 | 53% of 158 |
| … watched on the night before the breakout day | n = 60 | 38% of 158 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 80 | 51% of 158 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 30 | 19% of 158 |
| … triggered and STILL IN at s50 (half the gain made) | n = 5 | 3% of 158 |
| … near the breakout and still in at s50 | n = 2 | 1% of 158 |
| … triggered and KEPT >= half of the episode's gain | n = 1 | 1% of 158 |
| … near the breakout and kept >= half of the episode's gain | n = 1 | 1% of 158 |
| … triggered and kept >= half of the gain available from the fill | n = 2 | 1% of 158 |

All 243 big winners, any class (covered n = 235): watched 122 (52%); triggered (tl fill in the catch window) 105 (45%); still in at s50 10 (4%); kept >= half of the episode's gain 3 (1%); a tl fill ANYWHERE in [trough − 20, peak] 177 (75%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 124 (53%).

**2017-21 excluding 2020, x200** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 158)

- NOT WATCHED on any base night: n = 75 (47% of 158). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - close below the 50-day (`sma50`): n = 42 (56% of 75)
  - prior move < 30% (no pole) (`prior_move`): n = 17 (23% of 75)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 14 (19% of 75)
  - raw close under $5 (`universe_price`): n = 1 (1% of 75)
  - pole data artifact (`pole_artifact`): n = 1 (1% of 75)
  - on the night before the breakout day alone: `prior_move` n = 37; `sma50` n = 20; `close_above_pole_high` n = 10; `universe_dv` n = 6; `universe_price` n = 2
- WATCHED BUT NO TRIGGER in the catch window: n = 13 (8%); of them a trendline level existed on some base night (C0_tl) n = 13, watched on the night before the breakout n = 8, a tl fill came later anywhere before the peak n = 6, some other K filled in the window n = 7
- TRIGGERED: n = 80 (51%). Fills per episode in the window: median 1, max 6; retrigger rows as the first fill n = 6; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -4 (-22 .. 0); before b n = 51, on b n = 9, 1–5 after n = 8, later n = 12; share of the episode's gain already made at the fill: median (quartiles) 0.10 (0.05 .. 0.16)
  - the original STOP fired before s50: n = 65 (81% of 80) — of which before the breakout day itself n = 38; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 10 (12%); still in at s50: n = 5 (6%); status split: stopped n = 36, stopped_day0 n = 29, trailed n = 10, time_exit n = 5
  - realized R of the catch: mean +1.58, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 6, >= 10R n = 5; sessions held median 2
  - kept, in the trade's ADR unit: the episode's gain = 21.6 (16.7 .. 27.2) ADR, the gain available from the fill = 18.5 (14.6 .. 25.3) ADR, the trade's P&L = -0.23 (-0.36 .. 0.25) ADR; kept share of the episode's gain median (quartiles) -0.010 (-0.020 .. 0.009), mean 0.021; kept share of the available gain median -0.011 (-0.023 .. 0.010); kept >= half of the episode's gain n = 1, >= half of the available n = 2, >= a quarter of the episode's gain n = 5
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 10; best fill's kept share of the episode's gain median -0.004 (-0.015 .. 0.021), >= half n = 1

By trough year (measurable breakouts covered → watched → triggered → still in at s50 → kept >= half):

| year | big winners | measurable breakouts covered | watched | triggered | still in at s50 | kept >= half |
|---|---|---|---|---|---|---|
| 2017 | n = 26 | n = 18 | n = 6 | n = 8 | n = 0 | n = 0 |
| 2018 | n = 48 | n = 33 | n = 16 | n = 12 | n = 2 | n = 1 |
| 2019 | n = 40 | n = 29 | n = 13 | n = 15 | n = 3 | n = 0 |
| 2020 | n = 751 | n = 323 | n = 157 | n = 157 | n = 20 | n = 2 |
| 2021 | n = 129 | n = 78 | n = 48 | n = 45 | n = 0 | n = 0 |

### 2022-24, x200 — composition (n = 414 episodes after exclusions)

| item | value |
|---|---|
| episodes by trough year | 2022: n = 136, 2023: n = 142, 2024: n = 136 |
| tickers | n = 289 (episodes per ticker max 6) |
| close at the trough, $ (median, quartiles) | 13.80 (7.50 .. 26.05) (n = 414) |
| ADR20 at the trough (median, quartiles) | 0.069 (0.054 .. 0.088) (n = 414) |
| 63-session return into the trough (median, quartiles) | -0.24 (-0.41 .. 0.04) (n = 414) |
| gain trough → peak (median, quartiles) | 1.31 (1.14 .. 1.68) (n = 414); >= +200% n = 70 |
| sessions trough → peak (median, quartiles) | 59 (45 .. 69); peak extended past the 63-session window n = 159; extension truncated at the cut n = 31 |
| sessions trough → s25 / s50 (median) | 15 / 33 (n = 414) |
| EP-gap start (a >= 10% gap on >= 3x volume within 5 sessions of the trough) | n = 45 (11%) |
| trough moved to a lower close inside the run / a lower universe-failing close just before it / a lower close in the 10 sessions before | n = 261 / 81 (see log for the universe-fail count) |
| split inside [trough − 60, peak] (flag only) | n = 9 |

| breakout class (one per episode) | primary: longest window, span <= 5 ADR60, sideways | span <= 4 ADR60 | span <= 7 ADR60 | unit ADR20(b-1), span <= 5 | no sideways rule | SHORTEST window (post hoc, added after the first build) |
|---|---|---|---|---|---|---|
| measurable_breakout | 260 (63%) | 290 (70%) | 197 (48%) | 267 (64%) | 261 (63%) | 335 (81%) |
| ep_gap | 45 (11%) | 45 (11%) | 45 (11%) | 45 (11%) | 45 (11%) | 45 (11%) |
| late_base | 107 (26%) | 73 (18%) | 163 (39%) | 101 (24%) | 106 (26%) | 32 (8%) |
| no_consolidation | 2 (0%) | 5 (1%) | 1 (0%) | 0 (0%) | 2 (0%) | 2 (0%) |
| other | 0 (0%) | 1 (0%) | 8 (2%) | 1 (0%) | 0 (0%) | 0 (0%) |

A base breakout AND a gap start (overlap, primary rule): n = 41.

The measurable breakouts under the primary rule (n = 260): breakout day b − trough median (quartiles) 12 (7 .. 22) sessions; base length L 27 (17 .. 40); the base contains the trough 231 (89%); base span 4.5 (4.1 .. 4.7) ADR60 = 4.4 (3.8 .. 5.0) ADR20; base depth 0.25 (0.20 .. 0.31); share of the episode's gain made at the close BEFORE b 0.11 (0.05 .. 0.16) and at b's close 0.20 (0.13 .. 0.26); the breakout close over the base high 0.51 (0.21 .. 1.03) ADR20; b opened with a gap of 1.7 (0.5 .. 5.7)%.
The expansion-day version (range >= 1 ADR20, close in the top 30%, volume >= 1.5x the 50-day) holds on 88 (34%) of them — range ok 200 (77%), close location ok 197 (76%), volume ok 143 (55%).
The late-base episodes (n = 107): the first close above the longest base's high came when 0.46 (0.36 .. 0.58) of the gain was already made, b − trough 22 (14 .. 30) sessions, base depth 0.34 (0.30 .. 0.41), the base contains the trough 81 (76%).

### 2022-24, x200 — what we did

**2022-24, x200** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 414 | 100% of 414 |
| with a measurable breakout (primary rule) | n = 260 | 63% of 414 |
| … whose base nights our watch covers | n = 258 | 99% of 260 |
| … WATCHED (a watch row on some base night) | n = 115 | 45% of 258 |
| … watched with a trendline level (C0_tl) on some base night | n = 115 | 45% of 258 |
| … watched on the night before the breakout day | n = 71 | 28% of 258 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 112 | 43% of 258 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 43 | 17% of 258 |
| … triggered and STILL IN at s50 (half the gain made) | n = 14 | 5% of 258 |
| … near the breakout and still in at s50 | n = 11 | 4% of 258 |
| … triggered and KEPT >= half of the episode's gain | n = 0 | 0% of 258 |
| … near the breakout and kept >= half of the episode's gain | n = 0 | 0% of 258 |
| … triggered and kept >= half of the gain available from the fill | n = 3 | 1% of 258 |

All 414 big winners, any class (covered n = 409): watched 183 (45%); triggered (tl fill in the catch window) 152 (37%); still in at s50 18 (4%); kept >= half of the episode's gain 1 (0%); a tl fill ANYWHERE in [trough − 20, peak] 307 (75%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 188 (46%).

**2022-24, x200** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 258)

- NOT WATCHED on any base night: n = 143 (55% of 258). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - close below the 50-day (`sma50`): n = 75 (52% of 143)
  - prior move < 30% (no pole) (`prior_move`): n = 47 (33% of 143)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 16 (11% of 143)
  - under $10M median dollar volume (`universe_dv`): n = 3 (2% of 143)
  - raw close under $5 (`universe_price`): n = 2 (1% of 143)
  - on the night before the breakout day alone: `prior_move` n = 73; `sma50` n = 30; `universe_dv` n = 24; `close_above_pole_high` n = 12; `universe_price` n = 4
- WATCHED BUT NO TRIGGER in the catch window: n = 25 (10%); of them a trendline level existed on some base night (C0_tl) n = 25, watched on the night before the breakout n = 9, a tl fill came later anywhere before the peak n = 15, some other K filled in the window n = 16
- TRIGGERED: n = 112 (43%). Fills per episode in the window: median 1, max 4; retrigger rows as the first fill n = 4; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -4 (-18 .. 0); before b n = 72, on b n = 13, 1–5 after n = 7, later n = 20; share of the episode's gain already made at the fill: median (quartiles) 0.12 (0.07 .. 0.17)
  - the original STOP fired before s50: n = 89 (79% of 112) — of which before the breakout day itself n = 60; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 9 (8%); still in at s50: n = 14 (12%); status split: stopped_day0 n = 48, stopped n = 42, trailed n = 22
  - realized R of the catch: mean +1.62, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 14, >= 10R n = 7; sessions held median 1
  - kept, in the trade's ADR unit: the episode's gain = 22.8 (17.4 .. 28.3) ADR, the gain available from the fill = 19.5 (13.7 .. 25.2) ADR, the trade's P&L = -0.30 (-0.49 .. 0.28) ADR; kept share of the episode's gain median (quartiles) -0.013 (-0.023 .. 0.016), mean 0.032; kept share of the available gain median -0.015 (-0.027 .. 0.019); kept >= half of the episode's gain n = 0, >= half of the available n = 3, >= a quarter of the episode's gain n = 12
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 20; best fill's kept share of the episode's gain median 0.002 (-0.018 .. 0.043), >= half n = 1

Any-K view on the covered measurable breakouts (n = 258; the entry tables' ORH5 filled C0 rows, E in the catch window): com: 130 (50%), E − b median -6; comb: 89 (34%), E − b median -8; full: 76 (29%), E − b median +0; k10: 122 (47%), E − b median -4; k5: 126 (49%), E − b median -6; tl: 122 (47%), E − b median -5.

Reverse view, 2017-21: 13368 judgeable fills (E in the watch window and E <= last session - 83; 0 later fills unjudgeable): in a big-winner catch window 482 (3.6%); anywhere in [trough-20, peak] of a big winner 1473 (11.0%)

Reverse view, 2022-24: 7791 judgeable fills (E in the watch window and E <= last session - 83; 1170 later fills unjudgeable): in a big-winner catch window 182 (2.3%); anywhere in [trough-20, peak] of a big winner 527 (6.8%)

## the +50% sensitivity set

### 2017-21, x150 — composition (n = 4,182 episodes after exclusions)

| item | value |
|---|---|
| episodes by trough year | 2017: n = 265, 2018: n = 439, 2019: n = 351, 2020: n = 2,365, 2021: n = 762 |
| tickers | n = 1,871 (episodes per ticker max 10) |
| close at the trough, $ (median, quartiles) | 24.48 (12.48 .. 49.93) (n = 4,182) |
| ADR20 at the trough (median, quartiles) | 0.059 (0.042 .. 0.081) (n = 4,182) |
| 63-session return into the trough (median, quartiles) | -0.19 (-0.42 .. 0.05) (n = 4,182) |
| gain trough → peak (median, quartiles) | 0.77 (0.60 .. 1.08) (n = 4,182); >= +200% n = 243 |
| sessions trough → peak (median, quartiles) | 56 (45 .. 73); peak extended past the 63-session window n = 1,457; extension truncated at the cut n = 0 |
| sessions trough → s25 / s50 (median) | 9 / 27 (n = 4,182) |
| EP-gap start (a >= 10% gap on >= 3x volume within 5 sessions of the trough) | n = 170 (4%) |
| trough moved to a lower close inside the run / a lower universe-failing close just before it / a lower close in the 10 sessions before | n = 2,886 / 535 (see log for the universe-fail count) |
| split inside [trough − 60, peak] (flag only) | n = 0 |

| breakout class (one per episode) | primary: longest window, span <= 5 ADR60, sideways | span <= 4 ADR60 | span <= 7 ADR60 | unit ADR20(b-1), span <= 5 | no sideways rule | SHORTEST window (post hoc, added after the first build) |
|---|---|---|---|---|---|---|
| measurable_breakout | 1,864 (45%) | 2,073 (50%) | 1,411 (34%) | 1,861 (45%) | 1,869 (45%) | 2,632 (63%) |
| ep_gap | 162 (4%) | 166 (4%) | 162 (4%) | 161 (4%) | 163 (4%) | 156 (4%) |
| late_base | 2,064 (49%) | 1,861 (45%) | 2,405 (58%) | 2,098 (50%) | 2,061 (49%) | 1,362 (33%) |
| no_consolidation | 21 (1%) | 37 (1%) | 11 (0%) | 5 (0%) | 18 (0%) | 21 (1%) |
| other | 71 (2%) | 45 (1%) | 193 (5%) | 57 (1%) | 71 (2%) | 11 (0%) |

A base breakout AND a gap start (overlap, primary rule): n = 155.

The measurable breakouts under the primary rule (n = 1,864): breakout day b − trough median (quartiles) 12 (7 .. 20) sessions; base length L 25 (16 .. 39); the base contains the trough 1,595 (86%); base span 4.5 (4.1 .. 4.8) ADR60 = 4.4 (3.8 .. 4.9) ADR20; base depth 0.18 (0.14 .. 0.24); share of the episode's gain made at the close BEFORE b 0.13 (0.08 .. 0.18) and at b's close 0.22 (0.16 .. 0.29); the breakout close over the base high 0.43 (0.18 .. 0.92) ADR20; b opened with a gap of 1.4 (0.4 .. 3.8)%.
The expansion-day version (range >= 1 ADR20, close in the top 30%, volume >= 1.5x the 50-day) holds on 531 (28%) of them — range ok 1,335 (72%), close location ok 1,347 (72%), volume ok 879 (47%).
The late-base episodes (n = 2,064): the first close above the longest base's high came when 0.52 (0.41 .. 0.66) of the gain was already made, b − trough 18 (13 .. 28) sessions, base depth 0.25 (0.20 .. 0.31), the base contains the trough 1,066 (52%).

### 2017-21, x150 — what we did

**2017-21, x150** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 4,182 | 100% of 4,182 |
| with a measurable breakout (primary rule) | n = 1,864 | 45% of 4,182 |
| … whose base nights our watch covers | n = 1,801 | 97% of 1,864 |
| … WATCHED (a watch row on some base night) | n = 709 | 39% of 1,801 |
| … watched with a trendline level (C0_tl) on some base night | n = 707 | 39% of 1,801 |
| … watched on the night before the breakout day | n = 403 | 22% of 1,801 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 589 | 33% of 1,801 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 184 | 10% of 1,801 |
| … triggered and STILL IN at s50 (half the gain made) | n = 45 | 2% of 1,801 |
| … near the breakout and still in at s50 | n = 31 | 2% of 1,801 |
| … triggered and KEPT >= half of the episode's gain | n = 5 | 0% of 1,801 |
| … near the breakout and kept >= half of the episode's gain | n = 3 | 0% of 1,801 |
| … triggered and kept >= half of the gain available from the fill | n = 8 | 0% of 1,801 |

All 4,182 big winners, any class (covered n = 4,108): watched 1,518 (37%); triggered (tl fill in the catch window) 1,005 (24%); still in at s50 70 (2%); kept >= half of the episode's gain 9 (0%); a tl fill ANYWHERE in [trough − 20, peak] 2,936 (71%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 1,215 (30%).

**2017-21, x150** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 1,801)

- NOT WATCHED on any base night: n = 1,092 (61% of 1,801). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - prior move < 30% (no pole) (`prior_move`): n = 634 (58% of 1,092)
  - close below the 50-day (`sma50`): n = 332 (30% of 1,092)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 96 (9% of 1,092)
  - under $10M median dollar volume (`universe_dv`): n = 15 (1% of 1,092)
  - raw close under $5 (`universe_price`): n = 11 (1% of 1,092)
  - pole data artifact (`pole_artifact`): n = 2 (0% of 1,092)
  - passes (my rebuild) (`pass`): n = 2 (0% of 1,092)
  - on the night before the breakout day alone: `prior_move` n = 721; `sma50` n = 175; `universe_dv` n = 117; `close_above_pole_high` n = 60; `universe_price` n = 17; `pass` n = 2
- WATCHED BUT NO TRIGGER in the catch window: n = 205 (11%); of them a trendline level existed on some base night (C0_tl) n = 203, watched on the night before the breakout n = 79, a tl fill came later anywhere before the peak n = 135, some other K filled in the window n = 86
- TRIGGERED: n = 589 (33%). Fills per episode in the window: median 1, max 6; retrigger rows as the first fill n = 38; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -9 (-24 .. 0); before b n = 436, on b n = 44, 1–5 after n = 41, later n = 68; share of the episode's gain already made at the fill: median (quartiles) 0.11 (0.06 .. 0.17)
  - the original STOP fired before s50: n = 491 (83% of 589) — of which before the breakout day itself n = 350; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 53 (9%); still in at s50: n = 45 (8%); status split: stopped n = 267, stopped_day0 n = 227, trailed n = 77, time_exit n = 18
  - realized R of the catch: mean +0.82, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 52, >= 10R n = 25; sessions held median 1
  - kept, in the trade's ADR unit: the episode's gain = 19.0 (13.9 .. 25.6) ADR, the gain available from the fill = 16.7 (12.1 .. 23.3) ADR, the trade's P&L = -0.23 (-0.46 .. 0.26) ADR; kept share of the episode's gain median (quartiles) -0.011 (-0.024 .. 0.013), mean 0.017; kept share of the available gain median -0.012 (-0.028 .. 0.014); kept >= half of the episode's gain n = 5, >= half of the available n = 8, >= a quarter of the episode's gain n = 30
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 77; best fill's kept share of the episode's gain median -0.005 (-0.020 .. 0.022), >= half n = 8

### 2022-24, x150 — composition (n = 2,381 episodes after exclusions)

| item | value |
|---|---|
| episodes by trough year | 2022: n = 924, 2023: n = 807, 2024: n = 650 |
| tickers | n = 1,176 (episodes per ticker max 9) |
| close at the trough, $ (median, quartiles) | 22.32 (11.14 .. 46.84) (n = 2,381) |
| ADR20 at the trough (median, quartiles) | 0.051 (0.039 .. 0.068) (n = 2,381) |
| 63-session return into the trough (median, quartiles) | -0.21 (-0.35 .. -0.03) (n = 2,381) |
| gain trough → peak (median, quartiles) | 0.70 (0.58 .. 0.94) (n = 2,381); >= +200% n = 72 |
| sessions trough → peak (median, quartiles) | 56 (39 .. 69); peak extended past the 63-session window n = 815; extension truncated at the cut n = 134 |
| sessions trough → s25 / s50 (median) | 10 / 26 (n = 2,381) |
| EP-gap start (a >= 10% gap on >= 3x volume within 5 sessions of the trough) | n = 135 (6%) |
| trough moved to a lower close inside the run / a lower universe-failing close just before it / a lower close in the 10 sessions before | n = 1,601 / 326 (see log for the universe-fail count) |
| split inside [trough − 60, peak] (flag only) | n = 26 |

| breakout class (one per episode) | primary: longest window, span <= 5 ADR60, sideways | span <= 4 ADR60 | span <= 7 ADR60 | unit ADR20(b-1), span <= 5 | no sideways rule | SHORTEST window (post hoc, added after the first build) |
|---|---|---|---|---|---|---|
| measurable_breakout | 1,153 (48%) | 1,325 (56%) | 787 (33%) | 1,152 (48%) | 1,156 (49%) | 1,739 (73%) |
| ep_gap | 132 (6%) | 134 (6%) | 134 (6%) | 132 (6%) | 133 (6%) | 132 (6%) |
| late_base | 1,060 (45%) | 887 (37%) | 1,362 (57%) | 1,073 (45%) | 1,057 (44%) | 497 (21%) |
| no_consolidation | 8 (0%) | 21 (1%) | 3 (0%) | 2 (0%) | 7 (0%) | 8 (0%) |
| other | 28 (1%) | 14 (1%) | 95 (4%) | 22 (1%) | 28 (1%) | 5 (0%) |

A base breakout AND a gap start (overlap, primary rule): n = 124.

The measurable breakouts under the primary rule (n = 1,153): breakout day b − trough median (quartiles) 10 (6 .. 18) sessions; base length L 24 (15 .. 36); the base contains the trough 1,030 (89%); base span 4.5 (4.1 .. 4.7) ADR60 = 4.3 (3.8 .. 4.8) ADR20; base depth 0.17 (0.14 .. 0.22); share of the episode's gain made at the close BEFORE b 0.13 (0.07 .. 0.18) and at b's close 0.24 (0.17 .. 0.30); the breakout close over the base high 0.47 (0.19 .. 1.01) ADR20; b opened with a gap of 1.5 (0.3 .. 4.6)%.
The expansion-day version (range >= 1 ADR20, close in the top 30%, volume >= 1.5x the 50-day) holds on 379 (33%) of them — range ok 886 (77%), close location ok 863 (75%), volume ok 580 (50%).
The late-base episodes (n = 1,060): the first close above the longest base's high came when 0.50 (0.40 .. 0.63) of the gain was already made, b − trough 19 (12 .. 29) sessions, base depth 0.24 (0.20 .. 0.30), the base contains the trough 782 (74%).

### 2022-24, x150 — what we did

**2022-24, x150** — the funnel (shares are of the row named in the third column)

| step | n | share of |
|---|---|---|
| big winners (episodes) | n = 2,381 | 100% of 2,381 |
| with a measurable breakout (primary rule) | n = 1,153 | 48% of 2,381 |
| … whose base nights our watch covers | n = 1,138 | 99% of 1,153 |
| … WATCHED (a watch row on some base night) | n = 319 | 28% of 1,138 |
| … watched with a trendline level (C0_tl) on some base night | n = 315 | 28% of 1,138 |
| … watched on the night before the breakout day | n = 184 | 16% of 1,138 |
| … TRIGGERED (a tl ORH5 fill, E in the catch window) | n = 262 | 23% of 1,138 |
| … triggered NEAR the breakout (E within 5 sessions of b) | n = 108 | 9% of 1,138 |
| … triggered and STILL IN at s50 (half the gain made) | n = 26 | 2% of 1,138 |
| … near the breakout and still in at s50 | n = 20 | 2% of 1,138 |
| … triggered and KEPT >= half of the episode's gain | n = 1 | 0% of 1,138 |
| … near the breakout and kept >= half of the episode's gain | n = 1 | 0% of 1,138 |
| … triggered and kept >= half of the gain available from the fill | n = 5 | 0% of 1,138 |

All 2,381 big winners, any class (covered n = 2,351): watched 809 (34%); triggered (tl fill in the catch window) 503 (21%); still in at s50 40 (2%); kept >= half of the episode's gain 3 (0%); a tl fill ANYWHERE in [trough − 20, peak] 1,530 (65%); any K (k5/k10/full/tl/com/comb where held) triggered in the catch window 753 (32%).

**2022-24, x150** — where we lost them (measurable-breakout episodes whose base nights are covered, n = 1,138)

- NOT WATCHED on any base night: n = 819 (72% of 1,138). The furthest gate any base night reached (my rebuilt funnel; the first failing gate in evaluation order):
  - prior move < 30% (no pole) (`prior_move`): n = 481 (59% of 819)
  - close below the 50-day (`sma50`): n = 280 (34% of 819)
  - a close above the pole high (base resolved) (`close_above_pole_high`): n = 42 (5% of 819)
  - under $10M median dollar volume (`universe_dv`): n = 10 (1% of 819)
  - raw close under $5 (`universe_price`): n = 6 (1% of 819)
  - on the night before the breakout day alone: `prior_move` n = 579; `sma50` n = 106; `universe_dv` n = 97; `close_above_pole_high` n = 26; `universe_price` n = 11
- WATCHED BUT NO TRIGGER in the catch window: n = 107 (9%); of them a trendline level existed on some base night (C0_tl) n = 103, watched on the night before the breakout n = 34, a tl fill came later anywhere before the peak n = 71, some other K filled in the window n = 73
- TRIGGERED: n = 262 (23%). Fills per episode in the window: median 1, max 5; retrigger rows as the first fill n = 14; non-mature n = 0.
  - timing: E − b (sessions; negative = before the breakout day) median (quartiles) -3 (-19 .. 0); before b n = 170, on b n = 33, 1–5 after n = 19, later n = 40; share of the episode's gain already made at the fill: median (quartiles) 0.14 (0.08 .. 0.19)
  - the original STOP fired before s50: n = 207 (79% of 262) — of which before the breakout day itself n = 141; the exit (trail / day-3 rule), not the stop, ended it before s50: n = 29 (11%); still in at s50: n = 26 (10%); status split: stopped n = 107, stopped_day0 n = 101, trailed n = 48, time_exit n = 6
  - realized R of the catch: mean +0.98, median (quartiles) -1.00 (-1.00 .. 0.67); >= 3R n = 30, >= 10R n = 13; sessions held median 1
  - kept, in the trade's ADR unit: the episode's gain = 18.8 (13.9 .. 26.6) ADR, the gain available from the fill = 15.7 (11.8 .. 23.2) ADR, the trade's P&L = -0.29 (-0.47 .. 0.30) ADR; kept share of the episode's gain median (quartiles) -0.014 (-0.027 .. 0.017), mean 0.022; kept share of the available gain median -0.016 (-0.031 .. 0.020); kept >= half of the episode's gain n = 1, >= half of the available n = 5, >= a quarter of the episode's gain n = 20
  - counting EVERY fill in the window (not only the first): some fill still in at s50 n = 39; best fill's kept share of the episode's gain median -0.005 (-0.021 .. 0.040), >= half n = 2

Reverse view, 2017-21: 13368 judgeable fills (E in the watch window and E <= last session - 83; 0 later fills unjudgeable): in a big-winner catch window 1400 (10.5%); anywhere in [trough-20, peak] of a big winner 5323 (39.8%)

Reverse view, 2022-24: 7791 judgeable fills (E in the watch window and E <= last session - 83; 1170 later fills unjudgeable): in a big-winner catch window 615 (7.9%); anywhere in [trough-20, peak] of a big winner 2448 (31.4%)

## Validation of the gate rebuild (from 02_catch_<era>.txt)

- 2017-21: [x200] 994 episodes; covered 986; watched 391; triggered 310; validation on covered nights {'in_table_pass': 4284, 'in_table_fail': 0, 'not_in_table_fail': 23491, 'not_in_table_pass': 0} (in_table_fail + not_in_table_pass should be ~0); 3s
- 2017-21: [x150] 4182 episodes; covered 4108; watched 1546; triggered 1021; validation on covered nights {'in_table_pass': 16149, 'in_table_fail': 0, 'not_in_table_fail': 99642, 'not_in_table_pass': 30} (in_table_fail + not_in_table_pass should be ~0); 8s
- 2022-24: [x200] 414 episodes; covered 409; watched 186; triggered 155; validation on covered nights {'in_table_pass': 1684, 'in_table_fail': 2, 'not_in_table_fail': 10502, 'not_in_table_pass': 7} (in_table_fail + not_in_table_pass should be ~0); 1s
- 2022-24: [x150] 2381 episodes; covered 2351; watched 828; triggered 516; validation on covered nights {'in_table_pass': 6903, 'in_table_fail': 10, 'not_in_table_fail': 58913, 'not_in_table_pass': 45} (in_table_fail + not_in_table_pass should be ~0); 5s
