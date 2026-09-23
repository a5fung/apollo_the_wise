"""Regression test for #orb_cancellation_classification limit_price bug
(AVAV 2026-05-28).

Pre-fix: `cancel_unfilled_entries` passed `trade["entry_price"]` as the
classifier's `limit_price` arg. `entry_price` equals the BUY-STOP trigger
(= orb_high), not the LIMIT ceiling (= stop_limit_buy_price(trigger)).
Effect: classifier saw trigger==limit and couldn't tell `would_have_filled`
from `gap_through` — every cross-trigger case mis-labelled `clean_miss`.

Post-fix: call site passes `stop_limit_buy_price(orb_high)`, the same
helper the entry submission uses to compute the actual order limit.
"""
from agents.market_intelligence.broker.order_manager import stop_limit_buy_price


def test_stop_limit_buy_price_is_strictly_above_trigger():
    """The helper must produce a limit STRICTLY > trigger so the classifier
    can distinguish would_have_filled from gap_through. AVAV was the case
    that surfaced the bug — verify the actual numbers."""
    avav_trigger = 204.86
    avav_limit = stop_limit_buy_price(avav_trigger)
    assert avav_limit > avav_trigger, (
        f"stop_limit_buy_price must be > trigger; got {avav_limit} for {avav_trigger}"
    )
    # AVAV actual submitted limit was $205.88. Verify the helper produces
    # something in that ballpark (0.5% buffer = 1.02 above trigger).
    assert 205.0 < avav_limit < 207.0, f"Expected ~$205.88, got {avav_limit}"


def test_penny_ticker_floor():
    """Penny tickers use the $0.02 absolute floor instead of 0.5% buffer."""
    cheap_trigger = 1.00
    cheap_limit = stop_limit_buy_price(cheap_trigger)
    assert cheap_limit >= cheap_trigger + 0.02, (
        f"Penny ticker floor: limit should be ≥ trigger + $0.02; "
        f"got {cheap_limit} for {cheap_trigger}"
    )


def test_normal_priced_uses_pct_buffer():
    """Normal-priced names use 0.5% buffer where it exceeds the $0.02 floor."""
    trigger = 100.0
    limit = stop_limit_buy_price(trigger)
    # 0.5% of $100 = $0.50, well above the $0.02 floor
    assert limit >= 100.5, f"Normal price 0.5% buffer; got {limit} for {trigger}"
