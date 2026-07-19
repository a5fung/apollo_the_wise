"""#322 judge -> narrative-radar feed — tests.

Four groups (mirrors test_coverage_probe.py's shape, the sibling shadow lane):
  1. Pure predicate/formatting logic (is_theme_gap, build_gap_name, build_gap_thesis).
  2. The feed wiring (mocked conn/db calls): fires only on a real gap, no-ops otherwise,
     writes source='judge_inferred', never raises.
  3. THE ANTI-CIRCULARITY PINS (the safety boundary): 'judge_inferred' must NEVER be
     auto-promoted into live mi_themes, and must NEVER re-enter the judge's own
     active_narratives input (get_narrative_theme_candidates) — a judge inference must
     never become the judge's own future corroborating evidence.
  4. The PROACTIVE /themes board section (verify-operator-facing-surface: correct DB
     rows are not a surface) — a separate DISPLAY-only read, so it must never touch
     the anti-circularity wall in group 3.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence import db as dbmod
from agents.market_intelligence import judge_theme_gap as jtg
from agents.market_intelligence import theme_engine as te

_ALERT_DATE = _dt.date(2026, 6, 17)


def _run(coro):
    return asyncio.run(coro)


# ════════════════════════════════════════════════════════════════════════════════════
# 1. Pure predicate / formatting logic
# ════════════════════════════════════════════════════════════════════════════════════

def test_is_theme_gap_true_when_theme_fires_and_neither_lane_tracks():
    assert jtg.is_theme_gap(["theme"], False, False) is True
    assert jtg.is_theme_gap(["narrative"], False, False) is True
    assert jtg.is_theme_gap(["catalyst", "theme"], False, False) is True


def test_is_theme_gap_false_on_missing_or_empty_fire_axes():
    # None = judge omitted it / fail-open — never a "gap", only an explicit fire is.
    assert jtg.is_theme_gap(None, False, False) is False
    assert jtg.is_theme_gap([], False, False) is False


def test_is_theme_gap_false_when_only_catalyst_axis_lit():
    assert jtg.is_theme_gap(["catalyst"], False, False) is False


def test_is_theme_gap_false_when_lane1_already_tracks_it():
    # Already-tracked = a credit question (#328/#329), not a detection gap.
    assert jtg.is_theme_gap(["theme"], True, False) is False


def test_is_theme_gap_false_when_lane2_already_tracks_it():
    assert jtg.is_theme_gap(["narrative"], False, True) is False


def test_build_gap_name_uses_sector_and_date():
    assert jtg.build_gap_name("Technology", _ALERT_DATE) == "Judge: Technology 2026-06-17"


def test_build_gap_name_falls_back_to_uncovered():
    assert jtg.build_gap_name(None, _ALERT_DATE) == "Judge: Uncovered 2026-06-17"
    assert jtg.build_gap_name("   ", _ALERT_DATE) == "Judge: Uncovered 2026-06-17"


def test_build_gap_name_truncates_to_80_chars():
    name = jtg.build_gap_name("X" * 200, _ALERT_DATE)
    assert len(name) <= 80


def test_build_gap_name_same_sector_same_day_collapses_to_same_name():
    # The merge mechanism: two different tickers, same sector+day -> identical name
    # -> the DB upsert's ticker-set union naturally merges them into one cohort.
    n1 = jtg.build_gap_name("Industrials", _ALERT_DATE)
    n2 = jtg.build_gap_name("Industrials", _ALERT_DATE)
    assert n1 == n2


def test_build_gap_thesis_preserves_rationale_verbatim():
    thesis = jtg.build_gap_thesis("JBL", "Riding the AI-infra buildout narrative.")
    assert "JBL" in thesis
    assert "AI-infra buildout" in thesis


def test_build_gap_thesis_handles_missing_rationale():
    thesis = jtg.build_gap_thesis("JBL", None)
    assert "no rationale recorded" in thesis


def test_build_gap_thesis_truncates_to_400_chars():
    thesis = jtg.build_gap_thesis("JBL", "A" * 1000)
    assert len(thesis) <= 400


# ════════════════════════════════════════════════════════════════════════════════════
# 2. The feed wiring (mocked db calls)
# ════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_feed_writes_candidate_on_a_real_gap(monkeypatch):
    upsert = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(jtg, "upsert_judge_theme_gap_candidate", upsert)
    monkeypatch.setattr(jtg, "log_audit_event", audit)

    name = await jtg.feed_judge_theme_gap(
        conn=object(), ticker="jbl", alert_date=_ALERT_DATE,
        sector="Technology", fire_axes=["theme"],
        in_active_theme=False, in_narrative_cohort=False,
        rationale="Riding the AI-infra buildout.",
    )

    assert name == "Judge: Technology 2026-06-17"
    upsert.assert_awaited_once()
    args = upsert.await_args.args
    assert args[1] == _ALERT_DATE
    assert args[2] == "Judge: Technology 2026-06-17"
    assert args[3] == ["JBL"]  # upper-cased
    assert "AI-infra buildout" in args[4]
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "judge_theme_gap_candidate_written"


@pytest.mark.asyncio
async def test_feed_noop_when_not_a_gap(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr(jtg, "upsert_judge_theme_gap_candidate", upsert)
    monkeypatch.setattr(jtg, "log_audit_event", AsyncMock())

    # Already tracked by Lane 1 -> not a gap.
    name = await jtg.feed_judge_theme_gap(
        conn=object(), ticker="JBL", alert_date=_ALERT_DATE,
        sector="Technology", fire_axes=["theme"],
        in_active_theme=True, in_narrative_cohort=False,
        rationale="x",
    )
    assert name is None
    upsert.assert_not_called()


@pytest.mark.asyncio
async def test_feed_noop_on_missing_ticker_or_date(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr(jtg, "upsert_judge_theme_gap_candidate", upsert)
    monkeypatch.setattr(jtg, "log_audit_event", AsyncMock())

    assert await jtg.feed_judge_theme_gap(
        conn=object(), ticker=None, alert_date=_ALERT_DATE,
        sector="Technology", fire_axes=["theme"],
        in_active_theme=False, in_narrative_cohort=False, rationale="x",
    ) is None
    assert await jtg.feed_judge_theme_gap(
        conn=object(), ticker="JBL", alert_date=None,
        sector="Technology", fire_axes=["theme"],
        in_active_theme=False, in_narrative_cohort=False, rationale="x",
    ) is None
    upsert.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_judge_theme_gap_candidate_writes_source_scoped_sql(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value="INSERT 0 1")

    await dbmod.upsert_judge_theme_gap_candidate(
        conn, _ALERT_DATE, "Judge: Technology 2026-06-17", ["JBL"], "thesis text",
    )

    conn.execute.assert_awaited_once()
    sql = conn.execute.await_args.args[0]
    params = conn.execute.await_args.args[1:]
    # source is parameterized ($5) via the shared _upsert_theme_candidate_shadow helper; the
    # anti-hijack guard scopes ON CONFLICT to this lane's source, stamped as the last param.
    assert "WHERE mi_theme_candidates_shadow.source = $5" in sql
    assert params == (_ALERT_DATE, "Judge: Technology 2026-06-17", "thesis text", ["JBL"],
                      "judge_inferred")


# ════════════════════════════════════════════════════════════════════════════════════
# 3. THE ANTI-CIRCULARITY PINS
# ════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_judge_active_narratives_feed_excludes_judge_inferred(monkeypatch):
    """get_narrative_theme_candidates feeds the judge's OWN active_narratives input
    (ep_grade_judge.assemble_judge_inputs) — a judge-sourced candidate must NEVER
    re-enter as a future call's corroborating evidence."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))

    await dbmod.get_narrative_theme_candidates(days=5)
    sql = conn.fetch.await_args.args[0]
    assert "judge_inferred" not in sql
    assert "narrative_cogap" in sql and "rs_slope_synthesis" in sql


def test_auto_promote_sources_excludes_judge_inferred():
    """Additions to the auto-promote allowlist are DELIBERATE (operator-signed) —
    'judge_inferred' (an un-vetted, zero-confirmation-bar judge inference) must never
    silently join it."""
    assert "judge_inferred" not in dbmod.AUTO_PROMOTE_THEME_SOURCES
    assert dbmod.AUTO_PROMOTE_THEME_SOURCES == {
        "shadow_v2", "narrative_cogap", "rs_slope_synthesis"}


@pytest.mark.asyncio
async def test_auto_promote_reader_excludes_judge_inferred_by_default(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))

    await dbmod.get_shadow_theme_candidates(days=7)
    args = conn.fetch.await_args.args
    allow = [a for a in args if isinstance(a, list)][0]
    assert "judge_inferred" not in allow

    await dbmod.get_shadow_theme_candidates(days=7, include_probe=True)
    operator_args = conn.fetch.await_args.args
    assert operator_args[2] is True   # include_probe bypasses the allowlist filter


@pytest.mark.asyncio
async def test_promote_shadow_themes_never_promotes_judge_inferred(monkeypatch):
    """Defense in depth (mirrors test_coverage_probe's wall-2 pin): even if the READER
    leaked judge_inferred rows, the promote path's own re-filter must drop them —
    zero mi_themes writes from an un-vetted judge inference."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[], []])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    from agents.market_intelligence import briefing as _brief
    monkeypatch.setattr(_brief, "send_telegram_message", AsyncMock())
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        {"name": "Judge: Technology 2026-06-17", "tickers": ["JBL", "AAA", "BBB"],
         "thesis": "t", "source": "judge_inferred"},
    ]))

    n = await te.promote_shadow_themes(_ALERT_DATE)

    assert n == 0
    conn.execute.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════════════
# 4. The PROACTIVE /themes board section (display-only; must not touch the wall)
# ════════════════════════════════════════════════════════════════════════════════════

def _make_agent():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentName
    with patch("agents.base.get_secrets"), patch("shared.audit.log_action"):
        agent = MarketIntelligenceAgent.__new__(MarketIntelligenceAgent)
        agent.agent_name = AgentName.MARKET_INTELLIGENCE
    return agent


def _themes_board_patches(shadow_candidates):
    """The standard set of /themes board dependencies, held constant except for
    `get_shadow_theme_candidates` (the one this test group varies)."""
    themes = [{"name": "Solo Theme", "stage": "Nascent", "tickers": ["AAA"],
               "theme_date": "2026-06-17"}]
    rs = {"AAA": {"rs_composite": 70.0, "rs_1m": 70.0, "rs_3m": 70.0, "rs_6m": 70.0}}
    return [
        patch("agents.market_intelligence.agent.get_today_themes",
              new=AsyncMock(return_value=themes)),
        patch("agents.market_intelligence.agent.get_rs_for_tickers",
              new=AsyncMock(return_value=rs)),
        patch("agents.market_intelligence.agent.get_prior_theme_scores",
              new=AsyncMock(return_value={})),
        patch("agents.market_intelligence.agent.get_current_regime",
              new=AsyncMock(return_value=None)),
        patch("agents.market_intelligence.theme_ecosystems.load_ecosystem_assignments",
              new=AsyncMock(return_value={})),
        patch("agents.market_intelligence.theme_engine.evaluate_narrative_themes",
              new=AsyncMock(return_value=[])),
        patch.object(dbmod, "get_shadow_theme_candidates", shadow_candidates),
    ]


@pytest.mark.asyncio
async def test_themes_board_renders_judge_inferred_section():
    """The PROACTIVE board (not just the reactive /themes <name> lookup) surfaces a
    single-member judge_inferred candidate, tagged with its distance from the 3-member
    /promotetheme bar — verify-operator-facing-surface, not just a correct DB row."""
    from shared.models import AgentRequest

    reader = AsyncMock(return_value=[
        {"name": "Judge: Technology 2026-06-17", "tickers": ["JBL"],
         "thesis": "Judge-inferred theme gap (JBL): AI-infra.", "source": "judge_inferred"},
        {"name": "Some other cohort", "tickers": ["X", "Y", "Z"],
         "thesis": "t", "source": "narrative_cogap"},
    ])
    patches = _themes_board_patches(reader)
    agent = _make_agent()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        resp = await agent._handle_theme_query(
            AgentRequest(task="/themes", user_id=1, conversation_id="t"))

    assert resp.success, resp.error
    assert "Judge-inferred theme gaps" in resp.result
    assert "Judge: Technology 2026-06-17" in resp.result
    assert "JBL" in resp.result
    assert "1/3 toward /promotetheme" in resp.result
    assert "Some other cohort" not in resp.result   # other sources aren't this section's job
    reader.assert_awaited_with(days=7, include_probe=True)


@pytest.mark.asyncio
async def test_themes_board_omits_section_when_no_judge_inferred_candidates():
    from shared.models import AgentRequest

    reader = AsyncMock(return_value=[
        {"name": "Some other cohort", "tickers": ["X", "Y", "Z"],
         "thesis": "t", "source": "narrative_cogap"},
    ])
    patches = _themes_board_patches(reader)
    agent = _make_agent()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        resp = await agent._handle_theme_query(
            AgentRequest(task="/themes", user_id=1, conversation_id="t"))

    assert resp.success, resp.error
    assert "Judge-inferred theme gaps" not in resp.result


@pytest.mark.asyncio
async def test_themes_board_survives_judge_inferred_section_failure():
    """Advisory-only: a broken reader must degrade the /themes board, never break it."""
    from shared.models import AgentRequest

    reader = AsyncMock(side_effect=RuntimeError("db down"))
    patches = _themes_board_patches(reader)
    agent = _make_agent()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        resp = await agent._handle_theme_query(
            AgentRequest(task="/themes", user_id=1, conversation_id="t"))

    assert resp.success, resp.error
    assert "Solo Theme" in resp.result
    assert "Judge-inferred theme gaps" not in resp.result
