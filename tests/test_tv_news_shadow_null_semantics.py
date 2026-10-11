"""#210 — `tv_items_we_missed` AND `tv_items_unmatched_seen` must keep their THREE states through
the DB write (and `tv_match_summary` its two).

The columns mean three different things and a reader acts differently on each:
  [ ... ]  the items TradingView had on the alert date that we did not
  []       we missed NOTHING — a real, earned zero
  NULL     NOT COMPUTABLE — no corpus (or no capture time) to diff against, or, for
           `tv_items_we_missed` only, a window that does not reach the start of the alert's
           news day (the DDL says so, and tv_news_shadow deliberately sets None)

The writer coerced None -> [] at the boundary, so "cannot tell" was stored as
"clean" — in the instrument built to COUNT news misses. Caught on the very first row
ever written (ALAB 2026-09-04): no corpus on our side, 25 TradingView items, stored
as []. Same false-zero class as #452, #414 and #540 this week. The #210 build (2026-10-10)
added a SECOND list column (`tv_items_unmatched_seen`) and a nullable dict column
(`tv_match_summary`), so the same three tests run over BOTH list columns and a fourth pins
the dict.
"""
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import db as dbmod

LIST_COLS = ["tv_items_we_missed", "tv_items_unmatched_seen"]


def _row(col, value):
    return {c: None for c in dbmod._TV_NEWS_SHADOW_COLS} | {
        "ticker": "ALAB", "alert_date": "2026-09-04", col: value,
    }


async def _captured(rows, col):
    conn = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = AsyncMock()
    pool.acquire = lambda *a, **k: ctx
    with patch.object(dbmod, "get_pool", new=AsyncMock(return_value=pool)):
        await dbmod.upsert_tv_news_shadow_rows(rows)
    vals = conn.executemany.await_args.args[1]
    idx = dbmod._TV_NEWS_SHADOW_COLS.index(col)
    return [v[idx] for v in vals]


@pytest.mark.parametrize("col", LIST_COLS)
@pytest.mark.asyncio
async def test_not_computable_stays_null(col):
    """The bug: None became [], which reads as a clean row forever after."""
    assert await _captured([_row(col, None)], col) == [None]


@pytest.mark.parametrize("col", LIST_COLS)
@pytest.mark.asyncio
async def test_an_earned_zero_is_still_an_empty_list(col):
    """[] must survive as [] — 'we missed nothing' is a real finding, not absence."""
    got = await _captured([_row(col, [])], col)
    assert got[0] is not None, "an earned zero must not be turned into NULL"


@pytest.mark.parametrize("col", LIST_COLS)
@pytest.mark.asyncio
async def test_real_misses_survive_the_write(col):
    item = {"title": "X", "provider": "benzinga", "published": "2026-09-04T12:00:00Z"}
    got = await _captured([_row(col, [item])], col)
    assert got[0] is not None and "benzinga" in str(got[0])


@pytest.mark.asyncio
async def test_match_summary_null_stays_null_and_a_dict_survives():
    """`tv_match_summary` is NOT in the dict-columns set that coerces None -> {} (that would
    store 'not computed' as 'computed, empty'); NULL stays NULL, a real summary survives."""
    assert await _captured([_row("tv_match_summary", None)], "tv_match_summary") == [None]
    summary = {"before_grade": {"title": 2}, "repoll_window": {}, "after_cutoff": {"none": 1}}
    got = await _captured([_row("tv_match_summary", summary)], "tv_match_summary")
    assert got == [summary]


def test_every_json_column_binds_with_an_explicit_jsonb_cast():
    """A jsonb column bound without ::jsonb is the #216 double-encode class. All four JSON
    columns the upsert writes (two dicts, the nullable dict, two lists) carry the cast."""
    sql = dbmod._TV_NEWS_SHADOW_UPSERT_SQL
    cols = list(dbmod._TV_NEWS_SHADOW_COLS)
    for c in ("tv_providers", "tv_providers_on_alert_date", "tv_items_we_missed",
              "tv_items_unmatched_seen", "tv_match_summary"):
        assert f"${cols.index(c) + 1}::jsonb" in sql, c
    assert f"${cols.index('our_captured_at') + 1}::jsonb" not in sql
