"""Regression tests for the catalyst-downgrade morning digest (#143).

Post-2026-05-28 incident: original ship used an in-process accumulator
that was reset on the 10:04 ET container restart, losing 9 morning
downgrades. Replaced with a DB query against mi_audit_log
`catalyst_earnings_revenue_weak_downgrade` events at digest time — same
in-process-state-vs-restart fix pattern as the EP scan watchdog.

Tests pin: empty-day silent, populated digest renders summary lines.
"""
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_mock_pool


def _make_pool(audit_rows: list[dict], judge_rows: "list[dict] | None" = None):
    """Wire `conn.fetch`: 1st call = downgrade audit rows, 2nd = judge-verdict rows (the
    judge-defer query added 6/17; only fetched when there ARE downgrades)."""
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[audit_rows, judge_rows or []])
    return pool, conn


@pytest.mark.asyncio
async def test_digest_job_empty_no_telegram():
    """Empty mi_audit_log result → returns 0 + no Telegram."""
    from agents.market_intelligence import scheduler

    pool, _conn = _make_pool([])
    sent = []

    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    with patch.object(scheduler, "get_pool", new=AsyncMock(return_value=pool)), \
         patch.object(scheduler, "send_telegram_message", new=_fake_send):
        count = await scheduler._catalyst_downgrade_digest_job()

    assert count == 0
    assert sent == []


@pytest.mark.asyncio
async def test_digest_job_renders_compact_per_ticker_lines():
    """Populated audit rows → single Telegram with one line per ticker."""
    from agents.market_intelligence import scheduler

    audit_rows = [
        {
            "summary": "FOO: strong → routine (earnings catalyst, rubric_composite_14.0_below_22_label_weak)",
            "detail": None,
            "created_at": None,
        },
        {
            "summary": "BAR: game_changer → routine (earnings catalyst, q_rev_yoy_missing_no_prior_year_comparable)",
            "detail": None,
            "created_at": None,
        },
    ]
    # NB: the message renders `game\_changer` (#148 escape) — same readable
    # text in the Telegram client, but parser-safe.
    pool, _conn = _make_pool(audit_rows)
    sent = []

    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    with patch.object(scheduler, "get_pool", new=AsyncMock(return_value=pool)), \
         patch.object(scheduler, "send_telegram_message", new=_fake_send):
        count = await scheduler._catalyst_downgrade_digest_job()

    assert count == 2
    assert len(sent) == 1
    msg = sent[0]
    assert "Catalyst downgrades" in msg
    assert "(2)" in msg
    assert "FOO" in msg
    assert "BAR" in msg
    # Reason rendered as human prose (#148, 2026-05-28):
    assert "rubric 14/39 below 22 floor (weak)" in msg
    assert "Q-rev YoY missing (no prior-year comparable)" in msg
    # Drilldown footer present
    assert "/rubric" in msg


@pytest.mark.asyncio
async def test_digest_annotates_judge_promoted_ticker():
    """A floor-downgraded name the JUDGE promoted to an authoritative HIGH is annotated, so the
    digest stops contradicting the HIGH alert (LZB 6/17). A non-promoted name stays plain."""
    from agents.market_intelligence import scheduler

    audit_rows = [
        {"summary": "LZB: strong → routine (earnings catalyst, q_rev_yoy_missing_no_prior_year_comparable)",
         "detail": None, "created_at": None},
        {"summary": "FOO: strong → routine (earnings catalyst, news_corpus_sparse_no_q_rev)",
         "detail": None, "created_at": None},
    ]
    judge_rows = [
        {"ticker": "LZB", "score_tier": "HIGH", "grade_engine_authority": "judge"},
        {"ticker": "FOO", "score_tier": "MODERATE", "grade_engine_authority": "floor"},
    ]
    pool, _conn = _make_pool(audit_rows, judge_rows)
    sent = []

    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    with patch.object(scheduler, "get_pool", new=AsyncMock(return_value=pool)), \
         patch.object(scheduler, "send_telegram_message", new=_fake_send):
        count = await scheduler._catalyst_downgrade_digest_job()

    assert count == 2
    msg = sent[0]
    lzb_line = next(l for l in msg.splitlines() if "LZB" in l)
    foo_line = next(l for l in msg.splitlines() if "FOO" in l)
    assert "judge promoted to HIGH" in lzb_line     # promoted → annotated
    assert "judge promoted" not in foo_line          # not promoted → plain downgrade line


def test_humanize_rubric_composite_reason():
    """`rubric_composite_X_below_22_label_Y` → `rubric X/39 below 22 floor (Y)`."""
    from agents.market_intelligence.briefing import _humanize_downgrade_reason
    assert _humanize_downgrade_reason(
        "rubric_composite_11.0_below_22_label_weak"
    ) == "rubric 11/39 below 22 floor (weak)"
    assert _humanize_downgrade_reason(
        "rubric_composite_12.3_below_22_label_weak"
    ) == "rubric 12.3/39 below 22 floor (weak)"
    assert _humanize_downgrade_reason(
        "rubric_composite_17.0_below_22_label_routine"
    ) == "rubric 17/39 below 22 floor (routine)"


def test_humanize_static_reason_map():
    """Known machine codes have curated prose translations."""
    from agents.market_intelligence.briefing import _humanize_downgrade_reason
    assert _humanize_downgrade_reason(
        "q_rev_yoy_missing_no_prior_year_comparable"
    ) == "Q-rev YoY missing (no prior-year comparable)"
    assert _humanize_downgrade_reason(
        "news_corpus_sparse_no_q_rev"
    ) == "news corpus sparse, no Q-rev data"


def test_md_escape_underscores_and_stars():
    """#148: dynamic content with `_` or `*` must be escaped before joining
    into Markdown V1 digest lines, else Telegram 400."""
    from agents.market_intelligence.briefing import _md_escape
    assert _md_escape("game_changer") == r"game\_changer"
    assert _md_escape("a_b_c") == r"a\_b\_c"
    assert _md_escape("Q-rev YoY missing (no prior-year comparable)") == \
        "Q-rev YoY missing (no prior-year comparable)"
    assert _md_escape("emphasis*stars*") == r"emphasis\*stars\*"
    assert _md_escape("") == ""
    assert _md_escape(None) == ""


def test_humanize_unknown_reason_falls_back_to_spaced():
    """Unrecognized reason → underscores → spaces, no crash."""
    from agents.market_intelligence.briefing import _humanize_downgrade_reason
    assert _humanize_downgrade_reason(
        "some_brand_new_reason_we_havent_seen_yet"
    ) == "some brand new reason we havent seen yet"
    assert _humanize_downgrade_reason("") == ""


@pytest.mark.asyncio
async def test_digest_job_handles_unparseable_summary_gracefully():
    """Audit row with off-format summary → falls back to verbatim line, no crash."""
    from agents.market_intelligence import scheduler

    audit_rows = [
        {
            "summary": "WEIRD: unstructured downgrade reason no earnings tag",
            "detail": None,
            "created_at": None,
        },
    ]
    pool, _conn = _make_pool(audit_rows)
    sent = []

    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    with patch.object(scheduler, "get_pool", new=AsyncMock(return_value=pool)), \
         patch.object(scheduler, "send_telegram_message", new=_fake_send):
        count = await scheduler._catalyst_downgrade_digest_job()

    assert count == 1
    assert len(sent) == 1
    assert "WEIRD: unstructured downgrade reason no earnings tag" in sent[0]
