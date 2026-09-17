"""A stock pinned by an announced acquisition is excluded AT THE SOURCE, in `get_rs_leaders`.

FOUND 2026-09-17, by the operator, on the evening brief's own line:

    ⚓ Unanchored persistent (5-session, RS≥90) — entered: ACVA
       theme-engine coverage gap — no theme claimed these names all week

His reply: *"From evening brief, but stock is being bought out."* Our own bars already said so —
ACVA gapped **+44.2% on 114.9M shares** on 2026-09-11 (vs a ~3M norm) and every session since
traded a **0.19–0.48%** range at 10.41–10.48. A cash deal price. RS is a backward-looking
1M/3M/6M percentile, so that one gap moved it **rank 1084 → 7**; it was still 17 six sessions
later on flat bars. The surface then asserted a coverage gap that cannot exist — a company being
acquired is un-themeable by construction.

⚠ WHY *HERE* AND NOT IN THE BRIEF. The first cut filtered `brief_composer.compute_unanchored` and
was reverted the same day, on the operator's question *"Is there a better fix upstream so it's
caught at the source"*. Two reasons it was wrong: it would have been the THIRD M&A mechanism in
this codebase (after the retired 9M range rule and `parabolic_detector`'s paid news check), and the
theme engine calls the SAME `get_rs_leaders` (`theme_engine.py:1296`) so it would have kept
ingesting them. `get_rs_leaders` is where the universe is already classified — `SKIP_TICKERS_LIST`,
the `mi_tracked_stocks.quote_type` non-equity clause, `is_sector_filtered` — and a deal pin is the
same KIND of fact: a per-ticker classification every downstream surface inherits for free.

⚠ The RULE is reused, not invented: `db.get_eod_9m_sugar_babies` already carried *"intraday range
>= 2% of close (rejects merger-arb pins like DBRG)"*.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db

ROWS = [
    {"ticker": "ACVA", "rs_composite": 99.3, "sector": "Industrials", "close": 10.42},
    {"ticker": "HURN", "rs_composite": 95.0, "sector": "Industrials", "close": 140.0},
    {"ticker": "CBZ",  "rs_composite": 93.4, "sector": "Industrials", "close": 60.0},
]


def _fake_pool(rows):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = AsyncMock()
    pool.acquire = lambda *a, **k: ctx
    return pool


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=_fake_pool(ROWS)))
    monkeypatch.setattr(db, "_resolve_score_date", AsyncMock(return_value="2026-09-17"))
    calls: list = []

    async def _pinned(as_of, tickers=None, **kw):
        calls.append(list(tickers or []))
        return {"ACVA", "CBZ"}
    monkeypatch.setattr(db, "get_deal_pinned_tickers", _pinned)
    return calls


@pytest.mark.asyncio
async def test_deal_pinned_leaders_are_dropped_at_the_source(wired):
    out = await db.get_rs_leaders("2026-09-17", limit=10)
    names = [r["ticker"] for r in out]
    assert "ACVA" not in names, (
        "ACVA still reached the leaders list — this is the exact name the operator corrected, and "
        "every downstream surface (brief, theme engine) reads this function"
    )
    assert "CBZ" not in names
    assert names == ["HURN"], f"a genuine leader was lost too: {names}"


@pytest.mark.asyncio
async def test_the_classifier_is_scoped_to_the_fetched_rows_not_the_universe(wired):
    """Cheap by construction: screening 9,700 names to filter 60 would be wasteful, and the
    helper's own docstring says the caller scopes it."""
    await db.get_rs_leaders("2026-09-17", limit=10)
    assert wired == [["ACVA", "HURN", "CBZ"]], (
        f"the classifier was not scoped to the fetched tickers: {wired}"
    )


@pytest.mark.asyncio
async def test_include_deal_pinned_opts_back_in_and_skips_the_classifier(wired):
    """Classification lives in one place; POLICY stays the caller's — an M&A monitor should be
    able to ask for them. And opting in must not pay for the screen it does not use."""
    out = await db.get_rs_leaders("2026-09-17", limit=10, include_deal_pinned=True)
    assert [r["ticker"] for r in out] == ["ACVA", "HURN", "CBZ"]
    assert wired == [], "the classifier ran even though the caller opted in to pinned names"


@pytest.mark.asyncio
async def test_the_existing_sector_filter_still_applies(monkeypatch):
    """The new skip must not displace the classifications already living here."""
    rows = [{"ticker": "TINY", "rs_composite": 99.0, "sector": "Healthcare", "close": 4.0},
            {"ticker": "HURN", "rs_composite": 95.0, "sector": "Industrials", "close": 140.0}]
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=_fake_pool(rows)))
    monkeypatch.setattr(db, "_resolve_score_date", AsyncMock(return_value="2026-09-17"))
    monkeypatch.setattr(db, "get_deal_pinned_tickers", AsyncMock(return_value=set()))
    out = await db.get_rs_leaders("2026-09-17", limit=10)
    assert [r["ticker"] for r in out] == ["HURN"], "the small-cap healthcare filter stopped applying"
