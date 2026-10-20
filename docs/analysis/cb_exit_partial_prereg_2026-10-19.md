# #702 — his partial and the stop after it: the day-based third only in profit, then the WHOLE-TRADE breakeven stop — pre-registration (2026-10-19, BEFORE any outcome of these arms)

**Why.** The hourly-close read (2026-10-19) showed the exit, not the stop, costing his own example: TSLA 2020-06-01 (bought
$58.37, stop $56.94 = that day's low, never hit) sold a third at the day-3 close BELOW cost ($57.63 on 06-04), moved the stop
up to cost, and the 06-05 dip ($57.75) took the rest out at cost — −0.17R — before the run to $68 by 06-10. Asked whether
his "sell a third after 3–5 days" applies only when the trade is in profit, the operator (2026-10-19): *"Yes, and maybe we
need to vary the stop adjustment, can we try adjusting stop so the whole trade is breakeven after taking the partial?"*, then
*"Wait , with 2r profit the original stop will be breakeven for the trade"* and *"This makes more sense given original stop
is where the pattern would fail"*. $0; no paper, no live; exit rules for money are his.

**What is decided by whom.** His "Yes" is a RULING on what his rule is: the day-based third sells only in profit (`pp` below)
is adopted, not tested. The TEST is his proposal on the stop: after the third, the stop goes where the whole trade nets zero
(`wbe`), instead of to the entry price. At a third sold at +2R the two coincide with the original stop (his point); at a
session-3 third sold in profit below +2R, `wbe` sits between the original stop and the entry. The reading "the stop stays at
the original stop after ANY third" (his "where the pattern would fail") is reported beside (`pp_s0`), never deciding.

## Method / population

- **Entry, stop, cells, periods — unchanged:** under ORH5 (the hourly-close RESULT's registered consequence): level `tl`, entry
  ORH5, the low-of-day stop no wider than one ADR20, the spec key's first break per base — the P5 trade population exactly (the
  pinned `trades_{discovery,pre,holdout}_p5.tsv.gz` fills). Only the EXIT changes, so every arm walks the SAME fills and the
  comparison is per trade. Periods: 2022-03..2024-12 (discovery) DECIDES; 2017-03..2021-12 beside; 2025-01..2026-10 descriptive
  (read once). C1 decides; C0 = the mechanism at scale (see Consequence).
- **Arms.** Common to all (exactly as `c3_p33_t20_cut3`): a 1/3 partial; the +2R leg (a high at fill + 2R sells at it, a gap open
  above it at the open, day 0 on the minutes); the staller cut (no +1R by the session-3 close → everything sold at that close,
  before any session leg); the 20-day trail filled at the next open; R against the entry stop; horizon 120. Per session the
  module's order is kept: gap partial, the stop in force BEFORE the session, the +2R leg, the reach / cut test, the session leg,
  the trail.
  - `A` = `c3_p33_t20_cut3`, the control: session leg = the session-3 close whatever the price; after any third the stop =
    max(stop, fill) from the next session (day 0: from the next minute).
  - `pp` = **his ruling**: the session leg sells the third only on a session-3 close ABOVE the fill; skipped otherwise (no sale,
    the stop does not move; the +2R leg stays armed). After a third the stop = max(stop, fill), as `A`.
  - **`pp_wbe` = `pp` + his proposal — the PRIMARY:** after a third sold at price p, the stop = max(stop0, min(fill, fill −
    (p − fill) ÷ 2)) — the level at which the two thirds left lose exactly what the third made, never below the original
    stop, never above the fill — resting from the next session; on day 0 the minute walk after a day-0 +2R third keeps stop0
    (the module's `day0_walk_target(breakeven=False)`, since p = fill + 2R gives exactly stop0).
  - Beside, never deciding: `wbe` (A's partial rule + the `wbe` stop; a below-cost third is capped at the fill, i.e. as `A`);
    `pp_s0` (`pp` with the stop left at stop0 after ANY third, day 0 included); `pp5_wbe` (the session leg = the FIRST close in
    sessions 3–5 above the fill, then the `wbe` stop).
  - **The trail when the session-3 third is skipped (every `pp`-family arm):** trail_live(j) = a third has sold OR j ≥ 3 — the
    session-3 close itself is tested against the 20-day, the same close `A` tests (A always has its third by then unless
    stopped or cut); a trail signal then sells EVERYTHING left at the next open. `pp5_wbe` uses the same j ≥ 3 rule.
- **Build (registered).** `consolidation_breakout.py` stays byte-identical (sha256 `e14027be…`, the live shadow's module). The
  arms run on a RUNNER-side copy of `walk_exit`'s qm path with flags for the session-leg rule and the post-partial stop rule,
  dispatched like `walk_his_arms`, reusing the module's `day0_walk_target`, `day0_peak_high` and `day0_target_to_outcome`
  unchanged. The copy emits `(j, "stop_to", level, 0.0)` on every stop move (excluded from the parity event comparison).
  **Parity, before any new-arm number (a mismatch exits non-zero and writes no report):** P1 — the copy with every flag off, on
  `A`, equals the pinned `trades_{discovery,pre,holdout}_p5` rows in all three periods (status, maturity, sessions_held,
  partial kind and session, realized R to 1e-9); P2 — on the hourly-close fills, `A` re-walked by the copy (day 0 from
  `walk_from` on the early-close-trimmed minutes) equals `trades_{period}_h60.tsv.gz`'s `h60` / `lod` / `c3_p33_t20_cut3` rows.
- **Reach, from `A`'s already-read rows (no new outcome):** 2022–24 C1 n = 79 trades; 34 take a third (17 +2R later, 12 +2R on day 0,
  5 at the session-3 close); only the 24 that `A` stopped AT COST after the third can differ under `pp_wbe` (in 14 of the 23
  months); `pp` alone changes only session-3 thirds sold at or below the fill (C1 1, C0 ~112). C0: 8,984 trades, 1,943 movable (2,874 take a third).
  **So CAN'T TELL is the expected C1 result**, and C0 is the powered read. The TSLA case itself is an hourly-close fill (under
  ORH5 that base traded 05-18) in 2017–21 — absent from the deciding trades.
- `A`'s `be_above_close` (the stop above the close after a third): from a session-3 third sold below cost (2022–24 C1 1 / C0
  112; 2017–21 0 / 170) or a +2R third on a bar closing under the fill (C1 1 / C0 27; 2017–21 0 / 48). Impossible under
  `pp_wbe` / `pp5_wbe`; under `pp` the +2R kind remains and is counted.

## Bars (2022–24; `tl`; ORH5; mature walks; month-block bootstrap on the FILL month, 2,000 resamples, seed 702; n first)

- **The deciding exit bar — the stop change:** per trade Δ = R(`pp_wbe`) − R(`pp`) (the ruled rule, with vs without his stop),
  n floor 30 trades, a trade with an open mark on either arm excluded and counted. On **C1**: lower end > 0 → `wbe` WINS; upper
  end < 0 → `wbe` LOSES; else can't tell. On **C0** the same Δ and interval, read only when C1 can't tell (see Consequence).
- Reported, never deciding: Δ(`pp` − `A`) (his ruling's effect), Δ(`pp_wbe` − `A`), Δ(`pp_s0` − `pp`), Δ(`pp5_wbe` − `pp_wbe`),
  `wbe` vs `A`; per arm × cell × period: n, win rate, average win / loss, mean R and interval, ≥ 5R / ≥ 10R / ≥ 20R per 100, total
  R, top-2% share, ADR P&L, median sessions held, the share partialled and how, the share stopped after the third at or below the
  fill, the ≥ 10R overlap with `A`.
- **The cell verdict under `pp_wbe`** (whether the SETUP passes with his exit) — the hourly-close read's bars word for word: PASS =
  n ≥ 30, interval lower end > 0, ADR P&L > 0, beats C0 under the same exit on mean R AND the ≥ 5R share, and the ≥ 10R trades
  from ≥ 3 tickers AND ≥ 3 months counting only stops ≥ 0.25 ADR20 wide; FAIL = n ≥ 30 AND (upper end < 0 OR not beating C0 on
  mean R); else CAN'T TELL.
- **Expectations, fixed now (an expectation that fails changes no rule; reported first):** C0 Δ(`pp_wbe` − `pp`) ≥ 0 at the
  point estimate (it keeps runners that the entry-price stop took out; it costs only on trades that fall from the third to the
  original stop); median sessions held under `pp_wbe` ≥ `A`'s.
- **WOULD-FAIL-IF (a broken implementation):** P1 or P2 fails; a `pp`-family session third on a close ≤ the fill; a
  `wbe`-family `stop_to` level ≠ max(stop0, min(fill, fill − (p − fill)/2)) (1e-9 relative) or below stop0; a `wbe`-family trade
  with a day-0 third that ends `stopped_day0` at a price above stop0; a trade that `A` stopped or cut with NO third having a
  `pp_wbe` R ≠ `A`'s; a trade `A` trailed out after a +2R third or an above-fill session third having `pp` R ≠ `A`'s; a
  `pp_wbe` ≥ 10R count below `A`'s (no `A` ≥ 10R trade was stopped at cost); TSLA 2020-06-01 on the hourly-close fills:
  `pp_wbe` takes NO third on 06-04 (close $57.63 < $58.37) and is not stopped on 06-05 (low $57.75 > stop $56.94) — mechanics
  from bars already shown, not an outcome claim. Synthetic golden: reached +1R, session-3 close ≤ the fill and below the
  20-day → everything sells at the session-4 open under `pp`.
- **Independent re-derivation** (pandas from the new trades table, no runner code): C1 n / mean R / ≥ 5R per arm, the deciding Δ
  (point and interval, same seed), the C0 Δ — VERDICT MATCH before the result is written.

## Consequence fixed now

| C1 Δ(`pp_wbe` − `pp`) | Exit carried into every next registration (the breakout-day quality rule, the stair-step number) |
|---|---|
| **win** | `pp_wbe` |
| **can't tell** | `pp_wbe` unless C0's Δ upper end < 0 (then `pp`) — his proposal, not shown worse at scale |
| **loss** | `pp` (his ruling stands; the stop goes to the entry price after the third) |

- `pp` replaces `A` in every case (his ruling). Reported to him either way, with `pp_s0` beside.
- **Paper: nothing from this read.** A C1 PASS under `pp_wbe` on 2022–24 is a DISCOVERY pass on a period read many times: a
  LEAD, recorded by the forward shadow, never a paper proposal; the 2025–26 holdout FAIL stands and its descriptive rows here
  cannot reverse it. Paper and live remain his sign-off (THE LINE).
- The forward shadow: recording the carried exit beside the 15 `cb.ARMS` needs the day-0 minute walk in the shadow's exit step
  (a recorder change, no order path), scoped as its own build after this read, with `A` recorded beside so the forward record is
  paired.

## What the read may NOT do

- Switch the deciding comparison or the primary arm; change the entry, stop, cells, periods, horizon, seed, draw count, the n
  floor, the open-mark exclusion or the block definition; edit this document above the marker after the freeze commit; read a
  period twice (the new trades table and its `.partial` refuse a second run).

## What this does not answer

- His partial size (a third vs a half) and the trail choice (10 vs 20 day by speed) — held at the P5 primary's. Whether he
  waits beyond day 5 when never in profit. The entry and the stop itself.

<!-- FREEZE -->
## Freeze record

Pinned (sha256 printed by the build's `--print-pins`, pasted here in the commit that precedes the run; the run verifies every
pin before it opens a file and refuses on any mismatch): `trades_{discovery,holdout}_p5.tsv.gz` + `trades_{discovery,holdout}_h60.tsv.gz`
(cb702/out), `trades_pre_p5.tsv.gz` + `trades_pre_h60.tsv.gz` (cb702_pre/out), both `daily_closes_all.csv.gz`, both minute
trees, the candidates files, `consolidation_breakout.py` (must equal `e14027be…`), the runner, the doc body. The RESULT is
appended below this record.

- module sha256: `e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b`
- runner sha256: `f69ea2807136340f2a2023f0aa81fd02a9879880a29f963f75b10248dd351caf`
- cb702/daily_closes_all.csv.gz sha256: `ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba`
- cb702_pre/daily_closes_all.csv.gz sha256: `b10eea41775e657939c64e314068cb3c606d23d44de8488649fb67a4ac5ed773`
- cb702/out/candidates.tsv sha256: `b75c828671171530225198f97fc1191c9bced8f9448b9b05aa46099d617ce0c7`
- cb702/out/candidates_com_comb.tsv sha256: `138149b87eed950d62ca94512b04c408329d18ef9a79779dc51d1a51589fc117`
- cb702/out/trades_discovery_p5.tsv.gz sha256: `8e906dc8d0242fba972e88d28eccb17c57b6b28d35f5f12fa1292208aa9c1bd4`
- cb702/out/trades_holdout_p5.tsv.gz sha256: `557a4152809aae22bb964653097a1684cfcedd8269777c69443227c9e794b673`
- cb702/out/trades_discovery_h60.tsv.gz sha256: `f0be23d6932e5dc9ea3f8b10e668dfd604ec6f8702032fb455a2992898ba01c8`
- cb702/out/trades_holdout_h60.tsv.gz sha256: `acc2c5cb4686f5ee04688607fc344a2086038af803e8e2e70d645d6abf494fa9`
- cb702_pre/out/candidates_tl_com.tsv sha256: `4ee9e04ca80f82fc02f1659b078263f9dcd1b197c395733a5f389367277268e6`
- cb702_pre/out/trades_pre_p5.tsv.gz sha256: `07c10b952316b28daf8f6cfff15437efb23b939af74a27b4bb60c5948712ec86`
- cb702_pre/out/trades_pre_h60.tsv.gz sha256: `b561742f27c192191d800f870aac2421b86514e4197406524f6df2c4fbbc3d1f`
- cb702/minutes (tree) sha256: `f1d98fd9d2352c45e90849e18a163b8ca31d2526eb851e5a76dd11ffd79a9fe5`
- cb702_pre/minutes (tree) sha256: `c019a52c8ed624263bd8b3ef0c36f54c5f77ce3cbee75751c0fd2a3026eeccd8`
- doc body sha256: `e4e6bbc472ece9791f3d233b48d014f8f049a19514455ef8dfed60189bb53d80`
