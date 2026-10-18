# Consolidation Breakout (Qullamaggie's breakout — a SETUP inside the consolidation family, #702)

**Phase**: SHADOW (forward recorder only — NO order path, NO `mi_strategies` row, NO sizing, NO Telegram on a normal night).
The offline backtest (`scripts/probes/_cb_backtest/`) decides whether it graduates; paper is decided on THIS setup's own
evidence (CHANGE_PROCESS rule 5; his ruling 2026-10-17 lifted the EP-first hold), live stays his sign-off.
**Origin (SOURCED)**: Qullamaggie, *"My 3 timeless setups that have made me tens of millions"*, shared by the operator
2026-10-17 — `docs/methodology/operator_shared_notes.md` §"2026-10-17 — Qullamaggie's BREAKOUT setup" and §"2026-10-17 —
his note on the breakout ENTRY" — plus additions of his own (group RS, RS, entry/exit timing, bull vs bear phase).
**Provenance rule (ADR 0013 §2 / #358): every cohort-shaping constant below cites its source or says it is a parameter
the backtest chooses; a constant with no source is telemetry or a parameter, never presented as sourced.**
**Code**: the pure core `agents/market_intelligence/consolidation_breakout.py` (`cb`, no I/O, shared by both callers) ·
the offline runner `scripts/probes/_cb_backtest/` · the forward recorder
`agents/market_intelligence/consolidation_breakout_shadow.py` (job `consolidation_breakout_shadow`, **17:48 ET mon–fri**,
tables `mi_consolidation_breakout_{watch,entry,exit,sic}`).

> **It is a SETUP, not Confirm, and not Family A's coil.** A setup has a defined buy and a defined stop (CLAUDE.md "SETUP vs
> FAMILY"). This one **buys the opening-range high on the breakout day and stops at the low of that day** (no wider than one
> ADR, else it abstains). Family A Confirm buys the close above the base high and stops at the base low. The two are never
> pooled, have their own names, tables and numbers. `docs/HANDOFF.md` once called Confirm "the consolidation breakout
> recorder" — that wording was about Confirm and is corrected there.

## What it records, in one paragraph's worth of facts

- **Watch list** — every night, every stock in the universe that passes the C0 structural gates gets ONE row
  (`mi_consolidation_breakout_watch`): all features as JSON, the pivot for each of four breakout levels K, and the cell flags
  C0…C7 (+ two reported-only cells) per K.
- **Entry rows** — the next session, for every watch row whose pivot that day's HIGH cleared, five rows per K (four minute
  variants `orh1 / orh5 / orh60 / pivot` + the daily `close` variant): a simulated fill and stop, or the NAMED reason there was
  none. An abstain is a row, never a gap.
- **Exit rows** — every filled entry is walked over all **15** exit arms (`cb.ARMS`) from stored daily bars, recomputed every
  night until each arm is mature.

## Definitions (computable; sessions, not calendar days; all on bars ≤ the watch night D unless stated)

Source column: **S** = sourced verbatim in `operator_shared_notes.md` (2026-10-17) · **R** = reuses an existing constant (cited) ·
**B** = a parameter the backtest chooses (P4 discovery read); NO source yet, never presented as sourced · **P** = fixed by the
approved plan, not by the article · **T** = telemetry only, never gates.

| Piece | Definition | Source | Code |
|---|---|---|---|
| Universe | common stock or ADR (or unknown type), ticker `^[A-Z]{1,5}$`, RAW close ≥ $5, 20-session median dollar volume ≥ $10M, ≥ 130 CONSECUTIVE sessions, not an exchange test symbol | **R**: universe floor reused from `rs_engine` — price floor $5 (reused `rs_engine.MIN_PRICE`; no sign-off of its own is on record) and median dollar-volume floor $10M (operator-signed 2026-06-15, #286; the sign-off is on the dollar-volume floor and lives in the `rs_engine` comment, no other document carries its text) | `cb.universe_ok`, `MIN_PRICE`, `MIN_DOLLAR_VOL` |
| Prior move | P = highest high in sessions [D−45, D−10]; pole_low = lowest low in [P−40, P]; high(P) / pole_low − 1 ≥ 0.30 | **S** *"anywhere from 30-100%+"*; the 40-session pole window is **P** (the article says only "sometime in the past 1-3 months") | `PRIOR_MOVE_MIN`, `POLE_LOOKBACK` |
| Base | the sessions after P up to D; 10 to 45 sessions long | **S** *"usually 2 weeks to 2 months"* (10 = two weeks; 45 ≈ two months, rounded up from ~43) | `BASE_MIN_SESSIONS`, `BASE_MAX_SESSIONS` |
| Base anchor | the base ends only if a CLOSE (not a wick) goes above high(P) | **R** the shipped HTF `_flag_resolved_by` (#592) | `_base_resolved` |
| Pivot (K) | `k5` / `k10` / `full` = highest high of the last 5 / 10 / all base sessions (HORIZONTAL levels); `tl` = the down-sloping trendline, projected one session ahead | k5 / k10 / full: **B** (the primary is picked in discovery, then frozen). `tl`: **S** his 2026-10-17 note *"a flag with a down sloping trend line and a breakout of that trend line"* — how the line is anchored and drawn is the #702 P1c reading of that sentence, tested BESIDE the horizontal levels | `PIVOT_KEYS`, `_down_trendline` |
| MA surfing | close ≥ SMA50; close ≥ 0.98 × SMA20; SMA50 rising over 10 sessions | **S** *"surfs the rising 10- and 20-day and sometimes the 50-day"* · **R** `anticipation._MA_NEAR_PCT` · 10-session slope **P** | `explain_watch`, `sma20_ok`, `sma50_rising` |
| Higher lows | lowest low of the last 5 sessions > the base low | **S** *"higher lows"*; the 5-session window is **B** | `higher_lows`, `RECENT_WINDOW` |
| Tightening | mean daily range of the last 5 sessions ÷ the first 5 base sessions ≤ 0.75 | **S** *"tightening range"* · **R** `flag_detector._RANGE_CONTRACTION_MAX` | `tightening_ok` |
| Retrace | ≤ 50% of the pole's range given back (a C1 term; "C1 without retrace" is reported beside, not deciding) | **R** `anticipation.COIL_HOLD_LIMIT` (Family A's signed hold rule) | `retrace_ok` |
| Deal-pin guards | median daily range of the last 5 sessions ≥ 0.5% (`deal_pin_median`); the #502 fresh deal-pin layer; a pole-window close jump > 50% on < 2× volume is a data artifact | **R** `flag_detector._DEAL_PIN_RANGE_THRESHOLD`, `_evaluate_fresh_pin`; artifact guard = `docs/setups/htf.md` "Flagpole data-artifact", its two literals now named `flag_detector._POLE_ARTIFACT_JUMP` / `_POLE_ARTIFACT_VOL_MULT` and imported here | `explain_watch`, `POLE_ARTIFACT_JUMP`, `POLE_ARTIFACT_VOL_MULT` |
| RS | percentile across the universe at D of the 21 / 63 / 126-session return; rs_best = the max of the three; ≥ 98 | **S** *"the 1 or 2% of stocks that are up the most over these 3 timeframes: 1-month, 3-month, 6-month"* | `RS_HORIZONS`, `RS_BEST_PRIMARY` |
| Group RS | SIC-2 group = median member 63-session return; groups with < 10 members → NULL; percentile across groups ≥ 80 | his addition; thresholds **B** | `group_returns`, `GROUP_PCT_MIN` |
| Phase (primary) | QQQ SMA10 > SMA20 and both higher than 1 session ago, at D | his addition — an ATTRIBUTION (operator-forwarded Gemini review, not in the article); the slope window is **B** | `phase_qqq_10_20` |
| Phase (alternative) | SPY and QQQ both close above their 50-day (cell C7) | **B** | `phase_spy_qqq_50` |
| Breakout volume, trigger-bar tightness, pole length, base depth, ATR14 slope | recorded | **T** — never gate | features |

## Cells (post-hoc flags on one watch row; the 8 deciding cells strict → loose)

C0 baseline (universe + prior move + base + a pivot + close ≥ SMA50 + the deal-pin guards) · **C1 Qullamaggie + the forwarded
10/20 market rule** (C0 + SMA20 tolerance + rising SMA50 + higher lows + tightening + retrace ≤ 50% + RS ≥ 98 + the QQQ phase) ·
C2 strict (C1 + prior move ≥ 50% + RS ≥ 99 + group ≥ 80) · C3 (C1 without phase) · C4 (C1 without RS) · C5 (RS ≥ 95) ·
C6 (C1 + group ≥ 80) · C7 (SPY + QQQ above their 50-day instead of the 10/20 rule). Reported beside C1, never deciding:
`C1_no_retrace`, `C1_no_tightening`; the slope-5 phase variant is stored as `C1_s5`.

## Entry, stop, exits

- **Breakout day E** = the first session after a watch night whose high clears the pivot. **One trade per base:** the first
  break of (ticker, pole date, K) is the trade, later breaks of the same base are stamped `retrigger = 1` (and
  `retrigger_chain` under the drift-robust key: poles ≤ 3 sessions apart are one base), reported apart.
- **Entry** (regular-hours minutes, slippage 0.1% = `ENTRY_SLIPPAGE_PCT`): `orh1 / orh5 / orh60` = the first minute after the
  1 / 5 / 60-minute opening range whose high exceeds max(opening-range high, pivot), filled at that level or at the minute's
  open if it gapped through (**S** *"The opening range highs can be the highs of the first 1-minute candle, the 5-minute
  candle or the 60-minute candle"*); `pivot` = the first minute above the pivot; `close` = the daily close if it is above the pivot.
- **Stop** = the low of the day AT THE FILL (minutes 09:30 … fill; the full-day low would be look-ahead). **Skip** if the stop
  is wider than ADR20 measured the session before (**S** *"stop should not be wider than the ATR or ADR"*).
- **Abstains (named, counted):** `no_minutes` · `minute_daily_mismatch` (minute high/low vs the daily's by > 1%) ·
  `minute_high_below_pivot` · `stop_at_or_above_fill` · `too_wide` · `no_opening_range_minutes` · `split_after_watch`.
  **No-trigger rows** (the level was never crossed): `no_minute_above_level` (minute variants) · `close_not_above_pivot` (close).
- **Day-0 walk:** after the fill the rest of day E is walked against the stop; a stop-out is a full −1R (worse on a gap) booked
  once for every arm and never reaches the daily walk.
- **Exits (daily walk from E+1; 15 arms in `cb.ARMS`):** the **S** grid *"sell 1/3 to 1/2 of the position after 3-5 days, and
  then move the stop to break even … trailed with the 10- or the 20-day moving average … You wait for the first CLOSE below the
  10-day"* = 1/3 or 1/2 × after session 3 or 5 × trail SMA10 or SMA20 (8 arms; primary `p33_s3_t10`), plus four sensitivities
  (`p33_s3_t10_early` trail live before the partial · `_close` trail filled at the signal close · `_nobe` no breakeven move ·
  `_ifprofit` partial only if the close is above the fill) and three controls (`trail10_only`, `stop_only`, `fixed_3r_12`).
  A trail signal fills at the NEXT OPEN (his 2026-09-29 execution ruling). Horizon 120 sessions, then marked and counted censored.
- **Mature** = a terminal exit, or the 120-session horizon reached with its next open behind it; anything else is an OPEN MARK,
  recorded and never in a decisive number.

## The forward shadow — what runs, nightly at 17:48 ET (mon–fri)

One job, one audit row (`consolidation_breakout_shadow_run`), under a 900 s budget that FAILS OPEN on timeout (an
`..._error` row, no raise — every step is idempotent). That `*_error` row is not silent: the audit self-check reads it
(`audit_invariants.check_audit_error_window` — any `*_error` event in the last 24 h — and `system_audit`'s
`audit_errors_per_day`), so a timeout is reported through the audit, not through a job-failure page. A step that crashes is
recorded and the others still run; the FIRST failure is re-raised after the audit row so `audit_wrap` records it and
`notify_job_failure` is the one page. No other Telegram.

**Order: watch → entries → exits.** Tonight's watch list is the one output nothing re-creates (the entries come back from the
3-session look-back, the exits are recomputed in full every night), so it runs FIRST: a slow or hanging minute fetch can cost
the entries a night, never the watch list.

1. **Tonight's watch list.** SQL prefilter (price ≥ 5, median dollar volume ≥ 7M — a strict superset of the module's) →
   `cb.universe_ok` → 130 consecutive sessions → RS percentiles over the WHOLE universe → group RS → phases (SPY/QQQ, joined by
   date) → `cb.explain_watch` → `cb.cell_flags` per K. Names with a split executed in their window and not yet applied to the
   stored bars sit the night out.
2. **Entries.** For each of the last **3** sessions E (oldest first): the previous session's watch rows whose pivot E's daily
   high cleared → candidates → one-trade-per-base stamping against every earlier candidate → E's minutes from
   `collector.get_alpaca_minute_bars_window(..., raise_on_error=True)` (batches of **25** - 25 x 390 minute bars fit one
   10,000-bar page; **a RAISED batch is asked once more, and 3 raised batches in a row (75 tickers) end the fetch**, after which the
   later look-back days of the same run do not ask again) → `cb.entry_variants` + `cb.close_entry` → five rows per candidate.
   **A returned dict means Alpaca ANSWERED** (#702): a ticker missing from it had no bars and is written as the retryable
   `no_minutes` abstain, an empty answer is never retried and never counts toward the stop. **A RAISED call is a failure and
   writes no row, on any look-back day:** a candidate in a batch that raised (or that the stop left unasked) is deferred and written
   the next night; on the OLDEST look-back day no later night reads it, so it is counted (`minutes_deferred_oldest`) and named in
   the `..._minutes_unavailable` audit event instead of being written as a false `no_minutes`. A `no_minutes` row may be
   overwritten by a later fetch (and only that row — a fill is never moved).
   **Splits are read before the breakout test.** The pivot was stored raw on night D; the 17:00 pull has since split-adjusted the
   stored bars, so E's bar and the pivot sit on two price scales. For a name with a split in (D, today] the pivot is carried into
   the stored units (#704: the scale is the splits ingest's OWN recorded verdict, `db.scale_from_split_rows` — the product of
   the factors it restated the bars by, 1.0 for a split it recorded as a phantom, unknown while any is unapplied; D's stored
   close against the close the watch row recorded stays as the cross-check, and a reading the data does not bear out is
   unexplained). A split the ingest recorded as a PHANTOM moved no bar and is no split here at all: the name is treated as
   unsplit (minutes fetched, variants fill). Only a PHANTOM reads 1.0: a split recorded `skipped_no_data` (the ingest wrote no
   bar — Polygon had none, OR the fetch failed, which is swallowed to an empty answer) and a split row written BEFORE the outcome
   column (outcome NULL) are both read at the table's ratio, so when the stored bars did not move they fail the cross-check and the
   name sits out — that case ages out within the 3-session look-back. A name that then breaks out
   abstains EVERY variant, named `split_after_watch` (minutes are raw as traded on E, the stored bars are not); a name that did
   not break out writes nothing, in either split direction. A name whose split is executed but not yet applied, or whose scale is
   unexplained, sits the entry step out for the night (counted in `entry_split_unresolved`, named in
   `entry_split_unresolved_tickers`); the look-back retries it once the split is applied.
3. **Exits.** Every filled entry with a non-mature arm has each of its NON-FINAL arms (of the 15) recomputed in full from stored
   bars; a mature arm is final and is neither recomputed nor overwritten. A split executing after E that MOVED a stored bar
   makes every still-open arm `unbookable` (stored fills are raw, stored bars retro-adjusted — the #667 HTF precedent); one the
   ingest recorded as a phantom is ignored, and one not yet applied defers the entry's walk to the next night
   (`exit_split_deferred`, no row written); an arm that settled before the split keeps its valid pre-split outcome. A forward window cut at a data hole ends `degraded`, and an entry still open past the
   horizon + 10 sessions is no longer re-walked. Bars are loaded 200 tickers at a time.
4. **Audit row** with watch count, universe size, the gate funnel, cells per K, new entries by status and reason, exits settled,
   SIC fetched/known, wall time, and the entry-step diagnostics: `entry_days_without_watch` (look-back sessions with no watch
   rows), `entry_split_rescaled` / `entry_split_unresolved` (+ `_tickers`), `exit_split_deferred`, `minutes_deferred` /
   `minutes_deferred_oldest` / `minutes_outage_days`, and `minutes_feed_down` (now evidence: 3 batches in a row RAISED).

Group RS needs SIC; the cache fills at most **300 names a night** (watch names first, then by dollar volume), so the first week
runs with a thin group RS (`grp_pct` NULL where a group has < 10 known members) and the group cells (C2, C6) read False
until it fills. The SIC is the CURRENT one, not the point-in-time one the backtest used.

### Verify-live (declared before the deploy)

- **EXPECT** (baseline: nothing exists — no rows in the four tables, no `consolidation_breakout_shadow` run in `mi_job_runs`):
  (1) the first market night after the deploy: a `success` run at 17:48 ET, one `consolidation_breakout_shadow_run` audit row,
  and **tens to a couple of hundred** watch rows for that `scan_date` (the backtest averaged ~210 a night over ~2,000
  universe names); `mi_consolidation_breakout_sic` gains up to 300 rows. (2) The first night a watch name's high clears its
  pivot: **5 entry rows per (name, K)** — a fill or a named abstain — and **15 exit rows per filled entry** the same night
  (the plan said 12; `len(cb.ARMS)` is 15). (3) Zero Telegram. (4) apollo-execution never imports the module. (5) Every
  minute-variant row carries `feed`, and it reads `sip` (the recorded prod feed; read the first night's values — see deviation 2).
- **DONE-WHEN:** the first entry has a mature row on every one of its 15 arms, and the review
  `consolidation_breakout_forward_read` (mature C1 primary-arm entries ≥ 30) has fired and been read.
- **WOULD-FAIL-IF:** watch rows exist and a pivot cross produces no entry row · a `success` run on a session writes 0 watch
  rows · a filled entry has fewer than 15 exit rows after the run that wrote it · the run row is `success` while the audit row
  lists `STEP ERRORS` · on `feed = 'sip'` rows, a `minute_daily_mismatch` or `minute_high_below_pivot` share well above the
  backtest's (it was SIP too) — on SIP that is a broken minute path, not an expected thin-feed artifact.

## Deviation list — where the forward recorder differs from the backtest

1. **Does NOT share Family A's coil detection.** Family A's coil/flag detectors (`anticipation.py`, `flag_detector.py`
   stages WATCH/TIGHTENING/COILED/TRIGGERED) are STATES of a different family; this setup has its own gates (`cb.explain_watch`)
   and reuses only the cited constants above (his 08-02 "some parameters differ").
2. **Minute feed.** The backtest's minutes are Alpaca SIP; production reads `ALPACA_DATA_FEED`, which the repo records as **`sip`
   in prod** (`CHANGELOG.md` "set in prod"; `docs/analysis/realtime_full_cutover_design_2026-07-20.md` "prod ALPACA_DATA_FEED=sip
   CONFIRMED, both containers"; `docs/setups/magna53_ep.md`) — `iex` is only the default when the variable is unset. So the two
   feeds should MATCH, and a high `minute_daily_mismatch` / `minute_high_below_pivot` share is a FAILURE signal on a `sip` row
   (a broken minute path), not a thin-feed artifact. The row's `feed` column is the ground truth (it is written from the job's own
   environment): read it on the verify night, and if it says `iex`, the thin-bar caveat applies and the share runs higher.
3. **SIC** is current, not point-in-time, and fills over about a week (above).
4. **Catch-up covers the ENTRIES, not the watch list.** The spec said "last night's watch rows"; the job looks back 3 sessions
   so a break day that was missed, or whose minute fetch RAISED, has its entries written the next night. It does NOT rebuild a
   missed night's WATCH LIST (`build_watch` builds only tonight): if night N crashes in the watch step, times out, or skips with
   `no_spy_bar_for_today`, there are no D = N rows, and the breakouts of session N+1 are lost for good (N's own entries are
   recovered on night N+1). #672's missed-job recovery covers a scheduler-missed slot only. The audit row names it:
   `entry_days_without_watch` lists the look-back sessions with no watch rows (a missed night, or a genuinely empty one). A
   rebuild was left out on purpose — a rebuilt D row would carry an ADJUSTED pivot from today's stored bars where a live night
   stores a raw one, `fill_sic` keys on the wall clock, and a legitimately empty night would re-scan every evening; whether the
   gap is worth that is the main loop's call.
5. **Runner-only analyses are not recorded:** the two controls (Family A `SETTLE_RULE`, `walk_arm` "Apollo as it runs today"),
   the cap-not-skip and ATR14-width sensitivities, the 60-session re-walk, the stop-floor sweep (derivable from `width_pct` and
   `adr20`). The 15 `cb.ARMS` are the shadow's arms.
6. **Stored features omit** `i` and every `*_idx` (positions inside one night's 150-bar slice; the matching dates are kept).
   Features agree with a whole-history evaluation (tested).
7. **One trade per base, night by night.** The chain key is stamped with the poles known at the candidate's night; a pole that
   appears LATER between two earlier ones can merge two bases after the fact, which the batch backtest sees and the forward
   record cannot (the spec key is unaffected). Tested and named.
8. **Slot.** 17:48 ET, not the spec's 17:50 (taken by `exit_path_shadow` and `chart_axis_shadow`) nor the plan's 17:45.
9. **Two named edges in the entry stamping.** (a) If the minute fetch RAISES on two CONSECUTIVE nights, E = N is deferred
   twice (it is not the oldest look-back day until night N+2), E = N+1 is stamped against a history that lacks it, and E = N is
   then — if it raises again on N+2 — NEVER written (#702: the oldest day writes no row on a raise; it used to be written as
   `no_minutes`), counted in `minutes_deferred_oldest`; if it answers on N+2 it is written with `retrigger = 0` beside E = N+1's
   row — two `retrigger = 0` rows in one base. A single-night outage is fine (oldest first). (b) *(corrected
   2026-10-17, review fix)* the split guard used to run AFTER the breakout test, comparing E's split-adjusted bar with D's raw pivot:
   a forward split hid a real breakout (no candidate, no row) and a reverse one invented a candidate for every K whether or not the
   price broke out, which then entered the stamping history. Now the pivot is carried into the stored units BEFORE the test
   (`split_scales`), so both directions are judged like-for-like: a real breakout writes the 20 `split_after_watch` rows and a
   non-breakout writes nothing. Remaining edge: a split executed but not yet applied, or an unexplained scale, sits the name out
   for the night (counted, retried by the look-back); if the split is still unapplied when E is the oldest look-back day, that
   day's candidate is not recorded.
10. **Steady-state cost.** ~130 breakout candidates a night × ~2.5 filled variants, each open until every arm is mature (the
    `stop_only` control runs to the horizon), is tens of thousands of open entries by month 6. Only non-final arms are recomputed
    and bars load in chunks, but `wall_s` in the audit row is the number to watch against the 900 s budget.
11. **The accrual review hard-codes the 5-minute opening-range entry (`orh5`).** If the P4 freeze picks a different primary
    entry, `consolidation_breakout_forward_read`'s predicate must be re-pointed (its question says so).
12. **Open parameter question — `RECENT_WINDOW = 5` is B-class but feeds a C0 gate** (`deal_pin_median`, the median range of
   the last 5 sessions). It is deliberately NOT in the provenance registry (no source exists to cite); it stays a parameter until
   the P4 read cites or replaces it. Same for `PRIOR_MOVE_STRICT`, `GROUP_PCT_MIN`, `RS_BEST_STRICT/LOOSE`, `PHASE_SLOPE_PRIMARY`.

## Paper path (MAPPED only, nothing built — every item is money-path work)

Paper is decided on this setup's own forward + holdout evidence; live is the operator's sign-off. What it would take:
a **per-strategy trail mode and the day 3–5 partial** (the partial is globally off today) · the **ORB submission window and the
10:00 ET unfilled-cancel** (`orh60` cannot fit inside 09:31–09:45, so the 60-minute variant is shadow-only) · a **risk
multiplier** to ≤ 1% of the account at the article's sizing (position = min(20%, 1% ÷ stop width)) · **shared paper slots**
(`max_positions`) with the EP lanes. None of it is touched by this build.

## Known limitations / open questions

- The primary K, the primary entry and the cell ladder are chosen in the backtest's discovery read and then frozen; this file's
  definitions change only through that path (CHANGE_PROCESS).
- **C1 is rare.** The backtest's HOLDOUT (2025-01-01 → 2026-10-16, ~21 months) holds 33 C1 trades under the spec key (k5) — about
  1.5 a month — so the review's bar of 30 MATURE primary-arm C1 entries is a ~1.5-year wait at that rate. The looser cells
  (holdout trades under the same key: C3 100, C4 285, C5 86, C7 63) accrue 2–9 times faster and are read beside C1; whether the
  bar or the cell is the right thing to wait on is the operator's call, not this file's.
- The minute feed (the row's `feed` column) and thin-SIC effects above bias the first weeks; the read states them.

## Change log

### 2026-10-18 — #702 minute fetch: a raised error defers the batch, an empty answer is a real `no_minutes` (the outage GUESS is replaced by the collector's own error)

**Trigger**: his "Aligned, let's do these tmr" 10-17 on the #702 line's build note. `collector.get_alpaca_minute_bars_window` returned `{}`
on ANY failure, so `fetch_minutes` guessed an outage from empty batches (a whole fetch with not one bar, or 3 empty batches in a
row) and, on the oldest look-back day, wrote the guess as a `no_minutes` abstain — a false row for a day that has minutes.

**What**: (1) `get_alpaca_minute_bars_window(..., *, raise_on_error=False)` — additive; `True` re-raises the ImportError / missing
credentials (RuntimeError) / timeout / API error after the same warning (the `get_asset` precedent), so a RETURNED dict, `{}`
included, means Alpaca answered. `ma_filter.read_open_window_pin` keeps the default and its never-raises contract (tested). (2)
`fetch_minutes` asks with `True`: a batch that raises is asked once more, then its tickers are deferred; `MINUTE_ERROR_STREAK_STOP`
(3) raised batches in a row stop the fetch, defer the unasked tickers and set `minutes_feed_down`; batches that answered earlier are
kept. (3) `record_entries_for` writes NO row for a deferred ticker on any look-back day, the oldest included — the oldest day's loss
is counted (`minutes_deferred_oldest`) and named in the audit event. (4) Removed: the empty-batch retry, the empty-batch streak stop
(`MINUTE_EMPTY_STREAK_STOP`), and the "no ticker returned a bar" outage test — each replaced by the real error path, not dropped.
**Behaviour changes, named**: a successful call with no bars for EVERY ticker used to be read as an outage (deferred) and is now
written as retryable `no_minutes` rows; a failure on the oldest day used to be written as `no_minutes` and is now a counted loss. Both
are the intended reading of an answer versus a failure.
**Not touched**: `consolidation_breakout.py`, the runner, any entry/stop/exit rule — the backtest is unaffected. No money path.
**Reversion-flag**: NEW; not a detection-criterion change. **Status**: built on a worktree branch, not deployed. EXPECT / DONE-WHEN /
WOULD-FAIL-IF: CHANGELOG 2026-10-18 (#702 minute fetch).

### 2026-10-18 — #704: the shadow reads the splits ingest's recorded verdict instead of re-deriving it (a phantom split is now no split here)

**Trigger**: the 10-17 /simplify altitude review found three consumers answering "did this split move the stored bars?" three
ways (this shadow's `split_scale` 2%, the parabolic-short shadow's `RESTATE_TOLERANCE` 0.5%, and `get_split_dates_after` for HTF
and this shadow's exit guard — any row, phantoms included); his "Aligned, let's do these tmr" 10-17.

**What**: `mi_splits` now carries `adjustment_outcome` (`applied` / `phantom` / `skipped_no_data`) and `applied_factor`, written by
`splits_ingest._apply_one` at the branch that decides (the bars it applies are unchanged — differential-checked against the
pre-change module on six fixtures). `db.stored_price_scale(ticker, since, through)` / `db.scale_from_split_rows` is the one reading.
(1) `split_scale` takes that reading, with its D-close comparison kept as the cross-check; (2) the exit guard and the
`split_after_watch` abstain count only splits that moved a stored bar. Back-fill: an outcome-NULL row that is applied reads as a
real split at the table's ratio (what the bare boolean always meant here).
**Behaviour changes, named**: a recorded PHANTOM no longer abstains the 20 entry rows with `split_after_watch` and no longer
voids the exit walk (`unbookable`) — it is ignored, as the parabolic shadow always did; a later split still UNAPPLIED defers the
exit walk (no row, `exit_split_deferred`) where it used to void it for good; a LEGACY phantom (no outcome) now sits the entry out
(`entry_split_unresolved`) instead of abstaining 20 rows.
**Review fix, same day**: only a PHANTOM reads 1.0. `skipped_no_data` is also what a FAILED Polygon fetch of a real split records
(`fetch_ticker_history` swallows every error to an empty answer), and then the pre-split bars stay raw while later bars are
post-split — so it is read at the table's ratio like a legacy row: the exit guard voids the walk as it did before #704, and the
entry step sits the name out on its D-close cross-check (it writes no `split_after_watch` rows and counts the name in
`entry_split_unresolved`) instead of treating it as unsplit and letting a reverse split invent a breakout.
**Not touched**: `consolidation_breakout.py`, the runner, the watch step's own `split_unapplied` gate, any threshold or entry/exit rule —
the backtest is unaffected. No money path (shadow tables only).
**Reversion-flag**: NEW; not a detection-criterion change (no admission, pivot, stop or exit rule moved). Reverting = make
`moved_splits` return its input and `split_scale` ignore the outcome columns (the columns stay).
**Status**: built on a worktree branch, not deployed. EXPECT / DONE-WHEN / WOULD-FAIL-IF: CHANGELOG 2026-10-18 (#704).

### 2026-10-17 (evening) — /simplify pass: one copy of the shared plumbing, no behaviour change

**What**: reuse / efficiency cleanups only. The backtest's seven pinned outputs (`candidates.tsv`, `discovery_report.tsv`,
`entries_holdout_composition.tsv` and the decompressed `watch` / `trades_discovery` / `entries_discovery` /
`close_variant_discovery`) hash identically before and after; the shadow's rows are unchanged.
- The plumbing the runner and the shadow both need (test symbols, the contiguity test, the breakout test, gap fields, the maturity
  label, the forward-window cut, the cross-section, the one-trade-per-base stamping, and `walk_arms`) lives ONCE in
  `consolidation_breakout.py` section 7 and is imported by both; the copy-equality parity tests are gone because there is no second
  copy to keep equal (the night-by-night vs batch stamping tests stay).
- `adr20_pct_from_bars` is the real `broker.exit_logic` function, imported under `# exec-boundary-ok:` (pure ladder math, the same reuse
  `pivot_analysis` / `giveback_shadow` make); it replaces the mirror and its equality test. That is the ONE broker module the pure core
  loads, so the census test now allows exactly `broker` + `broker.exit_logic`. The shadow itself still imports nothing from `broker/`.
- The pole-artifact literals (1.50 / 2.0) are named in `flag_detector` and imported here; their two provenance-registry entries moved
  to `flag_detector.py`.
- Shadow: `MINUTE_BATCH` 5 -> 25 (the outage threshold is now 75 tickers of empty batches, at the same 3 x 2 calls); the open-entries
  query is bounded by the stale date with one LEFT JOIN and the stale ones are counted by a second cheap query (`exit_entries_stale`
  unchanged); one candidate's K x variant entries that share (fill, stop, day-0, ADR) are walked once per arm; the recorded `feed` is
  `execution_client.get_data_feed_name()` (an unrecognised env value now records `iex`, which is what the fetch used); the unapplied-split
  tickers come from `get_unapplied_splits(since, upto=)`.
**Reversion-flag**: NEW. **Status**: built (✅ Confirmed in production 2026-10-18 00:25 ET, 61974034; at build time: market-agent; `db.py` is on the execution image's module list, as in the
entry below).

### 2026-10-17 — NEW: the forward SHADOW recorder (job `consolidation_breakout_shadow`, 17:48 ET mon–fri; tables + review; no order path)

**Trigger**: his 2026-10-17 ask to run Qullamaggie's breakout *"as a parallel shadow/paper from other consolidation"*, and his
ruling the same day that other setups may go to shadow and paper on their own evidence. The loose consolidation lanes show no
edge (Family A Confirm 157 settled trades at +0.10R, none reached 3R; Anticipate parked at −0.24R).

**Evidence**: the rules are the article's own words (`operator_shared_notes.md` 2026-10-17) plus his additions, each marked S / R /
B above; the pure module is pinned by its own suite (MRNA canary: watch night 2026-09-16, pivot_k5 149.7344, breakout day
2026-09-17) and the recorder by `tests/test_cb_shadow.py` (parity with the runner's plumbing, the job end to end against an oracle
built from the module) and `tests/test_cb_shadow_pg.py` (the SQL for real). Backtest verdict: NOT yet read (P4/P5) — the shadow
ships regardless of it, because it needs forward time to accrue and costs no money.

**Anticipated effect**: no production behaviour changes (no order, sizing, safeguard, grade or admission is touched; THE LINE).
Four new tables fill nightly; one audit row a night; ~300 Polygon reference calls a night for a week, then ~0.

**Reversion-flag**: NEW (no prior change to any of this).

A liveness watch (`health_checks._DETECTOR_LIVENESS_TABLES`, key `scan_date`) covers the one failure `audit_wrap` cannot see: a
`success` run whose writer wrote nothing.

**Review-fix round (same day, before any deploy)**: six findings fixed in the recorder, none touching `consolidation_breakout.py` or
the runner. (1) The split guard now runs BEFORE the breakout test (deviation 9b). (2) The watch step runs first and 3 empty minute
batches in a row end the fetch (the forward-shadow section; superseded 2026-10-18: 3 RAISED batches, see the change log). (3) The accrual predicate counts only primary-arm exits that carry an R
(a split-voided `unbookable` arm is final but has none). (4) The minute-feed wording follows the repo's record (`sip` in prod,
deviation 2). (5) The catch-up wording says it recovers entries, not a missed watch list (deviation 4). (6) `MIN_PRICE` is cited as a
reuse, not as #286-signed. Open for the P4 freeze: `consolidation_breakout.py` lines 15-17 still say "NOTHING here is in the
registry yet" although ten constants are registered (the module is hash-pinned, so the docstring is changed with the freeze).

**Status**: DEPLOYED 2026-10-17 20:13 ET (ea78bae7, both + execution) and re-deployed with the /simplify pass 2026-10-18 00:25 ET
(61974034); the four tables exist in prod, the SIC cache was seeded (3,303 with a code, 639 none). First run: Mon 10-19 17:48 ET.
Verify-live per the block above.
