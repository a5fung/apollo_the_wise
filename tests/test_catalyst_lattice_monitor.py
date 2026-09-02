"""#533 Change 6 — the catalyst-tier FLIP MONITOR (2026-08-22, operator-signed).

The flip is a negative test (operator: "flip now and revert when wrong ... and have a
condition to test if we're right or not and monitor"), so the monitor IS the safety story:
these tests pin the three revert triggers, the acting-side resolution (never inferred from
dates), the once-per-member P1 dedupe, the stand-down when the revert flag is off, and that
the alert message names the trigger, the numbers, and the EXACT revert command.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import health_checks as hc
from agents.market_intelligence import db as _db
from agents.market_intelligence import briefing as _brief

_FRI = date(2026, 8, 21)  # a Friday


def _weekday(d: date) -> bool:
    return d.weekday() < 5


# ── pure evaluators ──────────────────────────────────────────────────────────────────


def test_high_drop_fires_only_when_fall_exceeds_50_pct():
    assert hc._evaluate_lattice_high_drop(0.9, 2.0) is not None      # 55% fall -> fire
    assert hc._evaluate_lattice_high_drop(1.0, 2.0) is None          # exactly 50% -> no
    assert hc._evaluate_lattice_high_drop(1.5, 2.0) is None          # 25% fall -> no
    f = hc._evaluate_lattice_high_drop(0.5, 2.0)
    assert f["drop_pct"] == 75.0 and f["recent_avg"] == 0.5 and f["prior_avg"] == 2.0


def test_high_drop_never_fires_from_a_zero_baseline():
    """Nothing to fall FROM — a cold lane is trigger (c)'s job, not (b)'s."""
    assert hc._evaluate_lattice_high_drop(0.0, 0.0) is None


def test_acting_tier_is_decided_by_live_side_never_by_date():
    assert hc._lattice_acting_tier("lattice", "strong", "routine") == "routine"
    assert hc._lattice_acting_tier("llm", "routine", "strong") == "routine"
    assert hc._lattice_acting_tier(None, "routine", "strong") == "routine"  # pre-column rows = llm era


def test_fixture_loader_returns_members_and_skips_excluded():
    members = hc._load_must_not_miss_members()
    assert members is not None
    assert ("MRNA", "2026-08-19") in members
    assert all(t != "TDIC" for t, _ in members)  # excluded=True member stays out


def test_fixture_loader_returns_None_not_empty_on_import_failure(monkeypatch):
    """None (never []) so the caller can tell 'P1 trigger DARK' from 'no members'."""
    import types
    monkeypatch.setitem(sys.modules, "tests.fixtures.must_not_miss_eps",
                        types.ModuleType("tests.fixtures.must_not_miss_eps"))
    assert hc._load_must_not_miss_members() is None


# ── trigger (b) era-scope fix (2026-08-24) — pure helpers ──────────────────────────────


def test_era_windows_self_heal_once_flip_is_outside_the_lookback_span():
    """Flip far before the whole 37-day lookback -> byte-identical to the pre-fix windows
    (the fix must not permanently narrow trigger (b)), and scoped=False so the post-flip
    floor at the call site is correctly bypassed too (see the holiday-week test below)."""
    day = date(2026, 9, 1)
    recent, prior, scoped = hc._lattice_era_windows(day, date(2026, 1, 1))
    recent_orig = hc._lattice_trading_days(day, hc._LATTICE_RECENT_DAYS)
    prior_orig = [d for d in hc._lattice_trading_days(
        day, hc._LATTICE_RECENT_DAYS + hc._LATTICE_PRIOR_DAYS) if d not in set(recent_orig)]
    assert recent == recent_orig
    assert prior == prior_orig
    assert scoped is False


def test_era_windows_split_at_the_flip_drop_not_move(monkeypatch):
    """Flip lands inside the lookback span: 'recent' keeps only trading days on/after it,
    'prior' keeps only trading days before it, and a day on the wrong side of its ORIGINAL
    bucket is dropped rather than reassigned (see _lattice_era_windows docstring)."""
    monkeypatch.setattr(hc, "_is_trading_day", _weekday)
    day = date(2026, 8, 24)          # Monday
    flip = date(2026, 8, 22)         # Saturday -- first trading day on/after it is 08-24
    recent, prior, scoped = hc._lattice_era_windows(day, flip)
    assert recent == [date(2026, 8, 24)]
    assert all(d < flip for d in prior)
    assert date(2026, 8, 21) not in recent and date(2026, 8, 21) not in prior
    assert scoped is True


class _FlipDateConn:
    """Isolated fake for _lattice_flip_date's own source-priority tests."""

    def __init__(self, safeguard_row=None, shadow_row=None, raise_on=()):
        self.safeguard_row = safeguard_row
        self.shadow_row = shadow_row
        self.raise_on = set(raise_on)

    async def fetchrow(self, sql, *args):
        if "mi_safeguard_state" in sql:
            if "safeguard_state" in self.raise_on:
                raise RuntimeError("boom")
            return self.safeguard_row
        if "mi_catalyst_tier_shadow" in sql:
            if "shadow" in self.raise_on:
                raise RuntimeError("boom")
            return self.shadow_row
        raise AssertionError(f"unexpected query: {sql}")


@pytest.mark.asyncio
async def test_flip_date_prefers_the_safeguard_state_transition():
    conn = _FlipDateConn(safeguard_row={"flip_date": date(2026, 8, 22)},
                          shadow_row={"flip_date": date(2026, 8, 24)})
    d, source = await hc._lattice_flip_date(conn)
    assert (d, source) == (date(2026, 8, 22), "safeguard_state")


@pytest.mark.asyncio
async def test_flip_date_falls_back_to_the_shadow_acting_record():
    """No safeguard_state row (the expected case — the flip shipped via a code default,
    never an explicit toggle write) -> the acting-record MIN, not a guess."""
    conn = _FlipDateConn(safeguard_row=None, shadow_row={"flip_date": date(2026, 8, 22)})
    d, source = await hc._lattice_flip_date(conn)
    assert (d, source) == (date(2026, 8, 22), "shadow_acting_record")


@pytest.mark.asyncio
async def test_flip_date_falls_back_to_the_hardcoded_constant_when_both_are_empty():
    conn = _FlipDateConn(safeguard_row=None, shadow_row=None)
    d, source = await hc._lattice_flip_date(conn)
    assert (d, source) == (hc._LATTICE_FLIP_DATE_FALLBACK, "hardcoded_fallback")


@pytest.mark.asyncio
async def test_flip_date_falls_through_a_query_error_to_the_next_source():
    conn = _FlipDateConn(raise_on={"safeguard_state"},
                          shadow_row={"flip_date": date(2026, 8, 24)})
    d, source = await hc._lattice_flip_date(conn)
    assert (d, source) == (date(2026, 8, 24), "shadow_acting_record")


# ── the runner ───────────────────────────────────────────────────────────────────────


class _FakeConn:
    """Routes by SQL substring; fetchrow (audit dedupe) returns None unless set.

    `flip_date`: when set, answers the trigger-(b) flip-date lookup via the
    mi_catalyst_tier_shadow MIN(scan_date) route (source 2). `safeguard_transition`: when
    set, answers it via the mi_safeguard_state route (source 1, preferred). Neither set ->
    both flip-date queries return no row -> `_lattice_flip_date` falls through to the
    hardcoded fallback, exactly like a fresh/never-toggled DB."""

    def __init__(self, shadow_rows=None, alert_rows=None, dedupe_hit=False,
                 flip_date=None, safeguard_transition=None, supply=None):
        self.shadow_rows = shadow_rows or []
        self.alert_rows = alert_rows or []
        self.dedupe_hit = dedupe_hit
        self.flip_date = flip_date
        self.safeguard_transition = safeguard_transition
        # `supply` (trigger (b)'s denominator, 2026-08-26): None -> a FLAT tape, which makes
        # the supply-normalised statistic mathematically identical to the old per-trading-day
        # one (constant supply cancels), so every pre-existing trigger-(b) assertion keeps
        # measuring what it was written to measure. Pass a {date: gapping-stock-count} dict to
        # vary the tape; a date ABSENT from that dict is 'not measured' (no row at all), which
        # is NOT the same as a zero-supply day.
        self.supply = supply
        self.saw_sql = []

    _FLAT_SUPPLY = 20

    async def fetch(self, sql, *args):
        self.saw_sql.append(sql)
        if "mi_daily_closes" in sql:
            span_start, span_end = args[2], args[1]
            if self.supply is None:
                days, d = [], span_start
                while d <= span_end:
                    days.append((d, self._FLAT_SUPPLY))
                    d += timedelta(days=1)
            else:
                days = [(d, n) for d, n in sorted(self.supply.items())
                        if span_start <= d <= span_end]
            return [{"trade_date": d, "rows_with_open": 12_300, "supply": n}
                    for d, n in days]
        if "mi_catalyst_tier_shadow" in sql:
            return self.shadow_rows
        if "mi_ep_alerts" in sql:
            return self.alert_rows
        return []

    async def fetchrow(self, sql, *args):
        if "mi_safeguard_state" in sql:
            if self.safeguard_transition is None:
                return None
            return {"flip_date": self.safeguard_transition}
        if "mi_catalyst_tier_shadow" in sql:
            if self.flip_date is None:
                return None
            return {"flip_date": self.flip_date}
        return {"?": 1} if self.dedupe_hit else None


def _patch_common(monkeypatch, toggle=True):
    audit = AsyncMock()
    tg = AsyncMock(return_value=True)
    monkeypatch.setattr(_db, "get_runtime_toggle", AsyncMock(return_value=toggle))
    monkeypatch.setattr(_db, "log_audit_event", audit)
    monkeypatch.setattr(_brief, "send_telegram_message", tg)
    monkeypatch.setattr(hc, "_is_trading_day", _weekday)
    return audit, tg


def _alert_rows(day, recent_high, prior_high, zero_last_n=0):
    """Weekday rows over the 37-day span: prior window prior_high HIGHs/day, recent window
    recent_high HIGHs/day; the last zero_last_n trading days get 0 rows entirely."""
    rows, zeroed = [], 0
    d, i = day, 0
    while i < hc._LATTICE_RECENT_DAYS + hc._LATTICE_PRIOR_DAYS:
        if _weekday(d):
            in_recent = i < hc._LATTICE_RECENT_DAYS
            if in_recent and zeroed < zero_last_n:
                zeroed += 1  # no row at all — a genuinely silent day
            else:
                high = recent_high if in_recent else prior_high
                rows.append({"alert_date": d, "n": max(high, 1), "high_n": high})
        from datetime import timedelta
        d -= timedelta(days=1)
        i += 1
    return rows


@pytest.mark.asyncio
async def test_stands_down_when_the_revert_flag_is_off(monkeypatch):
    audit, tg = _patch_common(monkeypatch, toggle=False)
    out = await hc.run_catalyst_lattice_monitor(conn=_FakeConn(), today=_FRI)
    assert out["enabled"] is False and out["triggers"] == []
    tg.assert_not_called()
    audit.assert_not_called()


@pytest.mark.asyncio
async def test_healthy_day_is_totally_silent(monkeypatch):
    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=3, prior_high=3))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert out["triggers"] == [] and out["errors"] == []
    tg.assert_not_called()
    audit.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_a_member_graded_routine_by_the_acting_side(monkeypatch):
    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(
        shadow_rows=[{"scan_date": date(2026, 8, 19), "ticker": "MRNA",
                      "live_quality_last": "strong", "shadow_tier_last": "routine",
                      "live_side": "lattice"}],
        alert_rows=_alert_rows(_FRI, recent_high=3, prior_high=3))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    kinds = [t["kind"] for t in out["triggers"]]
    assert kinds == ["p1_member_routine"]
    msg = tg.call_args[0][0]
    assert "MRNA" in msg and "P1 MISS" in msg
    assert hc._LATTICE_REVERT_SQL in msg          # the EXACT revert command
    events = [c.args[0] for c in audit.call_args_list]
    assert "catalyst_lattice_monitor_alert" in events
    assert "catalyst_lattice_p1_miss" in events


@pytest.mark.asyncio
async def test_trigger_a_same_side_llm_row_uses_llm_grade_and_dedupe_holds(monkeypatch):
    audit, tg = _patch_common(monkeypatch)
    # live_side='llm': the LLM grade acted; lattice saying routine must NOT fire
    conn = _FakeConn(
        shadow_rows=[{"scan_date": date(2026, 8, 19), "ticker": "MRNA",
                      "live_quality_last": "strong", "shadow_tier_last": "routine",
                      "live_side": "llm"}],
        alert_rows=_alert_rows(_FRI, recent_high=3, prior_high=3))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert out["triggers"] == []
    # and an ALREADY-announced miss stays announced-once (dedupe row present)
    conn = _FakeConn(
        shadow_rows=[{"scan_date": date(2026, 8, 19), "ticker": "MRNA",
                      "live_quality_last": "strong", "shadow_tier_last": "routine",
                      "live_side": "lattice"}],
        alert_rows=_alert_rows(_FRI, recent_high=3, prior_high=3),
        dedupe_hit=True)
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert out["triggers"] == []


@pytest.mark.asyncio
async def test_trigger_b_high_collapse_names_the_numbers(monkeypatch):
    """A genuine halving, with the flip well outside the whole lookback span (self-healed —
    see _lattice_era_windows), MUST still fire exactly as before the era-scope fix."""
    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=1, prior_high=4),
                      flip_date=date(2026, 1, 1))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert [t["kind"] for t in out["triggers"]] == ["high_conversion_drop"]
    t = out["triggers"][0]
    # a FLAT tape makes the supply-normalised statistic identical to the old per-day one —
    # the halving is still a halving, and the raw per-day figures are still reported.
    assert t["recent_avg"] == 1.0 and t["prior_avg"] == 4.0 and t["drop_pct"] == 75.0
    assert t["recent_supply"] > 0 and t["prior_supply"] > 0
    assert t["flip_date"] == "2026-01-01" and t["flip_date_source"] == "shadow_acting_record"
    msg = tg.call_args[0][0]
    assert "CONVERTING LESS OF WHAT THE TAPE OFFERS" in msg
    assert "75.0%" in msg and "2026-01-01" in msg
    assert hc._LATTICE_REVERT_SQL in msg


# ── the actual 2026-08-24 incident: collapse predates the flip ─────────────────────────

# The real prod HIGH-alert series that misfired trigger (b) on 2026-08-24 (see the module
# header comment above _LATTICE_FLIP_DATE_FALLBACK). The collapse starts 08-17, five trading
# days before the flip (08-22, a Saturday -- the first trading day it could act on is 08-24).
# 08-03 is filled in at a level consistent with the rest of that week (not verified prod data)
# purely so the 30-trading-day prior window has no phantom zero-count day at its edge.
_REAL_INCIDENT_HIGH = {
    date(2026, 8, 3): 9,
    date(2026, 8, 4): 10, date(2026, 8, 5): 8, date(2026, 8, 6): 8, date(2026, 8, 7): 10,
    date(2026, 8, 10): 4, date(2026, 8, 11): 4, date(2026, 8, 12): 6, date(2026, 8, 13): 5,
    date(2026, 8, 14): 4,
    date(2026, 8, 17): 1, date(2026, 8, 18): 1, date(2026, 8, 19): 3, date(2026, 8, 20): 2,
    date(2026, 8, 21): 1,
    date(2026, 8, 24): 0,   # "today had zero alerts" — the only trading day so far ON/AFTER
                            # the flip, per the incident description
}
_REAL_INCIDENT_ROWS = [{"alert_date": d, "n": n, "high_n": n}
                       for d, n in _REAL_INCIDENT_HIGH.items()]


@pytest.mark.asyncio
async def test_trigger_b_does_not_fire_on_the_real_pre_flip_collapse(monkeypatch):
    """The actual 2026-08-24 incident, reproduced: the collapse is entirely pre-flip and
    there is only 1 post-flip trading day so far (today, zero alerts) -- must NOT fire, and
    the fix must not have silently made the OLD (unscoped) code fail to fire on the same
    numbers -- prove the old math genuinely would have (the bug was real, not a test
    artifact). Also pins the interaction requirement 5 flags: today's zero alerts must NOT
    trip trigger (c) alone -- 08-21 (the prior trading day) was non-zero, so (c) correctly
    waits for a SECOND consecutive silent day, exactly as it must."""
    audit, tg = _patch_common(monkeypatch)
    today = date(2026, 8, 24)   # Monday -- the first trading day on/after the Sat 08-22 flip
    flip = date(2026, 8, 22)
    conn = _FakeConn(alert_rows=_REAL_INCIDENT_ROWS, flip_date=flip)
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=today)
    assert all(t["kind"] != "high_conversion_drop" for t in out["triggers"])
    assert all(t["kind"] != "zero_alert_days" for t in out["triggers"])   # only 1 silent day
    tg_calls = [c.args[0] for c in tg.call_args_list]
    assert not any("CONVERTING LESS OF WHAT THE TAPE OFFERS" in m for m in tg_calls)

    # the OLD, unscoped math on these exact numbers WOULD have fired -- this is what tonight's
    # alert said before the fix (the transcript's "66.6% drop"), confirming the fix changed a
    # real false positive, not a no-op.
    old_recent = hc._lattice_trading_days(today, hc._LATTICE_RECENT_DAYS)
    old_prior = [d for d in hc._lattice_trading_days(
        today, hc._LATTICE_RECENT_DAYS + hc._LATTICE_PRIOR_DAYS) if d not in set(old_recent)]
    old_recent_avg = sum(_REAL_INCIDENT_HIGH.get(d, 0) for d in old_recent) / len(old_recent)
    old_prior_avg = sum(_REAL_INCIDENT_HIGH.get(d, 0) for d in old_prior) / len(old_prior)
    assert hc._evaluate_lattice_high_drop(old_recent_avg, old_prior_avg) is not None


@pytest.mark.asyncio
async def test_trigger_b_suppressed_when_too_few_post_flip_trading_days(monkeypatch):
    """Isolates the floor from window-scoping: a real-looking collapsed ratio in the 3
    trading days since the flip must NOT fire -- there simply isn't enough post-flip data
    yet to judge a halving (below _LATTICE_MIN_POST_FLIP_TRADING_DAYS)."""
    audit, tg = _patch_common(monkeypatch)
    flip = date(2026, 8, 10)     # Monday
    today = date(2026, 8, 12)    # Wednesday -- 3 trading days on/after the flip
    rows = []
    d, i = today, 0
    while i < hc._LATTICE_RECENT_DAYS + hc._LATTICE_PRIOR_DAYS:
        if _weekday(d):
            high = 1 if d >= flip else 4   # a real-looking halving if it were allowed to fire
            rows.append({"alert_date": d, "n": high, "high_n": high})
        d -= timedelta(days=1)
        i += 1
    conn = _FakeConn(alert_rows=rows, flip_date=flip)
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=today)
    assert all(t["kind"] != "high_conversion_drop" for t in out["triggers"])


@pytest.mark.asyncio
async def test_trigger_b_not_blocked_by_a_holiday_week_once_the_flip_is_old(monkeypatch):
    """The post-flip floor must gate ONLY an ACTUAL partial post-flip window (scoped=True at
    the call site). A routine NYSE holiday week -- _lattice_trading_days(day, 7) returns 4,
    not 5, ~9-10x/yr -- must never permanently silence trigger (b) once the flip is old
    enough that _lattice_era_windows returns scoped=False. Without the scoped guard at the
    call site, this genuine halving would go unreported every holiday week, forever."""
    audit, tg = _patch_common(monkeypatch)
    today = date(2026, 9, 4)      # Friday
    holiday = date(2026, 9, 3)    # a Thursday inside the recent-7-day window, dropped as a
                                  # weekday holiday so the recent trading-day count is 4

    def _is_td(d):
        return _weekday(d) and d != holiday

    monkeypatch.setattr(hc, "_is_trading_day", _is_td)
    flip = date(2026, 1, 1)       # long before the whole lookback span -> scoped=False
    conn = _FakeConn(alert_rows=_alert_rows(today, recent_high=1, prior_high=4),
                      flip_date=flip)
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=today)
    assert [t["kind"] for t in out["triggers"]] == ["high_conversion_drop"]
    assert out["triggers"][0]["recent_days"] == 4


@pytest.mark.asyncio
async def test_trigger_c_two_consecutive_zero_alert_trading_days(monkeypatch):
    audit, tg = _patch_common(monkeypatch)
    # last 2 trading days silent; earlier recent days busy enough that (b) stays quiet
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=4, prior_high=4, zero_last_n=2))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert [t["kind"] for t in out["triggers"]] == ["zero_alert_days"]
    assert out["triggers"][0]["days"] == ["2026-08-21", "2026-08-20"]
    msg = tg.call_args[0][0]
    assert "ZERO-ALERT DAYS" in msg and "2026-08-21" in msg
    assert hc._LATTICE_REVERT_SQL in msg


@pytest.mark.asyncio
async def test_trigger_c_still_fires_with_a_live_post_flip_era(monkeypatch):
    """Requirement 5, pinned directly: trigger (c) is untouched by the era-scope fix, checked
    with `today` actually INSIDE the post-flip era (unlike the test above, whose `today`
    predates even the hardcoded fallback flip date, so trigger (b) is inert throughout it and
    never exercises the era-scoping code alongside (c) in the same run)."""
    audit, tg = _patch_common(monkeypatch)
    today = date(2026, 8, 25)   # Tuesday, 1 trading day after the flip's first acting day
    flip = date(2026, 8, 22)
    conn = _FakeConn(alert_rows=_alert_rows(today, recent_high=4, prior_high=4, zero_last_n=2),
                      flip_date=flip)
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=today)
    assert [t["kind"] for t in out["triggers"]] == ["zero_alert_days"]
    assert out["triggers"][0]["days"] == ["2026-08-25", "2026-08-24"]


@pytest.mark.asyncio
async def test_one_zero_day_does_not_fire_trigger_c(monkeypatch):
    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=4, prior_high=4, zero_last_n=1))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert all(t["kind"] != "zero_alert_days" for t in out["triggers"])


@pytest.mark.asyncio
async def test_unreachable_fixture_is_loud_never_silent(monkeypatch):
    """P1 trigger going DARK is itself alert-worthy — a warning fires (3-day dedupe),
    an error is recorded, and the other two triggers still run."""
    audit, tg = _patch_common(monkeypatch)
    monkeypatch.setattr(hc, "_load_must_not_miss_members", lambda: None)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=3, prior_high=3))
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert {"fixture": "unreachable"} in out["errors"]
    assert out["triggers"] == []
    warn = tg.call_args[0][0]
    assert "DARK" in warn and "must_not_miss" in warn


def test_revert_sql_targets_the_one_flag():
    """The command the operator gets must flip exactly the `catalyst_tier_lattice`
    safeguard row the runtime toggle reads — the documented #400a idiom."""
    assert "'catalyst_tier_lattice'" in hc._LATTICE_REVERT_SQL
    assert "'global'" in hc._LATTICE_REVERT_SQL and "'off'" in hc._LATTICE_REVERT_SQL
    assert "ON CONFLICT (safeguard, account_mode)" in hc._LATTICE_REVERT_SQL


# ── trigger (b) SUPPLY NORMALISATION (2026-08-26) ──────────────────────────────────────
#
# Alert volume is a function of SUPPLY, and supply is seasonal (operator, after the second
# false fire in two days: "we are at the tail end of earnings season, so gap-ups (and downs)
# shrink naturally"). These tests pin the redefinition: the trigger fires on a fall in the
# share of available gap supply we CONVERT, never on a fall in raw alert count. Nothing here
# encodes an expected EP rate — the operator explicitly forbade assuming one.
#
# Real production series, 2026-07-06 -> 2026-08-24, captured once and read many
# (scripts/probes/_alertdrop_capture_out.psv, Q10 alert counts + Q5 tape breadth; the study is
# docs/analysis/alert_volume_collapse_2026-08-24.md). HIGH alerts, live source only, and the
# number of stocks whose open gapped >=10% past the D-1 universe floors that day.
_REAL_HIGH = {
    (7, 6): 1, (7, 7): 1, (7, 8): 1, (7, 9): 0, (7, 10): 2,
    (7, 13): 0, (7, 14): 2, (7, 15): 3, (7, 16): 0, (7, 17): 0,
    (7, 20): 2, (7, 21): 1, (7, 22): 2, (7, 23): 1, (7, 24): 2,
    (7, 27): 2, (7, 28): 1, (7, 29): 2, (7, 30): 7, (7, 31): 6,
    (8, 3): 2, (8, 4): 10, (8, 5): 8, (8, 6): 8, (8, 7): 10,
    (8, 10): 4, (8, 11): 4, (8, 12): 6, (8, 13): 5, (8, 14): 4,
    (8, 17): 1, (8, 18): 1, (8, 19): 3, (8, 20): 2, (8, 21): 1,
    (8, 24): 0,
}
_REAL_SUPPLY = {
    (7, 6): 27, (7, 7): 10, (7, 8): 5, (7, 9): 47, (7, 10): 16,
    (7, 13): 5, (7, 14): 49, (7, 15): 10, (7, 16): 14, (7, 17): 11,
    (7, 20): 17, (7, 21): 56, (7, 22): 8, (7, 23): 12, (7, 24): 9,
    (7, 27): 19, (7, 28): 14, (7, 29): 17, (7, 30): 133, (7, 31): 82,
    (8, 3): 8, (8, 4): 79, (8, 5): 38, (8, 6): 46, (8, 7): 60,
    (8, 10): 10, (8, 11): 17, (8, 12): 82, (8, 13): 19, (8, 14): 24,
    (8, 17): 11, (8, 18): 16, (8, 19): 21, (8, 20): 36, (8, 21): 25,
    (8, 24): 19,
}
_REAL_HIGH_D = {date(2026, m, d): n for (m, d), n in _REAL_HIGH.items()}
_REAL_SUPPLY_D = {date(2026, m, d): n for (m, d), n in _REAL_SUPPLY.items()}
_REAL_ROWS = [{"alert_date": d, "n": n, "high_n": n} for d, n in _REAL_HIGH_D.items()]
_OLD_FLIP = date(2026, 1, 1)   # flip far outside the lookback -> era scoping self-heals off,
                               # so the STATISTIC itself is what these tests judge


@pytest.mark.asyncio
async def test_trigger_b_stays_quiet_on_the_real_earnings_trough(monkeypatch):
    """THE FALSE FIRE THIS CHANGE EXISTS FOR. On the real 2026-08-24 series the raw
    per-trading-day form fires (1.4 alerts/day vs 4.19 — the alert that actually went out),
    but the tape had thinned from ~36 to ~23 gapping stocks a day and our conversion of it
    barely moved. The supply-normalised form must NOT fire — and the old math on the SAME
    numbers must, or this test proves nothing."""
    audit, tg = _patch_common(monkeypatch)
    today = date(2026, 8, 24)
    conn = _FakeConn(alert_rows=_REAL_ROWS, flip_date=_OLD_FLIP, supply=_REAL_SUPPLY_D)
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=today)
    assert all(t["kind"] != "high_conversion_drop" for t in out["triggers"])
    assert out["errors"] == []          # quiet because it MEASURED, not because it stalled

    recent = hc._lattice_trading_days(today, hc._LATTICE_RECENT_DAYS)
    prior = [d for d in hc._lattice_trading_days(
        today, hc._LATTICE_RECENT_DAYS + hc._LATTICE_PRIOR_DAYS) if d not in set(recent)]
    # the OLD statistic on these exact numbers WOULD have fired
    assert hc._evaluate_lattice_high_drop(
        sum(_REAL_HIGH_D.get(d, 0) for d in recent) / len(recent),
        sum(_REAL_HIGH_D.get(d, 0) for d in prior) / len(prior)) is not None
    # ...and the new one does not, by 1 HIGH alert — it is NOT a mute
    r_sup = sum(_REAL_SUPPLY_D[d] for d in recent)
    p_rate = (sum(_REAL_HIGH_D.get(d, 0) for d in prior)
              / sum(_REAL_SUPPLY_D[d] for d in prior))
    assert sum(_REAL_HIGH_D.get(d, 0) for d in recent) == 7
    assert int(hc._LATTICE_HIGH_DROP_FRACTION * p_rate * r_sup) == 6   # 7 would have to be <=6


@pytest.mark.asyncio
async def test_trigger_b_fires_when_conversion_breaks_on_the_same_thin_tape(monkeypatch):
    """The property that matters: a genuinely broken funnel still trips it on a THIN tape.
    Identical supply to the test above (the real, thinned 2026-08 tape) — only our alerts are
    gone. Must fire, or the change is a mute dressed as a fix."""
    audit, tg = _patch_common(monkeypatch)
    today = date(2026, 8, 24)
    broken = dict(_REAL_HIGH_D)
    for d in (date(2026, 8, 18), date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 21)):
        broken[d] = 0
    rows = [{"alert_date": d, "n": n, "high_n": n} for d, n in broken.items()]
    conn = _FakeConn(alert_rows=rows, flip_date=_OLD_FLIP, supply=_REAL_SUPPLY_D)
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=today)
    t = [x for x in out["triggers"] if x["kind"] == "high_conversion_drop"]
    assert t, "a conversion collapse on a thin tape MUST fire"
    assert t[0]["recent_high_n"] == 0 and t[0]["recent_supply"] == 117
    assert t[0]["prior_high_n"] == 88 and t[0]["prior_supply"] == 761
    assert t[0]["drop_pct"] == 100.0
    msg = tg.call_args[0][0]
    assert "CONVERTING LESS OF WHAT THE TAPE OFFERS" in msg
    assert "117" in msg and "761" in msg          # the tape is named, not hidden
    assert hc._LATTICE_REVERT_SQL in msg


@pytest.mark.asyncio
async def test_a_supply_only_collapse_does_not_fire_but_a_conversion_one_does(monkeypatch):
    """The clean A/B, and the whole point of the change. The ALERT series is identical in
    both halves — 4 HIGH/day falling to 1 HIGH/day, a 75% raw collapse that the old form
    fires on either way. Only the tape differs. Tape falls 75% too -> conversion is flat ->
    silent. Tape unchanged -> conversion falls 75% -> fires."""
    audit, tg = _patch_common(monkeypatch)
    span = hc._lattice_trading_days(_FRI, hc._LATTICE_RECENT_DAYS + hc._LATTICE_PRIOR_DAYS)
    recent = set(hc._lattice_trading_days(_FRI, hc._LATTICE_RECENT_DAYS))

    thin = {d: (10 if d in recent else 40) for d in span}
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=1, prior_high=4),
                      flip_date=_OLD_FLIP, supply=thin)
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert all(t["kind"] != "high_conversion_drop" for t in out["triggers"])

    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=1, prior_high=4),
                      flip_date=_OLD_FLIP, supply={d: 40 for d in span})
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert [t["kind"] for t in out["triggers"]] == ["high_conversion_drop"]
    assert out["triggers"][0]["drop_pct"] == 75.0


@pytest.mark.asyncio
async def test_the_2026_08_22_scan_log_logging_boundary_cannot_create_a_signal(monkeypatch):
    """#570 made the two silent D-1 universe floors log a row from 2026-08-22, so
    `mi_ep_scan_log`'s distinct-ticker count jumps ~18/day to ~222/day across that date for
    logging reasons alone. The denominator must be immune: the monitor never reads the scan
    log at all, and the supply query it does run applies the $5 / 50k-share universe floors
    inside SQL, so the sub-$5 names that class consists of are excluded identically on BOTH
    sides of the boundary."""
    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=3, prior_high=3),
                      flip_date=_OLD_FLIP)
    await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert not any("mi_ep_scan_log" in s for s in conn.saw_sql)
    supply_sql = [s for s in conn.saw_sql if "mi_daily_closes" in s]
    assert len(supply_sql) == 1
    assert "prev_close >= $4" in supply_sql[0] and "prev_volume >= $5" in supply_sql[0]
    assert hc._LATTICE_SUPPLY_MIN_PREV_CLOSE == 5.0
    assert hc._LATTICE_SUPPLY_MIN_PREV_VOLUME == 50_000


@pytest.mark.asyncio
async def test_trigger_b_suppressed_when_the_tape_cannot_be_measured(monkeypatch):
    """No denominator -> no conversion judgement. Silent (and recorded as an error) rather
    than falling back to raw counts: falling back is the false fire this change removes."""
    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=1, prior_high=4),
                      flip_date=_OLD_FLIP, supply={})
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert out["triggers"] == []
    assert {"supply": "unmeasurable"} in out["errors"]
    tg.assert_not_called()


@pytest.mark.asyncio
async def test_a_day_with_no_supply_row_is_dropped_from_BOTH_windows(monkeypatch):
    """An unmeasured day must never be read as zero supply — that would inflate the other
    window's rate and manufacture a fire. Here the whole RECENT window is unmeasured while
    the alerts on it collapse; with 'absent == 0 supply' this would fire."""
    audit, tg = _patch_common(monkeypatch)
    span = hc._lattice_trading_days(_FRI, hc._LATTICE_RECENT_DAYS + hc._LATTICE_PRIOR_DAYS)
    recent = set(hc._lattice_trading_days(_FRI, hc._LATTICE_RECENT_DAYS))
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=0, prior_high=4),
                      flip_date=_OLD_FLIP,
                      supply={d: 30 for d in span if d not in recent})
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert all(t["kind"] != "high_conversion_drop" for t in out["triggers"])
    assert {"supply": "unmeasurable"} in out["errors"]


@pytest.mark.asyncio
async def test_a_partial_close_ingest_is_not_a_measured_day():
    """A day whose mi_daily_closes rows are missing their open price would score as zero
    supply and inflate the other window's rate. It must be dropped as UNMEASURED instead."""
    class _Conn:
        async def fetch(self, sql, *args):
            return [{"trade_date": date(2026, 8, 20), "rows_with_open": 12_300, "supply": 36},
                    {"trade_date": date(2026, 8, 21), "rows_with_open": 12, "supply": 0}]

    got = await hc._lattice_supply_by_date(_Conn(), date(2026, 8, 1), date(2026, 8, 21))
    assert got == {date(2026, 8, 20): 36}


@pytest.mark.asyncio
async def test_supply_read_failure_is_empty_not_an_exception():
    class _Conn:
        async def fetch(self, sql, *args):
            raise RuntimeError("boom")

    assert await hc._lattice_supply_by_date(_Conn(), date(2026, 8, 1), date(2026, 8, 21)) == {}


@pytest.mark.asyncio
async def test_trigger_c_message_carries_the_tape_context_but_still_fires(monkeypatch):
    """Trigger (c) is deliberately NOT supply-normalised — two silent days on a live money
    path is worth a look even when the tape is the cause. What changed is that the message now
    carries each day's gap supply and the trailing conversion rate, so it can be dismissed at
    a glance. It must still fire, and it must not print a forecast."""
    audit, tg = _patch_common(monkeypatch)
    span = hc._lattice_trading_days(_FRI, hc._LATTICE_RECENT_DAYS + hc._LATTICE_PRIOR_DAYS)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=4, prior_high=4, zero_last_n=2),
                      flip_date=_OLD_FLIP, supply={d: 30 for d in span})
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    t = [x for x in out["triggers"] if x["kind"] == "zero_alert_days"]
    assert t and t[0]["days"] == ["2026-08-21", "2026-08-20"]
    assert t[0]["supply"] == [30, 30]
    assert t[0]["trailing_per_100"] is not None
    msg = tg.call_args[0][0]
    assert "ZERO-ALERT DAYS" in msg and "opened" in msg.lower()
    assert "per 100" in msg and "not a verdict" in msg
    assert hc._LATTICE_REVERT_SQL in msg


@pytest.mark.asyncio
async def test_trigger_c_still_fires_when_the_tape_is_unmeasurable(monkeypatch):
    """The one thing trigger (c) must never do is go quiet. No supply data -> it still fires,
    with the context marked unknown rather than omitted."""
    audit, tg = _patch_common(monkeypatch)
    conn = _FakeConn(alert_rows=_alert_rows(_FRI, recent_high=4, prior_high=4, zero_last_n=2),
                      flip_date=_OLD_FLIP, supply={})
    out = await hc.run_catalyst_lattice_monitor(conn=conn, today=_FRI)
    assert [t["kind"] for t in out["triggers"]] == ["zero_alert_days"]
    assert out["triggers"][0]["supply"] == [None, None]
    assert "?" in tg.call_args[0][0]
