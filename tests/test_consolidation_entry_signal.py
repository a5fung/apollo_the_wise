"""#327 FORWARD SHADOW — the entry-signal SINGLE-SOURCE pin (operator "wire it", 2026-06-18).

The forward shadow is only trustworthy if the LIVE entry-watch fires the SAME signal the offline
sweep validated. These tests pin that contract:
  1. is_entry_tight — the per-bar gate (rmv_5d + range + vol) flags tight/quiet bars, rejects wide
     or loud ones, and is point-in-time (backward-looking only);
  2. entry_signal_at — fires on N consecutive tight days strictly AFTER the runup anchor, returns
     the coiled_low stop + the structural alternate, and is INVARIANT to appended future bars (the
     look-ahead trap); the run must NOT straddle the anchor;
  3. the offline sweep (scripts/_327_entry_signal.py) DELEGATES its is_tight to is_entry_tight —
     loaded via importlib (the script name starts with a digit) so a future re-inline that drifts
     the validation away from the live signal is caught here.
"""
import importlib.util
from pathlib import Path

import agents.market_intelligence.anticipation as de

_ROOT = Path(__file__).resolve().parent.parent


def _mk(close, rng_pct, vol, day):
    """One OHLCV bar with a symmetric range = rng_pct × close around the close."""
    half = close * rng_pct / 2
    return {"date": f"d{day:04d}", "o": close, "h": round(close + half, 4),
            "l": round(close - half, 4), "c": round(close, 4), "v": vol}


def _coil_series(n_tight=8, rng=0.02, vol=8e5, lead=14, run=0.30):
    """A WIDE-range high-volume runup leg (sets ATR_max + ADV20) → the peak (anchor) → a tight,
    quiet coil below it. Returns (bars, anchor_idx). With rng small + vol < the runup's, the coil
    bars pass is_entry_tight; the runup bars do not (range 6% < 7% but vol 2e6 > ADV... actually the
    runup IS the ADV, so the discriminator the test exercises is range/rmv on the coil)."""
    bars, day, base = [], 0, 16.0
    for k in range(lead):
        c = base + run * base * k / (lead - 1)          # rises base → base*(1+run)
        bars.append(_mk(c, 0.06, 2e6, day)); day += 1
    anchor_idx = len(bars) - 1
    peak_c = bars[-1]["c"]
    for _ in range(n_tight):
        bars.append(_mk(peak_c * 0.985, rng, vol, day)); day += 1
    return bars, anchor_idx


# ── 1. is_entry_tight — the per-bar gate ──────────────────────────────────────
def test_is_entry_tight_flags_tight_quiet_bar():
    bars, _ = _coil_series(n_tight=8, rng=0.02, vol=8e5)
    rr = de.bars_to_rmv_rows(bars)
    vols = [b["v"] for b in bars]
    assert de.is_entry_tight(bars, rr, vols, len(bars) - 1) is True


def test_is_entry_tight_rejects_wide_range():
    bars, _ = _coil_series(n_tight=8, rng=0.10, vol=8e5)     # 10% > ENTRY_RANGE_MAX (7%)
    rr = de.bars_to_rmv_rows(bars)
    vols = [b["v"] for b in bars]
    assert de.is_entry_tight(bars, rr, vols, len(bars) - 1) is False


def test_is_entry_tight_rejects_loud_volume():
    bars, _ = _coil_series(n_tight=8, rng=0.02, vol=5e6)     # vol >> ADV20
    rr = de.bars_to_rmv_rows(bars)
    vols = [b["v"] for b in bars]
    assert de.is_entry_tight(bars, rr, vols, len(bars) - 1) is False


# ── 2. entry_signal_at — the N-run fire + look-ahead invariance ───────────────
def test_entry_signal_fires_on_post_runup_tight_run():
    bars, anchor = _coil_series(n_tight=8, rng=0.02, vol=8e5)
    sig = de.entry_signal_at(bars, len(bars) - 1, anchor)
    assert sig is not None
    assert sig["signal_n"] == de.ENTRY_TIGHT_N
    assert sig["stop_kind"] == "coiled_low"
    assert sig["stop_price"] == bars[-1]["l"]                # coiled_low = the fire-bar low
    # structural_low = base low over the N-run; with a flat coil it equals the bar low
    assert sig["structural_low"] <= sig["stop_price"] + 1e-9
    assert sig["entry_price"] == round(bars[-1]["c"], 4)


def test_entry_signal_point_in_time_invariant_to_future_bars():
    # The look-ahead trap: the fire AS OF bar `idx` must read only bars[:idx+1]. Append a future
    # expansion bar; the fire at `idx` must be byte-identical (same entry/stop/readings).
    bars, anchor = _coil_series(n_tight=8, rng=0.02, vol=8e5)
    idx = len(bars) - 1
    s1 = de.entry_signal_at(bars, idx, anchor)
    future = bars + [_mk(bars[-1]["c"] * 1.20, 0.15, 9e6, 9999)]   # a big up day after
    s2 = de.entry_signal_at(future, idx, anchor)
    assert s1 == s2


def test_entry_signal_run_must_form_after_anchor():
    # If the trailing N-run starts at/before the anchor, it is NOT a post-runup coil → no fire.
    bars, anchor = _coil_series(n_tight=8, rng=0.02, vol=8e5)
    idx = len(bars) - 1
    # anchor positioned so the N-run straddles it → guarded out
    assert de.entry_signal_at(bars, idx, anchor_idx=idx - 1) is None      # run_lo <= anchor_idx
    assert de.entry_signal_at(bars, idx, anchor_idx=idx) is None


def test_entry_signal_none_when_not_tight():
    bars, anchor = _coil_series(n_tight=8, rng=0.10, vol=8e5)   # wide coil → no tight run
    assert de.entry_signal_at(bars, len(bars) - 1, anchor) is None


# ── 3. the offline sweep DELEGATES to the single source (anti-re-inline pin) ───
def _load_sweep():
    path = _ROOT / "scripts" / "_327_entry_signal.py"
    spec = importlib.util.spec_from_file_location("_sweep_327", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_offline_sweep_is_tight_delegates_to_production():
    # The script's default thresholds (RMV_MAX=30, the sweep CENTER) differ from production's
    # (ENTRY_RMV_MAX=40, the live inclusive EDGE) by design — so pin the LOGIC under IDENTICAL
    # explicit thresholds, which is the single-source contract (same three comparisons).
    sweep = _load_sweep()
    bars, _ = _coil_series(n_tight=8, rng=0.02, vol=8e5)
    rr = sweep.rmv_rows(bars)                  # the script's adapter (== de.bars_to_rmv_rows)
    vols = [b["v"] for b in bars]
    assert rr == de.bars_to_rmv_rows(bars)     # the adapters must be 1:1
    kw = dict(rmv_max=35, range_max=0.05, vol_max=1.0)
    for i in range(len(bars)):
        assert sweep.is_tight(bars, rr, vols, i, **kw) == de.is_entry_tight(bars, rr, vols, i, **kw)
