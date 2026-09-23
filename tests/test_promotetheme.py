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


@pytest.fixture(autouse=True)
def _birth_gate_off(monkeypatch):
    """Phase-1 birth gate (2026-07-27): pin the 3-state 'theme_birth_gate' mode 'off' so
    these pre-gate promote pins exercise the byte-identical legacy path without
    a real DB read (fail-closed OFF is the production default)."""
    monkeypatch.setattr(te, "get_theme_birth_gate_mode", AsyncMock(return_value="off"))

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
        [],   # #530 prior_desc_rows (tombstone-skipping) — empty, no preservation exercised here
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

def _nightly_setup(monkeypatch, cand, prior_rows, prior_desc_rows=None):
    """Wire promote_shadow_themes with a mock pool. conn.fetch is consumed in order:
    [1] the prior-days_active batched query, [2] the #530 tombstone-skipping description
    lookup (empty by default — most callers don't exercise the preserve path), [3] the RS
    batched query (empty here)."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[prior_rows, prior_desc_rows or [], []])
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


# ─── #530 — shadow_v2 re-mint must not clobber a correct thesis with generic text ───
# Root cause (#491, the WULF/CORZ eviction on 2026-07-27): the shadow_v2 correlation lane
# re-generates a fresh LLM thesis every night regardless of whether the cohort changed, and
# `_upsert_promoted_theme`'s ON CONFLICT unconditionally wrote `description = EXCLUDED.description`
# with NO comparison to the description already on the board. F4 (#368) then judges membership
# against that thesis — a thesis overwritten with generic crypto-beta text actively evicts
# correct members (WULF/CORZ) from a theme whose OWN thesis named the AI conversion.
#
# Two `conn.fetch` calls now feed the decision: [1] `prior_rows` (name, days_active only —
# UNFILTERED, used for days_active continuity), [2] `prior_desc_rows` (description, tickers,
# theme_date, stage — filtered to `cardinality(tickers) > 0`, skips auto-retire tombstones).
# `_prior_days_active_row` / `_prior_desc_row` build each list's single dict for readability.

_SPECIFIC_THESIS = (
    "CIFR, CORZ, HUT, IREN, and WULF are Bitcoin miners converting mining facilities into "
    "AI/HPC data-center capacity — the conversion, not bitcoin price, is the driver."
)
_GENERIC_THESIS = (
    "CIFR, CORZ, HUT, IREN, and WULF are all pure-play Bitcoin mining operators showing "
    "high beta-adjusted correlation to bitcoin price levels."
)
_CRYPTO_COHORT = ["CIFR", "CORZ", "HUT", "IREN", "WULF"]
_THEME_NAME = "Bitcoin Mining & Crypto Infrastructure Operators"


def _prior_days_active_row(days_active=5):
    return [{"name": _THEME_NAME, "days_active": days_active}]


def _prior_desc_row(tickers, theme_date, stage="Fading", description=_SPECIFIC_THESIS):
    return [{"name": _THEME_NAME, "description": description, "tickers": tickers,
             "theme_date": theme_date, "stage": stage}]


def _run_530_promote(monkeypatch, prior_rows, prior_desc_rows, candidate_tickers=_CRYPTO_COHORT,
                      candidate_thesis=_GENERIC_THESIS):
    """Shared harness: wires promote_shadow_themes' THREE conn.fetch calls in order
    (prior_rows, prior_desc_rows, RS batched — empty) and returns conn for inspection."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[prior_rows, prior_desc_rows, []])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        _cand(_THEME_NAME, candidate_tickers, thesis=candidate_thesis, source="shadow_v2")]))
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    from agents.market_intelligence import briefing as _brief
    monkeypatch.setattr(_brief, "send_telegram_message", AsyncMock())
    return conn


@pytest.mark.asyncio
async def test_530_unchanged_cohort_preserves_specific_thesis_on_remint(monkeypatch):
    """The load-bearing case: shadow_v2 re-proposes the IDENTICAL ticker set tonight with a
    generic, re-generated thesis. Because membership did NOT change, the specific thesis
    already on the board must be preserved — not clobbered by tonight's fresh (and worse)
    correlation-lane text."""
    conn = _run_530_promote(
        monkeypatch, _prior_days_active_row(),
        _prior_desc_row(_CRYPTO_COHORT, _TODAY - _dt.timedelta(days=1)))
    await te.promote_shadow_themes(_TODAY)
    args = conn.execute.call_args[0]
    written_desc = args[4]   # (sql, today, name, score, desc, tickers, days_active)
    assert written_desc == _SPECIFIC_THESIS, (
        f"cohort unchanged — the specific thesis must survive the re-mint, got: {written_desc!r}"
    )


@pytest.mark.asyncio
async def test_530_tombstone_between_snapshots_still_preserves(monkeypatch):
    """Bug found on advisor review, fixed before ship: the MOST COMMON re-promote shape in
    prod is retire-by-absorption one day, re-promote the next — the IMMEDIATELY-prior row is
    an auto-retire tombstone (`stage='Retired', tickers=[]`, per `_synthetic_retired_row` /
    the engine-drop retire_rows). A naive "compare against the last row" lookup would see
    `set() != set(cohort)` and refuse to preserve on every such promote — the single most
    common shape, not an edge case. The fix looks past the tombstone to the last row that
    actually CARRIES the cohort."""
    conn = _run_530_promote(
        monkeypatch,
        _prior_days_active_row(),
        # prior_desc_rows already reflects what the DB query would return: DISTINCT ON (name)
        # ... AND cardinality(tickers) > 0 — the tombstone (empty tickers) is filtered OUT at
        # the SQL level, so the row that survives is the real cohort from 2 days back.
        _prior_desc_row(_CRYPTO_COHORT, _TODAY - _dt.timedelta(days=2)))
    await te.promote_shadow_themes(_TODAY)
    args = conn.execute.call_args[0]
    assert args[4] == _SPECIFIC_THESIS, (
        f"a tombstone sitting between two live snapshots must not defeat preservation, "
        f"got: {args[4]!r}"
    )


@pytest.mark.asyncio
async def test_530_prior_desc_lookup_sql_filters_empty_tickers(monkeypatch):
    """Pins the load-bearing HALF of the tombstone-skip fix that the scenario tests above
    can't see on their own: they hand the resolver a pre-filtered `prior_desc_rows` list
    (`_prior_desc_row(...)`), so they would keep passing even if a future edit dropped the
    `cardinality(tickers) > 0` clause from the REAL query — this pins the query text itself,
    the nightly path's second `conn.fetch` call."""
    conn = _run_530_promote(monkeypatch, _prior_days_active_row(), [])
    await te.promote_shadow_themes(_TODAY)
    prior_desc_sql = conn.fetch.await_args_list[1].args[0]
    assert "cardinality(tickers) > 0" in prior_desc_sql
    assert "theme_date, stage" in prior_desc_sql


@pytest.mark.asyncio
async def test_530_operator_path_prior_desc_lookup_sql_filters_empty_tickers(monkeypatch):
    """Same SQL-text pin as above, for the operator `/promotetheme` path's `conn.fetchrow`
    calls — [1] the unfiltered days_active lookup, [2] the tombstone-skipping description
    lookup."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        _cand(_THEME_NAME, _CRYPTO_COHORT, thesis=_GENERIC_THESIS, source="shadow_v2")]))
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())

    await te.promote_candidate_by_name(_THEME_NAME, _TODAY)

    prior_desc_sql = conn.fetchrow.await_args_list[1].args[0]
    assert "cardinality(tickers) > 0" in prior_desc_sql
    assert "theme_date, stage" in prior_desc_sql


@pytest.mark.asyncio
async def test_530_changed_cohort_allows_thesis_refresh(monkeypatch):
    """Edge case: the ticker set DID change (WULF joins tonight). That is real membership
    evidence, so the fresh thesis is allowed through — the theme should describe what it
    currently holds, not a stale membership."""
    prior_cohort = ["CIFR", "CORZ", "HUT", "IREN"]   # WULF not yet a member
    conn = _run_530_promote(
        monkeypatch, _prior_days_active_row(),
        _prior_desc_row(prior_cohort, _TODAY - _dt.timedelta(days=1)))
    await te.promote_shadow_themes(_TODAY)
    args = conn.execute.call_args[0]
    written_desc = args[4]
    assert written_desc == _GENERIC_THESIS, (
        f"cohort membership changed — the refreshed thesis should be written, got: {written_desc!r}"
    )


@pytest.mark.asyncio
async def test_530_no_prior_row_uses_candidate_thesis(monkeypatch):
    """Edge case: a genuinely NEW crossing (no prior mi_themes row at all) — nothing to
    preserve, so the candidate's own thesis is used exactly as before (unaffected by the fix)."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[], [], []])   # no prior row, no prior desc, no RS rows
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        _cand("Brand New Cohort", ["A", "B", "C"], thesis="fresh thesis", source="shadow_v2")]))
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    from agents.market_intelligence import briefing as _brief
    monkeypatch.setattr(_brief, "send_telegram_message", AsyncMock())

    await te.promote_shadow_themes(_TODAY)

    args = conn.execute.call_args[0]
    assert args[4] == "fresh thesis"


@pytest.mark.asyncio
async def test_530_retired_prior_never_preserved(monkeypatch):
    """Edge case (advisor review): a prior row can carry a matching ticker set on a RETIRED
    row (not every retirement path zeroes `tickers` — a pre-convention legacy row could) —
    preserving would resurrect a dead lineage's stale text under a fresh live promote, so a
    Retired prior is never preserved even though it passed the ticker-bearing filter."""
    conn = _run_530_promote(
        monkeypatch, _prior_days_active_row(),
        _prior_desc_row(_CRYPTO_COHORT, _TODAY - _dt.timedelta(days=1), stage="Retired"))
    await te.promote_shadow_themes(_TODAY)
    args = conn.execute.call_args[0]
    assert args[4] == _GENERIC_THESIS


@pytest.mark.asyncio
async def test_530_stale_prior_beyond_14d_never_preserved(monkeypatch):
    """Edge case (advisor review): mirrors `_canonicalize_theme_names`'s own 14-day window —
    an unchanged ticker set whose last row is OLDER than 14 days is not preserved (the same
    number this file's #59 precedent already uses for the analogous name-freeze decision)."""
    conn = _run_530_promote(
        monkeypatch, _prior_days_active_row(),
        _prior_desc_row(_CRYPTO_COHORT, _TODAY - _dt.timedelta(days=15), stage="Fading"))
    await te.promote_shadow_themes(_TODAY)
    args = conn.execute.call_args[0]
    assert args[4] == _GENERIC_THESIS


@pytest.mark.asyncio
async def test_530_prior_within_14d_and_not_retired_preserved(monkeypatch):
    """Positive control for the two new guards: a prior row that IS within 14 days and IS
    NOT Retired still preserves — the guards narrow the fix, they don't disable it."""
    conn = _run_530_promote(
        monkeypatch, _prior_days_active_row(),
        _prior_desc_row(_CRYPTO_COHORT, _TODAY - _dt.timedelta(days=14), stage="Fading"))
    await te.promote_shadow_themes(_TODAY)
    args = conn.execute.call_args[0]
    assert args[4] == _SPECIFIC_THESIS

