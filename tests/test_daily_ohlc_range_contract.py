"""`get_daily_ohlc_range` must return `volume` — pinned against the refactor that dropped it.

2026-09-04: a /simplify dedup folded `get_daily_ohlc_range` and `get_delayed_entry_daily_window`
onto one body and passed `with_volume=False` for this one. The pre-dedup SELECT read
`..., close, volume`. Nothing failed loudly: `sustain_reject_replay` reads `d0_row["volume"]`, so
it raised KeyError on all 95 of its candidates, wrote 0 rows, and its nightly job still reported
success — a recorder erroring on 100% of its population is indistinguishable from a quiet week.

The suite missed it because every test at this layer mocks the DB, so the mocked rows carried
whatever keys the test author supplied. These tests pin the SQL itself and tie it to a real
consumer, so the column cannot be dropped again without going red.
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


@pytest.mark.asyncio
async def test_get_daily_ohlc_range_selects_volume():
    """The contract its callers depend on: volume is in the column list."""
    import datetime as _dt
    conn = _CapturingConn()
    await _db.get_daily_ohlc_range(conn, "TEST", _dt.date(2026, 9, 1), _dt.date(2026, 9, 4))
    assert conn.sql is not None, "the function did not issue a query"
    cols = conn.sql.split("FROM")[0]
    assert "volume" in cols, (
        "get_daily_ohlc_range must SELECT volume — sustain_reject_replay reads d0_row['volume'] "
        f"and raises KeyError on every candidate without it. Column list was: {cols.strip()}"
    )


def test_a_real_consumer_still_reads_the_volume_key():
    """Ties the pin above to an actual reader, so this test cannot rot into a tautology:
    if no caller reads `volume` any more, this fails and the contract can be revisited
    deliberately rather than dropped by accident."""
    src = (_ROOT / "agents/market_intelligence/sustain_reject_replay.py").read_text()
    assert re.search(r'\[["\']volume["\']\]', src), (
        "no consumer reads the 'volume' key any more — if that is deliberate, retire this "
        "contract and its test together, in one commit, rather than letting them drift apart"
    )
