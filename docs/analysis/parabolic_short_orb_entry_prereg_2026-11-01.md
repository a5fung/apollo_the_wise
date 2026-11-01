# #314 — the parabolic short re-walked on HIS entry and stop: short the opening-range-low break, stop at the day's high, Russo's 1–3 session limit — pre-registration (2026-11-01, written BEFORE any minute bar was read or any outcome seen; FROZEN pre-pull 2026-11-01, see §7)

**What this is.** The 10-28 five-year replay (`docs/analysis/parabolic_short_replay_prereg_2026-10-21.md`, frozen `c70d7eaa`,
STEP 0 pinned `c0a53f03`) walked the detector's climax nights with OUR entry — a break of the PRIOR session's low within three
sessions, stop above the climax high + min(3%, 0.5 × ATR14), a third covered at +1R, a 3-/5-session time stop — and read CAN'T
TELL in both populations: the EP-floor population 252 shorts +0.08R [−0.04, +0.20], small caps 168 shorts −0.07R [−0.18, +0.06],
and **not one short reached 3R in five years**. Its own correction the same evening: the 1–3 day limit is RUSSO's rule ("shorts
last 1–3 days — longer is a red flag"), so the time stop is not the likely defect; the likelier gap is the ENTRY and the STOP.
The settled 10-28 shorts carried a stop a **median 36% above the entry** (mean 48%; quartiles 22% / 62%; `episodes.tsv`
`r5_risk / r5_entry_price`): with R that wide a 3R winner needs the stock to lose more than its whole price. His entry is
intraday and far tighter: *"Trigger: break of the opening-range low, or, if it keeps rising, a break below a 5-minute candle.
Stop: the high of the day (most of the time)"* (`docs/methodology/operator_shared_notes.md` §Parabolic short, ~L1725 — his own
shared notes), and the hold is Russo's 1–3 sessions (same file, §Russo, ~L2156). **This registration walks the SAME climax
nights on THAT entry and stop, with minute bars, and nothing else changes.**

**THE LINE.** Offline research, $0, no money, no live change, no recommendation about live trading. A paper or live step for the
parabolic short is his call; the live shadow (`mi_parabolic_short_shadow`) keeps recording unchanged. A CAN'T TELL or FAIL here is
a statement about THIS version (the detector's climax + this entry/stop/exit), never about the setup — his standing frame: these
setups have paid him for years; a backtest that misses it is OUR implementation's defect.

**The seal.** No bar, row or minute file dated 2025-01-01 or later enters a number: the request list is seal-clean by construction,
the minute loader refuses any row dated ≥ 2025-01-01, and the daily loaders drop every row after 2024-12-31 at read and assert it.
Two touches of post-seal bytes, disclosed (the 10-28 registration disclosed the same): (1) era B's split table is read through
2026-10-16 (`ps_common.SPLITS_THROUGH`) because that is the adjustment basis of the era-B export — a split executing in 2025–26 is
what makes a 2024 bar's raw price = adjusted × factor; those rows carry a date and a ratio, no price or outcome; (2) the era-B
export's 2025+ rows are parsed by the chunked reader and dropped before any array is built (`load_daily_subset(cut=2024-12-31)`,
asserted). No 2025+ price is ever held.

---

## 1. Population — the 10-28 climax nights, the same exclusions, re-derived from the pinned `climax_list.tsv`

The climax list is read AS PINNED (sha256 `53af1961…`, 844 rows: P1 418, P2 243, P2small 183; P2small ⊂ P2 — the same
(ticker, D0) rows under a second label; 661 distinct (ticker, D0)). Eras as frozen there: A = 2016-06-23..2022-03-16 (the rebuilt
Alpaca file, calendar `cb702_pre_v2/sessions.txt`), B = 2022-03-17..2024-12-19 (Polygon, calendar `calendar_B.txt`). Nothing is
re-detected; no climax is added or removed by hand.

**Exclusions applied BEFORE the walk (the 10-28 rules, re-applied to this walk's 3-session span):**
- `open_at_seal` — re-derived from THIS walk's rule: the walk occupies D0+1..D0+3, so a night is walkable only when D0+3 (on its
  era's calendar) ≤ 2024-12-31, i.e. D0 ≤ 2024-12-26. The 10-28 rule (D0+7 ≤ seal) excluded 17 rows; this rule excludes 10 rows = 8 distinct
  nights (ATOM, PDYN, INTZ 12-27; GRRR, HOLO, AENT, ONDS, SATX 12-30; two of them twice under P2 and P2small) — the 12-20..12-26 nights
  AIRE, HOUR, LXEH, SES are walkable here and were not on 10-28; stated so the two n's are reconciled. Counted, never in a number.
- `void_adjustment_event` — the 10-28 flag as pinned (a vendor-booked adjustment break inside the 120-row window or the D0+1..D0+7
  span): P1 4, P2 2, P2small 1. Kept as pinned for comparability (a break inside D0+4..D0+7 cannot touch this walk, but re-cutting the
  flag would be a new rule).
- `distribution` — the 10-28 evidence class as pinned in `episodes.tsv` (`distribution_class`): P1 1, P2 0. Kept as pinned, same reason.

**The pre-walk population (counts derived 2026-11-01 from the pinned files, before any minute bar; the reviewer's independent recount
matched every cell):**

| population | climax rows | era A / B | not walkable at the seal | void_adjustment_event | distribution | **pre-walk population** | A / B | distinct companies |
|---|---|---|---|---|---|---|---|---|
| P1 (the live $5 / $10M floors; **no cap floor** — the $250M cap was a 10-28 BESIDE row, never in the deciding P1) | 418 | 289 / 129 | 4 | 4 | 1 | **409** | 286 / 123 | 299 |
| P2 (small caps, the complement, no floors) | 243 | 148 / 95 | 4 | 2 | 0 | **237** | 148 / 89 | 199 |
| P2small (P2 under $250M; beside, never pooled) | 183 | 114 / 69 | 2 | 1 | 0 | **180** | 114 / 66 | 153 |

**Exclusions applied AT the walk (each a counted row in the funnel, never a silent drop; the vocabulary is fixed here):**
- `minute_missing` — the daily file has a bar for a walked session but the minute file has no rows for that (ticker, session). If the
  position is open at the miss the row reads `minute_missing_open`. Re-pullable; printed with the (ticker, session) list.
- `no_orb` — no bar starting at 09:30 on the entry session (a late first print, a halt at the open). The range needs the opening
  minute itself; a first print at 09:40 is not a "15-minute range" of one bar (review, 11-01). Applies to all three range widths.
- `basis_mismatch` — on any walked session present: the minute session's lowest low ÷ the daily RAW low outside [0.90, 1.10] (the bars
  are not the daily file's company, year or basis).
- `shape_mismatch` — the minute session's high ÷ the daily RAW high, or its low ÷ the daily RAW low, outside [0.98, 1.02]: a thinner
  feed (IEX prints a range inside the consolidated one) or a clock not converted to ET (the window lands on other hours) prints a
  narrower or displaced range while the level can still pass the basis band. **Calibrated 2026-11-01 on 715 local (ticker, session)
  pairs** (Alpaca SIP minute bars vs the two daily exports: 235 of this walk's own request pairs across the eras + 480 random era-B
  pairs): the minute high ÷ daily high and low ÷ low sit within 0.22% of each other on 99.5% of sessions (the exact same prints
  aggregate to both), the open within 1.2%, while the close differs by up to 5% (the official close is the 16:00 auction print, not
  the 15:59 bar) — so H and L carry the verdict, O and C are printed as diagnostics only.
- **The pull's own gate:** `basis_mismatch` + `shape_mismatch` together above **2% of the sessions checked** → **the RUN REFUSES**
  (no `result.txt`; the reason names the first failures) — a wrong pull is re-pulled, never walked with its worst names excluded
  (the excluded names would lean toward the reverse-split and collapse names, the short's best cases). Under 2% the failing episodes
  are counted exclusions and listed.
- `split_in_walk` — era B: a `cb702_splits.psv` split executing in (D0, D0+3]; era A: the raw ÷ adjusted factor on the last walked bar
  differs from D0's by more than 1% (`ps_common.JUMP_FAC_CHANGE`). R across two price scales is never booked.
- `hole` — the daily series has no bar on a walked session but has later bars (a halt). `hole_open` when the position is open at it
  (the 10-28's `degraded`).
- `ended_before_entry` / `ended_mid_walk` — the daily series ends (era A: before 2022-06-30; era B: before 2024-12-31) or the era-B
  owner's `delisted_utc` falls before a walked session: no entry → `ended_before_entry` (no R); position open → `ended_mid_walk`, booked
  at the last minute close with the 10-28 haircut variant (§4).
- `void_bad_geometry` — the stop is less than 1% above the entry (`(stop − entry) / entry < 0.01`). Registered NOW because the
  10-28 module's own void (`risk <= 0`) can never fire here (stop ≥ entry + $0.02 by construction) and a 5-cent R turns an ordinary fall
  into a 100R print that would own the mean and the tail. Counted; a beside row prints the base numbers with them in.
- `untriggered` — the entry session's low never trades through the opening-range low. No entry, no R.
- `episode_already_open` — rule (c) of the 10-28 replay re-applied: one open episode per COMPANY KEY, D0 order, advance-before-decide.
  Applied ONCE from the primary walk's close dates (settled → exit date; untriggered / void / no_orb / minute_missing / basis_mismatch /
  shape_mismatch / split_in_walk / hole-before-entry / ended_before_entry → the entry session, nothing was opened; ended_mid_walk /
  hole_open / minute_missing_open → the last walked session) and REUSED for every secondary, so the ten variants share one population.

**n = settled episodes** (triggered, then exited by `stop` or `time_stop`), admitted by rule (c), per population; per era beside.

## 2. The entry session

**D0+1 — the session after the climax day, on the era's calendar.** The detector scores the climax on D0's close (the 17:15 ET
`parabolic_scan`), so the first session a trader acting on it can short is D0+1; his A+ setup is "up three or four days in a row …
usually day 3 or 4", and the detector's `days_up_streak ≥ 3` on D0 makes D0+1 day 4 or later. The 10-28 walk let the trigger come on
any of D0+1..D0+3 (its settled entries fell 240 / 154 / 69 / 100 on D0+1 / +2 / +3 / later by calendar days), so this walk's triggered
set is SMALLER by construction — the D0+2 / D0+3 re-arm is a named "not answered" item (§9), not a secondary. **No entry if the
opening-range low is never broken on D0+1.**

## 3. Entry, stop, exit — the rules, fixed now

Minute bars = regular hours only: bars whose start time is in [09:30, 16:00) ET; on the 13:00 early closes
(`asis_common.EARLY_CLOSE`) bars at/after 13:00 are after-hours prints and dropped. The 16:00 bar is not used. `ts_et` is the bar's
START minute.

- **Opening range (ORB).** PRIMARY = the **5-minute** range: the bars starting 09:30..09:34 (ORB low = their lowest low; the
  session's high so far includes their highs). Pre-declared SECONDARIES: the **1-minute** range (the 09:30 bar alone) and the
  **15-minute** range (09:30..09:44). All three are walked and printed; the verdict is on the 5-minute range only. **The range needs
  a bar starting at 09:30**; without one → `no_orb` for every width.
- **Trigger.** From the first bar AFTER the range: the first bar whose `low ≤ ORB_low − $0.01` (price traded at or through a
  stop-sell resting one cent under the range low). A low exactly AT the range low does not trigger.
- **Fill.** `ORB_low − $0.01` when the bar opens at or above that level (the stop elects inside the bar); the bar's OPEN when it opens
  below it (a gap through — the first trade below the level is the open; pessimistic for a short).
- **Stop.** The session's HIGH as of the entry minute = **the highest high of every bar from 09:30 through the bar BEFORE the entry
  bar, plus $0.01. R = stop − entry.** The entry bar's own high is NOT in the stop: its prints cannot be ordered (on a gap-through
  fill the open IS the fill, so every later print of that bar comes after it; on an outside bar the order is unknown), and taking it
  in was the first draft's look-ahead (review HIGH #2, 11-01: a gap-through fill at 9.50 whose bar ran to 10.90 booked +1.06R under
  the first draft; a real short was stopped for −1R). **If the entry bar's high reaches the stop, the STOP is booked on the entry bar
  (−1R, exit = stop) and the bar is counted `ambiguous_entry_bar`** — exact for a gap-through, the adverse reading for an outside bar.
  The count and share of ambiguous entry bars are printed; the first draft's rule (the entry bar's high inside the stop) is walked as
  the BESIDE variant `o5h3x` on the primary only, never deciding. `R / entry < 1%` → `void_bad_geometry` (§1).
- **The stop is live on every later minute bar, across sessions.** A bar that OPENS at or above the stop covers at its open (a gap
  through the stop; pessimistic); a bar whose high reaches the stop covers AT the stop. Reason `stop`.
- **Exit — Russo's limit.** PRIMARY: cover at the close of the **3rd session**, the entry session counting as 1 (D0+3), at the close
  of its last regular-hours bar (the 15:59 bar; 12:59 on an early close). Pre-declared SECONDARIES: 1 session (D0+1's close) and
  2 sessions (D0+2's close). Reason `time_stop`.
- **Same-bar rule (pessimistic).** If the time-exit bar itself reaches the stop (open ≥ stop or high ≥ stop), the STOP is booked, not
  the close. There is no profit target in any variant; "target" here is the time exit.
- **One leg.** No flush cover, no add, no trail: his entry and stop with Russo's limit, nothing of ours layered on. Realized
  R = (entry − exit) ÷ R. MFE = (entry − lowest low after the entry bar, through the exit bar) ÷ R; MAE = (highest high after the entry
  bar − entry) ÷ R, floored at 1.0 on a stop.
- **The nine variants** = {1, 5, 15}-minute range × {1, 2, 3}-session hold, all walked in one pass from the same minute file and all
  printed with the same measures, plus the beside stop rule `o5h3x`. **The decision is (5-minute, 3 sessions, the stop before the
  entry bar). Nothing is chosen after seeing the grid.**

## 4. Costs, borrow, the fill optimism, the delisted walk — the 10-28 rules, cited

- **Exit slippage beside every headline** (10-28 §Costs, the data standard's §4 step 8): the covering leg's exit price × (1 + x) for
  x ∈ {0.1%, 0.2%}; the entry stays at the fill rule. The verdict is decided at zero cost; a PASS whose interval's lower end falls to
  ≤ 0 at 0.1% reads "PASS at zero cost only" (10-28 round 4, L4).
- **Tick slippage on BOTH legs, beside (review MEDIUM #4, 11-01).** The risk here is 2–10% of the price, against 36% on 10-28, so an
  exit-only 0.1% is 0.01–0.05R and cannot see fill optimism. For k ∈ {1, 2, 5} cents: the entry fills k lower, every cover (stop or
  time exit) fills k higher; the planned R (stop − entry at the fill rule) stays the unit, so **R_k = R − 2k ÷ risk** and ADR P&L_k =
  (entry − k − exit − k) ÷ entry ÷ ADR20. Three rows printed next to the headline with the same bootstrap and verdict function.
- **The fill-at-level optimism, named and calibrated.** A stop order fills at the first PRINT through its level, not at the level; a
  minute bar cannot see that print. The reviewer's martingale null (a price with NO drift, minute bars built from sub-minute prints,
  `scratchpad/314orb/review/calib3.py`), re-run after the stop fix with the fills ALSO taken from the sub-minute path
  (`scratchpad/314orb/fix/null_fills.py`, 5 seeds × 400 names each): with 0.18%-per-print paths and ~2% risk the exact-fill rule reads
  **+0.05R under no edge** and the path-fill rule +0.00R; with 0.36%-per-print paths and ~8% risk, +0.12R vs +0.07R. The bias is the
  fill rule, nothing else in the mechanics; the 1-cent row neutralises the realistic case, the 5-cent row the violent one. **Hence the
  reading rule in §5: a PASS must survive the 2-cent row, or it is "PASS at zero cost only" and treated as CAN'T TELL (fill optimism).**
  The 10-28 replay filled at its level too; this walk's tighter R makes the same optimism bigger in R terms, which is why it is
  registered here and not there.
- **Borrow** (10-28 §Substitutions (b)): historical borrow is not visible, so easy-to-borrow is ASSUMED at the entry. n overstates what
  could have been shorted, most of all in P2. Borrow fees are not modelled.
- **The delisted walk** (10-28 round 3/4, the data standard's C1): an `ended_mid_walk` position is booked at the last minute close of
  the last walked session, classed by `ps_walk.ending_class` on the daily series (collapse = raw last close < $1 or ≤ −50% against the
  close 60 sessions earlier; pinned = the last 10 closes within 1%; other), and ALSO at the adverse haircut — cover at **1.25 × the last
  close** for a collapse ending and for an `other` ending whose last bar is a one-day fall of 20% or more. The verdict is computed three
  ways — (a) settled only (deciding), (b) + ended_mid_walk at the last close, (c) + the haircut — and reads "<verdict (a)>, depends on
  N delisted episodes" when (b) or (c) differs (`ps_walk.verdict_three_ways`, called as is).
- **ADR P&L** (10-28 §ADR P&L): (entry − exit) ÷ entry ÷ ADR20%, ADR20% = the 10-28 `adr20` column of the pinned `episodes.tsv` (the mean
  of (high − low) ÷ close over the 20 sessions ending at D0 − 1), joined on (ticker, D0, population).

## 5. Measures and the decision bar — numbers written before the run, mirroring the 10-28 grid

Per population (P1, P2 deciding; P2small beside), pooled and per era, for the primary and every secondary:
- **n**, **mean R** with the month-block bootstrap 95% interval (blocks = the entry month = D0+1's month, 2,000 draws, seed 702,
  `runner.block_bootstrap_ci` via `ps_walk.mean_ci` — the 10-28 call, unchanged), **ADR P&L**, **win rate** (share of settled with
  R > 0), **share reaching 3R** two ways — realized R ≥ 3 (the tail clause's measure) and MFE ≥ 3R beside (what a 3R target would have
  caught), **the tail clause** (≥ 3 settled trades at ≥ 3R from ≥ 3 companies and ≥ 3 entry months; ≥ 2R beside), **the top 10 by R**
  (ticker, D0, entry, stop, R in dollars, exit reason, R), the exclusion funnel, the risk-to-entry distribution (median, quartiles —
  against the 10-28 median of 36%), the ambiguous-entry-bar count, the three tick rows and the two exit-slippage rows.
- **The bar (the 10-28 §Bars, verbatim in substance):** **PASS** = n ≥ 30 AND the interval's lower end > 0 AND mean ADR P&L > 0 AND the
  tail clause passes. **FAIL** = n ≥ 30 AND the upper end < 0. Else **CAN'T TELL** (n < 30 whatever the interval; an interval above zero
  without the tail = "CAN'T TELL (positive, no tail)"). Computed by `ps_walk.base_verdict` on rows carrying the 10-28 field names, so
  the two replays are judged by ONE function. **The reading rule on top (§4):** a PASS whose lower end is ≤ 0 at the 0.1% exit-slippage
  row OR at the 2-cent entry+cover row prints "PASS at zero cost only" and §10 treats it as CAN'T TELL (fill optimism).
- **What the bar can and cannot do (the reviewer's calibration, 11-01, re-run after the stop fix):** a build with a real −2%/day drift
  at ~2% risk PASSes 3 of 3 seeds and stronger drifts 6 of 6, while zero drift reads CAN'T TELL 3 of 3 — a correct build is not failed
  by construction. ⚠ The ≥ 3R tail clause does NOT discriminate at a 2% risk (a no-edge population still puts 27–36 trades at ≥ 3R):
  it stays in the bar for comparability with 10-28, but here the interval and the tick rows carry the decision.
- **Comparability line, printed beside:** the 10-28 primary — P1 n 252, +0.0767 [−0.0429, +0.1975], ADR P&L +0.26, 0 at ≥ 3R; P2 n 168,
  −0.0670 [−0.1818, +0.0551], ADR P&L −0.31, 0 at ≥ 3R; P2small n 133, −0.0564 [−0.1641, +0.0685]. Win rate of the 10-28 settled set
  47.5% (558 settled across the three labels).
- **Expectations fixed now (each can miss; a miss is reported first and changes no rule):** the triggered share of the pre-walk
  population (numerator and denominator both over the whole pre-walk population, before rule (c)) is between 40% and 85% (a parabolic
  name's day-after session usually trades under its opening range at some point; under 40% says the ORB minute is not where these names
  break, over 85% says the range is too thin to mean anything); the median risk-to-entry is under 15% (against 36% on 10-28 — the whole
  point of the tighter stop); the win rate is UNDER the 10-28's 47.5% (a tight stop is hit more often; the edge, if present, is in the
  size of the winners); at least one settled short reaches 3R realized in each of P1 and P2 (the 10-28 had none anywhere; zero again
  says the 3R bar is not where this setup's tail lives and the exit, not the entry, is the next question); `minute_missing` under 10% of
  walked (ticker, session) rows in era B and under 25% in era A (delisted small caps are where Alpaca's by-symbol minute history is
  thinnest); `basis_mismatch` + `shape_mismatch` under 2% of the sessions checked (above that the run refuses — the pull is wrong, not
  the names); `void_bad_geometry` under 5% of triggered episodes; ambiguous entry bars under 10% of triggered episodes (a one-minute bar
  that breaks the 5-minute low AND clears the day's high is a range wider than the opening range itself).

## 6. The data contract — minute bars

**The request** — `scripts/probes/_314_orb_entry_1101/minute_request.tsv` (written by `orb_replay.py --request` from the pinned
climax list and the two calendars; nothing else read): one row per distinct (ticker, session_date) over every walkable climax night's
D0+1, D0+2, D0+3 — **1,844 rows, 476 tickers, sessions 2016-07-06..2024-12-31** (653 of the 661 distinct (ticker, D0) are walkable;
overlapping windows of one ticker — AHG 2021-10-15 / 10-18 / 10-20 — are requested once per session). Columns: `ticker`,
`session_date`, `why` (the populations and D0 the session serves, and which of the three sessions it is). No row is dated ≥ 2025-01-01
(asserted at write). The request set is also re-derived by the walk from the pinned climax list and must equal the file's.

**The pull (the main loop, on the server; this code never touches the network):** Alpaca market data v2, **feed = SIP, timeframe =
1Min, `adjustment = raw`**, for each requested (ticker, session_date), the regular session (start 09:30 ET, end 16:00 ET exclusive,
built with `ZoneInfo("America/New_York")`; the pull may take the whole day and the replay keeps [09:30, 16:00)); every returned
timestamp converted to ET before the `HH:MM` is taken (`scripts/probes/_cb_backtest/fetch_minutes.py` has the window and the DST-proof
conversion — but it requests `Adjustment.SPLIT` and writes a minute INDEX; this pull needs `Adjustment.RAW` and the CSV below).
**Departure from the task text, stated:** the task said "split-adjusted to match the daily file". Alpaca's `adjustment=split` adjusts
to TODAY's basis, not to era A's as-of-2022 basis or era B's as-of-2026-10-16 basis, so a match to either daily file is not available
from the vendor; RAW is the one basis that is defined (the dollars printed), the one in which "one cent under the low" is a real tick,
and within a 3-session window with no split R is identical on either basis. A split inside the window is a counted exclusion
(`split_in_walk`), and every walked session's minute H / L / low-level are cross-checked against the daily file's RAW O/H/L/C
(`basis_mismatch`, `shape_mismatch`, §1; above 2% the run refuses). The repo's `ALPACA_DATA_FEED` defaults to `iex` — the pull must
pass the feed explicitly.

**The file** — `scripts/probes/_314_orb_entry_1101/minute_bars.csv.gz`: ONE gzipped CSV with a header,
`ticker,session_date,ts_et,open,high,low,close,volume`; `session_date` = `YYYY-MM-DD` (the ET session); `ts_et` = the bar's START
minute in ET after DST conversion, `HH:MM` (`HH:MM:SS` with `:00` accepted); prices in raw dollars; one row per bar; a (ticker,
session_date) with no bars is simply absent (the replay counts it `minute_missing`). Duplicate (ticker, session_date, ts_et) rows
refuse the run. Rows dated ≥ 2025-01-01 refuse the run.

**The sidecar** — `scripts/probes/_314_orb_entry_1101/minute_bars.meta.json`, written by the pull: `{"feed": "sip", "adjustment":
"raw", "tz": "America/New_York", "request_sha256": "<sha256 of minute_request.tsv>", "source": "alpaca v2 StockBarsRequest",
"pulled_at": "<ISO>"}`. The walk refuses unless `feed`, `adjustment` and `tz` read exactly so and `request_sha256` equals the request
file on disk. The local minute stores under `apollo_data/cb702*/minutes*` are NOT a source: they hold 235 of the 1,844 pairs and were
pulled split-adjusted (`Adjustment.SPLIT`), a basis this walk does not accept.

## 7. The code, the refusals, the freeze record

`scripts/probes/_314_orb_entry_1101/orb_replay.py` (imports `ps_common` / `ps_walk` from `_314_replay_build` by path — never
copied: `mean_ci`, `base_verdict`, `tail_clause`, `verdict_three_ways`, `ending_class`, the loaders, the constants, `sha`,
`freeze_missing`, `doc_body_sha`) and `orb_goldens.py` (the synthetic fixtures of §8). Three stages, each its own invocation:
- `--dry-run` — the fixtures of §8 through `walk_episode` (every fixture × all nine variants + the beside rule printed), the reviewer's
  adversarial cases as claims (an early close, a hole with the position open, an entry on the last bar, rule (c) on an overlapping
  company, a 2025 minute row at the loader, a duplicate minute), then synthetic end-to-end trees (two climax rows, one per era, on
  fixture #1's bars, written to a temp dir under the session scratchpad: calendars, daily exports with era A's raw companion, a split
  table, a climax list, an episodes file, a minute file, a sidecar) through the WHOLE `--walk` path — the loaders, the basis + shape
  checks, rule (c), the 10-28 verdict functions — with the pins overridden to that tree's: the clean tree, five REFUSAL trees (a
  doubled-price pull, a wrong-feed pull, a sidecar naming `iex`, a 2025 minute row, a corrupted data pin — each must refuse with its
  reason) and two EXCLUSION trees (a split inside the walk, an owner delisted at D0+2). No real input opened; writes `dry_run.txt`.
  Refuses (exit 2) on any hand number off by more than 1e-9 or any claim mismatched.
- `--request` — reads the pinned `climax_list.tsv` and the two calendars (their sha256 checked against the pins below); writes
  `minute_request.tsv`; refuses if the file exists or any session ≥ 2025-01-01 would be written.
- `--walk` — the one run. Refuses unless: every data pin below matches the file on disk; the CODE pins written ABOVE this document's
  marker (`orb_replay.py`, `orb_goldens.py`, `minute_request.tsv`, `dry_run.txt`) match the files on disk; below the marker the main
  loop has pasted `freeze_commit` (the commit that carried this document and those four files BEFORE the pull), `doc_body` (this
  document's bytes above the marker), `minute_bars` and `minute_bars_meta`; `git cat-file` of the four files and of this document at
  `freeze_commit` hash to what is on disk (local git, no network — the proof that nothing changed once bars were on disk); the sidecar
  reads feed sip / adjustment raw / tz America/New_York and names the request on disk; `dry_run.txt` ends `DRY RUN COMPLETE`;
  `result.txt` does not exist. Reads ONLY: the minute file and its sidecar, the pinned climax list, `episodes.tsv` (adr20,
  distribution_class), the two calendars, the two daily exports with era A's raw companion and era B's split table (through
  `ps_common` / `asis_common` loaders, every row after 2024-12-31 dropped at read and asserted). Writes `result.txt`, `episodes_orb.tsv`
  (one row per climax row, every variant's columns prefixed `o<range>h<hold>_`, the beside rule `o5h3x_`) and
  `episodes_orb.tsv.numbers.json` (every printed number, for an independent re-derivation). Any refusal names its reason and writes
  `result.refused.txt`.

**Data + imported-module pins (sha256, computed 2026-11-01 from the files on disk; every one equals the 10-28 freeze record's where that
record has it):**

| key | file | sha256 |
|---|---|---|
| climax_list | `apollo_data/ps314/climax_list.tsv` | `53af1961b7b0a19325d378433f150fccd0253dc3498a8b05b83e73aa78facf6a` |
| episodes | `apollo_data/ps314/episodes.tsv` | `5a712f21d29a0d4a0cedd71d03b28d0d3cf4d3e87a33b896bbadbc4ccf9e8b89` |
| calendar_B | `apollo_data/ps314/calendar_B.txt` | `a17d991a25a1b6b6977c388f352213142868635f94c2010813a7a0f8ef79d2be` |
| sessions_A | `apollo_data/cb702_pre_v2/sessions.txt` | `098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0` |
| export_A | `apollo_data/cb702_pre_v2/daily_closes_all.csv.gz` | `0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d` |
| raw_A | `apollo_data/cb702_pre_v2/daily_raw_close.csv.gz` | `f978db45074e9109178a1755c232fa1e684a6f83dab96ab007a26b12008f1444` |
| export_B | `apollo_data/cb702/daily_closes_all.csv.gz` | `ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba` |
| splits_B | `apollo_data/cb702/cb702_splits.psv` | `3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b` |
| ps_common.py | `scripts/probes/_314_replay_build/ps_common.py` | `6f99467e3a2bc5c36292b87d875a469a7571000b240c663632862722d8bccc10` |
| ps_walk.py | `scripts/probes/_314_replay_build/ps_walk.py` | `a4decccfebb4d49dd6328163f12a1bc1624513ae7a196ecf3ea41d9f48762cb0` |
| asis_common.py | `scripts/probes/_705_asis_1026/asis_common.py` | `4d36d6a42532dc782b7ccdce86a530a3b0bd948f66db74d5f1ab7af79a4562c4` |
| runner.py | `scripts/probes/_cb_backtest/runner.py` | `a4f016720f8226933367ae3d776a7067d9d94dea634b28e5e5685e186bc3ad69` |
| consolidation_breakout.py | `agents/market_intelligence/consolidation_breakout.py` | `e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b` |

**The freeze, two stages (review MEDIUM #3, 11-01: the first draft pinned the code only AFTER the pull, so nothing proved it was
unchanged once bars were on disk):**
1. **Pre-pull (this document, above the marker):** the code pin table below (`orb_replay.py`, `orb_goldens.py`, `minute_request.tsv`,
   `dry_run.txt`, computed after the final dry run), then ONE commit on `main` carrying this document and those four files — the main
   loop's step, named here; `freeze_commit` is that commit's hash. `--walk` reads the code pins from this body and refuses on any
   difference from disk, and refuses unless the committed copies at `freeze_commit` equal the disk copies. ⚠ Re-running `--dry-run`
   after the freeze rewrites `dry_run.txt` (its header carries the date) and changes its sha: any code edit after the freeze is a new
   pin table, a new commit and a new `freeze_commit` — never a quiet re-run.
2. **Post-pull (below the marker, pasted by the main loop AFTER the pull and BEFORE the walk):** `freeze_commit`, `doc_body` (the sha256
   of this document's bytes above the marker, as `--print-pins` prints it), `minute_bars` and `minute_bars_meta` (the pull's two files).
   The body pin is a record, not a gate on itself (a document cannot carry its own hash above the line): the gate on the body is the
   committed copy at `freeze_commit`.

**WOULD-FAIL-IF (checks the code performs; any one exits non-zero):** a minute row dated ≥ 2025-01-01; a daily row after the seal
surviving a read; a data pin, a code pin, a sidecar field or a committed copy that does not match; a duplicate (ticker, session,
minute); more than 2% of the sessions checked outside the basis / shape bands; a settled episode whose entry session ≠ D0+1 or whose
exit session > D0+hold; a stop on the entry bar booked at any price but the stop or not flagged ambiguous; a realized R not equal to
(entry − exit) ÷ (stop − entry) recomputed from the booked prices; a settled row behind a `basis_mismatch` / `shape_mismatch` /
`split_in_walk` exclusion (asserted per episode); two admitted episodes of one company key open on one night (asserted after rule
(c): each closes on or before the next one's D0); the request file's (ticker, session) set ≠ the set the walk derives from the pinned
climax list; `dry_run.txt` not ending `DRY RUN COMPLETE`.

## 8. The synthetic dry run — hand numbers, written before the code ran

Every fixture is a short list of minute bars per session (`ts`, open, high, low, close); sessions S1 = D0+1, S2, S3; the 5-minute
range = the bars starting 09:30..09:34. The code must reproduce every number below to 1e-9; `dry_run.txt` carries the printout. Rows
9b, 12 and 13 were added at the 11-01 review, their numbers written BEFORE the stop rule was changed in the code; rows 1–11 are
unchanged by the new stop rule (in every one the entry bar's high is under the prior high).

| # | fixture | hand walk | expected |
|---|---|---|---|
| 1 | **wins, time exit** — S1 09:30 10.00/10.50/9.80/10.20 · 09:31 10.20/10.60/10.10/10.40 · 09:32 10.40/10.70/10.30/10.50 · 09:33 10.50/10.65/10.35/10.40 · 09:34 10.40/10.55/10.20/10.30 · 09:35 10.30/10.45/10.00/10.05 · 09:40 10.05/10.10/9.70/9.75 · 10:00 9.75/9.90/9.40/9.50 · 12:00 9.50/9.60/9.00/9.10 · 15:59 9.10/9.20/8.90/9.00; S2 09:30 8.80/9.00/8.50/8.60 · 09:34 8.60/8.70/8.30/8.40 · 15:59 8.40/8.50/8.00/8.10; S3 09:30 8.10/8.20/7.80/7.90 · 15:59 7.90/8.00/7.50/7.60; adr20 = 0.10 | ORB5 low 9.80, high 10.70; 09:35 low 10.00 > 9.79 no (its high 10.45 joins the day high: still 10.70); 09:40 low 9.70 ≤ 9.79 → fill 9.79 (open 10.05 ≥ 9.79); stop = 10.70 + 0.01 = 10.71 (the 09:40 bar's own high 10.10 is not in it); R = 0.92; no later high ≥ 10.71; S3 last close 7.60 | entry 9.79, stop 10.71, risk 0.92, ambiguous 0; hold 3: R = 2.19 / 0.92 = **2.380434782608696**, `time_stop`, sessions_held 3; hold 1 (exit 9.00): **0.858695652173913**; hold 2 (exit 8.10): **1.836956521739130**; slippage 0.1%: (9.79 − 7.6076) / 0.92 = **2.372173913043478**; 0.2%: **2.363913043478261**; ticks: R − 0.02/0.92 = **2.358695652173913**, R − 0.04/0.92 = **2.336956521739130**, R − 0.10/0.92 = **2.271739130434783**; ADR P&L at 1c = (9.78 − 7.61) / 9.79 / 0.10 = **2.216547497446374**; MFE (low 7.50): **2.489130434782609**; MAE (high 9.90): **0.119565217391304**; ADR P&L = 2.19 / 9.79 / 0.10 = **2.236976506639428**; win |
| 1b | the same bars, 15-minute range | ORB15 = bars < 09:45 → low 9.70, high 10.70; 10:00 low 9.40 ≤ 9.69 → fill 9.69; stop 10.71; R 1.02 | hold 3: 2.09 / 1.02 = **2.049019607843137** |
| 1c | the same bars, 1-minute range | ORB1 = the 09:30 bar → low 9.80; 09:31..09:35 lows > 9.79; 09:40 → fill 9.79; stop 10.71 | hold 3: **2.380434782608696** (same as #1) |
| 2 | **stopped at the day high** — S1 09:30 20.00/20.80/19.90/20.50 · 09:31 20.50/21.00/20.40/20.90 · 09:32 20.90/21.20/20.70/20.80 · 09:33 20.80/20.90/20.30/20.40 · 09:34 20.40/20.50/20.00/20.10 · 09:35 20.10/20.20/19.85/19.95 · 09:40 19.95/20.50/19.90/20.40 · 10:00 20.40/21.30/20.30/21.00 · 15:59 21.00/21.10/20.90/21.00; S2, S3 flat 21.00 | ORB low 19.90; 09:35 low 19.85 ≤ 19.89 → fill 19.89; stop 21.20 + 0.01 = 21.21; R 1.32; 10:00 high 21.30 ≥ 21.21, open 20.40 < stop → cover 21.21 | R = **−1.0**, `stop`, sessions_held 1, exit on S1; MAE 1.0; ambiguous 0 |
| 3 | **never triggered** — S1 09:30 5.00/5.20/4.90/5.10 · 09:31..09:34 inside 4.95–5.30 · 09:35 5.10/5.15/4.90/5.00 (low AT the range low) · later lows ≥ 4.95; S2, S3 any | ORB low 4.90; no bar low ≤ 4.89 | `untriggered`, no R |
| 4 | **gap through the level** — S1 09:30..09:34 30.00–31.00 (low 30.00, high 31.00) · 09:35 29.50/29.60/29.20/29.30 · 15:59 29.30/29.40/29.00/29.10; S2 09:30 29.00/29.20/28.00/28.10 · 15:59 27.00/27.10/26.90/27.00; S3 09:30 26.90/27.00/25.00/25.10 · 15:59 24.10/24.20/23.90/24.00 | 09:35 opens 29.50 < 29.99 → fill at the open 29.50; stop = 31.00 + 0.01 = 31.01; R 1.51; the entry bar's high 29.60 < 31.01; S3 close 24.00 | R = 5.50 / 1.51 = **3.642384105960265**, `time_stop`; reaches 3R; ambiguous 0 |
| 5 | **same-bar tie on the exit bar** — #1's S1 and S2; S3 09:30 8.10/8.20/7.80/7.90 · 15:59 8.00/10.80/7.90/8.00 | the exit bar's high 10.80 ≥ 10.71 and open 8.00 < stop → the STOP is booked, not the 8.00 close | R = **−1.0**, `stop`, sessions_held 3 |
| 6 | **3-session time exit, a loser** — #1's S1; S2 09:30 9.00/9.30/8.90/9.20 · 15:59 9.50/9.60/9.40/9.50; S3 09:30 9.60/9.90/9.50/9.80 · 15:59 10.20/10.40/10.10/10.30 | no high ≥ 10.71; S3 close 10.30 | R = −0.51 / 0.92 = **−0.554347826086957**, `time_stop`, sessions_held 3 |
| 7 | **stopped at a session's open** — #1's S1; S2 09:30 11.00/11.20/10.90/11.10 | S2's first bar opens 11.00 ≥ 10.71 → cover at the open | R = −1.21 / 0.92 = **−1.315217391304348**, `stop`, sessions_held 2 |
| 8 | **minute file missing a session** — #1's S1; S2 absent from the minute file while the daily file has the bar | position open at the miss | `minute_missing_open`, no R; counted |
| 9 | **no opening range** — S1's first bar at 09:40 | no bar starting 09:30 | `no_orb`, no R — for the 1-, 5- AND 15-minute range (the first draft traded a one-bar "15-minute range" here) |
| 9b | **no 09:30 bar** — S1 09:31 10.20/10.60/10.10/10.40 · 09:32 10.40/10.70/10.30/10.50 · 09:40 … · 15:59 … | bars inside the window but none starting 09:30 | `no_orb` for every range width |
| 10 | **ended mid-walk, collapse** — #1's S1; S2 09:30 8.80/9.00/8.50/8.60 · 15:59 0.70/0.75/0.55/0.60; the daily series ends at S2 (raw last 0.60) | booked at the last close 0.60; raw last < $1 → collapse → haircut cover 0.75 | `ended_mid_walk`, class collapse; R at the last close = 9.19 / 0.92 = **9.989130434782609**; haircut = 9.04 / 0.92 = **9.826086956521739** |
| 11 | **void geometry** — S1 09:30 10.02/10.05/10.00/10.03 · 09:31..09:34 inside 10.00–10.05 · 09:35 10.01/10.02/9.98/9.99 | fill 9.99; stop 10.06; R 0.07; 0.07 / 9.99 = 0.70% < 1% | `void_bad_geometry` |
| 12 | **outside entry bar** (review case A) — #1's 09:30..09:34 · 09:35 10.30/11.50/9.70/11.40 · 15:59 11.40/11.45/11.30/11.40; S2, S3 flat 11.40 | 09:35 low 9.70 ≤ 9.79, open 10.30 ≥ 9.79 → fill 9.79; stop = the high BEFORE the bar 10.70 + 0.01 = 10.71; R 0.92; the bar's own high 11.50 ≥ 10.71 → the stop is booked on the entry bar | R = **−1.0**, `stop`, sessions_held 1, exit_ts 09:35, ambiguous 1, MAE 1.0, MFE 0.0; ticks −1.021739130434783 / −1.043478260869565 / −1.108695652173913. **Beside rule `o5h3x`** (the bar's high inside the stop): stop 11.51, R 1.72, time exit 11.40 → **−0.936046511627907** |
| 13 | **gap-through fill, then the bar rallies** (review case B) — #1's 09:30..09:34 · 09:35 9.50/10.90/9.40/10.80 · 15:59 9.00/9.10/8.90/9.00; S2 flat 9.00; S3 flat 8.00 | 09:35 opens 9.50 < 9.79 → fill 9.50; stop 10.71; R 1.21; the bar's high 10.90 ≥ 10.71 → stopped on the entry bar (the first draft booked **+1.06R** here) | R = **−1.0**, `stop`, sessions_held 1, ambiguous 1. **Beside rule `o5h3x`:** stop 10.91, R 1.41, time exit 8.00 → **1.063829787234043** |

## 9. What this does NOT answer

- **Borrow** — availability and cost at 09:35 on the day after a climax (hard-to-borrow is the norm in exactly these names; assumed
  easy). **Intraday liquidity at the ORB minute** — a one-cent stop-sell under a 5-minute low in a $3 stock may fill far worse; the
  slippage and tick rows are a proxy, not a measurement. **The sealed 2025–26 period** (#710) — not read.
- **His other trigger** — "if it keeps rising, a break below a 5-minute candle" — and the **D0+2 / D0+3 re-arm** when D0+1 never
  breaks: both are entries this registration does not walk (a later registration if this one earns it). **Adds / pyramiding**, the
  "losing momentum" top-day short (D0 itself), and **his stop management** after entry (Russo moved the stop to the day's high as the
  day developed; we fix it at entry).
- **The ORB window's own definition** beyond the three ranges (his notes name the 1-minute, 5-minute and the first 30/60-minute bars
  for the long side; the 30- and 60-minute ranges are not walked).
- **Minute-bar honesty** — a 1-minute bar cannot order its own prints. The choices here are the adverse ones where a choice exists
  (gap-through fills at the open, the stop before the time exit, the stop on an ambiguous entry bar), with ONE named exception that no
  bar rule can remove: the fill AT the level (§4 — the sub-minute print through the level is invisible; bounded by the tick rows and
  the reading rule, measured on the null, and the first thing a tick-data registration would fix).
- Everything the 10-28 registration listed under its own "does not answer" and carries over: the Perplexity exclusion, the earnings
  gate, survivorship after the fix, vendor differences between the eras, spin-offs the distribution rule cannot see.

## 10. Consequence fixed now

- **Any verdict goes to him as a reading about THIS version, with the 10-28 line beside it.** PASS (surviving the 2-cent row) → the
  entry / stop / exit of this registration become the CANDIDATE for the shadow's next design, put to him through CHANGE_PROCESS (entry,
  stop, time stop are his call; the shadow's current rules stay until he rules). "PASS at zero cost only" → CAN'T TELL (fill
  optimism): the next registration needs prints, not minute bars. CAN'T TELL → the shortfall named (n, tail, or interval) with what
  would make it decidable; no re-read without a dated event or a new registration. FAIL → reported with n; under his frame the next
  question is which of our pieces (the detector's climax, D0+1 only, the range width) misses his setup — never "no edge".
- Nothing live changes on any cell. No paper rung is proposed by this document.

---

## Revisions

- 2026-11-01 — written (Fable, under the main loop's "start day" card for #314). Reviewed by the advisor before the code was written:
  the raw-basis departure stated (§6), the R floor registered (§1), the seal re-derived for a 3-session walk (§1), the session-close
  and early-close conventions fixed (§3), the bar built by calling the 10-28 functions (§5), the request de-duplicated and placed
  before rule (c) (§1, §6), the two-stage freeze (§7), the funnel vocabulary split between `minute_missing` and `ended_mid_walk`
  (§1), the gap-open stop and the missing-session fixtures added (§8).
- 2026-11-01 — the first dry run ran AFTER the §8 numbers were written: 86 claims, 86 OK; `minute_request.tsv` written (1,844 rows, 476
  tickers, 2016-07-06..2024-12-31, no row at or past the seal). No minute bar, no real outcome, was read.
- 2026-11-01 — **the review round (Fable, the main loop's review card; every finding verified against the code, none rejected):**
  (HIGH #1) the pull check was a close-only ±10% that a wrong feed or a shifted clock passes → the daily RAW O/H/L/C is loaded and
  the minute H and L are checked at ±2% (calibrated on 715 local pairs), the run REFUSES above 2% of sessions instead of excluding
  the worst names, and a sidecar declares feed/adjustment/tz (§1, §6); (HIGH #2) the stop took the entry bar's own high → the stop is
  the high BEFORE the entry bar, a bar that reaches it books the stop (fixtures 12, 13; the first draft's rule kept as the beside
  `o5h3x`; `ambiguous_entry_bar` counted) (§3, §8); (MEDIUM #3) the code was pinned only after the pull → the code pins sit above the
  marker and a pre-pull commit is gated by `git cat-file` (§7); (MEDIUM #4) fills at the exact level → the tick rows on both legs, the
  fill optimism measured on the null (+0.05R / +0.12R under no edge; +0.00 / +0.07 with path fills) and the "survive 2 cents" reading
  rule (§4, §5, §10); (LOW) the range needs a 09:30 bar (fixtures 9, 9b); the §7 asserts now exist in the code; the P1 label; the
  seal's two disclosed touches; the triggered share over one population; refusal and exclusion trees in the dry run. A defect the
  review did not list, found by the new split tree: era B's split factor was called with ISO strings against date objects and would
  have crashed on the first walked ticker WITH a split (79 of the 178 era-B tickers have one) — fixed. Dry run: 164 claims, 164 OK.
  The population, the request file and the data pins are unchanged.

## — FROZEN 2026-11-01 — the code pins (pre-pull; computed after the final dry run; `--walk` reads this table)

| key | file | sha256 |
|---|---|---|
| orb_replay.py | `scripts/probes/_314_orb_entry_1101/orb_replay.py` | `1fa1cbbf0d0a4272ded0c8973f44e5c41d52bb23e1b4d55639e5cf4a3c504fb3` |
| orb_goldens.py | `scripts/probes/_314_orb_entry_1101/orb_goldens.py` | `b36bed75e4921bb8af63d1e5f83b9c456b71e2b600d236c56e2114ed13219989` |
| minute_request | `scripts/probes/_314_orb_entry_1101/minute_request.tsv` | `10ecab5db36c932d80523974659b5eff18a3f3809a5e5b9787934b8945f71b2d` |
| dry_run | `scripts/probes/_314_orb_entry_1101/dry_run.txt` | `8d5918edf75795e726264ff790ea363f674a9d5e7edcb751b8e9ba74ce26e4fa` |

Every byte above the next line is the frozen body (`doc_body`). Below it, the main loop pastes the post-pull pins (§7, stage 2); the
disclosed step the registration names in advance.

<!-- FREEZE -->
## Freeze record (the main loop; pasted after the pre-pull commit and the pull, before `--walk`)

- freeze_commit = cda8e943f365f1abdf9edd2340c1e5b1b0d6e7ee
- doc_body = 43f47d9e895c1124502ec1da8a3199dc32fff87db0cd069d2f24ea00cd7ce6fc
- minute_bars = bdadd36997913cd3f584f069bb97a352359e73cfb6c7c83b48aa05ca4e510b9f
- minute_bars_meta = cda8d4a7068acaf7d79402ffd5169b6cbff44190df4be47bcc0e43f44ab3e6b5
- pull (2026-11-01, main loop, his "allow pull"): `scripts/probes/_314_orb_entry_1101/pull_minutes.py` in apollo-market, Alpaca SIP, raw, 1-minute; 874 dates, 1,840 of 1,844 (ticker, session) pairs with bars, 641,431 bars, 0 date errors; the 4 empty pairs are in `pull_log.txt` (counted exclusions per §5).
- minute file location: kept OUT of git (7.8 MB), at `/Users/alvinfung/apollo_data/ps314/orb_1101/minute_bars.csv.gz` (and the probe folder), identified by the `minute_bars` pin above.
- walk (2026-11-01, run ONCE): `scripts/probes/_314_orb_entry_1101/walk_stdout.txt` + `result.txt` — P1 o5h3 n 301, mean R +0.3640 [+0.1012, +0.6313], 29 trades >= 3R / 29 companies / 19 months -> PASS (holds at the 2c entry-and-cover row: +0.3166 PASS; 5c: CAN'T TELL); P1 era B alone CAN'T TELL; P2 CAN'T TELL. A blind recount and an adversarial trade audit run before it is reported.
- verification (2026-11-01, before the result was reported; `scripts/probes/_314_orb_entry_1101/verify/`): (1) BLIND RECOUNT from this document's words, no shared code — every headline number MATCHES (216 of 216 fields, 1e-9) and 0 per-trade differences across 621 settled rows; disclosed: the bootstrap's seed KEY string is not registered (`orb:P1:pooled` gives the headline interval, `orb_o5h3:P1` the grid line's [+0.1063, +0.6538]; both lower ends > 0), and two side counts flip on exact-2R/3R float rounding (none that decides). (2) ADVERSARIAL AUDIT — the mechanics HOLD (20 hand-walks from the raw bars, no look-ahead, no fill better than the bars, 18 gap-throughs at the open); the PASS WEAKENS: the top 5 shorts carry 48% of R (without them: +0.194 [-0.022], CAN'T TELL), fills halfway to the trigger bar's low +0.270 [+0.007] / at its close CAN'T TELL, 5c CAN'T TELL, borrow 300%/yr CAN'T TELL, size > 10% of the trigger bar's volume excluded CAN'T TELL; without 2020 +0.371 PASS; without Rule 201 entries +0.426 PASS; the 29-at-3R count alone is within what §5's no-edge null produces (27-36). READING: PASS by the registered rule, about THIS version; thin and tail-driven. Nothing live changes.

