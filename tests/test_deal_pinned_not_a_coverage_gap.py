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

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

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


# ── the structural guard: a FOURTH input must not be able to leak the same way ─────────

def _discovery_inputs_gathered_by_the_theme_engine() -> set[str]:
    """DERIVED from theme_engine.py, never hand-listed — a hand-kept list would rot exactly
    the way the 'fixed by inheritance' claim did, and would then certify the rot. Same
    reasoning as tests/test_deploy_scope_core_copies.py and scripts/exec_loaded_modules.txt.

    Returns every `db.get_rs_*` / `get_rs_*` function name appearing inside an
    `asyncio.gather(...)` in theme_engine.py — i.e. the RS pools that feed discovery and
    assignment together."""
    tree = ast.parse((REPO / "agents" / "market_intelligence" / "theme_engine.py")
                     .read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if name != "gather":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Call):
                inner = arg.func
                iname = inner.attr if isinstance(inner, ast.Attribute) else getattr(inner, "id", "")
                if iname.startswith("get_rs_"):
                    found.add(iname)
    return found


def test_every_rs_pool_the_theme_engine_gathers_can_exclude_deal_pinned_names():
    """THE GUARD THIS FILE'S SECOND HALF EXISTS FOR, and the one that FOUND the last two pools.
    Any RS pool gathered alongside the others to feed theme discovery must carry the same
    classification, or a pinned name walks in through whichever input was forgotten. A NEW
    sixth pool reddens this the day it is added, not the day someone notices a deal stock
    sitting inside a theme.

    ⚠ The vacuity guard is folded in below rather than living as its own test: a derivation
    that reads EMPTY makes every assertion here pass, which looks exactly like passing.

    # source-pin-ok: a WIRING check — that the five RS pools theme_engine actually gathers each
    # carry the flag. The gathered SET exists only in theme_engine's source; there is no runtime
    # seam short of executing live discovery (Perplexity, DB, sector enrichment). This is the
    # case check_test_source_pins' own docstring reserves the escape for ("a correct helper
    # nobody called"), and the derivation is AST-walked, never hand-listed — a hand-kept list
    # would rot the way the "fixed by inheritance" claim did and then certify the rot. Same
    # reasoning as tests/test_deploy_scope_core_copies.py deriving from the Dockerfile.
    """
    import inspect
    pools = _discovery_inputs_gathered_by_the_theme_engine()
    assert len(pools) >= 3, (
        f"expected the theme engine to gather at least leaders + velocity + turners, found "
        f"{sorted(pools)} — the extraction broke, or the gather sites moved. Fix the extraction; "
        f"do not delete the guard: empty here means every assertion below passes by vacuity."
    )
    for fname in sorted(pools):
        fn = getattr(db, fname, None)
        assert fn is not None, f"theme_engine gathers db.{fname} but it does not exist"
        params = inspect.signature(fn).parameters
        assert "include_deal_pinned" in params, (
            f"db.{fname} feeds theme discovery but cannot exclude deal-pinned names. That is "
            f"the 2026-09-17 leak: the leaders were filtered, the SSoT claimed the engine was "
            f"'fixed by inheritance', and BWMN was live in the velocity top-30 the same day."
        )
        assert params["include_deal_pinned"].default is False, (
            f"db.{fname} defaults to INCLUDING deal-pinned names — the filter is off by default"
        )
