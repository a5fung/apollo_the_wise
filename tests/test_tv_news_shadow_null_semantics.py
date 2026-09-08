"""#210 — `tv_items_we_missed` must keep its THREE states through the DB write.

The column means three different things and a reader acts differently on each:
  [ ... ]  the items TradingView had on the alert date that we did not
  []       we missed NOTHING — a real, earned zero
  NULL     NOT COMPUTABLE — `our_corpus_available` is false, so there is nothing
           stored to diff against (the DDL says so, and tv_news_shadow's else-branch
           deliberately sets None)

The writer coerced None -> [] at the boundary, so "cannot tell" was stored as
"clean" — in the instrument built to COUNT news misses. Caught on the very first row
ever written (ALAB 2026-09-04): no corpus on our side, 25 TradingView items, stored
as []. Same false-zero class as #452, #414 and #540 this week.
"""
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import db as dbmod


def _row(missed):
    return {c: None for c in dbmod._TV_NEWS_SHADOW_COLS} | {
        "ticker": "ALAB", "alert_date": "2026-09-04", "tv_items_we_missed": missed,
    }


async def _captured(rows):
    conn = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = AsyncMock()
    pool.acquire = lambda *a, **k: ctx
    with patch.object(dbmod, "get_pool", new=AsyncMock(return_value=pool)):
        await dbmod.upsert_tv_news_shadow_rows(rows)
    vals = conn.executemany.await_args.args[1]
    idx = dbmod._TV_NEWS_SHADOW_COLS.index("tv_items_we_missed")
    return [v[idx] for v in vals]


@pytest.mark.asyncio
async def test_not_computable_stays_null():
    """The bug: None became [], which reads as a clean row forever after."""
    assert await _captured([_row(None)]) == [None]


@pytest.mark.asyncio
async def test_an_earned_zero_is_still_an_empty_list():
    """[] must survive as [] — 'we missed nothing' is a real finding, not absence."""
    got = await _captured([_row([])])
    assert got[0] is not None, "an earned zero must not be turned into NULL"


@pytest.mark.asyncio
async def test_real_misses_survive_the_write():
    item = {"title": "X", "provider": "benzinga", "published": "2026-09-04T12:00:00Z"}
    got = await _captured([_row([item])])
    assert got[0] is not None and "benzinga" in str(got[0])
