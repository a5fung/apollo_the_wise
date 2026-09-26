"""#506 nightly THEME-HIERARCHY health check (2026-09-26).

WHY THIS EXISTS. Operator, 2026-07-27: `parent_theme` sat at 1-of-94 live themes for 11 days
after the #471 arm flipped and NOTHING could have told anyone — no operator surface reads it, no
counter ever had a chance to. He noticed unprompted. Four metrics, each threshold DERIVED off
real `mi_themes` history at runtime (never a picked constant) — see health_checks.py's #506
section header for the full derivation.

#505 landed THE SAME MORNING (`b0bd97c9`) and shipped `theme_ecosystems.containment_parent` /
`resolve_theme_parent` — the ONE reader of the overloaded `parent_theme` column. #506 reads
through those functions here, never re-derives the split. Two framings this file tried and
rejected before the shipped one, both measured 2026-09-26: (a) a parent-centric "parent with
zero children" — all 4 real candidates were single-child parents whose one child retired
naturally, attrition not breakage; (b) a bare "child lost its parent_theme" scan — its biggest
cluster (3 in one day) was the PARENT retiring/renaming that night, `_restore_sub_theme_links`
correctly clearing a now-dangling pointer, the engine working AS DESIGNED. The shipped check
additionally verifies the lost parent NAME is still a live theme before counting a loss.

Mirrors test_theme_quality_check.py / test_ecosystem_reactivation.py's shape: PURE decisions
tested first with zero mocking (plain dicts — the exact shapes hand-verified against prod
2026-09-26), then the orchestrator driven end-to-end with the db.py layer monkeypatched.

THE OVERLOAD TESTS (red on any implementation that trusts `parent_theme` off a Retired row, or
that skips the parent-liveness check): a Retired row's `parent_theme` is a rename/absorption
SUCCESSOR pointer, never a real parent — `_hier_active_snapshot` and
`_hier_lost_parent_link_events` must both refuse to count it, and the latter must also refuse to
count a link clearing because the PARENT stopped existing.
"""
from __future__ import annotations

import inspect
from datetime import date

import pytest

from agents.market_intelligence import health_checks
from agents.market_intelligence.health_checks import (
    _hier_active_snapshot,
    _hier_orphan_point,
    _hier_orphan_series,
    _derive_orphan_growth_alert_pp,
    _hier_lost_parent_link_events,
    _hier_trailing_counts,
    _derive_lost_link_alert,
    _hier_ecosystem_breakdown,
    _hier_parent_kind_counts,
    _evaluate_theme_hierarchy,
    _HIER_MIN_ORPHAN_HISTORY_DATES,
    _HIER_MIN_LOSTLINK_HISTORY_DAYS,
    _HIER_MIN_OWN_HISTORY,
    run_theme_hierarchy_health_check,
    get_theme_hierarchy_evening_line,
)
from agents.market_intelligence.theme_ecosystems import (
    PARENT_KIND_CHILD, PARENT_KIND_ROOT, PARENT_KIND_CATCH_ALL,
)


def _row(name, d, stage, parent=None):
    return {"name": name, "theme_date": d, "stage": stage, "parent_theme": parent}


# ── _hier_active_snapshot — mirrors get_active_themes' own RETIRED-GAP fix ───────────────────────


def test_active_snapshot_keeps_latest_non_retired_row_per_name():
    rows = [
        _row("A", date(2026, 9, 20), "Nascent", "P"),
        _row("A", date(2026, 9, 24), "Fading", None),
        _row("B", date(2026, 9, 23), "Mainstream", "P"),
    ]
    snap = _hier_active_snapshot(rows, date(2026, 9, 25), window_days=7)
    assert set(snap) == {"A", "B"}
    assert snap["A"]["theme_date"] == date(2026, 9, 24)  # the LATEST row, not the parented one


def test_active_snapshot_drops_a_name_whose_latest_row_is_retired():
    # #505/#506 OVERLOAD CASE: this theme WAS parented, but it retired — its latest row is a
    # Retired tombstone. Must be dropped entirely, not counted as a live orphan OR a live child.
    rows = [
        _row("A", date(2026, 9, 20), "Nascent", "P"),
        _row("A", date(2026, 9, 22), "Retired", ""),
    ]
    snap = _hier_active_snapshot(rows, date(2026, 9, 25), window_days=7)
    assert snap == {}


def test_active_snapshot_excludes_rows_outside_the_window():
    rows = [_row("A", date(2026, 9, 1), "Nascent", None)]
    assert _hier_active_snapshot(rows, date(2026, 9, 25), window_days=7) == {}


# ── _hier_orphan_point ───────────────────────────────────────────────────────────────────────────


def test_orphan_point_counts_parented_vs_orphan():
    snap = {"A": {"parent_theme": "P"}, "B": {"parent_theme": None}, "C": {"parent_theme": ""}}
    pt = _hier_orphan_point(snap)
    assert pt == {"n_live": 3, "n_parented": 1, "orphan_pct": pytest.approx(200 / 3)}


def test_orphan_point_empty_snapshot_is_none_not_a_crash():
    assert _hier_orphan_point({}) == {"n_live": 0, "n_parented": 0, "orphan_pct": None}


# ── _hier_orphan_series + _derive_orphan_growth_alert_pp ─────────────────────────────────────────


def test_orphan_series_replays_each_historical_date_strictly_before_asof():
    rows = [
        _row("A", date(2026, 9, 1), "Nascent", "P"),
        _row("B", date(2026, 9, 2), "Nascent", None),
    ]
    # asof (09-02) is deliberately EXCLUDED — it is tonight's own reading, never part of the
    # history used to derive its own alert floor (the self-contamination this file's own test
    # suite caught: a real spike raised its own ceiling high enough to hide itself).
    series = _hier_orphan_series(rows, date(2026, 9, 2), lookback_days=10)
    dates = [pt["theme_date"] for pt in series]
    assert dates == [date(2026, 9, 1)]
    assert series[-1]["n_live"] == 1
    assert series[-1]["n_parented"] == 1


def test_derive_orphan_growth_alert_silent_below_min_history():
    series = [{"orphan_pct": 90.0 + i} for i in range(_HIER_MIN_ORPHAN_HISTORY_DATES - 1)]
    assert _derive_orphan_growth_alert_pp(series) is None


def test_derive_orphan_growth_alert_is_the_historical_max_plus_margin():
    # 20 points, day-over-day diffs mostly 0, one +2.0 spike -> alert = 2.0 + margin(0.5) = 2.5
    series = [{"orphan_pct": 90.0} for _ in range(_HIER_MIN_ORPHAN_HISTORY_DATES)]
    series[10]["orphan_pct"] = 92.0
    alert = _derive_orphan_growth_alert_pp(series)
    assert alert == pytest.approx(2.5)


# ── _hier_lost_parent_link_events — the OVERLOAD test (red on a naive implementation) ────────────


def _parent_still_live(d):
    """A minimal row for 'Parent' so it appears in the active snapshot on `d` — the parent-
    liveness check needs it to actually be a live theme, not just a string in a child's column."""
    return _row("Parent", d, "Mainstream", None)


def test_lost_link_fires_when_a_live_theme_loses_its_parent_without_retiring():
    rows = [
        _row("Child", date(2026, 9, 18), "Nascent", "Parent"),
        _row("Child", date(2026, 9, 21), "Fading", None),   # link gone, theme still alive
        _parent_still_live(date(2026, 9, 21)),               # Parent is STILL a live theme
    ]
    events = _hier_lost_parent_link_events(rows)
    assert len(events) == 1
    assert events[0] == {"name": "Child", "theme_date": date(2026, 9, 21), "lost_parent": "Parent"}


def test_lost_link_silent_when_the_parent_itself_retired_or_renamed_away():
    # THE REAL FALSE POSITIVE, measured 2026-09-26: 'Gold & Precious Metals Miners Rotation'
    # retired/renamed on 09-18 and its 3 children's links cleared THE SAME NIGHT —
    # `_restore_sub_theme_links` correctly dropping a dangling pointer, the engine working AS
    # DESIGNED, not "half-completed nesting". A bare (parent -> no parent, child alive) scan
    # would have counted all 3 as bugs. The discriminator: the parent is no longer a live theme.
    rows = [
        _row("Child", date(2026, 9, 18), "Nascent", "Parent"),
        _row("Child", date(2026, 9, 21), "Fading", None),   # link gone, child still alive
        # Parent has NO row at all near 09-21 — it retired/renamed away, so it is absent from
        # the active snapshot on the loss date (unlike _parent_still_live above).
    ]
    assert _hier_lost_parent_link_events(rows) == []


def test_lost_link_silent_when_the_child_actually_retired():
    # THE OVERLOAD CASE: a Retired row's parent_theme is a rename/absorption SUCCESSOR pointer,
    # not a dropped containment link — natural attrition, never "half-completed nesting".
    rows = [
        _row("Child", date(2026, 9, 18), "Nascent", "Parent"),
        _row("Child", date(2026, 9, 22), "Retired", ""),
        _parent_still_live(date(2026, 9, 22)),
    ]
    assert _hier_lost_parent_link_events(rows) == []


def test_lost_link_silent_when_the_parent_was_never_set():
    rows = [
        _row("Child", date(2026, 9, 18), "Nascent", None),
        _row("Child", date(2026, 9, 21), "Fading", None),
    ]
    assert _hier_lost_parent_link_events(rows) == []


def test_lost_link_silent_when_the_parent_is_still_held():
    rows = [
        _row("Child", date(2026, 9, 18), "Nascent", "Parent"),
        _row("Child", date(2026, 9, 21), "Fading", "Parent"),
        _parent_still_live(date(2026, 9, 21)),
    ]
    assert _hier_lost_parent_link_events(rows) == []


# ── _hier_trailing_counts + _derive_lost_link_alert ───────────────────────────────────────────────


def test_trailing_counts_rolls_a_window_day_by_day():
    counts = _hier_trailing_counts(
        [date(2026, 9, 18)], asof=date(2026, 9, 20), lookback_days=5, window_days=7)
    # evaluated days 09-15..09-19 (asof itself, 09-20, is excluded — see docstring); the event
    # (09-18) enters each day's OWN trailing-7 window starting the day it happens
    assert counts == [0, 0, 0, 1, 1]


def test_derive_lost_link_alert_silent_below_min_history():
    counts = [0] * (_HIER_MIN_LOSTLINK_HISTORY_DAYS - 1)
    assert _derive_lost_link_alert(counts) is None


def test_derive_lost_link_alert_is_the_historical_max():
    counts = [0] * _HIER_MIN_LOSTLINK_HISTORY_DAYS
    counts[3] = 5
    assert _derive_lost_link_alert(counts) == 5


# ── _hier_ecosystem_breakdown ──────────────────────────────────────────────────────────────────


def test_ecosystem_breakdown_catch_all_and_top_bucket():
    snap = {"A": {}, "B": {}, "C": {}, "D": {}}
    eco_map = {"A": "E-SAAS", "B": "E-SAAS", "C": "E-DEF"}  # D unmapped -> catch-all
    out = _hier_ecosystem_breakdown(snap, eco_map)
    assert out["catch_all_n"] == 1
    assert out["catch_all_pct"] == pytest.approx(25.0)
    assert out["top_e_code"] == "E-SAAS"
    assert out["top_n"] == 2
    assert out["n_buckets"] == 3


def test_ecosystem_breakdown_e_unassigned_row_is_the_same_bucket_as_unmapped():
    snap = {"A": {}, "B": {}}
    eco_map = {"A": "E-UNASSIGNED"}   # B has no row at all
    out = _hier_ecosystem_breakdown(snap, eco_map)
    assert out["catch_all_n"] == 2


# ── _hier_parent_kind_counts — ruling-(5) vocabulary (child / root / catch_all) ──────────────────


def test_parent_kind_counts_matches_resolve_theme_parent():
    snap = {
        "Child": {"name": "Child", "stage": "Nascent", "parent_theme": "Parent"},
        "RootThing": {"name": "RootThing", "stage": "Nascent", "parent_theme": None},
        "Unmapped": {"name": "Unmapped", "stage": "Nascent", "parent_theme": None},
    }
    eco_map = {"Child": "E-SAAS", "RootThing": "E-DEF"}  # Unmapped -> catch-all by omission
    counts = _hier_parent_kind_counts(snap, eco_map)
    assert counts == {PARENT_KIND_CHILD: 1, PARENT_KIND_ROOT: 1, PARENT_KIND_CATCH_ALL: 1}


def test_parent_kind_counts_a_retired_rows_parent_theme_never_counts_as_child():
    # Mirrors the overload guard: _hier_active_snapshot already drops Retired latest-rows, so a
    # kind-count call is only ever made on non-Retired rows in production — but the resolver
    # itself must ALSO refuse a Retired row's parent_theme, belt-and-suspenders.
    snap = {"Ghost": {"name": "Ghost", "stage": "Retired", "parent_theme": "Successor"}}
    counts = _hier_parent_kind_counts(snap, {})
    assert counts[PARENT_KIND_CHILD] == 0
    assert counts[PARENT_KIND_CATCH_ALL] == 1


# ── _evaluate_theme_hierarchy — pure decision ────────────────────────────────────────────────────


def _today(**over):
    base = {"orphan_pct": 91.5, "orphan_growth_alert_pp": 3.0, "lost_link_7d": 0,
            "lost_link_alert": 5, "catch_all_n": 3, "catch_all_pct": 2.5,
            "top_e_code": "E-SAAS", "top_pct": 10.2}
    base.update(over)
    return base


def test_orphan_growth_fires_on_a_real_spike():
    baseline = {"orphan_pct": 88.0}
    flags = _evaluate_theme_hierarchy(_today(orphan_pct=95.0), baseline, [])
    assert any(f["kind"] == "orphan_growth" for f in flags)


def test_orphan_growth_silent_without_a_baseline():
    # No usable prior row (first run, or a gap) -> measure only, never page off nothing.
    flags = _evaluate_theme_hierarchy(_today(orphan_pct=95.0), None, [])
    assert flags == []


def test_orphan_growth_silent_on_a_505_style_drop():
    # #505's backfill DROPS the orphan rate — must never be mistaken for a breach.
    baseline = {"orphan_pct": 95.0}
    flags = _evaluate_theme_hierarchy(_today(orphan_pct=10.0), baseline, [])
    assert flags == []


def test_lost_link_fires_above_the_derived_ceiling():
    flags = _evaluate_theme_hierarchy(_today(lost_link_7d=6, lost_link_alert=5), None, [])
    assert any(f["kind"] == "lost_link" for f in flags)


def test_lost_link_silent_at_or_below_the_ceiling():
    flags = _evaluate_theme_hierarchy(_today(lost_link_7d=5, lost_link_alert=5), None, [])
    assert not any(f["kind"] == "lost_link" for f in flags)


def test_catch_all_and_concentration_silent_with_thin_own_history():
    # Bootstrap case: n=0 self-collected history at ship. A big jump must NOT page — there is
    # nothing yet to judge "big" against; inventing a threshold here is exactly what's rejected.
    baseline = {"catch_all_pct": 2.5, "top_pct": 10.2}
    thin_history = [{"catch_all_pct": 2.5, "top_pct": 10.2}] * (_HIER_MIN_OWN_HISTORY - 1)
    flags = _evaluate_theme_hierarchy(
        _today(catch_all_pct=40.0, top_pct=60.0), baseline, thin_history)
    assert not any(f["kind"] in ("catch_all_growth", "concentration_drift") for f in flags)


def test_catch_all_growth_fires_once_own_history_is_long_enough():
    history = [{"catch_all_pct": 2.5, "top_pct": 10.0} for _ in range(_HIER_MIN_OWN_HISTORY)]
    baseline = {"catch_all_pct": 2.5, "top_pct": 10.0}
    flags = _evaluate_theme_hierarchy(_today(catch_all_pct=40.0), baseline, history)
    assert any(f["kind"] == "catch_all_growth" for f in flags)


def test_concentration_drift_is_two_sided():
    history = [{"catch_all_pct": 2.5, "top_pct": 10.0} for _ in range(_HIER_MIN_OWN_HISTORY)]
    baseline = {"catch_all_pct": 2.5, "top_pct": 30.0}
    # top_pct DROPPING sharply (30 -> 5) is also drift, not just growth
    flags = _evaluate_theme_hierarchy(_today(top_pct=5.0), baseline, history)
    assert any(f["kind"] == "concentration_drift" for f in flags)


# ── Integration: run_theme_hierarchy_health_check end-to-end (db.py layer monkeypatched) ──────────


@pytest.fixture
def _captured_telegram(monkeypatch):
    sent: list[str] = []

    async def _send(text, *a, **k):
        sent.append(text)
        return True

    import agents.market_intelligence.briefing as briefing
    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    return sent


@pytest.fixture
def _captured_audit(monkeypatch):
    events: list[tuple] = []

    async def _audit(event_type, summary, detail=""):
        events.append((event_type, summary, detail))

    monkeypatch.setattr(health_checks, "log_audit_event", _audit)
    return events


def _healthy_rows(today, n=15):
    """n live, non-Retired, unparented themes — a realistic thin-orphan-population board with
    NO history to derive an alert floor from (so metrics 1-2 stay unarmed too, same as a real
    fresh install)."""
    return [_row(f"T{i}", today, "Nascent", None) for i in range(n)]


def _wire(monkeypatch, rows, eco_map=None, baseline=None, own_history=None):
    async def _window(conn, asof, lookback_days=100):
        return rows

    async def _eco(conn, names):
        return eco_map or {}

    async def _baseline(conn):
        return baseline

    async def _hist(conn, limit=45):
        return own_history or []

    monkeypatch.setattr(health_checks, "get_theme_hierarchy_window", _window)
    monkeypatch.setattr(health_checks, "get_theme_ecosystem_map", _eco)
    monkeypatch.setattr(health_checks, "get_theme_hierarchy_baseline", _baseline)
    monkeypatch.setattr(health_checks, "get_theme_hierarchy_own_history", _hist)


@pytest.mark.asyncio
async def test_thin_board_is_skipped_not_flagged(_captured_telegram, _captured_audit, monkeypatch):
    today = date(2026, 9, 26)
    _wire(monkeypatch, _healthy_rows(today, n=3))  # below _HIER_MIN_LIVE_THEMES
    monkeypatch.setattr(health_checks, "et_today", lambda: today)

    summary = await run_theme_hierarchy_health_check(conn=object())

    assert summary["skipped"] is not None
    assert summary["flags"] == []
    assert _captured_telegram == []
    assert any(e[0] == "theme_hierarchy_health" and "skipped" in e[1] for e in _captured_audit)


@pytest.mark.asyncio
async def test_clean_run_is_audit_only_no_telegram(_captured_telegram, _captured_audit, monkeypatch):
    today = date(2026, 9, 26)
    _wire(monkeypatch, _healthy_rows(today, n=15))
    monkeypatch.setattr(health_checks, "et_today", lambda: today)

    summary = await run_theme_hierarchy_health_check(conn=object())

    assert summary["skipped"] is None
    assert summary["flags"] == []
    assert _captured_telegram == []
    assert any(e[0] == "theme_hierarchy_health" for e in _captured_audit)


@pytest.mark.asyncio
async def test_orphan_spike_fires_telegram_and_audit(_captured_telegram, _captured_audit, monkeypatch):
    today = date(2026, 9, 26)
    rows = _healthy_rows(today, n=15)
    # A rich, quiet history (flat 0% orphan) so the derived alert floor is tight (near 0 + margin),
    # then TODAY's board is 100% orphan — a real spike against that floor.
    hist_rows = []
    for i in range(_HIER_MIN_ORPHAN_HISTORY_DATES + 5):
        d = date(2026, 8, 1)
        from datetime import timedelta
        d = d + timedelta(days=i)
        hist_rows.append(_row(f"H{i}", d, "Nascent", "P"))
    _wire(monkeypatch, hist_rows + rows,
          baseline={"orphan_pct": 0.0})
    monkeypatch.setattr(health_checks, "et_today", lambda: today)

    summary = await run_theme_hierarchy_health_check(conn=object())

    assert any(f["kind"] == "orphan_growth" for f in summary["flags"])
    assert len(_captured_telegram) == 1
    assert "real parent link" in _captured_telegram[0]
    assert any(e[0] == "theme_hierarchy_health" and "FLAG" in e[1] for e in _captured_audit)


# ── Wiring pins — the derive-the-population discipline: a check that exists but isn't called
# from the nightly job is exactly the #506 failure mode (parent_theme with zero surfaces) ─────


def test_wired_into_post_nightly_audit_job():
    # source-pin-ok: wiring check that the health check is actually called from the nightly
    # job — _post_nightly_audit_job is a ~300-line orchestrator awaiting a dozen+ unrelated
    # health checks in sequence; no existing test drives it end-to-end (each check binds its
    # own get_pool at ITS OWN module's import time — see tests/test_inert_sweep_check.py's
    # file docstring). A correct check nobody calls is exactly #506's own motivating failure
    # (parent_theme sat unread for 11 days) reproduced at the wiring layer.
    from agents.market_intelligence import scheduler
    src = inspect.getsource(scheduler._post_nightly_audit_job)
    assert "run_theme_hierarchy_health_check" in src


def test_wired_into_the_evening_briefing():
    # source-pin-ok: wiring check that the evening line is actually rendered — send_evening_
    # briefing composes a real Telegram message from a dozen+ live data sources; asserting on
    # the sent TEXT would require faking the entire brief. This is the DoD itself: "an operator
    # surface must render this" is unverifiable any other way without standing up the whole
    # briefing pipeline for one line.
    from agents.market_intelligence import briefing
    src = inspect.getsource(briefing.send_evening_briefing)
    assert "get_theme_hierarchy_evening_line" in src


# ── get_theme_hierarchy_evening_line ──────────────────────────────────────────────────────────


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)


class _FakeConn:
    def __init__(self, summary):
        self._summary = summary

    async def fetchrow(self, *a, **k):
        return {"summary": self._summary} if self._summary is not None else None


@pytest.mark.asyncio
async def test_evening_line_none_when_no_row_tonight(monkeypatch):
    async def _pool():
        return _FakePool(_FakeConn(None))
    monkeypatch.setattr(health_checks, "get_pool", _pool)

    assert await get_theme_hierarchy_evening_line() is None


@pytest.mark.asyncio
async def test_evening_line_renders_tonights_summary(monkeypatch):
    async def _pool():
        return _FakePool(_FakeConn("2026-09-26 orphan 91.5% (10/118 parented)"))
    monkeypatch.setattr(health_checks, "get_pool", _pool)

    line = await get_theme_hierarchy_evening_line()
    assert line == "🌳 Theme hierarchy: 2026-09-26 orphan 91.5% (10/118 parented)"


@pytest.mark.asyncio
async def test_evening_line_fails_silent_never_raises(monkeypatch):
    async def _broken_pool():
        raise RuntimeError("pool exhausted")
    monkeypatch.setattr(health_checks, "get_pool", _broken_pool)

    assert await get_theme_hierarchy_evening_line() is None
