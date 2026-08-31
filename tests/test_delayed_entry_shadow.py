"""#327 delayed-entry watch lane tests (2026-08-30). Pure pattern core (to_rth_5min /
evaluate_session_minute / evaluate_session_daily / session_needs_minutes /
compute_screen_member) + the orchestration half with module-level db functions
monkeypatched. Every assertion checks a computed VALUE against the bars it came from,
never a label string. THE LINE: this recorder writes only mi_delayed_entry_watch /
mi_delayed_entry_trigger (+ mi_audit_log via log_audit_event) and must NEVER fabricate
a fill — both pinned below.
"""
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import delayed_entry_shadow as des

_ET = ZoneInfo("America/New_York")


def _ms(y, m, d, hh, mm):
    return int(datetime(y, m, d, hh, mm, tzinfo=_ET).timestamp() * 1000)


def _b5(m, o, h, l, c):
    return {"m": m, "o": o, "h": h, "l": l, "c": c}


# ── to_rth_5min ───────────────────────────────────────────────────────────────────────


def test_to_rth_5min_buckets_and_ohlc():
    """Three 1-min bars, two in the 9:30 bucket: high=max, low=min, close=the LAST
    minute's close; the 9:35 bar opens its own bucket."""
    raw = [
        {"t": _ms(2026, 8, 28, 9, 30), "o": 10.0, "h": 10.5, "l": 9.8, "c": 10.2},
        {"t": _ms(2026, 8, 28, 9, 34), "o": 10.2, "h": 10.6, "l": 10.0, "c": 10.4},
        {"t": _ms(2026, 8, 28, 9, 35), "o": 10.4, "h": 10.9, "l": 10.3, "c": 10.8},
    ]
    out = des.to_rth_5min(raw, date(2026, 8, 28))
    assert [b["m"] for b in out] == [570, 575]
    assert out[0]["h"] == 10.6 and out[0]["l"] == 9.8 and out[0]["c"] == 10.4
    assert out[1]["c"] == 10.8


def test_to_rth_5min_keeps_a_winter_late_bar_the_utc4_bug_would_drop():
    """MUTATION TARGET (Stage 0 D11): a hard-coded UTC-4 conversion shifts every EST
    bar one hour. A 15:59 ET bar on a JANUARY day is 20:59 UTC; under UTC-4 it reads
    as 16:59 'ET' and falls outside RTH — silently dropped. ZoneInfo keeps it."""
    raw = [{"t": _ms(2026, 1, 15, 15, 59), "o": 5.0, "h": 5.1, "l": 4.9, "c": 5.05}]
    out = des.to_rth_5min(raw, date(2026, 1, 15))
    assert len(out) == 1
    assert out[0]["m"] == 15 * 60 + 55  # the 15:55 bucket


def test_to_rth_5min_excludes_premarket_and_other_days():
    raw = [
        {"t": _ms(2026, 8, 28, 9, 15), "o": 1, "h": 1, "l": 1, "c": 1},   # pre-market
        {"t": _ms(2026, 8, 27, 10, 0), "o": 1, "h": 1, "l": 1, "c": 1},   # wrong day
        {"t": _ms(2026, 8, 28, 16, 0), "o": 1, "h": 1, "l": 1, "c": 1},   # post-close
    ]
    assert des.to_rth_5min(raw, date(2026, 8, 28)) == []


# ── rung 1: ep_low_reclaim ────────────────────────────────────────────────────────────


def test_ep_low_reclaim_stop_is_lowest_low_since_undercut_and_width_matches_bars():
    """The REQUIRED stop-width test: undercut at 9.4, a LOWER low 9.2 two bars later,
    reclaim close 10.0 -> stop must be 9.2 (not the undercut bar's 9.4) and
    stop_width_pct must equal (10.0 - 9.2) / 10.0 * 100 = 8.0 exactly from the bars."""
    bars = [
        _b5(570, 10.0, 10.2, 9.4, 9.5),    # undercuts gap_low 9.8
        _b5(575, 9.5, 9.7, 9.2, 9.6),      # the campaign low
        _b5(580, 9.6, 10.1, 9.5, 10.0),    # 5-min close back above 9.8 -> fire
    ]
    res = des.evaluate_session_minute(
        bars, gap_low=9.8, gap_close=11.0, gap_high=12.0,
        prior_session_low=9.9, state=des.new_state())
    assert len(res["fires"]) == 1
    f = res["fires"][0]
    assert f["rung"] == "ep_low_reclaim"
    assert f["entry"] == 10.0 and f["stop"] == 9.2 and f["fire_minute"] == 580
    assert des.stop_width_pct(f["entry"], f["stop"]) == pytest.approx(8.0)


def test_ep_low_reclaim_stop_carries_a_prior_session_low():
    """Undercut happened YESTERDAY with a 9.0 low (carried state); today never trades
    that low. The stop must still be 9.0 — the lowest low since the undercut spans
    sessions, not just the fire day's bars."""
    state = des.new_state()
    state.update({"undercut_seen": True, "low_since_undercut": 9.0})
    bars = [_b5(570, 9.6, 10.1, 9.5, 10.0)]   # reclaim on the first bar today
    res = des.evaluate_session_minute(
        bars, gap_low=9.8, gap_close=11.0, gap_high=12.0,
        prior_session_low=9.5, state=state)
    assert res["fires"][0]["stop"] == 9.0


def test_ep_low_reclaim_fires_once_only():
    state = des.new_state()
    state.update({"undercut_seen": True, "low_since_undercut": 9.0,
                  "fired_ep_low_reclaim": True})
    bars = [_b5(570, 9.6, 10.1, 9.5, 10.0)]
    res = des.evaluate_session_minute(
        bars, gap_low=9.8, gap_close=11.0, gap_high=12.0,
        prior_session_low=9.5, state=state)
    assert res["fires"] == []


# ── rung 2: ep_close_reclaim ──────────────────────────────────────────────────────────


def test_ep_close_reclaim_fires_with_dip_low_as_stop():
    bars = [
        _b5(570, 11.2, 11.3, 10.6, 10.7),   # dips under gap_close 11.0 (never near low 9.8)
        _b5(575, 10.7, 10.8, 10.5, 10.6),   # dip low 10.5
        _b5(580, 10.6, 11.2, 10.6, 11.1),   # close back above 11.0 -> fire
    ]
    res = des.evaluate_session_minute(
        bars, gap_low=9.8, gap_close=11.0, gap_high=12.0,
        prior_session_low=10.9, state=des.new_state())
    fires = {f["rung"]: f for f in res["fires"]}
    assert set(fires) == {"ep_close_reclaim"}
    assert fires["ep_close_reclaim"]["entry"] == 11.1
    assert fires["ep_close_reclaim"]["stop"] == 10.5


def test_ep_close_reclaim_killed_by_same_bar_undercut_of_the_ep_low():
    """MUTATION TARGET (the pess stop-first fold): a single bar undercuts the EP-day
    LOW (l=9.5 < 9.8) AND closes back above the EP-day CLOSE (c=11.1 > 11.0). Within-bar
    ordering is unknowable, so the low folds FIRST: the name reached the EP low, and
    ep_close_reclaim ('it never reaches that low') must NOT fire. The shape now belongs
    to ep_low_reclaim — which DOES fire on this bar's close above the EP low."""
    bars = [_b5(570, 11.2, 11.3, 9.5, 11.1)]
    res = des.evaluate_session_minute(
        bars, gap_low=9.8, gap_close=11.0, gap_high=12.0,
        prior_session_low=10.9, state=des.new_state())
    rungs = [f["rung"] for f in res["fires"]]
    assert "ep_close_reclaim" not in rungs
    assert rungs == ["ep_low_reclaim"]
    assert res["state"]["undercut_seen"] is True


def test_ep_close_reclaim_dead_once_undercut_seen_in_a_prior_session():
    state = des.new_state()
    state.update({"undercut_seen": True, "low_since_undercut": 9.0,
                  "dipped_below_close_seen": True, "low_of_dip": 9.0,
                  "fired_ep_low_reclaim": True})
    bars = [_b5(570, 10.9, 11.2, 10.8, 11.1)]   # close back above gap_close
    res = des.evaluate_session_minute(
        bars, gap_low=9.8, gap_close=11.0, gap_high=12.0,
        prior_session_low=10.0, state=state)
    assert res["fires"] == []


# ── rung 3: ep_high_break ─────────────────────────────────────────────────────────────


def test_ep_high_break_daily_unambiguous_fire_prices():
    """Whole daily bar at/above the EP close, high touches the EP high: buy = the LEVEL
    (gap_high), stop = the prior session's low — no minute bars needed."""
    res = des.evaluate_session_daily(
        12.3, 11.4, gap_low=9.8, gap_close=11.0, gap_high=12.0,
        prior_session_low=11.1, state=des.new_state())
    assert len(res["fires"]) == 1
    f = res["fires"][0]
    assert f["rung"] == "ep_high_break"
    assert f["entry"] == 12.0 and f["stop"] == 11.1 and f["fire_minute"] is None
    assert res["state"]["gap_high_exceeded"] is True


def test_ep_high_break_not_fired_daily_when_the_bar_also_dipped():
    """day_low < gap_close on the break day: intraday ordering is unknowable at daily
    grade, so the daily path must NOT fire (the walker fetches minutes instead —
    session_needs_minutes flags exactly this shape)."""
    res = des.evaluate_session_daily(
        12.3, 10.6, gap_low=9.8, gap_close=11.0, gap_high=12.0,
        prior_session_low=11.1, state=des.new_state())
    assert res["fires"] == []
    assert des.session_needs_minutes(
        12.3, 10.6, gap_low=9.8, gap_close=11.0, gap_high=12.0,
        state=des.new_state()) is True


def test_ep_high_break_minute_blocked_when_the_dip_comes_first():
    """Minute resolution, dip bar BEFORE the break bar: the pullback disqualifies
    'never pulls back' — no breakout fire, ever, in that session."""
    bars = [
        _b5(570, 11.5, 11.6, 10.9, 11.2),   # dips under gap_close first
        _b5(575, 11.2, 12.1, 11.2, 12.0),   # then pushes above gap_high
    ]
    res = des.evaluate_session_minute(
        bars, gap_low=9.8, gap_close=11.0, gap_high=12.0,
        prior_session_low=11.0, state=des.new_state())
    assert all(f["rung"] != "ep_high_break" for f in res["fires"])


def test_ep_high_break_abstains_without_a_prior_session_low():
    """No prior-session low in hand -> the fire is NOT recorded with a guessed stop;
    the evaluator flags it so the caller marks the session unscoreable and retries."""
    res = des.evaluate_session_daily(
        12.3, 11.4, gap_low=9.8, gap_close=11.0, gap_high=12.0,
        prior_session_low=None, state=des.new_state())
    assert res["fires"] == []
    assert res["p3_needs_prior_low"] is True
    assert res["state"]["fired_ep_high_break"] is False  # still eligible on retry


def test_stop_width_pct_records_degenerate_geometry_as_negative():
    """A prior-session low ABOVE the EP-day high (runaway tape) gives a stop above the
    entry: recorded as a NEGATIVE width, never dropped — dropping it would
    survivorship-filter the fire population on geometry."""
    assert des.stop_width_pct(12.0, 12.6) == pytest.approx(-5.0)
    assert des.stop_width_pct(0.0, 1.0) is None


# ── screen stamp + ADR ────────────────────────────────────────────────────────────────


def test_screen_member_true_false_and_null():
    ok = dict(gap_pct=9.0, prev_close=6.0, ep_dollar_volume=60e6,
              extension_pct=30.0, catalyst_grade="strong")
    assert des.compute_screen_member(**ok) is True
    assert des.compute_screen_member(**{**ok, "catalyst_grade": "routine"}) is False
    assert des.compute_screen_member(**{**ok, "gap_pct": 7.9}) is False
    assert des.compute_screen_member(**{**ok, "extension_pct": 51.0}) is False
    # a missing component is UNKNOWN, never guessed
    assert des.compute_screen_member(**{**ok, "extension_pct": None}) is None


def test_compute_adr20_uses_at_most_20_bars_and_reports_n():
    bars = [{"high_price": 11.0, "low_price": 10.0, "close": 10.0}] * 25
    adr, n = des.compute_adr20(bars)
    assert n == 20
    assert adr == pytest.approx(10.0)   # (11-10)/10 * 100
    assert des.compute_adr20([]) == (None, 0)


# ── orchestration (module-level db functions monkeypatched) ───────────────────────────


_EP = date(2026, 8, 24)      # Monday — the EP day
_THU = date(2026, 8, 27)
_FRI = date(2026, 8, 28)


def _member(**over):
    m = {
        "ticker": "TST", "ep_date": _EP, "session_date": _THU, "session_idx": 3,
        "first_unscoreable": None, "pattern_version": "v1",
        "gap_day_low": 9.8, "gap_day_close": 11.0, "gap_day_high": 12.0,
        "gap_day_volume": 5_000_000,
        "undercut_seen": True, "low_since_undercut": 9.2,
        "dipped_below_close_seen": True, "low_of_dip": 9.2,
        "gap_high_exceeded": False,
        "fired_ep_low_reclaim": False, "fired_ep_close_reclaim": False,
        "fired_ep_high_break": False,
        "eval_status": "complete", "unscoreable_reason": None,
        "ep_score": 62.0, "catalyst_grade": "strong", "in_active_theme": True,
        "gap_pct": 9.5, "prev_close": 10.0, "ep_dollar_volume": 55e6,
        "extension_pct": 20.0, "screen_member": True, "screen_version": "screen_v1",
    }
    m.update(over)
    return m


def _daily(d, o, h, l, c, v=1_000_000):
    return {"trade_date": d, "open_price": o, "high_price": h, "low_price": l,
            "close": c, "volume": v}


def _wire(monkeypatch, *, member, window, minute_bars, upsert_raises=False):
    """Wire the walker's collaborators. Returns (watch_writes, trigger_writes, audits)."""
    watch_writes, trigger_writes, audits = [], [], []

    async def _no_seeds(since, until):
        return []

    async def _lane(min_ep, lane_sessions):
        return [member]

    async def _window(ticker, start, end):
        return [b for b in window if start <= b["trade_date"] <= end]

    async def _daily_bar(ticker, day):
        for b in window:
            if b["trade_date"] == day:
                return (b["open_price"], b["high_price"], b["low_price"], b["close"], "daily")
        return (None, None, None, None, None)

    async def _minutes(ticker, day):
        return minute_bars

    async def _upsert(row):
        if upsert_raises:
            raise RuntimeError("boom: watch write failed")
        watch_writes.append(row)

    async def _trigger(row):
        trigger_writes.append(row)
        return True

    async def _unsc_count(ticker, ep, before):
        return 0

    async def _audit(event_type, summary, detail=""):
        audits.append((event_type, summary))

    async def _watch_row(ticker, ep, session):
        return None

    async def _no_open_triggers():
        return []

    async def _settle(row_id, fields):
        raise AssertionError("settle must not be called with no open triggers")

    monkeypatch.setattr(des, "get_delayed_entry_open_triggers", _no_open_triggers)
    monkeypatch.setattr(des, "settle_delayed_entry_trigger", _settle)
    monkeypatch.setattr(des, "get_delayed_entry_seed_candidates", _no_seeds)
    monkeypatch.setattr(des, "get_delayed_entry_open_lane", _lane)
    monkeypatch.setattr(des, "get_delayed_entry_daily_window", _window)
    monkeypatch.setattr(des, "get_delayed_entry_daily_bar", _daily_bar)
    monkeypatch.setattr(des, "_fetch_minute_5", _minutes)
    monkeypatch.setattr(des, "upsert_delayed_entry_watch", _upsert)
    monkeypatch.setattr(des, "insert_delayed_entry_trigger", _trigger)
    monkeypatch.setattr(des, "count_delayed_entry_unscoreable", _unsc_count)
    monkeypatch.setattr(des, "log_audit_event", _audit)
    monkeypatch.setattr(des, "get_delayed_entry_watch_row", _watch_row)
    return watch_writes, trigger_writes, audits


_WINDOW = [
    _daily(date(2026, 8, 21), 9.9, 10.2, 9.7, 10.0),
    _daily(_EP, 10.5, 12.0, 9.8, 11.0, 5_000_000),
    _daily(date(2026, 8, 25), 10.8, 11.0, 10.1, 10.3),
    _daily(date(2026, 8, 26), 10.2, 10.4, 9.4, 9.6),
    _daily(_THU, 9.5, 9.9, 9.2, 9.7),
    _daily(_FRI, 9.7, 10.5, 9.5, 10.4, 900_000),
]


@pytest.mark.asyncio
async def test_missing_minute_bars_records_unscoreable_never_a_fabricated_fill(monkeypatch):
    """THE ABSTAIN RULE (required test): the member is armed (undercut seen), Friday's
    daily bar shows a possible reclaim (high > gap_low), but the minute bars are
    MISSING. The session row must say eval_status='unscoreable' /
    'missing_minute_bars', NO trigger row may be written, and the raw daily state
    facts still fold (facts are facts)."""
    watch, triggers, audits = _wire(
        monkeypatch, member=_member(), window=_WINDOW, minute_bars=[])
    out = await des.run_delayed_entry_shadow(_FRI)
    assert triggers == []                                   # never a fabricated fill
    assert out["watch_rows"] == 1 and out["unscoreable"] == 1
    row = watch[0]
    assert row["eval_status"] == "unscoreable"
    assert row["unscoreable_reason"] == "missing_minute_bars"
    assert row["session_date"] == _FRI and row["session_idx"] == 4
    assert row["undercut_seen"] is True                     # daily facts still folded
    assert row["fired_ep_low_reclaim"] is False             # still eligible on retry


@pytest.mark.asyncio
async def test_fire_writes_trigger_with_version_and_stop_width_from_bars(monkeypatch):
    """A real reclaim: Friday 5-min bars dip to 9.5 then close 10.0 above the EP low.
    The trigger row must carry pattern_version, resolution='minute_5', the ex-ante
    stamps, and stop/width computed from the actual bars: stop = min(carried 9.2,
    Friday's pre-fire lows) = 9.2; width = (10.0-9.2)/10.0*100 = 8.0."""
    bars5 = [
        _b5(570, 9.7, 9.9, 9.5, 9.7),     # still below the EP low
        _b5(575, 9.7, 10.1, 9.6, 10.0),   # 5-min close back above 9.8 -> fire
    ]
    watch, triggers, audits = _wire(
        monkeypatch, member=_member(), window=_WINDOW, minute_bars=bars5)
    out = await des.run_delayed_entry_shadow(_FRI)
    assert out["triggers"] == 1 and len(triggers) == 1
    t = triggers[0]
    assert t["rung"] == "ep_low_reclaim"
    assert t["pattern_version"] == des.PATTERN_VERSION
    assert t["resolution"] == "minute_5" and t["fire_minute_et"] == 575
    assert t["fire_date"] == _FRI and t["sessions_since_ep"] == 4
    assert t["entry_price"] == 10.0 and t["stop_price"] == 9.2
    assert t["stop_width_pct"] == pytest.approx(8.0)
    assert t["prior_session_low"] == 9.2                    # Thursday's low
    assert t["screen_member"] is True and t["catalyst_grade"] == "strong"
    assert t["gap_day_volume"] == 5_000_000 and t["day_volume"] == 900_000
    assert t["adr20_n"] == 5                                # the 5 window bars pre-fire
    # the watch row reflects the fire
    assert watch[0]["fired_ep_low_reclaim"] is True
    assert watch[0]["eval_status"] == "complete"


@pytest.mark.asyncio
async def test_writer_failure_degrades_to_audit_log_and_the_job_completes(monkeypatch):
    """Required test: the watch-row writer raises. run_delayed_entry_shadow must NOT
    raise, must count the error, must write a delayed_entry_shadow_error audit event,
    and must still emit the UNCONDITIONAL summary event (so '0 of N' is
    distinguishable from '0 of 0'). No Telegram path exists in this module at all."""
    watch, triggers, audits = _wire(
        monkeypatch, member=_member(), window=_WINDOW, minute_bars=[],
        upsert_raises=True)
    out = await des.run_delayed_entry_shadow(_FRI)          # must not raise
    assert out["errors"] == 1 and out["members"] == 1
    events = [e for e, _ in audits]
    assert "delayed_entry_shadow_error" in events
    assert "delayed_entry_shadow_recorded" in events        # summary is unconditional
    err = next(s for e, s in audits if e == "delayed_entry_shadow_error")
    assert "TST" in err and "boom" in err


@pytest.mark.asyncio
async def test_daily_grade_high_break_fires_without_minutes(monkeypatch):
    """A clean never-pulled-back member: Friday gaps to the EP high with the whole bar
    above the EP close. No minute fetch is needed; the fire is daily-grade with
    entry = the LEVEL and stop = Thursday's low."""
    member = _member(undercut_seen=False, low_since_undercut=None,
                     dipped_below_close_seen=False, low_of_dip=None)
    window = [
        _daily(date(2026, 8, 21), 9.9, 10.2, 9.7, 10.0),
        _daily(_EP, 10.5, 12.0, 9.8, 11.0, 5_000_000),
        _daily(date(2026, 8, 25), 11.2, 11.6, 11.1, 11.5),
        _daily(date(2026, 8, 26), 11.5, 11.8, 11.2, 11.6),
        _daily(_THU, 11.6, 11.9, 11.3, 11.8),
        _daily(_FRI, 11.9, 12.4, 11.7, 12.3),               # pushes above 12.0, never below 11.0
    ]

    async def _no_minutes(ticker, day):                     # pinned: must not be called
        raise AssertionError("minute fetch must not happen on the unambiguous daily path")

    watch, triggers, audits = _wire(
        monkeypatch, member=member, window=window, minute_bars=[])
    monkeypatch.setattr(des, "_fetch_minute_5", _no_minutes)
    out = await des.run_delayed_entry_shadow(_FRI)
    assert out["triggers"] == 1
    t = triggers[0]
    assert t["rung"] == "ep_high_break" and t["resolution"] == "daily"
    assert t["entry_price"] == 12.0 and t["stop_price"] == 11.3   # Thursday's low
    assert t["stop_width_pct"] == pytest.approx((12.0 - 11.3) / 12.0 * 100)
    assert t["fire_minute_et"] is None


@pytest.mark.asyncio
async def test_missing_daily_bar_records_unscoreable_and_state_carries(monkeypatch):
    """No daily bar at all for Friday: the row is honest ('missing_daily_bar'), the
    state carries UNCHANGED (we know nothing about the day), and nothing fires."""
    window = [b for b in _WINDOW if b["trade_date"] != _FRI]
    watch, triggers, audits = _wire(
        monkeypatch, member=_member(), window=window, minute_bars=[])
    out = await des.run_delayed_entry_shadow(_FRI)
    assert triggers == []
    row = watch[0]
    assert row["eval_status"] == "unscoreable"
    assert row["unscoreable_reason"] == "missing_daily_bar"
    assert row["bar_source"] == "missing" and row["day_close"] is None
    assert row["low_since_undercut"] == 9.2                 # carried, not touched


# ── settlement: pure core (compute_settlement / sma_trail_line / day0_needs_minutes) ──

from datetime import timedelta

_F0 = date(2026, 6, 1)                      # a fire date for pure-core fixtures


def _sess(n):
    return [_F0 + timedelta(days=i) for i in range(1, n + 1)]


def _sbar(d, h, l, c):
    return {"trade_date": d, "high_price": h, "low_price": l, "close": c}


def _bars(specs):
    """specs: list of (h, l, c) mapped onto consecutive sessions after _F0."""
    return {_F0 + timedelta(days=i + 1): _sbar(_F0 + timedelta(days=i + 1), h, l, c)
            for i, (h, l, c) in enumerate(specs)}


_FD = {"h": 10.4, "l": 9.9, "c": 10.2}      # a clean fire-day bar (low above stop 9.0)


def _settle(*, entry=10.0, stop=9.0, fire_minute=None, fire_day_bar=None,
            post=None, specs=(), n_sessions=None, closes_before=()):
    specs = list(specs)
    n = n_sessions if n_sessions is not None else len(specs)
    return des.compute_settlement(
        entry=entry, stop=stop, fire_minute=fire_minute,
        fire_day_bar=fire_day_bar or dict(_FD), post_fire_bars5=post,
        sessions=_sess(n), bars_by_day=_bars(specs),
        closes_before_fire=list(closes_before))


def test_sma_trail_line_matches_live_exit_logic_semantics():
    """<10 closes: no line (live None-guard). 10-19: SMA10 alone. >=20: max(SMA10, SMA20),
    SMA including the current close."""
    assert des.sma_trail_line([10.0] * 9) is None
    assert des.sma_trail_line([10.0] * 19 + [20.0]) == pytest.approx(11.0)  # SMA10 only
    rising = [float(i) for i in range(1, 21)]                # SMA10=15.5 > SMA20=10.5
    assert des.sma_trail_line(rising) == pytest.approx(15.5)


def test_day0_needs_minutes_only_for_minute_fires_whose_day_low_touched_the_stop():
    assert des.day0_needs_minutes(None, 8.0, 9.0) is False   # daily fire: pess instead
    assert des.day0_needs_minutes(580, 9.5, 9.0) is False    # day low never touched
    assert des.day0_needs_minutes(580, 8.9, 9.0) is True     # ambiguous: order via minutes
    assert des.day0_needs_minutes(580, None, 9.0) is False


def test_stop_on_day3_settles_on_day3_not_day20():
    """REQUIRED: only THREE sessions of bars exist (today = fire+3) and the third one
    touches the stop -> the row settles NOW, both arms stopped at -1.0R. mae_r keeps the
    raw low (-1.1R: the gap-through stays visible even though realized is -1.0)."""
    res = _settle(specs=[(10.5, 9.8, 10.1), (10.3, 9.7, 10.0), (10.0, 8.9, 9.1)])
    assert res["status"] == "settled"
    assert res["outcome"] == "stop" and res["realized_r"] == -1.0
    assert res["outcome_trail"] == "stop" and res["realized_r_trail"] == -1.0
    assert res["mae_r"] == pytest.approx(-1.1)
    # checkpoints: s1 is the day-1 mark; s5/s10/s20 are frozen at the realized stop
    assert res["r_none_s1"] == pytest.approx(0.1)
    assert res["r_none_s5"] == -1.0 and res["r_none_s20"] == -1.0


def test_open_window_abstains_then_settles_time_exit_when_ripe():
    """A trigger with no stop hit and only 3 elapsed sessions is NOT settled — it stays
    open (abstain) and the identical inputs with 20 sessions settle as time_exit at the
    20th close. This is the partially-elapsed-window case: every fresh trigger abstains
    until its outcome is definitive."""
    three = [(10.5, 9.8, 10.1)] * 3
    res = _settle(specs=three)
    assert res == {"status": "abstain", "reason": "window_open"}
    twenty = [(10.5, 9.8, 10.1)] * 19 + [(10.6, 9.9, 10.5)]
    res = _settle(specs=twenty)
    assert res["status"] == "settled"
    assert res["outcome"] == "time_exit" and res["realized_r"] == pytest.approx(0.5)
    assert res["r_none_s20"] == pytest.approx(0.5)


def test_missing_middle_session_abstains_never_leaps_the_gap():
    """MUTATION TARGET (THE ABSTAIN RULE): day 2's bar is missing; day 3 would stop.
    The walk must ABSTAIN at the gap — a stop (or a gap-through) could hide inside it —
    and must NOT settle from the bars on the far side."""
    bars = _bars([(10.5, 9.8, 10.1), (10.3, 9.7, 10.0), (10.0, 8.9, 9.1)])
    del bars[_F0 + timedelta(days=2)]
    res = des.compute_settlement(
        entry=10.0, stop=9.0, fire_minute=None, fire_day_bar=dict(_FD),
        post_fire_bars5=None, sessions=_sess(3), bars_by_day=bars,
        closes_before_fire=[])
    assert res["status"] == "abstain"
    assert res["reason"] == f"missing_session:{(_F0 + timedelta(days=2)).isoformat()}"


def test_missing_day0_minutes_abstain_and_retry_never_a_daily_verdict():
    """REQUIRED: a minute-grade fire whose day low touched the stop can only be ordered
    by post-fire minutes. Without them -> ABSTAIN (retry next run). WITH them showing no
    post-fire touch -> the pre-fire low must NOT be read as a stop-out (a fabricated
    loss is as dishonest as a fabricated fill) — the row simply stays open."""
    fd = {"h": 10.4, "l": 8.5, "c": 10.2}    # day low 8.5 <= stop 9.0: pre-fire undercut
    res = _settle(fire_minute=600, fire_day_bar=fd, post=None, n_sessions=0)
    assert res == {"status": "abstain", "reason": "missing_day0_minutes"}
    post = [_b5(605, 9.4, 9.8, 9.3, 9.5)]    # post-fire lows all above the stop
    res = _settle(fire_minute=600, fire_day_bar=fd, post=post, n_sessions=0)
    assert res == {"status": "abstain", "reason": "window_open"}   # open, NOT stopped


def test_day0_post_fire_stop_settles_the_same_evening():
    """A fire whose stop is touched later the same day settles on the very first
    settlement pass — with ZERO forward sessions available yet."""
    fd = {"h": 10.4, "l": 8.5, "c": 9.0}
    post = [_b5(605, 9.4, 9.9, 8.95, 9.1)]   # post-fire low 8.95 <= stop 9.0
    res = _settle(fire_minute=600, fire_day_bar=fd, post=post, n_sessions=0)
    assert res["status"] == "settled"
    assert res["outcome"] == "stop" and res["realized_r"] == -1.0
    assert res["outcome_trail"] == "stop"
    assert res["r_none_s1"] == -1.0          # frozen from the day-0 exit


def test_realized_r_is_harvested_r_never_mfe():
    """REQUIRED: day 1 runs to +6.2R (MFE), the trade then round-trips and stops on
    day 3. realized_r must be the HARVESTED result (-1.0R), the +6.2R lives ONLY in
    mfe_r, and reached_4r is True because 4R printed on a clean pre-stop session."""
    res = _settle(specs=[(16.2, 9.9, 15.8), (15.9, 9.5, 9.6), (9.6, 8.9, 9.0)])
    assert res["status"] == "settled"
    assert res["realized_r"] == -1.0                       # harvested, not the peak
    assert res["mfe_r"] == pytest.approx(6.2)              # the peak, in its own column
    assert res["reached_4r"] is True
    assert res["realized_r"] != res["mfe_r"]               # the conflation is the bug


def test_exact_touch_of_the_stop_is_a_stop():
    """A session low exactly AT the stop level stops the trade (a resting stop executes
    on the touch) — pins the <= boundary against a silent < mutation."""
    res = _settle(specs=[(10.2, 9.0, 9.4)])                # low == stop == 9.0
    assert res["status"] == "settled" and res["outcome"] == "stop"


def test_reached_4r_is_pess_a_spanning_session_reads_stop_first():
    """MUTATION TARGET (pess stop-first): one session both touches the stop AND prints
    +5R. Within-day ordering is unknowable, so the stop is presumed first: outcome=stop
    and reached_4r=False. The high still folds into mfe_r (ceiling telemetry only)."""
    res = _settle(specs=[(15.0, 8.9, 9.2)])
    assert res["status"] == "settled"
    assert res["outcome"] == "stop"
    assert res["reached_4r"] is False
    assert res["mfe_r"] == pytest.approx(5.0)


def test_trail_exits_below_max_sma_while_none_holds_to_time_exit_one_write():
    """The two arms settle on ONE row in ONE write even when they resolve on different
    days: M-trail exits day 5 on a close below max(SMA10, SMA20); M-none never stops
    (wide stop) and time-exits at the 20th close. Checkpoints freeze per arm."""
    specs = ([(10.4, 10.1, 10.3), (10.5, 10.2, 10.4), (10.6, 10.3, 10.5),
              (10.7, 10.4, 10.6), (10.6, 8.8, 9.0)]      # day 5 closes under the SMAs
             + [(8.6, 8.0, 8.5)] * 15)
    res = _settle(entry=10.0, stop=5.0, specs=specs, closes_before=[10.0] * 25)
    assert res["status"] == "settled"
    assert res["outcome_trail"] == "trail_exit"
    assert res["realized_r_trail"] == pytest.approx(-0.2)  # (9.0-10)/5, the day-5 close
    assert res["outcome"] == "time_exit"
    assert res["realized_r"] == pytest.approx(-0.3)        # (8.5-10)/5, the day-20 close
    assert res["r_trail_s10"] == pytest.approx(-0.2)       # frozen at the trail exit
    assert res["r_none_s10"] == pytest.approx(-0.3)        # still marked to market
    assert res["reached_4r"] is False


def test_trail_cannot_exit_until_ten_closes_exist_then_arms():
    """<10 total closes -> no SMA line (the live None-guard): sessions 1-8 close below
    everything yet CANNOT trail-exit (the line does not exist); the trail arms the
    session the 10th close lands (session 9 here, closes accumulating like live's
    running_closes) and exits THERE. An early arming would exit session 1 at 9.9
    (-0.02R) — pinned distinct from the true session-9 exit at 9.5 (-0.1R)."""
    specs = [(10.1, 9.8, 9.9)] * 8 + [(9.6, 9.4, 9.5)] * 12
    res = _settle(entry=10.0, stop=5.0, specs=specs, closes_before=[])
    assert res["status"] == "settled"
    assert res["outcome_trail"] == "trail_exit"
    assert res["realized_r_trail"] == pytest.approx(-0.1)  # session 9's close, not 1's
    assert res["r_trail_s5"] == pytest.approx(-0.02)       # still open at s5: a mark
    assert res["outcome"] == "time_exit"                   # the stop (5.0) never near


def test_degenerate_geometry_is_unscoreable_not_scored():
    """A recorded ep_high_break with stop above entry (negative width — recorded, never
    dropped) cannot be scored as a trade: R is undefined. It closes unscoreable."""
    res = _settle(entry=10.0, stop=10.5, specs=[(11.0, 10.0, 10.8)])
    assert res == {"status": "unscoreable", "reason": "degenerate_geometry"}


# ── settlement: orchestration (db collaborators monkeypatched) ────────────────────────


def _trigger_row(**over):
    t = {
        "id": 7, "ticker": "TST", "ep_date": _EP, "rung": "ep_low_reclaim",
        "fire_date": _THU, "fire_minute_et": 580, "resolution": "minute_5",
        "entry_price": 10.0, "stop_price": 9.6,
        "day_high": 9.9, "day_low": 9.2, "day_close": 9.7,   # Thursday's bar
    }
    t.update(over)
    return t


def _wire_settle(monkeypatch, *, trigger, window, minute_bars, settle_result=True,
                 member=None):
    """Settlement wiring on top of _wire: one open trigger, captured settle writes."""
    watch, triggers, audits = _wire(
        monkeypatch, member=member or _member(session_idx=20),
        window=window, minute_bars=minute_bars)
    settles = []

    async def _open_triggers():
        return [dict(trigger)] if trigger else []

    async def _settle(row_id, fields):
        settles.append((row_id, dict(fields)))
        return settle_result

    monkeypatch.setattr(des, "get_delayed_entry_open_triggers", _open_triggers)
    monkeypatch.setattr(des, "settle_delayed_entry_trigger", _settle)
    return settles, audits


@pytest.mark.asyncio
async def test_settlement_rides_the_same_run_and_the_digest_counts_it(monkeypatch):
    """Thursday's minute fire (entry 10.0, stop 9.6; the day low 9.2 pre-dates the fire
    so day 0 is ordered via post-fire minutes) hits its stop on Friday's 9.5 low. The
    inline pass settles it: outcome=stop, realized -1.0R, settle_version stamped, and
    the ONE summary digest reports considered/settled."""
    post = [_b5(585, 9.7, 9.9, 9.65, 9.8)]           # post-fire day 0: never near 9.6
    settles, audits = _wire_settle(
        monkeypatch, trigger=_trigger_row(), window=_WINDOW, minute_bars=post)
    out = await des.run_delayed_entry_shadow(_FRI)
    assert out["settle_considered"] == 1 and out["settle_settled"] == 1
    assert out["settle_abstained"] == 0
    (row_id, fields), = settles
    assert row_id == 7
    assert fields["outcome"] == "stop" and fields["realized_r"] == -1.0
    assert fields["outcome_trail"] == "stop"
    assert fields["settle_version"] == des.SETTLE_VERSION
    summary = next(s for e, s in audits if e == "delayed_entry_shadow_recorded")
    assert "1 open trigger(s) considered, 1 settled" in summary


@pytest.mark.asyncio
async def test_not_yet_definitive_abstains_and_the_row_stays_open(monkeypatch):
    """Friday never touches a 9.0 stop and 20 sessions have not elapsed: the pass must
    consider the row, settle NOTHING, and count the abstain — the open row (outcome
    NULL) is the at-a-glance marker of a partially-elapsed window."""
    trig = _trigger_row(stop_price=9.0, day_low=9.7, fire_minute_et=None,
                        resolution="daily")
    settles, audits = _wire_settle(
        monkeypatch, trigger=trig, window=_WINDOW, minute_bars=[])
    out = await des.run_delayed_entry_shadow(_FRI)
    assert settles == []
    assert out["settle_considered"] == 1 and out["settle_settled"] == 0
    assert out["settle_abstained"] == 1
    summary = next(s for e, s in audits if e == "delayed_entry_shadow_recorded")
    assert "1 abstained" in summary


@pytest.mark.asyncio
async def test_orphan_past_horizon_closes_unscoreable_never_interpolated(monkeypatch):
    """A trigger 50+ calendar days old whose forward bars never arrived (halt/delist/
    hole) must not stay open forever OR be settled from guesses: it closes as
    outcome='unscoreable' with realized_r NULL, loud in the audit log."""
    old_fire = _FRI - timedelta(days=50)
    trig = _trigger_row(fire_date=old_fire, fire_minute_et=None, resolution="daily",
                        stop_price=9.0, day_low=9.7)
    settles, audits = _wire_settle(
        monkeypatch, trigger=trig, window=_WINDOW, minute_bars=[])
    out = await des.run_delayed_entry_shadow(_FRI)
    assert out["settle_unscoreable"] == 1 and out["settle_settled"] == 0
    (row_id, fields), = settles
    assert fields["outcome"] == "unscoreable"
    assert fields["outcome_trail"] == "unscoreable"
    assert fields.get("realized_r") is None                 # never a number
    assert any(e == "delayed_entry_shadow_unscoreable" for e, _ in audits)


@pytest.mark.asyncio
async def test_double_settle_is_a_noop_lost_race_is_not_counted(monkeypatch):
    """The DB guard (WHERE outcome IS NULL) makes a second settle a no-op; the caller
    must treat settle->False as already-settled: not counted, not an error."""
    post = [_b5(585, 9.7, 9.9, 9.65, 9.8)]
    settles, audits = _wire_settle(
        monkeypatch, trigger=_trigger_row(), window=_WINDOW, minute_bars=post,
        settle_result=False)
    out = await des.run_delayed_entry_shadow(_FRI)
    assert len(settles) == 1                                # attempted exactly once
    assert out["settle_settled"] == 0 and out["errors"] == 0


def test_double_settle_guard_is_pinned_in_the_sql():
    """The settle UPDATE must carry the `outcome IS NULL` guard and stamp settled_at —
    editing either out of db.py fails here (the two-phase contract, pinned)."""
    from agents.market_intelligence import db as dbmod
    assert "WHERE id = $1 AND outcome IS NULL" in dbmod._DELAYED_SETTLE_SQL
    assert "settled_at = NOW()" in dbmod._DELAYED_SETTLE_SQL
    assert "realized_r" in dbmod._DELAYED_SETTLE_COLS
