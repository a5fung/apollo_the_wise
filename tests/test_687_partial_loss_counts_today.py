"""#687 ruling (1), operator 2026-10-01 ("Yes"): a loss on a PARTIAL sale counts toward the 2%
daily loss limit AT ONCE.

The daily-loss gate (`live_tracker._check_safeguards`) summed `total_pnl` of trades CLOSED today.
A sale that sells part of a position at a loss and leaves the rest open — the close-below sale
beside a resting +8R profit-take third (#687 a+b keep that row open), or a stop that partly filled
— was invisible to it until the remainder exited, possibly days later. Now each losing leg dated
today (ET) on a still-open trade is added. The closed-trade query itself is unchanged (its shape
is pinned by tests/test_daily_loss_close_day.py).
"""
import asyncio
import json
from datetime import date

import pytest

from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker.skip_reasons import BLOCK_DAILY_LOSS

TODAY = date(2026, 10, 6)


def _leg(pnl, time):
    return {"shares": 2, "price": 10.0, "pnl": pnl, "time": time, "reason": "x"}


# ── the pure helper ──────────────────────────────────────────────────────────────────────────

def test_a_losing_partial_leg_today_counts():
    rows = [{"exits": [_leg(-60.0, "2026-10-06T13:31:00+00:00")]}]
    assert lt._partial_losses_realized_on(rows, TODAY) == -60.0


def test_a_profit_leg_never_counts_and_never_offsets_a_loss():
    rows = [{"exits": [_leg(+90.0, "2026-10-06T14:00:00+00:00"),
                       _leg(-25.0, "2026-10-06T19:00:00+00:00")]}]
    assert lt._partial_losses_realized_on(rows, TODAY) == -25.0


def test_a_leg_from_an_earlier_day_does_not_count_today():
    rows = [{"exits": [_leg(-60.0, "2026-10-05T13:31:00+00:00")]}]
    assert lt._partial_losses_realized_on(rows, TODAY) == 0.0


def test_the_day_is_the_ET_day_not_the_UTC_day():
    """01:30 UTC on Oct 7 is 21:30 ET on Oct 6 — still today. 03:30 UTC Oct 6 is Oct 5 ET."""
    rows = [{"exits": [_leg(-10.0, "2026-10-07T01:30:00+00:00"),
                       _leg(-7.0, "2026-10-06T03:30:00+00:00")]}]
    assert lt._partial_losses_realized_on(rows, TODAY) == -10.0


def test_a_naive_stamp_is_read_as_ET_wall_clock():
    """exit_logic writes `datetime.combine(today, 16:00).isoformat()` — no zone, ET by intent."""
    rows = [{"exits": [_leg(-5.0, "2026-10-06T16:00:00")]}]
    assert lt._partial_losses_realized_on(rows, TODAY) == -5.0


def test_exits_as_json_text_and_legs_without_pnl_or_time():
    rows = [{"exits": json.dumps([_leg(-3.0, "2026-10-06T15:00:00+00:00"),
                                  {"pnl": -99.0}, {"time": "2026-10-06T15:00:00+00:00"},
                                  _leg(None, "2026-10-06T15:00:00+00:00")])},
            {"exits": "not json"}, {"exits": None}]
    assert lt._partial_losses_realized_on(rows, TODAY) == -3.0


# ── the gate ─────────────────────────────────────────────────────────────────────────────────

class _Conn:
    def __init__(self, closed_losses, open_exit_rows):
        self.closed_losses, self.open_exit_rows = closed_losses, open_exit_rows
        self.open_query = None

    async def fetchval(self, q, *a, **k):
        if "SUM(total_pnl)" in q:
            return self.closed_losses
        return 0                                    # open-position counts

    async def fetch(self, q, *a, **k):
        if "SELECT exits FROM mi_live_trades" in q:
            self.open_query = (q, a)
            return self.open_exit_rows
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


def _run(monkeypatch, closed_losses, open_rows, equity=5000.0):
    conn = _Conn(closed_losses, open_rows)

    async def _pool():
        return _Pool(conn)

    async def _acct(*a, **k):
        return {"equity": equity}

    monkeypatch.setattr(lt, "get_pool", _pool)
    monkeypatch.setattr(lt.alpaca, "get_account", _acct)
    monkeypatch.setattr(lt, "et_today", lambda: TODAY)
    monkeypatch.setattr(lt, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setenv("DRAWDOWN_BREAKER_PHASE", "shadow")
    return asyncio.run(lt._check_safeguards(account_mode="paper")), conn


def test_a_partial_loss_today_trips_the_limit_at_once(monkeypatch):
    """Equity $5,000 → limit $100. Closed today: −$50. A 2/3 sale today at −$60 on a trade still
    open under its profit-take third: −$110 → blocked NOW (before the fix: −$50, allowed)."""
    (ok, reason, mult), conn = _run(
        monkeypatch, -50.0, [{"exits": [_leg(-60.0, "2026-10-06T13:30:05+00:00")]}])
    assert ok is False and reason.startswith(BLOCK_DAILY_LOSS), reason
    assert "-110" in reason, reason
    q, args = conn.open_query
    assert "status <> 'closed'" in q and args == ("paper",), (q, args)


def test_without_a_partial_loss_the_gate_reads_exactly_as_before(monkeypatch):
    (ok, reason, mult), _ = _run(monkeypatch, -50.0, [{"exits": [_leg(+40.0, "2026-10-06T14:00:00+00:00")]}])
    assert ok is True and reason is None, reason


def test_closed_losses_alone_still_trip_it(monkeypatch):
    (ok, reason, _), _ = _run(monkeypatch, -100.0, [])
    assert ok is False and reason.startswith(BLOCK_DAILY_LOSS), reason


@pytest.mark.parametrize("closed", [-50.0, None])
def test_a_numeric_or_null_closed_sum_adds_cleanly(monkeypatch, closed):
    """asyncpg returns NUMERIC as Decimal; the open-trade arm is float — they must add."""
    from decimal import Decimal
    c = Decimal(str(closed)) if closed is not None else None
    (ok, reason, _), _ = _run(monkeypatch, c, [{"exits": [_leg(-60.0, "2026-10-06T13:30:05+00:00")]}])
    assert ok is (closed is None), reason
