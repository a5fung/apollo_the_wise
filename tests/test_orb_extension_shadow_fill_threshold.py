"""The ORB-extension sim must fill at the BREAKOUT trigger, not at the stop-loss floor.

⚠ WHY THIS FILE EXISTS. `_simulate_day1` computed its fill threshold as
`stop_limit_buy_price(stop)` from the feature's first commit (`9e8a8ae`, 2026-05-04), and the
`limit` parameter was never referenced in the body at all. So the simulation bought just above the
STOP-LOSS FLOOR instead of the ORB-high breakout trigger.

Because price sits between `orb_low` and `orb_high` immediately after the range forms, that wrong
threshold is crossed within minutes of the open. Consequences, all measured on 2026-08-03:

  * 28 of 31 simulated trades "filled" — every one of which was a REAL entry that never triggered
    by 10:00 ET and was cancelled in production.
  * **All six tested cutoffs produced byte-identical results for every trade**, because the wrong
    threshold was already crossed long before the earliest cutoff. The review reading this would
    have concluded "10:00 is already optimal" — a false negative manufactured by the bug.
  * Risk per trade was understated ~5x: the sim risked fill→stop (≈0.5% of price) instead of the
    real orb_high→orb_low distance.

It survived three months because **this module had no tests at all** — the aggregate was first run
against its N>=20 threshold on 2026-08-03. The docstring meanwhile asserted the CORRECT rule while
the code did the opposite; a comment is not evidence.

These tests are behavioural: they feed bars that cross the stop-derived price but NOT the
limit-derived one, and assert no fill. A source-string check would not have caught the original bug
either, since the source read plausibly.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from agents.market_intelligence.broker.order_manager import stop_limit_buy_price
from agents.market_intelligence.broker.orb_extension_shadow import _simulate_day1

_ET = ZoneInfo("America/New_York")
_OPEN = datetime(2026, 8, 3, 9, 31, tzinfo=_ET)

# A realistic opening range: breakout trigger well above the stop.
ORB_HIGH, ORB_LOW = 100.0, 95.0
TRIGGER = stop_limit_buy_price(ORB_HIGH)     # what a real entry needs ≈ 100.50
STOP_DERIVED = stop_limit_buy_price(ORB_LOW)  # what the bug used      ≈ 95.48


def _bars(highs, lows=None, start=_OPEN):
    """(ts, open, high, low, close) minute bars — the shape _simulate_day1 consumes."""
    lows = lows or [h - 0.5 for h in highs]
    return [(start + timedelta(minutes=i), h - 0.2, h, lo, h - 0.1)
            for i, (h, lo) in enumerate(zip(highs, lows))]


def _run(bars, cutoff_min=29):
    return _simulate_day1(bars, _OPEN, _OPEN + timedelta(minutes=cutoff_min),
                          limit=ORB_HIGH, stop=ORB_LOW, shares=100)


# ── the bug, stated as a test ────────────────────────────────────────────────────────────────

def test_price_above_the_STOP_but_below_the_TRIGGER_does_NOT_fill():
    """THE regression. Every bar here clears the stop-derived threshold and none reaches the real
    breakout trigger — exactly the shape of a real ORB entry that never triggers and gets
    cancelled. The buggy version filled all of these."""
    bars = _bars([96.0, 97.5, 98.9, 99.9] * 3)
    assert max(b[2] for b in bars) > STOP_DERIVED, "fixture must clear the stop-derived price"
    assert max(b[2] for b in bars) < TRIGGER, "fixture must stay under the real trigger"
    assert _run(bars)["would_fill"] is False


def test_price_reaching_the_TRIGGER_does_fill_at_the_trigger():
    bars = _bars([96.0, 98.0, TRIGGER + 0.10, 99.0])
    out = _run(bars)
    assert out["would_fill"] is True
    assert abs(out["fill_price"] - TRIGGER) < 0.001, "fill must be AT the breakout trigger"


def test_the_fill_price_is_never_the_stop_derived_one():
    """The single number that gave the bug away on real rows: MRVL limit 259.80 / stop 252.43
    filled at 253.69 — exactly stop-derived, not the 261.10 the real trigger required."""
    out = _run(_bars([96.0, 98.0, TRIGGER + 1.0]))
    assert abs(out["fill_price"] - STOP_DERIVED) > 0.001


# ── the consequence that made the whole dataset useless ──────────────────────────────────────

def test_a_LATER_cutoff_can_change_the_outcome():
    """The bug's real signature was not optimism — it was that all six cutoffs returned identical
    results, because the wrong threshold was crossed before the earliest one. If extending the
    window cannot change anything, the review it feeds is unanswerable by construction."""
    late = _bars([96.0] * 20 + [TRIGGER + 0.10] + [99.0] * 5)
    assert _run(late, cutoff_min=10)["would_fill"] is False, "too early — trigger not yet reached"
    assert _run(late, cutoff_min=40)["would_fill"] is True, "later cutoff must be able to catch it"


def test_the_limit_parameter_is_actually_used():
    """It was dead for three months. Changing only the limit must change the outcome."""
    bars = _bars([96.0, 97.0, 98.0])
    unreachable = _simulate_day1(bars, _OPEN, _OPEN + timedelta(minutes=29),
                                 limit=ORB_HIGH, stop=ORB_LOW, shares=100)
    reachable = _simulate_day1(bars, _OPEN, _OPEN + timedelta(minutes=29),
                               limit=95.0, stop=ORB_LOW, shares=100)
    assert unreachable["would_fill"] is False and reachable["would_fill"] is True


def test_this_module_places_no_orders():
    """The reason this bug cost no money, and the property that must not change: it is a pure
    simulation with no broker calls."""
    src = open("agents/market_intelligence/broker/orb_extension_shadow.py").read()
    for forbidden in ("submit_order", "place_order", "OrderRequest", "trading_client"):
        assert forbidden not in src, f"shadow sim must never {forbidden}"
