"""#482 add-on (operator 2026-10-26, "Ok move to Tuesday"): the FIRST-HOUR entry recorded on EVERY
ORB alert the 5-minute shadow lane sees — a second bar size (60) in `mi_orb_shadow_trades`.

Synthetic, CI-safe (no DB, no Alpaca): every IO seam of `shadow_orb_tracker` is monkeypatched and
every write is captured. The 5-minute lane's payloads are compared to a GOLDEN fixture captured from
the tracker BEFORE this change (`tests/fixtures/482_shadow_5m_golden.json`) — the proof that the
60-minute lane changed nothing about the 5-minute rows.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence.broker import shadow_orb_tracker as sot

ET = ZoneInfo("America/New_York")
GOLDEN = Path(__file__).parent / "fixtures" / "482_shadow_5m_golden.json"
DAY = date(2026, 10, 27)          # a Tuesday, regular session
HALF_DAY = date(2026, 11, 27)     # the day after Thanksgiving: NYSE closes 13:00 ET


# ── synthetic minute bars (the tracker's own alpaca shape) ────────────────────────────────


def _bar(d: date, hh: int, mm: int, o: float, h: float, l: float, c: float) -> dict:
    return {"open": o, "high": h, "low": l, "close": c, "volume": 1000,
            "timestamp": datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET)}


def _flat_day(d: date, px: float, start: time = time(9, 30), end: time = time(16, 0),
              skip: set[tuple[int, int]] | None = None) -> list[dict]:
    """One flat bar per minute in [start, end), minus `skip` minutes."""
    bars = []
    t = datetime.combine(d, start, tzinfo=ET)
    stop = datetime.combine(d, end, tzinfo=ET)
    while t < stop:
        if not (skip and (t.hour, t.minute) in skip):
            bars.append(_bar(d, t.hour, t.minute, px, px, px, px))
        t += timedelta(minutes=1)
    return bars


def _with_hour_range(bars: list[dict], hi: float, lo: float) -> list[dict]:
    """Give the 09:30-10:29 bars a range [lo, hi] (09:31 prints the high, 09:40 the low)."""
    out = []
    for b in bars:
        ts = b["timestamp"]
        if (ts.hour, ts.minute) == (9, 31):
            b = {**b, "high": hi, "close": hi}
        elif (ts.hour, ts.minute) == (9, 40):
            b = {**b, "low": lo}
        out.append(b)
    return out


def _cross_at(bars: list[dict], hh: int, mm: int, high: float) -> list[dict]:
    return [{**b, "high": high} if (b["timestamp"].hour, b["timestamp"].minute) == (hh, mm) else b
            for b in bars]


# ── the IO seams ─────────────────────────────────────────────────────────────────────────


def _jsonable(v):
    if isinstance(v, (datetime,)):
        return "<datetime>"           # closed_at / quarantined_at are wall-clock stamps
    if isinstance(v, (date, time)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


class _Captured:
    def __init__(self):
        self.inserts: list[dict] = []
        self.updates: list[tuple[int, dict]] = []
        self.audit: list[tuple[str, str]] = []
        self.existing: set[tuple[str, date, int]] = set()

    async def insert(self, row: dict):
        key = (row["ticker"], row["alert_date"], row["bar_size_minutes"])
        if key in self.existing:
            return None
        self.existing.add(key)
        self.inserts.append(dict(row))
        return len(self.inserts)

    async def update(self, trade_id: int, fields: dict):
        self.updates.append((trade_id, dict(fields)))

    async def log_audit(self, event: str, summary: str, **_):
        self.audit.append((event, summary))

    def payloads(self) -> dict:
        return _jsonable({"inserts": self.inserts,
                          "updates": [{"id": i, "fields": f} for i, f in self.updates]})


def _patch_common(monkeypatch, cap: _Captured, *, minute_bars, daily_bars):
    """Every seam the two passes touch. `minute_bars(ticker, day, start, end)` and
    `daily_bars(ticker, from, to)` are the synthetic market-data sources."""
    import agents.market_intelligence.db as db
    import agents.market_intelligence.strategies.registry as registry
    monkeypatch.setattr(sot.alpaca, "get_minute_bars_window", AsyncMock(side_effect=minute_bars))
    monkeypatch.setattr(sot, "get_index_history", AsyncMock(side_effect=daily_bars))
    monkeypatch.setattr(sot, "insert_shadow_trade", cap.insert)
    monkeypatch.setattr(sot, "update_shadow_trade", cap.update)
    monkeypatch.setattr(db, "log_audit_event", cap.log_audit)
    monkeypatch.setattr(registry, "should_run", AsyncMock(return_value=True))
    monkeypatch.setattr(sot, "_fetch_latest_regime", AsyncMock(return_value={"regime": "neutral"}))


def _patch_5m_lane(monkeypatch, cap: _Captured):
    """The 5-minute entry pass's own gates, pinned to deterministic answers."""
    import sys
    # the tracker imports compute_atr_14 lazily by name, which resolves through sys.modules — where
    # conftest keeps a stub of backtester.filters; patch THAT object, not the package attribute
    filters = sys.modules["agents.market_intelligence.backtester.filters"]
    monkeypatch.setattr(sot, "_fetch_magna53_high_pre_open", AsyncMock(return_value=[
        {"ticker": "AAA", "alert_date": DAY, "gap_pct": 12.0, "rel_volume": 4.0, "ep_score": 80,
         "score_tier": "HIGH", "catalyst": "earnings", "catalyst_quality": "strong", "vol_percentile": 95},
        {"ticker": "BBB", "alert_date": DAY, "gap_pct": 9.0, "rel_volume": 3.0, "ep_score": 70,
         "score_tier": "HIGH", "catalyst": "guidance", "catalyst_quality": "ok", "vol_percentile": 80},
    ]))
    monkeypatch.setattr(sot, "get_all_9m_sugar_babies", AsyncMock(return_value=[]))
    monkeypatch.setattr(sot, "check_fade_guard", AsyncMock(return_value=(True, None)))
    monkeypatch.setattr(filters, "compute_atr_14", AsyncMock(return_value=(1.5, None)))

    async def _prepare(alert_ctx, orb_bar, atr_14, regime, **kw):
        stop = 2 * orb_bar["low"] - orb_bar["high"]
        return ({"entry_price": orb_bar["high"], "stop_loss_price": stop, "shares": 10,
                 "risk_dollars": 10 * (orb_bar["high"] - stop), "atr_14": atr_14}, None)
    monkeypatch.setattr(sot, "prepare_orb_order", _prepare)


def _minute_source_5m(ticker: str, day: date, start: int, end: int) -> list[dict]:
    """09:30-10:00 for the 5-minute lane: AAA breaks its 5-min ORB high at 09:41, BBB never does."""
    bars = _flat_day(day, 10.0, end=time(10, 0))
    if ticker == "AAA":
        bars = _cross_at([{**b, "high": 10.5} if b["timestamp"].minute == 32 else b for b in bars], 9, 41, 10.6)
    else:  # BBB: the 5-min ORB is [10, 10] and every later print sits under it
        bars = [b if b["timestamp"].minute < 35 else {**b, "high": 9.9, "open": 9.9, "close": 9.9} for b in bars]
    return [b for b in bars if start * 60 <= (b["timestamp"].hour * 60 + b["timestamp"].minute - 570) < end]


def _open_5m_row(ticker: str, alert_date: date, **over) -> dict:
    row = {"id": 1, "ticker": ticker, "alert_date": alert_date, "bar_size_minutes": 5,
           "status": "open", "remaining_shares": 10.0, "entry_price": 10.5, "hard_stop": 9.5,
           "entry_shares": 10.0, "partial_taken": False, "breakeven_active": False,
           "exits": [], "running_closes": [], "hold_days": None, "total_pnl": None,
           "stop_price": 9.5, "closed_at": None, "quarantined": False}
    row.update(over)
    return row


async def _drive_5m_lane(monkeypatch) -> dict:
    """The 5-minute lane end to end on the fixed fixture: the 10:00 entry pass, then the next
    session's exit step on one open 5-minute row that gets stopped out and one that just updates."""
    cap = _Captured()
    _patch_common(monkeypatch, cap,
                  minute_bars=_minute_source_5m,
                  daily_bars=lambda t, a, b: [{"o": 10.4, "h": 10.9, "l": 9.4 if t == "AAA" else 10.1,
                                               "c": 10.2, "t": 0}])
    _patch_5m_lane(monkeypatch, cap)
    # the hour lane's population query never sees a DB here: in the 5-minute drive it is empty
    monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=[]), raising=False)
    counts = await sot.run_shadow_pass(DAY)
    assert counts["open"] == 1 and counts["no_entry"] == 1
    open_rows = [_open_5m_row("AAA", DAY, id=1), _open_5m_row("CCC", DAY, id=2, entry_price=10.0, hard_stop=9.0)]

    async def _open(bar_size_minutes=None):
        return [r for r in open_rows if bar_size_minutes in (None, 5)]
    monkeypatch.setattr(sot, "get_open_shadow_trades", _open)
    out = await sot.update_shadow_positions(DAY + timedelta(days=1))
    assert out["closed"] == 1 and out["updated"] == 1
    return cap.payloads()


# ── (1) the 5-minute rows are byte-equal to the pre-change golden ────────────────────────


@pytest.mark.asyncio
async def test_5m_lane_payloads_match_the_pre_change_golden(monkeypatch):
    """Captured from the tracker at af4d2696 (before the hour lane existed). Every INSERT and UPDATE
    the 5-minute lane makes on this fixture must be identical, key for key, value for value."""
    got = await _drive_5m_lane(monkeypatch)
    want = json.loads(GOLDEN.read_text())     # a missing fixture FAILS — it is never re-captured here
    assert got == want


# ── (2) the 60-minute lane ───────────────────────────────────────────────────────────────


def _five_row(ticker: str, alert_date: date = DAY, **over) -> dict:
    row = {"ticker": ticker, "alert_date": alert_date, "signal_type": "magna53", "shape_tag": None,
           "score_tier": "HIGH", "atr_14": 1.5}
    row.update(over)
    return row


def _hour_day(d: date, *, hi: float = 11.0, lo: float = 9.5, cross: tuple[int, int] | None = None,
              end: time = time(16, 0), skip: set[tuple[int, int]] | None = None,
              cross_high: float = 11.2) -> list[dict]:
    """A day of flat 10.0 bars, the first hour ranging [lo, hi]; `cross` names the one minute whose
    high prints above the hour high."""
    bars = _with_hour_range(_flat_day(d, 10.0, end=end, skip=skip), hi, lo)
    return _cross_at(bars, *cross, cross_high) if cross else bars


async def _drive_hour(monkeypatch, candidates: list[dict], bars_by_ticker: dict, *,
                      today: date = DAY, daily_high: dict | None = None) -> tuple[dict, _Captured]:
    cap = _Captured()

    async def _minutes(ticker, day, start, end):
        return [b for b in bars_by_ticker[ticker]
                if start <= _minutes_from_open(b["timestamp"]) < end]

    async def _daily(ticker, a, b):
        h = (daily_high or {}).get(ticker)
        return [] if h is None else [{"o": 10, "h": h, "l": 9, "c": 10, "t": 0}]
    _patch_common(monkeypatch, cap, minute_bars=_minutes, daily_bars=_daily)
    monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=candidates))
    counts = await sot.run_shadow_hour_pass(today)
    return counts, cap


def _minutes_from_open(ts: datetime) -> int:
    return ts.hour * 60 + ts.minute - 570


@pytest.mark.asyncio
async def test_hour_lane_enters_only_above_the_hour_high_and_only_from_1030(monkeypatch):
    """A print above the first hour's high at 10:45 is the entry: stop-limit at the hour high from
    10:30, filled at the level, stop = 2 × hour low − hour high, one unit, risk = entry − stop."""
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")],
                                    {"AAA": _hour_day(DAY, cross=(10, 45))})
    assert counts["open"] == 1 and counts["error"] == 0
    (row,) = cap.inserts
    assert row["bar_size_minutes"] == 60
    assert row["status"] == "open"
    assert row["orb_high"] == 11.0 and row["orb_low"] == 9.5
    assert row["entry_price"] == 11.0
    assert row["trigger_minute_et"] == time(10, 45)
    assert row["trigger_minute_et"] >= time(10, 30)
    assert row["stop_price"] == row["hard_stop"] == pytest.approx(2 * 9.5 - 11.0)
    assert row["entry_shares"] == 1.0
    assert row["risk_dollars"] == pytest.approx(11.0 - (2 * 9.5 - 11.0))
    assert row["remaining_shares"] == 1.0
    assert row["signal_type"] == "magna53" and row["score_tier"] == "HIGH" and row["atr_14"] == 1.5


@pytest.mark.asyncio
async def test_hour_lane_a_print_inside_the_first_hour_is_the_bar_not_an_entry(monkeypatch):
    """The highest print before 10:30 IS the hour high — it cannot be crossed by itself. A day whose
    only high is at 10:15 and never retaken from 10:30 on is a no-entry, never an entry."""
    bars = _hour_day(DAY, cross=(10, 15), cross_high=11.5)
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")], {"AAA": bars})
    assert counts["no_entry"] == 1
    (row,) = cap.inserts
    assert row["status"] == "no_entry" and row["entry_price"] is None
    assert row["orb_high"] == 11.5                      # the 10:15 print is the hour high
    assert row["trigger_minute_et"] is None
    assert row["skip_reason"] is None                    # the 5-minute lane's plain no-entry shape


@pytest.mark.asyncio
async def test_hour_lane_level_touched_exactly_at_1030_is_the_first_eligible_minute(monkeypatch):
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")],
                                    {"AAA": _hour_day(DAY, cross=(10, 30))})
    assert counts["open"] == 1
    assert cap.inserts[0]["trigger_minute_et"] == time(10, 30)


@pytest.mark.asyncio
async def test_hour_lane_half_day_order_dies_at_1300(monkeypatch):
    """2026-11-27 closes 13:00 ET (exchange_calendars). A cross at 13:05 is after the day order
    expired → no_entry; the same cross at 12:55 fills. Both days' walks cover the window fully."""
    late = _hour_day(HALF_DAY, cross=(13, 5), end=time(16, 0))
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA", HALF_DAY)], {"AAA": late},
                                    today=HALF_DAY)
    assert counts["no_entry"] == 1 and cap.inserts[0]["status"] == "no_entry"
    early = _hour_day(HALF_DAY, cross=(12, 55), end=time(16, 0))
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA", HALF_DAY)], {"AAA": early},
                                    today=HALF_DAY)
    assert counts["open"] == 1 and cap.inserts[0]["trigger_minute_et"] == time(12, 55)
    # the fetch itself stops at the close: 210 minutes from the open on a half day, 390 on a full one
    assert sot._minutes_from_open(time(13, 0)) == 210 and sot._minutes_from_open(time(16, 0)) == 390


@pytest.mark.asyncio
async def test_hour_lane_day0_gap_rule_daily_high_below_hour_high_proves_no_entry(monkeypatch):
    """Holes after 10:30, no stored cross, and the day's high strictly BELOW the hour high → no_entry,
    proven. A daily high EQUAL to the hour high proves nothing (review F6: a stop triggers AT its
    price and the walk fills on h >= level, so the re-touch may sit in a missing minute) → deferred."""
    bars = _hour_day(DAY, skip={(11, 0), (11, 1), (14, 30)})
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")], {"AAA": bars},
                                    daily_high={"AAA": 10.95})
    assert counts["no_entry"] == 1
    (row,) = cap.inserts
    assert row["status"] == "no_entry"
    assert row["skip_reason"] == "no_entry:never_crossed_hour_high:proven_by_daily_high"
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")], {"AAA": bars},
                                    daily_high={"AAA": 11.0})
    assert counts["deferred"] == 1 and cap.inserts == []


@pytest.mark.asyncio
async def test_hour_lane_day0_gap_rule_daily_high_above_defers_then_records_the_gap(monkeypatch):
    """The same holes with a day high ABOVE the hour high: the cross may sit in a missing minute.
    Nothing is written while the alert is young; once HOUR_GAP_RETRY_SESSIONS old the row is
    recorded gate_blocked with the gap named (a positive observable, not a silent skip)."""
    bars = _hour_day(DAY, skip={(11, 0), (11, 1), (14, 30)})
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")], {"AAA": bars},
                                    daily_high={"AAA": 11.4})
    assert counts["deferred"] == 1 and cap.inserts == []
    later = DAY + timedelta(days=7)          # five weekday sessions after the alert
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")], {"AAA": bars},
                                    today=later, daily_high={"AAA": 11.4})
    assert counts["gate_blocked"] == 1
    (row,) = cap.inserts
    assert row["status"] == "gate_blocked"
    assert row["skip_reason"].startswith("infra:no_bar: entry_window_gaps:3_of_330")
    assert "session_high_at_or_above_hour_high" in row["skip_reason"]
    assert row["orb_high"] == 11.0 and row["entry_price"] is None


@pytest.mark.asyncio
async def test_hour_lane_no_daily_bar_defers_the_gap(monkeypatch):
    bars = _hour_day(DAY, skip={(11, 0)})
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")], {"AAA": bars})
    assert counts["deferred"] == 1 and cap.inserts == []


@pytest.mark.asyncio
async def test_hour_lane_thin_first_hour_defers_then_records(monkeypatch):
    """Fewer than 50 of the 60 first-hour minutes stored: the bar's high/low is not trusted."""
    bars = _hour_day(DAY, cross=(10, 45), skip={(9, m) for m in range(35, 60)})   # 35 of 60
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")], {"AAA": bars})
    assert counts["deferred"] == 1
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")], {"AAA": bars},
                                    today=DAY + timedelta(days=7))
    assert counts["gate_blocked"] == 1
    assert cap.inserts[0]["skip_reason"] == "infra:no_bar: first_hour_bars:35_of_60 (unresolved after 5 sessions)"


@pytest.mark.asyncio
async def test_hour_lane_no_minute_bars_at_all_defers_then_records(monkeypatch):
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")], {"AAA": []})
    assert counts["deferred"] == 1
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")], {"AAA": []},
                                    today=DAY + timedelta(days=7))
    assert counts["gate_blocked"] == 1 and "no_minute_bars" in cap.inserts[0]["skip_reason"]


@pytest.mark.asyncio
async def test_hour_lane_nonpositive_2r_stop_is_gate_blocked_not_open(monkeypatch):
    """A first hour ranging more than half its high (lo < hi/2) puts 2 × lo − hi at or below zero —
    the same reject `prepare_orb_order` makes on the 5-minute bar, recorded, never walked."""
    counts, cap = await _drive_hour(monkeypatch, [_five_row("AAA")],
                                    {"AAA": _hour_day(DAY, hi=11.0, lo=5.0, cross=(10, 45))})
    assert counts["gate_blocked"] == 1
    (row,) = cap.inserts
    assert row["status"] == "gate_blocked" and row["skip_reason"].startswith("first_hour_2r_stop_nonpositive")
    assert row["entry_price"] is None and row["trigger_minute_et"] == time(10, 45)


@pytest.mark.asyncio
async def test_hour_lane_unique_conflict_counts_duplicate_and_a_crash_is_isolated(monkeypatch):
    bars = {"AAA": _hour_day(DAY, cross=(10, 45)), "BBB": _hour_day(DAY, cross=(10, 45))}
    cands = [_five_row("AAA"), _five_row("AAA"), _five_row("BBB")]

    async def _minutes(ticker, day, start, end):
        if ticker == "BBB":
            raise RuntimeError("feed down")
        return bars[ticker]
    cap = _Captured()
    _patch_common(monkeypatch, cap, minute_bars=_minutes, daily_bars=lambda *a: [])
    monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=cands))
    counts = await sot.run_shadow_hour_pass(DAY)
    assert counts["open"] == 1 and counts["duplicate"] == 1 and counts["error"] == 1
    assert [e for e, _ in cap.audit] == ["shadow_orb_hour_pass"]


@pytest.mark.asyncio
async def test_hour_lane_honours_the_shadow_kill_switch(monkeypatch):
    import agents.market_intelligence.strategies.registry as registry
    cap = _Captured()
    _patch_common(monkeypatch, cap, minute_bars=lambda *a: [], daily_bars=lambda *a: [])
    monkeypatch.setattr(registry, "should_run", AsyncMock(return_value=False))
    fetch = AsyncMock(return_value=[_five_row("AAA")])
    monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", fetch)
    counts = await sot.run_shadow_hour_pass(DAY)
    assert counts["strategy_disabled"] == 1 and cap.inserts == [] and not fetch.called


# ── (3) the exit step walks both bar sizes, the 60-minute row on the same ladder ─────────


@pytest.mark.asyncio
async def test_exit_step_steps_the_hour_row_on_the_same_ladder_after_the_5m_rows(monkeypatch):
    cap = _Captured()
    _patch_common(monkeypatch, cap, minute_bars=lambda *a: [],
                  daily_bars=lambda t, a, b: [{"o": 11, "h": 11.5, "l": 7.9, "c": 8.5, "t": 0}])
    hour_row = _open_5m_row("AAA", DAY, id=7, bar_size_minutes=60, remaining_shares=1.0,
                            entry_shares=1.0, entry_price=11.0, hard_stop=8.0, stop_price=8.0)
    asked: list = []

    async def _open(bar_size_minutes=None):
        asked.append(bar_size_minutes)
        return [hour_row] if bar_size_minutes in (None, 60) else []
    monkeypatch.setattr(sot, "get_open_shadow_trades", _open)
    out = await sot.update_shadow_positions(DAY + timedelta(days=1))
    assert asked == [None]                      # one read, every bar size, quarantined rows excluded
    assert out["closed"] == 1
    (trade_id, fields), = cap.updates
    assert trade_id == 7 and fields["status"] == "closed"
    assert fields["exits"][0]["reason"] == "stop_hit" and fields["exits"][0]["price"] == 8.0
    assert fields["total_pnl"] == pytest.approx((8.0 - 11.0) * 1.0)     # one unit: pnl / risk = −1R


@pytest.mark.asyncio
async def test_exit_step_skips_day0_for_the_hour_row_exactly_as_for_5m(monkeypatch):
    """The step on the alert day itself is `skip_pre_alert` for every bar size — the hour row's
    first step is the next session, the 5-minute lane's own rule."""
    cap = _Captured()
    _patch_common(monkeypatch, cap, minute_bars=lambda *a: [],
                  daily_bars=lambda t, a, b: [{"o": 11, "h": 11.5, "l": 7.9, "c": 8.5, "t": 0}])
    hour_row = _open_5m_row("AAA", DAY, id=7, bar_size_minutes=60)

    async def _open(bar_size_minutes=None):
        return [hour_row] if bar_size_minutes in (None, 60) else []
    monkeypatch.setattr(sot, "get_open_shadow_trades", _open)
    out = await sot.update_shadow_positions(DAY)
    assert out["no_data"] == 1 and cap.updates == []


# ── (4) the writes are prepared at deploy ────────────────────────────────────────────────


def test_shadow_lane_statements_are_in_the_deploy_preflight_registry():
    import agents.market_intelligence.db as db
    import scripts.preflight_db_updates as pf
    assert any(sql is db.SHADOW_TRADE_INSERT_SQL for _, sql in pf.SHADOW_WRITER_STATEMENTS)
    assert any(sql is db.SHADOW_TRADE_EXIT_STEP_UPDATE_SQL for _, sql in pf.SHADOW_WRITER_STATEMENTS)
    assert "$2::jsonb" in db.SHADOW_TRADE_EXIT_STEP_UPDATE_SQL and "WHERE id = $1" in db.SHADOW_TRADE_EXIT_STEP_UPDATE_SQL


def test_update_sql_builder_numbers_params_contiguously_and_drops_unknown_keys():
    import agents.market_intelligence.db as db
    sql, values = db.shadow_trade_update_sql({"bogus": 1, "status": "closed", "exits": [{"a": 1}]})
    assert sql == "UPDATE mi_orb_shadow_trades SET status = $2, exits = $3::jsonb WHERE id = $1"
    assert values[0] == "closed" and len(values) == 2
    assert db.shadow_trade_update_sql({"bogus": 1}) == (None, [])


# ── (5) the population query names both bar sizes and the lookback ───────────────────────


@pytest.mark.asyncio
async def test_hour_lane_population_is_5m_rows_without_a_60m_sibling(monkeypatch):
    import agents.market_intelligence.db as db
    import scripts.preflight_db_updates as pf
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[
        {"ticker": "AAA", "alert_date": DAY, "signal_type": "magna53", "shape_tag": None,
         "score_tier": "HIGH", "atr_14": None}])
    monkeypatch.setattr(sot, "get_pool", AsyncMock(return_value=pool))
    rows = await sot._fetch_hour_lane_candidates(DAY)
    assert rows[0]["ticker"] == "AAA" and rows[0]["atr_14"] is None
    sql, *args = conn.fetch.call_args.args
    assert args == [DAY, 5, 60, 14]
    assert sql is db.SHADOW_HOUR_LANE_CANDIDATES_SQL
    assert "hour.id IS NULL" in sql and "LEFT JOIN mi_orb_shadow_trades hour" in sql
    assert any(s is db.SHADOW_HOUR_LANE_CANDIDATES_SQL for _, s in pf.SHADOW_WRITER_STATEMENTS)
    assert sot.HOUR_LANE_LOOKBACK_DAYS >= 2 * sot.HOUR_GAP_RETRY_SESSIONS   # a gap row stays in reach


# ── (6) a LATE fill (the backfill) is caught up through yesterday, never quarantined ─────


def _ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=ET).timestamp() * 1000)


@pytest.mark.asyncio
async def test_late_fill_is_walked_through_yesterday_so_the_stale_guard_passes(monkeypatch):
    """Alert Tue 10-20, recorded the following Tue night (the 14-day backfill). The four sessions
    10-21..10-26 are walked at write time; the row then steps tonight like any other and
    `detect_stale_for_step` sees a current row (the quarantine the advisor review traced)."""
    alert, today = date(2026, 10, 20), date(2026, 10, 27)
    history = {date(2026, 10, 21): (10.8, 10.9), date(2026, 10, 22): (10.6, 11.1),
               date(2026, 10, 23): (10.9, 11.3), date(2026, 10, 26): (11.0, 11.4),
               date(2026, 10, 27): (11.2, 11.6)}         # (low, close); none breaches the 8.0 stop
    calls: list = []

    async def _daily(ticker, a, b):
        calls.append((a, b))
        return [{"o": c, "h": c, "l": l, "c": c, "t": _ms(d)} for d, (l, c) in history.items()
                if a <= d.isoformat() <= b]
    cap = _Captured()
    _patch_common(monkeypatch, cap, minute_bars=lambda t, d, s, e: _hour_day(alert, cross=(10, 45)),
                  daily_bars=_daily)
    monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=[_five_row("AAA", alert)]))
    counts = await sot.run_shadow_hour_pass(today)
    assert counts["open"] == 1
    assert calls == [("2026-10-21", "2026-10-26")]            # through YESTERDAY, never today
    (trade_id, fields), = cap.updates
    assert fields["running_closes"] == [10.9, 11.1, 11.3, 11.4]
    assert fields["hold_days"] == (date(2026, 10, 26) - alert).days
    assert 0 < fields["remaining_shares"] <= 1.0 and "status" not in fields   # the ladder's own partial may fire
    stale, _ = sot.detect_stale_for_step(alert, fields["hold_days"], today)
    assert stale is False


@pytest.mark.asyncio
async def test_late_fill_stopped_out_in_a_missed_session_closes_at_write_time(monkeypatch):
    alert, today = date(2026, 10, 20), date(2026, 10, 27)

    async def _daily(ticker, a, b):
        return [{"o": 10, "h": 10, "l": 7.5, "c": 8.0, "t": _ms(date(2026, 10, 21))}]
    cap = _Captured()
    _patch_common(monkeypatch, cap, minute_bars=lambda t, d, s, e: _hour_day(alert, cross=(10, 45)),
                  daily_bars=_daily)
    monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=[_five_row("AAA", alert)]))
    await sot.run_shadow_hour_pass(today)
    (_, fields), = cap.updates
    assert fields["status"] == "closed" and fields["exits"][0]["reason"] == "stop_hit"
    assert fields["total_pnl"] == pytest.approx(8.0 - 11.0)    # one unit → −1R in risk_dollars terms


@pytest.mark.asyncio
async def test_fills_with_no_missed_session_are_not_caught_up(monkeypatch):
    """Today's alert has no missed session; yesterday's is covered by tonight's exit step; and a
    Friday alert recorded on Monday has no session between them either — the calendar gap is not a
    missed session, so no history is read and the row is inserted open as it is."""
    for alert, today in ((DAY, DAY), (DAY - timedelta(days=1), DAY),
                         (date(2026, 10, 23), date(2026, 10, 26))):          # Fri → Mon
        daily = AsyncMock(return_value=[])
        cap = _Captured()
        _patch_common(monkeypatch, cap, minute_bars=lambda t, d, s, e, a=alert: _hour_day(a, cross=(10, 45)),
                      daily_bars=daily)
        monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=[_five_row("AAA", alert)]))
        counts = await sot.run_shadow_hour_pass(today)
        assert counts["open"] == 1 and cap.updates == [] and not daily.called, (alert, today)


@pytest.mark.asyncio
async def test_late_fill_with_no_history_is_deferred_then_recorded_never_inserted_open(monkeypatch):
    """Review F1: a late fill whose exit history comes back empty (Polygon swallows errors into [])
    writes NOTHING — an `open` row with no catch-up would be quarantined by the exit step's stale
    guard on its first step and never retried. It is deferred (retried nightly) and, once the alert
    is HOUR_GAP_RETRY_SESSIONS old, recorded gate_blocked with the missing history named, the fill
    facts (hour bar, trigger minute) kept, and no entry price."""
    alert = date(2026, 10, 20)
    for today, expect in ((date(2026, 10, 23), "deferred"), (date(2026, 10, 27), "gate_blocked")):
        cap = _Captured()
        _patch_common(monkeypatch, cap, minute_bars=lambda t, d, s, e: _hour_day(alert, cross=(10, 45)),
                      daily_bars=AsyncMock(return_value=[]))
        monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=[_five_row("AAA", alert)]))
        counts = await sot.run_shadow_hour_pass(today)
        assert counts[expect] == 1 and cap.updates == [], today
        assert not any(r["status"] == "open" for r in cap.inserts)
    (row,) = cap.inserts
    assert row["status"] == "gate_blocked"
    assert row["skip_reason"].startswith("infra:no_bar: exit_history:2026-10-21..2026-10-26:0_session_bar(s)")
    assert "stale resume guard" in row["skip_reason"] and row["skip_reason"].endswith("(unresolved after 5 sessions)")
    assert row["trigger_minute_et"] == time(10, 45) and row["orb_high"] == 11.0
    assert row["entry_price"] is None and row["hard_stop"] is None and row["remaining_shares"] == 0


@pytest.mark.asyncio
async def test_late_fill_partial_history_is_judged_by_the_exit_steps_own_stale_guard(monkeypatch):
    """Alert Tue 10-20. Recorded Mon 10-26 with history that stops at 10-21, the row would be two
    sessions behind — the exit step would quarantine it, so it is deferred (still inside the retry
    window). Recorded Tue 10-27 with history through 10-23 (10-26 missing) it is one session behind,
    which the same guard tolerates — inserted open with the three sessions walked."""
    alert = date(2026, 10, 20)

    def _hist(days):
        async def _daily(ticker, a, b):
            return [{"o": 11, "h": 11.2, "l": 10.8, "c": 11.0, "t": _ms(d)} for d in days]
        return _daily
    cap = _Captured()
    _patch_common(monkeypatch, cap, minute_bars=lambda t, d, s, e: _hour_day(alert, cross=(10, 45)),
                  daily_bars=_hist([date(2026, 10, 21)]))
    monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=[_five_row("AAA", alert)]))
    counts = await sot.run_shadow_hour_pass(date(2026, 10, 26))
    assert counts["deferred"] == 1 and cap.inserts == [] and cap.updates == []
    today = date(2026, 10, 27)
    cap = _Captured()
    _patch_common(monkeypatch, cap, minute_bars=lambda t, d, s, e: _hour_day(alert, cross=(10, 45)),
                  daily_bars=_hist([date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)]))
    monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=[_five_row("AAA", alert)]))
    counts = await sot.run_shadow_hour_pass(today)
    assert counts["open"] == 1
    (_, fields), = cap.updates
    assert len(fields["running_closes"]) == 3 and fields["hold_days"] == 3
    assert sot.detect_stale_for_step(alert, fields["hold_days"], today) == (False, None)


@pytest.mark.asyncio
async def test_the_open_row_and_its_catch_up_are_written_together_after_every_read(monkeypatch):
    """Review F1's shape: the minute bars and the exit history are both read before the INSERT, and
    the catch-up UPDATE follows the INSERT in the same candidate — never an open row alone."""
    alert, today = date(2026, 10, 20), date(2026, 10, 27)
    order: list[str] = []
    cap = _Captured()

    async def _minutes(t, d, s, e):
        order.append("minutes"); return _hour_day(alert, cross=(10, 45))

    async def _daily(t, a, b):
        order.append("history"); return [{"o": 11, "h": 11.2, "l": 10.8, "c": 11.0, "t": _ms(date(2026, 10, 26))}]

    async def _insert(row):
        order.append("insert"); return await cap.insert(row)

    async def _update(i, f):
        order.append("update"); return await cap.update(i, f)
    _patch_common(monkeypatch, cap, minute_bars=_minutes, daily_bars=_daily)
    monkeypatch.setattr(sot, "insert_shadow_trade", _insert)
    monkeypatch.setattr(sot, "update_shadow_trade", _update)
    monkeypatch.setattr(sot, "_fetch_hour_lane_candidates", AsyncMock(return_value=[_five_row("AAA", alert)]))
    assert (await sot.run_shadow_hour_pass(today))["open"] == 1
    assert order == ["minutes", "history", "insert", "update"]


# ── (7) one walk, under broker/, for both recorders ──────────────────────────────────────


def test_the_hour_bar_walk_is_one_pure_broker_module_shared_by_both_recorders():
    """Review F4: the tracker is imported lazily by its jobs, so nothing it imports is seen by the
    execution deploy-scope derivation — the walk lives under broker/ (execution-routed by definition)
    and is imported at TOP level by the tracker; the book recorder re-exports the same objects."""
    import types
    from agents.market_intelligence import book_geometry_arms as bga
    from agents.market_intelligence.broker import hour_bar_walk as hbw
    # the tracker binds the walk at MODULE level — a lazy import inside the pass would leave no attribute
    assert sot.classify_hour_entry is hbw.classify_hour_entry and sot.session_close_et is hbw.session_close_et
    for name in ("stop_limit_buy_price", "entry_walk", "first_hour_frame", "session_close_et",
                 "classify_hour_entry", "FIRST_HOUR_END", "MIN_HOUR_BARS", "NO_ENTRY_HOUR"):
        assert getattr(bga, name) is getattr(hbw, name), name
    # pure: nothing from the package is bound in its namespace (no DB, no Alpaca client, no trade state)
    bound = {v.__name__ for v in vars(hbw).values() if isinstance(v, types.ModuleType)}
    assert bound == {"logging"}, bound
    assert not any(getattr(v, "__module__", "").startswith("agents.") for v in vars(hbw).values()
                   if callable(v) and getattr(v, "__module__", None) != hbw.__name__)
