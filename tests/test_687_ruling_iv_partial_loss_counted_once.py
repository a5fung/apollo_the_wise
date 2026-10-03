"""#687 RULING (iv), operator 2026-10-02 — each realized dollar counts toward the 2% daily loss
limit ONCE, on the day it was realized.

Ruling (1) (2026-10-01) counts a losing PARTIAL-sale leg on its own day, while the trade is still
open. The closed-trade arm summed the whole trade's `total_pnl` on the day it later CLOSES, so that
same leg counted a second time. Now `live_tracker._closed_losses_realized_on` nets out of
`total_pnl` every losing leg dated an EARLIER ET day than the close day (exactly the legs ruling (1)
counted); a partial realized the same day as the close stays inside `total_pnl` and counts once.

Partial PROFIT legs are unchanged from ruling (1)'s design: never counted on their own day and
never netted, so they stay inside `total_pnl` and still offset the trade's loss on its close day.

`total_pnl = sum(exits[].pnl)` is the invariant every closer writes (order_manager "Invariant:
total_pnl = sum(exits[].pnl)"), which is what lets the earlier-day part be separated.
"""
import asyncio
from datetime import date
from decimal import Decimal

from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker.skip_reasons import BLOCK_DAILY_LOSS

DAY1 = date(2026, 10, 5)
DAY2 = date(2026, 10, 6)


def _leg(pnl, time, reason="x"):
    return {"shares": 2, "price": 10.0, "pnl": pnl, "time": time, "reason": reason}


def _closed(*legs):
    return {"total_pnl": sum(l["pnl"] for l in legs), "exits": list(legs)}


# ── the pure helper ──────────────────────────────────────────────────────────────────────────

def test_a_partial_loss_on_day_1_and_the_close_on_day_2_counts_only_the_remainder_on_day_2():
    """Day 1: 4 sh sold at −$60 (ruling (1) counted it on day 1). Day 2: the last 2 sh at −$50.
    Day 2 counts −$50, not the trade's −$110."""
    row = _closed(_leg(-60.0, "2026-10-05T19:30:00+00:00"),
                  _leg(-50.0, "2026-10-06T14:00:00+00:00"))
    assert lt._closed_losses_realized_on([row], DAY2) == -50.0


def test_the_same_day_partial_and_close_count_once():
    row = _closed(_leg(-60.0, "2026-10-06T14:00:00+00:00"),
                  _leg(-50.0, "2026-10-06T19:00:00+00:00"))
    assert lt._closed_losses_realized_on([row], DAY2) == -110.0


def test_each_day_sees_its_own_dollars_exactly_once():
    """The two arms together, day by day: day 1 (trade open) counts the partial; day 2 (trade
    closed) counts the remainder. Sum over the days == the trade's total loss."""
    legs = (_leg(-60.0, "2026-10-05T19:30:00+00:00"), _leg(-50.0, "2026-10-06T14:00:00+00:00"))
    day1 = lt._partial_losses_realized_on([{"exits": [legs[0]]}], DAY1)    # open on day 1
    day2 = lt._closed_losses_realized_on([_closed(*legs)], DAY2)           # closed on day 2
    assert (day1, day2) == (-60.0, -50.0)
    assert day1 + day2 == _closed(*legs)["total_pnl"]


def test_a_day_2_profit_after_a_day_1_partial_loss_counts_nothing_on_day_2():
    """Day 1 −$100 (counted then); day 2 the rest +$30. total_pnl −$70 — but day 2 realized a
    PROFIT, so nothing counts on day 2 (before ruling (iv): −$70 counted again)."""
    row = _closed(_leg(-100.0, "2026-10-05T19:30:00+00:00"),
                  _leg(+30.0, "2026-10-06T14:00:00+00:00"))
    assert lt._closed_losses_realized_on([row], DAY2) == 0.0


def test_an_earlier_partial_PROFIT_is_not_netted_and_still_offsets_the_close_day_loss():
    """Ruling (1)'s design, unchanged: a profit leg is never counted on its own day, so it stays
    inside total_pnl. Day 1 +$300, day 2 −$200 → total +$100 → nothing counts on day 2."""
    row = _closed(_leg(+300.0, "2026-10-05T19:30:00+00:00"),
                  _leg(-200.0, "2026-10-06T14:00:00+00:00"))
    assert row["total_pnl"] == 100.0           # filtered out by `total_pnl < 0` in SQL already
    assert lt._closed_losses_realized_on([row], DAY2) == 0.0
    row = _closed(_leg(+50.0, "2026-10-05T19:30:00+00:00"),
                  _leg(-200.0, "2026-10-06T14:00:00+00:00"))
    assert lt._closed_losses_realized_on([row], DAY2) == -150.0


def test_a_leg_with_no_readable_time_is_never_netted():
    """Ruling (1) never counted it (no day to count it on), so the close day counts it."""
    row = _closed(_leg(-60.0, "not a time"), _leg(-50.0, "2026-10-06T14:00:00+00:00"))
    row["exits"].append({"pnl": -5.0})          # no time at all
    row["total_pnl"] = -115.0
    assert lt._closed_losses_realized_on([row], DAY2) == -115.0


def test_the_ET_day_decides_earlier():
    """01:30 UTC on Oct 6 is 21:30 ET on Oct 5 — an EARLIER ET day, netted on Oct 6."""
    row = _closed(_leg(-60.0, "2026-10-06T01:30:00+00:00"),
                  _leg(-50.0, "2026-10-06T14:00:00+00:00"))
    assert lt._closed_losses_realized_on([row], DAY2) == -50.0


def test_numeric_total_pnl_and_json_text_exits():
    import json
    legs = [_leg(-60.0, "2026-10-05T19:30:00+00:00"), _leg(-50.0, "2026-10-06T14:00:00+00:00")]
    rows = [{"total_pnl": Decimal("-110.00"), "exits": json.dumps(legs)},
            {"total_pnl": Decimal("-20.00"), "exits": None}]
    assert lt._closed_losses_realized_on(rows, DAY2) == -70.0


# ── the gate ─────────────────────────────────────────────────────────────────────────────────

class _Conn:
    def __init__(self, closed_rows, open_rows):
        self.closed_rows, self.open_rows = closed_rows, open_rows
        self.closed_query = None

    async def fetchval(self, q, *a, **k):
        return 0                                    # open-position counts

    async def fetch(self, q, *a, **k):
        flat = " ".join(q.split())
        if flat.startswith("SELECT total_pnl, exits FROM mi_live_trades"):
            self.closed_query = (flat, a)
            return self.closed_rows
        if "SELECT exits FROM mi_live_trades" in q:
            return self.open_rows
        return []                                   # circuit-breaker streak: none


class _Acq:
    def __init__(self, c):
        self.c = c

    async def __aenter__(self):
        return self.c

    async def __aexit__(self, *e):
        return False


class _Pool:
    def __init__(self, c):
        self.c = c

    def acquire(self, *a, **k):
        return _Acq(self.c)


def _run(monkeypatch, closed_rows, open_rows=(), today=DAY2, equity=5000.0):
    conn = _Conn(closed_rows, list(open_rows))

    async def _pool():
        return _Pool(conn)

    async def _acct(*a, **k):
        return {"equity": equity}

    monkeypatch.setattr(lt, "get_pool", _pool)
    monkeypatch.setattr(lt.alpaca, "get_account", _acct)
    monkeypatch.setattr(lt, "et_today", lambda: today)
    monkeypatch.setattr(lt, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setenv("DRAWDOWN_BREAKER_PHASE", "shadow")
    return asyncio.run(lt._check_safeguards(account_mode="paper")), conn


def test_the_gate_on_the_close_day_counts_only_what_was_realized_that_day(monkeypatch):
    """Equity $5,000 → limit $100. Trade closed today at −$110, of which −$60 was a partial sale
    YESTERDAY (counted yesterday). Today counts −$50 → allowed (before ruling (iv): −$110,
    blocked a second time for yesterday's dollars)."""
    row = _closed(_leg(-60.0, "2026-10-05T19:30:00+00:00"),
                  _leg(-50.0, "2026-10-06T14:00:00+00:00"))
    (ok, reason, _), conn = _run(monkeypatch, [row])
    assert ok is True and reason is None, reason
    q, args = conn.closed_query
    assert "(closed_at AT TIME ZONE 'America/New_York')::date = $1" in q
    assert "status = 'closed' AND total_pnl < 0" in q and args == (DAY2, "paper"), (q, args)


def test_the_gate_still_trips_on_a_same_day_partial_and_close(monkeypatch):
    row = _closed(_leg(-60.0, "2026-10-06T14:00:00+00:00"),
                  _leg(-50.0, "2026-10-06T19:00:00+00:00"))
    (ok, reason, _), _ = _run(monkeypatch, [row])
    assert ok is False and reason.startswith(BLOCK_DAILY_LOSS) and "-110" in reason, reason


def test_the_gate_on_day_1_counts_the_partial_while_the_trade_is_open(monkeypatch):
    """Ruling (1) unchanged: day 1, the trade still open — its −$60 partial counts at once."""
    (ok, reason, _), _ = _run(
        monkeypatch, [_closed(_leg(-45.0, "2026-10-05T15:00:00+00:00"))],
        open_rows=[{"exits": [_leg(-60.0, "2026-10-05T19:30:00+00:00")]}], today=DAY1)
    assert ok is False and "-105" in reason, reason
