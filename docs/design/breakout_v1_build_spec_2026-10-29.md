# Breakout v1 — PAPER build spec (for the Fri 2026-10-30 build; Opus builds, Opus reviews; deploy in the 21:15 ET window)

Owner of the rules: `docs/setups/consolidation_breakout.md` (2026-10-28 entries "v1 FINAL" and "his PAPER GO"). This file is
the build plan only; every rule below is quoted from there, and the SSoT is updated in the same commit as the code.

**What his rules are (unchanged here):** RS = best of the 21 / 63 / 126-session return percentiles ≥ 98 the night before ·
universe raw close ≥ $2, 20-session median dollar volume ≥ $5M · prior move and higher lows as the SSoT rows · NO base anchor ·
level = the highest high of the last 5 sessions, strict · surf = 5+ sessions in a row with the low within 1.0 ADR of one of
the 10 / 20 / 50-day · tightening = last 5 sessions' mean range ≤ 1.1× the 5 before · breakout volume ≥ 1.2× the 50-day ·
entry `orh5` in regular hours · stop = the day's low at the fill, abstain beyond 1 ADR · exit = the `pp` arm · size = EP's ·
his grade = a label on a running list, never a gate.

## Two forks that were HIS (entry discipline / safeguards — THE LINE) — RULED 2026-10-29 ("ok" to both recs): F1 (a), F2 (a)

| # | Fork | Options | Rec |
|---|---|---|---|
| F1 | Breakout volume is only known at the close, but `orh5` buys during the day | (a) volume so far vs the stock's normal volume BY THAT MINUTE ≥ 1.2× (an intraday volume curve measured once from stored minute bars), checked when the buy triggers · (b) EP's linear projection (raw × 390 / minutes since open — passes almost every early break, too loose for a 1.2× bar) · (c) no check at the buy; the close-volume is recorded as a label | (a) |
| F2 | The paper book's position cap (shared with the #624 small-cap paper lane) | (a) share the paper book's 5 · (b) its own 5 (`mi_strategies.max_concurrent_positions`) | (a) |

## Components (build order = priority; B1–B4 are the minimum for Monday's first list, B5–B7 for Monday's first fill)

**B1 — the rules, PURE (`agents/market_intelligence/breakout_v1.py`, new).** `v1_gates(bars, D, *, rs_best) -> dict` returns
each gate's pass/fail and value plus `level`, `adr20`, `pole` facts, by CALLING `consolidation_breakout` (`cb`) primitives
(`_pole_top`, the higher-lows and prior-move helpers, `_sma_at`, ADR20) — `cb` is sha-pinned (`runner.EXITPB_MODULE_SHA`) and
is NOT edited. The surf / tightening / volume / level / universe arithmetic is ported from
`scripts/probes/_qm_0810_review/v1_check.py` + `v1_check_variant.py` (V3 + RSbest), not re-derived.
- **Parity test (the acceptance bar):** a committed fixture of the 2019-01-02..2020-08-10 daily bars for the 24 dated good
  setups' tickers (+ the RS cross-section rank each needs, precomputed by the probe — CI has no `apollo_data`, memory
  `green-pre-push-is-not-green-ci`) → `v1_gates` reproduces `v1_check_variant_rs.txt` exactly: 12 of 24 caught on his day or
  1–2 sessions late, and the per-gate miss table. A mismatch is a defect in the port, never a reason to move a threshold.

**B2 — the nightly list (job `breakout_v1_list`, 17:55 ET mon–fri, after the 17:48 shadow).** Universe from `mi_daily_closes`
+ `mi_security_types` at the v1 floors ($2 / $5M) — common stock + ADRs + SINGLE-ASSET funds (his 10-29 ruling: `ETV` minus leveraged / inverse and multi-asset baskets, derived from the fund names in the ticker reference, the kept and excluded lists printed in the build's output and pinned by a test for his check; ZCSH must be kept); RS cross-section over THAT universe (`cb.cross_section_one_date`'s
`rs_best`, measured at D exactly as the probe did); `v1_gates` per name; every passing name → `mi_breakout_v1_list`
(scan_date, ticker, level, adr20, rs_best, every gate value as JSON, list_rank by rs_best). ~4 names a night (the check's
3.7). One audit row `breakout_v1_list_run` (n universe / n passing / per-gate fail counts). SILENT except a job failure.
Not a step inside the shadow job — that job runs under its own budget and is a pinned recorder; a separate job cannot starve
it.

**B3 — the running list + grade (Telegram, orchestrator scope).** After B2, ONE paper-prefixed message: tonight's names
(ticker, level, rs_best, the chart link the briefing already builds) — only when the list is non-empty
(`an-alert-that-says-no-action-is-noise`). `/bgrade TICKER A+|A|B|C|skip [note]` writes `mi_breakout_v1_grades`
(scan_date defaults to the latest list containing the ticker); `/bgrade` alone lists ungraded names from the last 5 nights
(his "if I miss a day or two I'll catch-up"). A grade never gates an entry. A new slash command lives in THREE places or it
is invisible (`docs/architecture/market_agent_reference.md`) — deploy `both` + `execution`.

**B4 — the strategy row and the four paper walls (mirror `broker/lowcap_paper_entry.py`, #624).** `mi_strategies`
'breakout_v1': phase 'paper', enabled, `position_size_multiplier` 1.0, `max_concurrent_positions` per F2 (NULL under the rec).
Walls, each test-pinned: (1) reads only `mi_breakout_v1_list`, never `mi_ep_alerts`; (2) refuses the run unless the row is
phase 'paper' and resolves to 'paper'; (3) `submit_trade_entry(require_account_mode='paper')`; (4) every order's COID is
`make_client_order_id('paper', 'breakout_v1', ticker)`. Stop switch: runtime toggle `breakout_v1_paper` (mi_safeguard_state,
global) + `mi_strategies.enabled`; LIVE_TRADING_ENABLED=false stops it.

**B5 — the entry (paper; execution-owned job, 09:35–15:55 ET each minute, list names only).**
- At 09:35 (the 5-minute opening range closed): ORH5 / ORL5 from the 09:30–09:34 minute bars; `level = max(ORH5, list level)`
  (`cb._entry_one`'s `orh5`); abstain by name when the first five minutes are missing (`no_opening_range_minutes`).
- The order: a stop-limit buy at `level` (limit `stop_limit_buy_price`), DAY, OTO with the protective stop at the day's low so
  far. **His stop is the day's low AT THE FILL**, so while the buy is unfilled the minute job re-prices the stop leg to each new
  day's low (cancel + replace, same COID family) and CANCELS the buy with `setup:stop_too_wide` once `level − day low > 1 ADR20`
  (`cb._finish_entry`'s width rule). This is the rule as written, not a choice.
- F1's volume check runs at the trigger: under the rec the buy is only live while volume-so-far ≥ 1.2× the stock's normal
  volume by that minute; the curve (cumulative share of a day's volume by minute, from stored minute bars) is measured once and
  committed with its source query.
- The #500 price-aware submit applies (a price already past `level` buys at latest × 1.002 within the 1.5× risk cap).
- Sizing = EP's (`order_manager.prepare_orb_order`'s risk_pct × equity / (fill − stop), the regime multiplier, the 20% notional
  cap) with the stop above — a `spec_builder` for `submit_trade_entry`; the funnel needs a `bar_fetcher` argument (default =
  today's `fetch_orb_bar_with_retry`, byte-identical for EP / 9M) so this caller hands it the 5-minute range instead.
- One trade per list name per day (the funnel's dedupe); unfilled at 15:55 → cancelled (the 10:00 cancel is EP's and is NOT
  applied to `breakout_v1`).

**B6 — the exit: the `pp` arm on the paper book.** Stamp `exit_rule='breakout_pp'` at insert (the #687 B stamp path). The
nightly tracker maps `consolidation_breakout_pp`'s walk onto the live machinery: a third at +2R (the existing intraday profit
scan), else at the session-3 close ONLY when that close is above the fill (the 15:45 partial job); after any third the stop moves
to the fill; the rest sells at the next open after the first close under the 20-day (the paper DAY market order of #687 option
(c)); the stall cut — no +1R by the session-3 close → all of it at that close. **Equality test:** on random paths, the live
mapping's decisions equal `consolidation_breakout_pp.walk_pp` (arm `pp`) event for event (the pattern `tests/test_cb_pp_recorder.py` uses).

**B7 — SSoT + verify.** `consolidation_breakout.md` change-log entry with EXPECT (baseline: 0 list rows, 0 breakout paper
trades), DONE-WHEN, WOULD-FAIL-IF, VERIFY-LIVE; `docs/SSoT.md` row updated (the paper path); PLAN task "breakout v1 paper"
filed when #711 closes (count flat).

## Cut lines (if Friday runs short — ship in this order, never a half-built order path)
1. B1 + B2 + B3 + B4 (list + grade, no orders) — Monday's first list is real; entries wait.
2. + B5 + B6 together (an entry never ships without its exit).

## Deploy (21:15 ET Fri): `bash scripts/deploy.sh execution`, poll the box, then `bash scripts/deploy.sh both`. Pre-deploy:
diff the running image against origin/main (`read-the-delta-before-an-execution-deploy`).
