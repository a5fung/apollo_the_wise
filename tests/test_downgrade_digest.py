"""Regression tests for the catalyst-downgrade morning digest (#143).

Post-2026-05-28 incident: original ship used an in-process accumulator
that was reset on the 10:04 ET container restart, losing 9 morning
downgrades. Replaced with a DB query against mi_audit_log
`catalyst_earnings_revenue_weak_downgrade` events at digest time — same
in-process-state-vs-restart fix pattern as the EP scan watchdog.

Tests pin: empty-day silent, populated digest renders summary lines.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pool(audit_rows: list[dict]):
    """Mock asyncpg pool whose conn.fetch returns the given rows."""
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=audit_rows)
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
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
    # Inner reason surfaces post the "(earnings catalyst, " split:
    assert "rubric_composite_14.0_below_22_label_weak" in msg
    assert "q_rev_yoy_missing_no_prior_year_comparable" in msg
    # Drilldown footer present
    assert "/rubric" in msg


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
