"""stop_2r_running_comparison — corrected old-rule counterfactual (2026-08-18).

`data_gated_reviews.yaml`'s `stop_2r_running_comparison` review reconstructs what
the OLD rule (stop at the ORB low) would have done on each closed trade, so the
2026-08-16 2R-stop change can be scored against a real counterfactual instead of
waiting for a live control arm that will never exist. Its original (rehearsed)
query scored every trade that ever touched -1R as a FLAT -1.00R old-rule loss --
even on a trade where a PARTIAL had already been banked before the stop was
touched. That overstates the old rule's loss (a partial the old rule would have
taken too, since profit-take mechanics don't depend on which stop rule is live)
and so flatters the new rule by comparison. This module fixes it.

THE FIX. Every one of the 20 currently-closed trades this review reads pre-dates
2026-08-16 -- the OLD rule WAS the live rule when each one closed. So whenever a
partial fired before the old stop was touched, the trade's own `realized_r` IS
the old rule's true result; there is nothing to model. The flat -1.00R fallback
belongs ONLY on trades that touched the old stop with no partial already banked.

VERIFIED AGAINST PROD 2026-08-18 (read-only, THE LINE untouched -- see
`scripts/probes/_rehearsal_stop_2r_running_corrected_2026-08-18.sql` +
`..._out_2026-08-18.psv`): of the 20 closed trades, exactly ONE -- FIGS
(2026-08-07, trade_id 332) -- has a partial that fired BEFORE its old-stop touch
(`partial_profit` at 13:35 ET, `stop_hit` on the remainder at 13:51 ET, same day).
Its naive score was -1.00R; corrected it is realized_r = -0.3674369298831882R, a
bias of +0.6326R on that one trade (sum across all 20: naive -18.4813R, corrected
-17.8487R -- same 0.6326R gap, because FIGS is the only trade that changes).

⚠ CORRECTS AN EARLIER (WRONG) CLAIM: a prior report named SMCI 2026-05-06 as a
second pre-stop-partial trade, quoting a $639.34 loss on $995.26 of risk
(-0.64R). That SMCI/date/dollars combination is real, but it is NOT one of this
review's 20 trades -- it is a *different*, PAPER-account SMCI position (id 82,
`mi_live_trades`), outside `mi_exit_path_shadow`'s live-only population entirely,
and its own `exits` history is bug-distorted (a phantom full-position stop_hit
on 05-06 followed six days later by a real partial+stop-out on 05-12 -- the kind
of pnl_attribution-class defect this review's population already excludes by
construction). $995.26 does not even reconcile against that paper trade's own
numbers (entry_price/orb_low/entry_shares gives $800.26 of risk, not $995.26) --
flagged as unreconciled, not further guessed at. The ACTUAL live SMCI trade in
the 20-trade population (id 271, 2026-07-22) has `partial_taken=false` -- no
partial at all; its realized_r of -0.70R (vs a flat -1.00R) is ordinary
stop-fill slippage (exit printed 28.79 against an ORB low of 28.5), which this
fix does not and should not touch -- crediting slippage was never the ask, only
crediting a genuine pre-stop partial. MANE and FRMI were also named in that
earlier report and are confirmed `partial_taken=false` too -- the flat
counterfactual is correct for both, exactly as re-verified here.

⚠ THE GUARD THIS MODULE ADDS ON TOP OF THE FIX (advisor-caught, 2026-08-18,
before this shipped): `exit_path_shadow.py` anchors `stop_ref` /
`risk_per_share` / `touched_minus_1r` to the ORB low for EVERY trade regardless
of era -- so on a trade filled UNDER THE NEW 2R RULE (fill_day >= 2026-08-16),
`touched_minus_1r` can fire as the position sails PAST -1R on its way to the
actual (wider) stop, and `realized_r` then reflects the NEW rule's outcome, not
the old rule's. Returning `realized_r` in the touched+partial branch for such a
trade would silently collapse both arms of the comparison to the same number --
on exactly the trades this review exists to discriminate. So the "credit the
partial" branch below ONLY fires for pre-cutover trades, where old rule = live
rule makes `realized_r` provably correct. For a post-cutover trade with a
partial before the touch, this returns `None` (ADR 0014's own convention,
already used by `order_manager.profit_target_r_per_share`: no valid frame ->
the caller must SKIP, never fabricate a number) rather than guess at a blend --
`mi_exit_path_shadow` doesn't store the partial's actual shares/price, and
FIGS's own partial fired at ~+1.13R, not the modelled +2R target, so a blend
would be modelling, not measuring. AMLX (first new-rule fill, 2026-08-18) will
be the first trade to actually exercise this branch once it closes.

THE LINE: pure, DB-free scoring/reporting only. No detection/entry/sizing/stop
path reads this module or its output.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# 2026-08-16 — the date the 2R stop went live (operator-signed). A trade with
# fill_day on or after this date runs under the NEW rule; before it, the OLD
# rule (ORB-low stop) was the live rule. Named so the two places that need it
# (the guard below, and whoever wires the real predicate_sql) can't drift.
STOP_2R_CUTOVER_DATE = date(2026, 8, 16)


@dataclass(frozen=True)
class ShadowDayRow:
    """One `mi_exit_path_shadow` row for a single trade/trading_day -- only the
    two fields this module's logic needs."""
    trading_day: date
    touched_minus_1r: bool
    breakeven_armed: bool


def old_rule_counterfactual_r(
    day_rows: list[ShadowDayRow],
    realized_r: float,
    fill_day: date,
    flat_r: float = -1.0,
    cutover_date: date = STOP_2R_CUTOVER_DATE,
) -> float | None:
    """The corrected old-rule (ORB-low stop) counterfactual R for one closed trade.

    `day_rows` must be every `mi_exit_path_shadow` row for the trade (any order --
    sorted here by `trading_day`), each carrying `touched_minus_1r` and
    `breakeven_armed` for that day. `realized_r` is the trade's actual realized R
    multiple (`mi_exit_path_shadow.realized_r` on its `is_exit_day` row).
    `fill_day` is the trade's actual fill date -- required, not optional, because
    which branch is even SAFE to compute depends on it (see the guard below).

    Rule:
      - The old stop was never touched -> the old rule rides the exact same path
        as what actually happened: return `realized_r` unchanged (this branch is
        untouched by the 2026-08-18 fix -- it was already correct, and `fill_day`
        doesn't matter here: no divergence between the rules has occurred yet).
      - The old stop WAS touched, no partial had fired by then -> the old rule
        would have exited the whole position there: return `flat_r` (default
        -1.00), unchanged from the original (correct-for-this-case) scoring.
        `fill_day` doesn't matter here either -- both rules agree a stop-out at
        the ORB low is a full -1R loss (the NEW rule just doesn't stop there).
      - The old stop WAS touched, AND a partial had ALREADY fired by the first
        day it was touched (`breakeven_armed` true on that day):
          * `fill_day < cutover_date` (old rule was actually live) -> the
            partial would have been taken under the old rule too (profit-take
            timing doesn't depend on which stop is live), so `realized_r`
            already prices in that credit correctly -> return it.
          * `fill_day >= cutover_date` (NEW rule was live) -> `realized_r`
            reflects what the NEW, wider stop produced past this point, which
            is NOT what the old rule would have done -- return `None` rather
            than fabricate a number (see module docstring's guard section).

    Ordering is exact, not exit-day-only: this picks the FIRST trading_day where
    `touched_minus_1r` is true and reads `breakeven_armed` as of THAT day -- a
    trade that touches -1R on one day and only takes a partial on a LATER day
    must still score flat (the partial did not precede the touch). Every trade in
    the current 20-trade population happens to touch and exit on the same row, so
    this distinction hasn't been exercised live yet -- it is pinned by test so a
    future multi-day case scores right the first time.

    Raises nothing; `day_rows=[]` returns `realized_r` (no touch info available is
    the same as "never touched" -- never fabricate a -1.00R from missing data).
    """
    ordered = sorted(day_rows, key=lambda r: r.trading_day)
    touch_row = next((r for r in ordered if r.touched_minus_1r), None)
    if touch_row is None:
        return realized_r
    if not touch_row.breakeven_armed:
        return flat_r
    if fill_day < cutover_date:
        return realized_r
    return None  # NEW-rule trade: realized_r is the wrong rule's result -- refuse to score


def summarize(trades: list[dict]) -> dict:
    """`trades`: [{"ticker", "day_rows": [ShadowDayRow, ...], "realized_r",
    "fill_day"}, ...] (one entry per closed trade, `is_exit_day` row's values).
    Returns the per-trade corrected values plus the naive (pre-fix) values and
    the aggregate bias -- OVER SCOREABLE TRADES ONLY (a `None` corrected value,
    the new-rule/partial-before-touch guard above, is excluded from every sum
    and listed separately in `unscoreable`, never coerced into the totals).
    Never a verdict by itself (see the review's own confidence/maturity
    handling for that).
    """
    per_trade = []
    unscoreable = []
    for t in trades:
        corrected = old_rule_counterfactual_r(t["day_rows"], t["realized_r"], t["fill_day"])
        touched = any(r.touched_minus_1r for r in t["day_rows"])
        naive = -1.0 if touched else t["realized_r"]
        if corrected is None:
            unscoreable.append(t["ticker"])
            continue
        per_trade.append({
            "ticker": t["ticker"],
            "realized_r": t["realized_r"],
            "old_rule_naive_r": naive,
            "old_rule_corrected_r": corrected,
            "bias_r": naive - corrected,
        })
    return {
        "per_trade": per_trade,
        "unscoreable": unscoreable,
        "naive_sum_r": sum(p["old_rule_naive_r"] for p in per_trade),
        "corrected_sum_r": sum(p["old_rule_corrected_r"] for p in per_trade),
        "total_bias_r": sum(p["bias_r"] for p in per_trade),
    }
