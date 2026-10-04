# #686 — Pre-registration: re-reading #684 on the September block (frozen 2026-10-04)

**MEASUREMENT ONLY. $0. Nothing here changes or proposes to change the score, the admission line, any
threshold, stop, size, safeguard or live trade state — any such change is CHANGE_PROCESS and the
operator's call (THE LINE).** This document is a REGISTRATION: it fixes, before a single outcome of the
block exists, what will be measured, on which rows, with which rule, and what each possible result
will be called. The read itself is `scripts/probes/_686/preregistered_read.py`; it refuses to run before
the block has matured and refuses to run if this document or itself has been edited (§Freeze record).
Written 2026-10-04 PT. The block's 15th forward session is 2026-10-16, twelve days away; no outcome of
any scan date in the block was looked at, queried or computed while writing this.

**Population:** every gap-day candidate the EP scan SCORED (`mi_ep_scan_log.ep_score IS NOT NULL`) with
`scan_date` from 2026-09-04 to 2026-09-25 inclusive, one row per (ticker, scan_date) — n = counted by
the read's STEP 0 and printed before any outcome (expected ≈ 75–120 rows, §7).

## 0. The question and the answer it can give

- **Question (his, 2026-09-28, fork 1 of #684):** does any feature known on the gap day mark the EPs
  that run big — out of sample, on a block #684 never saw?
- **Possible answers, named now:** for each of 65 draws (the 63 #684 features + the 2 reversed leads),
  one of **CONFIRMED · HOLDS (report only) · AGAINST · can't tell · no data** (§6). "None hold" means
  zero CONFIRMED. Only CONFIRMED features reach his ruling as "a feature holds".
- **What a CONFIRMED feature leads to:** a one-paragraph proposal for his ruling (§10) — never a
  change made by this read.

## 1. The block, and the earliest date the read may run

- **Block = scan dates 2026-09-04 .. 2026-09-25**, the 15 NYSE sessions 09-04, 09-08, 09-09, 09-10,
  09-11, 09-14, 09-15, 09-16, 09-17, 09-18, 09-21, 09-22, 09-23, 09-24, 09-25 (2026-09-07 is Labor
  Day). It starts the day after #684's last scan date (09-03) so the two populations are disjoint.
- **Maturity:** the outcome needs sessions +1..+15 after each scan date (§3). The 15th NYSE session after
  2026-09-25 is **2026-10-16** (exchange_calendars XNYS: 09-28, 09-29, 09-30, 10-01, 10-02, 10-05, 10-06,
  10-07, 10-08, 10-09, 10-12, 10-13, 10-14, 10-15, 10-16 — Columbus Day 10-12 is a trading session; no
  holiday in the span). The 10-16 daily bar lands in `mi_daily_closes` with that evening's nightly pull.
- **Earliest run: 2026-10-17 (PT).** The script's calendar gate refuses before that date; its data gate
  additionally refuses unless the pulled daily file holds a SPY session dated ≥ 2026-10-16. Rows whose
  own ticker lacks 15 forward sessions (a halt, a delisting) are censored and counted, never filled in.
- The script re-derives "15th session after 09-25" from the calendar library at run time and asserts
  it equals 2026-10-16, so the hardcoded date cannot silently disagree with the calendar.

## 2. Population rule (verbatim #684, `scripts/probes/_686/extract.sh` → `data/pop.tsv`)

- **Every scored candidate, blocked or not** (his ruling 2026-09-28): a row enters on `ep_score IS NOT
  NULL` alone. Names the live system later skipped for a safeguard (`block:*` — circuit breaker, max
  positions, daily loss, /pause) are IN, as EPs; so are names it never ordered. Safeguards are
  orthogonal to what an EP is.
- **One row per (ticker, scan_date)**, #684's dedupe: prefer the tick that PASSED (`filter_reason IS
  NULL AND score_tier IS NOT NULL`), else the highest `ep_score`, ties → the latest tick.
- **`alerted`** = the gap-day scan's own PASS verdict (any tier), as in #684. **`HIGH`** (new column, for
  frame B only) = a live-source `mi_ep_alerts` row with `score_tier = 'HIGH'` exists (`any_high_alert`);
  its time = that first HIGH alert row's creation minute (`first_high_alert_et`). **The scan tick's tier
  is NOT used:** `mi_ep_scan_log` is written before the judge override (`ep_detector.py:6746` vs the
  W2c override at `:7141`), so a tick logged HIGH can be demoted to a MODERATE alert and never ordered,
  and a MODERATE tick promoted to a HIGH alert and ordered — in #684's own population (rows from
  05-11) 15 and 28 such rows. The order fires off the alert, so the alert row is the record of what the
  live path acted on. #684's `first_pass_time` (first pass of ANY tier) is not used for the live frame.
- **Era:** every row is era B (the 08-22 rescaled score, bar 65). The `ep_score` draw is read with its
  frozen era-A cut (top third = score ≥ 60) and is flagged a scale artefact in advance (§5).
- **Not in the population, by construction:** names never scored (the top-20 gap cap, `mcap_too_small`,
  the universe floor) — the ABNB/CHPT class is #617/#624's question, not this read's.

## 3. Outcomes — two frames, both registered

**Frame A — from the gap-day close** (identical to #684, `_684/study.py::add_outcomes`):
`run_xadr = (max HIGH over sessions +1..+15 − gap-day CLOSE) / ADR$`, `ADR$ = mean((h−l)/c) over the 20
sessions before the gap day × the gap-day close` (`features.py: adr_dollar_ep`, =
`delayed_entry_shadow.compute_ep_adr_dollar`). Bars from `mi_daily_closes` (split-adjusted).

**Frame B — from the live entry, modelled on TODAY's order path** (`preregistered_read.py::frame_b`,
`entry_today`). Read from the code, cited, not summarised:

| step | today's code | how the replay models it |
|---|---|---|
| who gets an order | only a HIGH alert: `scheduler.py:1236` `if ep.get("score_tier") == "HIGH"` (the post-judge tier the alert carries) → alert → ORB path | rows without a HIGH alert ROW (§2): no order, `filled = 0`, `runnerB = 0`, status `not_high_never_ordered` |
| when | `scheduler.py:1211` `within_orb_window = market_open and now_et.hour == 9 and now_et.minute < 45`; a pre-market HIGH subscribes and fires when the first bar closes; a HIGH first seen at/after 09:45 is `WINDOW_OUT_OF_ORB` (`scheduler.py:1266-1273`, never placed) | submit = max(first HIGH alert minute, 09:31); first HIGH alert ≥ 09:45 → `window_out_of_orb`, `filled = 0` |
| the ORB | the single 09:30–09:31 one-minute bar (`entry_pipeline.fetch_orb_bar_with_retry` → `alpaca_client.get_first_bar`) | the stored 09:30 bar; missing → unreadable |
| fade guard | `check_fade_guard` is a no-op for MAGNA53 — `live_tracker` passes `fade_midpoint_ratio=None` (CLAUDE.md §EP Detection) | nothing to model |
| real-time gap re-check | `entry_pipeline.check_rt_gap_floor` (step 4b, line 599): toggle `ep_rt_entry_gap_recheck` ON since 2026-08-02; floor `MIN_GAP_PCT` = **9.0 %** since 2026-08-19; fails OPEN on a missing price or denominator | (open of the submit-minute bar − prior close) / prior close < 9 % → `gap_below_floor`, `filled = 0`; missing bar → passes |
| ORB validity | `validate_orb_entry` (`backtester/filters.py:207`, called from `order_manager._build_order_spec`): zero range, or range > 1.5 × ATR-14-prior → `setup:stop_too_wide` | `study_orb_live.validate_orb_entry` + `compute_atr14_prior` (mirrors `alert_rank_shadow`, 40 calendar days, ≥ 10 prior rows else skipped) |
| the stop | `order_manager.py:620` `stop_loss_price = 2 * orb_low - orb_high` (entry − 2R) | `stop = 2L − H` — needed only for the chase cap |
| **#500 market-or-skip** | `order_manager.submit_entry._pick_entry` (lines 771–827): latest trade > ORB high → a LIMIT buy at `latest × 1.002`; the ask-aware arm (ON for live since 2026-08-07, `docs/setups/magna53_ep.md:2924`) does the same when the ask > ORB high | price at submission = the OPEN of the first stored bar at/after the submit minute (the finest grain stored; the ask is not stored, so ask ≈ last — an approximation, stated) |
| **the chase cap** | `_chase_cap_reason` (lines 829–839): `limit − stop > CHASE_RISK_INFLATION_CAP (1.5) × (orb_high − stop)` → `setup:chase_cap_exceeded`, NO order | same arithmetic → `chase_cap_skip`, `filled = 0` |
| the bracket | otherwise `place_bracket_order(stop = orb_high, limit = stop_limit_buy_price(orb_high))` — a stop-limit buy with the 0.5 %-or-$0.02 buffer (`order_manager.py:116`) | `study_orb_live.entry_walk` (mirrors `sustain_reject_replay.entry_walk`), bar by bar from submit |
| cancel | the 10:00 ET job `scheduler.py:2857` → `cancel_unfilled_entries("ORB window unfilled")` | no fill by 10:00 → `no_entry` |
| safeguards | `_check_safeguards` (LIVE_TRADING_ENABLED, /pause, max positions, daily loss, drawdown breaker) and sizing | **not modelled** — a safeguard-blocked name is treated as placed (his "blocked EPs are EPs"). A FILLED row means "today's path would have bought", not "would have executed regardless of the book" |

**Fills today's path CAN make — these and only these:**
1. stop-limit bracket: the first bar whose open is in [H, limit] → filled at that open; a bar opening
   below H whose high reaches H → filled at H; a bar opening above the limit arms the limit, and a
   later bar whose low reaches the limit → filled at the limit (a stop-limit that gapped through its
   limit rests until 10:00 and can fill on a pullback — real Alpaca behaviour, kept);
2. #500 marketable limit: price already above H at submission and inside the chase cap → filled at that
   bar's open (the limit sits 0.2 % above it).

**Fills today's path CANNOT make — and the replay never makes:** any fill for a row with no HIGH alert
(MODERATE, none, or rejected); for a HIGH first seen at/after 09:45; after 10:00 ET; beyond the 1.5×
chase cap; at a pullback to the limit when the price was already above H at submission (that case is
the #500 branch, which fills at once or skips — the pre-#500 pullback walk is not applied there).

**Frame B outcome:** `run_xadr_B = (max high from the fill minute through session +15 − FILL PRICE) /
ADR$` (same denominator as frame A; day 0 from `mi_intraday_bars`, +1..+15 from `mi_daily_closes`).
Unfilled rows have `runnerB = 0` — they are not excluded, exactly as #684 frame B did. Rows whose fill
window has bar gaps wide enough to hide a cross (`entry_walk` → `abstain`) or lack a 09:30 bar are
UNREADABLE: excluded and counted, never guessed.

**Two frame-B populations, both declared, so the admission confound is visible rather than hidden:**
- **B1** = every row with a frame-A outcome (the spec's frame: rows today's path never orders count 0).
  ⚠ Registered caveat: any feature correlated with the score or with admission (the score itself,
  catalyst grade, gap %) reads mechanically favourable in B1, because "HIGH" is the only way to a
  non-zero outcome. B1 therefore cannot CONFIRM on its own (§6).
- **B2** = the rows today's path PLACES an order for (HIGH, first HIGH tick < 09:45, both admission
  gates passed; `orderable = 1`) — selection among what we would actually buy. Expected to be thin (§7).

**Dry-run limitation, stated:** #684's `pop.tsv` carries only the FIRST live alert row's tier and
creation minute (and no alert rows at all before 05-11, where the scan PASS tick's tier stands in), so
the dry run on the old blocks approximates HIGH by that first row. Frame B on the old blocks is
therefore today's mechanics replayed, with no published number to match; frame A on the old blocks must
and does match `results.tsv` exactly (§11).

## 4. Runner definition

- **RUNNER = run ≥ 5 ADR within sessions +1..+15** (frame A: from the close; frame B: from the fill).
  Also reported: ≥ 8 ADR. Not tuned, not re-expressed in percent, not re-cut on the new block.
- Why ADR units and 15 sessions: #684's definition (the 09-27 H5 read), kept so the two blocks are one
  study. The known unit effect (≥ 5 ADR vs ≥ 25 % disagree on 38 of 667 old rows) is a limit, not a
  dial.

## 5. The 65 draws — the same 63 features, their frozen cut points, and the two reversed leads

Every feature below is computed by #684's `scripts/probes/_684/features.py`, run UNCHANGED on the new
block's captured files (`preregistered_read.py` imports it and points it at `_686/data/`). The dry run
proved the import reproduces the committed `features.tsv` byte for byte. Each row names the code block
in `features.py` (its section comment) that computes it. **Favourable** = the side declared in #684's
`study.py` docstring, unchanged. **Cut points** = terciles of #684's DISCOVERY rows (05-01..08-14),
recomputed deterministically from the committed `features.tsv` (`study.tercile_cuts`) and applied to the
new block unchanged — LOWER = value ≤ cut_lo, HIGHER = value ≥ cut_hi; booleans compare to the
favourable value; the ordinal catalyst grade = game_changer/strong vs routine.

| # | feature (plain words) | column | known when | favourable | cut_lo | cut_hi | computed in `features.py` |
|---|---|---|---|---|---|---|---|
| 1 | today's EP score ⚠ era-A cut on an era-B block: scale artefact | `ep_score` | scan tick | HIGHER | 36 | 60 | row init (`ep_score` from pop.tsv) |
| 2 | gap % at the scan | `PRE_gap_pct_scan` | scan tick | HIGHER | 12.16 | 16.29 | "scan-time / PRE features straight from the scan log" |
| 3 | prev close above its 5-day low close (live gate def) | `PRE_ext_5d_pct` | PRE | LOWER | 2.2082 | 7.6933 | "bar-derived features" |
| 4 | prev close vs SMA10, in ADRs | `PRE_ext_sma10_xadr` | PRE | LOWER | −0.1793 | 0.7882 | "bar-derived features" |
| 5 | prev close vs SMA20, in ADRs | `PRE_ext_sma20_xadr` | PRE | LOWER | −0.3984 | 1.0403 | "bar-derived features" |
| 6 | prev close vs SMA50, in ADRs | `PRE_ext_sma50_xadr` | PRE | LOWER | −0.6252 | 2.1748 | "bar-derived features" |
| 7 | mean distance to SMA10/20/50, in ADRs | `PRE_ext_ma_mean_xadr` | PRE | LOWER | −0.4172 | 1.2469 | "bar-derived features" |
| 8 | prev close above its 20-day low | `PRE_ext_20d_low_pct` | PRE | LOWER | 9.6904 | 22.9466 | "bar-derived features" |
| 9 | 1-month change before the gap | `PRE_chg_1m_pct` | PRE | LOWER | −4.1533 | 12.51 | "bar-derived features" |
| 10 | 3-month change before the gap | `PRE_chg_3m_pct` | PRE | LOWER | −4.5615 | 26.6071 | "bar-derived features" |
| 11 | 40-day close range / price (base tightness) | `PRE_base_range40_pct` | PRE | LOWER | 26.8164 | 44.0225 | "base / neglect" |
| 12 | 20-day close range / price | `PRE_base_range20_pct` | PRE | LOWER | 16.3469 | 27.9941 | "base / neglect" |
| 13 | net 40-day drift, in ADRs (flat base) | `PRE_base_absdisp40_xadr` | PRE | LOWER | 2.2463 | 4.7582 | "base / neglect" |
| 14 | sessions since the 6-month high (neglect) | `PRE_days_since_6m_high` | PRE | HIGHER | 14 | 66 | "base / neglect" |
| 15 | prev close below the 6-month high, % (depth) | `PRE_base_depth_6m_pct` | PRE | HIGHER | 13.0831 | 30.0735 | "base / neglect" |
| 16 | overhead to the 52-week high, in ADRs | `PRE_dist_52w_high_xadr` | PRE | LOWER | 3.6044 | 11.0296 | "base / neglect" |
| 17 | scan price above the 6-month high | `PRE_cleared_6m_scanprice` | scan tick | yes (1) | — | — | "supply cleared, PRE version" |
| 18 | scan price above the 52-week high | `PRE_cleared_52w_scanprice` | scan tick | yes (1) | — | — | "supply cleared, PRE version" |
| 19 | scan price above the all-time high | `PRE_cleared_ath_scanprice` | scan tick | yes (1) | — | — | "supply cleared, PRE version" |
| 20 | prev close above SMA50 | `PRE_above_sma50` | PRE | yes (1) | — | — | "bar-derived features" |
| 21 | prev close above SMA200 | `PRE_above_sma200` | PRE | yes (1) | — | — | "bar-derived features" |
| 22 | how many of SMA10/20/50 the prev close is above | `PRE_n_ma_above` | PRE | HIGHER | 1 | 3 | "bar-derived features" |
| 23 | Stage 2 (close > SMA50 > rising SMA200) | `PRE_stage2` | PRE | yes (1) | — | — | "bar-derived features" |
| 24 | RS composite the prior day | `PRE_rs_composite` | PRE | HIGHER | 32.3 | 81.2 | "scores / themes / regime / sector / repeat (PRE)" |
| 25 | in the RS pool the prior day | `PRE_in_rs_pool` | PRE | yes (1) | — | — | "scores / themes / regime / sector / repeat (PRE)" |
| 26 | catalyst grade (game_changer/strong vs routine) | `PRE_catalyst_ord` | scan tick | HIGHER (≥ 1) | — | — | "scan-time / PRE features straight from the scan log" |
| 27 | in an active theme the prior night (any age) | `PRE_themed` | PRE | yes (1) | — | — | "scores / themes / regime / sector / repeat (PRE)" |
| 28 | in an active theme the prior night (7-day bounded) | `PRE_themed_7d` | PRE | yes (1) | — | — | same |
| 29 | theme stage Nascent/Accelerating | `PRE_theme_early` | PRE | yes (1) | — | — | same |
| 30 | market regime Bull | `PRE_regime_bull` | PRE | yes (1) | — | — | same (regime row dated before the scan) |
| 31 | SPY vs its 50-day ⚠ a day-level feature; a week-block permutation cannot test it (#684 VERIFIED) | `PRE_spy_vs_50ma` | PRE | HIGHER | 2.62 | 6.26 | same |
| 32 | share price | `PRE_prev_close` | scan tick | LOWER | 18.06 | 66.6 | "scan-time / PRE features straight from the scan log" |
| 33 | ADR % | `PRE_adr20_pct` | PRE | HIGHER | 4.4901 | 6.4167 | "bar-derived features" |
| 34 | 20-day dollar volume | `PRE_dollar_vol_20d` | PRE | LOWER | 3.2458e7 | 1.6391e8 | "bar-derived features" |
| 35 | a scored gap on this name in the prior 90 days | `PRE_repeat_scored_90d` | PRE | no (0) | — | — | "scores / themes / regime / sector / repeat (PRE)" |
| 36 | pre-market relative volume | `PRE_pm_rvol` | scan tick | HIGHER | 3.867 | 9.226 | "scan-time / PRE features straight from the scan log" |
| 37 | projected volume multiple at the scan | `PRE_projected_vol_multiple` | scan tick | HIGHER | 3.3 | 6.2 | same |
| 38 | first scored tick before 09:30 ⚠ mechanical in frame B: it predicts window, not outcome (#684 addendum) | `PRE_first_tick_preopen` | scan tick | yes (1) | — | — | same |
| 39 | gap % at the open print | `O930_gap_open_pct` | 09:30 | HIGHER | 8.7855 | 14.6654 | "0930: the open print" |
| 40 | open above the 6-month high | `O930_cleared_6m_open` | 09:30 | yes (1) | — | — | "0930: the open print" |
| 41 | open above the 52-week high | `O930_cleared_52w_open` | 09:30 | yes (1) | — | — | "0930: the open print" |
| 42 | open above the all-time high | `O930_cleared_ath_open` | 09:30 | yes (1) | — | — | "0930: the open print" |
| 43 | open vs SMA50, in ADRs | `O930_ext_open_sma50_xadr` | 09:30 | LOWER | 1.8108 | 4.6732 | "0930: the open print" |
| 44 | open vs SMA20, in ADRs | `O930_ext_open_sma20_xadr` | 09:30 | LOWER | 1.6660 | 3.6377 | "0930: the open print" |
| 45 | Stage 2 with the open | `O930_stage2_open` | 09:30 | yes (1) | — | — | "0930: the open print" |
| 46 | where 09:44 sits in the opening range | `O945_orb_position` | 09:45 | HIGHER | 0.3167 | 0.7572 | "0945: opening range" (≥ 12 of 15 bars) |
| 47 | opening range / ADR | `O945_orb_range_xadr` | 09:45 | LOWER | 1.3233 | 2.0053 | "0945: opening range" |
| 48 | gap % at 09:44 | `O945_gap_0945_pct` | 09:45 | HIGHER | 10.2919 | 16.4043 | "0945: opening range" |
| 49 | 09:44 vs the open | `O945_close_vs_open_pct` | 09:45 | HIGHER | −1.5023 | 3.6390 | "0945: opening range" |
| 50 | first-15-minute volume / 20-day avg daily volume | `O945_orb_vol_vs_20d` | 09:45 | HIGHER | 0.2810 | 0.4829 | "0945: opening range" |
| 51 | opening-range high above the 6-month high | `O945_orb_high_above_6m` | 09:45 | yes (1) | — | — | "0945: opening range" |
| 52 | close location in the day's range | `CLOSE_close_loc` | close | HIGHER | 0.3070 | 0.7067 | "CLOSE: the gap-day bar" |
| 53 | day range / ADR | `CLOSE_range_xadr` | close | HIGHER | 1.9047 | 2.9858 | "CLOSE: the gap-day bar" |
| 54 | volume vs the biggest day in a year | `CLOSE_vol_vs_max250` | close | HIGHER | 0.3714 | 0.6978 | "CLOSE: the gap-day bar" |
| 55 | volume vs 50-day average | `CLOSE_vol_vs_avg50` | close | HIGHER | 2.3054 | 3.7649 | "CLOSE: the gap-day bar" |
| 56 | close vs open | `CLOSE_close_vs_open_pct` | close | HIGHER | −1.7976 | 4.1438 | "CLOSE: the gap-day bar" |
| 57 | gap % at the close | `CLOSE_gap_close_pct` | close | HIGHER | 8.8776 | 17.1742 | "CLOSE: the gap-day bar" |
| 58 | close vs SMA50, in ADRs (the 09-27 EOD lead) | `CLOSE_ext_sma50_xadr` | close | LOWER | 1.8898 | 5.0530 | "CLOSE: the gap-day bar" |
| 59 | close vs SMA20, in ADRs | `CLOSE_ext_sma20_xadr` | close | LOWER | 1.7722 | 4.2700 | "CLOSE: the gap-day bar" |
| 60 | close above the 6-month high | `CLOSE_cleared_6m` | close | yes (1) | — | — | "CLOSE: the gap-day bar" |
| 61 | close above the 52-week high | `CLOSE_cleared_52w` | close | yes (1) | — | — | "CLOSE: the gap-day bar" |
| 62 | close above the all-time high | `CLOSE_cleared_ath` | close | yes (1) | — | — | "CLOSE: the gap-day bar" |
| 63 | unscheduled catalyst (alerted rows only; BACKFILLED field, may carry hindsight — #684 VERIFIED) | `ALERT_expct_unscheduled` | alert | yes (1) | — | — | `study.main` inline derivation from `ALERT_expct_scheduled` (replicated in `derive_alert_unscheduled`) |

"Known when" tags follow #684's VERIFIED correction: "scan tick" draws are read at the chosen tick
(07:00–09:55), not strictly pre-open. CLOSE draws are valid for a day-2+ entry only; they are read in
frame A for continuity and carry no claim about the 09:31 entry.

**The two reversed leads (L1, L2) — worded as the #684 VERIFIED section requires, direction fixed now:**

| lead | wording (the prediction) | the third | statistic | declared sign |
|---|---|---|---|---|
| **L1** | **the quietest third runs LESS** — names in the bottom third by 20-day close range as % of price have a LOWER runner rate than the other two thirds | `PRE_base_range20_pct ≤ 16.3469` (frozen cut) | rate(quietest third) − rate(rest) | NEGATIVE |
| **L2** | **the widest gap-day-range third runs LESS** — names in the top third by gap-day range in ADR units have a LOWER runner rate than the rest | `CLOSE_range_xadr ≥ 2.9858` (frozen cut) | rate(widest third) − rate(rest) | NEGATIVE |

Neither is worded "already moving runs more". **ADR % controlled, operationalised in ONE way:** strata =
terciles of `PRE_adr20_pct` by the frozen discovery cuts (≤ 4.49 · 4.49–6.42 · ≥ 6.42); the controlled
statistic is the stratum-size-weighted mean of the within-stratum (third − rest) differences; its
permutation shuffles labels within (ISO week × ADR stratum). The raw (uncontrolled) version is reported
beside it; only the controlled version decides. `CLOSE_range_xadr` is already in ADR units; it is
stratified anyway so the two leads are read the same way.

## 6. The test, the bar, and the exact pass/fail rule

**Per draw, the statistic** (unchanged from #684): favourable group vs the rest, runner rate each, the
difference; AUC reported for the frozen leg.

**Permutation:** runner labels shuffled WITHIN the ISO week of the scan date (week-block), 2,000 draws.
Seed **684** for the frozen discovery legs (so they reproduce #684 exactly); seed **686** for the
new-block leg, one generator shared sequentially in `DRAWS` order (frame A, then B1, then B2 for each
feature), and seed 687 for the leads. Both tails are taken from the same shuffles: p(declared) =
share of shuffles with difference ≥ observed; p(reverse) = share ≤ observed.

**The four-condition bar, exactly as #684 defined it, with the new block as the held-out leg:**
1. **discovery p < 0.05** in the declared direction — FROZEN from #684 (DISCOVERY = scan dates
   05-01..08-14, 604 bar-tested rows); the script recomputes it from the committed `features.tsv` +
   `daily.tsv.gz` and ASSERTS equality with `results.tsv` (n_disc, n_fav, p_disc, drop-week p, drop-two
   p); a mismatch aborts the read as INVALID;
2. **same sign on the held-out block** — now the September block; a held-out read with **fewer than 3
   runners in the block, or fewer than 8 rows on either side**, reads "can't tell (thin)" and cannot pass;
3. survives dropping the discovery ISO week with the most runners (**W19**, frozen) — same sign and p < 0.05;
4. survives dropping the two largest discovery runs (**UMC 05-06, CRSR 05-08**, frozen) — same sign and p < 0.05.

**Added for this block, because it can carry a p where #684's 4-runner held-out could not:** the
new-block leg has its own permutation p (seed 686). Condition 2 is reported as #684 wrote it (sign only,
column "#684 bar") AND the stricter form below decides.

**Verdict per draw, frame A — one of these, in this order of checking:**
- **no data** — fewer than 30 discovery rows with the feature, or every new-block row falls on one side
  of the frozen cut;
- **can't tell (thin)** — the block holds < 3 frame-A runners, OR the favourable group < 8 rows, OR the
  rest < 8 rows;
- **CONFIRMED** — conditions 1, 3 and 4 all hold (frozen) AND on the new block the favourable−rest
  difference > 0 AND p(declared) < 0.05;
- **HOLDS (report only)** — on the new block difference > 0 AND p(declared) < 0.05, but conditions 1,
  3, 4 do not all hold. This is a NEW lead for a third block, never a finding;
- **AGAINST** — on the new block difference < 0 AND p(reverse) < 0.05;
- **can't tell** — anything else.

**For L1 and L2** the same vocabulary, with: conditions 1, 3, 4 = the ADR-CONTROLLED statistic on the
frozen discovery rows (negative sign, p(less) < 0.05 on all rows, without W19, without UMC+CRSR), and the
new-block leg = the controlled statistic on the block (negative sign and p(less) < 0.05 → CONFIRMED if
1/3/4 hold, else HOLDS report-only; positive and p(more) < 0.05 → AGAINST).

**Frame B (B1 and B2):** the same thin rule and the same new-block statistic on `runnerB`; frame B carries
NO discovery leg (#684's published frame B used the pre-#500 walk and any-tier passes — not comparable),
so its verdicts are **HOLDS (report only) · AGAINST · can't tell · no data**, never CONFIRMED. A frame-A
CONFIRMED feature is reported to him with its B1 and B2 readings beside it; a frame-B HOLDS alone is a
lead for a third block.

**What counts as "none hold":** zero CONFIRMED across the 65 frame-A draws. HOLDS-only draws do not
change that answer; they are listed as leads.

**Multiplicity, stated before the data:** 65 draws × 0.05 ≈ 3.3 HOLDS by chance; up to 3 HOLDS is noise.
CONFIRMED is only reachable by draws whose frozen conditions 1, 3 and 4 already hold. **On the frozen
data that is exactly two of the 63: ADR % (`PRE_adr20_pct`: p 0.020 / 0.029 / 0.010) and 20-day dollar
volume (`PRE_dollar_vol_20d`: p 0.010 / 0.001 / 0.007).** Share price clears 1 and 3 but not 4 (drop-two
p 0.053) and can reach HOLDS at most. **Neither lead can reach CONFIRMED:** L1's controlled discovery
leg is −1.0 pp, p(less) 0.383 (the "quietness" reversal was ADR % — the #684 VERIFIED section's own
warning, now a number); L2's controlled discovery leg clears (−4.9 pp, p 0.029) and survives dropping
UMC+CRSR (p 0.018) but not dropping W19 (p 0.079). So the expected number of chance CONFIRMED verdicts
is about 2 × 0.05 = 0.1, and the honest prior for this read is "none hold" unless ADR % or dollar volume
repeats. The leads are read on the new block as report-only, as are any new HOLDS.

**Co-primary check — his labelled EPs:** every name in `docs/methodology/operator_labelled_eps.md` with an
EP date inside the block is reported per draw as "in the favourable group: yes/no" — where they sit,
never whether they are runners. Today (2026-10-04) that list holds none in the block (latest: CHPT
09-03). Names he labels BEFORE the run date enter the check; a label added after the run cannot change
any verdict (it may be added to the report as a note, dated).

## 7. Expectations written before the data (what the composition and the frames should look like)

- **Rows:** 15 sessions × roughly 5–8 scored candidates a day → ≈ 75–120 rows (#684 averaged 7.8/day
  05-01..09-03; its era-B tail 09-01..09-03 ran 5/day). All era B. Alerted (any tier) ≈ 20–30 % of rows
  (09-01..09-03: 3 of 15); HIGH alert rows whose first HIGH alert is before 09:45 ≈ 10–25 rows.
- **Frame-A runners:** at #684's 10.6 % base rate, ≈ 8–12. **If the block holds fewer than 3 the whole
  read is "can't tell (thin)" and says so first** — that is a sample-size result, not a null.
- **Frame B2** is expected thin by construction (≈ 10–25 orderable rows, 0–3 runners_B): most B2 verdicts
  will be "can't tell (thin)". That prediction is made here so a thin frame B is read as the registered
  expectation, not as evidence of anything.
- **Alarms, checked by whoever runs the read on STEP 0's printout BEFORE reading on** (the script aborts
  on the first by itself; the rest are figures it prints): a scan date outside 09-04..09-25 in the pull;
  a row count outside 40–200; fewer than 5 HIGH rows in the whole block (would mean the HIGH columns
  did not join); more than 3 rows without 20 prior sessions; 09:45 minute coverage below 80 %. Any of
  these → investigate the pull (`extract.sh`), fix the PULL, re-pull, re-run; the registration and the
  read's code do not change.

## 8. What the read may NOT do

- Re-tune anything: the 5-ADR runner bar, the 0.05 alpha, the tercile cuts, the thin rule, the 15-session
  horizon, the 09:45 window, the 9 % floor, the 1.5× cap, the seeds, the number of permutation draws.
- Add, drop, re-sign or re-word a feature or a lead; move a feature between frames; re-cut on the block.
- Drop, re-label or re-date any row after an outcome is visible. Censored rows are counted, not filled.
- Change the block (its dates or the dedupe rule), the HIGH definition, the submit-time rule or the
  price proxy. If a data defect is found, the PULL is fixed and STEP 0 re-run; the rule is not.
- Run more than once on the block. The first complete run's `out/686_*` files are the record; a re-run is
  allowed only to reproduce them byte for byte after a pull fix, and says so.
- Read a frame-B HOLDS, a HOLDS-only frame-A draw, or a descriptive line as a finding. Only CONFIRMED is
  a finding; everything else is a lead or a description.
- Edit this document or the script after 2026-10-16. The script hashes both and refuses on any change.

## 9. What this does not answer

- **Whether a feature that is CONFIRMED here is a selection rule.** Two blocks agreeing on one of 65
  draws is evidence worth his eye, not a rule; a third block and a cost read (what it would have
  excluded — P14's asymmetry) come before any proposal to act.
- **Power.** A block of ≈ 100 rows with ≈ 10 runners can confirm a large effect (a tercile running at
  ~20 % vs ~5 %) and little else; most "can't tell" verdicts will be exactly that.
- **The never-scored class** (the top-20 gap cap, `mcap_too_small`) — #617/#624.
- **Frame B's approximations:** the ask is not stored (ask ≈ last); the real-time price is a bar open;
  portfolio safeguards and sizing are not modelled; `abstain` rows are excluded.
- **Why a lead fails.** If ADR % or dollar volume does not repeat, this read cannot say whether the May
  cluster carried it or the effect is period-specific; it can only say it did not repeat.
- **Catalyst content** (surprise vs expectation): unmeasured beyond draw 63, which is backfilled and
  alerted-only.
- **The ep_score draw on an era-B block** is a scale artefact by construction (§2) and is reported, not read.

## 10. What the proposal for his ruling MAY say (the template — not a result)

One paragraph, written after the run, in plain words, every number with its n:
- If **none hold** (zero CONFIRMED): "No gap-day feature repeated out of sample; the leads from #684
  (ADR %, dollar volume, the two reversed leads) read [sign, n, p] on the September block. No change to
  the score or admission is supported. [HOLDS-only draws, if any, named as leads for a third block.]"
- If **a feature is CONFIRMED**: "[Feature] held out of sample: discovery [rate vs rate, p], September
  block [rate vs rate, n, p], frame B1 [..], B2 [..]. Three options are his: a third block, a cost read of
  what the favourable third excludes, or nothing. Any change to score or admission is CHANGE_PROCESS
  and his call." The paragraph never proposes a threshold.

## 11. Dry-run record (2026-10-04, local, #684's captured files only, `--dry-run-old-block`)

- **Frame A reproduces #684 exactly:** on all 63 bar-tested draws the recomputed n_disc, n_fav,
  discovery p, drop-week p and drop-two p equal `results.tsv` to 4 decimals, and with #684's own
  held-out (08-15..09-03, n = 63 rows, 4 runners) the held-out n/sign and every verdict match the
  published ones — including the single PASS (`PRE_dollar_vol_20d`). The import of `features.py` with
  a redirected data directory reproduced the committed `features.tsv` byte for byte.
- **Frame B machinery runs** on the old held-out under today's mechanics: of n = 63 rows, 46 never
  ordered (no HIGH alert row — 17 HIGH, of which 13 inside the window; 1 scan-tick HIGH was a judge
  demotion), 4 window_out_of_orb, 2 gap_below_floor, 1 orb_invalid, 1 abstain; 9 orderable, 8 filled (6
  stop-limit bracket, 2 market-or-skip limit), 1 no_entry, 1 runner_B. No published number exists for
  this (see §3 dry-run limitation) — it proves the code path, not a reproduction.
- **Leads on the frozen discovery rows** (the numbers §6 relies on): L1 raw n = 201 quietest at 6.5 % vs
  403 at 13.4 %, p(less) 0.006; controlled −1.0 pp, p 0.383. L2 raw n = 202 widest at 7.4 % vs 402 at
  12.9 %, p(less) 0.007; controlled −4.9 pp, p 0.029; drop-W19 p 0.079; drop-UMC+CRSR p 0.018.
- **Refusals verified:** the read without flags exits 3 (calendar gate, today 2026-10-04 < 2026-10-17);
  `--no-freeze-check` without the dry-run flag exits 3 at the same gate and would exit 2 after it;
  `extract.sh` exits 3 before the date.
- Files: `scripts/probes/_686/out/dryrun_results_out.txt`, `dryrun_cuts.tsv` (the frozen cut table above),
  `dryrun_outcomes.tsv`, `dryrun_summary.json`.

## THE LINE

Registration only. No strategy, score, threshold, admission rule, stop, size, safeguard or live trade
state was changed or is proposed as decided. No prod query, no ssh, no LLM call, no paid API, no deploy,
no PLAN.md edit was made in writing this. The read, when it runs, is read-only and $0.

<!-- FREEZE -->
## Freeze record

The read verifies these before it runs and refuses on any mismatch. The "doc body" hash covers every
byte of this file ABOVE the `<!-- FREEZE -->` marker.

- script sha256: `c30d76a62ae6a30a600e57664ec3cc72a19f50c74db0896906a032ce72476b8e` — `scripts/probes/_686/preregistered_read.py`
- extract.sh sha256: `a27b2f812db3779a253e550cf97498c13c4b17455e48f87512556eaa6803fe4e` — `scripts/probes/_686/extract.sh`
- doc body sha256: `b69c8e54fcc5e59ae2511e674dd8536e1a782982bf90c10015389641aa779f03` — this file above the marker
- freeze commit: the commit that added this file on branch `686-preregistration` (`git log --follow -- docs/analysis/686_preregistration_2026-10-04.md`)
