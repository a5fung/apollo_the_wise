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

## Breakout v1 — the nightly LIST rules (the PAPER setup; REBUILT 2026-11-02 on his spec sign-off)

The table above is the forward SHADOW's (`cb`). Breakout v1 — the paper setup's 17:55 ET list (`breakout_v1.py`,
`breakout_v1_list.py`, table `mi_breakout_v1_list`) — has its OWN rules and constants (it reads `cb`'s helpers, never
moves `cb`'s numbers). Since the 2026-11-02 rebuild (change log below; spec
`docs/analysis/cb_rebuild_from_qm_trades_2026-11-02.md`, "signd off"), at the watch night D on bars <= D:

> **⚠ 2026-11-11 — INITIAL RULE SET wired on branch `worktree-agent-af09ad1fb995d350b`, PENDING HIS SIGN-OFF BEFORE
> PAPER (deployed 2026-11-11 `cec3cc3c`; `breakout_v1_paper` OFF).** Change log 2026-11-11 below. Where it differs, it
> SUPERSEDES the table under it:
> - rule 5 run-up into the pole **>= 20%** (was 32.1%) · rule 4 base depth **1.51-11** daily ranges (was -8.98) ·
>   rule 6 close vs the 21-day EMA **>= -0.9** (was -0.6335) · rule 7 the 50-day **is no longer a gate** (telemetry).
> - A **range** (10+ sessions counting to the next session, giving back no more than half its run) is MEASURED on
>   every name (`breakout_v1.range_levels`, the row's `range`); it is never a gate. **The level = the LOWER of the
>   range high and the 5-day high** (`level_source`); no range = the 5-day high as before. **Wick rule:** a 5-day
>   high set by a day that closed in the lower half of its range is replaced by the high of the sessions after it.
> - **Volume is NOT a buy condition** (his 2026-11-11 "drop it"; replaces F1 of 10-29 and the 1.2 x 10-day bar of
>   11-02): the price break alone buys. The bar and the intraday pace are still computed and recorded.
> - **⚠ 2026-11-12: rule 3 the daily-range floor is now ADR20 >= 4% (was 2.1%)** — change log 2026-11-12 below.
> - Unchanged: $2, $5M, 86 sessions, strength 35, stop, sizing, exits, slots, the order score.

| # | Rule | Value | Source | Code |
|---|---|---|---|---|
| 1 | universe + history | raw close >= $2, 20-session median dollar volume >= $5M, >= 86 consecutive sessions | v1 (2026-10-28), unchanged | `universe`, `history`; `MIN_PRICE`, `MIN_DOLLAR_VOL`, `MIN_BARS` |
| — | pinned deal | ADR20 >= 1% (inside rule 3; kept so the counts name a deal target) | his "both", 2026-11-02 | `pinned`; `PINNED_ADR_MAX` |
| 3 | daily range | ADR20 >= 4% (2026-11-12; was 2.1%, his good EW 2.11%, LMT 2.6%) | his 2026-11-12 "aligned": Qullamaggie does not trade low-ADR stocks, "4-5 as minimum" | `adr`; `ADR_MIN` |
| 2 | strength | rs_best (best of the 21/63/126-session percentiles) >= 35 | Qullamaggie's 269 buys' lowest, 35.3 | `rs`; `RS_MIN` (the list's own; `cb.RS_BEST_PRIMARY` 98 is the shadow's) |
| 5 | run-up into the pole | high(P) / min low[P-40, P] - 1 >= 0.3213536987121892 (P = the pole top in [D-45, D-10]) | backward step 3 (dropped only his NOs) | `prior_move`; `PRIOR_MOVE_MIN` (the list's own; `cb.PRIOR_MOVE_MIN` 0.30 stays) |
| 4 | base depth | (high(P) - the lowest low of P+1..D) / high(P) / ADR20 in [1.511376833908041, 8.979719460898997], inclusive | backward step 2; low end = his good LRN 2020-08-05 | `base_depth`; `BASE_DEPTH_ADR_MIN/MAX` |
| 6 | close vs the 21-day EMA | (close / EMA21 - 1) / ADR20 >= -0.6335 (EMA seeded at the series' first bar) | his labels on 9 EMA-dropped buys; pinned at TSLA 2022-04-21 (-0.63349) | `ema21`; `EMA21_ADR_MIN`, `ema_at` |
| 7 | close vs the 50-day SMA | close >= the mean of the 50 closes ending D | his picks; drops none of Qullamaggie's buys | `sma50`; `SMA_SESSIONS` |
| — | REMOVED | higher lows, surf (riding an average), tightening, the breakdown check | his CODX / PENN charts (11-02): the definitions misread his pattern | — |

- **The level and the volume bar (for the next session):** level = the highest high of D-4..D (strict break); the
  volume bar = **1.2 x the mean volume of the last 10 sessions D-9..D** (his ruling 2026-11-02; was the 50-day; `vol50`
  is kept on the row as telemetry only). Live, the entry reads it as the F1 intraday pace against this bar.
- **The ORDER inside the list (spec §2; `breakout_v1.order_inputs` + `breakout_v1_list.rank_rows`):** per name,
  `runup6m` = max over j in [D-125, D] of high(j) / min low[j-63, j] - 1, `runup6m_adr` = it / ADR20, and
  `spread10_adr` = (max / min - 1 of the closes D-9..D) / ADR20; per NIGHT over the whole passing list,
  order_score = the mean of the within-night percentile of `runup6m_adr` (bigger first) and of `spread10_adr`
  (tighter first), pandas `rank(pct=True)` average-tie semantics; list_rank 1 = the highest score, ties by ticker; a
  name missing an input has no score and ranks last. The score ORDERS, it never removes. Stored as `order_score`,
  `runup6m_adr`, `spread10_adr` on `mi_breakout_v1_list` (comparable only inside one night).
- **The message and `/bgrade`:** the 17:55 Telegram shows the top 10 by the score + the night's count — and, since
  2026-11-07 (stage 2), no `/bgrade` line (his 2026-11-05 word: grades come from chart sheets shown in chat); bare
  `/bgrade` still shows the newest night's top 10 ungraded + the total and per-night ungraded counts (the command stays
  as the catch-up path).
- **The entry at 150-350 names (stage 2, 2026-11-07; change log below):** the minute job reads every name's bars in ONE
  batched fetch, takes the paper slots in LIST RANK order (hold-only; the overflow waits for a slot the same session,
  judged at that minute's price) and records, at 15:55, every name that BROKE OUT while held and never got a slot
  (`breakout_v1_missed_by_slots`, with the first break minute — the level reached with the volume pace held, the live tick's own check).
- **Acceptance:** `tests/test_breakout_v2_stage1.py` on `tests/fixtures/qm_breakout_scorecard/` (the scorecard below).

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
- **Breakout v1's list tests no SHAPE (open since 2026-11-10; #717).** The first paper session bought five charts he
  said were not breakouts (no higher lows, no price surfing a rising 10/21-day). The shape rules removed on 11-02 are
  being rewritten from Qullamaggie's words and his reads as list gates: pre-registered and scored in
  `docs/analysis/cb_shape_gates_2026-11-11.md`. **Result 2026-11-11: FAIL — no shape gate is enforced
  (`breakout_v1.ENFORCED_SHAPE_GATES` is empty; the list is the seven rules above, unchanged).** The five gates reject
  11 of his 12 `no` charts but keep only 6 of his 16 good / ok and 108 of Qullamaggie's 269 buys; the one revision
  (close no more than 1 daily range above the 10-day EMA + the last 10 closes within 4 daily ranges) rejects 9 of 12
  (SIG, ABCL, NVAX pass), keeps 13 of 16 and 225 of 269 (24 of 26 big winners). Higher lows and the rising average are
  still not defined in a way that matches his grades. Paper stays OFF; any gate ships only on his sign-off.
  **Round 2 (2026-11-11, after his regrade to 17 `no` / 11 good-ok and "stick with qullamaggie first"):** four gates
  sized against Qullamaggie's own buys — the close not above the pole top, the 21-day EMA not lower than 5, 10 and 20
  sessions ago, the 21-day EMA no more than one daily range under the 50-day, the base's low not made on the list
  night — reject 13 of his 17 `no` (SIG, DUOL, CVLT, OUST pass), keep 9 of 11 good / ok and 249 of Qullamaggie's 263
  listed buys (25 of 26 big winners). Still short of "every `no` rejected", so still NOT enforced.
  **Round 3 (2026-11-11):** one long-term-trend gate on top (close above the 200-day; 50-day above the 200-day; a
  rising 200-day; both) — every variant FAILS: 16 to 32 more of Qullamaggie's buys go (big winners 22-23 of 26), and
  the rising-200-day ones drop three of his own good / ok charts. Not enforced.
  **Round 4 (2026-11-11, his grades on the would-buy sheet: 2 of 12 ok, "a few more tight days"):** three right-edge
  tightness gates (range of the last 5 sessions vs the 5 before; the last 5 closes' band; tight days in a row) each
  drop most of his 13 good / ok (2, 6 and 0 kept) and 45 to 137 of Qullamaggie's buys — the names he sends back for
  "more tight days" are already the tightest by daily bars, and five tickers graded twice a few sessions apart carry
  opposite grades. SCOPE FINDING (the analysis doc's last section): 28 of 28 is not reachable by a rule on these bars
  until he says what the tight-days read counts. Nothing enforced.
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
- **Breakout v1's rebuilt list (2026-11-02) — known limits, carried in the open:** (a) it keeps **16 of Qullamaggie's buys
  he labelled no / EP-like** (named in the change log; pinned ON in `tests/test_breakout_v2_stage1.py` as the committed
  negatives the next rule is judged on) and MRNA / INO 2020-08-07 ("breaking down") still pass; (b) it holds **~250 names a
  night** and the order score separates his yes from his no only 70% of the time — of his firing buys only 52 of 156 rank in
  their day's top 5 (stage 0); the slot RULES are his 2026-11-06 rulings (hold-only, the overflow waits the same session,
  the count stays 5 shared with the small-cap lane) and every name that broke out while held for a slot and never got
  one is recorded for #720's monthly review (`breakout_v1_missed_by_slots`) — whether the slot count or the order
  should change is that review's question; (c) CLOSED 2026-11-07 (stage 2, change log below): the entry job reads the list in one batched
  fetch per minute (≤ 14 requests at 350 names) and fills the slots by the score; the paper switch stays off until his
  word; (d) two rules sit on knife edges by
  design — rule 6 at TSLA 2022-04-21's own value (1.3e-5 daily ranges inside) and rule 4's low end AT LRN 2020-08-05's
  depth — so a change in how ADR20, the EMA or the depth is computed can drop his own "ok"/"good" buys (the scorecard test
  catches it); (e) the order inputs read up to 189 sessions (the list job loads 200; a name with less history gets a
  shortened 6-month look-back, as the research's era-B store did on its first 59 nights).

## Change log

### 2026-11-12 — breakout v1: ADR floor 2.1% → 4% (OPERATOR-SIGNED "aligned", 2026-11-12; paper still OFF; not deployed)

**Trigger**: his words 2026-11-12 — Qullamaggie does not trade low-ADR stocks, **"4-5 as minimum"**; his reply to the floor proposal: **"aligned"**.

**Evidence**: era-A replay `scripts/probes/_717_precision_1112/03_adr_floor.out` — fires a day (median) **213 → 68**; all **26 of 26** big winners kept; fired Qullamaggie buys **447 → 375**. The buys under 4% are mostly undated panel sightings, funds and liquid large caps — none a big winner. 5% would keep 299 and 25 of the 26, so 4% is the floor.

**What changed**: `breakout_v1.ADR_MIN` 0.021 → 0.04 (the `adr` gate; the 1% `pinned` gate is unchanged). On the scorecard: of the 269 dated buys, 40 now stop at `adr` alone (229 listed, 217 fire on the break day; 256 before), none a big winner. 22 more of the 84 High-tier buys drop (56 listable, was 79), each by `adr` alone. Three of the 16 known non-setups (TDOC 2019-10-31, MU 2021-12-21, FCX 2021-12-27) and two of his six former NOs (YPF, SQM) leave the list.

**Head to head on all 757 buys** (`13_head_to_head.py` run on current constants with the 11-02 side pinned to ADR 2.1%): listed **479** (11-02 rules 455), fired on the daily bar **386** (209); the 26 dated big winners 26 of 26 fire (21). 31 buys the 11-02 rules fired no longer fire.

**Reversion-flag**: REVERSAL of the 2026-11-02 rebuild's 2.1% floor and a partial return toward the 2026-11-02 4.26% floor it replaced; `ADR_MIN = 0.021` restores it. Tests: the shape-gate research records are re-read at 2.1% in their autouse fixture (scored on those rules).

### 2026-11-11 — breakout v1: VOLUME IS NO LONGER A BUY CONDITION — the price break alone buys (his ruling "drop it"; PENDING HIS SIGN-OFF BEFORE PAPER; wired on a branch, not merged, not deployed, paper OFF)

**Trigger**: his words 2026-11-11 — *"we need to look at the moment he buys not after the fact"*, then, on the pace-at-the-cross result, **"drop it"**. Full-day volume is unknowable at the entry, and the live pace check blocked Qullamaggie's own buys.

**Evidence**: `scripts/probes/_717_qm_confidence_1111/15_pace_at_cross.out` — minute bars on 261 of the 272 buys the daily trigger fired on and on all 26 big winners; at the first minute from 09:35 that reaches the live level, the live pace (volume through the minute before / the 10-day average x the intraday curve) is at or above the 1.2 it needed on **82% of the fired (n = 244)** and **66% of every buy that took out the level (n = 421)**; 18 of the 26 big winners. The four big winners the day's volume kept out cross at 0.38 (DOYU 2020-08-24), 0.60 (MDB 2020-09-21), 0.86 (JMIA 2021-01-12), 1.00 (NVDA 2020-09-25). **Head to head, all 757 (n = 757 / 757 / 26; `16_no_volume_gate.out`; listed / fired on the daily bar / big winners fired): with the volume bar 566 / 272 / 22; the price break alone 566 / 465 / 26; 0 lost, 193 gained.**

**What changed**: `breakout_v1.breakout_triggered` fires on the level alone (`volume_pass` still reported); `broker/breakout_v1_entry.VOLUME_PACE_GATE = False` — a name under the pace gets its buy, a resting buy is not cancelled for volume, and the missed-by-slots record counts a touch of the level as the break. The pace (`f1_ok`, `cum_volume`, `need_volume`) stays on the tick state, the order audit row and the missed row; the list row keeps `vol_bar`. The nightly message no longer states a volume condition. Stops, sizing, exits, slots, the safety floors: untouched.

**Anticipated effect**: more buys, earlier in the session (no wait for the pace), including breaks on quiet volume. Not measured: how many more non-Qullamaggie names buy across the market, or their outcome.

**Reversion-flag**: REVERSAL of F1 (2026-10-29, "volume so far >= 1.2x normal by that minute") and of the 2026-11-02 volume bar (1.2 x the last 10 sessions) AS BUY CONDITIONS — both judged a day's or a minute's volume against a bar his own buys do not respect at the moment of the buy (above). `VOLUME_PACE_GATE = True` restores the old behaviour; its tests still run with it on.

**Status**: MERGED and DEPLOYED 2026-11-11 21:16 ET (server `cec3cc3c`, market-agent then execution); `breakout_v1_paper` = off (read on prod after the deploy) — paper only on his word after his sign-off.

### 2026-11-11 — breakout v1 INITIAL RULE SET: the list gates loosened to keep Qullamaggie's buys; a range is measured, the level is the lower of the range high and the 5-day high (PENDING HIS SIGN-OFF BEFORE PAPER; wired on a branch, not merged, not deployed, paper OFF)

**Trigger**: his words 2026-11-11 — *"rate each buy with how confident we know it's a breakout and where the buy point is, then let's first focus on the high confidence ones to craft initial rules, then expand as needed"*; on the 21 high-confidence buys the list missed, *"these are qullamaggie buys, they all look good"*; then *"we are trying to buy like qullamaggie, stop with all the random tangents, buy his setups period."* The only target is Qullamaggie's buys; his grades of our list charts and his earlier NO labels of Qullamaggie buys are a report column, not a bar.

**Evidence**: `docs/analysis/cb_qm_buy_confidence_2026-11-11.md` (the rating of his 757 buys; 84 High) and `docs/analysis/cb_initial_rules_2026-11-11.md`. **Head to head on all 757 buys (`scripts/probes/_717_qm_confidence_1111/13_head_to_head_fixup.out`; listed the night before / fired on the daily bar of a window session / big winners fired, n = 757 / 757 / 26): the 11-02 rules 455 / 209 / 21; this rule set 566 / 260 / 21.** Every buy the 11-02 trigger fired on still fires (0 lost); 51 more fire, 14 of them widened High. On the 84 High: 79 listed the night before (63 on 11-02), 76 fire (`tests/test_breakout_v1_range_break.py`, by name). Per change: prior move 20% (lowest High buy 21%, PBR; flat from 20% to dropped) · the 50-day dropped (9 of the 31 widened High buys sat under it; NVAX 2021-04-13 21% under) · EMA21 -0.9 (NVAX -0.85) · base depth to 11 (HEXO 10.8).

**What was tried and NOT kept (same day):**
- **A range as a list gate + the range high as the only level + a 20-session volume bar** (the first wiring, `c41436db`): 319 listed / 94 fired / 11 big winners — fewer of his buys than the 11-02 rules. Removed.
- **The range high as the level wherever a range exists** (measured, not wired): 228 fired, 18 big winners, 27 of the 11-02 trigger's buys lost — the range high sits AT or ABOVE the 5-day high, and he often buys the nearer pivot.
- So the level is the LOWER of the two. **On all 566 listed buys the range high was never under the 5-day high, so today the level IS the 5-day high everywhere and the whole gain comes from the loosened gates**; the range high is recorded on the row as the rated buy point, for the next step.

**The wick rule (same day, his "Fix it"; pre-registered in `docs/analysis/cb_initial_rules_2026-11-11.md` §WICK RULE, pending his sign-off):** when the highest high of the 5-day window was set by a day that closed in the lower half of its own range (upper wick >= 0.5 of the day's range) and is not the last day, the level is the highest high of the sessions AFTER it (`breakout_v1.settled_level`, `LEVEL_WICK_MIN`; the row's `level_source = settled_after_wick`, `wick_date`). His 2026-10-18 note: *big upper wick then settling lower → ignore part of the wick.* Case: APT 2020-02-21 — 5.98 (the 02-13 spike, close 5.18) becomes 5.40 and the buy fires. **Head to head, all 757 (n = 757 / 757 / 26; `14_wick_rule.out`): 566 listed / 260 fired / 21 big winners without it; 566 / 272 / 22 with it; 0 lost.** The 12 gained: APT 2020-02-21, CRWD 2020-09-18, NVAX 2020-12-17, DKNG 2021-02-26, LAC 2021-09-30 (dated); IPHI 2020-01-03, EPZM 2020-01-23, ROKU 2020-09-15, DQ 2020-11-24, CAN 2020-12-30, MELI 2021-02-19, DVN 2022-02-11 (widened). Sweep X = 0.4 / 0.5 / 0.6 / 0.7: 273 / 272 / 271 / 269 fired, 22 big winners at each. Not measured: how many more non-Qullamaggie names a lower level triggers across the market.

**Known costs, stated plainly (each pinned in a test):**
- **The unchanged floors cost 5 of the 84:** BNGO 2019-12-30, INO 2020-01-21, HEXO 2020-08-13 ($5M dollar volume: $1.5M, $3.6M, $4.4M), FCEL 2020-02-10 (raw close $1.72, the $2 floor) and PLTR 2021-01-22 (86 sessions). Moving a floor is his call.
- **Three listed High buys are short of his volume bar on the break day:** AMD 2020-01-17, AVLR 2020-01-02, LVGO 2020-09-25.
- **His 6 former NOs and MTW 2026-10-30 are back on the list.** His 28 no / not-yet list charts all pass the loosened gates.

**Anticipated effect**: a longer nightly list (more names clear a 20% run-up, sit under the 50-day, or have a deeper base). How much longer is NOT measured — the saved 11-10 file holds only the 190 names the 11-02 rules listed, all 190 of which stay. Levels, the volume bar, the entry, stop, sizing and exits are unchanged.

**Reversion-flag**: REVERSAL of four 2026-11-02 list constants (prior move, base depth cap, EMA21 line, the 50-day gate) — the 11-02 values were fit on the 269 buys OUR detector could date and on his NO labels of Qullamaggie buys; the widened set (488 more of his positions) showed they drop his clean range breaks, and his 11-11 ruling removes those labels as a bar. NEW: the range measure (telemetry + the lower-of-two level).

**Status**: MERGED and DEPLOYED 2026-11-11 21:16 ET (server `cec3cc3c`, market-agent then execution); `breakout_v1_paper` = off (read on prod after the deploy) — paper only on his word after his sign-off. Not verified: the whole-market list size; the intraday entry on the break days (daily bars only); strength rank on 6 unranked nights.

### 2026-11-07 — breakout v1's paper entry reads its strategy row FRESH every minute, and a row it cannot READ is a third state: no action that minute, nothing cancelled (#312 review + re-review; the PAPER lane only — no rule, number or exit moved)

- **Why**: his Demote / No action page (#312) commits a phase change in the market agent; apollo-execution's registry cache never learned of it, so the entry tick would have kept ordering on the OLD phase until a restart. The tick now reads `registry.get_strategy_fresh` (one primary-key SELECT, bounded 5 s on the acquire and the query — `FRESH_READ_TIMEOUT_S`, re-review finding 5) every minute.
- **The third state** (re-review finding 2): the round-1 fix answered a FAILED read like a refused phase, and the tick's switch-off branch then cancelled every resting buy under `block:strategy_disabled` — one database blip at 10:05 lost that name for the day. Now `_strategy_state` answers `STATE_UNREADABLE` and the tick returns `strategy_unreadable`: no new order, no re-price, NO cancel — a resting buy is left exactly as an unreadable broker leaves it — and the next minute re-reads. The cancel of resting buys stays for the switch / a disabled row (`switched_off`, quiet) and for a phase other than paper (`refused`, paged). Audit row `breakout_v1_strategy_unreadable` per such minute; paged once a day under its own key (never the refusal's, so a morning blip cannot silence a real refusal page later that day).
- **Tests**: `tests/test_breakout_v1_entry.py` — a resting buy plus one failed read (a timeout) at 10:05 leaves the buy open (`order_placed`, no cancel event), one page; 10:06 proceeds with the buy `resting`; a real refusal at 10:07 still pages (two pages) and still cancels. Red on the round-1 code (it answered `switched_off` and cancelled).

### 2026-11-07 — breakout v1 STAGE 2 (#717): the entry job reads the whole list in ONE batched minute-bar fetch, fills the paper slots by the order score HOLD-ONLY with the overflow WAITING for a slot the same session, and records every name that broke out but never got a slot (OPERATOR-SIGNED 2026-11-06 "Go with rec, track what we miss"; the PAPER lane only — the switch `breakout_v1_paper` stays OFF) — BUILT + REVIEWED TWICE (the 11-07 review's six findings and the re-review's four fixed, below), not deployed

**Trigger**: the rebuilt list (2026-11-02) holds 150-350 names a night (11-05: 150, 11-06: 184) and the entry job was built for ~25: it fetched one name's minute bars per REST call every minute (~350 calls a minute, ~133,000 a day at 350 names), and its slots were first-to-break — the funnel's `block:max_positions` wrote a terminal `skipped` row, so on the first tick with 6+ names past the pace every name past the 5th was dead for the day. Known limitation (c) above; stage 0's open question ("the slot count or a better order"); his 2026-11-05 word that grades come from chart sheets, not Telegram (the `/bgrade` line goes).

**Evidence**: user judgment — his rulings 2026-11-06 on the two forks put to him with recommendations (`docs/design/717_stage2_design_2026-11-06.md` §G; PLAN #717's 11-06 note), verbatim *"Go with rec, track what we miss"*: (1) HOLD-ONLY, no displacement of a resting lower-ranked buy; (2) a name the full book turns away WAITS for a slot the same session, judged at that minute's price by the existing width rule — no terminal skip; (3) TRACK WHAT WE MISS — every list name that met the break but never got a slot that day is recorded for #720's monthly review. The request arithmetic (design D1, read from alpaca-py 0.43.2): `get_stock_bars` pages 10,000 bars per HTTP request across symbols, so 350 names cost 2 requests at 09:35 and 14 at 15:55 (~2,800 a day, under the 200-a-minute data floor). No detection criterion or threshold moved (not a backtest item, CHANGE_PROCESS rule 1 does not apply); the slot order is the list's own order score, signed 2026-11-02; the slot count stays 5 shared with the small-cap lane (his F2, 2026-10-29).

**The change** (code: `broker/breakout_v1_entry.py` — the tick, `_free_slots`, `_hold_for_slot`, `_record_missed_by_slots`; `broker/alpaca_client.py::get_minute_bars_range_batch` + `bars_batch_chunk_size`; `db.bv1_get_list` now also reads `order_score`; `breakout_v1_list.py::format_list_message`):
- **ONE batched fetch per tick** for every name the minute must judge (no row yet before 15:55, or a resting / unsubmitted breakout row; at 15:55 also the held-never-seated names, for the missed record below), the whole day so far (never incremental — a late minute bar under an incremental read would under-count the pace), chunked so each request is one page (symbols per request = min(200, 10,000 // (bars so far + the minute in progress))), sequential on the batch's OWN single-thread executor (`alpaca_client._run_bars_page`; re-review fix 2026-11-07, finding 2 — never `_sdk`'s ~7-thread pool that every broker call in apollo-execution shares: a live EP order, a cancel, a stop placement), each page bounded at 60 s (the design said bare `to_thread`; a bounded wait means a hung page ends the read instead of holding the event loop). **A page that HANGS (its 60 s fires) ends the loop for that tick** (review fix, finding 4): the chunks after it are not sent, the unsent names are unread that minute, retried next tick — **and while that page is still on the batch thread, every later tick SKIPS its batch outright** (`get_minute_bars_range_batch` answers None; the tick writes one `breakout_v1_bars_batch_in_flight` row, 'bars batch still in flight', every name unread that minute, a resting buy left as it is): a hanging bars endpoint can never hold more than that ONE thread, never a thread of the shared pool, and never a queue of stale pages behind the stuck one; it clears by itself the moment alpaca-py returns. A chunk that fails FAST leaves only its own names ABSENT from the answer → `bars_unreadable` this minute, ONE `breakout_v1_bars_unreadable` audit row naming them, and a resting buy under such a name is left exactly as it is (never cancelled or re-priced on nothing); a name Alpaca returned no bars for is `[]` → `wait`, as before. **3 straight ticks with unread names — a failed request or a skipped in-flight batch alike — page ONCE a day** (paper-prefixed, naming the names and the reason; a tick where every request answered resets the count — review fix, finding 5: an audit row a minute would have let one bad symbol blind up to 200 names all day unseen). `evaluate` / `bars_by_minute` untouched; the fill check's own per-name read untouched. With the switch OFF the tick still returns before any batched read (pinned; the fill check's per-name read still runs for a filled breakout row).
- **THE SLOTS**: after the existing rows are managed (pass 1 — a cancel this minute frees its slot this minute), the names whose state permits a buy (opening range set, stop inside ADR20, the F1 pace) are taken in LIST RANK order; `free` = 5 − `live_tracker.count_open_positions(conn, 'paper')` (the funnel's own SQL: every paper strategy's filled / order_placed / confirmed rows — the lane's included), and the SMALLER of that and the breakout row's own `mi_strategies.max_concurrent_positions` minus its own open count when that cap is set (NULL today, F2; the funnel enforces it when set, #65 — review fix, finding 5); the first `free` go to the funnel (whose advisory-locked recount still rules), the rest are HELD: one `breakout_v1_entry_hold` row (state `slots_full`, carrying the first hold's facts, the free count AT the hold — 0 — and how many names were seated ahead of it that minute), NO trade row, retried every minute. A funnel `block:max_positions` or `block:strategy_position_cap` on one name (the disclosed race with a same-moment lane entry) holds the rest of that minute's names instead of sending each to a terminal skip — **and writes the blocked name a hold row too** (review fix, finding 3: its skipped row is terminal for the day, so without the hold row 15:55 could never record it); an ordinary funnel skip (the width rule at the fill) does not consume the slot. An open count that cannot be READ holds every eligible name under its OWN state (`slots_count_unreadable`, `breakout_v1_slots_unreadable` audited) which 15:55 never records (review fix, finding 5: a database blip must not become a missed record). The pre-flight is asked once per tick, not once per name. HOLD-ONLY pinned in a test: a resting lower-ranked buy is never cancelled to seat a higher rank (displacement = a one-function add on his word).
- **TRACK WHAT WE MISS** (his ruling: *"every name that met the break (level + volume pace) but never got a slot that day"*, with the first break minute — review fix, finding 2: the first build recorded names that were merely READY to buy, at the hold minute): at 15:55 ET one `breakout_v1_missed_by_slots` audit row per list name held for `slots_full` at least once today, that never got a slot — no trade row today, or only a `skipped` one (no order was ever placed); a cancelled / order_placed / filled row means it had a slot at some point — **and that BROKE OUT after the hold**: the held-never-seated names are added to the 15:55 batched bars read and `first_break` (PURE) finds the first minute k at/after the first hold's minute whose bar high reached the level **AND whose volume pace held at that minute** — `f1_permits(the volume through minute k-1, the list row's vol_bar, k-1)`, exactly the check the live tick makes at minute k before it places or keeps the buy that would have filled in that minute (re-review fix 2026-11-07, finding 1: the first fix checked the level only, so a name whose volume dried up after the hold and then touched its level — a buy that would have been cancelled `setup:breakout_volume_below_curve` long before — was written as a miss; both halves of his ruling, *level + volume pace*, are now met); a held name that never traded at its level, or touched it only on lapsed volume, writes nothing (nothing would have filled); a later touch back on pace is the break. The detail JSON: `ticker`, `day`, `minute` + `clock_et` (THE BREAK), `break_high`, `break_price` (the level the buy would have rested at), `stop` (the day's low through the break minute, on the cent — the resting buy was re-priced to each new low until the fill, so this is the stop it would have carried) + `width`, `break_cum_volume` / `break_need_volume` (the pace at the break: through the minute before, against the curve there), `hold_minute` / `hold_clock_et` / `stop_at_hold` (the first hold), `list_rank`, `order_score`, `cum_volume` / `need_volume` (the pace at the hold), `vol_bar` and `adr20` from the list row (so #720 applies the width filter without a join), `reason` = `slots_full`, `row_status`. The holds are read back from the audit log BEFORE the bars read (restart-safe: a restart between the hold and 15:55 loses no name; a second hold row after a restart does not move the first hold minute). **A hold note is marked written only when the audit log confirms the row** (`log_audit_event` now answers True / False; re-review fix 2026-11-07, finding 4 — it used to mark the name noted BEFORE a write that swallows its own failures, so a hold whose first write timed out dropped out of the 15:55 record for good): a swallowed write is retried on the next tick, and the record's first hold is then the first hold WRITTEN (one minute later than attempted); the 15:55 count is the number of missed records that EXIST — a swallowed record write is not counted and is lost unless a restart inside the misfire grace re-runs the 15:55 minute (there is no later tick). Only `slots_full` notes are retried — the other states are marked noted whether or not the write landed, so a slow audit log does not make every tick re-write ~350 `wait` notes (final review finding 2). Idempotent on a re-run of the 15:55 minute; an unreadable hold log writes nothing, audits `breakout_v1_missed_unreadable` and pages (paper-prefixed); a candidate whose bars were NOT read at 15:55 (its chunk failed) is never judged "never broke" on an absence — audited + paged the same way, nothing written for it. Query for the review: `SELECT detail::jsonb FROM mi_audit_log WHERE event_type = 'breakout_v1_missed_by_slots'`; #720 joins daily bars on `ticker` / `day` / `break_price` / `stop` against the names we did seat.
- The 17:55 message drops its `/bgrade` line and no longer says "(list and grades only)" — it says nothing about grading (grades come from chart sheets in chat); "No order is placed from this message." The command stays (`agent.py`, `channels/telegram.py`, the preflight registrations — untouched; no orchestrator deploy). `db.bv1_get_list`'s SELECT (it reads `order_score` since stage 2) is registered in `scripts/preflight_db_updates.py` like `bv1_ungraded`'s, so a schema without the column fails the deploy gate, not the first 09:35 tick (review fix, finding 5).
- Tests: `tests/test_breakout_v1_entry.py` §9 — 24 (the 350-name tick is one batch call and no per-name call; the chunking 2 / 14; a raised chunk leaves its names absent; **a hung chunk ends the batch for the tick while a fast failure does not**; shape parity with the per-name read; **3 straight unread ticks page once and an answered tick resets**; slots by rank with the overflow held (the hold row's free count 0, 2 seated) and no skipped row; a held name enters once a slot frees; hold-only pinned; lane rows count and are untouched; the count is the funnel's SQL once a tick; **the `max_positions` race holds the rest AND the blocked name, which 15:55 records when it broke out**; **a breakout cap on the strategy row takes the smaller of the two caps and its block holds the rest**; **the list read is the registered prepare copy**; an unreadable count holds all under its own state and is never recorded, a blip followed by a full book records from the `slots_full` hold, and the pre-flight runs once; **`first_break` (PURE): at/after the hold, the first high at the level, the stop = the low through the break minute**; **his test: a 7-name break day (every name trades above its level) with 5 free slots records exactly the 2 lowest-ranked names, once each, at their BREAK minutes — an 8th eligible name that never traded at its level is NOT recorded**; a later-seated name is not recorded while a skipped-only one that broke out is; the records survive a restart, and bars or a log unreadable at 15:55 page rather than write; zero batched requests with the switch off; no writer of the paper switch anywhere; **re-review 2026-11-07: `first_break` needs the pace at the break minute exactly as the live tick applies it (through the minute before; the break minute's own volume never counts; a touch on lapsed volume is skipped and a later touch on pace is the break; the volume half cannot be left off); the reviewer's repro — a name held on pace whose volume dried up and then traded above its level at 15:20 with 634,000 shares against the 743,000 the curve needs — is NOT recorded while a name on pace at the same minute IS, with that minute, the level and `adr20`; a hung bars page holds only the batch's own thread (`alpaca-bars-batch`), the next call is skipped with nothing submitted while it is in flight, the shared pool never carries a page, and it clears when the page returns; a tick whose batch is in flight reads nothing, writes the in-flight row, counts toward the 3-straight page and reads normally once it clears; a hold write the audit log swallowed is retried next tick and the name is still recorded at 15:55 from its first WRITTEN hold; the 15:55 count counts only the records written and a re-run writes the swallowed one**) + `tests/test_breakout_v1_list.py` (no `/bgrade` and no grading in the message; the command's three places and bare `/bgrade` unchanged). Each review-fix test was run against the pre-fix code first and failed there (12 failed), then passed after the fix; the entry + list + feed + stage-1 + parity suites: 162 passed; the full `tests/` suite: see the commit.

**Anticipated effect**: DARK while `breakout_v1_paper` is off (every `breakout_v1_entry` run returns `switched_off` before the batched bars read; the fill check still fetches one name's bars per call when a filled breakout row exists — none today — so "0 bars requests while off" means 0 BATCHED requests). `breakout_v1_missed_by_slots` rows: 0 while the switch is off. Once he turns it on (stage 3): bars requests a minute fall from one per name to ≤ 14 at 350 names; on a day with more eligible names than free slots, `slots_full` hold rows > 0 and **0 `block:max_positions` skipped rows for `breakout_v1`, except one per minute in which a same-moment lane entry raced; that name also has a `slots_full` hold row** (the old code wrote one per overflow name — the discriminator); every placed breakout name's rank ≤ every held name's that minute; abstain `skipped` rows scale with the list (~100 a day at 350); at 15:55 one `breakout_v1_missed_by_slots` row per name that broke out — its high at the level WITH the volume pace held at that minute — while held and never got a slot (0 on a day with no more eligible names than free slots, 0 for a held name that never traded at its level, and 0 for one that touched it only on lapsed volume); the Monday 17:55 message carries no `/bgrade` and no "grades".

**Reversion-flag**: REFINEMENT of the 2026-10-29 PHASE 2 entry (the slots were the funnel's first-to-break with a terminal skip) and of the 2026-10-30 part A build (the per-name fetch). Known limitation (c) above CLOSED; (b)'s slot question answered by his rulings.

**Status**: built 2026-11-07, reviewed the same day (six findings, all fixed above — the suite had been red on two of them: a source-pin baseline the new T10 test outgrew, refreshed; and the batch request's `feed=` passed through a variable, which the feed-resolver gate rejects — now `feed=get_data_feed()` in the request) and re-reviewed the same day (four findings, all fixed above: the missed record now needs the volume pace at the break, not the level alone; the bars batch runs on its own single thread and a tick skips its batch while the previous page is still in flight; the stage-3 expectation allows the one `block:max_positions` row the disclosed race writes; a hold note is marked written only when the audit log confirms it, and the 15:55 count counts only the records written), DEPLOYED DARK 2026-11-07 on his "Go" (`deploy.sh market-agent && deploy.sh execution`, both preflights PASS, server `359fa1d7`; `breakout_v1_paper` read back OFF); the D8 probe met its bar (Fri 11-06's 184 names in 8 requests, 3.1 s, 0 absent; `scripts/probes/_717_d8_1107/d8.out`); EXPECT-STAGE2 on PLAN #717 (filed before the ship); field validation = Mon 11-09's list message and entry runs, and stage 3 when he turns the switch on. Disclosed, not built for: the funnel race still writes ONE terminal skipped row for the name it blocks on a same-moment lane entry (the rest of the minute is held, the blocked name gets a hold row so 15:55 can record it; `entry_pipeline.py` not touched); a held name is judged at the later minute's price, so a name that ran away abstains `stop_too_wide` when seated (no late-entry rule added); the 15:55 tick is the one writer of the missed records (a 15:55 tick lost to an overrun loses them, as it loses the `breakout_v1_entry_day` row; and on a day the switch is turned OFF mid-session the 15:55 tick returns `switched_off` before that step, so that day writes none); the missed record's break is "the first bar at/after the hold whose high reached the level with the volume pace held at that minute" — it replays the pace (re-review fix, finding 1) but NOT the width rule after the hold, so a name whose day low fell far enough AFTER the hold that a seated buy would have been cancelled `stop_too_wide` before the break can still be recorded (`width` at the break and the list row's `adr20` are in the row; #720 can filter on it); nor the volume CANCEL: a seated buy whose pace lapses is cancelled `setup:breakout_volume_below_curve` and finished for the day, while a HELD name that lapses, recovers its pace and then touches its level is recorded — so #720 reads the record as an UPPER BOUND on the trades we missed (final review 2026-11-07 finding 3); **a hung bars page still costs the names unread until alpaca-py returns it** (re-review fix 2026-11-07, finding 2: the page runs on the batch's OWN single thread, never the pool every broker call in apollo-execution shares, and every tick that finds that thread still busy skips its batch — `breakout_v1_bars_batch_in_flight`, counted toward the 3-straight page — so stuck threads no longer accumulate, one per hung minute, and the shared pool is never touched — this holds while the breakout tick is the batch's ONE caller (max_instances=1), stated at the flag; what remains is that the whole list goes unjudged, a resting buy left as it is, for as long as the one page hangs, since alpaca-py sets no HTTP timeout) — a per-call HTTP timeout in the data client is the follow-up if the D8 probe shows slow pages; the chunk cap of 200 symbols is a URL-length guess the D8 probe measures on the real endpoint; IEX minute sparsity at 350 names (more `no_opening_range_minutes` abstains than the research saw) is a stage-3 read, not a stage-2 change; `_note` rows and abstain rows scale ~10× with the list (readers are counts only).

### 2026-11-02 — breakout v1's list REBUILT from Qullamaggie's own trades: the 7 list rules, the order score, the 10-day volume bar (OPERATOR-SIGNED: his spec sign-off "signd off", 2026-11-02; stage 1 = the list) — BUILT on branch `breakout-v2-stage1`, NOT deployed

**Trigger**: v1's first paper buy (MTW, 11-02) was not a setup by his read — *"the problem is there's no setup ... we're trying
to implement the breakout setup, we're not trying to buy random stocks and make it profitable"* — and his method the same
day: *"we have all the winner trades from qullamaggie already, it's proven, we need to trade those and that's it"*, *"get as
close as possible, that is the starting point and then work backwards from there to define our rules"*
(`docs/methodology/operator_shared_notes.md` 2026-11-02). v1 then listed **60 of Qullamaggie's 269** dated breakout buys the
night before (22%) and **4 of his 26 big winners**. The spec he signed off: `docs/analysis/cb_rebuild_from_qm_trades_2026-11-02.md`
(*"signd off. What's the effort to build? Can we break up into stages and start some this week?"*, 2026-11-02).

**The change (stage 1, the nightly list — market-agent code; the entry job's per-name loop / slots are stage 2, the stop
and exit unchanged):** the rules in the "Breakout v1 — the nightly LIST rules" block above — strength >= 35 (was 98), the
daily-range floor 2.1% (was 4.26%; the 1% pinned gate kept), the run-up >= 32.1% (was 30%), NEW base depth 1.511-8.980
daily ranges, NEW close >= -0.6335 daily ranges vs the 21-day EMA, NEW close >= the 50-day SMA; REMOVED higher lows,
surf, tightening and the breakdown check; the volume bar 1.2x the LAST 10 sessions (was the 50-day); the list ranked by
the ORDER SCORE (was rs_best); three new columns `order_score`, `runup6m_adr`, `spread10_adr` (`ALTER TABLE ... ADD COLUMN
IF NOT EXISTS`, the deploy's prepare gate registers the changed INSERT and the bare-`/bgrade` SELECT); the 17:55 message
and bare `/bgrade` show the top 10 by the score + the count; the list job loads 200 sessions (was 150 — the 6-month move
needs 189). `broker/breakout_v1_entry.py`: docstrings only (F1 reads `vol_bar` from the row, so the 10-day bar reaches it
through the list).

**Evidence** (every number printed in `scripts/probes/_qm_breakouts_vs_v1_1102/`; no R, P&L or win rate decided any rule):
- **The scorecard, re-run on the LIVE code** (`tests/test_breakout_v2_stage1.py`, fixture `tests/fixtures/qm_breakout_scorecard/`,
  his 269 buys' own bars): **263 of 269 on the list, 26 of 26 big winners, 0 mismatches** with the research result row by row;
  the 6 off are exactly his 6 NOs (YPF 2019-04-17 and MRNA 2021-11-29 on base depth; W 2020-04-07, DOCU 2020-12-04 + 12-15,
  SQM 2021-09-10 on the run-up). The **16 buys he labelled no / EP-like that the list still keeps** are pinned ON as the
  known negatives (ANET 2018-03-12, TDOC 2019-10-31, STNE 2019-11-18, ZS 2020-03-24, EXEL 2020-04-20, SHOP 2020-04-20,
  NVAX 2020-05-12, PLNT 2020-05-26, UAL 2020-05-27, JMIA 2020-11-18, FEAC 2020-11-30, UPST 2021-08-12, FCX 2021-12-07,
  MU 2021-12-21, FCX 2021-12-27, MDB 2021-12-27). **MTW 2026-10-30 is OFF** — on the run-up alone (30.8% < 32.1%).
- **His labels behind the rules** (95 name-nights, 48 ok-or-better / 47 no, never sampled on outcomes): the 11 backward-dropped
  buys, 3 blind sample nights, the 9 EMA21 drops, the 23 sub-70% run-ups, the 29 loose buys (operator_shared_notes 2026-11-02).
  The order score puts his yes above his no 70% of the time (83 labelled names on the list).
- **The order inputs equal the research formula** on all 269 series (the 6-month move bit for bit; the two daily-range
  measures to 1e-12), and the 18 era-B buys read exactly as stage 0 printed them (`stage0/s0.txt`), 11 of 18 firing on the
  10-day bar.
- **Knife edges, stated:** rule 6 sits 1.3e-5 daily ranges under TSLA 2022-04-21's value (-0.6334871); rule 4's low end IS
  LRN 2020-08-05's depth (equality, inclusive). Both are his "ok"/"good" buys and are pinned ON.
- **Stage 0** (2026-11-02, Opus build + blind recount): the live entry replayed on his buy days buys 154 of his 263 listed
  buys with the 10-day bar (143 with the 50-day), 17 of 26 big winners; 2017-24 the list runs a median 249 names a night,
  ~25 breakouts a day.

**Reversion-flag**: **REVERSAL of the 2026-11-02 morning daily-range floor** — that entry (below) read: *"a new gate `adr`
in `breakout_v1.v1_gates` (after `universe`): ADR20 at D ... must be >= `ADR_MIN` = 0.0426. The value is his own
reverse-engineered stock pool (... ADR20 >= 4.26% ...). A pinned deal target sits far below it (ARX 0.25%)"*, with the
evidence *"3,414 of 18,094 placed name-days (19%) fall under the floor; their 919 decisive fills averaged -0.464R"*. **Why it
was wrong (not just incomplete):** it rested on two things — a SELECT rule fitted to a reverse-engineered stock POOL, and
the paper book's R — and neither is the target. His ruling the same day is that a rule is judged on whether the list holds
Qullamaggie's setups, never on returns; and on Qullamaggie's own buys the 4.26% line cuts setups he called GOOD (EW
2019-08-16 at 2.11%, LMT 2022-04-05 / 04-06 at 2.6%). The problem the floor was shipped for — a pinned deal target like
BWMN (0.16%) — is caught by the 1% `pinned` gate his "both" named, which STAYS. **Also a REVERSAL of the 2026-10-29
breakdown check (his "yes" that day) and a REFINEMENT of the 2026-10-28 "v1 FINAL" starting values** (strength 98, the
30% run-up, higher lows / surf / tightening, the 50-day volume): those were *"starting values, refined on paper fills and his
grades"*, fitted to 24 setups of one stream (12 of 24 caught), and the breakdown check to one example (ODD 09-08,
single-case). Wrong as DEFINITIONS: his CODX / PENN drawn charts (11-02) read "higher lows" as lows above a rising line from
the base's bottom (a shakeout allowed) and "surfing" as holding around the 10/21-day EMAs across the base — not v1's
last-5-low and SMA-band counts — and on the scorecard the old set left 209 of his 269 buys off (each rule's share: strength 98 175, surf 69, tightening 56, the 4.26% floor 50, higher lows 47, breakdown 7; `01_gate_misses.txt`). His
ODD 09-08 "no setup" reading is KEPT: the rebuilt ema21 and sma50 rules reject it (`tests/test_breakout_v1_parity.py`).
The 10-day volume bar is his own ruling ("Yes", 11-02).

**Anticipated effect**: the 17:55 ET list goes from ~9-30 names a night (9 on 11-02 under the 4.26% floor; 22-30 before it)
to **~150-350** (median ~250 on 2017-24 history; ~310 on 2022-24); each row carries the order score and its two inputs;
the per-gate fail counts in the `breakout_v1_list_run` audit row carry `base_depth`, `ema21`, `sma50` and no longer
`higher_lows` / `surf` / `tightening` / `breakdown`; 0 listed names under 2.1% daily range; MTW-like slow run-ups (< 32%)
absent; the message shows 10 lines + the count. The paper switch `breakout_v1_paper` stays OFF (no order) — the entry
tick returns on the switch before its per-name loop (verified 11-02), so the longer list costs no broker calls; with the
switch on, today's entry job could not keep up with ~250 names a minute (stage 2, Sat 11-07, batches it and fills the 5
slots by the score). Known miss carried: MRNA and INO 2020-08-07 (his "breaking down") still pass.

**EXPECT** (declared before it ships; BASELINE the 11-02 list: 9 names, none under 4.26%): the 17:55 ET list holds ~150-350
names; each row carries the order score; 0 names under 2.1% daily range; MTW-like slow movers (run-up < 32%) absent.
UNINTENDED, declared: the list now carries names he will call non-setups (the 16 known negatives' kind) — the score orders
them, it does not remove them; bare `/bgrade` can no longer show every ungraded name (top 10 + counts).
**DONE-WHEN:** 5 trading nights of lists with the counts in range and his spot check of one night's top 12 by the order score.
**WOULD-FAIL-IF:** the list stays ~22-30 a night (the old gates still running), or any name under 2.1% daily range appears.

**Status**: BUILT, reviewed, MERGED to main 2026-11-03 (`246996c9`), DEPLOYED 2026-11-04 21:16-21:27 ET on his go (`deploy.sh market-agent` then `deploy.sh execution`, both DEPLOY OK, server `35c646ff`; the 3 list columns exist). First list under these rules: Thu 2026-11-05 17:55 ET, read against the EXPECT above. Deploy plan (the main session's): the list job
is market-agent; `db.py` (the DDL + the INSERT) is also on `scripts/exec_loaded_modules.txt`, so the scope is the main
session's call. The paper switch stays off until his word (stage 3).

### 2026-11-02 — breakout v1's list gains a DAILY-RANGE FLOOR: ADR20 >= 4.26% (OPERATOR-SIGNED "yes to both", 2026-11-02; paper only — no live order path)

**Trigger**: his catch on the first paper morning — *"bwmn is clearly a buyout candidate"*: BWMN (Bernhard Capital's $43 cash buyout, signed 2026-08-10) traded $42.88-42.91 in its opening range and v1 placed a buy at $42.95 on a 7-cent stop (cancelled at 09:49 by its own volume pace). The same night's 27-name list also carried PCRX (Viatris deal; our EP M&A filter blocked it 10-29) and ARX (ADR20 0.25%; blocked by the M&A filter in August). v1 had no deal-target check of its own; a pinned deal target is not a breakout.

**The rule**: a new gate `adr` in `breakout_v1.v1_gates` (after `universe`): ADR20 at D (the mean of (high-low)/close over the 20 sessions ending D, v1's own `adr20_at`) must be >= `ADR_MIN` = 0.0426. The value is his own reverse-engineered stock pool (`docs/analysis/cb_reverse_engineer_his_rules_prereg_2026-10-24.md` L814: ADR20 >= 4.26%, not down > 5.8% over 60 sessions, a 52-week high within 233 sessions — the SELECT rule that PASSED on 2021-22). A pinned deal target sits far below it (ARX 0.25%).

**Evidence**: backtest on the frozen 2017-2024 paper-baseline replay (`scripts/probes/_breakout_v1_replay_1101/adr_floor_1102/adr_floor_effect.txt`, before the code shipped): 3,414 of 18,094 placed name-days (19%) fall under the floor; their 919 decisive fills averaged -0.464R. With the floor, the paper book (5 slots, 2c): 2017-21 -0.153 -> -0.139R, 2022-24 -0.412 -> -0.340R; no slot limit: 2017-21 -0.047 -> +0.001R, 2022-24 -0.326 -> -0.252R. Cost: 9 of the 63 10R+ trades are below the floor. N >> 10, both eras the same direction. Tests `tests/test_breakout_v1_adr_floor.py` (the gate named and ordered, a pinned series fails, a mover passes, 4.25% fails / 4.27% passes); the v1 list / parity / entry / fund suites unchanged (131).

**Anticipated effect**: the 17:55 ET list loses its pinned and low-volatility names (~19% fewer rows on history; ARX, BWMN-like names); the list audit row's per-gate fail counts carry an `adr` count; nothing else in the entry or exit changes.

**His "both" (2026-11-02, after the list check below)**: ALSO a named PINNED-DEAL gate `pinned`, ADR20 >= 1% (`PINNED_ADR_MAX`), before `adr`. On the 11-02 list (scan 10-30, `scripts/probes/_verify_1102/q6_list_baseline.out`) 12 of 27 names sat under 4.26%: the three deal targets at 0.16% (BWMN) / 0.25% (ARX) / 0.73% (PCRX) and nine ordinary low-range names at 2.9-4.1% (incl. MTW, the first paper buy, 4.06%). The 4.26% floor contains the 1% rule, so the LIST is the same; the two gates name WHY a name is out (a deal-pinned stock vs a slow mover) in the per-gate counts.

**Reversion-flag**: NEW.

**Status**: shipped, awaiting field validation — deploy Mon 11-02 12:00-13:00 ET (market-agent, where the 17:55 list job runs; batched with the 11-01 simplify + the M&A sweep fix, then execution). VERIFY-LIVE: the 11-02 17:55 ET list's audit row shows `pinned` and `adr` fail counts > 0 and no listed name with ADR20 < 4.26%. WOULD-FAIL-IF: a listed name with ADR20 < 4.26%, or no `pinned` / `adr` key in the per-gate counts. ⚠ The frozen C replay and template grid pinned `breakout_v1.py`; they reproduce at their freeze commits (`e2c7938d`, `087e0908`), not on HEAD.
⚠ **REVERSED the same day by the rebuild entry above** (the floor becomes 2.1%; the 1% `pinned` gate stays) — that change is BUILT on a branch, not deployed: until it deploys, production runs THIS entry's 4.26% floor.

### 2026-11-01 — breakout v1 studies on the frozen 2017-2024 replay: the paper baseline FAIL, the path to his template FAIL in every step, the spot-check of his 28 biggest buys (RESEARCH ONLY — no rule changed; any change is his call)

Moved here from the #717 PLAN line at the 11-01 CLOSE (the line keeps one pointer). Each study was registered and frozen before its data, run once and verified (a recount + an adversarial audit) before it was reported; vault `tests/717_paper_baseline_replay.md`, `tests/717_big_winners_and_book_fixes.md`, `tests/717_template_grid.md`, `tests/717_his_big_winners_vs_v1.md`.

- 📉 **11-01 THE PAPER BASELINE (task C, his 10-28 weekend list) — FAIL:** breakout v1 replayed 2017-2024 on the paper lane's own rules (frozen `e2c7938d`, the live v1 code called, run once, recount MATCH, adversarial audit: no loss-side defect): 1,639 trades -0.245R [-0.38, -0.09] at 2c with 5 slots, 4.6% at 3R+ (bar 8%); break-even uncapped with no costs; the top-ranked names take the slots and read worse (ranks 1-5 -0.16R vs 11-40 +0.04/+0.13R). `docs/analysis/breakout_v1_paper_replay_prereg_2026-11-01.md`; vault `tests/717_paper_baseline_replay.md`. Paper runs as built (no money); the yardstick says expect a loss; any rule change is his call, tested on the frozen replay first.
- 🧭 **11-01 THE PATH TO HIS TEMPLATE (his 'Ok' + 'Aligned'), frozen `087e0908`, run once, verified (Opus recount + adversarial):** FAIL in every step — exit C (speed trail, no partial) / + the 15c floor / + strength 90 / slots 8-10, best 2022-24 -0.131R; exit C matches his average win (+4.7R) but halves the win rate; the gap is the count of 5R+ winners (his 13.7 per 100 vs ours 3.5-4.8 under every exit). Next lever (held fixed so far): the entry + the day-low stop (a third of trades exit on the buy day). `docs/analysis/breakout_v1_template_grid_prereg_2026-11-01.md`; vault `tests/717_template_grid.md`.
- 🔍 **11-01 SPOT-CHECK, his 28 biggest buys (5R+ when his buy is replayed with OUR exit — not his own results) vs v1 (his ask; builder + blind reader + reconcile, `scripts/probes/_breakout_v1_replay_1101/qm_vs_v1_1101/SUMMARY.md`):** 4 of 28 on v1's list on his night, 0 matched with the 5-slot book; the strength and shape misses look the same on his winners and losers (61% vs 62%, 54% vs 48%) — loosening them adds losers; candidates for his ruling: the buy level at the prior day's high (v1 above his point on 43% of his winners vs 28% of losers), skip the day after a wide up day (v1's 489 such trades lost 68%). Vault `tests/717_his_big_winners_vs_v1.md`.

### 2026-10-30 — breakout v1 PHASE 1 LIVE: the first night's list (DEPLOYED 10-30 12:00-12:08 ET, server `7acfed65`)

17:55 ET (`scripts/probes/_bv1_first_night_1030/q1.out`): `breakout_v1_list_run` written, **27 names** on the list of a 4,097-name RS pool (2,814 listable, 2,801 with history), every stored row's gates all pass, the paper-chat message sent; 17:00 stored Polygon names for 13,257 of 14,202 security rows; funds kept 39, excluded 15 (leveraged / inverse 8, basket 4, two underlyings 2, no known underlying 1; 0 for a missing name); ZCSH listed (rank 2, rs 99.9). Gate fails: rs 2,654 · prior move 2,026 · surf 1,872 · breakdown 995 · tightening 960 · higher lows 791.
⚠ **THE EXPECT'S "about 4 names a night" WAS WRONG — corrected, not a defect of the build:** the 2020 check's ~3.7 a night counted FIRES (the watch night's gates AND the next session's level break on 1.2x volume); this table is the WATCH LIST — the setups that could break out next session — so it runs several times the fire count. A second, smaller push: ruling (a)'s pool carries ~1,500 rank-only funds/ETFs today (vs ~550 in the 2020 data), so stocks clear 98 slightly more easily. Re-read the count with the fires once the paper entry (phase 2) runs; the ceiling question goes to him only if the list is too long to grade.

### 2026-10-29 — breakout v1 PHASE 2 BUILT (the paper buy + the pp exit) — MERGED to main 2026-10-31 (`c4ebc727`) — DEPLOYED 2026-10-31 on his "Allow deploy" (server `17853040`, `both` then `execution`, DEPLOY OK x2, 0 tracebacks; #717, first paper buys Mon 11-02) — his three rulings applied (the stop at the fill; only a third that FILLED counts; the unfilled +2R third cancelled and sold on session 3, the stop held until a third sells)

The two builders' entries follow as written (entry, then exit), after a four-lens review and one fix round (13,140 passed). Deploys only after the main loop's own read of the shared-code diffs.

**HIS RULINGS 2026-10-29 ("Go with rec" — verbatim: `docs/methodology/operator_shared_notes.md`, the last entry), BUILT on the branch the same day — DEPLOYED 2026-10-31 with phase 2 (server `17853040`, #717):**

**(1) THE STOP AT THE FILL** (answers reading 2 of part A). One minute after a fill — the first `breakout_v1_entry` tick whose last completed minute is the fill minute (the BROKER's fill time; the row's `filled_at` is the stream's clock) — the TRUE low of the day through the fill minute is read from the minute bars:
- `cb._finish_entry`'s width rule fails on it — (fill − true low) > ADR20 × fill, on the raw low — → the WHOLE position is sold at once (paper, market: `order_manager.execute_full_exit`, reason `setup:stop_too_wide_after_fill`), paged paper-prefixed;
- otherwise, the true low below the placed stop → the protective stop leg is LOWERED to the cent at or below it (an atomic price-only replace of the OTO stop leg — `scan_breakeven_arms`' shape: the live leg read first, the successor confirmed live before the row says so, a dead stop re-protected through the coverage invariant). The row then carries the new `stop_order_id`, `stop_price` AND `hard_stop` (so the pp exit's R, its +2R target and its stall cut use the walk's stop) and `risk_dollars_actual` = shares × (fill − new stop) — the dollar risk may sit above the sized `risk_dollars`; both are in the `breakout_v1_stop_lowered_after_fill` audit row. Never raised; never under a third sold or pending, nor under a stop already at/above the fill;
- otherwise nothing changes.
Exactly once per trade: the marker `breakout_v1_fill_stop_checked` (an audit row naming the trade and its decision — `lowered` / `sold` / `kept` / `superseded_*` / `stopped_before_check` / `not_checkable` / `closed_before_sale` / `sale_pending`) is written AFTER the step; a tick after a crash re-decides from broker truth (a leg already at the new price is only recorded; a sale already pending or a row already closed is only marked). The row's `stop_order_id` moves to the successor the moment the replace returns (before the verify polls — Alpaca marks the old leg `replaced` on accept); a leg that still reads `replaced` (a crash before that write, or a replace call that raised after the broker took it) is resolved by adopting the ONE live sell-stop in this strategy's order-id family covering the shares (`breakout_v1_fill_stop_successor_adopted`), recorded the next minute — 0 or >1 candidates: nothing guessed, audited, retried; never a re-protect against a live successor. A rejected lower keeps the old stop, pages once, retries next minute. A partly filled entry waits until it is complete. The fill-minute bar not yet published: waits up to 3 minutes, then judges without it (`fill_bar_seen: false`; the fill price bounds the low). Runs with the breakout switch OFF too (it is the position's stop, like the exit jobs), never on a refused phase. Only `breakout_v1` PAPER rows (guarded again in the step and in the CAS write). One new writer, `breakout_v1_entry._record_stop_lowered` (registered in `scripts/audit_column_writes.py`, its SQL copied in `scripts/preflight_db_updates.py`, pinned). **Disclosed:** a fill in the 15:55 minute (a race with the EOD cancel) has no tick after it — it is audited `breakout_v1_fill_stop_unchecked` and paged, not checked. A 5-minute +2R poll that runs between the fill and the check uses the tighter placed stop's target for that one poll.

**(2) THE FIRST THIRD AT +2R — FOLLOW WHAT ACTUALLY FILLED** (answers part B's difference 10). "A third sold" is the row's `partial_taken` (flipped TRUE when a partial FILLS) — `breakout_pp_rules.third_sold` — never a daily or minute high at +2R, and no longer the day-0 facts' modelled `partial_price`. So a +2R touch whose resting limit did not fill: the 20-day trail does NOT start before session 3, and **the session-3 third is NOT sold** — it is never sold beside a still-resting +2R third (`session3_decision` → `third_resting`, audited `breakout_pp_session_third_resting`; the open partial is read from `mi_live_orders` with the shared `PENDING_EXIT_TERMINAL_STATUSES`, an unreadable book reads as resting; the shared partial-exit dedup stays the backstop). ⚠ **In practice the session-3 third is never sold after a touch** (review 2026-10-29): on paper the +2R limit is a GTC resting OCO whose trigger (the high since the fill) stays true after the touch, so it is still resting at 15:45 on session 3 unless it filled — the "session-3 third still applies" half of his ruling and the "never two thirds" half cannot both hold while it rests. On the builder's fuzz: 105 unfilled touches, 0 session-3 thirds sold. The fork this left (sell nothing at session 3 while the limit rests, or cancel it and sell the third at the close) is **RULED — (3) below** (cancel and sell); the placement-time breakeven this paragraph described is **REPLACED by (3)(ii)**. The 16:45 stop-to-cost backstop reads `partial_taken`. **The equality test is now two-sided** (`tests/test_breakout_pp_exit.py`): on every path where the limit fills in the touching session (`LIMIT_AT_TOUCH`) live equals `walk_pp` event for event (500 fuzz paths, the scenario tails, the long horizons); on paths where an intrabar touch does not fill (`LIMIT_NEXT_TOUCH`: it fills on the next session that reaches the target, or never) the DEFINED divergence is asserted rule by rule — the events before the touch are the walk's; at the touch no third, the limit rests and the stop goes to cost; a third is booked only when it fills, after the touch, at or above the target; no trail sale before session 3 without a filled third; no session-3 third beside the resting one ('third_resting' whenever that close is above the fill). On that fuzz: 300 paths with no touch and 95 gap-open touches equal the walk; 105 unfilled touches all diverge as defined (5 later fills, 2 `third_resting`, 2 where the walk trailed before session 3 and live did not). Mutation-checked (a session-3 third beside a resting one, or a trail live from session 1, fails it).

**(3) THE UNFILLED +2R THIRD — HIS RULING 2026-10-29 late ("Friday, and option a"; verbatim: `docs/methodology/operator_shared_notes.md`, the last entry), BUILT on the branch the same night (not deployed).** He chose the cancel-and-sell reading of the fork in (2) — "option a" in the message put to him, which is NOT the "(a) as built" lettering of (2) above:
- **(i) session 3, the close above the fill, the +2R limit still resting unfilled** → `session3_decision` returns `cancel_resting_third` (was `third_resting`); the 15:45 step (`live_tracker._breakout_pp_session3`) writes the marker `breakout_pp_planned_third_cancel` (trade + order) FIRST, cancels the limit, and waits ~3 s for the broker to confirm (`breakout_pp_exit.cancel_resting_third`). Then exactly one of: **dead, nothing filled** → the order row is closed (compare-and-set, so the shared partial-exit dedup sees no open third) and the third — the cancelled limit's OWN size — is sold at the 15:45 price through `execute_partial_exit` (market; audit `breakout_pp_third_cancelled_for_session_third` then `breakout_pp_session_third`); **filled, in full or in part, in the race** → that fill IS the third, nothing more is sold (`breakout_pp_third_filled_in_race`; the trade stream books the fill and re-protects any unfilled rest, unchanged); **still live / refused / unreadable / no order id** → nothing sold, audited `breakout_pp_third_cancel_unconfirmed` and paged. A sale that fails after a confirmed cancel re-protects the third's shares from broker truth (`reprotect_after_unsold_third` → the shared `_ensure_stop_coverage`; `breakout_pp_session_third_unsold_reprotected` + page). **One third ever:** once the marker exists, `scan_profit_triggers` never re-places a +2R limit on that trade (`breakout_pp_third_cancelled_no_replace`; read only for `breakout_v1` rows), and the trade stream leaves a MARKED cancel with NOTHING filled alone (`breakout_pp_planned_third_cancel_seen`, read only for a `_breakout_v1_` order id) — otherwise its re-protect would put a stop on the very shares the step is selling. At or under the fill on session 3 a resting limit is left alone (nothing sold).
- **(ii) the stop stays where it was until a third ACTUALLY sells** → on a `breakout_pp` row `execute_partial_exit` never moves the stop: the #548 resting-mode Step 2b (the 2/3's price-only replace to breakeven), the third's OCO sibling stop (at the CURRENT stop, not max(stop, entry)) and the market-mode fold-in are each skipped behind `exit_rule == 'breakout_pp'` (audit `breakout_pp_stop_held_at_placement`). When a third FILLS IN FULL, `order_manager.finalize_partial_exit` raises the stop on the rest to the fill (`update_stop(.., entry, 'breakeven')`, raise-only, after the advisory lock; audit `breakout_pp_stop_to_fill_after_third`; a failure is audited/paged and never raises into the fill handler); a partly filled order is left to the stream's cancel re-protect (`breakout_pp_stop_to_fill_deferred`). The 16:45 job lifts a stop still under the fill once `partial_taken` (now also on the breakout day itself).
- **EP magna53, the small-cap lane and 9M rows are unchanged**: every new branch is behind `exit_rule == 'breakout_pp'`, `signal_type == 'breakout_v1'` or a `_breakout_v1_` order id (an EP row's placement still moves its stop to breakeven, its OCO sibling sits at max(stop, entry), its fill takes no extra step and no extra read, its cancels re-protect as before — pinned in `tests/test_breakout_pp_option_a.py` beside the unchanged #548 / #566 / partial-exit suites).
- **Disclosed, not built for:** the stop move after a third's fill runs INLINE in the trade stream's fill handler (`update_stop`: cancel, place, verify — a few seconds), so other fill events on the paper stream wait behind it on those few breakout fills (paper only; the plain partial-cancel restore already does broker calls inline); ~~a cancel the broker accepts but does not confirm inside ~3 s, then settles later, leaves the third without its OCO stop (the marker keeps the stream from re-protecting) until the 5-minute coverage repair (to 15:55 ET) — paged at the time~~ (CLOSED by the pre-merge pass 2026-10-31, (A) below: the marker is withdrawn and cover converged from broker truth at once); the cancel-and-sell is decided on the 15:45 price (difference 3); a 5-minute +2R poll in the seconds around the cancel cannot re-place the limit — before the cancel the resting limit blocks it (the shared partial-exit dedup), from the marker on the marker does.
- **The equality harness** (`tests/test_breakout_pp_exit.py`): placing the limit no longer emits `stop_to`; the stop moves only in the session a third sold (D6, asserted on every path of both models, with at most one third ever); an unfilled day-0 touch walks the rest of the breakout day's minutes against the ORIGINAL stop; D5 = on session 3 with the limit resting and the close above the fill, `limit_cancelled` then `partial` at that close then `stop_to` (and no later +2R third). `LIMIT_AT_TOUCH` paths still equal `walk_pp` event for event. Mutation-checked: removing any of the seven new gates, or either EP-isolation filter (the poll's `breakout_v1` check, the stream's `_breakout_v1_` order-id check), fails a test.

**PRE-MERGE PASS 2026-10-31 (merged 2026-10-31) — the option-(a) review's 7 lows + the advisor's 3 items (`scripts/probes/_breakout_v1_phase2/low_findings_option_a_review_1029.jsonl`), fixed. No rule moved: the entry, the exit, the sizing and his rulings (1)–(3) above are as written; every change in shared code is behind `exit_rule == 'breakout_pp'` / `signal_type == 'breakout_v1'` / a `_breakout_v1_` order id, and the EP / small-cap / 9M pins in `tests/test_breakout_pp_option_a.py` still hold. 13,231 passed, 44 skipped (the full `tests/` suite, `scripts/probes/_breakout_v1_phase2/premerge_1031/full_suite.out`).**
- **(A) The unstopped-third window is CLOSED (findings 1, 2 + advisor item 1 — one defect).** The "Disclosed, not built for" line above said a cancel the broker accepts but does not confirm in ~3 s leaves the third without its OCO stop until the 5-minute coverage repair; and a sibling STOP-leg fill during the cancel read as a 'dead' parent (cancelled, 0 filled) and sold a SECOND third. Now (`breakout_pp_exit.cancel_resting_third`): the parent AND its OCO sibling stop leg are read (the leg id from the stored OCO row's `raw_response`, else the live read's legs): a limit fill in the race is the third (`breakout_pp_third_filled_in_race`, as before); a **stop-leg fill is the third sold at its stop** — nothing more sold, the parent's row closed, audited `breakout_pp_third_stopped_in_race`; a dead parent whose leg will not read sells nothing (a second third is the worse error). **CONFIRM-OR-REPLACE, idempotent on a late settle:** when the cancel ends 'open' / 'unknown' after the wait, or the dead order's row could not be closed (two attempts), the step (i) **withdraws** the stream's "leave this cancel alone" (`breakout_pp_planned_third_cancel_withdrawn`, trade + order; `planned_third_cancel_marked` reads the NEWEST of marker / withdrawal, so a cancel that settles LATER is an ordinary OCO-parent cancel to the stream → `_handle_oco_parent_cancel` → `_ensure_stop_coverage` from broker truth), and (ii) converges cover itself at once (`reprotect_after_unsold_third` → the shared `_ensure_stop_coverage`) — a NO-OP while the limit really rests (its open order row nets the third out of the target; the held leg is hidden from the open-orders read), so no second stop is ever placed on top of a live OCO leg (two sells for one third), and the cover when the settle already raced the withdrawal. The row-close failure path closes the dead row once more inside the re-protect first, so `get_pending_exit_qty` stops counting a dead order as cover. The read-before-withdraw order holds (a settle seen on the last read is the ordinary sale). Pinned: the deadline settle (handed back + covered + the stream's late-settle re-protect with the real reader + `_ensure_stop_coverage_outcome` placing nothing when the live stop already meets the target), the stop-leg fill (stored-row and nested-read leg ids; the held-leg control still sells the third), the unreadable leg, the row-close failure (three CAS attempts, no sale, covered), and that a cancel the step never sent withdraws and covers nothing.
- **(B) Finding 3:** every confirmation read is `get_order(.., timeout=3.0)` (`CANCEL_READ_TIMEOUT_S` ≤ 5 s, pinned) under a wall-clock deadline `CANCEL_DEADLINE_S` = 8 s (`time.monotonic`; `CANCEL_POLL_ATTEMPTS` = 24 is the read cap) — the session-3 sale goes out at 15:45, never at the close. The cancel REQUEST itself keeps the SDK's 45 s write timeout (`alpaca_client.cancel_order` takes none; not changed here).
- **(C) Finding 4:** the +2R poll's marker read **fails CLOSED** (`third_replacement_banned`: any marker row — withdrawn or not — or an unreadable log → no +2R limit this poll; the stream's reader keeps failing OPEN to re-protect). And `execute_partial_exit` re-checks a `breakout_pp` row **under the lock**, on the row it just read: `partial_taken` TRUE (the session-3 market sale or a +2R fill landed between the caller's read and the lock) refuses any further partial; a PLACEMENT (`limit_price` given) is refused once the ban reads True; the session-3 market sale itself (no `limit_price`) runs past its own marker. Audit `breakout_pp_partial_refused_under_lock`. EP rows never read the ban (pinned on the 548/566 harnesses).
- **(D) Finding 5:** `_breakout_pp_stop_to_fill_after_third` reads the third's order row (`qty`, `status`); a `'partially_filled'` row whose cumulative fill == qty (the stream's terminal partial-fill path) is set `'filled'` (compare-and-set, `breakout_pp_third_row_marked_filled`) BEFORE `update_stop`, so the stop on the rest is sized on the whole rest, not remaining minus the third again. A real partial (cum < qty) still defers to the 16:45 lift.
- **(E) Finding 7:** `_finalize_partial_exit_locked -> str | None` (pinned by signature). **Which path pages:** the stream's planned-cancel return (`breakout_pp_planned_third_cancel_seen`) is an AUDIT ROW ONLY — the step is selling those shares and pages itself on failure; the 15:45 unconfirmed / unsold paths PAGE (`breakout_pp_third_cancel_unconfirmed`, `breakout_pp_session_third_unsold_reprotected`), and both now say plainly **"No third was sold today, and the +2R limit will not be re-placed."**
- **(F) Advisor item 2 — `hard_stop` has two writers for breakout rows, by design:** `scripts/audit_column_writes.py`'s registry comment no longer calls it single-writer: `breakout_v1_entry._set_unsubmitted_order` (before the fill, the stop re-priced to a new day low) and `_record_stop_lowered` (ONCE after the fill, to the true low, never raised, never beside a third) — ruling (1). The pp exit reads `hard_stop` for R, the +2R target and the stall cut, so a lowered stop changes R mid-trade on purpose. The equality harness now exercises that trade (`TestTheLoweredStopIsTheExitsR`): the replay on the lowered stop equals `walk_pp` on the lowered stop AND differs from the replay on the placed stop on a path where the targets differ (session 1 touches 10.70, not 10.90: a placed-stop third at 10.70 vs the session-3 third at the close); the 15:45 step frames the stall cut on `hard_stop` (not `stop_price` — the columns crossed on purpose: the lowered row is CUT where the placed row sells the third); `ensure_day0_facts` frames the +2R target on `hard_stop`.
- **(G) Advisor item 3 — the 15:55 fill race is checked by the 16:45 pass** (`breakout_v1_entry.check_stop_at_fill_after_close`, called from `update_open_positions_live`'s breakout branch BEFORE the day-0 facts, which read `hard_stop`). Why the 16:45 pass and not the next session's first tick: the minute job's population is TODAY's rows for last night's list, so a row filled the day before is never in it, while the 16:45 pass already visits every open breakout row on its breakout day; and the trade then carries no unchecked stop into session 1. Mechanics: the breakout day's minutes (every minute complete), the same `stop_at_fill_decision`; the stop it lowers is the **16:20 post-close refresh's GTC stop** (the entry's DAY leg expired at the close — `post_close_stop_refresh`), a price-only replace after hours. A pointer still on the dead leg (the refresh missed) is left alone — audited `breakout_v1_fill_stop_unreadable` + `breakout_v1_fill_stop_unchecked_after_close`, paged once, no marker — and is NOT retried: the stop stands as it filled (never wider) — the pass visits ONLY rows FILLED THAT SESSION (the retry pass 2026-10-31 below, change 3; it used to re-visit every open breakout row every evening). Too wide → `execute_full_exit` (a paper market sale after hours fills at the next open). A row already checked costs one marker read. Pinned: the lowered refreshed stop (once, restart-safe), the dead-leg pointer (nothing replaced; not retried), the too-wide sale, the before-the-facts order and the facts on the LOWERED stop.
- **Finding 6 — RULED 2026-10-31 (the retry pass below):** the marker still bans the +2R limit for the life of the trade on the INTENT to cancel; a session-3 third that was decided but did not sell is now RETRIED at each later session's close (his "Retry the sale at the next day's close"), so a trade no longer ends with zero thirds on those paths.
- **EXPECT (for the first session-3 cancel on a paper breakout trade):** one `breakout_pp_planned_third_cancel`, then exactly one of `breakout_pp_third_cancelled_for_session_third` → `breakout_pp_session_third` + a partial exit / `breakout_pp_third_filled_in_race` / `breakout_pp_third_stopped_in_race` / `breakout_pp_third_cancel_unconfirmed` (+ `breakout_pp_planned_third_cancel_withdrawn` and a page saying no third was sold; the broker then shows ONE live sell-stop covering the whole position within the pass, never two); every `get_order` in the step under 3 s; no `breakout_pp_partial_refused_under_lock` on a quiet trade (one means the race fired and was stopped). For the first fill in the 15:55 minute: a `breakout_v1_fill_stop_checked` row from the 16:45 pass (decision `lowered` with the replaced GTC stop at the true low, or `kept` / `sold`) BEFORE that evening's `breakout_pp_day0_facts`. **WOULD-FAIL-IF:** two partial exits on one breakout trade; a `breakout_pp_third_cancel_unconfirmed` with no withdrawal row and no coverage read; a breakout trade past +2R with no partial placed and `breakout_pp_marker_unreadable` rows for it (the fail-closed read is FAILING, not a ban — the unintended consequence of (C), now a durable audit row rather than a log line); a `breakout_v1_stop_lower_rejected` audited by the 16:45 pass (the broker did not take the after-hours price-only replace of the GTC stop — the assumption (G) rests on; the check must then move to the next session's first minutes, not built — until then the stop stands as filled, not retried, which its page now says); a bare stop placed while the OCO still rests (two live sell-stops on the ticker); a stop-leg fill followed by a session-3 sale; a 16:45 `breakout_pp_day0_facts` whose `stop` differs from the row's `hard_stop` after a `lowered` check.

**RETRY PASS 2026-10-31 (merged 2026-10-31) — HIS RULING on finding 6, plus the two review lows of the pre-merge pass.** The exchange, verbatim — my recommendation: *"Retry the sale at the next day's close"*; his reply: *"Go with rec on both"*. Built the same day (`scripts/probes/_breakout_v1_phase2/retry_1031/`): 13 new tests + 1 rewritten, the three breakout suites 182 passed; the full `tests/` suite in `retry_1031/full_suite.out`. No rule moved; every shared-code change is behind `exit_rule == 'breakout_pp'` / `signal_type == 'breakout_v1'` (the EP / small-cap / 9M pins in `tests/test_breakout_pp_option_a.py` hold).
- **(1) THE RETRY — "one third per trade, ever" now means one, not at most one.** The 15:45 step records the DECISION to sell the session-3 third the moment it is made — the close above the fill, no third sold — BEFORE any cancel or sale (`breakout_pp_session_third_due`, trade + price + whether a limit rested). On sessions 4, 5, … the SAME step (`live_tracker._breakout_pp_third_retry`, reached from `_breakout_pp_session3` when `len(fwd) > 3`) reads that record back from the DB (`breakout_pp_exit.session_third_due`: the due row, the planned-cancel marker or the "selling N sh" row — any one proves the decision; an unreadable log reads as NOT due, audited `breakout_pp_third_due_unreadable`, nothing sold that session) and, while the trade is open and `partial_taken` is FALSE, retries the sale at that session's close through the ONE sell path session 3 uses (`_breakout_pp_sell_third`): a partial-exit order still resting — the +2R limit left past session 3, or a session-3 sale that never settled — is cancelled first with the (A) discipline (the marker, bounded reads, the sibling stop leg read, confirm-or-replace: a limit fill in the race IS the third, a stop-leg fill is the third sold at its stop, dead → its own size sold at the close, unconfirmed → nothing sold, marker withdrawn, cover converged, retried at the next close); nothing resting → a third of the shares held sold at market. **One third ever:** a +2R limit that fills before the step flips `partial_taken` (the stream) and the retry never starts — no read of the book, nothing cancelled; a fill that lands between the step's row read and the sale's lock is refused by (C)'s re-check under the lock. **The flag is not the whole truth (the advisor's final-review finding, fixed before commit):** the third's OCO STOP leg filling is the third sold at its stop, but the stop-fill finalizer (`_finalize_stop_fill_locked`) only decrements `remaining_shares` and books a `stop_hit` exit — `partial_taken` stays FALSE — so a retry reading the flag alone would have sold a SECOND third the next session. The session-3 step and the retry now read `breakout_pp_exit.shares_already_sold` beside the flag: a booked exit with shares on the OPEN row (nothing but a sold third, its stop leg or the reduced 2/3 stop ever books one), or a filled / partly filled `partial_exit` / `stop_loss` order row the stream has not booked yet → nothing sold, nothing cancelled, no retry (session 3 audits `breakout_pp_third_already_sold` once; a third left resting under its OCO closes when its own leg fills — difference 10's terminal state); an unreadable book reads as sold (fail closed, `breakout_pp_shares_sold_unreadable`). The fuzz now models the stop-leg fill the way the finalizer books it (an exit, no flag). **Neither is the whole truth either (the review of this pass, 2026-10-31, medium — fixed on the branch):** a session-3 market sale the broker ACCEPTED whose order row was never written (the `mi_live_orders` INSERT raised after the place — `execute_partial_exit` audits `partial_exit_sell_failed` and returns False; or the process restarted between the two) fills as an **'Untracked SELL'** the stream books nowhere (no row to claim: `partial_taken` FALSE, `exits` empty), and the 16:05 sync then lowers `remaining_shares` alone (`sync_qty_overwrite`: a quantity, no exit) — the next session's retry read all three and sold a SECOND third. The reader now also compares **the row's own share counts** — `remaining_shares` below `entry_shares` (both are set to the FILLED quantity at the entry fill, by the stream and the polling backup alike; an entry partial fill is visibility-only — so on an open row with no flag and no exit a gap is a sale the books never recorded: the synced state) — and, last, **the broker's position**: `qty` (what is HELD — never `qty_available`, which a resting +2R OCO lowers by reserving its shares) below the row's count (the same afternoon, before the sync); no position read — gone, or unreadable (the client answers None to both) — reads as sold, fail closed, audited `breakout_pp_shares_sold_unreadable`. Either read firing writes **`breakout_pp_shares_left_unbooked`** (which read, the numbers), and a retry that was DUE but stopped by the wider read now audits `breakout_pp_third_already_sold` with `retry: true` and the `why` (it used to stop silently). Disclosed: the broker read is one `get_position` per open breakout row at 15:45; and a +2R OCO filled in PART (one share of three — the non-terminal partial the stream only observes, #566's unprobed state) now reads as the third already sold at the step (the broker holds fewer than the row): nothing cancelled, nothing sold, the OCO's remainder closes through its own limit or leg — before, the cancel's read treated that one share as the third and cancelled the rest; both hold one third ever, the new reading leaves the rest of the third at +2R. Pinned: the accepted-but-unrecorded sale on session 3 → sessions 4, 5, 6 sell nothing and cancel nothing, from the synced row (`row_counts`) and from the broker before the sync (`broker_position`), with the stopped-retry row; no position read → fail closed; the control (an honest 9-of-9 row with 6 available) still retries; the resting OCO's reservation on session 3 still cancels and sells; the fuzz adds the unrecorded sale after an accepted sale and after a 'refused' one, synced and not, with the broker's position tracking what filled. The marker's ban on RE-PLACING the +2R limit is untouched (`third_replacement_banned` reads the marker alone): the retry is a close sale, never a limit. State from the DB and the broker only (restart-safe). **The retry re-executes the session-3 DECISION and nothing else:** a trade whose session-3 close was at or under the fill (no third due by his rule) is never retried, however high it closes later — pinned; and his rec carried no price condition, so NONE is applied on the retry day (a retry day closing under the fill still sells — pinned as the literal reading; **the one fork he may rule on:** re-apply "only above the fill" on the retry day, a one-line change in `breakout_pp_rules.retry_decision`). Audit: `breakout_pp_third_retry` (the state found) then exactly one of `breakout_pp_third_retry_sold` / `_third_filled` / `_third_stopped` / `_failed` (a retry whose plain sale RAISES is `_failed` with the error + a page, and the pass goes on to the next row; `too_small_to_split` on a 1–2 share position writes `_failed` every session, no page); the inner rows carry `session` + `retry`; the sale page says "day N (retry) … retrying at today's close", and every failure page now says "the sale is retried at the next close" beside "the +2R limit will not be re-placed". Pinned (`tests/test_breakout_pp_exit.py` §8): an unconfirmed session-3 cancel → session 4 sells (the limit still resting: cancelled again, dead, its size sold; settled after session 3: a plain third); a failed session-3 sale (after a cancel, and plain with nothing resting) → session 4 sells; a limit fill on session 4 before the step → no retry sale, and a fill during the retry's cancel is the third; a stuck session-3 MARKET sale is the resting order on session 4 (filled → the third; dead → its size sold); the retry sells with the close under the fill and stops once `partial_taken`; a stop-leg fill of the third (in the race on session 3, in the morning of session 3, and as a filled order row the stream has not booked) sells nothing and retries nothing, and the unreadable book fails closed; a retry whose plain sale raises is audited `_failed`, paged, and the pass goes on; the decision record is written before the cancel and before the plain sale and never on a session 3 that decided nothing; the due reader's three records and its fail-closed read; and a 120-seed fuzz over sessions 3..6 (resting or not, the cancel dead / filled / stop-filled / unconfirmed, the sale ok / refused / raised, the collision's limit landing or not, a sale that fills or sticks, a late settle that cancels / fills / rests) asserting at most ONE third fills, at most one sale and one cancel per session, nothing after a sold third (a stop-leg fill modelled as the finalizer books it: an exit on the row, no flag), and a retry every later session while none has — every outcome of the sell path reached. **Disclosed:** a retry that fails AT THE BROKER every session (a sell that raises, a stop replacement that fails) feeds the per-mode partial-exit circuit breaker like any partial (`_consecutive_partial_exit_failures`; a dedup or under-the-lock refusal does not count) — an open breaker pauses every paper partial exit, the small-cap lane's too, until `/partialnow` closes it (pre-existing semantics; the retry makes daily failure a realistic path).
- **(2) Review low — the 15:45 collision's REVERSE order (`live_tracker` ~1529):** the +2R poll runs at 15:45:00 too; when it placed its OCO between the step's resting read (nothing resting) and the step's sale taking the lock, the shared pending-exit dedup refused the sale, no marker was written, and the limit rested past session 3 unretried. Now a plain sale that returns False is followed by ONE re-read of the book (`resting_third`; the refusal is not distinguishable by return value): a partial-exit order now resting → `breakout_pp_session_third_refused_limit_resting`, the cancel path (the marker, confirm-or-replace) and the third sold, this session; nothing resting → `breakout_pp_session_third_unsold` + a page ("No third was sold today … retried at the next close"), and (1) retries it the next close. Pinned both ways (the second sale is `execute_partial_exit(trade, 3)` after one cancel; the re-read that finds nothing is followed by a session-4 retry that cancels the limit and sells — one third).
- **(2b) Review low (the retry pass, 2026-10-31) — a sale refused because the +2R limit filled first:** the lock's `partial_taken` re-check refuses the close sale, and nothing rests any more. The step now re-reads the flag (`breakout_pp_exit.partial_taken_now`) before calling the third unsold: TRUE = that fill IS the third — audit `breakout_pp_session_third_sold_by_limit`, no 'NOT sold' page, no retry; unreadable keeps the not-sold path (audited, paged, retried at the next close). Test: `test_a_sale_refused_because_the_limit_filled_first_is_the_third_and_never_pages_not_sold`.
- **(3) Review low — `fill_stop_checked`'s 3-day lookback vs the 16:45 caller (`breakout_v1_entry` ~786):** `check_stop_at_fill_after_close` visited EVERY open breakout row every evening, and after a restart (the in-memory `_fill_checked` cache gone) a row filled more than 3 days ago read "not checked" and was re-decidable from its day-0 bars — a `not_checkable` row (no bars that evening) could be SOLD days after the fill once the bars existed. Now the after-close pass checks ONLY a row FILLED THAT SESSION (`alert_date` = the pass's ET date; any other row → `fill_other_session`, no read of any kind), and the marker is looked up regardless of age (no date bound on the read, pinned as SQL text). Consequence, owned: the (G) dead-leg path is no longer retried the next evening — the stop stands as it filled (never wider), audited `breakout_v1_fill_stop_unchecked_after_close` ("not retried"), the page says so. Pinned: a day-0 `not_checkable` row is never re-decided on evenings 1, 4 and 10 after a restart (no fetch, no sale, one marker); the same session after a restart reads the marker (`fill_checked`). ⚠ **Disclosed (the retry-pass review, 2026-10-31, low):** with the date gate, a 16:45 pass that does not run ON the fill day (a restart or a failed job at 16:45) leaves a 15:55–15:59 fill unchecked for good — later evenings skip it as `fill_other_session`. Accepted on purpose: a check days later is not his ruling's "a minute after the fill", and selling then on day-0 bars would be worse; the minute job has already paged "could not be checked before 15:55 ET — check the stop on Alpaca by hand" for that fill.
- **EXPECT (for the first retry on a paper breakout trade; BASELINE today: 0 `breakout_pp_session_third_due` rows, 0 `breakout_pp_third_retry*` rows, 0 breakout paper trades with a session-3 third that did not sell):** on every session 3 whose 15:45 price is above the fill with no third sold, ONE `breakout_pp_session_third_due` row BEFORE that trade's `breakout_pp_planned_third_cancel` / `breakout_pp_session_third` rows (audit timestamps). When the session-3 sale did not happen (a `breakout_pp_third_cancel_unconfirmed`, `breakout_pp_session_third_unsold_reprotected` or `breakout_pp_session_third_unsold` row), the next session's 15:45 shows ONE `breakout_pp_third_retry` row for the trade, then exactly one of `breakout_pp_third_retry_sold` (+ `partial_exit_started` → ONE `partial_exit_committed` for the trade when it fills, `partial_taken` TRUE, the stop then at the fill via `breakout_pp_stop_to_fill_after_third`) / `breakout_pp_third_retry_third_filled` / `_third_stopped` (no sale; `partial_taken` TRUE from the stream) / `breakout_pp_third_retry_failed` (+ a withdrawal/coverage row and a page saying "retried at the next close", and the next session shows another `breakout_pp_third_retry`). Over the trade's life exactly ONE `partial_exit_committed` — AND, over its life, the broker's position never drops by more than one third while the row is open with a `partial_exit` or `stop_hit` of that size (an 'Untracked SELL' page on a breakout ticker after a `breakout_pp_session_third_unsold` row is the unrecorded sale: the next session must then show `breakout_pp_shares_left_unbooked` + `breakout_pp_third_already_sold` (`retry: true`) and NO `breakout_pp_third_retry`). A session-3 sale that went through produces NO retry rows on later sessions; a trade whose session-3 close was at/under the fill produces no `breakout_pp_session_third_due` and no retry rows ever. For the first 15:55 fill after this pass: one `breakout_v1_fill_stop_checked` from THAT evening's 16:45 pass, and no `breakout_v1_*` fill-stop rows for the trade on any later evening. **DONE-WHEN:** the first retry has run on a real paper trade and its audit chain reads as above (one `breakout_pp_third_retry`, one terminal row, at most one `partial_exit_committed` on the trade) — or, after 20 paper breakout trades, no session-3 sale has failed and the retry has never been needed (then the fuzz is the evidence and the task closes on the collision/evening pins). **WOULD-FAIL-IF:** a `breakout_pp_third_retry` row on a trade with no `breakout_pp_session_third_due` / planned-cancel / session-third row (a retry with no decision); a retry row on a trade whose `partial_taken` was already TRUE, or whose `exits` already held a `stop_hit` / whose `remaining_shares` < `entry_shares` / whose broker position at the step was below `remaining_shares` (a stop-leg fill or an unrecorded sale read as no third — the reader now compares all three); a `breakout_pp_third_retry_sold` on a trade with a `sync_qty_overwrite` or an 'Untracked SELL' before it and no `partial_exit_committed` (a second third); `breakout_pp_shares_sold_unreadable` with `read: broker_position` on three consecutive sessions (the position read is failing, not a ban); a `breakout_pp_session_third` on a trade with a `stop_exit_committed` row that left it OPEN; two `partial_exit_committed` rows on one breakout trade; a `breakout_pp_third_retry_sold` beside an open `partial_exit` order the step did not cancel (its `breakout_pp_planned_third_cancel` missing); a `breakout_pp_session_third_unsold` with no re-read (`resting_third`) — visible as a limit resting past session 3 with no marker and no retry the next session; a `breakout_pp_third_due_unreadable` on three consecutive sessions (the record read is failing, not a ban); a `breakout_v1_fill_stop_checked` row written on an evening after the trade's breakout day, or any `breakout_v1_sold_too_wide_after_fill` on a trade more than a session old.

### 2026-10-30 — breakout v1 PHASE 2 part A BUILT: the strategy row, the four paper walls and the `orh5` entry (merged 2026-10-31 with part B, the exit)

**Built** (spec `docs/design/breakout_v1_build_spec_2026-10-29.md` B4 + B5; his rulings as written — entry `orh5` in regular hours, stop = the day's low AT THE FILL with the 1 ADR20 abstain, size = EP's, F1 (a), F2 (a)):
- **Strategy row** `mi_strategies 'breakout_v1'` (`db._seed_strategies_registry`, seeded once): phase 'paper', enabled, `position_size_multiplier` 1.0, `max_concurrent_positions` NULL — F2: it shares the paper account's cap of 5 with the small-cap paper lane, no cap of its own. Exit levels left NULL (the exit is the per-row stamp below).
- **Stop switch:** runtime toggle `breakout_v1_paper` (`mi_safeguard_state`, account_mode 'global', default ON) + `mi_strategies.enabled`. LIVE_TRADING_ENABLED=false stops the job. `/pause` does not (paper; same as #624).
- **The four walls** (mirrored from `broker/lowcap_paper_entry.py`, each pinned in `tests/test_breakout_v1_entry.py`): (1) reads only `mi_breakout_v1_list`; (2) every tick refuses unless the row is phase 'paper' AND resolves to 'paper' (a refusal pages once); (3) `submit_trade_entry(require_account_mode='paper')`; (4) order ids `make_client_order_id('paper', 'breakout_v1', ticker)` (built by `submit_entry` from the paper row). Pre-flight: the paper account must answer before the first order of the day.
- **The entry** `agents/market_intelligence/broker/breakout_v1_entry.py`, job `breakout_v1_entry` (EXECUTION-owned, every minute 09:35–15:55 ET mon-fri, second 10; window enforced in the tick; NYSE holidays skipped): for each name on the previous session's list — ORH5 / ORL5 from the 09:30–09:34 minute bars, `level = max(ORH5, list level)`; a stop-limit buy at the level (limit `stop_limit_buy_price(level)`), DAY, OTO with the protective stop at the day's low so far, through the funnel with a spec builder that sizes like EP (`_resolve_regime_risk_pct` × paper equity / (level − stop), the 20% notional cap, the funnel's composite multiplier — pinned equal to `prepare_orb_order` share for share where the stops coincide). The #500 price-aware submit applies (pinned on a breakout row: price past the level → limit at latest × 1.002 inside the 1.5× chase cap).
- **F1 (RULED)** — the buy is only placed, and only kept live, while the volume through the last completed minute ≥ the list's volume bar (1.2 × the 50-day average) × the share of a day's volume normally done by that minute. **The curve is ONE pooled curve for every stock (not per-stock — a per-stock curve is a later refinement):** `broker/breakout_v1_volume_curve.py` (390 minutes), built once by `scripts/probes/_breakout_v1_phase2/build_volume_curve.py` (output `build_volume_curve.out`) from the stored SIP minute bars of the consolidation-breakout backtest (`apollo_data/cb702_pre_v2/minutes`) and that backtest's daily volumes (`daily_closes_all.csv.gz`, the same Polygon grouped-daily family as `mi_daily_closes`): **149,086 ticker-days, 3,151 tickers, 1,215 full sessions 2017-03-02 .. 2022-01-03** (4 early-close sessions dropped; 221 ticker-days with no daily row dropped), the mean over ticker-days of regular-hours volume through the minute / **the day's FULL daily volume** — the same unit as the list's 50-day average, so the bar is his 1.2× like for like. It reads 3.1% of a day's full volume by the end of 09:34, 9.9% by 09:59, 58% by 14:59 and 80% by 15:59 (the other ~20% trades in extended hours and the 16:00 closing cross); stable year to year (09:59: 9.1–10.8%). The curve is a mean; the median ticker-day is lower early in the day (2.4% by 09:34), so for a typical stock the opening minutes ask a little more than 1.2× its own pace. **Review fix 2026-10-30:** the first build divided by the day's regular-hours volume (ending at exactly 1.0) while the bar is full-day volume — that made F1 ask about 1.5× normal volume (1.6× at 09:34), close to the 1.5× he rejected on 10-28; rebuilt with the full-day denominator, pinned by test.
- **The stop at the fill:** while the buy is unfilled, a new day's low cancels the order (broker-confirmed) and places it again on the same row with the new stop and a fresh `apollo_paper_breakout_v1_*` id — never two live buys; a cancel that races a fill is never re-placed (the fill stands, paged). The buy is CANCELLED with `setup:stop_too_wide` once (level − day low) > ADR20 × level, with `setup:breakout_volume_below_curve` when F1 stops permitting, and with `window:breakout_unfilled_eod` at 15:55 ET. New named abstain `setup:no_opening_range_minutes` (a durable paper skip row).
- **Restart-safe:** every tick reconciles from the broker (the paper account's open orders in the `apollo_paper_breakout_v1_` family + `get_order` on each row's order) and today's rows; a planned cancel writes the marker `breakout_v1_planned_entry_cancel` (trade + order) BEFORE it cancels, so the trade stream does not record it as a broker kill (`trade_stream._handle_cancel_or_reject`: a marked, UNFILLED breakout cancel → no status write, no page; every other cancel unchanged, pinned) and a tick after a crash finishes the step from broker truth. **The polling backup `order_manager.check_fills` (10:00, 10:30, hourly to 15:00) knows the marker too** (review fix 2026-10-30): a marked breakout cancel is left to the minute job, and any other breakout cancel it records is compare-and-set on the row still being `order_placed` on THAT order (`_cancel_breakout_row_if_unchanged`) — so it can never mark cancelled a row the minute job has just re-priced onto a new order (which would have left the new buy resting untracked). Every other strategy's row takes check_fills' unchanged write (pinned for MAGNA53, the small-cap lane, 9M and NULL rows). A BUY-side order in the family that no LIVE row carries (none, or only a `cancelled` / `skipped` row) is cancelled and paged; a `filled` row still owns its partly filled entry (sell-side orders — protective stop legs — are never in the family, so the sweep can never strip a position's stop).
- **One trade per list name per day** (the funnel's duplicate key). **The 10:00 ET EP cleanup no longer cancels breakout rows** — excluded by SIGNAL TYPE (`cancel_unfilled_entries(exclude_signal_types=("breakout_v1",))` from `_orb_window_cleanup_job` only); the small-cap paper lane's unfilled orders and legacy NULL-signal rows are still cancelled at 10:00 (pinned); the 16:05 ET EOD cleanup is unchanged and is the backstop.
- **Exit stamp:** every breakout row is stamped `exit_rule = 'breakout_pp'` at insert (`order_manager.resolve_exit_rule_stamp`, no toggle; MAGNA53 / small-cap / 9M unchanged, pinned). **The exit itself is part B — this part must not deploy without it**: until B lands a filled row would meet the global +2R third (`scan_profit_triggers`) and the 16:45 default ladder.
- **Shared code, defaults = today:** `submit_trade_entry(bar_fetcher=None)` → `fetch_orb_bar_with_retry` exactly as before (EP and the small-cap lane pass none — pinned by an AST scan of every call site; 9M Day 2 has had no call site since #515); `cancel_unfilled_entries(exclude_signal_types=())`; `trade_stream`'s new branch is reached only by a `breakout_v1` row. Registrations: `EXECUTION_OWNED_JOB_IDS`, `scripts/audit_column_writes.py` (two compare-and-set writers), `scripts/preflight_db_updates.py` (both UPDATEs, copies pinned to source), `scripts/exec_loaded_modules.txt` (regenerated: +2 broker modules), skip-reason labels, `_SIGNAL_DISPLAY` / `/skipped` labels, the registry adapter.

**Readings the build had to make (mechanics, not his rules — each can be overruled):**
1. **An F1 lapse after the buy is resting is terminal for the day** (the row's duplicate key is one trade per name per day); before the first buy, F1 only holds — the buy is placed the first minute it permits (recorded once per state change, `breakout_v1_entry_hold`).
2. **Everything reads through the last COMPLETED minute** — so the stop attached at the fill can sit well ABOVE his "day's low at the fill", and a day his rule abstains as too wide can fill. The resting order carries the stop of the last tick (second 10 of each minute), which has read through the minute before the fill minute at best, or two minutes before when the break comes in the fill minute's first ~10 s. A drop in those last one or two minutes — or inside the fill minute itself — is not in the stop: the gap can be most of the true risk (a shakeout-then-rip: 09:36 flushes to 9.95, the break at 09:37:02 fills with the 10.05 stop — 0.10 tighter on a 0.55 true risk), and when 09:36 flushes to 9.80 and breaks 10.50 inside the same minute the order fills with stop 10.20 while his rule abstains too-wide (width 6.7% > ADR20 6%). On synthetic minute paths (`scripts/probes/_breakout_v1_phase2/stop_lag_probe.out`, not real tape) the stop differs on 0.6–2.3% of fills, tighter by a median ~9% (up to 50%) of the true risk; 6 of 3,956 too-wide days filled. Never wider. **RULED 2026-10-29 (b) + (c) — "Go with rec":** a minute after the fill the true low through the fill minute is read; too wide → sold at once, else the stop leg is lowered to it (the umbrella entry above; pinned by `test_ruled_the_reviewers_flush_inside_the_fill_minute_is_sold_a_minute_after_the_fill`). The stop sits on the cent at or below the low.
3. **A lower stop re-sizes the order** so the dollar risk placed never grows and the share count never rises (EP's sizing divides by the stop distance).
4. **The 1 ADR20 width is also judged at the #500 fallback's fill** (latest × 1.002) when the price is already past the level.
5. **At 09:35 the range waits one minute for the 09:34 bar**; `no_opening_range_minutes` only when later minutes exist and none in 09:30–09:34 (`cb._entry_one`'s rule).
6. **The curve and the bar are in the same unit** (full daily volume, extended hours and the closing cross included — review fix 2026-10-30, above). The live numerator is regular-hours volume only, matching the curve's numerator. On an early-close day the full-session curve makes F1 easier late in the session.
7. **Switch off (toggle / disabled / refused) cancels every resting unfilled breakout buy** (`block:strategy_disabled`), not just new ones.
8. **A resting unfilled buy holds a paper slot all day** (`order_placed` counts as open — F2's shared 5); a funnel skip (cap full at that minute, etc.) is terminal for the day, as for EP.
9. **Gap % on the row** = today's first open / the list night's close − 1. No fade guard, no EP gap floor.

**Known interactions, recorded not changed:** the paper book's (ticker, day) duplicate key is shared with the small-cap lane — whichever writes a paper row on a name first that day owns it. The stop-ACK watchdog's fallback stop (a fill whose stop leg never acks) sits at `orb_low` = ORL5, which is at or above the day-low stop — tighter, not wider. The previous session is the NYSE calendar's (`trading_calendar`), and the list is read for exactly that night: a night whose list job did not run (or wrote 0 names) is no names — a list a session stale is never traded.

**EXPECT** (BASELINE today: no `mi_strategies` row 'breakout_v1'; 0 `mi_live_trades` rows with signal_type 'breakout_v1'; 0 `breakout_v1_*` entry audit rows; 0 `breakout_v1_entry` job runs):
- positives: the row exists (paper, enabled, 1.0, cap NULL); `breakout_v1_entry` runs about 381 times a market day; on a day the list has names, ONE `breakout_v1_preflight_ok`, then each name reaches a named state — an order row (status `order_placed`, `exit_rule='breakout_pp'`, `orb_high` = the level, `stop_price` ≤ ORL5, order id `apollo_paper_breakout_v1_*`) or a `breakout_v1_entry_hold` / `breakout_v1_entry_abstain` row; `breakout_v1_stop_repriced` rows when an unfilled name prints a new low; unfilled buys cancelled at 15:55 ET with `window:breakout_unfilled_eod`; ONE `breakout_v1_entry_day` row at 15:55; the 10:00 cleanup touches no breakout row and still cancels the lane's unfilled paper orders.
- positives, the stop at the fill (his ruling 2026-10-29; BASELINE: 0 `breakout_v1_fill_stop_checked` rows): every FILLED breakout row gets exactly ONE `breakout_v1_fill_stop_checked` row by the tick after its fill minute; a `lowered` one has a `breakout_v1_stop_lowered_after_fill` row and the broker stop leg named by the row's `stop_order_id` rests at the row's `stop_price` = `hard_stop` = the cent at or below the day's minute low through the fill minute; a `sold` one has a `setup:stop_too_wide_after_fill` full exit; a `kept` one's stop_price is unchanged.
- unintended: any breakout row outside the paper book; two open family orders on one ticker at once; a row `order_placed` with no open or filled order at the broker after a re-price; `breakout_v1_entry_crash` / `breakout_v1_cancel_failed` / `breakout_v1_reprice_lost` / `breakout_v1_orphan_order` rows; a paper "Entry CANCELLED" page for a planned re-price; any page on a normal day; a MAGNA53 or small-cap row stamped differently or cancelled differently than before.

**DONE-WHEN:** the first list day ends with every list name in exactly one named state in that day's `breakout_v1_entry_day` row, at least one breakout order placed through the funnel (paper id, `breakout_pp` stamp), and — the first time an unfilled name prints a new low — a `breakout_v1_stop_repriced` row whose new order's stop leg at the broker equals the row's `stop_price`. Then this part closes with part B's exit.

**WOULD-FAIL-IF:** a re-priced row's broker stop leg is still at the old stop (or the row is `order_placed` with a dead order); the 10:00 cleanup cancels a breakout row, or no longer cancels a lane row; a name with F1 permitting and a valid range has no order and no hold/abstain row explaining why; a filled breakout order is cancelled or a second buy is placed for the same name that day; an EP / lane entry fetches its opening bar anywhere but `fetch_orb_bar_with_retry`; a filled breakout row with no `breakout_v1_fill_stop_checked` row after its fill minute (outside the disclosed 15:55 edge, which pages); two such rows for one trade; a `lowered` row whose broker leg still shows the old stop, or a stop the check RAISED; a `kept` / `lowered` trade whose (fill − true low) > ADR20 × fill (it should have been sold); any `breakout_v1_fill_stop_*` / `stop_lowered_after_fill` row on a non-breakout trade.

**VERIFY-LIVE:**
```sql
SELECT strategy_id, phase, enabled, position_size_multiplier, max_concurrent_positions FROM mi_strategies WHERE strategy_id = 'breakout_v1';
SELECT date(started_at AT TIME ZONE 'America/New_York') d, count(*), count(*) FILTER (WHERE status <> 'success') bad
  FROM mi_job_runs WHERE job_id = 'breakout_v1_entry' GROUP BY 1 ORDER BY 1 DESC LIMIT 3;
SELECT id, ticker, status, orb_high, orb_low, stop_price, entry_shares, exit_rule, skip_reason, entry_order_id
  FROM mi_live_trades WHERE signal_type = 'breakout_v1' ORDER BY id DESC LIMIT 20;
SELECT created_at, event_type, summary FROM mi_audit_log WHERE event_type LIKE 'breakout_v1_%' AND event_type <> 'breakout_v1_list_run'
 ORDER BY created_at DESC LIMIT 40;
SELECT o.alpaca_order_id, o.side, o.order_type, o.stop_price, o.status, o.purpose FROM mi_live_orders o
  JOIN mi_live_trades t ON t.id = o.trade_id WHERE t.signal_type = 'breakout_v1' ORDER BY o.id DESC LIMIT 20;
```
(The broker side of the re-price check: the paper account's open orders for the ticker — one parent, its stop leg at the row's `stop_price`. The stop at the fill: one `breakout_v1_fill_stop_checked` row per filled trade in the audit query above; for a `lowered` one, `get_order(stop_order_id)` at the broker reads the row's `stop_price`, and the day's minute low through the fill minute (from the broker's `filled_at`) re-derives it.)

Deploy scope: `execution` FIRST (broker/*, `trade_stream.py`, `scheduler.py`, `db.py` run on apollo-execution), then `both` (`db.py`, `agent.py`, `sell_discipline.py`, `strategies/adapters.py`). Ships with part B (the exit), never alone. DEPLOYED 2026-10-31 with part B in that order (server `17853040`, #717).

### 2026-10-30 — Breakout v1 PAPER, phase 2 part B: the `pp` exit on the paper book (BUILT; DEPLOYED 2026-10-31 with part A, server `17853040`, #717)

**What.** Every `breakout_v1` row (stamped `exit_rule = 'breakout_pp'` at insert, part A) now runs his `pp` arm live, on the
PAPER book only. No rule moved: the definition is `consolidation_breakout_pp.walk_pp` (arm `pp`), and the live decisions are
held equal to it event for event wherever the +2R limit fills at the touch, with the defined divergence where it does not
(his ruling 2026-10-29, difference 10) (`tests/test_breakout_pp_exit.py`, 500 random daily + minute days, the scenario tails,
120+-session paths and short histories; mutation-checked: a wrong trail length, cut level, leg session, a missing stop
move or a dropped reach test each fail it).

**Who does what (the mapping).**
| Walk event | Live owner | When |
|---|---|---|
| a third at +2R (at the target; at the open when it opened above), breakout day on | `order_manager.scan_profit_triggers` (unchanged): R = entry − hard_stop (breakout_v1 is not ORB-framed), the global multiple 2.0, `int(shares // 3)`; sells via `execute_partial_exit` | the 5-minute poll of the minute highs since the fill |
| after any third the stop rests at the fill | `order_manager.finalize_partial_exit` when a third FILLS (breakout-only: `update_stop` to the fill, raise-only) — never at placement (ruling (3)(ii)); the 16:45 job lifts a stop still under the fill once a third has sold (raise-only), the breakout day included | at the third's fill; 16:45 backstop |
| stall cut: no high at fill + 1R by the close of session 3 → everything sold at that close | `live_tracker.run_partial_exits` → `execute_full_exit(.., 'breakout_stall_cut')` | 15:45 ET on session 3 |
| session-3 third, ONLY when that close is above the fill (and no third yet) | `run_partial_exits` → (a still-resting +2R limit cancelled first, confirmed — ruling (3)(i)) → `execute_partial_exit`; a DECIDED third that did not sell is retried by the same step at each later session's close (his ruling 2026-10-31; `breakout_pp_rules.retry_decision`) | 15:45 ET on session 3; sessions 4, 5, … while no third has sold |
| the rest at the next open after the first close under the 20-day SMA — live from session 3, or from a +2R third | `live_tracker.update_open_positions_live` MARKS (`depth_sell_pending_on`); `order_manager.run_breakout_pp_open_sales` (new job `breakout_pp_open_sale`, 19:02 ET mon–fri, execution-owned) sends the PAPER DAY market sale (#687 option (c)'s vehicle, through `execute_depth_open_sale`) | 16:45 on the settled close → fills at the next open |
| the stop (the day's low at the fill) | the broker's resting stop leg; the 16:45 ladder's trail-stop raise does NOT run on these rows | always |
| day-0 facts (the +2R touch before the stop, the highest minute high after the fill) | `breakout_pp_exit.ensure_day0_facts` = the recorder's `day0_facts` (ported; equal on 600 random minute days), from the breakout day's minute bars, stored once on `mi_live_trades.breakout_day0_pp` (JSONB, new column, one writer) | 16:45 ET on the breakout day (or the first later run that finds it missing) |

A `breakout_pp` row is never put through the day-3/5 ladder or the 10/20 trail, and a `breakout_pp` row whose account is not
'paper' is refused by the 15:45, 16:45 AND 19:02 steps (audited `breakout_pp_refused_not_paper` + paged, nothing sold or moved). Depth rows, EP, the small-cap lane and 9M run
exactly as before (the depth runner still selects `exit_rule = 'depth'` alone; its words are unchanged).

**Where the live machinery CANNOT express the walk exactly (named, not bent):**
1. Intrabar order: the walk's daily bar puts the stop before the +2R (unless the session opened above it); live, the broker
   and the poll act in real time order. After a +2R third on session 1+ the walk rests the stop at the fill from the NEXT
   session; live moves it when the third FILLS (a same-session fall back to the fill stops the rest at cost). Day 0 matches
   (the minute walk also moves it from the next minute). Placing the +2R limit moves nothing (ruling (3)(ii)).
2. The +2R third is found by the 5-minute poll and sold at market (or a resting limit at the target when the paper
   resting-limit toggle is on) — not exactly at the target.
3. "The close of session 3" is the 15:45 ET price: the cut, the session-3 third and its price are decided 15 minutes early;
   a +1R high printed after 15:45 does not save a trade from the cut. A missed 15:45 run on session 3 is not retried (no decision was made that day); a session-3 third that WAS decided and did not sell is retried at each later close (his ruling 2026-10-31).
4. Whole shares: a third = shares ÷ 3 rounded down; 1–2 shares → no third (and so no stop move to cost).
5. "The next open" = a DAY market order queued at 19:02 ET that fills at the first prints after 09:30, not the opening print.
6. No horizon: the walk marks a trade at 120 sessions; live holds until a stop, the cut or the trail.
7. Session j is counted from the stock's daily bars; a missing daily bar shifts it.
8. No breakout-day record (no fill time in the session, no minute bars) → the stall cut is NOT applied (audited, paged).
9. The +2R third rides the global `PROFIT_TRIGGER_R` (2.0) and its on/off switch (the breakout row has no override). A
   test pins the poll's target to the pp target, so changing the global fails the build.
10. **Only a third that FILLED counts — RULED 2026-10-29 ("Go with rec"), the defined divergence.** The review
   (2026-10-30) found the walk's reading in live ("was a third sold" = a daily high at +2R); his ruling replaced it with the
   row's truth (`partial_taken`, `breakout_pp_rules.third_sold`). On the paper book the +2R third is a resting limit (an
   OCO, its own breakeven stop) at the target placed by the poll after a minute high touched it; when it does NOT fill at
   the touch, live departs from the walk on exactly those paths: no 20-day trail before session 3 (unless the limit fills
   first), the third booked only when (and at the price) it fills, and at session 3 — the close above the fill and the
   limit still resting — the limit CANCELLED and the third sold at that close (RULED 2026-10-29 late, "option a": the
   umbrella entry's (3)); the stop stays where it was from the touch until a third actually sells. A touch after session 3
   (or a session 3 at or under the fill) leaves the limit resting; after a trail sale it stays open with its own target and
   its OCO stop (at the stop the shares had) until one of them fills. Pinned two-sided by
   `TestTheDefinedDivergenceWhenTheLimitDidNotFill` + `test_ruled_a_target_touch_whose_limit_did_not_fill_is_not_a_third_sold`;
   the race and the shared-code gates by the `test_1545_*` tests and `tests/test_breakout_pp_option_a.py`.

**EXPECT** (baseline 2026-10-30: 0 breakout paper trades, 0 rows with `breakout_day0_pp`, 0 `breakout_pp_*` audit rows):
on the first breakout paper fill — that evening one `breakout_pp_day0_facts` audit row and the row's `breakout_day0_pp`
set (`v` = 1); `hold_days` advancing each evening while it is open; on session 3 at
15:45 exactly one of: a stall cut (`breakout_pp_stall_cut` + a full exit), a third (`breakout_pp_session_third` + a partial exit), or
nothing (price at or under the fill / a third already sold — `partial_taken`), or, when the +2R third is still resting
unfilled and the price is above the fill, `breakout_pp_planned_third_cancel` → `breakout_pp_third_cancelled_for_session_third`
→ `breakout_pp_session_third` + a partial exit of the cancelled limit's size (or `breakout_pp_third_filled_in_race` and no
sale, or `breakout_pp_third_cancel_unconfirmed` and no sale + a page — then `breakout_pp_third_retry` at the next session's 15:45); on every +2R placement `breakout_pp_stop_held_at_placement`
with `stop_price` unchanged, and on a third's fill `breakout_pp_stop_to_fill_after_third` (stop_price → entry); a 16:45 close under the 20-day → `breakout_pp_close_below_sma20`
and at 19:02 a `depth_open_sale_placed` row with vehicle `day_market`, `apollo_paper_breakout_v1_` order id, filled after
09:30 next day. Unintended (each would be a defect): a `breakout_pp` row's stop raised to a 10/20 line, a day-3/5 ladder
partial on it, any `breakout_pp` action on a non-paper row, any change in a depth/EP/9M row's exit.
**DONE-WHEN:** the first breakout paper trade has closed through one of the pp exits (stop, cut, trail) with its day-0 record
written and every live event matching a re-walk of `walk_pp` on its stored fill/stop and the prod bars (modulo the named
differences above). A third left resting under its OCO after a trail sale (difference 10) closes when its own target or
breakeven stop fills; the trade is done when that leg is.
**WOULD-FAIL-IF:** a breakout paper row with no `breakout_day0_pp` after its breakout-day 16:45 · a session-3 third at or
under the fill · a trail sale before session 3 on a trade whose `partial_taken` was FALSE at that 16:45 (a touch that did
not fill started the trail) · a session-3 third sold while a `partial_exit` order of the trade was still open and NOT
cancelled by the step (a double third) · two `partial_profit` exits on one breakout trade from different thirds · a +2R limit
placed on a trade after its `breakout_pp_planned_third_cancel` · a session-3 third skipped on a trade whose 15:45 price was
above the fill with no third filled and either none resting or a resting one the step confirmed cancelled · a breakout
row's `stop_price` raised before any `partial_exit_committed` on it · a stall cut on a trade whose recorded peak or a session
1–3 high reached fill + 1R · a `breakout_pp` stop moved anywhere but to the fill · a 19:02 sale on the live account.
**VERIFY-LIVE:** `SELECT id, ticker, breakout_day0_pp, partial_taken, stop_price, hard_stop, entry_price, status FROM
mi_live_trades WHERE exit_rule = 'breakout_pp'`; `SELECT * FROM mi_audit_log WHERE event_type LIKE 'breakout_pp_%' ORDER BY
created_at`; re-walk each trade with `consolidation_breakout_pp.walk_pp_arms` on its fill, hard_stop, stored facts and the prod
daily bars, and compare events.

### 2026-10-29 — breakout v1 PHASE 1 BUILT (the nightly list + grading; no orders)

**Built** (spec `docs/design/breakout_v1_build_spec_2026-10-29.md` B1–B3 + this entry; B4 strategy row, B5 entry, B6 exit NOT built):
- `agents/market_intelligence/breakout_v1.py` — the v1 rules, PURE: `v1_gates` (universe $2 / $5M, RS best-of-three ≥ 98, prior move, higher lows, surf, tightening, the breakdown check; every gate's pass + value, the next session's level and volume bar), `breakout_triggered` (high > level strict, volume ≥ 1.2× the 50-day), the fund rule `fund_rule` / `fund_is_single_asset`, `security_admitted`. Calls `cb` (`_pole_top`, `_sma_at`, `_dollar_vol_median`, `cross_section_one_date`); `cb` is not edited.
- `agents/market_intelligence/breakout_v1_list.py` + job `breakout_v1_list` (17:55 ET mon–fri, intelligence-owned, `audit_wrap`, fails open after 600 s with a `breakout_v1_list_error` row) → table `mi_breakout_v1_list` (the night's rows replaced whole, ranked by rs_best, every gate value in `gates`) + ONE `breakout_v1_list_run` audit row + ONE paper-chat Telegram naming tonight's names (ticker, level, RS) only when the list is non-empty.
- `/bgrade TICKER A+|A|B|C|skip [note]` → `mi_breakout_v1_grades` (the latest list night carrying the ticker; a re-grade replaces); bare `/bgrade` lists the ungraded names of the last 5 list nights. Handler + dispatch (`agent.py`), CommandHandler + BotCommand (`channels/telegram.py`). A grade gates nothing.
- `mi_security_types.name` (new column) — Polygon's reference name, stored by the security-type refresh (`collector.fetch_all_ticker_types`, `db.upsert_security_types_batch`); the refresh also runs when no row carries a name yet, so the first night after the deploy fills names instead of waiting for Monday.
- Tests: `tests/test_breakout_v1_parity.py` (committed fixture `tests/fixtures/breakout_v1_parity/`, built once by `scripts/probes/_breakout_v1_build/build_parity_fixture.py` from the reference code itself), `tests/test_breakout_v1_fund_rule.py`, `tests/test_breakout_v1_list.py`.

**Parity (the acceptance bar): PASS.** On every one of the 2,879 evaluated nights of his 23 names the port's gates equal the reference's gate by gate, and every universe-wide prefiltered candidate of the 2020 window agrees with it (the 3,524 V3 fires included). The 24 classify exactly as `v1_check_variant_rs.txt`: HIT 10 | LATE 2 | EARLY 1 | MISS 11, **12 of 24 caught** (the 4 secondary: HIT 2 | MISS 2). **With the breakdown check added, no row changes** (PENN-3 stays EARLY-31); universe-wide it removes 3 of 486 fire-days (AHPIQ 2020-07-16, COLL 2020-02-28, VIR 2020-04-20): **3.71 → 3.69 names a night** in the 2020 check.
⚖ **THE RS POOL — HIS RULING 2026-10-29 ("Ok a"): the job ranks RS against EVERY security above $2 / $5M (funds and ETFs included) — the pool the approved 12-of-24 check used — and the type rule decides only who may be LISTED** (`breakout_v1_list.scan_members`: a pool-only member is ranked, never given the gates; pinned by `tests/test_breakout_v1_list.py::test_the_rs_ranking_pool_is_every_security_at_the_floors_and_only_admitted_types_are_listable`). Why it was put to him: the first build ranked against the type-admitted universe only. A review rebuilt the 2020 pool with that type filter (today's Polygon types applied to 2020 tickers; untagged delisted names admitted; the build review 2026-10-29, types from `small_pulls.psv` + `cb702_sic.psv` over `apollo_data/cb702_pre_v2`, ETF / FUND / ETN / SP / UNIT dropped — ~550 of ~2,900 names a night): **10 of 24 caught** — CELH-1 HIT → EARLY-12 (RS 98.0 → 97.6), PENN-2 HIT → MISS (98.2 → 97.9), PENN-3 EARLY-31 → MISS (97.7 → 97.2); admitting every ETV fund as well changes nothing. The ~3.7 names a night is also an untyped-pool number; the typed pool's names a night is UNMEASURED. He chose (a) over (b) (the typed pool, 10 of 24). Caveat stated to him: about 1,218 ETFs clear $2 / $5M today (of 4,166 names, `scripts/probes/_breakout_v1_build/q_pool_types.out`) against ~550 of ~2,900 in the 2020 data, so a few more stocks may clear the top 2% than in that check; the first nights' counts show it.

**The fund rule** (his ruling "single asset makes sense"; a pure NAME rule — no leveraged / inverse word, no basket word, exactly one known underlying; a name naming none is EXCLUDED, fail closed), on the 90 ETV names of the 10-28 pull:
- KEPT (60): BAR BAVA BHYP BITB BNO BSOL BTC CANE CLNK CORN CPER CTWO DBO ETH ETHE ETHW FGDL FSOL FXA FXB FXC FXE FXF FXY GBTC GDOG GLD GLDM GLNK GSOL GSUI GXRP IAU IAUM MSBT MSOL MSSE NRR OUNZ PALL PHYS PLTM PPLT PSLV SCOP SGOL SIVR SLV SOEZ SOYB UGA UNG UNL USL USO UUP WEAT XRP XRPZ ZCSH.
- EXCLUDED, leveraged / inverse (13): AGQ BOIL EUO GLL KOLD SCO UCO UDN UGL ULE YCL YCS ZSL. Baskets (12): BITW DBA DBB DBC DBE DBP GDLC GLTR GSG TAGS TKNZ USCI. Two underlyings (3): BTCK CEF SPPP. No known underlying (2): BDRY BWET.
- **Ambiguous, for his check:** UUP (kept — one dollar-index futures contract, itself an index of six currencies) · CTWO (kept — EU carbon allowances) · UNL / USL (kept — a 12-month futures strip of one commodity) · BDRY / BWET (excluded — dry-bulk / tanker freight futures across several routes) · the staking coin funds BSOL ETH ETHE GSOL GSUI (kept — one coin plus its staking yield). A NEW coin fund whose coin is not in the rule's word list is excluded until it is added (named in the audit row's `fund_excluded_tickers`).

**Readings the build had to make (not his rules, stated so he can overrule):** the nightly RS cross-section is every security at the $2 / $5M floors with a 63-session return over consecutive sessions (his ruling (a) above — bad tickers / test symbols and names across an unapplied split are out of it); a horizon that crosses a calendar hole reads None; an unknown security type (no `mi_security_types` row) is admitted, as `cb.universe_ok` does; the list table is NOT in the detector-liveness registry (a 0-name night is legitimate — the audit row is the liveness).

**EXPECT** (BASELINE today: 0 `mi_breakout_v1_list` rows, 0 `mi_breakout_v1_grades` rows, no `breakout_v1_list_run` audit row):
- positives: the first weekday 17:55 ET run writes ONE `breakout_v1_list_run` audit row and about 4 names a night (the 2020 check read ~3.7 on the same untyped RS pool; today's pool carries a larger ETF share, so a somewhat higher count is not by itself a defect), every row's stored gates all passing; ZCSH-like single-asset funds appear when they qualify; `funds_excluded_no_name` ≈ 0 on the FIRST night (the 17:00 pull before it refreshes types and stores names — it runs on a Monday and whenever no row has a name yet), and `mi_security_types` shows ~all rows named.
- unintended: a crash or a `breakout_v1_list_error` row; a list far above ~10 names a night; ZCSH-like funds missing (names not stored → every fund excluded, `funds_excluded_no_name` large) or a leveraged / inverse / basket fund present.

**DONE-WHEN:** the first night's list is written, its message is sent (`message: sent` in the audit row), and one `/bgrade` round-trip is stored.

**WOULD-FAIL-IF:** a night with names whose stored gates do not all pass; a leveraged / inverse or basket fund on the list.

**VERIFY-LIVE:**
```sql
SELECT created_at, summary FROM mi_audit_log WHERE event_type IN ('breakout_v1_list_run', 'breakout_v1_list_error')
 ORDER BY created_at DESC LIMIT 5;
SELECT scan_date, count(*) AS names, bool_and((gates->>'ok')::boolean) AS all_pass,
       string_agg(ticker || ':' || coalesce(security_type, '?'), ' ' ORDER BY list_rank) AS list
  FROM mi_breakout_v1_list GROUP BY scan_date ORDER BY scan_date DESC LIMIT 5;
SELECT l.scan_date, l.ticker, s.name FROM mi_breakout_v1_list l JOIN mi_security_types s USING (ticker)
 WHERE s.security_type = 'ETV' ORDER BY l.scan_date DESC;
SELECT * FROM mi_breakout_v1_grades ORDER BY graded_at DESC LIMIT 5;
SELECT count(*) FILTER (WHERE name IS NOT NULL) AS named, count(*) FROM mi_security_types;
```
Deploy scope: `both` + `execution` (`agent.py`, `db.py`, `collector.py`, `scheduler.py` are on `scripts/exec_loaded_modules.txt`; `channels/telegram.py` is orchestrator). Not deployed.

### 2026-10-29 — his ODD reading: a setup day that closes below all the averages and undercuts the recent lows is NOT a setup; a check for it costs none of his caught setups (RULED IN — his "yes" 2026-10-29)

His words (`operator_shared_notes.md` 2026-10-29): *"on sept 8 ODD dropped 5% below all moving avg, below recent lows, it's still higher then a low on Aug 17 but no longer surfing cleaning and became less tight ... there's no setup on Sept 8"*. Verified on the bars: 09-08 close $13.02 under the 10/20/50-day ($14.20 / $13.53 / $14.94), low $12.99 under the prior 10 sessions' low $13.07; v1's higher-lows rule passed only because the base low is 08-17's, and the surf rule passed because a low within 1 ADR of the 20-day counts even from below. **The check (his "yes", 2026-10-29 — in v1):** at the watch night D, close not below ALL of the 10/20/50-day AND low not below the lowest low of the 10 sessions before. On his 12 caught good setups it keeps **12 of 12** (each also passes "close ≥ the 50-day"), and it rejects ODD 09-08 (`scripts/probes/_qm_0810_review/v1_breakdown_gate_check.txt`). Its effect on names a night is measured at the build (it can only lower the ~3.7). **His better date, ODD 2026-10-09, v1 MISSES** (`scripts/probes/_594_sample4_1029/v1_gates_odd_1009.txt`): every shape rule passes (prior move +71%, higher lows, 16 sessions on the averages, tightening 0.80) and the new check passes, but breakout volume was 0.63× the 50-day (needs 1.2×) and strength 96.6 (needs 98). One example — no threshold moves on it; it is the first positive row for the volume rule's next read.

### 2026-10-29 — his sample-4 "garbage" charts checked against breakout v1: none fires; ODD passes every SHAPE rule and only the strength rule stops it

He asked whether the eight gap-day charts he ruled bad (all BAD_CHART, `tests/fixtures/must_not_trade_charts.py` session 2026-10-29) would pass our breakout test. They were EP samples, not breakout picks, and none fires v1 (`scripts/probes/_594_sample4_1029/v1_gates_on_sample4.txt`, the probe's own gate code, setup at the close before the gap): seven fail the shape rules (no 30% prior move — AKAM, PHVS, GNRC, ROIV, CCL, SIG; no higher lows / no surf — DFTX, GNRC, ROIV, CCL; no tightening — AKAM, CCL, SIG). **ODD 09-09 passes every shape rule** (prior move +95%, higher lows, 11 sessions on the averages, tightening 1.06, broke the 5-session high on volume) — the chart he called *"garbage, no pattern at all, chopping around"* — and fails only the strength rule: best of the 1/3/6-month percentiles 88.1 against 98 (`q4_odd_rs.out`; −8% in a month, −7% in six). The forward shadow listed none of the eight. Read: the shape rules alone admit a chop he rejects; the top-2% strength rule is load-bearing, so it must not be loosened without his eye on what it lets in.

### 2026-10-29 — his positive example ZCSH (10-29) checked against breakout v1: every setup rule passes, but the UNIVERSE excludes it (an ETF)

He pointed at ZCSH (Grayscale Zcash ETF) as the pattern: *"big run up, pulls back, pulls into 50d then moves back above all moving avg making higher lows, tighten and trying to breakout today"* (`operator_shared_notes.md` 2026-10-29). Our v1 rules on its stored bars as of the 10-28 close (`scripts/probes/_zcsh_1029/v1_gates_at_1028.txt`, the probe's own gate code): price $34.63, $41M a day; up 215% in 3 months, 354% in 6; prior move +337% to a 09-23 top at $43.91, a 25-session base; higher lows yes; surfed the averages 7 sessions in a row (≥ 5); tightening 0.56 (≤ 1.1); today's level $35.13, needing ≥ 1.92M shares (1.2× the 50-day). **But it can never fire:** ZCSH is security type ETV, and this module's universe takes common stock and ADRs only (`UNIVERSE_SECURITY_TYPES`), so the forward shadow never wrote a ZCSH watch row. Whether funds belong on the list is his call (the universe is part of the rule); 92 ETV names (single-asset trusts such as ZCSH) and 5,809 ETFs sit outside it today.
**RULED 2026-10-29 (his "yes, single asset makes sense"):** breakout v1's universe adds single-asset funds (one underlying: a coin, a metal, a commodity, a currency), not general ETFs. The `ETV` type is not exactly that set — it also holds about a dozen leveraged / inverse funds (AGQ, BOIL, KOLD, UCO, SCO, ZSL …) and several multi-asset baskets (DBC, GSG, USCI, GLTR, GDLC …), which stay out; the build derives the kept set from the fund names and prints kept and excluded for him to check (`docs/design/breakout_v1_build_spec_2026-10-29.md` B2).

### 2026-10-29 — breakout v1 BUILD SPEC written for the Fri 10-30 paper build (nothing built)

`docs/design/breakout_v1_build_spec_2026-10-29.md`: seven components in priority order (the rules as a pure module with a parity test that must reproduce his 12 of 24, the nightly list, the running list + `/bgrade`, the strategy row behind four paper walls, the `orh5` entry with the stop kept at the day's low until the fill, the `pp` exit, the SSoT/verify), a cut line (list + grade first; an entry never ships without its exit), and two forks that are his: how breakout volume is judged at an intraday buy (rec: volume so far vs the stock's normal volume by that minute ≥ 1.2×) and whether the paper book's cap of 5 is shared (rec: shared). **RULED 2026-10-29 (his "ok" to both recs, `operator_shared_notes.md`):** breakout volume at the buy = volume so far vs the stock's normal volume by that minute ≥ 1.2×; breakout v1 shares the paper account's cap of 5 with the small-cap paper lane.

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
