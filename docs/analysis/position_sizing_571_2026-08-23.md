# #571 — What our position sizing actually does (2026-08-23)

**MEASUREMENT ONLY. Nothing changed. Sizing, risk percentage, caps and multipliers are the
operator's sole authority (THE LINE); any change implied here is his fork, not a recommendation.**

## The question

For every closed live trade: how much did we intend to bet (`equity × risk_pct`), how much was
actually at risk at the placed stop, why they differ, what the 2026-08-16 2R-stop change does to
that, and whether size is what stands between us and the sufficiency target (~4 converted tail
winners, i.e. ≈ +24R — `docs/roadmap/ep_profitability_program.md` § sufficiency target).

## Data

- One read-only prod capture: `scripts/probes/_571_sizing_capture.sql` →
  `_571_sizing_capture_out.psv` (pulled once 2026-08-23, read many). Arithmetic:
  `_571_sizing_analysis.py`.
- Cohort = the same one `kill_scale_bands.assemble_band_inputs` uses: `mi_live_trades`,
  `account_mode='live'`, `status='closed'`, `pnl_attribution IS NULL` → **22 closed trades**,
  2026-07-06 → 2026-08-19. Plus 3 open positions (ABCL, AMLX, MRNA) reported separately.
- "Intended" = 1% of equity (`RISK_PCT`), the base rule. "Booked budget" = the row's
  `risk_dollars` = equity × risk_pct **after** the sizing multipliers of the day (VIX-scaled +
  QQQ-EMA halve until 07-26; `REGIME_SIZING_ENABLED` regime multipliers after — flipped live
  2026-07-26 (#456, verified then; re-verified ON in prod `.env` today), and the booked budgets
  in the data match the multipliers exactly from 07-27 onward). "Actual at stop" = shares × (fill price − placed hard stop) —
  what a stop-out really loses before slippage.
- Equity basis: booked budget uses the live 9:31 Alpaca equity; my 1% column uses the prior
  16:12 snapshot. They differ by under 1.5% — noise here.
- Every entry that filled, filled in full (`mi_live_orders`: filled_qty = qty on all 22).
  **Partial fills explain none of the spread.**

## Result 1 — we bet about HALF of what the rule intends, and the 20% notional cap is why

Totals over the 22 closed trades:

| | total | per-trade median |
|---|---|---|
| intended at the base rule (1% of equity) | $1,071 | $48 |
| booked budget (after the day's multiplier) | $728 | $30 |
| **actually at risk at the placed stop** | **$552** | **$23** |

- **Multipliers cut intent by ~32%** (VIX/QQQ halve pre-07-26, regime multiplier after — a
  Correcting morning bets $20-24, a Crisis morning $12, on a ~$4,800 account).
- **Mechanics cut what remains to a median 80 cents per budgeted dollar.** The binder, per trade:
  **11 of 22 hit the 20%-of-equity notional cap** (tight ORB stop → big share count → ~$950
  position ceiling), 3 lost >15% of the budget to whole-share rounding on $150-300 stocks,
  8 landed on budget.
- **Worst cases:** NET risked $15.39 of a $47.94 budget (32% — cap), FIGS 39% (cap), MANE 47%
  (cap), FTNT $6.47 of an $11.96 Crisis budget (54% — one share of a $166 stock; that is also
  just **0.14% of equity** on a full stop-out).
- **Overshoots exist too:** chase fills above the ORB high raise per-share risk after shares are
  set — WKC booked 1.15× its budget, NVCR 1.07×, TSEM 1.05×. Small in dollars (≤ $3).
- Side effect worth knowing when reading band math: realized R everywhere divides P&L by the
  **budget**, so a clean full stop-out on a cap-bound trade reads ≈ −0.8R, not −1.0R.

## Result 2 — the 2R change: shares halve only where the budget was the binder, and actual risk finally lands ON the budget

**The 2R stop is LIVE — first live fill under it is AMLX 2026-08-18** (its hard stop = 2·ORB_low
− ORB_high, confirmed in the data; ETON on 08-14 still carries the ORB-low stop).
⚠ `docs/setups/magna53_ep.md` line ~20 still says "Built, NOT yet deployed" — **that line is
stale** and is flagged for deletion at its verify-live step (not edited here).

Era split — 21 closed pre-2R, 3 entries under 2R (1 closed: MRVL; 2 open: AMLX, MRNA):

| | pre-2R (n=21 closed) | 2R era (n=3 entries) |
|---|---|---|
| actual $ at stop, median | $23 | $45 (45.40 / 49.94 / 43.60) |
| actual ÷ booked budget, median | 0.80 | 0.91 / 1.03 / 0.87 |
| notional-cap bound | 11 of 21 | 0 of 3 |

- **Did share counts halve?** Where the budget was the binder, yes, exactly: AMLX 32 → 16,
  MRNA 8 → 4 (old-rule counts recomputed from the same ORB and budget). Where the **cap** was
  the binder it did NOT: MRVL 4 → 4 — same shares, double the stop distance, so its dollar risk
  at the stop **doubled** ($22.76 → $45.40).
- **Did dollar risk hold constant?** The intended budget held ($48-50, Bull 1.0×). The
  **actual** dollar risk roughly doubled ($23 → $45 median) — not because the rule changed but
  because doubling the stop distance halves the share count, which halves the notional, so the
  20% cap stops truncating and the risk formula governs for the first time. Plainly:
  **pre-2R we were silently betting about half of what the rule intended; under 2R we bet what
  we intend.** (The signed 08-16 design said "half size, same dollar risk" — true against the
  budget; against what the old mechanics *actually placed*, risk per trade went up ~2×. The
  §0c-pre evidence compared at equal dollar risk, so this does not touch that comparison.)
- n=3 entries, 1 closed — this is the mechanism confirming itself, not yet a distribution.

## Result 3 — size is NOT the binding constraint on the sufficiency target; the number that decides it

The target is **~4 converted tail winners ≈ +24R over 4½ months** — denominated in R, and R is
sizing-agnostic: no share count makes a trade convert. The dollars:

- +24R at today's Bull budget (~$50) ≈ **+$1,200**.
- The ENTIRE sizing shortfall across the whole live book — every dollar the cap, rounding and
  multipliers kept off the table over 8 weeks — is **$519** of risk never placed ($1,071
  intended vs $552 placed). And placing it would have scaled the SAME trades: this book
  converts 2 of 22 closed to profit (PLTR +$118.60, ETON +$19.32; sum −$321.54), so at full
  budgets the closed book computes to **−$447, not a smaller loss**. Better sizing mechanics on
  this book buys bigger losses, not winners.
- The gap to the target is **conversion** (2 realized-profit closes vs ~4 tail winners needed;
  the 3 open positions carry +$65.36 of realized partials), exactly what the program doc already
  concluded from the other direction.

**The one place size genuinely touches conversion at this account:** it can delete a candidate
entirely. 4 alerts died `setup:size_too_small` — SIMO/EME/PWR on the 07-30 Crisis morning, where
0.25× of $4,782 = a **$12 budget** that buys zero shares of a $16-29-per-share stop, and SITM on
08-06 ($48 budget vs $48.88 per-share risk). The 2R change doubles every per-share distance, so
the zero-share line moves in: at the Bull budget (~$50) a name with an ORB range over ~$25 is
now unbuyable; under Correcting 0.5× ~$12.50; under Crisis 0.25× ~$6 (CAT, ARM, THC-class names
zero out). **Whether that admission cost is acceptable is the operator's fork; nothing here
recommends a level.**

## Result 4 — the regime-multiplier tension, where it stands today (stated, not resolved)

The 08-17 `exit_regime_separability` read (matched reconstruction, not this live book): winners
average +7.92R in Choppy and +2.98R in Correcting vs +2.22R in Bull — while the live multipliers
bet 0.75× and 0.50× there. On the live closed book as of today:

- **Choppy 7 closed, 1 winner — and it is the book's biggest: PLTR +$118.60, taken at 0.75×.**
  At 1.0× the same trade pays ≈ +$158; the haircut cost ≈ $40 on the single best outcome.
- **Correcting 7 closed + Crisis 1: 0 winners, 8 losses, −$150.60 total** — at full size the
  same trades lose ≈ twice that. The haircut protected real dollars here.
- Bull: 7 closed, 1 winner (ETON +$19.32), −$151.22 net.

Both halves of the operator's question are live in the data and neither is established — the
winner side rests on n=1 (PLTR) in this book and n=3/3/1 in the 08-17 read. This is exactly what
the gated review `regime_sizing_vs_tail_recheck` (earliest 2026-09-15, second regime cell at 5
winners ≥ +1.5R) exists to judge. **No multiplier change is proposed; his ruling.**

## ⚠ What this study does NOT answer

- **Whether the 2R era keeps actual risk pinned to the budget** — 3 entries, 1 closed. Needs
  ~15-20 2R-era fills before the pre/post comparison in Result 2 is a distribution rather than
  an arithmetic check.
- **Whether the regime multipliers are net-protective or net-costly** — 1-2 winners per cell;
  owned by the gated review above, not answerable sooner by this book.
- **Whether 1% base risk or the 20% notional cap are the right levels** — this doc measures
  what they DO; setting them is THE LINE.
- **Slippage beyond the stop** is visible (BW stopped 5¢ through, $4 extra; MRVL's exit filled
  $10.82 under entry against an 11.38 planned distance) but not systematically studied here —
  it moved no conclusion above.
- **Nothing here says whether to change the account size.** At $5,033 (08-21) the worst single
  closed loss was $49.60 (0.99% of equity) — losses are landing inside intent; that is a
  statement of fact, not sufficiency.

## What this means

1. **Sizing was never examined and it turns out it was quietly half-off** — the 20% notional cap,
   not the risk rule, set most positions pre-2R. The 2R change fixes that as a side effect.
2. **Size is an irrelevance to the sufficiency target at this account size** — $519 of missing
   risk over 8 weeks vs a +$1,200 target that only conversion can reach; on the current book
   more size = more loss.
3. **The one live sizing lever that can touch conversion is the zero-share line** (multiplier ×
   equity × 2R distance), which deleted 4 candidates already and tightened under 2R. Fork is
   the operator's, gated with the regime review.
4. **Housekeeping for the main session:** `magna53_ep.md`'s "NOT yet deployed" caveat is stale
   (first 2R live fill 08-18), and `safeguards.md` §regime-sizing's Phase paragraph still reads
   flag-OFF although the flip went live 2026-07-26 (#456, in git) with no change-log entry in
   that file. Report only — not edited by this task. (That SSoT's own §456 notes already
   predicted the cap-binding in Result 1: "28/43 historical trades were 20%-notional-capped" —
   this study is the live-book confirmation, 11/22, not a new discovery.)
