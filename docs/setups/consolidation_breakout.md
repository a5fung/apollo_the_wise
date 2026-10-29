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
tables `mi_consolidation_breakout_{watch,entry,exit,sic}`) · the recorder's `pp` / `A` exit walk
`agents/market_intelligence/consolidation_breakout_pp.py` (pure, no I/O; #705 (c)).

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
  night until each arm is mature. **Since #705 (c) every fill recorded after the change is ALSO walked on two more arms,
  `pp` (his carried exit) and `A` (the control it replaced), by a separate step beside the fifteen** (17 rows per fill).

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
| Pivot `com` (P4b, runner-only) | the CENTER-OF-MASS level = **the median of the base's daily highs over (P, D]** (bars ≤ D; `pivot_com_date` = the base bar nearest it); a breakout is `high(E) > pivot_com(D)`, same keys and cells as the four above. NOT in `PIVOT_KEYS` / `KS`: the shadow never computes it and no pinned backtest output carries it; the runner computes it on `--keys com` into `*_com` files | **S** his 2026-10-18 rule *"he finds where the center of mass is in the consolidation and ignore the outliers if it's just a short period, meaning a 1-3 bars spike then drop back to the basing area"*; WHICH reading of that sentence (`COM_VARIANT` = `quantile`, `COM_QUANTILE` = 0.5) is **B**, chosen on the plateau of the P4b label read (43 of his 58 drawn lines within 0.5 ADR vs 23 for the best existing level; `docs/analysis/cb_preregistration_2026-10-18.md` §P4b); the spike filter (`COM_MAX_RUN` = 3 **S** his "1-3 bars"; `COM_SPIKE_ADR` = 0.5, `COM_FALLING_SLOPE` = 0.2%/session **B**, the runner-up reading's values) serves the five other readings and is telemetry under the chosen one | `EXTRA_PIVOT_KEYS`, `com_level`, `spike_mask` |
| Pivot `comb` (P4b step 6b, runner-only) | `com` read only on the nights the stock CLOSED AT OR BELOW the level: `pivot_comb` = `pivot_com` (same level, same date fields) and **C0 additionally requires `close(D) <= pivot_comb(D)`** (equality counts; every cell inherits it). A night that closed above the line gets NO `comb` candidate (else its first break would consume the base's one trade under the spec key). Not in `PIVOT_KEYS` / `KS`; the runner computes it on `--keys comb` (or `--keys com,comb`, one pass, outputs suffixed `_com_comb`) | a reading of `com`, not a new level: no threshold of its own (Gate 5 registers nothing). WHY: `com` sits under the watch night's close on 38% / 41% of nights, where a "breakout" is any up day; the main loop (2026-10-18) made `comb` the PRIMARY `com` reading and `com` the one reported beside it | `EXTRA_PIVOT_KEYS`, `CLOSED_BELOW_KEYS`, `comb_fields`, `cell_flags` |
| His exit (runner-only arms) | `HIS_EXIT_ARMS`, 25 arms `<trigger>_p33_<trail>`, walked by the runner's `exits` stage BESIDE the 15 registered arms, never by the shadow: partial trigger `r2` = sell 1/3 at fill + 2 × (fill − stop) (a session whose high reaches it sells AT it, one that OPENS above it sells at the open; on the breakout day the minutes after the fill are walked, `day0_walk_target`), `d3` / `d5` = the close of session 3 / 5 (the registered timing), `c3` / `c5` = whichever comes first; then the stop moves to breakeven (resting from the next bar) and the trail arms (first close under the average, filled at the next open): `t10` / `t20` fixed, `tspd` = the 10-day when ADR20(D) > 0.0479 (his "faster stocks"; the top tercile of the discovery C0 ADR distribution) else the 20-day, `td1` / `td2` = at the partial, the 10-day when the close stands more than 1 / 2 ADR20 above its own 10-day, else the 20-day. A daily bar touching both the stop and the target books the STOP (pessimistic) unless it OPENED above the target. `d3_p33_t10` IS `p33_s3_t10` (tested equal) | **S** his 2026-10-18 correction *"sell 1/3 at 2R then move to break even stop then trail rest at break of 10 or 20d ... 10d for faster stocks and 20d for slower stocks, also depend how far the are from 10/20"* and *"The day thing is also correct, it may be a combo and depends"*; the +2R (`PARTIAL_TARGET_R`) is S; WHICH reading of "faster" (`TRAIL_SPEED_ADR_CUT`) and of "how far" (`TRAIL_DISTANCE_X`) is **B** — two readings of one sentence, both reported, neither chosen; exit parameters are not cohort-shaping and are not in the provenance registry (as `FIXED_TARGET_R`) | `HIS_EXIT_ARMS`, `walk_exit`, `day0_walk_target`, `walk_his_arms`, `PARTIAL_TARGET_R`, `TRAIL_SPEED_ADR_CUT`, `TRAIL_DISTANCE_X` |
| Stop variants (runner-only) | five readings of the stop, every arm walked under each, REPORTED alternatives: `lod` = the registered low of the day at the fill; `lod_cap05` = max(lod, fill − ½ ADR); `lod_floor05` = min(lod, fill − ½ ADR) (the brief's "floored at 0.5 ADR below the fill" read as a price floor and as a width floor — both run, neither chosen); `level_m05` = the breakout level (the pivot K(D)) − ½ ADR; `base_low` = the base's low. ½ ADR = 0.5 × ADR20 × the fill; each skipped as `too_wide` beyond one ADR20 (the registered rule); R = fill − that stop, so R is not comparable across variants (the read ranks on P&L in ADR units, and a variant that abstains on most trades is compared on its own trades) | the stop is **his** (the article's: *"Stop is always lows of the day"*); the variants are the 2026-10-18 brief's and `STOP_HALF_ADR` is **B** | `stop_variants`, `STOP_VARIANTS`, `STOP_HALF_ADR` |
| P5 primary exit — the stall cut (runner-only; the HOLDOUT read's deciding exit) | `CUT_EXIT_ARMS` = one arm, `c3_p33_t20_cut3` (`P5_PRIMARY_ARM`): the `c3_p33_t20` arm (sell 1/3 at +2R or at the close of session 3, whichever first; breakeven; trail the 20-day, filled at the next open) **plus** the stall cut — if no high has reached fill + `STALL_CUT_R` (1) × (fill − stop) by the close of session `STALL_CUT_SESSION` (3; E = session 0) and the trade was not stopped, everything is sold at that close (event `cut`, status `time_exit`, terminal so mature, no day-3 partial). "Reached" = the highest minute high after the fill minute on the breakout day (`day0_peak_high`, passed to `walk_exit(day0_peak=)`; a day-0 +R partial implies it) or any session's high on sessions 1..3 including session 3's own; the stop is checked first. A trade that reached it walks the `c3_p33_t20` path unchanged (tested). Walked by the runner's `p5` stage (discovery) and by `holdout`'s second pass, on the `lod` stop, with `p33_s3_t10` / `c3_p33_t20` / `r2_p33_t20` beside it, on `tl` / `com` / `comb`. NOT in `cb.ARMS` (the shadow) and NOT `cb.PRIMARY_ARM` (the pinned discovery report's headline arm, unchanged): only the holdout read's primary moves | **S** his stalled-breakout lines (2026-10-18) *"if breakouts have no follow through in next few days then it may be better to get out as momentum didn't continue regardless if it isn't stopped"* / *"Cut stallers is important because funds are limited, turnover for swing trades is important, holding breakeven for a long time has opportunity cost"*; the **numbers** `+1R` and `session 3`, the 20-day trail and the day-3 combo are the operator's 2026-10-18 ruling as relayed in the P5 brief (his verbatim lines say "next few days"), not fitted; exit parameters are not cohort-shaping and are not in the provenance registry (as `FIXED_TARGET_R`) | `CUT_EXIT_ARMS`, `P5_PRIMARY_ARM`, `STALL_CUT_SESSION`, `STALL_CUT_R`, `Arm.stall_cut_*`, `walk_exit`, `day0_peak_high`, `walk_his_arms` |
| `pp` and `A` in the shadow (#705 (c); recorded, NOT in `cb.ARMS`; `A` IS the P5 primary `c3_p33_t20_cut3`, recorded through `consolidation_breakout_pp`) | `pp` = `c3_p33_t20_cut3` with the session-3 third sold ONLY WHEN THAT CLOSE IS ABOVE THE FILL: sell 1/3 at +2R (a high reaching it sells AT it, an open above it at the open; on the breakout day the minutes after the fill are walked) or at the close of session 3 when that close is above the fill; after ANY third the stop rests at the fill (cost) from the next session; the rest trails the first close under the 20-day, filled at the next open, **live from session 3 whether or not the third sold** (a session-3 close under the 20-day sells everything at the next open); the stall cut stays (no high at fill + 1R by the close of session 3, not stopped → everything sold at that close). `A` = the same walk with the session-3 third sold whatever the close; it IS `cb.CUT_EXIT_ARMS["c3_p33_t20_cut3"]` (proved equal event for event, the added `stop_to` events aside). Stored as exit rows with `arm` = `pp` and `A`; events carry `stop_to` (the level the stop rests at from the next session) and `be_above_close` beside the module's. A `close`-variant fill has no minute after it: day 0 is "nothing happened". Pre-change fills (no stored facts) are not walked | **S** his ruling 2026-10-19 (*"Yes"*: the day-based third sells only in profit; change log below); the +2R, the third, the 20-day trail and the +1R-by-session-3 cut are the registered `c3_p33_t20_cut3` | `consolidation_breakout_pp.py`: `walk_pp`, `walk_pp_arms`, `day0_facts`, `no_day0_facts`; the registered definition it ports and is tested equal to: `runner.exitpb_walk` / `exitpb_walk_arms` |
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
- **His exit (runner-only; 2026-10-18):** the 25 `HIS_EXIT_ARMS` × the five `STOP_VARIANTS` (definition rows above), walked by
  `runner.py exits` on the DISCOVERY first breaks at ORH5 into `trades_discovery_exits_<levels>.tsv.gz` and read by `exits-report`
  into `exits_report_<levels>.{tsv,txt}` — new files beside the pinned ones; the shadow walks `cb.ARMS` plus, since #705 (c), `pp` and `A` (definition row above). The read:
  `docs/analysis/cb_his_exit_2026-10-18.md`.
- **P5 primary (runner-only; operator 2026-10-18):** the HOLDOUT read's deciding exit is `c3_p33_t20_cut3` (definition row above) on
  the registered `tl` level, ORH5, the low-of-day stop and the spec key; `p33_s3_t10` (the article's arm), `c3_p33_t20`,
  `r2_p33_t20` and the `com` / `comb` levels are reported beside, never deciding
  (`docs/analysis/cb_preregistration_2026-10-18.md` §P5). Nothing the shadow records or the registered discovery report prints changed.

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
3. **Exits.** Every filled entry with a non-mature arm has each of its NON-FINAL arms (of the 15; the `pp` / `A` rows are never counted here — the work-list SQL joins `x.arm NOT IN ('A', 'pp')`, else two early-maturing pp arms plus thirteen registered ones would close an entry whose `stop_only` control is still open) recomputed in full from stored
   bars; a mature arm is final and is neither recomputed nor overwritten. A split executing after E that MOVED a stored bar
   makes every still-open arm `unbookable` (stored fills are raw, stored bars retro-adjusted — the #667 HTF precedent); one the
   ingest recorded as a phantom is ignored, and one not yet applied defers the entry's walk to the next night
   (`exit_split_deferred`, no row written); an arm that settled before the split keeps its valid pre-split outcome. A forward window cut at a data hole ends `degraded`, and an entry still open past the
   horizon + 10 sessions is no longer re-walked. Bars are loaded 200 tickers at a time.
3b. **Exits, `pp` and `A` (#705 (c)).** A separate step after the fifteen (`walk_pp_exits`), its own work list (filled entries that
   CARRY `day0_pp` with a non-final `pp` / `A` row), its own counters (`pp_*`), written to the same exit table. The walk needs the
   breakout day on the MINUTES (a +2R touch before the stop, the day's highest minute high for the stall cut), and the exit step
   fetches no minute: the ENTRY step computes the facts ONCE, from the minutes it already holds for the fill, and stores them on
   the entry row (`day0_pp` JSONB, `consolidation_breakout_pp.day0_facts`; the `close` variant stores "nothing on day 0"). A
   fill recorded before the column existed has NULL there and is not walked (named in `pp_day0_missing` only for fills that
   failed to compute; a pre-change fill is simply outside the step). Split handling is the registered arms' (a moved bar →
   `unbookable`, a phantom ignored, an unapplied split defers — `pp_split_deferred`).
4. **Audit row** with watch count, universe size, the gate funnel, cells per K, new entries by status and reason, exits settled,
   SIC fetched/known, wall time, the pp / A counters (`pp_day0_recorded`, `pp_day0_missing`, `pp_entries_open`, `pp_entries_stale`,
   `pp_exit_rows`, `pp_exit_mature`, `pp_exit_status`, `pp_exit_errors`, `pp_split_deferred`), and the entry-step diagnostics: `entry_days_without_watch` (look-back sessions with no watch
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

### Verify-live for #705 (c) — `pp` and `A` recorded (declared before the deploy)

- **EXPECT** (baseline, 2026-10-25: zero exit rows with `arm IN ('A','pp')`; the entry table has no `day0_pp` column): (1) the first
  market night after the deploy that records a FILLED entry: that fill carries `day0_pp` (a JSON object, `v` = 1) and the same
  run writes exactly 2 more exit rows for it, `A` and `pp`, beside its 15; the audit row shows `pp_day0_recorded` = the fills
  recorded that night and `pp_exit_rows` ≥ 2 per fill. (2) A fill whose day 0 stopped it out has both rows `stopped_day0`,
  mature, session 0 (a day-0 +2R touch before the stop shows a `partial_r` event at session 0 and a `stop_to` at the fill).
  (3) A fill that ran: `pp` and `A` rows are non-mature (`degraded`) night after night, `n_fwd` growing, until a trail / stop /
  cut. (4) The fifteen are unchanged: a filled entry still has 15 registered rows, `exit_rows` counts only those, and no
  registered row's values moved. (5) Fills before the deploy have NO `pp` / `A` rows and are never written one. (6) No minute
  fetch on any night is for a session older than the 3-session look-back (the exit step fetches none). (7) Wall time
  `wall_s` stays far under the 900 s budget (the pp step's work list is small: its arms mature in weeks, `stop_only` does not).
- **DONE-WHEN:** (a) the same night the first post-change fill is recorded, that fill has a `pp` and an `A` row (his DoD); AND
  (b) the daily walk has run in prod, not only the day-0 booking: at least one `pp` row with `status` ≠ `stopped_day0` and
  `n_fwd` ≥ 1 exists (a fill that survived day 0 and was walked on stored bars); AND (c) at least one post-change entry has BOTH
  arms mature by a DAILY-WALK exit (status stopped / trailed / time_exit, `sessions_held` ≥ 1 — a day-0 stop-out does not count),
  with the invariants below holding on every mature `pp` row; AND (d) the cross-check below agrees on the first 3 or more minute fills. Then comparing `pp` with `A` (and the fifteen) on the
  forward record is a read for the forward-read review, not a build item.
- **VERIFY-LIVE:** on the first market night after the deploy (the 17:48 ET job; verify date = that night, a Monday if it ships this
  weekend), read-only, by SQL (not the counter ratio: a retried candidate group re-counts already-filled rows): every `status = 'filled' AND
  break_date >= <deploy date>` entry has `day0_pp IS NOT NULL` and exactly 2 exit rows with `arm IN ('A','pp')` beside 15 others; the
  audit row has `pp_day0_missing` = 0 and `pp_exit_errors` ≤ `exit_errors` on the same entries; `SELECT count(*) FROM mi_consolidation_breakout_entry WHERE status = 'filled' AND
  break_date >= <deploy date> AND day0_pp IS NULL` = 0; `SELECT count(*) FROM mi_consolidation_breakout_exit WHERE arm IN ('A','pp')`
  > 0 (baseline 0). If no watch name breaks that night there is nothing to see: the check waits for the first night that
  records a fill (DONE-WHEN a), it does not pass on an empty night. **Cross-check (free, read-only):** for the first 3 or more
  post-deploy MINUTE fills, re-fetch that break day's Alpaca minutes and run `runner.exitpb_walk_arms` (the registered definition) on the
  stored fill, stop and fill minute plus the prod daily bars. Note: `pp` / `A` day-0 stop-outs use the +2R / breakeven minute walk and
  need not match the entry's registered `day0_stopped` — a +2R touch that falls back to the fill stops `pp` / `A` while the fifteen walk on.
- **WOULD-FAIL-IF** (each is a positive observation): a post-change filled entry with 15 rows and no `pp` / `A` row after the
  run that wrote it · a `pp` row carrying a session-3 `partial` event whose price is at or below the entry `fill` · a `partial` /
  `partial_r` event with no `stop_to` at the fill in the same session, unless that same bar's stop took the remainder (a gap-open
  +2R third followed by the stop in one bar ends the walk with no `stop_to`) · a `pp` row that differs from the `A` row of the same entry
  although `A`'s third sold above the fill (they must agree there) · `pp_day0_missing` > 0 on a night with fills (the facts failed
  to compute) · `pp_exit_errors` > 0 on an entry whose fifteen registered arms walked clean that night · any recorded `day0_pp` field
  or `pp` / `A` event that differs from the cross-check's re-walk · a registered arm's row count per entry ≠ 15 · `unbookable` on a `pp` row with no split
  recorded for the name.

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
   `adr20`), the `HIS_EXIT_ARMS` grid and the other `exitpb` arms (`pp_wbe`, `wbe`, `pp_s0`, `pp5_wbe` — his proposal LOST).
   The shadow's arms are the 15 `cb.ARMS` plus `pp` and `A` (#705 (c)).
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
13. **`pp` / `A` coverage (#705 (c)).** (a) Only fills recorded AFTER the change carry the day-0 facts; fills before it (the
    shadow's first sessions) have no `pp` / `A` rows and none are back-filled (the minutes of an old break day would have to be
    re-fetched; not built, not needed for the forward read, which counts mature entries from the change on). (b) The `close`
    variant has no minute after its fill, so its `pp` / `A` day 0 is empty — the registered `exitpb` read only ever walked ORH5 /
    hourly-close fills, so there is no registered number for it; it is walked like the fifteen walk it. (c) The walk is a PORT
    (`consolidation_breakout_pp.py`), not a call into `cb`, because `consolidation_breakout.py` is hard-pinned by sha256 for the
    registered exit read (`runner.EXITPB_MODULE_SHA`); `tests/test_cb_pp_recorder.py` keeps it equal to the runner's registered
    walk event for event.

## Paper path (MAPPED only, nothing built — every item is money-path work)

Paper is decided on this setup's own forward + holdout evidence; live is the operator's sign-off. What it would take:
a **per-strategy trail mode and the day 3–5 partial** (the partial is globally off today) · the **ORB submission window and the
10:00 ET unfilled-cancel** (`orh60` cannot fit inside 09:31–09:45, so the 60-minute variant is shadow-only) · a **risk
multiplier** to ≤ 1% of the account at the article's sizing (position = min(20%, 1% ÷ stop width)) · **shared paper slots**
(`max_positions`) with the EP lanes. None of it is touched by this build.

## Known limitations / open questions
- **Spin-offs and special distributions are NOT adjusted in the daily export (found 2026-10-23, his catch).** The export
  (Alpaca, split-adjusted) adjusts splits only, so a spin-off reads as a one-session crash: OPLN (KAR Auction → IAA spin-off,
  2019-06-28, −62%), ZWS (Zurn, 2021-10), BEP (the BEPC distribution, 2020-07). Every replay on this export books those as stop-through
  losses — −34 R on OPLN — and they inflate the worst-trade and drawdown figures. A corporate-action screen (spin-off / special
  distribution dates) is needed before any worst-loss or drawdown figure is quoted as real. Until then such gaps are flagged by hand.


- The primary K, the primary entry and the cell ladder are chosen in the backtest's discovery read and then frozen; this file's
  definitions change only through that path (CHANGE_PROCESS).
- **C1 is rare.** The backtest's HOLDOUT (2025-01-01 → 2026-10-16, ~21 months) holds 33 C1 trades under the spec key (k5) — about
  1.5 a month — so the review's bar of 30 MATURE primary-arm C1 entries is a ~1.5-year wait at that rate. The looser cells
  (holdout trades under the same key: C3 100, C4 285, C5 86, C7 63) accrue 2–9 times faster and are read beside C1; whether the
  bar or the cell is the right thing to wait on is the operator's call, not this file's.
- The minute feed (the row's `feed` column) and thin-SIC effects above bias the first weeks; the read states them.

## Change log

### 2026-10-28 — breakout v1 FINAL for the Saturday 10-31 build (his "Ok" after the check against his 24 dated good setups)

| piece | v1 (build this) | why (`scripts/probes/_qm_0810_review/`) |
|---|---|---|
| universe | raw close ≥ $2, 20-session median dollar volume ≥ $5M (was $5 / $10M) | the $5 / $10M floor alone failed 7 of his 24 good setups |
| RS | best of the 21 / 63 / 126-session return percentiles ≥ 98, the night before | his article; his "biggest gainers in 1,3,6 month ... prior to breakout" |
| prior move, higher lows | as this file's rows | — |
| base anchor | **dropped** (a close above an earlier peak no longer breaks the base) | it failed 8 of 24 |
| level | the **highest high of the last 5 sessions** (the tight range), strict | his breakouts clear it 23 of 24; the whole base high 15 of 24 |
| surf / tightening / volume | 5+ sessions within 1.0 ADR of one of the 10/20/50-day; last 5 sessions' range ≤ 1.1× the 5 before; breakout volume ≥ 1.2× the 50-day | his confirmed starting values |
| entry, stop, exit, size, grade | `orh5` regular hours; the day's low ≤ 1 ADR; the `pp` arm; EP sizing; his grade a label | the entries above |

**Check on his 24 dated good setups (2020-08-10 review): 12 caught on his day or 1-2 sessions late (14 counting two earlier fires on the
same base); about 3.7 fires a night across the 2020 universe.** The misses: not a top-2% gainer then (CVNA, DFS, PLUG, PENN-3); below-
average breakout volume (NVAX, NAIL); too small (QUMU, TTOO — "tiny accounts only"); base did not surf or tighten (OPK-3, RUN). One
stream, picked in hindsight: starting values, refined on paper fills and his grades.

### 2026-10-28 — his PAPER GO for "breakout v1" (the starting rule set, refined as we trade); NOTHING built yet — the build is Sat 10-31

**Trigger**: his direction 2026-10-28 (`operator_shared_notes.md`): *"let's get to some near-term conclusion, some near-term rules
that we're confident it to work with and refine over time as we trade ... let's not boil the ocean here"*, then *"Yes paper"*, *"Size
paper similar to EP"*, and grading as *"running list and grade as best effort from me"*.

**v1 (the build's spec; each piece's source in brackets):** stocks = rs_best ≥ 98 + the scan his trades imply (ADR20 about 4%+, not
falling, near the 52-week high) on this file's universe [his words; #705 reverse-engineering SELECT PASS] · setup = this file's prior
move + base + higher lows + tightening, PLUS his repeated rule (10-28): the pullback comes WITHIN A REASONABLE RANGE of the 10-, 20- or 50-day and TURNS BACK UP
(his 10-28 clarification: *"touch MAs can be flexible ... discretion of pattern"*; the band is a distance in ADR, set from his graded examples; an undercut-and-reclaim counts) — and it is a STRETCH, not a touch: *"it's not touch and done, it'll surf for multiple days near the MAs, tighten, then breakout"* (his 10-28): several sessions in a row inside the band, the range tightening across them, then the breakout; the session count and band come from his graded examples — CONFIRMED starting values (his "Yes" 2026-10-28; `scripts/probes/_qm_0810_review/dating_calibration.md`): 5+ sessions in a row with the low within 1.0 ADR of one of the 10-, 20- or 50-day (88% of his 24 good setups; 43% of ordinary sessions), and tightening = the last 5 sessions' mean range ≤ 1.1× the 5 before (92%) — today's `MA surfing` row checks only "above the 20 and 50" [his words, Qullamaggie's 2020-08-10 review]
· level = the base high (`full`) — the trendline fired about 1.2 ADR early [#705 breakout-definition read] · breakout day on VOLUME:
≥ 1.2× the 50-day average [his words; set from his 24 good setups in the dated 2020-08-10 review (79% pass; 1.5× failed 11 of 24) and confirmed by his "Yes" 2026-10-28 — today breakout volume is telemetry only] · entry `orh5`, regular hours [his buys lean on his opening-range highs; beat the hourly-close
entry] · stop = the day's low, abstain beyond 1 ADR [the article] · exit = the recorded `pp` arm [his corrected rule + the stall cut] ·
size = EP's (2% account-risk base, EP's regime multiplier and caps) — **a departure from the article's 0.25-1%, by his ruling** ·
his A+ grade = a label on a running list, never a gate on a paper entry.

**Evidence, stated honestly**: the mechanical version LOST on the 2025-26 holdout (C1 −0.72R on 30, above); the only PASS on file is
his own picks traded with his rules (+264%, alpha t 2.31, `cb_holdings_replay_prereg_2026-10-24.md`). Paper is his call and carries
no money; the label comparison (his A+ vs the rest) is what v1's paper run is for. CHANGE_PROCESS: the two new gates (MA touch,
volume) are threshold additions — their starting values are set from his graded examples before the build and recorded here with
the counts; the paper read replaces a pre-paper backtest by his direction (no money at risk), stated as such.

**The paper-path items above still stand** and become the build: a per-strategy trail / partial mode, a breakout entry window that
is NOT the EP ORB window (a breakout can come any time of day — his 10-22 note), EP sizing (his ruling replaces the article's ≤ 1%
multiplier), paper slots shared with any EP paper lane, a nightly running list + a grade command (three places for a Telegram
command). **Reversion**: nothing to revert until the build; after it, the paper row's `enabled` flag.

### 2026-10-25 — #705 (c) the forward shadow also records `pp` (his carried exit) beside `A` — a recorder change, no order path, no registered number moved

**Trigger**: the 2026-10-19 registration carried `pp` (the day-3 third only in profit, the stop to cost after any third) as the
exit of every next registration, and the shadow still recorded only the 15 `cb.ARMS` ("until a recorder build"). Without `pp` rows
the forward read could never judge the exit he actually carries; the plan line (#705 (c)) asked for it beside `A`.

**Evidence**: not a threshold or gate change (no detection, entry, stop, size or live rule moves), so no backtest is owed; the
walk is the registered one. `tests/test_cb_pp_recorder.py`: the new walk equals the runner's registered `exitpb_walk_arms` event
for event on scenario tails and on a fuzz of 400 random daily + minute days (the facts round-tripped through JSON), and `A` equals
the module's own `cb.walk_his_arms` on `c3_p33_t20_cut3`. The fifteen registered arms and the entry rows' existing columns are
byte-identical to the pre-change code on the same fixtures (250 entry rows, 960 registered exit rows, MRNA + MRNB over 24 sessions;
digest frozen in the test, taken from git `d3e8ed20`); the new SQL ran on a real Postgres (`tests/test_cb_shadow_pg.py`, 20 passed).
A faithful-fake test caught the one real trap: the work list counted mature rows over ALL arms, so two early-maturing `pp`/`A` rows
plus thirteen registered ones would have closed an entry before its `stop_only` control finished — the SQL now joins
`x.arm NOT IN ('A', 'pp')` (tested on both stores).

**What changed**: (1) `consolidation_breakout_pp.py` (new, pure): `walk_pp` / `walk_pp_arms` (a port of the runner's registered
`pp`), `day0_facts`. `consolidation_breakout.py` is UNTOUCHED (it is hard-pinned by sha256 for the registered exit read, so editing
it would have closed that read; a `pp` is not expressible with the `cb.Arm` flags). (2) the entry step stores the breakout day's
facts on a FILLED row (`day0_pp` JSONB, new nullable column added by `ADD COLUMN IF NOT EXISTS` in the shadow DDL) from the minutes
it already holds; every other column of the entry row is as before. (3) `walk_pp_exits`, a new step after the exits: filled entries
that carry facts, `pp` and `A` rows into the same exit table (`arm` is free text; no new table), recomputed in full each night,
mature rows final, the registered arms' split reading. (4) the registered work-list SQL excludes the two names. (5) audit-row
counters `pp_*`.

**Anticipated effect**: from the first market night after the deploy that records a filled entry, 2 more exit rows per fill (17,
not 15) and one more JSON value on the entry row; the audit summary gains `pp/A N exit row(s)`. No Telegram, no order, no change to
any registered row or to the 17:48 job's schedule. Cost: one extra bar read per night for the (small) set of fills whose `pp` / `A`
arms are not final. Not covered: fills recorded before the deploy (no facts, no rows — deviation 13).

**Reversion-flag**: NEW (additive: no existing level, cell, entry, stop or exit moved). Reverting = drop the `walk_pp_exits` step
(the column and the rows can stay; nothing reads them but the forward read). **Status**: built and tested (the SQL on a real
Postgres); the live check is the verify-live block above.

### 2026-10-22 — #705 his A+ rating read (a fixed score, the best 3 a week): CAN'T TELL in both 2017–21 and 2022–24, so it is not recorded; RS leadership alone is named as the next test

**What**: the pre-registration `docs/analysis/cb_aplus_rating_prereg_2026-10-21.md` was frozen at `0d80a8d1` and read once
per era, with re-derivation VERDICT MATCH.
- **The score:** seven concepts from his notes, ranked against the prior 20 sessions' breakouts:
  - fractal contraction;
  - volume dry-up;
  - RS leadership;
  - prior move;
  - stair-step, earlier = better;
  - upward expansion at the fill;
  - volume so far against a normal day.
- **2017–21:** 534 A+ fills, mean +0.13R [−0.11, +0.39], 1.12 ≥ 10R per 100 against 1.235 for all breakouts.
- **2022–24:** 288 A+ fills, mean −0.17R [−0.41, +0.09], 0.35 ≥ 10R per 100 against 0.95.
- **Paired A+ − REST:** can't tell in both eras.
- **+grp** (the group-strength secondary): can't tell in both eras.

**Consequence (registered)**:
- The shadow records nothing new.
- The next registration is `alone_c3`, RS leadership alone. It had the highest two-era big-winner rate that also spread across
  ≥ 3 tickers and months in both eras: 1.76 / 1.74 per 100. It will be tested once on the sealed 2025–26 table.
- Disclosed: the stair-step concept alone could not be measured (a tie effect of the pinned percentile on a discrete value). It
  is negligible inside the core (at most 4 fills near a cutoff).
- No live or paper change.

**Reversion-flag**: none (a read; no rule changed). **Status**: complete.

### 2026-10-19 — #702 his exit, two parts: the day-based third ONLY IN PROFIT is adopted (his ruling); the whole-trade-breakeven stop after the third LOSES — the next tests carry `pp`

**What**: pre-registered `docs/analysis/cb_exit_partial_prereg_2026-10-19.md`, frozen, read once per period, re-derivation
MATCH. His ruling ("Yes": the day-3 third sells only in profit) replaces `A` = `c3_p33_t20_cut3` with `pp`. His proposal (after
the third, the stop where the whole trade nets zero = the original stop after a +2R third) tested against the entry-price
stop on the same 79 C1 trades of 2022–24: −0.12R per trade (−0.16 .. −0.08) — a loss, also −0.12R on 2017–21; neutral at
scale (C0 +0.00R on 8,983). TSLA 2020-06-01 under `pp`: +18.5R (was −0.17R). **Consequence (registered)**: `pp` is the exit
of the next registrations; runner-only, no live or paper change; the shadow keeps its 15 arms until a recorder build.
**Reversion-flag**: none. **Status**: complete.

### 2026-10-19 — #702 the hourly-close entry (`h60`) read: C1 FAIL on 2022–24 and it LOSES to ORH5 on the same bases — not recorded

**What**: buy only after a 60-minute bar closes above the line (fill at the next minute's open, low-of-day stop, first
confirmed break per base), pre-registered `docs/analysis/cb_hourly_entry_prereg_2026-10-19.md` and frozen before the read.
**C1 FAIL** on 2022–24 (−0.31R on 78, interval −0.55 .. −0.04, no ≥ 10R trade); paired vs ORH5 on the same 91 bases −0.55R
(a loss); the same-day stop-out share did not fall (35.7% vs ORH5's ~35%). 2017–21 CAN'T TELL (+0.59R on 180), 2025–26
descriptive FAIL. Independent re-derivation MATCH. **Consequence (registered)**: not recorded; next tests under ORH5 (a
breakout-day quality rule at the confirming bar; the stair-step number). **Reversion-flag**: none (a read, no rule changed).
**Status**: complete.

### 2026-10-19 — #702 the frozen primary read on 2017–21 (his 10x era): CAN'T TELL on C1 — no paper; the next tests are the entry and the stop

**What**: the frozen primary (trendline / ORH5 / low-of-day stop / his exit with the stalled breakouts cut), read once on
Alpaca 2017-03..2021-12 (pre-registered `docs/analysis/cb_2017_21_read_prereg_2026-10-19.md`). **C1 CAN'T TELL** in the
whole era (+0.28R on 180, interval −0.24 .. +0.99, −0.29 without the top five) and in 2020–21 alone (+0.45R on 72,
interval −0.56 .. +2.26); one real +54R trade (Overstock, filed under NXH) carries the mean — without it −0.02R / −0.31R.
C4 FAIL both windows; C0 break-even (+0.02R). **Consequence (registered)**: no paper; the entry (an hourly-close
confirmation) and the stop are tested next on 2022–24, confirmed only by the forward shadow. **Reversion-flag**: none (a
read, no rule changed). **Status**: complete.

### 2026-10-19 — #702 P5 HOLDOUT READ: FAIL on the primary — no paper; the forward shadow keeps recording

**What**: the one-time holdout read (2025-01..2026-10-15) on the frozen primary (trendline / ORH5 / low-of-day stop / his
exit with the stalled breakouts cut), run once 2026-10-19, independently re-derived (VERDICT: MATCH). **C1 FAIL** (−0.72R on
30, interval [−1.06, −0.35], none ≥5R); C3 / C5 / C7 FAIL; C4 CAN'T TELL (−0.11R on 226, interval spans zero); C2 / C6
CAN'T TELL by n; C0 −0.13R on 7,531. Discovery's C1 +0.32R is contradicted. Result paragraph + tables:
`docs/analysis/cb_preregistration_2026-10-18.md` §RESULT (below the freeze marker; the pinned body unchanged).
**Consequence (registered §0/§5)**: no paper lane. The forward shadow (`consolidation_breakout_shadow`, 17:48 ET) is
unchanged and keeps accruing; the setup as tested is the trendline breakout bought at the 5-minute opening-range high
with the day's-low stop, not the pattern. **Reversion-flag**: none (a read, no rule changed). **Status**: complete.

### 2026-10-18 — #702 P5 prep: the holdout read's primary becomes HIS exit with the stalled breakouts cut (`c3_p33_t20_cut3`) — runner-only, no pinned byte moved, the holdout is runnable and was NOT run

**Trigger**: the operator aligned (2026-10-18) that the holdout read's primary is the registered trendline level with HIS exit —
sell 1/3 at +2R or at the close of day 3, whichever first, breakeven, trail the rest to the first close under the 20-day average
(next-open fill), the low-of-day stop — AND cut the stallers (no +1R by the close of session 3 and not stopped → sell everything
at that close), his words *"Cut stallers is important because funds are limited, turnover for swing trades is important"*
(`operator_shared_notes.md`).

**What**: (1) module (additive): `STALL_CUT_SESSION` = 3 / `STALL_CUT_R` = 1.0; two `Arm` fields (`stall_cut_session`,
`stall_cut_r`) defaulting to no cut, validated; `CUT_EXIT_ARMS` (one arm, `c3_p33_t20_cut3`) and `P5_PRIMARY_ARM`; `walk_exit(...,
day0_peak=)` with the cut step between the +R target and the session partial; `day0_peak_high`; `walk_his_arms` passes the day-0
peak to a cut arm. `ARMS` (15), `HIS_EXIT_ARMS` (25) and `PRIMARY_ARM` are untouched. (2) runner: `evaluate_exits(stops=, arms=)`
(defaults = the `exits` stage), the `p5` stage (discovery: `trades_discovery_p5.tsv.gz`, `p5_report_discovery.{tsv,txt}` — the
primary and the three arms beside it, on `tl` / `com` / `comb`, every cell, spec + chain key, year / QQQ phase / Apollo-regime
slices, the cut's own effect against the uncut twin), a per-trade cross-check of the registered arm inside the P5 table against the
minute stage's table, and `holdout`'s SECOND pass (the same function on the holdout: `trades_holdout_p5.tsv.gz`,
`p5_report_holdout.{tsv,txt}`, P5 rows appended to `regime_report_holdout.{tsv,txt}`); the once-only guard and the dry run cover the
new table; new pins (`candidates_com_comb.tsv`, `watch_com_comb.tsv.gz`, `entries_holdout_composition_com_comb.tsv`,
`trades_discovery_p5.tsv.gz`, `p5_report_discovery.{tsv,txt}`). (3) tests: module — the arm, its validation, a staller cut at the
day-3 close, a +1R touch on day 2 / on session 3's own high / on the day-0 minutes is not cut, a day-0 stop-out unaffected, the
uncut path equals `c3_p33_t20` on 300 random paths, no registered or his-exit arm ever emits a cut; runner — the narrowed walk, the
stage end to end, byte-identical re-run, the cross-check, the holdout's second pass and guard, the new pins. (4) the pre-registration
§P5 (above its freeze marker) and the re-printed freeze record.

**Result (discovery, `tl`, ORH5, spec key — `p5_report_discovery.txt`)**: the new primary reads C0 −0.169R (n = 8,984, interval
[−0.28, −0.04], 2.6% ≥ 5R), **C1 +0.323R (79, [−0.21, +1.11], 3.8% ≥ 5R, −0.274 without the top five)**, C3 −0.028, C5 +0.509; the
article's arm on the same trades reads −0.189 / −0.051 / −0.222 / +0.251. The cut sells 250 of the 8,984 C0 trades (2.8%) at the
session-3 close and leaves the mean R unchanged (−0.169 vs −0.170 uncut) while freeing about 2.3 sessions per cut trade; in C1 it
fires on 2 of 79, so the C1 read is the `c3_p33_t20` read. The primary reads above the article's arm in each year of C1, but its
positive mean is 2023's (+0.877 on 34; 2022 −0.131 on 14; 2024 −0.080 on 31). **Nothing is decided**: the bars of the pre-registration are unchanged and the holdout has not been read.

**Anticipated effect**: none in production — the shadow walks `cb.ARMS` only; no table, job or Telegram changes. Byte-identical
proof: `daily | minute | step0-entries | report` on the default keys re-run into a scratch dir after the change, all seven content
hashes equal to the pinned set; the `exits` / `exits-report` outputs (`tl` and `com,comb`) re-run into a scratch dir are
byte-identical. **Freeze consequence**: the module and runner pins moved by bytes (stale since P4b; re-printed in this commit
with the holdout's `--print-pins`, diff in the commit message); `holdout` is runnable (`--dry-run` passes the freeze check) and was
NOT run.

**Reversion-flag**: NEW (additive; no existing level, cell, entry, stop or exit moved; the deciding exit of the holdout read moved
on the operator's ruling, before any holdout outcome existed). Reverting = drop `CUT_EXIT_ARMS` and the P5 stage/pass and restore
§3's exit in the registration. **Status**: built on a worktree branch; discovery numbers pinned; no holdout row opened.

### 2026-10-18 — #702 his exit: the +2R / day / combo partial, the 10- or 20-day trail switches and five stop variants, read on 2022–24 — runner-only, no pinned byte moved

**Trigger**: his correction of the sell rule (`operator_shared_notes.md` 2026-10-18): the first third goes at +2R, then breakeven,
then the 10-day (faster stocks) or 20-day (slower; "also depend how far they are from 10/20") trail — and *"The day thing is also
correct, it may be a combo and depends"*; plus his A+ question (tightness before the breakout) and the stop variants of the brief.

**What**: (1) module (additive): `PARTIAL_TARGET_R`, `PARTIAL_TRIGGERS`, `TRAIL_MODES`, `TRAIL_SPEED_ADR_CUT`, `TRAIL_DISTANCE_X`,
`STOP_HALF_ADR`, `STOP_VARIANTS`; four `Arm` fields defaulting to the registered behaviour (`partial_trigger`, `partial_r`,
`trail_mode`, `trail_dist_x`, validated); guarded branches in `walk_exit` (the +R target: a gap open above it at the open, a high
at it AT it, both-touched books the stop; the speed / distance SMA choice; `day0_partial_px`); `day0_walk_target`,
`day0_target_to_outcome`, `walk_his_arms`, `stop_variants`, `HIS_EXIT_ARMS` (25). `ARMS` is still the 15 the shadow iterates.
(2) runner: `read_candidates(extra_floats=)`, the `exits` / `exits-report` stages, `--levels` (the holdout REFUSES it); discovery
split hard-coded; new files only. (3) tests: 28 module cases (the touch, the gap-through, both-touched, the combo, the no-trail-
before-the-partial, both switches, day 0 on the minutes, the stop variants, `d3_p33_t10 == p33_s3_t10`, the registered arms never
emit the new events) + 12 runner cases (the stage end to end, the registered row equals the minute stage's, holdout refusal).
(4) the read: `docs/analysis/cb_his_exit_2026-10-18.md`.

**Result (discovery, ORH5, spec key)**: his exit reads a little less bad than the article's day-3 partial on C0, inside the noise
(`tl` n = 8,985: −0.070 vs −0.087 ADR per trade for the best same-population combo, `c3_p33_t20` on the half-ADR-capped day-low
stop; interval [−0.29, −0.05]); the +2R partial lowers the ≥ 5R share (2.7% vs 3.6%) and raises the win rate (29% vs 24%); on C1
`tl` (79) it reads +0.32R vs −0.05R with an interval spanning zero, and worse on `com` / `comb` C1; the wider stops do not help and
the base-low stop is a tight-base subpopulation (755 of 8,989); the tightest fifth of bases is still the worst fifth under his
exit. **Nothing is decided**: the primary stays `p33_s3_t10` on the low-of-day stop; the grid is a reported alternative.

**Anticipated effect**: none in production — the shadow walks `cb.ARMS` only; no table, job or Telegram changes. Byte-identical
proof: `daily | minute | step0-entries | report` on the default keys re-run into a scratch dir before and after the change, all
seven content hashes equal to the pinned set; every existing `*_com_comb` file in `DATA/out/` hashes identically. **Freeze
consequence**: the module and runner pins are stale by bytes (the state declared since P4b step 6); `holdout` refuses until the
main loop re-pins.

**Reversion-flag**: NEW (additive; no existing level, cell, entry, stop or exit moved). Reverting = drop `HIS_EXIT_ARMS` /
`stop_variants` and the two stages. **Status**: built on a worktree branch; the read is done; no holdout row opened.

### 2026-10-18 — #702 P4b step 6b: `comb` (`com`, closed at or below the line the night before) is the primary `com` reading, plus the per-regime table — runner-only, no pinned byte moved

**Trigger**: step 6's `com` level sits under the watch night's close on 38% / 41% of watch nights, so the next-day "breakout" there
is often just an up day; and the operator (2026-10-18): *"breakouts likely wont do as well in bear markets, or choppy markets"*.

**What**: (1) module: `EXTRA_PIVOT_KEYS = ("com", "comb")`, `CLOSED_BELOW_KEYS = ("comb",)`, `comb_fields` (the three `pivot_comb*`
fields copy `com`'s), `cell_flags(k="comb")`: C0 additionally needs `close(D) <= pivot_comb` (equality counts, a missing close
reads False). (2) runner: `--keys comb` / `--keys com,comb` (ONE pass; outputs `*_com_comb`, the `K` column carries both); a `comb`
candidate exists only on a night that closed at or below the line (the unstated piece: a from-above row would be
`retrigger = 0` and push the real break-from-below to `retrigger = 1`); the daily stage asserts the `comb` (ticker, E) pairs are a
subset of `com`'s (`comb_fetch_check`) so no minute fetch beyond `com`'s is needed. (3) the per-regime table: `report` writes
`regime_report{suffix}.tsv` and the `holdout` stage writes `regime_report_holdout.tsv` on its one run — for every cell row of
the headline table, n / mean R / share >= 5R per `apollo_regime` (Bull / Choppy / Correcting / Crisis / missing + an `ALL` row);
the label is joined from the candidates table at read time (the trades layout carries none), and the table is reported
BESIDE, never deciding. **Coverage caveat, measured: Apollo's regime label exists only from 2025-03-03 (424 dates: Bull 289 / Choppy 36 /
Correcting 42 / Crisis 57), so every DISCOVERY night (2022-03-28 .. 2024-12-31) and the holdout's first 39 nights read `missing` —
the discovery table is one `missing` column; a discovery-era regime split would need a bars-based rule (a separate, declared step).** (4) tests: `comb` C0 false above / true at equality and below / every cell inherits it, `comb_fields`,
C0 on every MRNA watch night, the one-pass `com,comb` daily (strict subset of `com`, `com` rows byte-identical to the `com`-only
run, same fetch list), the subset assertion (pass + raise), the regime table on a synthetic set (n per regime adds to the cell's n),
and the report / holdout end to end. (5) docs: this row and entry, preregistration §P4b.6, the runner README.

**Anticipated effect**: none in production — the shadow computes `KS` only. Byte-identical proof: `daily|minute|step0-entries|report`
on the default keys re-run into a scratch dir, all seven content hashes equal to the pre-change run; `daily --keys com
--no-close-variant` reproduces `candidates_com.tsv` / `watch_com.tsv.gz` byte for byte. **Freeze consequence**: the module, runner
and doc-body pins are stale by bytes (as already declared at step 6); `holdout` refuses until the main loop re-pins after the `com`
minute fetch. **Not decided here**: no regime filter, gate or size change is proposed; the primary triple and every bar are unchanged.

**Reversion-flag**: NEW (additive; no existing level, cell, entry, stop or exit moved). Reverting = drop `comb` from
`EXTRA_PIVOT_KEYS` and the regime-table calls. **Status**: built on a worktree branch; the `com,comb` discovery re-read waits on the
`com` minute fetch (main loop); no `com` / `comb` outcome has been read.

### 2026-10-18 — #702 P4b step 6: a fifth breakout level `com` (the base's median high — where he actually draws the line), runner-only, no pinned byte moved

**Trigger**: his 2026-10-18 rule (verbatim in `operator_shared_notes.md`): the line goes on the consolidation's center of
mass, a 1–3 bar spike that drops back is ignored; and step 5's finding that on 32 of his 58 drawn lines EVERY existing level
sits above the line (median 5.6%, ~1.5 ADR under `pivot_full`).

**Evidence**: 58 labelled bases (48 bar_verified / 10 eyeball_confirmed; 2019–23, one bull era), scored by
`scripts/probes/_qm_streams/p4b_com_rule.py` over 262 readings of his sentence, all computed by the module's own
`cb.com_level`, with the pick rule written before the grid ran (`docs/analysis/cb_preregistration_2026-10-18.md` §P4b).
The only plateau is the quantile family at q 0.4–0.55; **q = 0.5 (the median base high) puts 43 of 58 lines within 0.5 ADR
(bar_verified 35 of 48, eyeball 8 of 10, flat 26 of 35, falling 17 of 23), bias +0.01 ADR; the best existing level (k5)
23 of 58, bias +0.58 ADR; the literal "ignore the spike, take the top" reading 8 of 58 (1.2 ADR above his lines).**
Runner-up: `switch_close` (filtered flag line when falling, highest kept close when flat) 31 of 58. 10 of 58 miss by over
1 ADR, 8 of them lines drawn well below the base that no base-top rule reaches.

**What**: (1) module: `EXTRA_PIVOT_KEYS = ("com",)`, `spike_mask` and `com_level` (six readings; the chosen one by default),
`cell_flags` / `breakout_key` accept the extra key; `explain_watch`, the four levels and `KS` untouched (the shadow iterates
`KS`). (2) runner: `--keys com` runs the level through `daily` / `minute` / `step0-entries` / `report` into `*_com`
outputs (`candidates_com.tsv`, `minute_fetch_list_com.tsv` + `_delta_com.tsv` in `fetch_minutes.py`'s format,
`trades_discovery_com.tsv.gz`, `discovery_report_com.txt`); `--no-close-variant` (daily) computes no outcome; `holdout`
refuses `--keys`. (3) registry: `COM_VARIANT`, `COM_QUANTILE`, `COM_MAX_RUN`. (4) tests: equivalence (no filter = the
existing levels on every MRNA watch night), the synthetic spike cases, the character switch, and five of his labelled
bases as a fixture (`tests/fixtures/cb_p4b_labelled_bars.psv` + `cb_p4b_labels.tsv`, bars and derived numbers only).

**Anticipated effect**: none in production — the shadow computes `KS` only and no table, job or Telegram changes. The
byte-identical proof: the four stages re-run on the registered levels into a scratch dir, all seven content hashes and the
four other pinned outputs (`minute_fetch_list.tsv`, `gap_in_bars.tsv`, `minute_fetch_list_delta.tsv`,
`discovery_report.txt`) identical to the 10-17 run. **Freeze consequence**: the module, runner and doc-body pins are
stale by bytes (additive code, unchanged outputs); `holdout` refuses until the main loop re-pins after the `com` minute
fetch (which changes the minutes pin anyway). Under `com` the level sits under the watch night's close on 38% of watch
nights and the breakout day opens above it on 55% of first breaks (C1 holdout: 23 of 42) — an EARLIER, lower entry than
the four levels; stated in §P4b.4, to be read, not tuned.

**Reversion-flag**: NEW (additive; no existing level, cell, entry, stop or exit moved). Reverting = drop `--keys` and the
`com_level` call; nothing else depends on them. **Status**: built on a worktree branch; the `com` discovery re-read waits
on the minute fetch (main loop); no `com` outcome has been read.

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
**Reversion-flag**: NEW; not a detection-criterion change. **Status**: DEPLOYED 2026-10-18 (028fddcb is in server 25fabf93);
the shadow's first live run is Mon 10-19 17:48 ET. EXPECT / DONE-WHEN / WOULD-FAIL-IF: CHANGELOG 2026-10-18 (#702 minute fetch).

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
**Status**: DEPLOYED 2026-10-18 (server 25fabf93; `deploy.sh both` + `execution`); verify on the first split night per
#704's PLAN line (ETA 10-23). EXPECT / DONE-WHEN / WOULD-FAIL-IF: CHANGELOG 2026-10-18 (#704).

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
