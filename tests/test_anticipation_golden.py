"""#270 Step 3 Phase 2 — the two BLOCKING golden tests (advisor 6/16).

1. FUNNEL: anticipation.replay() reproduces the gate-free cohort funnel byte-identical
   (WATCHED 62 → ARMED 30 → TRIGGERED 16 unique tickers) + the MNTS lifecycle dates.
   Guards porting fidelity — the whole Step-3 detector inherits replay()'s behavior, so a
   silent drift here corrupts everything downstream.
2. RMV ADAPTER: compute_rmv (replay→RMV key-adapter) == flag_detector._compute_rmv on the
   same series. Guards the silent-corruption surface the funnel test does NOT cover — RMV is
   non-gating telemetry, so a key-swap yields garbage with no error.

Fixtures are the tracked cohort/MNTS TSVs in scripts/ (committed WITH this test — an untracked
fixture makes a "blocking" gate silently no-op in CI / a fresh clone).
"""
from collections import defaultdict
from pathlib import Path

import agents.market_intelligence.anticipation as de

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_cohort(tsv: Path):
    bars_by = defaultdict(list)
    for line in tsv.read_text(encoding="utf-8").splitlines():
        p = line.rstrip("\r").split("\t")
        if len(p) != 7:
            continue
        t, d, o, h, l, c, v = p
        bars_by[t].append({"date": d, "o": float(o), "h": float(h), "l": float(l),
                           "c": float(c), "v": float(v)})
    for t in bars_by:
        bars_by[t].sort(key=lambda b: b["date"])
    return bars_by


def _load_one(tsv: Path):
    bars = []
    for line in tsv.read_text(encoding="utf-8").splitlines():
        line = line.rstrip("\r")
        if "\t" not in line:
            continue
        d, o, h, l, c, v = line.split("\t")
        bars.append({"date": d, "o": float(o), "h": float(h), "l": float(l),
                     "c": float(c), "v": float(v)})
    return bars


def _first(events, state):
    return next((d for d, s, _ in events if s == state), None)


def test_cohort_funnel_62_30_16():
    bars_by = _load_cohort(SCRIPTS / "_270_cohort_bars.tsv")
    reached = {"WATCHED": set(), "ARMED": set(), "TRIGGERED": set()}
    for t, bars in bars_by.items():
        for _, state, _ in de.replay(bars):
            if state in reached:
                reached[state].add(t)
    funnel = tuple(len(reached[s]) for s in ("WATCHED", "ARMED", "TRIGGERED"))
    assert funnel == (62, 30, 16), f"cohort funnel drifted from the gate-free port: {funnel} != (62, 30, 16)"


def test_mnts_lifecycle_dates():
    events = de.replay(_load_one(SCRIPTS / "_270_bars_mnts.tsv"))
    # FIRST occurrence of each state (the script's validation convention) — replay() can
    # re-enter WATCHED after a TRIGGERED, so last-occurrence would not match.
    assert _first(events, "WATCHED") == "2026-05-26"
    assert _first(events, "ARMED") == "2026-06-08"
    assert _first(events, "TRIGGERED") == "2026-06-11"


def test_rmv_adapter_matches_flag_detector():
    from agents.market_intelligence.flag_detector import _compute_rmv
    # asymmetric ranges (high/low at different distances from close) so a high↔low swap in
    # the adapter would change the TR and fail this test; contraction then expansion.
    # 16 bars so the default lookback=15 actually computes (idx 15); asymmetric ranges throughout.
    spec = [(1.6, 0.7), (1.3, 0.5), (1.5, 0.6), (1.1, 0.45), (1.4, 0.55), (1.2, 0.5),
            (1.2, 0.4), (1.0, 0.5), (0.7, 0.3), (0.5, 0.2), (0.3, 0.15),
            (0.2, 0.1), (0.15, 0.08), (0.1, 0.05), (0.9, 0.6), (1.4, 0.7)]
    bars = [{"date": f"d{i}", "o": 10.0, "h": 10.0 + hr, "l": 10.0 - lr, "c": 10.0}
            for i, (hr, lr) in enumerate(spec)]
    rmv_rows = [{"high_price": b["h"], "low_price": b["l"], "close": b["c"]} for b in bars]
    seen_value = False
    for idx in range(len(bars)):
        direct = _compute_rmv(rmv_rows, idx)
        via_adapter = de.compute_rmv(bars, idx)
        assert direct == via_adapter, f"RMV adapter drift at idx {idx}: {direct} != {via_adapter}"
        seen_value = seen_value or (direct is not None)
    assert seen_value, "RMV never computed a non-None value — series too short to exercise the adapter"


def test_rmv_tight_multibar_base_reads_near_zero():
    """Sustained contraction (last 3 bars far tighter than the 15-bar baseline) → RMV at the floor."""
    from agents.market_intelligence.flag_detector import _compute_rmv
    rows = ([{"high_price": 10.5, "low_price": 9.5, "close": 10.0}] * 13
            + [{"high_price": 10.05, "low_price": 9.95, "close": 10.0}] * 3)
    rmv = _compute_rmv(rows, 15)
    assert rmv is not None
    assert rmv < 5.0  # recent/base ratio well under FLOOR → clamped near 0 (computed: 0.0)


def test_rmv_one_quiet_day_after_runup_is_not_zero():
    """The regression the rewrite fixes: 14 wide runup bars + ONE quiet inside day. The recent-3
    window still holds 2 wide bars, so the ratio stays high. The OLD min-max form read ~0 here
    (the single wide bar owned the max), falsely flagging max-coil; ratio-to-baseline must not."""
    from agents.market_intelligence.flag_detector import _compute_rmv
    rows = ([{"high_price": 10.5, "low_price": 9.5, "close": 10.0}] * 15
            + [{"high_price": 10.05, "low_price": 9.95, "close": 10.0}])
    rmv = _compute_rmv(rows, 15)
    assert rmv is not None
    assert rmv > 15.0  # NOT a phantom coil on one inside day (computed: 31.3, vs old min-max ~0)


def test_rmv_dead_feed_returns_none_not_zero():
    """Zero-variance series (frozen / halted feed) → baseline vol 0 → None, never a phantom 0 coil.
    0 is a REAL max-coil signal, so a dead feed must not be able to mint it."""
    from agents.market_intelligence.flag_detector import _compute_rmv
    rows = [{"high_price": 10.0, "low_price": 10.0, "close": 10.0}] * 16
    assert _compute_rmv(rows, 15) is None
