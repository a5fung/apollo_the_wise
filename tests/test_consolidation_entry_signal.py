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


def test_is_entry_tight_requires_contraction_not_just_quiet():
    """The min-max→ratio regression (2026-06-27): a UNIFORMLY quiet series (tight range + low vol, but
    NO prior expansion to contract from) must be REJECTED — RMV measures contraction vs a baseline, not
    raw tightness. The old min-max read ~0 here (atr_max≈atr_min → the degenerate floor) and FALSELY
    fired; the ratio form reads ~55 (recent ≈ baseline) → no fire. The range + vol gates pass, so this
    isolates the RMV gate as the discriminator."""
    bars = [_mk(20.0, 0.02, 8e5, d) for d in range(20)]   # flat: tight range, quiet vol, NO runup
    rr = de.bars_to_rmv_rows(bars)
    vols = [b["v"] for b in bars]
    i = len(bars) - 1
    assert (bars[i]["h"] - bars[i]["l"]) / bars[i]["c"] <= de.ENTRY_RANGE_MAX   # range gate would pass
    assert bars[i]["v"] <= de.ENTRY_VOL_MAX * de._adv(vols, i)                  # vol gate would pass
    assert de._compute_rmv(rr, i, lookback=15) > de.ENTRY_RMV_MAX              # but no contraction
    assert de.is_entry_tight(bars, rr, vols, i) is False


def test_is_entry_tight_rejects_recent_halt_with_live_baseline():
    """The recent-halt edge (Gemini 2026-06-27): a trading halt — 3 flat, zero-range, zero-VOLUME bars —
    inside an otherwise-live 15-bar baseline drives the recent NTR → 0 → ratio → 0 → a phantom 'max coil'.
    RMV sees only price range, so a halt looks identical to a perfect coil. Verified pre-fix this session:
    it fired True at rmv 0. The dead-data guards (the range-dead NTR floor in _compute_rmv + the
    volume-dead bar in is_entry_tight) must REJECT it — a halt is a void, not a coiled spring."""
    bars, day, base = [], 0, 16.0
    for k in range(17):                                   # live, rising, volatile runup leg
        c = base + 0.30 * base * k / 16
        bars.append(_mk(c, 0.06, 2e6, day)); day += 1
    peak = bars[-1]["c"]
    for _ in range(3):                                    # the HALT: zero range, zero volume
        bars.append(_mk(peak, 0.0, 0, day)); day += 1
    rr = de.bars_to_rmv_rows(bars)
    vols = [b["v"] for b in bars]
    i = len(bars) - 1
    assert de._compute_rmv(rr, i, lookback=15) is None    # range-dead recent window → None, not a phantom 0
    assert de.is_entry_tight(bars, rr, vols, i) is False  # rejected, not a phantom coil


def test_is_entry_tight_rejects_zero_volume_bar():
    """The volume-dead half of the halt guard, isolated: a bar with a real (coil-tight) range but ZERO
    volume is a void, not a rest — rejected even though the range + rmv gates would pass. Without the
    guard the final `v <= vol_max·ADV` check passes on v=0 (0 ≤ anything) and it would fire (Gemini 6/27)."""
    bars, _ = _coil_series(n_tight=8, rng=0.02, vol=8e5)
    i = len(bars) - 1
    bars[i]["v"] = 0                                       # halt the final coil bar's volume only
    rr = de.bars_to_rmv_rows(bars)
    vols = [b["v"] for b in bars]
    assert de.is_entry_tight(bars, rr, vols, i) is False


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
    # the gate reading (rmv_15d) is recorded + within the gate; rmv_5d kept as 2nd telemetry
    assert sig["rmv_15d"] is not None and sig["rmv_15d"] <= de.ENTRY_RMV_MAX
    assert "rmv_5d" in sig


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


# ── 2b. confirm_signal_at — the CONFIRM entry mode (#354 flag→consolidation merge) ──
# The DB-level coexist (an Anticipate + a Confirm row OPEN on the same ticker/anchor) is enforced by
# the 3-col partial unique index idx_cons_entry_shadow_open_mode + the (ticker, anchor_date,
# entry_mode) ON CONFLICT — deploy-verified (the pure CI suite has no DB). These pin the detector.
def _breakout_series(brk_mult=1.05, brk_vol=1e7, **kw):
    """A post-runup coil (via _coil_series) + a final BREAKOUT bar: close above the coil high."""
    bars, anchor = _coil_series(**kw)
    coil_high = max(b["c"] for b in bars[anchor + 1:])      # the base high (post-peak closes)
    bars.append(_mk(round(coil_high * brk_mult, 4), 0.05, brk_vol, 9000))
    return bars, anchor


def test_confirm_fires_on_volume_breakout():
    bars, anchor = _breakout_series(brk_mult=1.05, brk_vol=1e7)
    sig = de.confirm_signal_at(bars, len(bars) - 1, anchor)
    assert sig is not None
    assert sig["stop_kind"] == "base_low"                   # Confirm stop = base low (≠ anticipate coiled_low)
    assert sig["signal_n"] == 0                             # confirm is not a tight-day-count signal
    assert sig["entry_price"] == round(bars[-1]["c"], 4)    # entry = the break-day close
    assert sig["stop_price"] == round(min(b["l"] for b in bars[anchor + 1:]), 4)   # base low


def test_confirm_none_without_close_above_base():
    bars, anchor = _breakout_series(brk_mult=0.99, brk_vol=1e7)   # closes BELOW the base high
    assert de.confirm_signal_at(bars, len(bars) - 1, anchor) is None


def test_confirm_none_on_weak_volume():
    bars, anchor = _breakout_series(brk_mult=1.05, brk_vol=1e5)   # break close, but no confirming volume
    assert de.confirm_signal_at(bars, len(bars) - 1, anchor) is None


def test_confirm_point_in_time_invariant_to_future_bars():
    # Same look-ahead trap as entry_signal_at: the fire AS OF `idx` must read only bars[:idx+1].
    bars, anchor = _breakout_series(brk_mult=1.05, brk_vol=1e7)
    idx = len(bars) - 1
    s1 = de.confirm_signal_at(bars, idx, anchor)
    future = bars + [_mk(bars[-1]["c"] * 1.20, 0.15, 9e6, 9999)]
    assert de.confirm_signal_at(future, idx, anchor) == s1


def test_confirm_needs_a_base_between_peak_and_break():
    # No room for a base (idx < anchor+2) → no fire (guards the empty-base max()).
    bars, anchor = _breakout_series(brk_mult=1.05, brk_vol=1e7)
    assert de.confirm_signal_at(bars, anchor + 1, anchor) is None


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
