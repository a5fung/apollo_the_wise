"""#593 (2026-08-24, operator-directed) — `/why TICKER` answers "what did the system see
and what did it decide and why" for a name that NEVER ALERTED.

Operator, looking at NSSC: "i need to know exactly what it is graded and why. As it
stands, all i see is average earnings and a gap, i would never trade it, i need to know
what our system saw and what it decided and why."

The gap was that the grader's own rationale and the news corpus it read were computed,
handed to the shadow writer, and dropped — only a LENGTH was stored. Alerting names kept
their rationale in mi_ep_alerts; every graded name that died under the score bar or on a
post-grade filter kept nothing. These tests pin the DISPLAY half: the rendered section,
the graded-day resolution that makes a bare `/why NSSC` land on the right day, and the
guard that stops the handler bailing out before the section can render.

THE LINE: every assertion here is about DISPLAY. No grade, threshold, prompt or rule is
touched anywhere in this build.
"""
import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence.agent import (
    _GRADE_LADDER, _corpus_sources, _format_catalyst_grade_block, _grade_agreement,
    MarketIntelligenceAgent,
)
from shared.models import AgentRequest

_ET = ZoneInfo("America/New_York")


def _nssc_row(**over):
    """The NSSC 2026-08-24 shape: graded `strong` on a scheduled earnings release, scored
    under the alert bar, so no alert row exists and this is the ONLY surviving record."""
    row = {
        "scan_date": date(2026, 8, 24), "ticker": "NSSC",
        "first_seen_et": datetime(2026, 8, 24, 9, 31, tzinfo=_ET),
        "last_seen_et": datetime(2026, 8, 24, 9, 56, tzinfo=_ET),
        "live_quality_first": "strong", "live_quality_last": "strong",
        "shadow_tier_first": "strong", "shadow_tier_last": "strong",
        "rule_last": "strong_unchanged", "regrade_count": 0,
        "live_side": "lattice", "live_ep_score": 41.0, "live_tier": None,
        "expct_sched": "scheduled", "expct_sched_src": "earnings_calendar",
        "expct_looking": "analyst_only", "expct_combined": "unclassified",
        "expct_beat": False, "demotion_marker": False, "concrete_event": True,
        "sector": "Industrials", "sector_n": 1, "board_n": 18, "sector_confirm": False,
        "gap_pct_last": 9.4,
        "claude_analysis": (
            "NSSC reported Q3 revenue of $137.6M, up 11% year over year. The release is a "
            "scheduled quarterly report with no guidance change and no new contract; the "
            "beat against consensus is modest."),
        "news_summary": "Napco reported third-quarter revenue of $137.6 million, up 11%.",
        "grounded_head": (
            "[SEC 8-K filed 2026-08-24, items 2.02] Napco announced results...\n\n"
            "[Benzinga 2026-08-24] Napco Q3 Revenue Up 11%...\n\n"
            "[Benzinga 2026-08-23] Napco To Report Q3 Earnings...\n\n"
            "[Web summary] Napco reported quarterly revenue growth of 11%..."),
        "grounded_len": 1164,
    }
    row.update(over)
    return row


# ── the rendered section ──────────────────────────────────────────────────────────────


def test_a_graded_name_that_never_alerted_still_reports_grade_reason_and_news():
    """THE ASK, all four parts in one block: what grade, who set it, WHY (the grader's
    own words), and what news it read."""
    out = "\n".join(_format_catalyst_grade_block(_nssc_row()))
    assert "🧠 CATALYST GRADE — strong" in out
    assert "up 11% year over year" in out            # the reasoning, verbatim
    assert "no guidance change" in out               # the beat-vs-guidance distinction
    assert "SEC 8-K" in out and "Benzinga" in out    # what news we read
    assert "1,164 chars" in out
    assert "under the alert bar — no alert" in out   # and why he never saw it


def test_which_grader_acted_is_stated_never_inferred():
    """Both sides are recorded per row; the operator must never have to work out which
    one acted. Plain words on both branches, and the other side is always named."""
    lattice = "\n".join(_format_catalyst_grade_block(
        _nssc_row(live_side="lattice", live_quality_last="game_changer",
                  shadow_tier_last="strong",
                  rule_last="gc_demoted_scheduled_no_content_delta")))
    assert "set by the tier correction" in lattice
    assert "the news grader said game_changer" in lattice
    assert "gc_demoted_scheduled_no_content_delta" in lattice

    llm = "\n".join(_format_catalyst_grade_block(
        _nssc_row(live_side="llm", live_quality_last="routine",
                  shadow_tier_last="strong")))
    assert "set by the news grader" in llm
    assert "the tier correction would have said strong" in llm


def test_a_missing_rationale_says_so_instead_of_going_silent():
    """A pre-#593 row (or a genuinely blind grade) must READ as missing evidence, not as
    an absent section — silence is what made the NSSC question unanswerable."""
    out = "\n".join(_format_catalyst_grade_block(
        _nssc_row(claude_analysis=None, grounded_head=None, grounded_len=0)))
    assert "no rationale recorded" in out
    assert "NO news corpus" in out


def test_a_filter_killed_grade_reports_that_it_was_never_scored():
    """The ARM-class hole: graded, then killed by a post-grade filter before scoring."""
    out = "\n".join(_format_catalyst_grade_block(
        _nssc_row(live_ep_score=None, live_tier=None)))
    assert "never scored — killed by a post-grade filter" in out


def test_an_intraday_regrade_is_visible():
    held = "\n".join(_format_catalyst_grade_block(_nssc_row(regrade_count=0)))
    moved = "\n".join(_format_catalyst_grade_block(_nssc_row(regrade_count=3)))
    assert "grade held all day" in held
    assert "grade changed 3x intraday" in moved


def test_no_row_renders_nothing_and_never_raises():
    assert _format_catalyst_grade_block(None) == []
    assert _format_catalyst_grade_block({}) == []


def test_the_section_is_plain_text_no_markdown_no_pipe_table():
    """`/why` posts with no parse_mode (dynamic prose unbalances Telegram markup) and
    Telegram cannot render pipe tables — CLAUDE.md formatting rules."""
    out = "\n".join(_format_catalyst_grade_block(_nssc_row()))
    assert "|" not in out
    assert "*" not in out and "_" not in out.replace("gc_demoted", "").replace(
        "strong_unchanged", "")


def test_corpus_sources_names_what_was_read_and_dedupes_wires():
    srcs = _corpus_sources(
        "[SEC 8-K filed 2026-08-24, items 2.02] x\n\n"
        "[Benzinga 2026-08-24] a\n\n[Benzinga 2026-08-23] b\n\n[Web summary] c")
    assert srcs == ["SEC 8-K", "Benzinga x2 (2026-08-24)", "web summary"]
    assert _corpus_sources(None) == []
    assert _corpus_sources("") == []


def test_the_rubric_agreement_line_answers_agree_or_disagree_in_plain_words():
    """The operator's real question is whether the deterministic methodology rubric BACKS
    the grade that acted. `weak` sits on the same strength ladder (one step under
    routine) so it is a genuine disagreement, not an incomparable scale."""
    assert "AGREES" in _grade_agreement("strong", "strong")
    out = _grade_agreement("weak", "strong")
    assert "DISAGREES" in out and "2 steps weaker" in out
    assert "1 step stronger" in _grade_agreement("game_changer", "strong")
    # mna is a deal CLASS, not a strength level — no verdict claimable.
    assert "not comparable" in _grade_agreement("routine", "mna")


def test_the_grade_ladder_covers_both_vocabularies_in_strength_order():
    """The grader emits the first three; the rubric emits all four. Order is load-bearing
    — the step count and the weaker/stronger direction are read straight off it."""
    assert _GRADE_LADDER == ("game_changer", "strong", "routine", "weak")
    from agents.market_intelligence.ep_detector import _CATALYST_TOOL
    _enum = _CATALYST_TOOL["input_schema"]["properties"]["quality"]["enum"]
    assert set(_enum) - {"mna"} == set(_GRADE_LADDER) - {"weak"}


# ── the /why handler wiring ───────────────────────────────────────────────────────────


def _wire(monkeypatch, *, grade_row, graded_day=None, latest_union=None):
    """Stub the handler's DB surface: nothing alerted, nothing traded, nothing logged —
    the graded row is the ONLY evidence that exists, which is the whole point."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()

    async def _fetchrow(sql, *args):
        if "MAX(d)" in sql:
            return {"d": latest_union}
        return None

    conn.fetchrow = _fetchrow
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr("agents.market_intelligence.db.get_pool",
                        AsyncMock(return_value=pool))
    monkeypatch.setattr("agents.market_intelligence.db.get_catalyst_grade_record",
                        AsyncMock(return_value=grade_row))
    monkeypatch.setattr("agents.market_intelligence.db.get_latest_catalyst_grade_date",
                        AsyncMock(return_value=graded_day))
    monkeypatch.setattr("agents.market_intelligence.db.get_security_exchange_map",
                        AsyncMock(return_value={}))
    monkeypatch.setattr("agents.market_intelligence.agent._send_plain_with_keyboard",
                        AsyncMock(return_value=False))   # falsy -> body returned to us
    monkeypatch.setattr(
        "agents.market_intelligence.catalyst_metrics_extractor.lookup_cached_metrics",
        AsyncMock(return_value=None))
    return pool


def test_why_renders_the_grade_section_when_nothing_else_exists(monkeypatch):
    """The bail-out guard used to return "no alert / trade / audit events" before the
    section could render — for the exact cohort this build exists to explain."""
    _wire(monkeypatch, grade_row=_nssc_row(), graded_day=date(2026, 8, 24))
    agent = MarketIntelligenceAgent()
    res = asyncio.run(agent._handle_why_query(
        AgentRequest(task="/why NSSC 2026-08-24", user_id=1, conversation_id="t")))
    body = res.result if hasattr(res, "result") else res["result"]
    assert "no alert / trade / audit events" not in body
    assert "🧠 CATALYST GRADE — strong" in body
    assert "up 11% year over year" in body


def test_bare_why_resolves_to_the_last_graded_day(monkeypatch):
    """No alert / trade / audit row exists for a graded-but-not-alerted name, so the
    existing date resolution fell through to today and rendered nothing. The graded day
    now counts as activity — `/why NSSC` with no date typed works."""
    seen = {}

    async def _record(ticker, scan_date):
        seen["scan_date"] = scan_date
        return _nssc_row()

    _wire(monkeypatch, grade_row=None, graded_day=date(2026, 8, 24), latest_union=None)
    monkeypatch.setattr("agents.market_intelligence.db.get_catalyst_grade_record",
                        _record)
    agent = MarketIntelligenceAgent()
    asyncio.run(agent._handle_why_query(
        AgentRequest(task="/why NSSC", user_id=1, conversation_id="t")))
    assert seen["scan_date"] == date(2026, 8, 24)


def test_a_more_recent_alert_day_still_wins_over_an_older_graded_day(monkeypatch):
    """The graded day is folded in as one more activity source, not as an override —
    an actual alert/trade day that is newer must still be the day /why shows."""
    seen = {}

    async def _record(ticker, scan_date):
        seen["scan_date"] = scan_date
        return None

    _wire(monkeypatch, grade_row=None, graded_day=date(2026, 8, 20),
          latest_union=date(2026, 8, 24))
    monkeypatch.setattr("agents.market_intelligence.db.get_catalyst_grade_record",
                        _record)
    agent = MarketIntelligenceAgent()
    asyncio.run(agent._handle_why_query(
        AgentRequest(task="/why NSSC", user_id=1, conversation_id="t")))
    assert seen["scan_date"] == date(2026, 8, 24)


def test_a_telemetry_failure_never_breaks_the_diagnosis(monkeypatch):
    """Display-only means fail-open: a broken grade read must degrade /why to its old
    output, never raise."""
    _wire(monkeypatch, grade_row=None, graded_day=None, latest_union=date(2026, 8, 24))
    monkeypatch.setattr(
        "agents.market_intelligence.db.get_catalyst_grade_record",
        AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(
        "agents.market_intelligence.db.get_latest_catalyst_grade_date",
        AsyncMock(side_effect=RuntimeError("boom")))
    agent = MarketIntelligenceAgent()
    res = asyncio.run(agent._handle_why_query(
        AgentRequest(task="/why NSSC 2026-08-24", user_id=1, conversation_id="t")))
    body = res.result if hasattr(res, "result") else res["result"]
    assert "no alert / trade / audit events" in body
