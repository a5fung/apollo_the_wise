"""`get_delayed_entry_daily_window` must return `volume` — the untested sibling of the
2026-09-04 `get_daily_ohlc_range` incident.

Both functions share one body, `db._daily_closes_range(conn, ticker, start, end, *,
with_volume)`. The incident (see `test_daily_ohlc_range_contract.py`) was a /simplify dedup
that passed `with_volume=False` for `get_daily_ohlc_range` when a real consumer
(`sustain_reject_replay`) read `d0_row["volume"]` — a loud `KeyError` on every candidate. The
fix restored `with_volume=True` and pinned it with a contract test, but only for that one
wrapper. `get_delayed_entry_daily_window` (`db.py`, `with_volume=True`) is the OTHER caller of
the same shared body and had no equivalent pin — a future edit that flips its flag would
regress silently rather than loudly:

`delayed_entry_shadow.py` reads the window's `volume` with `.get("volume")`, not `["volume"]`
(`enroll_new_members` and the pivot-refetch branch inside the delayed-entry walk both do this,
to compute `ep_dollar_volume` for `compute_screen_member`). `compute_screen_member` already
treats a missing component as `None` ("unknown") by design, so a dropped `volume` column would
never raise — it would just quietly turn every freshly-computed `screen_member` into `None`,
the exact "wrong number reaches a report instead of an exception" shape the KeyError sibling
warns about, only quieter.

These tests pin the SQL itself and tie it to the real consumers, mirroring
test_daily_ohlc_range_contract.py's shape.
"""
import re
from pathlib import Path

import pytest

from agents.market_intelligence import db as _db

_ROOT = Path(__file__).resolve().parents[1]


class _CapturingConn:
    """Captures the SQL instead of executing it."""
    def __init__(self):
        self.sql = None

    async def fetch(self, sql, *args):
        self.sql = sql
        return []


class _FakePool:
    """Just enough of asyncpg's Pool.acquire() context-manager protocol to hand back a
    fixed capturing connection."""
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _CM:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _CM()


@pytest.mark.asyncio
async def test_get_delayed_entry_daily_window_selects_volume(monkeypatch):
    """The contract its callers depend on: volume is in the column list. Calls the PUBLIC
    wrapper (not the shared private body) so a future edit that flips its own with_volume
    literal — the exact shape of the 2026-09-04 incident, just on the sibling wrapper —
    fails this without needing a live DB."""
    import datetime as _dt
    conn = _CapturingConn()

    async def _fake_pool():
        return _FakePool(conn)

    monkeypatch.setattr(_db, "get_pool", _fake_pool)
    await _db.get_delayed_entry_daily_window("TEST", _dt.date(2026, 9, 1), _dt.date(2026, 9, 4))
    assert conn.sql is not None, "the function did not issue a query"
    cols = conn.sql.split("FROM")[0]
    assert "volume" in cols, (
        "get_delayed_entry_daily_window must SELECT volume — delayed_entry_shadow's "
        "enroll_new_members and pivot-refetch path both read window[0].get('volume') to "
        f"compute ep_dollar_volume for the screen gate. Column list was: {cols.strip()}"
    )


def test_a_real_consumer_still_reads_the_volume_key():
    """Ties the pin above to actual readers, so this test cannot rot into a tautology: if no
    caller reads `volume` off a get_delayed_entry_daily_window result any more, this fails and
    the contract can be revisited deliberately rather than dropped by accident."""
    src = (_ROOT / "agents/market_intelligence/delayed_entry_shadow.py").read_text()
    assert re.search(r'window\[0\]\.get\(["\']volume["\']\)', src), (
        "no consumer reads the 'volume' key off a get_delayed_entry_daily_window result any "
        "more — if that is deliberate, retire this contract and its test together, in one "
        "commit, rather than letting them drift apart"
    )
