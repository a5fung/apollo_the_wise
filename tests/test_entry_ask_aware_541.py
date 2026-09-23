"""The #500 price-aware entry guard was blind to the offer, and the venue is not.

2026-08-06/07: two live entries were killed by Alpaca in single-digit milliseconds —
INSM ("[6098] Stop Price Already Triggered", then ran +33%) and QNST ("Unsolicited: Bad
Stop 19.8", record revenue +43% YoY). Both looked healthy on trades and were already
through on the offer:

    QNST  trigger 19.80   last trade 19.50    ask 19.83
    INSM  trigger 129.41  last trade 128.67   ask 129.48

A buy-stop below the offer is immediately marketable, so it is not a stop and the venue
refuses it. #500 already owns exactly this question ("would the trigger be
in-the-money?") — it just asked `get_latest_trade`, which cannot see it.

These tests pin the three things that make the fix safe rather than merely correct:
the toggle is OFF by default, it fails CLOSED on anything unreadable, and the existing
chase cap still bounds the fallback price.
"""
import pytest


@pytest.fixture()
def om():
    from agents.market_intelligence.broker import order_manager
    return order_manager


# ── the toggle: default OFF, fails CLOSED ────────────────────────────────────────

@pytest.mark.asyncio
async def test_toggle_is_OFF_when_no_row_exists(om, monkeypatch):
    """Ships dark. A deploy must change nothing until the operator flips it."""
    from agents.market_intelligence import db
    async def _none(*a, **k):
        return None
    monkeypatch.setattr(db, "get_safeguard_state", _none)
    assert await om._ask_aware_entry_enabled("live") is False


@pytest.mark.asyncio
async def test_toggle_is_ON_only_for_the_literal_on_state(om, monkeypatch):
    from agents.market_intelligence import db
    for state, expected in (("on", True), ("ON", True), ("off", False),
                            ("observe", False), ("", False)):
        async def _row(*a, _s=state, **k):
            return {"state": _s}
        monkeypatch.setattr(db, "get_safeguard_state", _row)
        assert await om._ask_aware_entry_enabled("live") is expected, state


@pytest.mark.asyncio
async def test_toggle_fails_CLOSED_when_the_read_raises(om, monkeypatch):
    """An unreadable flag must never silently enable a money-path change."""
    from agents.market_intelligence import db
    async def _boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "get_safeguard_state", _boom)
    assert await om._ask_aware_entry_enabled("live") is False


# ── the quote reader ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_zero_ask_is_no_information_not_a_cheap_offer(monkeypatch):
    """A missing/zero ask must return None, never 0.0 — otherwise `ask > orb_high`
    is False and the guard reads a broken quote as 'the market is below us'."""
    from agents.market_intelligence.broker import alpaca_client

    class _Q:
        ask_price = 0
        bid_price = 19.35
        timestamp = None

    async def _sdk(fn, req):
        return {"QNST": _Q()}
    monkeypatch.setattr(alpaca_client, "_sdk", _sdk)
    monkeypatch.setattr(alpaca_client, "_get_data_client", lambda: object())
    assert await alpaca_client.get_latest_quote("QNST") is None


# ── the chase cap still bounds it: the real numbers from both incidents ──────────

@pytest.mark.parametrize("name,orb_high,stop,ask", [
    ("QNST", 19.80, 19.21, 19.83),
    ("INSM", 129.41, 126.15, 129.48),
])
def test_both_real_incidents_land_inside_the_chase_cap(om, name, orb_high, stop, ask):
    """The fallback must not smuggle in extra risk. Recomputes the #500 cap on the
    two orders that actually failed — if either exceeded it, the fix would be trading
    a cancelled entry for an oversized one."""
    fallback_limit = round(ask * 1.002, 2)
    planned = orb_high - stop
    actual = fallback_limit - stop
    assert planned > 0
    ratio = actual / planned
    assert ratio <= om.CHASE_RISK_INFLATION_CAP, (
        f"{name}: fallback {fallback_limit} = {ratio:.2f}x planned risk, over the cap")
    assert ratio < 1.25, f"{name}: expected a modest chase, got {ratio:.2f}x"


def test_the_ask_is_what_separates_these_cases_from_the_old_logic(om):
    """Guard the premise: on BOTH incidents the last trade says 'not through' and the
    ask says 'already through'. If that ever stops being true the fix is pointless and
    this test should fail loudly rather than the feature quietly doing nothing."""
    for orb_high, last, ask in ((19.80, 19.50, 19.83), (129.41, 128.674, 129.48)):
        assert not (last > orb_high), "old trade-based check would have caught it"
        assert ask > orb_high, "ask-based check must catch it"
