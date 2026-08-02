"""#490 — real-time gap re-check at SUBMISSION (`entry_pipeline.check_rt_gap_floor`).

Operator ruling 2026-08-01: *"the blocking live path is in fact correct given the price retreated
from the 10% gap, so in a way the current path is a bug."* `MIN_GAP_PCT = 10.0` is an existing
signed criterion; the entry path selects an alert ROW written hours earlier and never re-reads
price, so a name that retreated below the floor before 09:31 was entered in violation of the
system's own rule.

**Two invariants this file exists to pin:**
1. It BLOCKS only on a positive, trustworthy real-time read below the floor.
2. It FAILS OPEN on absolutely everything else — a bad tick must never kill a good entry.

Invariant 2 is the load-bearing one: this guard sits on the live money path, and a failure mode that
blocks is far worse than one that lets a marginal trade through (that is merely today's behaviour).
"""
import asyncio
from datetime import date

import pytest

from agents.market_intelligence.broker import entry_pipeline
from agents.market_intelligence.broker.skip_reasons import SETUP_GAP_BELOW_FLOOR

_DATE = date(2026, 7, 30)
_PREV_CLOSE = 100.0


def _wire(monkeypatch, *, enabled=True, price=None, prev_close=_PREV_CLOSE,
          toggle_raises=False, price_raises=False, prev_raises=False):
    async def _toggle(name, env, default=False):
        if toggle_raises:
            raise RuntimeError("toggle store down")
        return enabled
    monkeypatch.setattr("agents.market_intelligence.db.get_runtime_toggle", _toggle)

    async def _prev(ticker, before_date):
        if prev_raises:
            raise RuntimeError("db down")
        return prev_close
    monkeypatch.setattr("agents.market_intelligence.db.get_prev_close", _prev)

    async def _latest(ticker):
        if price_raises:
            raise RuntimeError("alpaca down")
        return {"price": price} if price is not None else None
    monkeypatch.setattr(entry_pipeline.alpaca, "get_latest_trade", _latest)


_MAGNA53_FLOOR = 10.0


def _run(alert=None, floor=_MAGNA53_FLOOR):
    """`floor` is MAGNA53's 10% criterion. It is a PARAMETER, not a constant baked into the
    guard: `submit_trade_entry` is the shared funnel for MAGNA53 and 9M Day 2, and 9M's bar is
    3% / 4% intraday. See test_does_not_impose_one_strategys_floor_on_another."""
    return asyncio.run(entry_pipeline.check_rt_gap_floor(
        "FTNT", alert if alert is not None else {"alert_date": _DATE, "gap_pct": 10.79}, floor))


# ── invariant 1: it blocks the real case ─────────────────────────────────────────────────────

@pytest.mark.parametrize("price,expect_ok", [
    (107.77, False),   # FTNT 7/30 — the measured case
    (108.91, False),   # WKC  7/24
    (109.50, False),   # QBTS 7/27
    (109.99, False),   # just under the floor
    (110.00, True),    # exactly at the floor — NOT below, must pass
    (110.01, True),
    (125.00, True),
])
def test_floor_boundary(monkeypatch, price, expect_ok):
    _wire(monkeypatch, price=price)
    ok, reason = _run()
    assert ok is expect_ok
    if not expect_ok:
        assert SETUP_GAP_BELOW_FLOOR in reason


def test_block_reason_carries_both_numbers(monkeypatch):
    """The operator reads this string in the skip digest — it must say what the alert claimed AND
    what the price actually was, or the skip is unauditable."""
    _wire(monkeypatch, price=107.77)
    ok, reason = _run()
    assert ok is False
    assert "7.8%" in reason or "7.77" in reason
    assert "10.79" in reason or "10.8%" in reason
    assert "$107.77" in reason and "$100.00" in reason


# ── invariant 2: it fails OPEN on every non-answer ───────────────────────────────────────────

def test_fails_open_when_toggle_off(monkeypatch):
    _wire(monkeypatch, enabled=False, price=107.77)   # would block if enabled
    assert _run() == (True, None)


def test_fails_open_when_no_latest_trade(monkeypatch):
    _wire(monkeypatch, price=None)
    assert _run() == (True, None)


@pytest.mark.parametrize("bad_price", [0.0, -1.0])
def test_fails_open_on_nonsense_price(monkeypatch, bad_price):
    _wire(monkeypatch, price=bad_price)
    assert _run() == (True, None)


@pytest.mark.parametrize("bad_prev", [None, 0.0, -5.0])
def test_fails_open_without_a_usable_denominator(monkeypatch, bad_prev):
    """No prior bar (new listing, data gap) → cannot judge → must NOT block."""
    _wire(monkeypatch, price=50.0, prev_close=bad_prev)
    assert _run() == (True, None)


def test_fails_open_without_an_alert_date(monkeypatch):
    _wire(monkeypatch, price=107.77)
    assert _run({"gap_pct": 10.79}) == (True, None)


@pytest.mark.parametrize("kw", [
    {"toggle_raises": True}, {"price_raises": True}, {"prev_raises": True},
])
def test_fails_open_when_any_dependency_raises(monkeypatch, kw):
    """An exception inside a guard that can only REMOVE entries must land on today's behaviour,
    never on a silent halt of the whole book."""
    _wire(monkeypatch, price=107.77, **kw)
    assert _run() == (True, None)


def test_missing_alert_gap_still_blocks_and_renders(monkeypatch):
    """gap_pct absent from the alert row must not crash the reason string — the block still stands,
    since the decision rests on the real-time read, not on what the alert claimed."""
    _wire(monkeypatch, price=107.77)
    ok, reason = _run({"alert_date": _DATE})
    assert ok is False and "n/a" in reason


def test_humanize_renders_the_new_reason():
    """Machine prefixes must never reach the operator raw (CLAUDE.md Telegram contract)."""
    from agents.market_intelligence.broker.skip_reasons import humanize
    out = humanize(f"{SETUP_GAP_BELOW_FLOOR}: rt 7.8% < 10% floor")
    assert "setup:" not in out and out


# ── the guard must not impose one strategy's criterion on another ────────────────────────────

def test_defaults_to_skip_when_no_floor_is_passed(monkeypatch):
    """Default None = opt-OUT. A strategy must ASK for this check, or the shared funnel would
    silently apply someone else's rule to it."""
    _wire(monkeypatch, price=107.77)          # would block at a 10% floor
    assert asyncio.run(entry_pipeline.check_rt_gap_floor(
        "FTNT", {"alert_date": _DATE, "gap_pct": 10.79})) == (True, None)


def test_does_not_impose_one_strategys_floor_on_another(monkeypatch):
    """THE defect this parameter exists to prevent, caught by the /simplify efficiency pass.

    `submit_trade_entry` is the single funnel for MAGNA53 AND 9M Day 2. The guard originally
    imported `ep_detector.MIN_GAP_PCT` (MAGNA53's 10%) directly, so it would have blocked any 9M
    Day 2 entry under 10% — while 9M's own criterion is 3% gap or 4% intraday gain. That is
    rewriting another strategy's entry discipline, i.e. THE LINE.

    Same price, same alert: blocked at MAGNA53's floor, allowed at 9M's.
    """
    _wire(monkeypatch, price=105.0)           # +5% vs prev close
    assert _run(floor=10.0)[0] is False, "must block below MAGNA53's 10%"
    assert _run(floor=3.0) == (True, None), "must NOT block above 9M's 3%"


def test_magna53_call_site_actually_opts_in():
    """Wiring, not just behaviour — a guard nobody passes a floor to is silently inert."""
    src = open("agents/market_intelligence/broker/live_tracker.py").read()
    assert "rt_gap_floor_pct=_MAGNA53_MIN_GAP_PCT" in src
    pipe = open("agents/market_intelligence/broker/entry_pipeline.py").read()
    assert "check_rt_gap_floor(ticker, alert_context, rt_gap_floor_pct)" in pipe
    assert "from agents.market_intelligence.ep_detector import MIN_GAP_PCT" not in pipe, \
        "the shared funnel must not bake in one strategy's constant"
