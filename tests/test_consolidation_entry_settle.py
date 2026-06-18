"""#327 FORWARD-SHADOW SETTLEMENT — the capture/stop/open bet + the settle wiring (operator 6/18).

Pins the settlement core the live _consolidation_entry_settle_job calls:
  1. entry_bet_outcome — the validated asymmetric bet under a FIXED stop: capture (MFE hits
     +target_r×risk first), stop (stop first), open (neither by the window), with the UNCAPPED
     fwd_mfe_r; risk≤0 → None;
  2. settle_entry_shadow — ABSTAINS below ENTRY_SETTLE_WINDOW forward bars, else returns
     {outcome, fwd_mfe_r, realized_r} (realized_r via the reused, separately-pinned settle_row);
  3. the offline sweep (scripts/_327_entry_signal.bet_outcome) DELEGATES to entry_bet_outcome
     (anti-re-inline pin — loaded via importlib, the script name starts with a digit).
"""
import importlib.util
from pathlib import Path

import agents.market_intelligence.anticipation as de

_ROOT = Path(__file__).resolve().parent.parent


def _bar(c, h=None, l=None, day=0):
    return {"date": f"s{day:04d}", "o": c, "h": h if h is not None else c,
            "l": l if l is not None else c, "c": c, "v": 1e6}


def _series(entry=100.0, fwd=None, pad=6):
    """Entry bar at index `pad` (pre-pad bars are irrelevant — entry_bet_outcome reads forward
    only). `fwd` = [(high, low), ...] for the forward bars; close = midpoint."""
    bars = [_bar(entry, day=i) for i in range(pad)]
    bars.append(_bar(entry, day=pad))
    for k, (h, l) in enumerate(fwd or [], start=1):
        bars.append({"date": f"s{pad + k:04d}", "o": (h + l) / 2, "h": h, "l": l,
                     "c": (h + l) / 2, "v": 1e6})
    return bars, pad


# ── 1. entry_bet_outcome — entry 100, stop 95, risk 5, +3R target = 115 ───────
def test_bet_capture_when_target_hit_first():
    bars, e = _series(fwd=[(116, 99)])                  # high 116 ≥ 115 before any stop
    out, mfe = de.entry_bet_outcome(bars, e, 95.0)
    assert out == "capture" and abs(mfe - (116 - 100) / 5) < 1e-9


def test_bet_stop_when_stop_hit_first():
    bars, e = _series(fwd=[(101, 94)])                  # low 94 ≤ 95, high 101 < 115
    out, mfe = de.entry_bet_outcome(bars, e, 95.0)
    assert out == "stop" and abs(mfe - (101 - 100) / 5) < 1e-9


def test_bet_open_when_neither_in_window():
    bars, e = _series(fwd=[(102, 98)] * 12)             # never target, never stop, full window
    out, mfe = de.entry_bet_outcome(bars, e, 95.0)
    assert out == "open" and abs(mfe - (102 - 100) / 5) < 1e-9


def test_bet_none_on_nonpositive_risk():
    bars, e = _series(fwd=[(102, 98)])
    assert de.entry_bet_outcome(bars, e, 100.0) is None     # stop == entry → risk 0
    assert de.entry_bet_outcome(bars, e, 105.0) is None     # stop above entry


def test_bet_respects_window_bound():
    # a capture on bar 13 must NOT count (window 12) → open over the first 12 bars
    fwd = [(102, 98)] * 12 + [(200, 99)]
    bars, e = _series(fwd=fwd)
    out, _ = de.entry_bet_outcome(bars, e, 95.0, window=12)
    assert out == "open"


# ── 2. settle_entry_shadow — abstain vs settle ────────────────────────────────
def test_settle_abstains_below_window():
    bars, e = _series(fwd=[(102, 98)] * 5)             # only 5 forward bars < ENTRY_SETTLE_WINDOW
    assert de.settle_entry_shadow(bars, e, 95.0) is None


def test_settle_returns_outcome_and_realized_when_ripe():
    bars, e = _series(fwd=[(116, 99)] + [(102, 98)] * 13)   # capture on bar 1, ≥12 fwd bars
    res = de.settle_entry_shadow(bars, e, 95.0)
    assert res is not None
    assert res["outcome"] == "capture"
    assert abs(res["fwd_mfe_r"] - round((116 - 100) / 5, 4)) < 1e-9
    assert isinstance(res["realized_r"], float)        # realized_r path lit (settle_row pinned elsewhere)


def test_settle_open_path_is_float_realized():
    bars, e = _series(fwd=[(102, 98)] * 12)
    res = de.settle_entry_shadow(bars, e, 95.0)
    assert res is not None and res["outcome"] == "open"
    assert isinstance(res["realized_r"], float)


def test_settle_early_definitive_stop_settles_despite_short_window():
    # The survivorship fix (advisor 6/18): a name that STOPS on bar 2 then halts (only 4 fwd bars)
    # must still settle 'stop' — the bare 12-bar gate would orphan it (outcome NULL forever). A
    # definitive capture/stop is final regardless of remaining window.
    bars, e = _series(fwd=[(101, 96), (101, 94), (100, 99), (100, 99)])
    res = de.settle_entry_shadow(bars, e, 95.0)
    assert res is not None and res["outcome"] == "stop"


def test_settle_open_still_abstains_when_window_incomplete():
    # The complement: genuinely OPEN (no target/stop) with < window bars stays provisional (None) —
    # only the residual halt-while-open, surfaced via the readout's open_overdue, is left open.
    bars, e = _series(fwd=[(102, 98)] * 6)
    assert de.settle_entry_shadow(bars, e, 95.0) is None


# ── 3. the offline sweep DELEGATES to the single source (anti-re-inline pin) ───
def _load_sweep():
    path = _ROOT / "scripts" / "_327_entry_signal.py"
    spec = importlib.util.spec_from_file_location("_sweep_327_settle", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_offline_bet_outcome_delegates_to_production():
    sweep = _load_sweep()
    for fwd in ([(116, 99)], [(101, 94)], [(102, 98)] * 12):
        bars, e = _series(fwd=fwd)
        assert sweep.bet_outcome(bars, e, len(bars) - 1, 95.0) == de.entry_bet_outcome(bars, e, 95.0)
