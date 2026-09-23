"""#543 DoD (c) — a health signal for GRADING ITSELF.

The 08-06/08-07 extraction outage graded 14 earnings names/day down on an exception and the
one number that separates "weak tape" from "dead component" — the share of grading decisions
caused by system FAILURE vs caused by the DATA — went 0% → 53% → 88% across three days with
nothing watching. The failure rows logged as `catalyst_earnings_revenue_weak_downgrade`
(reason `extraction_failed_extraction_call_failed`), a normal-sounding business outcome, so a
total component outage read as a quiet day of weak catalysts.

These tests pin, with the REAL per-day event counts from prod mi_audit_log:
  1. the classifier splits failure-shaped events (incl. the incident's weak_downgrade-with-
     failure-reason shape) from data-driven decisions;
  2. the predicate FIRES on both real incident days and is SILENT on every real healthy-day
     shape around them, including 08-11 (0 failures / 8 data) and 07-27 (1/1 — the
     single-failure guard);
  3. the runner Telegrams + writes the audit row ONLY when the predicate fires — a healthy
     day writes NOTHING (a guard that always fires is not a guard, CLAUDE.md 08-03);
  4. the check is wired into the nightly audit job.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import health_checks as hc

# ── the classifier ──────────────────────────────────────────────────────────


def test_failure_events_classify_as_failure():
    for ev in ("catalyst_extraction_failed_grade_kept", "extraction_error",
               "live_enriched_grade_failed", "judge_verdict_truncated"):
        assert hc._classify_grading_event(ev, None) == "failure", ev


def test_data_downgrades_classify_as_data():
    detail = json.dumps({"reason": "rubric_composite_15.0_below_22_label_routine"})
    assert hc._classify_grading_event(
        "catalyst_earnings_revenue_weak_downgrade", detail) == "data"
    for ev in ("catalyst_prose_mismatch_downgrade", "catalyst_pplx_hedge_downgrade",
               "catalyst_downgrade_carveout_applied", "catalyst_yoy_recovered_live"):
        assert hc._classify_grading_event(ev, None) == "data", ev


def test_the_incident_shape_weak_downgrade_with_failure_reason_is_FAILURE():
    """THE 08-06/07 shape: the failure hid inside a normal-sounding downgrade event whose
    DETAIL carried `extraction_failed_extraction_call_failed`. If this classifies as data,
    the original outage is invisible again — this line is the whole point of the check."""
    detail = json.dumps({"ticker": "DOCS", "reason": "extraction_failed_extraction_call_failed"})
    assert hc._classify_grading_event(
        "catalyst_earnings_revenue_weak_downgrade", detail) == "failure"


def test_garbled_detail_defaults_to_data_not_failure():
    """Bad JSON must never fake an outage."""
    assert hc._classify_grading_event(
        "catalyst_earnings_revenue_weak_downgrade", "not json{") == "data"
    assert hc._classify_grading_event(
        "catalyst_earnings_revenue_weak_downgrade", None) == "data"


def test_unrelated_events_are_not_grading_decisions():
    assert hc._classify_grading_event("spend_alarm_fired", None) is None


# ── the predicate, on the REAL daily counts from prod mi_audit_log ──────────


def test_fires_on_incident_day_one_0806_real_counts():
    """2026-08-06: 9 failure-driven (8 weak_downgrades w/ extraction_failed reason +
    1 live_enriched_grade_failed) vs 8 data-driven → 53%. Day one must fire."""
    flag = hc._evaluate_grading_health(9, 8)
    assert flag is not None
    assert flag["ratio"] == pytest.approx(0.529, abs=0.001)


def test_fires_on_incident_day_two_0807_real_counts():
    """2026-08-07: 46 failure-driven vs 6 data-driven → 88%."""
    flag = hc._evaluate_grading_health(46, 6)
    assert flag is not None
    assert flag["ratio"] == pytest.approx(0.885, abs=0.001)


def test_silent_on_the_eve_of_the_incident_0805_real_counts():
    """2026-08-05: 0 failures, 23 data-driven decisions → healthy, silent."""
    assert hc._evaluate_grading_health(0, 23) is None


def test_silent_today_0811_real_counts():
    """2026-08-11 (the silence proof day): 0 failures, 8 data decisions."""
    assert hc._evaluate_grading_health(0, 8) is None


def test_single_failure_never_alerts_the_0727_real_day():
    """2026-07-27 was a REAL 1-failure/1-data day (ratio 50%!). One failure is not an
    outage signal — the F>=2 floor keeps this silent, and history says it must."""
    assert hc._evaluate_grading_health(1, 1) is None
    assert hc._evaluate_grading_health(1, 0) is None


def test_two_call_day_cannot_scream_denominator_floor():
    """2 failures, 0 data → 100% of a 2-decision day. The denominator floor holds."""
    assert hc._evaluate_grading_health(2, 0) is None


def test_small_day_total_outage_still_fires():
    """3 names, 2 failed + 1 data-graded → 67% of 3 decisions: the smallest real
    outage shape that should alert."""
    assert hc._evaluate_grading_health(2, 1) is not None


def test_minority_failures_stay_silent():
    """Failures present but the data still decided the day (e.g. 2 of 16) — silent."""
    assert hc._evaluate_grading_health(2, 14) is None


# ── the runner: alert path writes + sends, healthy path touches NOTHING ─────


def _mock_conn(rows):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)
    return conn


def _wd(reason, ticker="XYZ"):
    return {"event_type": "catalyst_earnings_revenue_weak_downgrade",
            "summary": f"{ticker}: ...",
            "detail": json.dumps({"ticker": ticker, "reason": reason})}


def _ev(event_type, ticker="XYZ"):
    return {"event_type": event_type, "summary": f"{ticker}: ...",
            "detail": json.dumps({"ticker": ticker})}


@pytest.mark.asyncio
async def test_runner_fires_audit_and_telegram_on_incident_shape(monkeypatch):
    rows = ([_wd("extraction_failed_extraction_call_failed", ticker=f"F{i}")
             for i in range(8)]
            + [_ev("live_enriched_grade_failed", ticker="F9")]
            + [_wd("rubric_composite_15.0_below_22_label_routine", ticker=f"D{i}")
               for i in range(8)])
    from agents.market_intelligence import db as _db, briefing as _brief
    audit = AsyncMock()
    tg = AsyncMock()
    monkeypatch.setattr(_db, "log_audit_event", audit)
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    out = await hc.run_grading_health_check(conn=_mock_conn(rows), today=date(2026, 8, 6))

    assert out["failure_n"] == 9 and out["data_n"] == 8
    assert out["flag"] is not None
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "grading_health_alert"
    tg.assert_awaited_once()
    msg = tg.await_args.args[0]
    assert "GRADING HEALTH" in msg
    assert "```" in msg  # #477 parity: snake_case event names inside the fence


@pytest.mark.asyncio
async def test_runner_totally_silent_on_a_healthy_day(monkeypatch):
    """The 08-11 shape: only data-driven decisions. No audit row, no Telegram —
    the runner must not write ANYTHING on a healthy day."""
    rows = ([_wd("rubric_composite_14.0_below_22_label_routine", ticker=f"D{i}")
             for i in range(5)]
            + [_ev("catalyst_yoy_recovered_live", ticker="K1"),
               _ev("catalyst_yoy_recovered_live", ticker="K2"),
               _ev("catalyst_downgrade_carveout_applied", ticker="K3")])
    from agents.market_intelligence import db as _db, briefing as _brief
    audit = AsyncMock()
    tg = AsyncMock()
    monkeypatch.setattr(_db, "log_audit_event", audit)
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    out = await hc.run_grading_health_check(conn=_mock_conn(rows), today=date(2026, 8, 11))

    assert out["failure_n"] == 0 and out["data_n"] == 8
    assert out["flag"] is None
    audit.assert_not_awaited()
    tg.assert_not_awaited()


@pytest.mark.asyncio
async def test_runner_silent_on_an_empty_day(monkeypatch):
    """No earnings names at all (weekend / quiet tape) → nothing to divide, nothing sent."""
    from agents.market_intelligence import db as _db, briefing as _brief
    audit = AsyncMock()
    tg = AsyncMock()
    monkeypatch.setattr(_db, "log_audit_event", audit)
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    out = await hc.run_grading_health_check(conn=_mock_conn([]), today=date(2026, 8, 9))

    assert out["total"] == 0 and out["flag"] is None
    audit.assert_not_awaited()
    tg.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_ticker_relogged_across_scan_ticks_counts_ONCE(monkeypatch):
    """The ACMR case, real: a broken emission dedup logged the SAME ticker's
    grade_kept 4x on 08-07, and a persistently-failing ticker re-extracts every
    scan tick. One name failing repeatedly is ONE failure — it must not cross
    the F>=2 floor and fake a multi-name outage."""
    rows = ([_ev("catalyst_extraction_failed_grade_kept", ticker="ACMR")
             for _ in range(4)]
            + [_wd("rubric_composite_15.0_below_22_label_routine", ticker="D1"),
               _wd("rubric_composite_16.0_below_22_label_routine", ticker="D2")])
    from agents.market_intelligence import db as _db, briefing as _brief
    audit = AsyncMock()
    tg = AsyncMock()
    monkeypatch.setattr(_db, "log_audit_event", audit)
    monkeypatch.setattr(_brief, "send_telegram_message", tg)

    out = await hc.run_grading_health_check(conn=_mock_conn(rows), today=date(2026, 8, 7))

    assert out["failure_n"] == 1  # 4 rows, one name
    assert out["flag"] is None
    audit.assert_not_awaited()
    tg.assert_not_awaited()


# ── wiring: the check must actually run somewhere (dead-column-sweep test idiom) ──

SCHED = pathlib.Path("agents/market_intelligence/scheduler.py").read_text(encoding="utf-8")


def test_wired_into_the_nightly_audit_job():
    assert "run_grading_health_check" in SCHED, "the grading-health check is not wired into any job"
    # inside _post_nightly_audit_job, before the next job def
    seg = SCHED.split("async def _post_nightly_audit_job")[1].split("\nasync def ")[0]
    assert "run_grading_health_check" in seg
    # own try/except so its failure can't kill the rest of the audit chain
    call_zone = seg.split("run_grading_health_check")[0][-800:]
    assert "try:" in call_zone
    assert 'notify_job_failure("grading_health_check"' in seg


def test_grade_kept_emission_dedup_arg_order_is_fixed():
    """ep_detector passed (ticker, event) to the (event, ticker) dedup helper, so the
    dedup NEVER matched, failed open, and re-logged grade_kept every scan tick (prod
    08-07: ACMR 4x). Pin the corrected order; no call site may pass `ticker` first."""
    import re
    src = pathlib.Path("agents/market_intelligence/ep_detector.py").read_text(encoding="utf-8")
    assert '"catalyst_extraction_failed_grade_kept", ticker' in src
    assert not re.search(r"_should_log_catalyst_earnings_event_today\(\s*ticker", src), (
        "a dedup call site passes `ticker` as the first (event_type) argument again")
