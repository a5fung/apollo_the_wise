"""ADR 0023 F1 — giveback (peak-lock) shadow on the live book. Pins the counterfactual
compute: a round-tripper locks in MORE (positive marginal, earlier exit); a name that never
runs up doesn't arm (zero marginal); no multi-day path → None.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence.giveback_shadow import compute_giveback_shadow


def _trade(closes, entry=100.0, shares=100.0, stop=95.0, pnl=0.0):
    return {"entry_price": entry, "entry_shares": shares, "hard_stop": stop,
            "running_closes": closes, "alert_date": date(2026, 4, 1), "total_pnl": pnl}


def test_giveback_shadow_roundtripper_locks_in_more():
    # Runs 100→120 then fades to 98. The +6%/60% lock (floor 112 at the 120 peak) exits at 108,
    # while the baseline SMA-trail rides it down to 98 → the lock keeps MORE, earlier.
    r = compute_giveback_shadow(_trade([110, 120, 118, 108, 100, 98], pnl=-134))
    assert r is not None
    assert r["giveback_early"] is True
    assert r["marginal"] > 0
    assert r["giveback_pnl"] > r["baseline_pnl"]


def test_giveback_shadow_no_runup_never_arms_zero_marginal():
    # Drops from the open, never reaches the +6% arm → the lock never engages → identical to baseline.
    r = compute_giveback_shadow(_trade([98, 96], pnl=-400))
    assert r is not None
    assert r["marginal"] == 0.0
    assert r["giveback_early"] is False


def test_giveback_shadow_no_multiday_path_returns_none():
    assert compute_giveback_shadow(_trade([100])) is None     # 1 close
    assert compute_giveback_shadow(_trade([])) is None         # no path (same-day close)
    assert compute_giveback_shadow(_trade([110, 120], entry=0)) is None  # no entry price


def test_giveback_shadow_params_recorded():
    r = compute_giveback_shadow(_trade([110, 120, 108]))
    assert r["arm"] == 0.06 and r["floor_frac"] == 0.60   # the operator-picked 7/9 parameterization
