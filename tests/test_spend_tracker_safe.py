"""log_anthropic_call_safe — the sanctioned call-site wrapper (S2/F9, 2026-07-03).

Card S2 finding F9: the #377 cost meter was wired by copy-pasting
`try: ... await log_anthropic_call(...) except Exception: pass` at ~16 call
sites. Most swallowed silently — if the tracker broke, ALL spend telemetry went
dark with zero signal (the exact May-2026 12-day outage class it was built to
fix). `log_anthropic_call_safe` is the one sanctioned wrapper: it calls
`log_anthropic_call` and, on failure, logs exactly ONE WARNING instead of
vanishing silently. These tests pin that contract directly (isolated from any
particular call site).
"""
import asyncio
import logging

import pytest

from agents.market_intelligence import spend_tracker


def _run(coro):
    return asyncio.run(coro)


def test_raising_log_anthropic_call_is_swallowed_and_warned(monkeypatch, caplog):
    """A raising log_anthropic_call must NOT propagate out of the safe wrapper,
    and must produce exactly one WARNING naming the caller."""
    async def _boom(*, model, caller, usage):
        raise RuntimeError("db down")

    monkeypatch.setattr(spend_tracker, "log_anthropic_call", _boom)

    with caplog.at_level(logging.WARNING, logger=spend_tracker.logger.name):
        # Must not raise.
        result = _run(spend_tracker.log_anthropic_call_safe(
            model="claude-sonnet-4-6", caller="my_caller", usage=object(),
        ))

    assert result is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "spend tracking failed at my_caller" in warnings[0].message
    assert "db down" in warnings[0].message


def test_healthy_call_forwards_args_and_logs_no_warning(monkeypatch, caplog):
    """A healthy log_anthropic_call must receive the exact args passed to the
    safe wrapper, and no warning should be emitted."""
    calls = []

    async def _capture(*, model, caller, usage):
        calls.append({"model": model, "caller": caller, "usage": usage})
        return 0.042

    monkeypatch.setattr(spend_tracker, "log_anthropic_call", _capture)

    sentinel_usage = object()
    with caplog.at_level(logging.WARNING, logger=spend_tracker.logger.name):
        result = _run(spend_tracker.log_anthropic_call_safe(
            model="claude-opus-4-8", caller="theme_advisor_x", usage=sentinel_usage,
        ))

    assert result is None  # safe wrapper returns None regardless (fire-and-forget)
    assert len(calls) == 1
    assert calls[0] == {
        "model": "claude-opus-4-8",
        "caller": "theme_advisor_x",
        "usage": sentinel_usage,
    }
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_end_to_end_healthy_call_still_writes_the_api_usage_row(monkeypatch):
    """Sanity check the wrapper isn't a no-op shim: a healthy call still goes
    all the way through to the real log_anthropic_call's DB write."""
    from tests.conftest import make_mock_pool

    inserts = []
    pool, conn = make_mock_pool()

    async def _execute(query, *args):
        if "INSERT INTO api_usage" in query:
            inserts.append(args)

    conn.execute.side_effect = _execute

    async def _get_pool():
        return pool

    monkeypatch.setattr(spend_tracker, "_SCHEMA_ENSURED", True)
    monkeypatch.setattr(spend_tracker, "get_pool", _get_pool)

    class _Usage:
        input_tokens = 1000
        output_tokens = 200
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 0

    _run(spend_tracker.log_anthropic_call_safe(
        model="claude-sonnet-4-6", caller="e2e_check", usage=_Usage(),
    ))

    assert len(inserts) == 1
    model, caller, in_tok, out_tok, _cc, _cr, cost = inserts[0]
    assert model == "claude-sonnet-4-6"
    assert caller == "e2e_check"
    assert in_tok == 1000 and out_tok == 200
    assert cost > 0
