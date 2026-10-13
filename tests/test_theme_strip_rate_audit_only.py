"""The theme strip-rate check records an audit row and sends nothing (operator 2026-10-13).

The strips it counts have already happened (validation removed the misfit members, the
rehome moved the rest), so a Telegram line asking him to "review" had no action behind it.
"""
import asyncio
from datetime import date, datetime, timezone

from agents.market_intelligence import briefing, db, scheduler


class _Conn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, *_a, **_k):
        return self._rows

    async def fetchval(self, *_a, **_k):
        return None  # not alarmed before → the row is new


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_a):
        return False


class _Pool:
    def __init__(self, rows):
        self._conn = _Conn(rows)

    def acquire(self):
        return _Acquire(self._conn)


def test_strip_rate_writes_the_audit_row_and_sends_no_telegram(monkeypatch):
    row = {"name": "Quick-Service & Fast-Casual Restaurant Franchisors",
           "theme_date": date(2026, 10, 9),
           "created_at": datetime(2026, 10, 9, 21, 9, tzinfo=timezone.utc),
           "member_count": 3, "stripped_within_3d": 2}
    audits, sends = [], []

    async def _get_pool():
        return _Pool([row])

    async def _audit(event_type, **kw):
        audits.append((event_type, kw))

    async def _send(*a, **k):
        sends.append(a)
        return True

    monkeypatch.setattr(db, "get_pool", _get_pool)
    monkeypatch.setattr(db, "log_audit_event", _audit)
    monkeypatch.setattr(briefing, "send_telegram_message", _send)

    asyncio.run(scheduler._theme_round_trip_validator_job())

    assert [a[0] for a in audits] == ["theme_high_strip_rate"]
    assert "2/3 members stripped within 3d of creation (67%)" in audits[0][1]["summary"]
    assert sends == []
