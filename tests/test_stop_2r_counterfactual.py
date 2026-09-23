"""2026-08-18 -- fix for the `stop_2r_running_comparison` old-rule counterfactual
bias: the naive scoring assumed a flat -1.00R on ANY trade that ever touched the
old (ORB-low) stop, even when a partial had already been banked before the touch.
That overstates the old rule's loss and flatters the new 2R rule by comparison.

Verified against prod 2026-08-18 (read-only): of the 20 currently-closed trades,
exactly one -- FIGS (2026-08-07) -- has a partial before its old-stop touch. Its
naive score was -1.00R; corrected it is its own realized_r, -0.3674369298831882R.
SMCI (2026-07-22, the live trade actually in this population) has NO partial and
is correctly UNCHANGED by this fix -- pinned here specifically because an earlier
report wrongly named a different, paper-account SMCI trade as a second partial
case.

Also covers the guard added on advisor review before shipping: crediting
`realized_r` on a touched+partial trade is only valid when the OLD rule was
actually live for that trade (fill_day < the 2026-08-16 cutover). A NEW-rule
trade's `realized_r` reflects the wider stop's own outcome, not the old rule's --
scoring it the same way would silently collapse both arms of the comparison.

THE LINE: this is analysis-counterfactual plumbing only. No test touches
broker/, entry_pipeline, or any live exit path.
"""
from __future__ import annotations

from datetime import date

import pytest

from scripts.stop_2r_counterfactual import (
    STOP_2R_CUTOVER_DATE,
    ShadowDayRow,
    old_rule_counterfactual_r,
    summarize,
)

_OLD_FILL = date(2026, 7, 22)   # pre-cutover -- old rule was live
_NEW_FILL = date(2026, 8, 18)   # post-cutover -- new 2R rule is live


def _row(day, touched, armed):
    return ShadowDayRow(trading_day=date(2026, 7, 1) if day is None else day,
                         touched_minus_1r=touched, breakeven_armed=armed)


# ── never touched the old stop -> untouched by this fix ───────────────────────


def test_never_touched_returns_realized_r_unchanged():
    """A trade that never reached -1R: old rule rides the same path. This branch
    pre-dates the fix and must not move -- and fill_day doesn't matter here,
    old or new rule alike."""
    rows = [_row(date(2026, 8, 14), touched=False, armed=True)]  # ETON-shaped: partial, no touch
    for fill_day in (_OLD_FILL, _NEW_FILL):
        assert old_rule_counterfactual_r(rows, realized_r=0.5187487919592789,
                                          fill_day=fill_day) == pytest.approx(0.5187487919592789)


# ── touched, no partial before the touch -> flat -1.00R stands ────────────────


def test_touched_with_no_prior_partial_stays_flat_minus_one():
    """MANE/FRMI/SMCI-shaped: the old stop was touched, breakeven never armed.
    The flat -1.00R counterfactual is correct here and this fix must NOT change
    it, even though the trade's own realized_r (e.g. SMCI's -0.70R, from ordinary
    stop-fill slippage, not a partial) differs from -1.00 -- crediting slippage
    was never the ask. fill_day doesn't matter here either: both rules agree a
    stop-out at the ORB low is a full -1R loss."""
    rows = [
        _row(date(2026, 7, 22), touched=False, armed=False),
        _row(date(2026, 7, 23), touched=False, armed=False),
        _row(date(2026, 7, 24), touched=False, armed=False),
        _row(date(2026, 7, 27), touched=True, armed=False),
    ]
    for fill_day in (_OLD_FILL, _NEW_FILL):
        result = old_rule_counterfactual_r(rows, realized_r=-0.701030927835052, fill_day=fill_day)
        assert result == pytest.approx(-1.0)
        assert result != pytest.approx(-0.701030927835052)  # the un-credited slippage number must NOT leak through


# ── the load-bearing case: partial before the touch, OLD rule -> credit it ────


def test_partial_before_touch_pre_cutover_credits_realized_r_not_flat_minus_one():
    """FIGS-shaped: partial fired, THEN the remainder hit -1R, same day, and the
    trade filled BEFORE the 2026-08-16 cutover (old rule was live). The
    corrected counterfactual must be the trade's real (partial-credited)
    realized_r, not a flat -1.00R. This is the exact bias the fix targets --
    reverting `old_rule_counterfactual_r` to always return flat_r when touched
    (the pre-fix behavior) makes this fail (-1.0 != -0.3674...)."""
    rows = [_row(date(2026, 8, 7), touched=True, armed=True)]
    result = old_rule_counterfactual_r(rows, realized_r=-0.3674369298831882, fill_day=_OLD_FILL)
    assert result == pytest.approx(-0.3674369298831882)
    assert result != pytest.approx(-1.0)


# ── the guard: partial before the touch, NEW rule -> refuse to score ──────────


def test_partial_before_touch_post_cutover_refuses_to_score():
    """A trade filled ON OR AFTER the 2026-08-16 cutover: realized_r reflects
    the NEW (wider) stop's own outcome past the -1R touch, not what the old
    rule would have done there -- crediting it the same way as a pre-cutover
    trade would silently collapse both arms of the comparison to the same
    number. Must return None (ADR 0014's "no valid frame -> SKIP" convention),
    never fabricate a blended or flat value. This is the load-bearing guard:
    removing the fill_day check (always crediting realized_r once armed) makes
    this fail (returns -0.10 instead of None)."""
    rows = [_row(date(2026, 8, 18), touched=True, armed=True)]
    result = old_rule_counterfactual_r(rows, realized_r=-0.10, fill_day=_NEW_FILL)
    assert result is None


def test_cutover_boundary_is_inclusive_of_the_cutover_date_itself():
    """fill_day == the cutover date is a NEW-rule trade (the rule went live
    THAT day) -- must refuse to score, not fall through to the old-rule credit
    branch."""
    rows = [_row(date(2026, 8, 16), touched=True, armed=True)]
    result = old_rule_counterfactual_r(rows, realized_r=-0.10, fill_day=STOP_2R_CUTOVER_DATE)
    assert result is None


def test_day_before_cutover_still_credits_realized_r():
    rows = [_row(date(2026, 8, 15), touched=True, armed=True)]
    result = old_rule_counterfactual_r(rows, realized_r=-0.10, fill_day=date(2026, 8, 15))
    assert result == pytest.approx(-0.10)


def test_partial_only_on_a_later_day_does_not_retroactively_credit():
    """Ordering must be exact: a trade that touches -1R on day 1 and only takes a
    partial on day 3 (hypothetical -- not in the live population yet, but the
    logic must not assume same-day touch+partial always) must still score flat
    -1.00R, because the old rule would have stopped out on day 1, before any
    partial existed."""
    rows = [
        _row(date(2026, 8, 10), touched=True, armed=False),   # touch day: no partial yet
        _row(date(2026, 8, 11), touched=False, armed=True),   # partial fires AFTER the touch
        _row(date(2026, 8, 12), touched=False, armed=True),
    ]
    assert old_rule_counterfactual_r(rows, realized_r=-0.10, fill_day=_OLD_FILL) == pytest.approx(-1.0)


def test_touch_row_out_of_order_input_still_finds_the_first_touch():
    """day_rows are sorted internally -- callers must not have to pre-sort."""
    rows = [
        _row(date(2026, 8, 12), touched=False, armed=True),
        _row(date(2026, 8, 10), touched=True, armed=False),  # actually the first day
        _row(date(2026, 8, 11), touched=False, armed=True),
    ]
    assert old_rule_counterfactual_r(rows, realized_r=-0.10, fill_day=_OLD_FILL) == pytest.approx(-1.0)


def test_no_day_rows_returns_realized_r_never_fabricates_minus_one():
    """Missing touch history must never be silently treated as 'touched'."""
    assert old_rule_counterfactual_r([], realized_r=0.25, fill_day=_OLD_FILL) == pytest.approx(0.25)


# ── summarize() -- the aggregate the running read reports ─────────────────────


def test_summarize_reproduces_the_verified_20_trade_bias():
    """Pins the exact prod-verified numbers (2026-08-18 rehearsal): naive sum
    -18.4813R, corrected sum -17.8487R, bias +0.6326R, entirely from FIGS.
    All three trades are pre-cutover (real fill dates)."""
    trades = [
        {"ticker": "SMCI", "realized_r": -0.701030927835052, "fill_day": date(2026, 7, 22),
         "day_rows": [_row(date(2026, 7, 27), touched=True, armed=False)]},
        {"ticker": "FIGS", "realized_r": -0.3674369298831882, "fill_day": date(2026, 8, 7),
         "day_rows": [_row(date(2026, 8, 7), touched=True, armed=True)]},
        {"ticker": "ETON", "realized_r": 0.5187487919592789, "fill_day": date(2026, 8, 14),
         "day_rows": [_row(date(2026, 8, 14), touched=False, armed=True)]},
    ]
    out = summarize(trades)
    assert out["unscoreable"] == []
    figs = next(p for p in out["per_trade"] if p["ticker"] == "FIGS")
    assert figs["old_rule_naive_r"] == pytest.approx(-1.0)
    assert figs["old_rule_corrected_r"] == pytest.approx(-0.3674369298831882)
    # bias_r = naive - corrected: negative means the naive scoring was MORE
    # negative (a worse loss) than the corrected value -- i.e. it overstated
    # the old rule's loss on this trade by 0.6326R.
    assert figs["bias_r"] == pytest.approx(-0.6325630701168118)
    smci = next(p for p in out["per_trade"] if p["ticker"] == "SMCI")
    assert smci["bias_r"] == pytest.approx(0.0)   # unchanged -- no partial before touch
    eton = next(p for p in out["per_trade"] if p["ticker"] == "ETON")
    assert eton["bias_r"] == pytest.approx(0.0)   # never touched -- untouched by the fix
    assert out["total_bias_r"] == pytest.approx(-0.6325630701168118)


def test_summarize_excludes_unscoreable_new_rule_trades_from_every_sum():
    """AMLX-shaped: a new-rule trade that touches -1R with a partial already
    banked must be reported as unscoreable, not silently folded into the sums
    (which would understate the old rule's loss by counting a NEW-rule result
    as if it were the old rule's)."""
    trades = [
        {"ticker": "OLD", "realized_r": -1.0, "fill_day": date(2026, 7, 10),
         "day_rows": [_row(date(2026, 7, 10), touched=True, armed=False)]},
        {"ticker": "AMLX", "realized_r": +0.80, "fill_day": date(2026, 8, 18),
         "day_rows": [_row(date(2026, 8, 20), touched=True, armed=True)]},
    ]
    out = summarize(trades)
    assert out["unscoreable"] == ["AMLX"]
    assert [p["ticker"] for p in out["per_trade"]] == ["OLD"]
    assert out["naive_sum_r"] == pytest.approx(-1.0)
    assert out["corrected_sum_r"] == pytest.approx(-1.0)
