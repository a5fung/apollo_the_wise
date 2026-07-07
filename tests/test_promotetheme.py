"""/promotetheme — operator single-candidate theme promotion (theme_engine.promote_candidate_by_name).

The promoted theme is written exactly like the nightly auto-promote (source='shadow_promoted') and then
behaves like ANY other theme (operator 6/29: no special treatment — daily discovery re-writes it while
the cohort co-moves; the 7d recency cap ages it out if it dissolves). These pin the lookup branches +
the write.
"""
import datetime as _dt
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import theme_engine as te
from agents.market_intelligence import db as dbmod

_TODAY = _dt.date(2026, 6, 29)


def _cand(name, tickers, thesis="thesis", source="rs_slope_synthesis"):
    return {"name": name, "tickers": list(tickers), "thesis": thesis, "source": source}


@pytest.mark.asyncio
async def test_not_found_lists_available(monkeypatch):
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates",
                        AsyncMock(return_value=[_cand("Rare Biotech", ["A", "B", "C"])]))
    res = await te.promote_candidate_by_name("nonexistent xyz", _TODAY)
    assert res["status"] == "not_found"
    assert "Rare Biotech" in res["available"]


@pytest.mark.asyncio
async def test_too_few_members(monkeypatch):
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates",
                        AsyncMock(return_value=[_cand("Tiny", ["A", "B"])]))
    res = await te.promote_candidate_by_name("tiny", _TODAY)
    assert res["status"] == "too_few"
    assert res["n_members"] == 2


@pytest.mark.asyncio
async def test_ambiguous_substring(monkeypatch):
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        _cand("Rare Metals", ["A", "B", "C"]), _cand("Rare Pharma", ["D", "E", "F"])]))
    res = await te.promote_candidate_by_name("rare", _TODAY)
    assert res["status"] == "ambiguous"
    assert len(res["matches"]) == 2


@pytest.mark.asyncio
async def test_promoted_writes_shadow_promoted(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])          # RS-lookup → empty (rs_avg None)
    conn.fetchrow = AsyncMock(return_value=None)     # no prior days_active
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        _cand("Rare & Orphan Biotech Re-Rating", ["RARE", "MIRM", "RGNX", "AGIO"])]))
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))   # no rename
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())

    res = await te.promote_candidate_by_name("rare orphan", _TODAY)

    assert res["status"] == "promoted"
    assert res["name"] == "Rare & Orphan Biotech Re-Rating"
    assert res["n_members"] == 4
    assert res["canonicalized"] is False
    # the live write fired with the auto-promote's source (behaves like any other theme)
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO mi_themes" in sql
    assert "'shadow_promoted'" in sql


@pytest.mark.asyncio
async def test_noop_when_guard_skips_live_theme(monkeypatch):
    # ON CONFLICT WHERE source='shadow_promoted' skips a native live theme → "INSERT 0 0" → noop
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 0")
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        _cand("Already Live", ["X", "Y", "Z"])]))
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())

    res = await te.promote_candidate_by_name("already live", _TODAY)
    assert res["status"] == "noop"


# ─── F7 (2026-07-02 review) — shared write path ────────────────────────────
# `promote_candidate_by_name` (operator /promotetheme) and `promote_shadow_themes` (nightly
# auto-promote) used to hand-copy the SAME guarded INSERT...ON CONFLICT — a future change to
# one copy could silently diverge the operator path from the nightly job. Both now delegate to
# `theme_engine._upsert_promoted_theme`. These pin (1) the helper's own SQL/merge semantics and
# (2) that BOTH public entry points actually call it with equivalent params for an equivalent
# candidate, so a re-introduced hand-copy would show up as a routing/param mismatch here.

@pytest.mark.asyncio
async def test_upsert_promoted_theme_merge_and_sql():
    """Direct pin on the shared helper: desc fallback, days_active roll-forward, score from
    rs_avg, and the guarded UPSERT SQL text (the load-bearing 'source = shadow_promoted' clause)."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value="INSERT 0 1")

    wrote = await te._upsert_promoted_theme(
        conn, "Rare & Orphan Biotech Re-Rating", ["RARE", "MIRM"], None,
        "fallback desc", _TODAY, rs_avg=42.5, prior_days_active=3)

    assert wrote is True
    args = conn.execute.call_args[0]
    sql = args[0]
    assert "INSERT INTO mi_themes" in sql
    assert "ON CONFLICT (theme_date, name) DO UPDATE SET" in sql
    assert "WHERE mi_themes.source = 'shadow_promoted'" in sql
    # positional params: today, name, score, desc, tickers, days_active
    assert args[1:] == (_TODAY, "Rare & Orphan Biotech Re-Rating", 42.5, "fallback desc",
                         ["RARE", "MIRM"], 4)   # days_active = prior(3) + 1


@pytest.mark.asyncio
async def test_upsert_promoted_theme_no_prior_and_thesis_used():
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value="INSERT 0 1")

    await te._upsert_promoted_theme(
        conn, "New Theme", ["A"], "operator thesis", "fallback", _TODAY,
        rs_avg=None, prior_days_active=None)

    args = conn.execute.call_args[0]
    assert args[1:] == (_TODAY, "New Theme", None, "operator thesis", ["A"], 1)


@pytest.mark.asyncio
async def test_operator_and_nightly_paths_both_delegate_to_shared_helper(monkeypatch):
    """Same candidate through both public entry points → both must call the SAME shared helper
    with the SAME resolved (rs_avg, prior_days_active) — i.e. no re-diverged hand-copy."""
    from tests.conftest import make_mock_pool
    calls = []

    async def _spy(conn, name, tickers, thesis, desc_fallback, today, *, rs_avg, prior_days_active):
        calls.append((name, tuple(tickers), rs_avg, prior_days_active))
        return True

    monkeypatch.setattr(te, "_upsert_promoted_theme", _spy)
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())

    cand = _cand("Rare & Orphan Biotech Re-Rating", ["RARE", "MIRM", "RGNX", "AGIO"])

    # Operator path (/promotetheme)
    pool1, conn1 = make_mock_pool()
    conn1.fetch = AsyncMock(return_value=[
        {"ticker": "RARE", "rs_composite": 80.0}, {"ticker": "MIRM", "rs_composite": 60.0}])
    conn1.fetchrow = AsyncMock(return_value={"days_active": 2})
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool1))
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[cand]))
    await te.promote_candidate_by_name("rare orphan", _TODAY)

    # Nightly path (promote_shadow_themes) — same candidate, same RS rows, same prior days_active
    pool2, conn2 = make_mock_pool()
    conn2.fetch = AsyncMock(side_effect=[
        [{"name": "Rare & Orphan Biotech Re-Rating", "days_active": 2}],   # prior_rows batched query
        [{"ticker": "RARE", "rs_composite": 80.0}, {"ticker": "MIRM", "rs_composite": 60.0}],  # RS batched
    ])
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool2))
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[cand]))
    await te.promote_shadow_themes(_TODAY)

    assert len(calls) == 2
    op_call, nightly_call = calls
    assert op_call[0] == nightly_call[0] == "Rare & Orphan Biotech Re-Rating"
    assert op_call[2] == nightly_call[2] == 70.0   # rs_avg over RARE(80)+MIRM(60)
    assert op_call[3] == nightly_call[3] == 2      # prior_days_active


# ─── Option A (operator 2026-07-07) — graduation ping only on a genuine NEW crossing ───
# The nightly promote re-upserts every still-qualifying cohort, so the 🎓 confirm fired every
# run (the SAME theme re-"graduating" nightly — audit showed Autoimmune... on 6/30, 7/1, 7/2).
# These pin: a NEW crossing (no prior row) pings + NAMES the theme; a re-promotion (prior row
# exists) stays silent (the write still happens + is in the shadow_themes_promoted audit).

def _nightly_setup(monkeypatch, cand, prior_rows):
    """Wire promote_shadow_themes with a mock pool. conn.fetch is consumed in order:
    [1] the prior-days_active batched query, [2] the RS batched query (empty here)."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[prior_rows, []])   # prior rows, then RS rows (empty → rs_avg None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")    # _upsert_promoted_theme → wrote=True
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[cand]))
    from agents.market_intelligence import briefing as _brief
    tg = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tg)   # fn imports it at call-time
    return tg


@pytest.mark.asyncio
async def test_new_graduation_pings_and_names(monkeypatch):
    cand = _cand("Coal Mining & Exploration", ["A", "B", "C", "D"])
    tg = _nightly_setup(monkeypatch, cand, prior_rows=[])        # no prior row → genuine NEW crossing
    n = await te.promote_shadow_themes(_TODAY)
    assert n == 1
    tg.assert_awaited_once()
    msg = tg.await_args[0][0]
    assert "NEWLY graduated" in msg
    assert "Coal Mining & Exploration" in msg                    # NAMED, not a bare count


@pytest.mark.asyncio
async def test_repromotion_stays_silent(monkeypatch):
    cand = _cand("Coal Mining & Exploration", ["A", "B", "C", "D"])
    # prior row exists → re-promotion of an already-live cohort (the nightly-noise case)
    tg = _nightly_setup(monkeypatch, cand,
                        prior_rows=[{"name": "Coal Mining & Exploration", "days_active": 5}])
    n = await te.promote_shadow_themes(_TODAY)
    assert n == 1                     # the write STILL happens (theme stays live)
    tg.assert_not_awaited()           # …but NO Telegram — steady-state, audit-only
