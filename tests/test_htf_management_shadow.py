"""#396 HTF Phase 4 — EMA-trail MANAGEMENT shadow.

Pins the lifecycle replay (`_htf_management_replay`): scale 33-50% into strength day 3-5 ->
breakeven -> trail the runner on the 10/20 EMA (exit only on a daily close below) -> hard
max-loss stop. Distinct from Phase 3's fixed-3R capture/stop bet (_htf_settle_from_bars,
tests/test_htf_breakout_shadow.py) — this replays the ACTUAL sourced management protocol, not a
fixed-target bet. The EMA arithmetic itself is pinned separately (tests/test_exit_logic.py); these
tests pin the LIFECYCLE (event sequence + terminal status + share accounting), using constant
post-entry closes so the EMA trail is trivially known (a constant series' EMA == that constant).
"""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.flag_detector import _htf_management_replay


def _bar(d, c, h=None, l=None):
    return {"date": d, "o": c, "h": h if h is not None else c,
            "l": l if l is not None else c, "c": c, "v": 1e6}


def _daterange_bars(start_ordinal_offset_days, closes):
    """Bars for consecutive calendar days starting the day AFTER entry (2026-06-01)."""
    base = date(2026, 6, 1)
    out = []
    for i, c in enumerate(closes, start=1):
        from datetime import timedelta
        out.append(_bar((base + timedelta(days=i)).isoformat(), c))
    return out


def test_abstains_when_stop_at_or_above_entry():
    bars = [_bar("2026-06-01", 100.0), _bar("2026-06-02", 101.0)]
    assert _htf_management_replay(bars, 0, entry_price=100.0, initial_stop=100.0,
                                  shares=100.0) is None


def test_still_open_before_scale_window_with_only_entry_event():
    # Only 1 forward bar (hold_days=1) — nowhere near the day-3 scale window.
    bars = [_bar("2026-06-01", 100.0), _bar("2026-06-02", 102.0)]
    res = _htf_management_replay(bars, 0, entry_price=100.0, initial_stop=90.0, shares=100.0)
    assert res["status"] == "open"
    assert res["events"] == [{"date": "2026-06-01", "type": "entry", "price": 100.0, "shares": 100.0}]
    assert res["remaining_shares"] == 100.0
    assert res["realized_r"] == 0.0


def test_hard_stop_fires_before_any_scale():
    # Day 1 gaps straight through the hard stop — no scale-out ever gets a chance to fire.
    bars = [_bar("2026-06-01", 100.0), _bar("2026-06-02", 80.0, h=85.0, l=80.0)]
    res = _htf_management_replay(bars, 0, entry_price=100.0, initial_stop=90.0, shares=100.0)
    assert res["status"] == "closed_hard_stop"
    types = [e["type"] for e in res["events"]]
    assert types == ["entry", "hard_stop_exit"]
    assert res["remaining_shares"] == 0.0
    # backtest-pure semantics fill AT hard_stop (90), not the bar's actual close (80):
    # pnl = (90-100)*100 = -1000; risk-dollars = 10/share * 100 = 1000 -> -1R exactly.
    assert res["realized_r"] == pytest.approx(-1.0)


def test_full_lifecycle_scale_breakeven_then_trail_exit():
    # entry=100, stop=90 (risk 10/share), shares=100, scale_fraction default 0.40.
    # Days 1-20: constant close=110 -> scale fires the FIRST day the day>=3 gate opens (day 3;
    # close 110 > entry 100 satisfies the hold_days<=4 condition, so it needn't wait for the
    # hold_days>=5 forced branch) -> 40 shares out @110, 60 remain, breakeven floor=100.
    # By day 20 running_closes = [110]*20 -> ema10 == ema20 == 110 EXACTLY (a constant series'
    # EMA equals that constant — hand-computable, no float surprises).
    # Day 21 close drops to 95: effective_stop = max(hard_stop=90, ema~110, breakeven=100) = ~110
    # (EMA still dominates) -> 95 < effective_stop -> trail_exit at close=95 (NOT hard-stop;
    # bar_low defaults to close here, well above the 90 hard-stop floor).
    closes = [110.0] * 20 + [95.0]
    bars = [_bar("2026-06-01", 100.0)] + _daterange_bars(0, closes)
    res = _htf_management_replay(bars, 0, entry_price=100.0, initial_stop=90.0, shares=100.0)

    assert res["status"] == "closed_trail_exit"
    types = [e["type"] for e in res["events"]]
    assert types == ["entry", "scale_out", "breakeven", "trail_exit"]

    scale_evt = res["events"][1]
    assert scale_evt["shares"] == 40.0        # 100 * scale_fraction(0.40)
    assert scale_evt["price"] == 110.0

    be_evt = res["events"][2]
    assert be_evt["stop"] == 100.0             # breakeven floor = entry_price

    exit_evt = res["events"][3]
    assert exit_evt["price"] == 95.0
    assert exit_evt["shares"] == 60.0          # the remaining 60 (100 - 40 scaled out)

    assert res["remaining_shares"] == 0.0
    # realized_r = total pnl / (risk_per_share * initial shares) = total pnl / 1000
    # scale pnl = (110-100)*40 = 400; trail-exit pnl = (95-100)*60 = -300; total = 100
    assert res["realized_r"] == pytest.approx(0.10)


def test_variable_scale_fraction_and_trail_mode_are_wired_through():
    # scale_fraction=0.50 (the sourced upper bound) changes the scale-out size; passing
    # trail_mode explicitly should behave identically to the default (both are 'ema_10_20').
    bars = [_bar("2026-06-01", 100.0)] + _daterange_bars(0, [105.0] * 5)
    res = _htf_management_replay(bars, 0, entry_price=100.0, initial_stop=90.0, shares=100.0,
                                 scale_fraction=0.50, trail_mode="ema_10_20")
    scale_evt = next(e for e in res["events"] if e["type"] == "scale_out")
    assert scale_evt["shares"] == 50.0


# ── DB wiring (candidates query + idempotent upsert) — mocked pool ─────────


@pytest.mark.asyncio
async def test_upsert_management_shadow_writes_expected_params(monkeypatch):
    from tests.conftest import make_mock_pool
    from agents.market_intelligence import db as dbmod
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
    await dbmod.upsert_htf_management_shadow(
        1, "XYZ", "2026-06-28", entry_price=100.0, initial_stop=90.0, initial_shares=100.0,
        scale_fraction=0.40, trail_mode="ema_10_20", status="open", remaining_shares=100.0,
        partial_taken=False, breakeven_active=False,
        events=[{"date": "2026-06-28", "type": "entry", "price": 100.0, "shares": 100.0}],
        realized_r=None, last_bar_date=None,
    )
    assert conn.execute.await_count == 1
    args = conn.execute.await_args.args
    assert args[1] == 1               # shadow_id
    assert args[2] == "XYZ"           # ticker
    assert args[9] == "open"          # status


@pytest.mark.asyncio
async def test_get_management_shadow_candidates_queries_join(monkeypatch):
    from tests.conftest import make_mock_pool
    from agents.market_intelligence import db as dbmod
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[
        {"shadow_id": 1, "ticker": "XYZ", "break_date": date(2026, 6, 28),
         "entry_price": 100.0, "stop_loss_price": 90.0, "shares": 100},
    ])
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
    rows = await dbmod.get_htf_management_shadow_candidates()
    assert rows == [{"shadow_id": 1, "ticker": "XYZ", "break_date": date(2026, 6, 28),
                     "entry_price": 100.0, "stop_loss_price": 90.0, "shares": 100}]
    assert "LEFT JOIN mi_htf_management_shadow" in conn.fetch.await_args.args[0]
    assert "would_reject_reason IS NULL" in conn.fetch.await_args.args[0]
