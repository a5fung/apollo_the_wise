"""#385 volume dry-up TELEMETRY (Gemini review 6/27) — pins the SECOND, independent contraction
axis alongside rmv_5d/rmv_15d on the Family-A #327 entry-shadow. RMV (_compute_rmv) reads gap-aware
TRUE RANGE only, so a range-tight bar on ELEVATED volume (a drift) reads identically to a genuine
low-volume rest. `anticipation.volume_dryup` mirrors RMV's own window shape (current_window=3 over
lookback=15) on the VOLUME axis instead — these tests pin:
  1. volume_dryup — the pinned SMA/ratio arithmetic + the insufficient-history floor
  2. point-in-time invariance (the same look-ahead trap every #327 primitive is tested against)
  3. entry_signal_at / confirm_signal_at carry the three new fields through to the fire record
     (the shadow-row wiring the graduation eval will read)
"""
import agents.market_intelligence.anticipation as de


def _vbar(v, i, c=10.0):
    """One OHLCV bar with a fixed price (only volume varies) — isolates the volume axis."""
    return {"date": f"d{i:04d}", "o": c, "h": round(c * 1.01, 4), "l": round(c * 0.99, 4),
            "c": c, "v": v}


def _mk(close, rng_pct, vol, day):
    """One OHLCV bar with a symmetric range = rng_pct × close around the close (mirrors
    test_consolidation_entry_signal._mk)."""
    half = close * rng_pct / 2
    return {"date": f"d{day:04d}", "o": close, "h": round(close + half, 4),
            "l": round(close - half, 4), "c": round(close, 4), "v": vol}


def _coil_series(n_tight=8, rng=0.02, vol=8e5, lead=14, run=0.30):
    """A wide-range high-volume runup leg → the peak (anchor) → a tight, quiet coil below it.
    Mirrors test_consolidation_entry_signal._coil_series exactly (kept local — test files in this
    repo are self-contained, one helper each)."""
    bars, day, base = [], 0, 16.0
    for k in range(lead):
        c = base + run * base * k / (lead - 1)
        bars.append(_mk(c, 0.06, 2e6, day)); day += 1
    anchor_idx = len(bars) - 1
    peak_c = bars[-1]["c"]
    for _ in range(n_tight):
        bars.append(_mk(peak_c * 0.985, rng, vol, day)); day += 1
    return bars, anchor_idx


# ── 1. volume_dryup — pinned arithmetic + insufficient-history floor ─────────────────────────
def test_volume_dryup_pinned_values():
    # 12 bars @ 1000 (the baseline) + 3 dried-up bars @ 100/200/300 (the current window).
    vols = [1000] * 12 + [100, 200, 300]
    bars = [_vbar(v, i) for i, v in enumerate(vols)]
    idx = len(bars) - 1
    vol_sma_3, vol_sma_15, ratio = de.volume_dryup(bars, idx)
    assert vol_sma_3 == 200.0                        # mean(100, 200, 300)
    assert vol_sma_15 == 840.0                        # mean(12×1000 + 100+200+300) / 15
    assert ratio == round(200.0 / 840.0, 4)


def test_volume_dryup_none_when_insufficient_history():
    bars = [_vbar(500, i) for i in range(10)]         # only 10 bars, lookback=15 needs 15
    assert de.volume_dryup(bars, len(bars) - 1) == (None, None, None)
    # exactly at the floor (idx == lookback - 1 == 14, i.e. 15 bars) must succeed
    bars15 = [_vbar(500, i) for i in range(15)]
    vol_sma_3, vol_sma_15, ratio = de.volume_dryup(bars15, len(bars15) - 1)
    assert vol_sma_3 == 500.0 and vol_sma_15 == 500.0 and ratio == 1.0


def test_volume_dryup_none_when_baseline_dead():
    # a zero-volume baseline (void/halt feed) has no denominator to ratio against.
    bars = [_vbar(0, i) for i in range(15)]
    vol_sma_3, vol_sma_15, ratio = de.volume_dryup(bars, len(bars) - 1)
    assert vol_sma_3 == 0.0 and vol_sma_15 == 0.0 and ratio is None


def test_volume_dryup_custom_windows():
    vols = list(range(1, 21))                          # bars 0..19, v = 1..20
    bars = [_vbar(v, i) for i, v in enumerate(vols)]
    idx = len(bars) - 1                                 # v[idx] == 20
    vol_sma_2, vol_sma_10, ratio = de.volume_dryup(bars, idx, current_window=2, lookback=10)
    assert vol_sma_2 == round((19 + 20) / 2, 1)
    assert vol_sma_10 == round(sum(range(11, 21)) / 10, 1)
    assert ratio == round(vol_sma_2 / vol_sma_10, 4)


# ── 2. point-in-time invariance — the same look-ahead trap every #327 primitive is pinned on ──
def test_volume_dryup_point_in_time_invariant_to_future_bars():
    vols = [1000] * 12 + [100, 200, 300]
    bars = [_vbar(v, i) for i, v in enumerate(vols)]
    idx = len(bars) - 1
    r1 = de.volume_dryup(bars, idx)
    future = bars + [_vbar(999999, 9999)]
    r2 = de.volume_dryup(future, idx)
    assert r1 == r2


# ── 3. entry_signal_at / confirm_signal_at carry the fields through (the shadow-row wiring) ──
def test_entry_signal_at_includes_volume_dryup_fields():
    bars, anchor = _coil_series(n_tight=8, rng=0.02, vol=8e5)
    sig = de.entry_signal_at(bars, len(bars) - 1, anchor)
    assert sig is not None
    for key in ("vol_sma_3", "vol_sma_15", "vol_dryup_ratio"):
        assert key in sig
    assert sig["vol_sma_3"] is not None and sig["vol_sma_15"] is not None
    # the fire run is quiet (vol=8e5) vs the runup-leg baseline (vol=2e6) → a real dry-up reads < 1
    assert sig["vol_dryup_ratio"] < 1.0
    # cross-check against the pure primitive directly (single source, no re-derivation drift)
    idx = len(bars) - 1
    assert (sig["vol_sma_3"], sig["vol_sma_15"], sig["vol_dryup_ratio"]) == de.volume_dryup(bars, idx)


def test_entry_signal_at_volume_dryup_point_in_time_invariant():
    bars, anchor = _coil_series(n_tight=8, rng=0.02, vol=8e5)
    idx = len(bars) - 1
    s1 = de.entry_signal_at(bars, idx, anchor)
    future = bars + [_mk(bars[-1]["c"] * 1.20, 0.15, 9e6, 9999)]
    s2 = de.entry_signal_at(future, idx, anchor)
    assert s1 == s2   # includes the new vol_sma_3/vol_sma_15/vol_dryup_ratio keys


def test_confirm_signal_at_includes_volume_dryup_fields():
    bars, anchor = _coil_series(n_tight=8, rng=0.02, vol=8e5)
    coil_high = max(b["c"] for b in bars[anchor + 1:])
    bars = bars + [_mk(round(coil_high * 1.05, 4), 0.05, 1e7, 9000)]
    sig = de.confirm_signal_at(bars, len(bars) - 1, anchor)
    assert sig is not None
    for key in ("vol_sma_3", "vol_sma_15", "vol_dryup_ratio"):
        assert key in sig
    idx = len(bars) - 1
    assert (sig["vol_sma_3"], sig["vol_sma_15"], sig["vol_dryup_ratio"]) == de.volume_dryup(bars, idx)
