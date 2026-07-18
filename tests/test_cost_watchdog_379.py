"""#379 Cost-observability Phase 3 — THE WATCHDOG.

Pins: (1) per-caller $/day anomaly detection fires on a SYNTHETIC spike vs a
caller's own trailing baseline (reusing system_audit's trimmed-median ± MAD
band routing) and stays cold-start/noise-floor gated otherwise; (2) the three
cost-reduction heuristics (Opus-where-Sonnet-fits, oversized prompts,
runaway-retry call volume) fire on fixture data; (3) the daily job Telegrams
ONLY on a real $ anomaly, logs an audit row whenever there's anything to
report, and stays fully silent otherwise; (4) the /cost board appendix render
is empty when there's nothing to show and #477-parity safe (dynamic caller
names inside the code block) when there is.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import cost_board as cb

TODAY = date(2026, 7, 17)


def _mock_pool_with_rows(monkeypatch, rows):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=rows)
    monkeypatch.setattr(cb, "get_pool", AsyncMock(return_value=pool))
    return conn


def _row(caller, d, model="claude-sonnet-4-6", spend=0.0, calls=1, in_tok=1000, out_tok=200):
    return {"caller": caller, "model": model, "d": d, "spend": spend,
            "calls": calls, "in_tok": in_tok, "out_tok": out_tok}


# ── per-caller $ anomaly detection ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_caller_anomaly_fires_on_synthetic_spike(monkeypatch):
    """A caller quietly spending $0.20/day for 2 weeks that spikes to $10
    today (50x) must fire — the DoD's synthetic cost-spike case."""
    rows = [_row("theme_validation", TODAY - timedelta(days=k), spend=0.20, calls=2)
            for k in range(1, 15)]
    rows.append(_row("theme_validation", TODAY, spend=10.0, calls=4))
    _mock_pool_with_rows(monkeypatch, rows)

    out = await cb.compute_caller_cost_anomalies(TODAY)

    assert len(out) == 1
    a = out[0]
    assert a["caller"] == "theme_validation"
    assert a["today_spend"] == 10.0
    assert a["ratio"] >= 5.0


@pytest.mark.asyncio
async def test_caller_anomaly_cold_start_gated(monkeypatch):
    """Only 2 days of history (< CALLER_MIN_SAMPLE_DAYS) — must NOT fire even
    though the ratio would otherwise qualify."""
    rows = [_row("brand_new_caller", TODAY - timedelta(days=k), spend=0.20, calls=2)
            for k in range(1, 3)]
    rows.append(_row("brand_new_caller", TODAY, spend=10.0, calls=4))
    _mock_pool_with_rows(monkeypatch, rows)

    out = await cb.compute_caller_cost_anomalies(TODAY)

    assert out == []


@pytest.mark.asyncio
async def test_caller_anomaly_respects_noise_floor(monkeypatch):
    """Today's spend below CALLER_ANOMALY_MIN_USD never fires, no matter the
    ratio — mirrors the board alarm's $1 floor, scaled per-caller."""
    rows = [_row("tiny_caller", TODAY - timedelta(days=k), spend=0.01, calls=1)
            for k in range(1, 10)]
    rows.append(_row("tiny_caller", TODAY, spend=0.10, calls=1))
    _mock_pool_with_rows(monkeypatch, rows)

    out = await cb.compute_caller_cost_anomalies(TODAY)

    assert out == []


@pytest.mark.asyncio
async def test_caller_anomaly_leak_class_call_volume(monkeypatch):
    """When the spike's call count also scaled up proportionally, label it
    the call-volume/retry-loop leak class (not a per-call cost blowup)."""
    rows = [_row("scanner", TODAY - timedelta(days=k), spend=0.20, calls=2)
            for k in range(1, 15)]
    # 50x spend AND ~50x calls -> same $/call -> call-volume leak class.
    rows.append(_row("scanner", TODAY, spend=10.0, calls=100))
    _mock_pool_with_rows(monkeypatch, rows)

    out = await cb.compute_caller_cost_anomalies(TODAY)

    assert out[0]["leak_class"] == "call-volume (possible retry loop)"


@pytest.mark.asyncio
async def test_caller_anomaly_leak_class_per_call_cost(monkeypatch):
    """Same call count, much higher $/call (e.g. a bloated single prompt) ->
    per-call cost leak class, not call-volume."""
    rows = [_row("judge", TODAY - timedelta(days=k), spend=0.20, calls=2)
            for k in range(1, 15)]
    rows.append(_row("judge", TODAY, spend=10.0, calls=2))
    _mock_pool_with_rows(monkeypatch, rows)

    out = await cb.compute_caller_cost_anomalies(TODAY)

    assert out[0]["leak_class"] == "per-call cost"


# ── cost-reduction surfacing heuristics (pure, fixture-driven) ──────────────

def test_reduction_opportunity_opus_where_sonnet_fits():
    totals = {
        "theme_senior_advisor": {
            "calls": 20, "in_tok": 200_000, "out_tok": 20_000, "spend": 5.0,
            "by_model": {"claude-opus-4-8": {
                "calls": 20, "in_tok": 200_000, "out_tok": 20_000, "spend": 5.0,
            }},
        },
    }
    out = cb._reduction_opportunities_from_totals(totals)
    opus_flags = [o for o in out if o["type"] == "opus_where_sonnet_fits"]
    assert len(opus_flags) == 1
    f = opus_flags[0]
    assert f["caller"] == "theme_senior_advisor"
    # sonnet-equivalent: 200k/1e6*3.00 + 20k/1e6*15.00 = 0.6 + 0.3 = 0.9
    assert f["sonnet_equiv"] == pytest.approx(0.90, abs=0.01)
    assert f["est_savings"] == pytest.approx(4.10, abs=0.01)


def test_reduction_opportunity_oversized_prompt():
    totals = {
        "bloated_caller": {
            "calls": 5, "in_tok": 250_000, "out_tok": 5_000, "spend": 2.0,
            "by_model": {"claude-sonnet-4-6": {
                "calls": 5, "in_tok": 250_000, "out_tok": 5_000, "spend": 2.0,
            }},
        },
    }
    out = cb._reduction_opportunities_from_totals(totals)
    prompt_flags = [o for o in out if o["type"] == "oversized_prompt"]
    assert len(prompt_flags) == 1
    assert prompt_flags[0]["avg_input_tokens"] == 50_000


def test_reduction_opportunity_below_savings_floor_not_flagged():
    """Opus usage that's cheap enough that the Sonnet-equivalent savings
    don't clear the noise floor must NOT be surfaced."""
    totals = {
        "occasional_opus": {
            "calls": 1, "in_tok": 1_000, "out_tok": 200, "spend": 0.015,
            "by_model": {"claude-opus-4-8": {
                "calls": 1, "in_tok": 1_000, "out_tok": 200, "spend": 0.015,
            }},
        },
    }
    out = cb._reduction_opportunities_from_totals(totals)
    assert out == []


def test_retry_loop_opportunity_fires_on_call_volume_trend():
    """Runaway-retry heuristic: a caller's recent call volume well above its
    own non-overlapping baseline, even at a per-call cost too small to ever
    trip the $ anomaly check."""
    daily = {"haiku_retrier": {}}
    series = daily["haiku_retrier"]
    for k in range(3, 33):  # baseline window (non-overlapping w/ "recent")
        series[TODAY - timedelta(days=k)] = {"spend": 0.05, "calls": 5}
    for k in range(0, 3):   # recent window: 4x the baseline call volume
        series[TODAY - timedelta(days=k)] = {"spend": 0.20, "calls": 20}

    out = cb._retry_loop_opportunities(daily, TODAY)

    assert len(out) == 1
    assert out[0]["caller"] == "haiku_retrier"
    assert out[0]["type"] == "runaway_retries"
    assert out[0]["ratio"] >= 1.8


def test_retry_loop_opportunity_quiet_on_stable_volume():
    daily = {"steady_caller": {}}
    series = daily["steady_caller"]
    for k in range(0, 33):
        series[TODAY - timedelta(days=k)] = {"spend": 0.05, "calls": 5}

    out = cb._retry_loop_opportunities(daily, TODAY)

    assert out == []


# ── render_cost_watchdog (pure) ──────────────────────────────────────────────

def test_render_cost_watchdog_empty_when_nothing():
    assert cb.render_cost_watchdog({"anomalies": [], "opportunities": []}) == ""


def test_render_cost_watchdog_parity_safe():
    """Snake_case caller names must stay inside the code block (#477 class)."""
    w = {
        "anomalies": [{"caller": "theme_validation", "today_spend": 10.0,
                       "median30": 0.2, "mad": 0.0, "ratio": 50.0,
                       "today_calls": 4, "median_calls": 2.0,
                       "calls_ratio": 2.0, "leak_class": "per-call cost"}],
        "opportunities": [{"note": "some_caller could use fewer tokens."}],
    }
    out = cb.render_cost_watchdog(w)
    assert "WATCHDOG" in out
    in_code = False
    outside = []
    for line in out.split("\n"):
        if line.strip() == "```":
            in_code = not in_code
            continue
        if not in_code:
            outside.append(line)
    body = "\n".join(outside)
    assert "_" not in body, f"bare underscore outside code block: {body!r}"


# ── run_cost_watchdog (the daily job) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_run_cost_watchdog_fires_telegram_on_anomaly(monkeypatch):
    monkeypatch.setattr(cb, "compute_cost_watchdog", AsyncMock(return_value={
        "anomalies": [{"caller": "theme_validation", "today_spend": 10.0,
                       "median30": 0.2, "mad": 0.0, "ratio": 50.0,
                       "today_calls": 4, "median_calls": 2.0,
                       "calls_ratio": 2.0, "leak_class": "per-call cost"}],
        "opportunities": [],
    }))
    audit = AsyncMock()
    monkeypatch.setattr(cb, "log_audit_event", audit)
    from agents.market_intelligence import briefing as _brief
    tg = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    result = await cb.run_cost_watchdog(TODAY)

    assert result is not None
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "cost_watchdog_check"
    tg.assert_awaited_once()
    msg = tg.await_args.args[0]
    assert "COST WATCHDOG" in msg
    assert "theme_validation" in msg
    assert "```" in msg  # #477 parity: caller name is inside a fence


@pytest.mark.asyncio
async def test_run_cost_watchdog_silent_telegram_opportunities_only(monkeypatch):
    """Reduction opportunities alone log an audit row (queryable / weekly
    digest fodder) but do NOT push a Telegram alert — advisory, not urgent."""
    monkeypatch.setattr(cb, "compute_cost_watchdog", AsyncMock(return_value={
        "anomalies": [],
        "opportunities": [{"type": "oversized_prompt", "caller": "x", "note": "..."}],
    }))
    audit = AsyncMock()
    monkeypatch.setattr(cb, "log_audit_event", audit)
    from agents.market_intelligence import briefing as _brief
    tg = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    result = await cb.run_cost_watchdog(TODAY)

    assert result is not None
    audit.assert_awaited_once()
    tg.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_cost_watchdog_fully_quiet_when_nothing(monkeypatch):
    monkeypatch.setattr(cb, "compute_cost_watchdog", AsyncMock(return_value={
        "anomalies": [], "opportunities": [],
    }))
    audit = AsyncMock()
    monkeypatch.setattr(cb, "log_audit_event", audit)
    from agents.market_intelligence import briefing as _brief
    tg = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    result = await cb.run_cost_watchdog(TODAY)

    assert result is None
    audit.assert_not_awaited()
    tg.assert_not_awaited()
