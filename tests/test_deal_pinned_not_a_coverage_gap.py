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


# ══════════════════════════════════════════════════════════════════════════════════════
# THE SECOND HALF, added the same evening by review — `get_rs_leaders` was ONE OF FIVE.
#
# The first fix filtered the leaders and the SSoT said "the theme engine is fixed by
# inheritance". That inheritance claim was tested against ONE call site. The live gather
# (`theme_engine.py:7886`) takes leaders + velocity + turners; a second live gather (`:7919`,
# behind `birth_gate_on`) adds accelerators + recovery-slope; `run_theme_discovery_shadow`
# (`:1296`) takes all five unconditionally.
#
# ⚠ THE LAST TWO WERE FOUND BY THE STRUCTURAL GUARD AT THE BOTTOM OF THIS FILE, not by
# inspection — it went RED on its first run against a fix believed complete. They are also the
# most deal-shaped selectors of the five: `get_rs_accelerators` fires on a rank improvement of
# >=800 places or an RS jump >=25 in two sessions (ACVA: 1084 -> 7, RS 54 -> 99 — both arms),
# and `get_rs_recovery_slope` fires on `rs_1m>=90 AND rs_6m<=30`, which IS the post-gap shape.
# They are dark in live today (prod birth gate reads `dedup_only`); filtered anyway, because a
# dark selector is the one nobody re-checks the day it is switched on.
#
# Not theoretical: with only the leaders filtered, **BWMN was in the LIVE velocity top-30 on
# prod on 2026-09-17** while being gone from the leaders; ACVA and MKTX sat in the uncapped
# velocity pool one rank move away. Velocity is the worst leg to leave open — an announcement
# gap IS a one-week RS jump, so a pinned name scores maximum front-weighted velocity for the
# four weeks the gap sits in the window (ACVA: RS 54 -> 99 in one session).
#
# Same day's recurring defect in a new costume: the population, never the arithmetic.
# ══════════════════════════════════════════════════════════════════════════════════════

VEL_ROWS = [
    {"ticker": "BWMN", "rs_now": 93.0, "velocity_score": 41.0},   # the live leak, 2026-09-17
    {"ticker": "HURN", "rs_now": 95.0, "velocity_score": 12.0},
    {"ticker": "ACVA", "rs_now": 99.0, "velocity_score": 45.0},
]


@pytest.fixture
def wired_weekly(monkeypatch):
    """Velocity and turners both run through `_prepare_weekly_snapshots`, so it is stubbed to
    a resolved date rather than re-deriving snapshot dates that are irrelevant here."""
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=_fake_pool(VEL_ROWS)))
    monkeypatch.setattr(
        db, "_prepare_weekly_snapshots",
        AsyncMock(return_value=(["2026-09-17"], ["2026-09-17"], "2026-09-17",
                                "2026-09-10", "2026-09-03", "2026-08-27", "2026-08-20")),
    )
    calls: list = []

    async def _pinned(as_of, tickers=None, **kw):
        calls.append(list(tickers or []))
        return {"ACVA", "BWMN"}
    monkeypatch.setattr(db, "get_deal_pinned_tickers", _pinned)
    return calls


@pytest.mark.asyncio
async def test_velocity_drops_the_name_that_was_live_in_the_top_30(wired_weekly):
    """BWMN, the row observed in prod's velocity top-30 on 2026-09-17 while prod still ran
    UNFILTERED code. The leaders-only fix would have dropped it from the leaders and left it
    here — so this asserts the pool it would have survived in."""
    out = await db.get_rs_velocity("2026-09-17", limit=10)
    names = [r["ticker"] for r in out]
    assert "BWMN" not in names, (
        "BWMN reached the velocity list — the EXACT row observed in prod's velocity top-30 on "
        "2026-09-17, which a leaders-only fix would have left untouched. Velocity feeds theme "
        "discovery at every gather site."
    )
    assert "ACVA" not in names
    assert names == ["HURN"], f"a genuine velocity name was lost too: {names}"


@pytest.mark.asyncio
async def test_turners_apply_the_same_filter(wired_weekly):
    """No measured hit on 2026-09-17 (a pinned name is a weak turner by construction — turners
    need RS <= 30 four weeks ago). Pinned here anyway: 'no hit today' is not a reason to leave
    the third input open, and this is the test that says so out loud."""
    out = await db.get_rs_turners("2026-09-17", limit=10)
    assert [r["ticker"] for r in out] == ["HURN"]


@pytest.mark.asyncio
async def test_velocity_and_turners_scope_the_classifier_and_honour_the_opt_in(wired_weekly):
    await db.get_rs_velocity("2026-09-17", limit=10, include_deal_pinned=True)
    assert wired_weekly == [], "the classifier ran even though the caller opted in"
    await db.get_rs_velocity("2026-09-17", limit=10)
    assert wired_weekly == [["BWMN", "HURN", "ACVA"]], (
        f"velocity did not scope the classifier to its own fetched rows: {wired_weekly}"
    )


# ── the structural guard: a SEVENTH pool must not be able to leak the same way ─────────
#
# ⚠ THIS GUARD WAS REPLACED THE SAME EVENING, AND THE REPLACEMENT IS WHY.
# The first version AST-walked `theme_engine.py`'s `asyncio.gather` calls to derive the pool
# list. It found `get_rs_accelerators` and `get_rs_recovery_slope` — two pools nobody had looked
# at — by going RED on its first run. But its own population was wrong in the same way the fix
# had been: it could only see pools passed to a `gather`, in one file. A repo-wide AST sweep
# then found `get_rs_velocity`/`get_rs_turners` called BARE in `theme_synthesis.py`, and a SIXTH
# pool — `get_rs_recovery` — feeding the evening brief's RECOVERY section from `briefing.py`,
# outside any gather and outside the theme engine entirely.
#
# So the derivation moved DOWN a level, from call sites to definitions: every RS POOL in `db`
# must carry the flag, wherever it is called from and whether it is called at all. That is
# strictly stronger (call-site-independent), catches a new pool at definition rather than at
# wiring, and — because `inspect.signature` on an imported function reads no source text — it
# is not a source pin, so the #653 baseline goes back DOWN to 404 rather than up.
#
# POOL vs LOOKUP is derived, never hand-listed: a pool ranks a population and takes `limit`;
# a lookup answers about names you already hold and takes `tickers`/`conn`. On 2026-09-17 that
# split 9 `get_rs_*` functions into 6 pools and 3 lookups with no overlap.

import inspect


def _rs_pools() -> dict:
    """Every ranked RS population in `db`, derived from signatures. A hand-kept list would rot
    the way the "fixed by inheritance" claim did and then certify the rot."""
    out = {}
    for name in dir(db):
        if not name.startswith("get_rs_"):
            continue
        fn = getattr(db, name)
        if not callable(fn):
            continue
        params = inspect.signature(fn).parameters
        if "limit" in params and "tickers" not in params and "conn" not in params:
            out[name] = params
    return out


def test_every_rs_pool_can_exclude_deal_pinned_names():
    """THE GUARD THIS FILE'S SECOND HALF EXISTS FOR. Any function that ranks an RS population
    must be able to drop deal-pinned names, or one walks in through whichever pool was
    forgotten — which is what BWMN was positioned to do through velocity, and what the brief's
    RECOVERY section could have done with no theme engine involved at all.

    A NEW seventh pool reddens this the day it is DEFINED, before it is ever wired up."""
    pools = _rs_pools()
    assert len(pools) >= 6, (
        f"expected at least the six known RS pools, found {sorted(pools)} — the derivation "
        f"broke. Fix it; do not delete the guard: empty here means every assertion below "
        f"passes by vacuity, which reads exactly like passing."
    )
    for name, params in sorted(pools.items()):
        assert "include_deal_pinned" in params, (
            f"db.{name} ranks an RS population but cannot exclude deal-pinned names. That is "
            f"the 2026-09-17 leak: the leaders were filtered, the SSoT claimed the theme engine "
            f"was 'fixed by inheritance', and five other pools were never looked at."
        )
        assert params["include_deal_pinned"].default is False, (
            f"db.{name} defaults to INCLUDING deal-pinned names — the filter is off by default"
        )


def test_the_pool_lookup_split_is_derived_and_does_not_swallow_lookups():
    """The other half: the rule must not drag per-ticker lookups in. `get_rs_for_tickers`,
    `get_rs_history` and `get_rs_on_date` answer about names the caller already holds — there
    is nothing to exclude, and demanding the flag there would be noise that teaches people to
    add it thoughtlessly."""
    pools = _rs_pools()
    for lookup in ("get_rs_for_tickers", "get_rs_history", "get_rs_on_date"):
        assert hasattr(db, lookup), f"{lookup} is gone — re-derive the split before trusting it"
        assert lookup not in pools, (
            f"{lookup} was classified as a ranked pool. It takes an explicit ticker list, so "
            f"the caller has already chosen the names; the split rule has drifted."
        )
