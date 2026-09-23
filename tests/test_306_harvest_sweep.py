"""Unit tests for the pure replay/grid logic of scripts/_306_harvest_sweep.py
(ADR 0023 Card 2). Exercises the round-tripper lock, same-day short-circuit,
hard-stop baseline, and grid shape — no prod/Polygon needed.
"""
import importlib.util
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# module name starts with a digit → load by path
_spec = importlib.util.spec_from_file_location(
    "_306_harvest_sweep", REPO / "scripts" / "_306_harvest_sweep.py")
hs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hs)


def mkbar(ds, low, close):
    return {"date": ds, "date_obj": date.fromisoformat(ds),
            "o": close, "h": max(low, close), "l": low, "c": close, "v": 1e6}


def mktrade(**ov):
    t = {"ticker": "TST", "fill_date": "2026-05-01", "close_date": "2026-05-11",
         "account_mode": "paper", "entry_price": 100.0, "entry_shares": 90.0,
         "orig_stop": 95.0, "final_stop": 95.0, "partial_taken": True,
         "actual_pnl": 150.0, "peak_intraday": 120.0, "low_intraday": 96.0,
         "n_running_closes": 6}
    t.update(ov)
    return t


# A round-tripper: rise to 119 then fade. The lock should exit EARLIER and KEEP MORE.
ROUNDTRIP_BARS = {"TST": [
    mkbar("2026-05-04", 107, 109),   # day3: partial fires, arms +8%
    mkbar("2026-05-05", 117, 119),   # peak close 119
    mkbar("2026-05-06", 116, 118),
    mkbar("2026-05-07", 106, 108),   # fades below the +8%/50% floor (109.5) → lock here
    mkbar("2026-05-08",  98, 100),
    mkbar("2026-05-11",  96,  98),   # baseline rides down to here
]}

GAIN_8_50_SMA = {"a": {"kind": "gain", "val": 0.08, "floor": 0.50}, "b": "sma", "c": None,
                 "label": "lock +8%/50%·sma·⅓"}


def test_replay_giveback_locks_roundtripper_earlier_and_higher():
    # Baseline rides to the real exit (anchored to actual, marginal 0). The lock triggers an
    # EARLIER exit near the peak → positive marginal vs actual.
    t = mktrade()
    base = hs.replay(t, ROUNDTRIP_BARS, hs.BASELINE_CELL)
    gb = hs.replay(t, ROUNDTRIP_BARS, GAIN_8_50_SMA)
    assert base["early"] is False and base["alt_pnl"] == t["actual_pnl"]   # anchored to actual
    assert base["marginal"] == 0.0
    assert gb["early"] is True                                             # lock exited early
    assert gb["marginal"] > 0                                             # kept more than actual
    assert gb["alt_pnl"] > base["alt_pnl"]
    assert gb["exit_date"] < t["close_date"]                              # strictly before real exit
    assert gb["exit_reason"] == "sma_trail_stop"                          # lock raised effective_stop


def test_replay_same_day_shortcircuits_to_actual():
    t = mktrade(close_date="2026-05-01", partial_taken=False, actual_pnl=-450.0)
    r = hs.replay(t, {"TST": []}, GAIN_8_50_SMA)
    assert r["replayed"] is False
    assert r["alt_pnl"] == -450.0 and r["marginal"] == 0.0
    assert r["exit_reason"] == "same_day_actual"


def test_replay_non_triggering_rule_anchors_to_actual():
    # A trade that never triggers an earlier exit rides to its real outcome — NOT a force-close.
    t = mktrade(actual_pnl=777.0)
    # bars that never breach the stop and never fade below any floor before the real close
    bars = {"TST": [mkbar("2026-05-04", 101, 103), mkbar("2026-05-05", 102, 104),
                    mkbar("2026-05-06", 103, 105)]}       # close_date 05-11 > last bar
    r = hs.replay(t, bars, hs.BASELINE_CELL)
    assert r["early"] is False
    assert r["alt_pnl"] == 777.0 and r["marginal"] == 0.0
    assert r["exit_reason"] == "rode_to_actual"


def test_replay_early_hard_stop_is_flagged_and_uses_replay_pnl():
    # A backtest-pure hard-stop STRICTLY BEFORE the real close counts as an early exit at the stop.
    t = mktrade(actual_pnl=150.0)
    bars = {"TST": [mkbar("2026-05-04", 94, 96)]}          # low 94 <= stop 95, date < close 05-11
    r = hs.replay(t, bars, hs.BASELINE_CELL)
    assert r["early"] is True
    assert r["exit_reason"] == "stop_hit"
    assert r["alt_pnl"] == (95.0 - 100.0) * 90             # -450, full size at the stop
    assert r["marginal"] == -450.0 - 150.0


def test_r_arm_passes_risk_per_share():
    kw = hs._giveback_kwargs(
        {"a": {"kind": "r", "val": 2.0, "floor": 0.5}}, entry=100.0, orig_stop=95.0)
    assert kw["giveback_arm_r"] == 2.0
    assert kw["giveback_risk_per_share"] == 5.0            # entry - orig_stop
    assert kw["giveback_arm_gain"] is None


def test_build_grid_shape():
    grid = hs.build_grid()
    # (3 trails × 3 scales) no-lock cells + (4 arms × 3 floors × 3 trails × 3 scales) armed
    assert len(grid) == 3 * 3 + 4 * 3 * 3 * 3
    assert grid[0]["a"] is None                            # anchor baseline first
    assert grid[0]["b"] == "sma" and grid[0]["c"] is None  # == today's live rules
    assert sum(1 for c in grid if c["a"] is None) == 9     # the no-lock B×C block


def test_peak_close_potential_floor_at_zero():
    t = mktrade(entry_price=100.0, entry_shares=10.0)
    # peak close below entry → no upside to capture → 0 (never negative)
    assert hs.peak_close_potential(t, {"peak_close": 90.0}) == 0.0
    assert hs.peak_close_potential(t, {"peak_close": 110.0}) == 100.0
