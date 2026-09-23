"""#p74 (2026-08-11) — get_flag_universe path (c), the MAGNA53 R3-carryforward,
hardcoded `AND account_mode = 'paper'`. Correct when P7.2 shipped 2026-05-17
(MAGNA53 was paper-only then); silently wrong from ~2026-06-22 once MAGNA53
graduated to live — the literal never followed the strategy's phase. Measured
against prod: the buggy query admitted 0 tickers via this path over the
trailing 30 days; dropping the mode filter (the chosen fix — see the
db.py comment for why the resolver was considered and rejected) restores it
to 13.

These tests pin the query construction (no account_mode literal survives)
and the merge behavior (a ticker's tag lands regardless of which book its
stop-out was recorded under) so the mode filter cannot silently come back.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import db as db_mod


def _rows(tickers, extra_cols=None):
    """Build fake asyncpg Record-like rows: list[dict] with a 'ticker' key
    (+ any extra columns the organic query's boolean tags need)."""
    out = []
    for t in tickers:
        row = {"ticker": t}
        if extra_cols:
            row.update(extra_cols)
        out.append(row)
    return out


@pytest.mark.asyncio
async def test_path_c_query_has_no_account_mode_literal():
    """The query text for path (c) must not filter on account_mode at all —
    neither the old hardcoded 'paper' bug nor a re-introduced 'live' swap
    (same rot, new expiry date). The untouched pieces (skip_reason literal,
    7-day lookback, status='closed') must survive unchanged."""
    from tests.conftest import make_mock_pool

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])  # every path returns empty rows

    with patch.object(db_mod, "get_pool", new=AsyncMock(return_value=pool)):
        result = await db_mod.get_flag_universe("2026-08-11")

    assert result == {}

    sqls = [c.args[0] for c in conn.fetch.await_args_list]
    r3_sqls = [s for s in sqls if "r3_reentry_disabled" in s]
    assert r3_sqls, "expected one query filtering on skip_reason = 'block:r3_reentry_disabled'"
    assert len(r3_sqls) == 1
    r3_sql = r3_sqls[0]

    # The bug + its "fix by swapping the literal" trap — neither may appear.
    assert "account_mode" not in r3_sql, (
        f"path (c) must not filter on account_mode (mode-agnostic by design):\n{r3_sql}"
    )
    # Untouched per the task constraints: same window, same skip_reason, same terminal status.
    assert "INTERVAL '7 days'" in r3_sql
    assert "skip_reason = 'block:r3_reentry_disabled'" in r3_sql
    assert "status = 'closed'" in r3_sql


@pytest.mark.asyncio
async def test_path_c_admits_tickers_regardless_of_originating_book():
    """Behavioral: a ticker whose R3 stop-out was recorded in EITHER book
    must land in the returned universe tagged 'magna53_failed_r3'. Before
    the fix, a ticker stopped out post-cutover (live book) was invisible —
    this is the exact defect class (MAGNA53 graduated to live 2026-06-22,
    the hardcoded filter only ever looked at paper)."""
    from tests.conftest import make_mock_pool

    pool, conn = make_mock_pool()
    # Call order inside get_flag_universe: (a+b) organic, (c) r3, (d) 9m, (e) stage-carry.
    conn.fetch = AsyncMock(side_effect=[
        [],                                    # (a+b) organic — none
        _rows(["LIVETICK", "PAPTICK"]),        # (c) r3 — one from each book, indistinguishable
        [],                                    # (d) 9m universe-watch — none
        [],                                    # (e) flag-stage carryforward — none
    ])

    with patch.object(db_mod, "get_pool", new=AsyncMock(return_value=pool)):
        result = await db_mod.get_flag_universe("2026-08-11")

    assert result.get("LIVETICK") == ["magna53_failed_r3"]
    assert result.get("PAPTICK") == ["magna53_failed_r3"]


@pytest.mark.asyncio
async def test_path_c_respects_disable_env_flag(monkeypatch):
    """Untouched control surface: MAGNA53_FLAG_CARRYFORWARD_ENABLED=false must
    still skip path (c) entirely (no r3 query issued, no magna53_failed_r3 tag)."""
    from tests.conftest import make_mock_pool

    monkeypatch.setenv("MAGNA53_FLAG_CARRYFORWARD_ENABLED", "false")
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[
        [],   # (a+b) organic
        [],   # (d) 9m
        [],   # (e) stage-carry
    ])

    with patch.object(db_mod, "get_pool", new=AsyncMock(return_value=pool)):
        result = await db_mod.get_flag_universe("2026-08-11")

    assert result == {}
    sqls = [c.args[0] for c in conn.fetch.await_args_list]
    assert not any("r3_reentry_disabled" in s for s in sqls)
