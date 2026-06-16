"""#270 Step 3 Phase 4a — evaluate_candidate (lifecycle-from-bars) derivation.

Pins the JOB-layer label→state mapping: the real MNTS cycle derives armed 6/08 + the
RECLAIM 6/11 as state 'ready' (a set-up, NOT 'triggered'/entry — the load-bearing rule),
plus synthetic watched/armed/expired off a flat-then-gap series.
"""
from pathlib import Path

import agents.market_intelligence.delayed_ep as de

MNTS = Path(__file__).resolve().parent.parent / "scripts" / "_270_bars_mnts.tsv"


def _load(tsv):
    bars = []
    for line in tsv.read_text(encoding="utf-8").splitlines():
        line = line.rstrip("\r")
        if "\t" not in line:
            continue
        d, o, h, l, c, v = line.split("\t")
        bars.append({"date": d, "o": float(o), "h": float(h), "l": float(l),
                     "c": float(c), "v": float(v)})
    return bars


def _flat(n, c=10.0, v=1_000_000.0, start=0):
    return [{"date": f"d{start + i:04d}", "o": c, "h": c, "l": c, "c": c, "v": v}
            for i in range(n)]


def test_mnts_derives_ready_at_reclaim():
    bars = _load(MNTS)
    row = de.evaluate_candidate(bars, "2026-05-26")
    assert row is not None
    assert row["armed_date"] == "2026-06-08"
    assert row["ready_date"] == "2026-06-11"
    # the reclaim is a SET-UP awaiting the 3b entry — NOT an entry, so NO entry price.
    assert row["state"] == "ready"
    assert row["entry_tactic"] is None and row["entry_price"] is None


def test_unknown_gap_day_returns_none():
    assert de.evaluate_candidate(_flat(210), "nope") is None


def _gap_series(post):
    """205 flat bars + a +55% gap (3×+ vol) at d0205, then `post` bars appended."""
    bars = _flat(205)                                   # d0000..d0204, close 10, vol 1e6
    bars.append({"date": "d0205", "o": 14.0, "h": 15.6, "l": 14.0, "c": 15.5, "v": 4_000_000.0})
    bars.extend(post)
    return bars


def test_synthetic_watched():
    # gap then 3 bars that hold above gap_day_low (14.0) → still WATCHED (within arm window).
    post = [{"date": f"d{206+i:04d}", "o": 15.0, "h": 15.2, "l": 14.5, "c": 15.0, "v": 1_500_000.0}
            for i in range(3)]
    row = de.evaluate_candidate(_gap_series(post), "d0205")
    assert row["state"] == "watched" and row["armed_date"] is None


def test_synthetic_expired():
    # gap then 20 bars with no undercut → past ARM_WINDOW (15) → expired.
    post = [{"date": f"d{206+i:04d}", "o": 15.0, "h": 15.2, "l": 14.5, "c": 15.0, "v": 1_500_000.0}
            for i in range(20)]
    row = de.evaluate_candidate(_gap_series(post), "d0205")
    assert row["state"] == "expired"


def test_synthetic_armed_on_undercut():
    # one undercut bar (low 13.5 < gap_day_low 14.0, vol below the burst) → ARMED, no coil yet.
    post = [{"date": "d0206", "o": 14.5, "h": 14.6, "l": 13.5, "c": 14.0, "v": 2_000_000.0}]
    row = de.evaluate_candidate(_gap_series(post), "d0205")
    assert row["state"] == "armed" and row["armed_date"] == "d0206"
