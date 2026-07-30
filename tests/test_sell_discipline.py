"""#508 WS1 — unified sell-discipline RECORDER tests. Pins the pure compute (both peak axes,
the WHEN-attribution ladder, the R frame) on the REAL live-cohort shapes (QBTS / SMCI / MANE,
prod values 2026-07-30), the renderer contract (monospace block, no pipe tables, honesty
marker for extremes-sourced peaks), the write half (mocked pool — the #173 0-rows lesson),
and that the section rides the mgmt-judge Telegram in every branch. NO exit rule anywhere —
this surface records and displays only (THE LINE)."""
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import sell_discipline as sd
from agents.market_intelligence.sell_discipline import (
    compute_sell_record, format_sell_discipline_section, trade_risk_per_share)

_ET = ZoneInfo("America/New_York")


def _et(y, m, d, hh, mm, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=_ET)


# ── real cohort fixtures (prod mi_live_trades values, read 2026-07-30) ───────────────────

def _qbts():
    # Filled 07-27 09:31 ET, peaked +3.74R at the day-1 16:00 bar, held overnight UNBANKED,
    # stopped −1.00R 09:36 day 2 — the trade that motivated this recorder.
    return {
        "id": 279, "ticker": "QBTS", "signal_type": "magna53", "account_mode": "live",
        "alert_date": date(2026, 7, 27), "entry_price": 18.17, "hard_stop": 17.75,
        "entry_shares": 53, "total_pnl": -22.26, "stop_price": 17.75,
        "breakeven_active": False, "partial_taken": False, "highest_price_seen": 19.74,
        "filled_at": _et(2026, 7, 27, 9, 31, 31), "closed_at": _et(2026, 7, 28, 9, 36, 25),
        "pnl_attribution": None,
    }


_QBTS_DAILY = [
    {"trade_date": date(2026, 7, 27), "high_price": 19.54, "close": 19.51},
    {"trade_date": date(2026, 7, 28), "high_price": 18.89, "close": 17.635},
]


def _smci():
    # Filled 07-22, peak 32.585 printed on hold-day 2 (07-23), closed 07-27 −0.70R.
    # Pre-07-25 trade → NO usable minute bars; peak day recovered from the daily-high match.
    return {
        "id": 271, "ticker": "SMCI", "signal_type": "magna53", "account_mode": "live",
        "alert_date": date(2026, 7, 22), "entry_price": 29.47, "hard_stop": 28.5,
        "entry_shares": 22, "total_pnl": -14.96, "stop_price": 28.5,
        "breakeven_active": False, "partial_taken": False, "highest_price_seen": 32.585,
        "filled_at": _et(2026, 7, 22, 9, 33, 30), "closed_at": _et(2026, 7, 27, 10, 37, 45),
        "pnl_attribution": None,
    }


_SMCI_DAILY = [
    {"trade_date": date(2026, 7, 22), "high_price": 32.2844, "close": 30.56},
    {"trade_date": date(2026, 7, 23), "high_price": 32.585, "close": 31.2},
    {"trade_date": date(2026, 7, 24), "high_price": 31.33, "close": 30.1},
    {"trade_date": date(2026, 7, 27), "high_price": 30.94, "close": 29.81},
]


def _mane():
    # +7.92R day-1 excursion, held overnight, exited −0.23R at next open. Peak fell on the
    # FILL day — only the extremes value + the fill-day high corroboration can date it.
    return {
        "id": 261, "ticker": "MANE", "signal_type": "magna53", "account_mode": "live",
        "alert_date": date(2026, 7, 15), "entry_price": 119.34, "hard_stop": 118.02,
        "entry_shares": 8, "total_pnl": -2.40, "stop_price": 118.02,
        "breakeven_active": False, "partial_taken": False, "highest_price_seen": 129.80,
        "filled_at": _et(2026, 7, 15, 9, 33, 2), "closed_at": _et(2026, 7, 16, 9, 30, 6),
        "pnl_attribution": None,
    }


_MANE_DAILY = [
    {"trade_date": date(2026, 7, 15), "high_price": 129.8, "close": 123.7},
    {"trade_date": date(2026, 7, 16), "high_price": 125.165, "close": 105.83},
]


# ── the R frame ──────────────────────────────────────────────────────────────────────────

def test_risk_uses_hard_stop_then_orb_low():
    assert trade_risk_per_share({"entry_price": 18.17, "hard_stop": 17.75}) == pytest.approx(0.42)
    # hard_stop missing → orb_low fallback (9M-class rows)
    assert trade_risk_per_share({"entry_price": 10.0, "hard_stop": None, "orb_low": 9.5}) == 0.5
    # NEVER a zero/negative denominator (the ADR 0014 trailed-stop trap)
    assert trade_risk_per_share({"entry_price": 10.0, "hard_stop": 10.0}) is None
    assert trade_risk_per_share({"entry_price": 10.0, "hard_stop": 11.0, "orb_low": 12.0}) is None


def test_compute_returns_none_without_r_frame_or_round_trip():
    t = _qbts()
    t["hard_stop"] = t["entry_price"]  # no valid risk
    assert compute_sell_record(t, daily_rows=_QBTS_DAILY) is None
    t2 = _qbts()
    t2["closed_at"] = None  # not a completed round trip
    assert compute_sell_record(t2, daily_rows=_QBTS_DAILY) is None


# ── QBTS: minute-bar WHEN + the unbanked overnight close axis ────────────────────────────

def test_qbts_record_minute_bar_when_and_close_axis():
    rec = compute_sell_record(
        _qbts(),
        minute_peak=(19.74, _et(2026, 7, 27, 16, 0)), minute_bars_n=391,
        daily_rows=_QBTS_DAILY,
        decisions=[{"decision_date": date(2026, 7, 27), "verdict": "TRAIL_TIGHTEN",
                    "r_multiple": 2.73, "stop_above_entry": False}],
    )
    assert rec["realized_r"] == pytest.approx(-1.0, abs=0.001)          # what we KEPT
    assert rec["peak_r"] == pytest.approx(3.738, abs=0.001)             # what it REACHED
    assert rec["peak_source"] == "minute_bars"
    assert rec["peak_day"] == date(2026, 7, 27) and rec["peak_hold_day"] == 1
    assert rec["peak_time"].astimezone(_ET).strftime("%H:%M") == "16:00"
    # daily-close axis: +3.19R was STILL ON THE TABLE at the day-1 close (unbanked overnight)
    assert rec["peak_close_r"] == pytest.approx(3.190, abs=0.001)
    assert rec["peak_close_day"] == date(2026, 7, 27)
    assert rec["giveback_r"] == pytest.approx(4.738, abs=0.001)
    assert rec["hold_trading_days"] == 2
    assert rec["stop_above_entry_ever"] is False and rec["partial_taken"] is False
    # judge context: TRAIL_TIGHTEN at +2.73R the day before the round trip completed
    assert rec["judge_last_verdict"] == "TRAIL_TIGHTEN"
    assert rec["judge_first_warn_verdict"] == "TRAIL_TIGHTEN"
    assert rec["judge_first_warn_r"] == pytest.approx(2.73)


# ── SMCI: pre-07-25 trade — day-granularity WHEN from the daily-high match ───────────────

def test_smci_record_daily_high_when_no_minute_precision():
    rec = compute_sell_record(
        _smci(),
        minute_peak=(29.48, _et(2026, 7, 22, 9, 30)), minute_bars_n=1,  # fill-seed bar only
        daily_rows=_SMCI_DAILY,
        decisions=[
            {"decision_date": date(2026, 7, 22), "verdict": "HOLD", "r_multiple": 1.18,
             "stop_above_entry": False},
            {"decision_date": date(2026, 7, 23), "verdict": "HOLD", "r_multiple": 1.65,
             "stop_above_entry": False},
            {"decision_date": date(2026, 7, 24), "verdict": "HOLD", "r_multiple": 0.77,
             "stop_above_entry": False},
        ],
    )
    assert rec["realized_r"] == pytest.approx(-0.701, abs=0.001)
    assert rec["peak_r"] == pytest.approx(3.211, abs=0.001)
    # the middle-day (07-23) session high == the extremes value → day-level WHEN, no fake time
    assert rec["peak_source"] == "daily_high+extremes"
    assert rec["peak_day"] == date(2026, 7, 23) and rec["peak_hold_day"] == 2
    assert rec["peak_time"] is None
    assert rec["peak_close_r"] == pytest.approx(1.784, abs=0.001)       # close axis saw +1.78R
    assert rec["hold_trading_days"] == 4
    assert rec["judge_verdicts_n"] == 3 and rec["judge_last_verdict"] == "HOLD"
    assert rec["judge_first_warn_verdict"] is None                       # judge never warned


# ── MANE: fill-day peak — extremes value corroborated by the fill-day session high ───────

def test_mane_record_fill_day_peak_and_close_axis():
    rec = compute_sell_record(_mane(), minute_peak=None, minute_bars_n=1,
                              daily_rows=_MANE_DAILY, decisions=[])
    assert rec["peak_r"] == pytest.approx(7.924, abs=0.001)
    assert rec["peak_source"] == "extremes+daily"
    assert rec["peak_day"] == date(2026, 7, 15) and rec["peak_hold_day"] == 1
    assert rec["peak_time"] is None                                      # no minute bars → no fake time
    assert rec["realized_r"] == pytest.approx(-0.227, abs=0.001)
    assert rec["peak_close_r"] == pytest.approx(3.303, abs=0.001)        # +3.3R at the day-1 close
    assert rec["capture_pct"] == pytest.approx(-0.0287, abs=0.001)


# ── same-day round trip: the daily-close axis STRUCTURALLY cannot see it ─────────────────

def test_same_day_round_trip_close_axis_is_null_but_day_is_known():
    t = _qbts()
    t["closed_at"] = _et(2026, 7, 27, 9, 57)      # stopped 26 min after fill
    t["total_pnl"] = -22.26
    t["highest_price_seen"] = 18.4
    rec = compute_sell_record(t, minute_peak=None, minute_bars_n=0,
                              daily_rows=_QBTS_DAILY[:1], decisions=[])
    assert rec["peak_close"] is None and rec["peak_close_r"] is None     # invisible to close axis
    assert rec["peak_day"] == date(2026, 7, 27) and rec["peak_hold_day"] == 1
    assert rec["peak_source"] == "extremes"                              # value floor, timing unknown
    assert rec["hold_trading_days"] == 1


def test_no_peak_source_at_all_records_honest_none():
    t = _qbts()
    t["highest_price_seen"] = None
    t["closed_at"] = _et(2026, 7, 27, 9, 57)
    rec = compute_sell_record(t, minute_peak=None, minute_bars_n=0, daily_rows=[], decisions=[])
    assert rec["peak_price"] is None and rec["peak_r"] is None
    assert rec["peak_source"] == "none"
    assert rec["giveback_r"] is None and rec["capture_pct"] is None
    assert rec["realized_r"] == pytest.approx(-1.0, abs=0.001)           # kept is still recorded


def test_seed_bar_never_masquerades_as_minute_precision():
    # 1 in-hold bar whose high coincides with the peak must NOT claim bar-level WHEN.
    t = _qbts()
    t["closed_at"] = _et(2026, 7, 27, 9, 57)
    t["highest_price_seen"] = 18.4
    rec = compute_sell_record(t, minute_peak=(18.4, _et(2026, 7, 27, 9, 30)),
                              minute_bars_n=1, daily_rows=[], decisions=[])
    assert rec["peak_source"] == "extremes"
    assert rec["peak_time"] is None


def test_stop_above_entry_folds_trade_row_and_judge_rows():
    t = _smci()
    rec = compute_sell_record(t, daily_rows=_SMCI_DAILY, decisions=[
        {"decision_date": date(2026, 7, 23), "verdict": "HOLD", "r_multiple": 1.0,
         "stop_above_entry": True}])
    assert rec["stop_above_entry_ever"] is True                          # from a judged day
    t2 = _smci()
    t2["stop_price"] = 30.0                                              # final stop above entry
    rec2 = compute_sell_record(t2, daily_rows=_SMCI_DAILY, decisions=[])
    assert rec2["stop_above_entry_ever"] is True


# ── renderer: monospace block, no pipe tables, honesty marker ────────────────────────────

def _render_data():
    return {
        "open_lines": [" FTNT  d0  peak +0.1R → now +0.1R  stop -1.0R"],
        "provisional": [{"ticker": "WKC", "peak_r": 0.9, "realized_r": -1.02}],
        "recorded": [
            {"ticker": "QBTS", "close_day": date(2026, 7, 28), "peak_r": 3.74,
             "peak_hold_day": 1, "peak_time": _et(2026, 7, 27, 16, 0), "realized_r": -1.0,
             "peak_source": "minute_bars", "account_mode": "live",
             "judge_last_verdict": "TRAIL_TIGHTEN", "judge_last_verdict_r": 2.73},
            {"ticker": "SMCI", "close_day": date(2026, 7, 27), "peak_r": 3.21,
             "peak_hold_day": 2, "peak_time": None, "realized_r": -0.7,
             "peak_source": "extremes", "account_mode": "live",
             "judge_last_verdict": "HOLD", "judge_last_verdict_r": 0.77},
        ],
        "live_cohort": {"n": 11, "wins": 0, "reached_avg": 1.83, "kept_avg": -0.92,
                        "partials": 0, "stop_above": 0,
                        "regimes": [("Correcting", 6, -5.82), ("Choppy", 4, -3.29),
                                    ("Bull", 1, -1.0)]},
        "cohorts": [{"signal_type": "magna53", "account_mode": "paper", "n": 26,
                     "reached_avg": 1.1, "kept_avg": -0.4}],
        "shadow": {"consol": [("anticipate", 118, 2.44, -0.27), ("confirm", 43, 0.7, -0.1)],
                   "htf": (2, 0.51, -1.0), "wick": (65, 8.1, 2.3),
                   "giveback_n": 1, "pivot_n": 8},
    }


def test_renderer_full_surface():
    out = format_sell_discipline_section(_render_data())
    assert out.startswith("📼 *Sell discipline — reached vs kept*")
    assert "no rule" in out                                              # the scope disclaimer renders
    assert out.count("```") == 2                                         # ONE monospace block
    assert "|" not in out                                                # Telegram can't render pipes
    assert "QBTS" in out and "+3.7R d1 16:00" in out and "TT@+2.7R" in out
    assert "~+3.2R d2" in out                                            # extremes peak carries ~
    assert "extremes-poll peak" in out                                   # …and the footnote explains it
    assert "Correcting 6" in out and "regime@entry" in out               # reconstructed, not stored
    assert "consol-anticipate" in out and "wick (pct frame)" in out
    assert "giveback n=1 · pivot n=8" in out
    assert len(out) < 2500                                               # rides the 4096-char digest


def test_renderer_empty_returns_empty():
    assert format_sell_discipline_section({}) == ""
    assert format_sell_discipline_section({"open_lines": [], "recorded": []}) == ""


def test_renderer_no_footnote_without_approx_lines():
    data = {"recorded": [{"ticker": "QBTS", "close_day": date(2026, 7, 28), "peak_r": 3.74,
                          "peak_hold_day": 1, "peak_time": _et(2026, 7, 27, 16, 0),
                          "realized_r": -1.0, "peak_source": "minute_bars",
                          "account_mode": "live", "judge_last_verdict": None}]}
    out = format_sell_discipline_section(data)
    assert "extremes-poll peak" not in out


# ── write half: mocked pool (the #173 0-rows lesson — pin the INSERT wiring) ─────────────

@pytest.mark.asyncio
async def test_record_sell_discipline_writes_row_and_audits(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[
        [_qbts()],                # the catch-up scan
        _QBTS_DAILY,              # daily rows
        [],                       # decisions
    ])
    conn.fetchrow = AsyncMock(return_value={"high": 19.74, "bar_time": _et(2026, 7, 27, 16, 0)})
    conn.fetchval = AsyncMock(return_value=391)
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(sd, "get_pool", AsyncMock(return_value=pool))
    audit = AsyncMock()
    monkeypatch.setattr(sd, "log_audit_event", audit)

    n = await sd.record_sell_discipline(date(2026, 7, 30))
    assert n == 1
    ins = conn.execute.await_args_list[0]
    assert "INSERT INTO mi_sell_discipline_records" in ins.args[0]
    assert "ON CONFLICT (trade_id) DO NOTHING" in ins.args[0]            # idempotent re-runs
    assert len(ins.args) - 1 == 37                                       # every column bound
    assert ins.args[1] == 279 and ins.args[2] == "QBTS"                  # trade_id, ticker
    audit.assert_awaited()                                               # loud on success too
    # the scan SQL carries the explicit casts (the date>=integer prod-crash class)
    scan_sql = conn.fetch.await_args_list[0].args[0]
    assert "$1::date - $2::int" in scan_sql


@pytest.mark.asyncio
async def test_record_sell_discipline_skips_no_r_frame_loudly(monkeypatch):
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    bad = _qbts()
    bad["hard_stop"] = bad["entry_price"]
    bad["orb_low"] = None
    conn.fetch = AsyncMock(side_effect=[[bad], [], []])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    conn.execute = AsyncMock()
    monkeypatch.setattr(sd, "get_pool", AsyncMock(return_value=pool))
    audit = AsyncMock()
    monkeypatch.setattr(sd, "log_audit_event", audit)

    n = await sd.record_sell_discipline(date(2026, 7, 30))
    assert n == 0
    conn.execute.assert_not_awaited()                                    # no junk row
    assert any("sell_discipline_record_skipped" in c.args[0]
               for c in audit.await_args_list)                           # …but never silent


# ── the surface rides the judge Telegram in every branch ─────────────────────────────────

@pytest.mark.asyncio
async def test_mgmt_judge_appends_section_when_no_positions(monkeypatch):
    from agents.market_intelligence import mgmt_judge as mj
    monkeypatch.setattr("agents.market_intelligence.db.get_open_live_trades",
                        AsyncMock(return_value=[]))
    monkeypatch.setattr("agents.market_intelligence.collector.et_today",
                        lambda: date(2026, 7, 30))
    monkeypatch.setattr(
        "agents.market_intelligence.sell_discipline.build_sell_discipline_section",
        AsyncMock(return_value="📼 SECTION"))
    text = await mj.run_position_mgmt_judge(send=False)
    assert "no open positions" in text
    assert text.endswith("📼 SECTION")                                    # unified surface, one message


@pytest.mark.asyncio
async def test_mgmt_judge_section_failure_is_loud_not_blocking(monkeypatch):
    from agents.market_intelligence import mgmt_judge as mj
    monkeypatch.setattr("agents.market_intelligence.db.get_open_live_trades",
                        AsyncMock(return_value=[]))
    monkeypatch.setattr("agents.market_intelligence.collector.et_today",
                        lambda: date(2026, 7, 30))
    monkeypatch.setattr(
        "agents.market_intelligence.sell_discipline.build_sell_discipline_section",
        AsyncMock(side_effect=RuntimeError("boom")))
    audit = AsyncMock()
    monkeypatch.setattr("agents.market_intelligence.db.log_audit_event", audit)
    text = await mj.run_position_mgmt_judge(send=False)
    assert "no open positions" in text                                    # the judge digest survives
    assert "surface failed" in text                                       # and says so
    assert any("sell_discipline_surface_error" in c.args[0]
               for c in audit.await_args_list)                            # audited, never swallowed
