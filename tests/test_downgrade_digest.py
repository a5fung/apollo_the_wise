"""Regression tests for the catalyst-downgrade morning digest (#143, 2026-05-28).

Pre-#143 behavior: every catalyst downgrade fired a rich per-ticker
Telegram immediately. Today's 9 downgrades = 9 alerts.

Post-#143: per-downgrade Telegram replaced with an in-process
accumulator append. Scheduled job at 10:10 ET drains the accumulator
and sends one digest. Audit log unchanged (per-ticker rows preserved
for `/rubric` drilldown).

Tests pin the accumulator behavior + digest composition.
"""
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import ep_detector


def _reset_accumulator():
    """Helper — wipe module-level state between tests so order doesn't matter."""
    ep_detector._downgrade_digest_pending = []
    ep_detector._downgrade_digest_date = None


# ── Accumulator semantics ────────────────────────────────────────────────────

def test_enqueue_appends_to_accumulator():
    _reset_accumulator()
    ep_detector._enqueue_downgrade_for_digest({"ticker": "FOO", "from_quality": "strong"})
    ep_detector._enqueue_downgrade_for_digest({"ticker": "BAR", "from_quality": "game_changer"})
    assert len(ep_detector._downgrade_digest_pending) == 2
    assert [e["ticker"] for e in ep_detector._downgrade_digest_pending] == ["FOO", "BAR"]


def test_drain_returns_and_clears():
    _reset_accumulator()
    ep_detector._enqueue_downgrade_for_digest({"ticker": "FOO"})
    ep_detector._enqueue_downgrade_for_digest({"ticker": "BAR"})
    items = ep_detector.drain_downgrade_digest()
    assert len(items) == 2
    assert ep_detector._downgrade_digest_pending == []


def test_drain_empty_returns_empty_list():
    _reset_accumulator()
    assert ep_detector.drain_downgrade_digest() == []
    assert ep_detector._downgrade_digest_pending == []


def test_new_day_clears_yesterday():
    """If the accumulator carries entries from a previous date (e.g.,
    container restart spanning midnight), the next enqueue clears stale
    state before appending."""
    from datetime import date as _date
    _reset_accumulator()
    # Manually plant a yesterday-bucketed entry
    ep_detector._downgrade_digest_pending = [{"ticker": "STALE"}]
    ep_detector._downgrade_digest_date = _date(2026, 5, 27)  # yesterday
    # enqueue uses et_today() — patch to return a different date
    with patch.object(ep_detector, "et_today", return_value=_date(2026, 5, 28)):
        ep_detector._enqueue_downgrade_for_digest({"ticker": "FRESH"})
    assert [e["ticker"] for e in ep_detector._downgrade_digest_pending] == ["FRESH"]
    assert ep_detector._downgrade_digest_date == _date(2026, 5, 28)


def test_same_day_appends_without_clearing():
    """Multiple enqueues on the same ET date all accumulate."""
    from datetime import date as _date
    _reset_accumulator()
    with patch.object(ep_detector, "et_today", return_value=_date(2026, 5, 28)):
        ep_detector._enqueue_downgrade_for_digest({"ticker": "A"})
        ep_detector._enqueue_downgrade_for_digest({"ticker": "B"})
        ep_detector._enqueue_downgrade_for_digest({"ticker": "C"})
    assert len(ep_detector._downgrade_digest_pending) == 3


# ── Digest job (end-to-end) ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_digest_job_empty_no_telegram():
    """No accumulated entries → digest job returns 0 + no Telegram."""
    _reset_accumulator()
    from agents.market_intelligence import scheduler

    sent = []
    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    with patch.object(scheduler, "send_telegram_message", new=_fake_send):
        count = await scheduler._catalyst_downgrade_digest_job()

    assert count == 0
    assert sent == []


@pytest.mark.asyncio
async def test_digest_job_renders_compact_per_ticker_lines():
    """Accumulated entries → single Telegram with one line per ticker.
    Verifies header + drilldown footer + correct ticker rendering."""
    _reset_accumulator()
    from agents.market_intelligence import scheduler

    ep_detector._enqueue_downgrade_for_digest({
        "ticker": "FOO", "from_quality": "strong",
        "rubric_composite": 14.0, "rubric_label": "weak",
        "q_rev_yoy": None, "extraction_quality": "high",
        "reason": "rubric_composite_14.0_below_22_label_weak",
    })
    ep_detector._enqueue_downgrade_for_digest({
        "ticker": "BAR", "from_quality": "game_changer",
        "rubric_composite": None, "rubric_label": None,
        "q_rev_yoy": None, "extraction_quality": "medium",
        "reason": "q_rev_yoy_missing_no_prior_year_comparable",
    })

    sent = []
    async def _fake_send(text, *args, **kwargs):
        sent.append(text)

    with patch.object(scheduler, "send_telegram_message", new=_fake_send):
        count = await scheduler._catalyst_downgrade_digest_job()

    assert count == 2
    assert len(sent) == 1
    msg = sent[0]
    assert "Catalyst downgrades" in msg
    assert "(2)" in msg
    assert "FOO" in msg
    assert "BAR" in msg
    assert "14" in msg  # rubric composite shown for FOO
    assert "q_rev_yoy_missing" in msg  # reason fallback for BAR
    assert "/rubric" in msg  # drilldown footer
    # Accumulator drained
    assert ep_detector._downgrade_digest_pending == []
