"""A lane that switches ON must announce itself (operator 2026-08-02).

*"we can have hidden costs that provides no value that is running and no way for us to know about
in time."*

The two existing #379 detectors share a blind spot, and the code says so out loud:
`compute_caller_cost_anomalies` is COLD-START GATED — its own docstring reads *"so a brand-new
caller can't false-positive on day 2"* — and the reduction heuristics only ever ask whether EXISTING
spend is reducible. Nothing asked whether a lane should exist at all. So a new lane ramps invisibly
until it is large enough to move a whole-board total, which for an $11/month experiment is never.

This detector makes the weakest possible claim on purpose: *a caller that never spent before is
spending now*. It passes no judgement on whether it should — that is the operator's call. It exists
so the question gets ASKED on day one instead of five weeks later by accident.
"""
from datetime import date, timedelta

import pytest

from agents.market_intelligence import cost_board as cb

_TODAY = date(2026, 8, 2)


def _row(caller, days_ago, spend=1.0, calls=1):
    """One api_usage row, shaped as _daily_caller_series expects."""
    return {"caller": caller, "model": "claude-opus-5", "d": _TODAY - timedelta(days=days_ago),
            "spend": spend, "calls": calls, "in_tok": 1000, "out_tok": 100}


def _lanes(rows, **kw):
    return cb._new_lanes_from_rows(rows, _TODAY, **kw)


def _callers(rows, **kw):
    return [r["caller"] for r in _lanes(rows, **kw)]


# ── the thing it must catch ──────────────────────────────────────────────────────────────────

def test_a_lane_that_just_started_is_flagged():
    assert _callers([_row("chart_axis_shadow", 0, 4.0, 12)]) == ["chart_axis_shadow"]


def test_the_actual_8_02_case_a_shadow_ramping_under_an_existing_lane():
    """Had the shadow carried its own label, this is the day-one signal that was missing. Note the
    established lane alongside it stays quiet — the point is the NEW one, not the busy one."""
    rows = [_row("ep_grade_judge", d, 0.40, 2) for d in range(0, 30)]
    rows += [_row("chart_axis_shadow", d, 0.45, 6) for d in range(0, 3)]
    assert _callers(rows) == ["chart_axis_shadow"]


def test_it_reports_what_it_cost_and_asks_the_question():
    """A bare name is not actionable; the operator must be able to answer without digging."""
    n = _lanes([_row("new_thing", 1, 2.5, 7)])[0]
    assert n["recent_spend"] == 2.5 and n["recent_calls"] == 7
    assert "what is it buying" in n["note"]


def test_biggest_new_lane_comes_first():
    rows = [_row("small", 0, 0.5, 1), _row("big", 0, 9.0, 40)]
    assert _callers(rows) == ["big", "small"]


# ── the things it must NOT cry wolf on ───────────────────────────────────────────────────────

def test_an_established_lane_is_never_new():
    rows = [_row("ep_grade_judge", d, 1.0, 3) for d in range(0, 30)]
    assert _callers(rows) == []


def test_a_lane_quiet_recently_but_active_in_the_baseline_is_not_new():
    """Resuming is not starting."""
    rows = [_row("theme_discovery", d, 1.0, 3) for d in (0, 1, 10, 20)]
    assert _callers(rows) == []


def test_a_sparse_weekly_lane_is_not_new():
    """Weekly cadence still leaves baseline days — this is the caller class the anomaly detector's
    active-days-only median was built for, and it must not trip this one either."""
    rows = [_row("system_review_weekly", d, 0.8, 1) for d in (0, 7, 14, 21, 28)]
    assert _callers(rows) == []


def test_a_trivial_smoke_test_is_below_the_floor():
    """One cheap call while someone tests a script is not a lane."""
    assert _callers([_row("probe", 0, 0.01, 1)]) == []


def test_the_floor_is_on_dollars_not_calls():
    """Many cheap Haiku calls still cost real money and still count."""
    assert _callers([_row("cheap_but_busy", 0, 0.50, 900)]) == ["cheap_but_busy"]


def test_no_rows_no_lanes():
    assert _lanes([]) == []


def test_a_lane_older_than_the_recent_window_is_not_new():
    """Started 5 days ago with the window at 3 → its day-4 spend IS baseline, so it is not new.
    Without this the window would slide forever and re-announce old lanes."""
    rows = [_row("older", d, 1.0, 2) for d in range(0, 5)]
    assert _callers(rows) == []


# ── announced ONCE, ever ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_already_announced_lane_is_not_re_announced(monkeypatch):
    """Without this a monthly-cadence caller re-announces every month — the exact 'repeated
    non-actionable Telegram' failure run_daily_spend_alarm already learned on 7/17. The audit log
    is the state; no new table."""
    class _Conn:
        async def fetch(self, *a, **k):
            return [{"summary_caller": "already_known"}]

    class _Acq:
        async def __aenter__(self): return _Conn()
        async def __aexit__(self, *a): return False

    class _Pool:
        def acquire(self): return _Acq()

    async def _pool():
        return _Pool()

    monkeypatch.setattr(cb, "get_pool", _pool)
    out = await cb._unannounced_new_lanes(
        [{"caller": "already_known"}, {"caller": "brand_new"}])
    assert [c["caller"] for c in out] == ["brand_new"]


@pytest.mark.asyncio
async def test_no_candidates_does_not_touch_the_database():
    """The daily job runs every weekday and almost always has nothing — it must not pay for a
    query to learn that."""
    def _boom():
        raise AssertionError("hit the DB with no candidates")

    import agents.market_intelligence.cost_board as mod
    saved, mod.get_pool = mod.get_pool, _boom
    try:
        assert await cb._unannounced_new_lanes([]) == []
    finally:
        mod.get_pool = saved


# ── it reaches the operator ──────────────────────────────────────────────────────────────────

def test_the_board_renders_new_lanes():
    out = cb.render_cost_watchdog(
        {"anomalies": [], "opportunities": [],
         "new_lanes": [{"caller": "chart_axis_shadow", "recent_spend": 4.0,
                        "recent_calls": 12, "window_days": 3}]})
    assert "chart_axis_shadow" in out and "never spent before" in out


def test_a_new_lane_alone_still_renders_a_watchdog_block():
    """It must not need an anomaly to ride along — a new lane IS the finding."""
    out = cb.render_cost_watchdog(
        {"anomalies": [], "opportunities": [],
         "new_lanes": [{"caller": "x", "recent_spend": 1.0, "recent_calls": 2, "window_days": 3}]})
    assert out.startswith("*🐕 WATCHDOG*")


def test_still_silent_when_there_is_nothing_at_all():
    assert cb.render_cost_watchdog({"anomalies": [], "opportunities": [], "new_lanes": []}) == ""


def test_caller_names_stay_inside_the_code_fence():
    """Caller labels are snake_case; a bare underscore outside a fence breaks Telegram Markdown
    (the #477 parity class)."""
    out = cb.render_cost_watchdog(
        {"anomalies": [], "opportunities": [],
         "new_lanes": [{"caller": "chart_axis_shadow", "recent_spend": 1.0,
                        "recent_calls": 2, "window_days": 3}]})
    body, fence, rest = out.partition("```")
    assert "chart_axis_shadow" not in body and "chart_axis_shadow" in rest
