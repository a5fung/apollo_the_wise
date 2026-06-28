"""#356 Phase 3 — HTF breakout-entry SHADOW.

The load-bearing nuance: settlement uses entry=base_high (the stop-limit-buy FILL), NOT the bar close
(anticipation.entry_bet_outcome hardcodes entry=bars[idx]['c']) — and the break day itself is in the
forward window (the fill is intraday). The order geometry records would-be REJECTS (would_reject_reason),
never drops them. SHADOW only — no order is ever submitted.
"""
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.flag_detector import _htf_settle_from_bars


def _bar(d, c, h, l):
    return {"date": d, "c": c, "h": h, "l": l}


def test_settle_uses_base_high_entry_not_close():
    # entry=base_high=100, stop=94 -> risk=6, 3R target=118. The break day CLOSES at 105, but the
    # entry is the FILL at 100 — if it wrongly used the close, risk/tgt/fwd_mfe_r would all differ.
    bars = [_bar("2026-06-01", 105, 101, 99),    # break day (close 105, but entry = base_high 100)
            _bar("2026-06-02", 110, 120, 108)]   # high 120 >= tgt 118 -> capture
    res = _htf_settle_from_bars(bars, 0, entry_price=100.0, stop=94.0, target_r=3.0, window=1)
    assert res is not None
    assert res["outcome"] == "capture"
    assert res["realized_r"] == 3.0
    assert res["fwd_mfe_r"] == pytest.approx(3.33, abs=0.01)   # (120-100)/6 — pins entry=100, not 105


def test_settle_stop_on_break_day_itself():
    # the break day fills at base_high then reverses through the stop -> stop, -1R (break-day inclusive)
    bars = [_bar("2026-06-01", 95, 101, 93)]     # low 93 <= stop 94 on the break day
    res = _htf_settle_from_bars(bars, 0, entry_price=100.0, stop=94.0, target_r=3.0, window=5)
    assert res is not None
    assert res["outcome"] == "stop"
    assert res["realized_r"] == -1.0


def test_settle_abstains_when_window_incomplete():
    # neither target nor stop hit + window not elapsed -> None (provisional, retry next run)
    bars = [_bar("2026-06-01", 101, 102, 99)]
    assert _htf_settle_from_bars(bars, 0, entry_price=100.0, stop=94.0, target_r=3.0, window=12) is None


def test_settle_none_when_stop_ge_entry():
    bars = [_bar("2026-06-01", 100, 101, 99)]
    assert _htf_settle_from_bars(bars, 0, entry_price=100.0, stop=100.0, target_r=3.0, window=5) is None


@pytest.mark.asyncio
async def test_order_records_reject_never_drops():
    from agents.market_intelligence.broker.order_manager import prepare_htf_breakout_order
    # base_low is 30% below entry -> stop distance > 8% cap -> would_reject set, but spec STILL returned
    spec, wreject = prepare_htf_breakout_order(base_high=100.0, base_low=70.0)
    assert spec is not None
    assert spec["entry_price"] == 100.0
    assert wreject == "stop_distance_gt_8pct"


@pytest.mark.asyncio
async def test_order_picks_tightest_stop_within_cap():
    from agents.market_intelligence.broker.order_manager import prepare_htf_breakout_order
    # base_low 90 (10% -> over cap), sma_10 96 (4% -> within), sma_20 93 (7% -> within)
    # tightest-within-cap = sma_10 (the highest stop that still respects the cap)
    spec, wreject = prepare_htf_breakout_order(base_high=100.0, base_low=90.0, sma_10=96.0, sma_20=93.0)
    assert spec["stop_kind"] == "sma_10"
    assert spec["stop_loss_price"] == 96.0
    assert wreject is None
    assert spec["notional_basis"] == 100_000.0   # fixed notional, no live equity


@pytest.mark.asyncio
async def test_insert_idempotent(monkeypatch):
    from tests.conftest import make_mock_pool
    from agents.market_intelligence import db as dbmod
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(side_effect=[{"id": 1}, None])   # 1st = new row, 2nd = ON CONFLICT no-op
    monkeypatch.setattr(dbmod, "get_pool", AsyncMock(return_value=pool))
    kw = dict(break_time=None, parent_scan_date=None, parent_stage="COILED", base_high=100.0,
              base_low=94.0, base_age=5, runup_pct=120.0, flagpole_ratio=None, flag_depth_pct=None,
              rmv_5d=None, rmv_15d=None, range_contraction_ratio=None, vol_contraction_ratio=None,
              atr_14=None, entry_price=100.0, limit_price=100.5, stop_loss_price=94.0, stop_kind="base_low",
              max_loss_pct=0.06, risk_per_share=6.0, risk_dollars=600.0, shares=100, position_size=10000.0,
              notional_basis=100_000.0, would_reject_reason=None, minutes_since_open=30,
              today_volume=1_000_000, adv_20=500_000, volume_pct_of_adv=200.0, target_r=3.0)
    assert await dbmod.insert_htf_breakout_shadow("XYZ", "2026-06-28", **kw) is True
    assert await dbmod.insert_htf_breakout_shadow("XYZ", "2026-06-28", **kw) is False
