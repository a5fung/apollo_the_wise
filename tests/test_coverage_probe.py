"""S2/S3 coverage probe (EP↔theme coverage loop, design 2026-07-13) — tests.

Three groups:
  1. THE CARVE-OUT PINS (the safety boundary): source='coverage_probe' cohorts must NEVER
     be selected by the nightly auto-promote — neither by the reader
     (get_shadow_theme_candidates default) nor by the promote path itself even if the
     reader leaks (defense in depth). Operator surfaces (/themes, /promotetheme) opt in
     explicitly. Without this wall an un-vetted probe cohort would auto-promote into live
     mi_themes → live judge context/R4 → live grade (THE LINE).
  2. Pure probe logic (F-D market adjustment, cohort overlap, families-agree bar,
     stub naming, tag parsing).
  3. The probe writer/feed wiring (mocked conn): themeless-only, unconfirmed rows still
     logged, confirmed cohorts fed source-scoped, judge fire_axes stored as a read-only
     calibration column, and the job NEVER raises into the EOD chain.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence import coverage_probe as cp
from agents.market_intelligence import db as dbmod
from agents.market_intelligence import theme_engine as te

_TODAY = _dt.date(2026, 7, 13)
_PRIOR = _dt.date(2026, 7, 10)


def _run(coro):
    return asyncio.run(coro)


# ════════════════════════════════════════════════════════════════════════════════════
# 1. THE CARVE-OUT PINS — coverage_probe is surface-only, never auto-promoted
# ════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_auto_promote_reader_excludes_coverage_probe_by_default(monkeypatch):
    """PIN wall 1: the auto-promote reader (get_shadow_theme_candidates, default args —
    exactly how promote_shadow_themes calls it) must exclude source='coverage_probe'.
    The operator opt-in (include_probe=True) lifts the filter."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))

    await dbmod.get_shadow_theme_candidates(days=7)
    default_sql = conn.fetch.await_args.args[0]
    default_args = conn.fetch.await_args.args[1:]
    # #469 allowlist inversion: the default filter is source = ANY(<allowlist>) —
    # coverage_probe (and ANY unknown future source) is out because it is not IN,
    # not because someone remembered to name it (THE LINE).
    assert "source = ANY" in default_sql, (
        "the auto-promote reader lost its source allowlist — an un-vetted "
        "cohort could auto-promote into live mi_themes (THE LINE)")
    allow = [a for a in default_args if isinstance(a, list)][0]
    assert "coverage_probe" not in allow
    assert set(allow) == dbmod.AUTO_PROMOTE_THEME_SOURCES

    await dbmod.get_shadow_theme_candidates(days=7, include_probe=True)
    # Single parameterized query (review 7/17): include_probe=True is passed as
    # the $2 boolean that short-circuits the allowlist filter — operator
    # surfaces see EVERY source.
    operator_args = conn.fetch.await_args.args
    assert "($2::boolean OR source = ANY($3::text[]))" in operator_args[0]
    assert operator_args[2] is True                 # the filter is bypassed


@pytest.mark.asyncio
async def test_promote_shadow_themes_never_promotes_coverage_probe(monkeypatch):
    """PIN wall 2 (defense in depth): even if the READER someday leaks probe rows (its
    default flips, a new call site passes include_probe=True by mistake), the nightly
    promote path itself must drop source='coverage_probe' — zero mi_themes writes."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[], []])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    from agents.market_intelligence import briefing as _brief
    monkeypatch.setattr(_brief, "send_telegram_message", AsyncMock())
    # Simulate the reader LEAK: it returns a >=3-member probe cohort anyway.
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        {"name": "Probe: Robotics 2026-07-10", "tickers": ["A", "B", "C", "D"],
         "thesis": "t", "source": "coverage_probe"},
    ]))

    n = await te.promote_shadow_themes(_TODAY)

    assert n == 0
    conn.execute.assert_not_awaited()   # NO mi_themes write of any kind


@pytest.mark.asyncio
async def test_promote_drops_probe_but_keeps_legit_cohorts(monkeypatch):
    """Mixed feed: the probe cohort is dropped, a legitimate lane's cohort still
    promotes — the carve-out is surgical, not a promote-lane shutdown."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[], []])   # prior rows, RS rows
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    from agents.market_intelligence import briefing as _brief
    monkeypatch.setattr(_brief, "send_telegram_message", AsyncMock())
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        {"name": "Probe: Robotics 2026-07-10", "tickers": ["A", "B", "C", "D"],
         "thesis": "t", "source": "coverage_probe"},
        {"name": "Quantum Networking", "tickers": ["QX", "QY", "QZ"],
         "thesis": "t", "source": "rs_slope_synthesis"},
    ]))

    n = await te.promote_shadow_themes(_TODAY)

    assert n == 1
    written_names = [
        c.args[2] for c in conn.execute.await_args_list
        if "INSERT INTO mi_themes" in c.args[0]
    ]
    assert written_names == ["Quantum Networking"]
    assert "Probe: Robotics 2026-07-10" not in written_names


@pytest.mark.asyncio
async def test_operator_promotetheme_reads_probe_and_can_promote_it(monkeypatch):
    """The operator one-tap (/promotetheme → promote_candidate_by_name) is the ONLY
    sanctioned graduation path for probe cohorts: it reads with include_probe=True and a
    probe cohort promotes through it exactly like any other candidate."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    reader = AsyncMock(return_value=[
        {"name": "Probe: Robotics 2026-07-10", "tickers": ["A", "B", "C"],
         "thesis": "t", "source": "coverage_probe"},
    ])
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", reader)
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())

    res = await te.promote_candidate_by_name("probe robotics", _TODAY)

    assert reader.await_args.kwargs.get("include_probe") is True
    assert res["status"] == "promoted"
    assert res["n_members"] == 3


@pytest.mark.asyncio
async def test_probe_candidate_writer_is_source_scoped():
    """The S3 feed writer: writes ONLY mi_theme_candidates_shadow, stamps
    source='coverage_probe', and its ON CONFLICT is guarded so it can never hijack a
    same-named cohort from another lane."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()

    await dbmod.upsert_coverage_probe_candidate(
        conn, _TODAY, "Probe: Robotics 2026-07-10", ["A", "B"], "thesis")

    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO mi_theme_candidates_shadow" in sql
    assert "'coverage_probe'" in sql
    assert "WHERE mi_theme_candidates_shadow.source = 'coverage_probe'" in sql
    assert "mi_themes" not in sql   # never the live table


# ════════════════════════════════════════════════════════════════════════════════════
# 2. Pure probe logic
# ════════════════════════════════════════════════════════════════════════════════════

def test_market_adjust_subtracts_spy():
    """Fork F-D: every leg is adjusted by SPY's same-day move before the co-movement
    floor — the everything-rallies confound is removed."""
    adj = cp.market_adjust_moves({"A": 5.0, "B": 2.0}, spy_move=1.5)
    assert adj == {"A": 3.5, "B": 0.5}


def test_market_adjust_missing_spy_passes_raw_through():
    """No SPY row → raw moves pass through unchanged (degraded-but-honest; the probe row
    records p3_spy_move NULL so the health read can tell)."""
    moves = {"A": 5.0, "B": 2.0}
    assert cp.market_adjust_moves(moves, spy_move=None) == moves


def test_cohort_overlap_intersection_over_smaller():
    assert cp.cohort_overlap({"A", "B"}, {"A", "B"}) == 1.0
    assert cp.cohort_overlap({"A", "B", "C", "D"}, {"A", "B"}) == 1.0   # core preserved
    assert cp.cohort_overlap({"A", "B"}, {"C", "D"}) == 0.0
    assert cp.cohort_overlap({"A", "B"}, {"B", "C"}) == 0.5
    assert cp.cohort_overlap(set(), {"A"}) == 0.0


def test_families_agree_requires_p1_and_measured_co_movement():
    """§3.3 bar 1: >=1 P1 structural hit AND P3 co_moving is True. P2 co-gap alone never
    confirms (it can't set either family), and a None co_moving (not computable) is NOT
    agreement — unknown never confirms."""
    assert cp._families_agree(1, True) is True
    assert cp._families_agree(0, True) is False    # tape alone never confirms
    assert cp._families_agree(2, False) is False   # structure without tape
    assert cp._families_agree(2, None) is False    # unknown tape ≠ agreement


def test_matched_name_tickers_parses_tags():
    assert cp.matched_name_tickers(
        ["name:FRND:friendco", "name:OTHR:other systems"]) == {"FRND", "OTHR"}
    assert cp.matched_name_tickers([]) == set()
    assert cp.matched_name_tickers(["kw:lithium"]) == set()   # non-name tags ignored


def test_build_stub_name_deterministic_and_falls_back():
    assert cp.build_stub_name("Semiconductors", _PRIOR) == "Probe: Semiconductors 2026-07-10"
    assert cp.build_stub_name(None, _PRIOR) == "Probe: Uncovered 2026-07-10"
    assert cp.build_stub_name("  ", _PRIOR) == "Probe: Uncovered 2026-07-10"
    # deterministic — same inputs, same name (no randomness, no LLM)
    assert cp.build_stub_name("X", _PRIOR) == cp.build_stub_name("X", _PRIOR)


# ════════════════════════════════════════════════════════════════════════════════════
# 3. Probe wiring (mocked conn) — themeless-only, evidence rows, S3 feed, never-raises
# ════════════════════════════════════════════════════════════════════════════════════

def _patch_probe_deps(monkeypatch, *, heat=None, industry_peers=None, names=None,
                      warm_names=None, sectors=None, moves=None):
    monkeypatch.setattr(cp, "get_theme_heat_asof", AsyncMock(return_value=heat))
    monkeypatch.setattr(cp, "get_industry_peers",
                        AsyncMock(return_value=industry_peers or []))
    monkeypatch.setattr(cp, "get_company_names_batch",
                        AsyncMock(return_value=dict(names or {})))
    monkeypatch.setattr(cp, "_ensure_company_names",
                        AsyncMock(return_value=dict(warm_names or {})))
    monkeypatch.setattr(cp, "get_sectors_batch",
                        AsyncMock(return_value=dict(sectors or {})))
    monkeypatch.setattr(cp, "get_daily_moves", AsyncMock(return_value=dict(moves or {})))
    writer = AsyncMock()
    monkeypatch.setattr(cp, "upsert_coverage_probe_row", writer)
    return writer


def _alert(ticker="TICK", tier="MODERATE", text=None, fire_axes=None):
    return {"ticker": ticker, "alert_date": _TODAY, "score_tier": tier,
            "grounded_text": text, "fire_axes": fire_axes}


@pytest.mark.asyncio
async def test_probe_skips_theme_tracked_subject(monkeypatch):
    """A subject with a 7d-bounded as-of theme hit is NOT a blind spot — no probe row."""
    writer = _patch_probe_deps(monkeypatch, heat={"name": "Robotics", "stage": "Nascent",
                                                  "score": 10.0, "tickers": ["TICK"],
                                                  "description": ""})
    row = await cp._probe_one_alert(
        None, _alert(), day_alert_tickers={"TICK"}, peer_universe=set(),
        cooldown_tickers=set(), prior_cohorts=[])
    assert row is None
    writer.assert_not_awaited()
    # and the themeless test used the 7d-bounded variant (design C2)
    assert cp.get_theme_heat_asof.await_args.kwargs.get("recency_days") == 7


@pytest.mark.asyncio
async def test_probe_unconfirmed_row_still_logged(monkeypatch):
    """Below-bar evidence still accrues: P1 hit but cohort NOT co-moving → row written,
    families_agree False, confirmed False; judge fire_axes stored verbatim as the
    read-only calibration column."""
    writer = _patch_probe_deps(
        monkeypatch,
        names={"FRND": "Friendco Corporation"},
        moves={"TICK": 6.0, "FRND": -4.0, "SPY": 0.5},   # opposite sign → not co-moving
    )
    row = await cp._probe_one_alert(
        None, _alert(text="TICK signed a pact with Friendco Corporation.",
                     fire_axes=["theme"]),
        day_alert_tickers={"TICK"}, peer_universe={"FRND"},
        cooldown_tickers=set(), prior_cohorts=[])

    writer.assert_awaited_once()
    persisted = writer.await_args.args[1]
    assert persisted["p1_name_score"] == 1
    assert persisted["p1_matched_names"] == ["name:FRND:friendco"]
    assert persisted["p3_co_moving"] is False
    assert persisted["families_agree"] is False
    assert persisted["confirmed"] is False
    assert persisted["judge_fire_axes"] == ["theme"]   # calibration only — stored, unused
    assert "anchor_date" not in persisted              # internal field never persisted
    assert row["confirmed"] is False


@pytest.mark.asyncio
async def test_probe_confirmed_needs_persistence(monkeypatch):
    """Families agree on day 1 (P1 + market-adjusted co-movement) but NO overlapping
    prior cohort → persistence_met False → unconfirmed (one-day wonders die here)."""
    writer = _patch_probe_deps(
        monkeypatch,
        names={"FRND": "Friendco Corporation"},
        moves={"TICK": 6.0, "FRND": 4.0, "SPY": 1.0},   # adj: TICK 5.0, FRND 3.0 → co-move
    )
    await cp._probe_one_alert(
        None, _alert(text="TICK signed a pact with Friendco Corporation."),
        day_alert_tickers={"TICK"}, peer_universe={"FRND"},
        cooldown_tickers=set(), prior_cohorts=[])
    persisted = writer.await_args.args[1]
    assert persisted["families_agree"] is True
    assert persisted["persistence_met"] is False
    assert persisted["confirmed"] is False
    assert persisted["p3_spy_move"] == 1.0             # F-D leg recorded


@pytest.mark.asyncio
async def test_probe_confirms_with_overlapping_prior_cohort(monkeypatch):
    """The full §3.3 bar: P1 hit + adjusted co-movement + an overlapping families-agree
    cohort on a prior day → confirmed; anchor date = the earliest prior day."""
    writer = _patch_probe_deps(
        monkeypatch,
        names={"FRND": "Friendco Corporation"},
        moves={"TICK": 6.0, "FRND": 4.0, "SPY": 1.0},
    )
    prior = [{"ticker": "FRND", "alert_date": _PRIOR, "cohort_tickers": ["FRND", "TICK"]}]
    row = await cp._probe_one_alert(
        None, _alert(text="TICK signed a pact with Friendco Corporation."),
        day_alert_tickers={"TICK"}, peer_universe={"FRND"},
        cooldown_tickers=set(), prior_cohorts=prior)

    persisted = writer.await_args.args[1]
    assert persisted["families_agree"] is True
    assert persisted["persistence_met"] is True
    assert persisted["confirmed"] is True
    assert set(persisted["cohort_tickers"]) == {"TICK", "FRND"}
    assert row["anchor_date"] == _PRIOR


@pytest.mark.asyncio
async def test_probe_cooldown_tickers_dropped_from_cohort(monkeypatch):
    """§3.3 bar 3: an active validation-cooldown ticker is dropped from the evidence
    cohort (recorded in excluded_tickers) — a solo subject can't confirm."""
    writer = _patch_probe_deps(
        monkeypatch,
        names={"FRND": "Friendco Corporation"},
        moves={"TICK": 6.0, "FRND": 4.0, "SPY": 1.0},
    )
    prior = [{"ticker": "FRND", "alert_date": _PRIOR, "cohort_tickers": ["FRND", "TICK"]}]
    await cp._probe_one_alert(
        None, _alert(text="TICK signed a pact with Friendco Corporation."),
        day_alert_tickers={"TICK"}, peer_universe={"FRND"},
        cooldown_tickers={"FRND"}, prior_cohorts=prior)
    persisted = writer.await_args.args[1]
    assert persisted["excluded_tickers"] == ["FRND"]
    assert persisted["cohort_tickers"] == ["TICK"]
    assert persisted["confirmed"] is False   # < MIN_COHORT_MEMBERS after exclusion


@pytest.mark.asyncio
async def test_feed_confirmed_cohort_writes_source_scoped_candidate(monkeypatch):
    """S3 feed: a confirmed cohort upserts ONE mi_theme_candidates_shadow row through the
    source-scoped writer with the deterministic stub name (dominant industry + anchor)."""
    monkeypatch.setattr(cp, "get_industries_for_tickers",
                        AsyncMock(return_value={"TICK": "Robotics", "FRND": "Robotics"}))
    monkeypatch.setattr(cp, "get_theme_excluded_tickers", AsyncMock(return_value=set()))
    feed = AsyncMock()
    monkeypatch.setattr(cp, "upsert_coverage_probe_candidate", feed)
    monkeypatch.setattr(cp, "log_audit_event", AsyncMock())

    row = {"ticker": "TICK", "alert_date": _TODAY, "cohort_tickers": ["FRND", "TICK"],
           "p1_name_score": 1, "anchor_date": _PRIOR}
    name = await cp._feed_confirmed_cohort(None, row)

    assert name == "Probe: Robotics 2026-07-10"
    feed.assert_awaited_once()
    args = feed.await_args.args
    assert args[1] == _TODAY                       # run_date
    assert args[2] == "Probe: Robotics 2026-07-10"
    assert args[3] == ["FRND", "TICK"]             # members


@pytest.mark.asyncio
async def test_feed_respects_theme_exclusions(monkeypatch):
    """mi_theme_exclusions pairs are honored at the S3 write; a cohort shrunk below the
    member floor writes nothing."""
    monkeypatch.setattr(cp, "get_industries_for_tickers",
                        AsyncMock(return_value={"TICK": "Robotics"}))
    monkeypatch.setattr(cp, "get_theme_excluded_tickers",
                        AsyncMock(return_value={"FRND"}))
    feed = AsyncMock()
    monkeypatch.setattr(cp, "upsert_coverage_probe_candidate", feed)
    monkeypatch.setattr(cp, "log_audit_event", AsyncMock())

    row = {"ticker": "TICK", "alert_date": _TODAY, "cohort_tickers": ["FRND", "TICK"],
           "p1_name_score": 1, "anchor_date": _PRIOR}
    name = await cp._feed_confirmed_cohort(None, row)

    assert name is None
    feed.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_coverage_probe_never_raises_into_eod_chain(monkeypatch):
    """SHADOW contract: any failure is swallowed to the coverage_probe_error audit event
    (ends in _error → caught by the nightly %error% sweep, not silent) and a summary dict
    — the EOD chain never sees an exception."""
    monkeypatch.setattr(cp, "get_today_ep_alerts",
                        AsyncMock(side_effect=RuntimeError("db down")))
    audit = AsyncMock()
    monkeypatch.setattr(cp, "log_audit_event", audit)

    out = await cp.run_coverage_probe(_TODAY)   # must not raise

    assert out["error"] is not None
    assert any(c.args[0] == "coverage_probe_error" for c in audit.await_args_list)


@pytest.mark.asyncio
async def test_promote_wall_excludes_UNKNOWN_sources_by_default(monkeypatch):
    """#469 allowlist inversion — THE class-kill pin: a source that did not exist
    when the wall was written (the next coverage_probe) must be dropped by the
    promote path's re-filter without anyone remembering to denylist it."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[], []])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    from agents.market_intelligence import briefing as _brief
    monkeypatch.setattr(_brief, "send_telegram_message", AsyncMock())
    # Simulate a reader leak of a BRAND-NEW experimental source.
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        {"name": "Experimental: axis-shadow X", "tickers": ["A", "B", "C", "D"],
         "thesis": "t", "source": "axis_shadow_x_2027"},
    ]))

    n = await te.promote_shadow_themes(_TODAY)

    assert n == 0
    conn.execute.assert_not_called()   # zero mi_themes writes


def test_allowlist_is_exactly_the_three_vetted_lanes():
    """Additions to the auto-promote allowlist are DELIBERATE (operator-signed) —
    this pin forces the diff to show up here, not just in db.py."""
    assert dbmod.AUTO_PROMOTE_THEME_SOURCES == {
        "shadow_v2", "narrative_cogap", "rs_slope_synthesis"}
