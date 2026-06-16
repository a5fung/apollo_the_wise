"""#270 generalized TIGHTENING recorder (operator 2026-06-16) — the core signal is a
constructive tightening PULLBACK; the gap-low undercut is ONE shape, not a requirement.

These pin the advisor-flagged surfaces:
  1. the volume-extended adapter `bars_to_ft_rows` maps keys 1:1 to what
     flag_detector._compute_fresh_tightening reads — a swap yields garbage RMV/TR with NO
     error and silently poisons the calibration set (same guard as the RMV adapter);
  2. detect_pullback_shape recognises the multiple pivots (gap-low / MA / low-vol-rest);
  3. the recorder is wired into evaluate_candidate AND the narrow gate is intact — MNTS still
     arms via the gap-low undercut, recorded as armed_shape='gap_low_undercut'.
"""
from pathlib import Path

import agents.market_intelligence.anticipation as de
from agents.market_intelligence.flag_detector import _compute_fresh_tightening

MNTS = Path(__file__).resolve().parent.parent / "scripts" / "_270_bars_mnts.tsv"


def _load_mnts():
    bars = []
    for line in MNTS.read_text(encoding="utf-8").splitlines():
        line = line.rstrip("\r")
        if "\t" not in line:
            continue
        d, o, h, l, c, v = line.split("\t")
        bars.append({"date": d, "o": float(o), "h": float(h), "l": float(l),
                     "c": float(c), "v": float(v)})
    return bars


def _series(n=25):
    """OHLCV with distinct h/l/c/v so a high/low key-swap in the adapter would change ATR/TR."""
    bars = []
    for i in range(n):
        c = 10.0 + (i % 5) * 0.1
        bars.append({"date": f"d{i:04d}", "o": c, "h": c + 0.30, "l": c - 0.25,
                     "c": c, "v": 1_000_000.0 + i * 1000})
    return bars


def _flat(n=25, c=10.0):
    return [{"date": f"d{i:04d}", "o": c, "h": c + 0.05, "l": c - 0.05, "c": c, "v": 200_000.0}
            for i in range(n)]


# ── 1. adapter key-mapping (the silent-corruption guard) ──────────────────────
def test_ft_adapter_maps_keys_exactly():
    b = _series(1)[0]
    assert de.bars_to_ft_rows([b])[0] == {
        "high_price": b["h"], "low_price": b["l"], "close": b["c"], "volume": b["v"]}


def test_compute_fresh_tightening_matches_flag_detector():
    bars = _series(25)
    idx, base_age = 24, 6
    got = de.compute_fresh_tightening(bars, idx, base_age)
    rows = [{"high_price": x["h"], "low_price": x["l"], "close": x["c"], "volume": x["v"]}
            for x in bars]
    assert got == _compute_fresh_tightening(rows, idx, base_age)


# ── 2. shape detector recognises multiple pivots (not just the undercut) ──────
def test_shape_gap_low_undercut():
    bars = _series(25)
    gap_idx = 20
    bars[22]["l"] = bars[gap_idx]["l"] - 1.0                 # undercut the gap-day low
    primary, shapes = de.detect_pullback_shape(bars, gap_idx, 22)
    assert "gap_low_undercut" in shapes and primary == "gap_low_undercut"


def test_shape_ma_pullback_and_low_vol_rest_without_undercut():
    bars = _flat(25)                                         # flat tight quiet series
    primary, shapes = de.detect_pullback_shape(bars, gap_idx=5, i=24)
    assert "gap_low_undercut" not in shapes                  # never undercuts → the U&R-only gate misses it
    assert "low_vol_rest" in shapes
    assert any(s.endswith("_pullback") for s in shapes)      # price sits on the MA
    assert primary != "gap_low_undercut"


# ── 3. recorder wired in + narrow gate intact (anti-drift for the U&R case) ───
def test_tightening_telemetry_native_types():
    tel = de.tightening_telemetry(_series(25), 24, gap_idx=20, armed_idx=22)
    assert set(tel) == {"pullback_shape", "pullback_shapes", "fresh_tightening",
                        "fresh_2bar_tr_pct", "atr14_pct", "tight_close_streak"}
    assert isinstance(tel["fresh_tightening"], bool)
    assert isinstance(tel["tight_close_streak"], int)
    for k in ("fresh_2bar_tr_pct", "atr14_pct"):
        assert tel[k] is None or isinstance(tel[k], float)
    assert tel["pullback_shape"] is None or isinstance(tel["pullback_shape"], str)


def test_tight_close_streak_counts_pradeep_series():
    # Pradeep "series of tight days": consecutive bars with |close %change| ≤ 0.4%.
    # 3 dead-flat closes ending at i, preceded by a +5% jump → streak of exactly 3.
    bars = [{"date": f"d{i}", "o": 10, "h": 10, "l": 10, "c": 10.0, "v": 1e6} for i in range(5)]
    bars.append({"date": "d5", "o": 10.5, "h": 10.5, "l": 10.5, "c": 10.5, "v": 1e6})  # +5% break
    bars += [{"date": f"d{6+i}", "o": 10.5, "h": 10.5, "l": 10.5, "c": 10.5, "v": 1e6} for i in range(3)]
    assert de.tight_close_streak(bars, len(bars) - 1) == 3
    assert de.tight_close_streak(bars, 5) == 0          # the +5% bar itself breaks the streak


def test_evaluate_candidate_carries_recorder_and_mnts_arms_on_undercut():
    bars = _load_mnts()
    row = de.evaluate_candidate(bars, "2026-05-26")
    for k in ("pullback_shape", "pullback_shapes", "armed_shape",
              "fresh_tightening", "fresh_2bar_tr_pct", "atr14_pct"):
        assert k in row
    # the narrow gate is unchanged: MNTS armed via the gap-low undercut → recorded as that shape.
    assert row["armed_shape"] == "gap_low_undercut"
