"""#270 Step 3 Phase 3 — realized_r settlement + the STRUCTURAL-ABSTAIN guard (advisor 6/16).

The load-bearing test is `test_first5_no_fills_abstains`: a minute-scale tactic with no
persisted day-0 fills must ABSTAIN (return None), never fall back to a daily-bar approximation
— that fallback is exactly what would re-inject the MFE-shaped error into the deployable for the
+1–2R tactic the edge lives in. Plus terminal-fallback (halt/delist) + a harvest-parity test
pinning the ported simulate to scripts/_270_harvest.py.
"""
import importlib.util
from pathlib import Path

import agents.market_intelligence.anticipation as de

_HARVEST = Path(__file__).resolve().parent.parent / "scripts" / "_270_harvest.py"
_spec = importlib.util.spec_from_file_location("_270_harvest", _HARVEST)
harvest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harvest)


def _bars(closes):
    """Minimal ascending OHLC bars from a close list (h=c+0.5, l=c-0.5, o=c)."""
    return [{"o": c, "h": c + 0.5, "l": c - 0.5, "c": c} for c in closes]


# ── the load-bearing one: structural abstain ────────────────────────────────────
def test_first5_no_fills_abstains():
    res = de.settle_row(entry_tactic="first5_break", entry_price=10.0, stop_price=9.0,
                        bars=_bars([10, 11, 12, 13, 14, 15]), entry_idx=0, day0_fills=None)
    assert res is None, "first5 with no persisted day-0 fills MUST abstain, not approximate"


def test_gdl_no_fills_abstains():
    res = de.settle_row(entry_tactic="gdl_reclaim", entry_price=10.0, stop_price=9.0,
                        bars=_bars([10, 11, 12, 13, 14, 15]), entry_idx=0, day0_fills=[])
    assert res is None


def test_first5_with_fills_settles_from_fills():
    # entry 10, stop 9 → risk 1. fills: ½@11 (+0.5R) + ½@13 (+1.5R) = +2.0R realized.
    fills = [{"price": 11.0, "fraction": 0.5, "day_idx": 0},
             {"price": 13.0, "fraction": 0.5, "day_idx": 0}]
    res = de.settle_row(entry_tactic="first5_break", entry_price=10.0, stop_price=9.0,
                        bars=_bars([10, 11, 12, 13, 14, 15]), entry_idx=0, day0_fills=fills)
    assert res is not None and res["settled"] and not res["degraded"]
    assert abs(res["realized_r"] - 2.0) < 1e-9


def test_anticipation_settles_with_enough_forward_bars():
    # 1 entry bar + 5 forward bars = enough; should settle a finite realized_r.
    res = de.settle_row(entry_tactic="anticipation", entry_price=10.0, stop_price=9.0,
                        bars=_bars([10, 11, 12, 11, 12, 13]), entry_idx=0)
    assert res is not None and res["settled"] and not res["degraded"]
    assert isinstance(res["realized_r"], float)


def test_anticipation_too_few_bars_abstains():
    res = de.settle_row(entry_tactic="anticipation", entry_price=10.0, stop_price=9.0,
                        bars=_bars([10, 11, 12]), entry_idx=0, days_since_trigger=2)
    assert res is None, "only 2 forward bars (<5) and not stalled → abstain, re-eval later"


def test_terminal_fallback_settles_degraded():
    # stopped printing: only 2 forward bars but 25 calendar days elapsed → settle DEGRADED.
    res = de.settle_row(entry_tactic="anticipation", entry_price=10.0, stop_price=9.0,
                        bars=_bars([10, 11, 12]), entry_idx=0, days_since_trigger=25)
    assert res is not None and res["settled"] and res["degraded"]


def test_unknown_tactic_abstains():
    res = de.settle_row(entry_tactic="mystery", entry_price=10.0, stop_price=9.0,
                        bars=_bars([10, 11, 12, 13, 14, 15]), entry_idx=0)
    assert res is None


def test_harvest_simulate_parity_with_script():
    """ported de.simulate == scripts/_270_harvest.simulate on the same path+rule (anti-drift)."""
    bars = _bars([10, 11, 10.5, 12, 13, 11, 14])
    path = de.daily_path(bars, 0, 6)
    assert path == harvest.daily_path(bars, 0, 6)                       # adapters identical
    for rname in ("all_out_+1R", "half_1R_trail", "bank_1R_3R", "twophase_g50"):
        rule = harvest.RULES[rname]
        assert de.simulate(10.0, 9.0, path, rule, "pess") == harvest.simulate(10.0, 9.0, path, rule, "pess"), rname
        assert de.simulate(10.0, 9.0, path, rule, "opt") == harvest.simulate(10.0, 9.0, path, rule, "opt"), rname
