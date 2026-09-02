"""#611 — the catalyst-lattice monitor's SUPPLY figure, reconciled against `mi_ep_scan_log`.

THE BUG (as reported). On 2026-09-01 the #533 revert-trigger monitor (trigger (c), zero-alert
days) told the operator: "The tape offered 4 and 3 stocks gapping 10%+ past the universe floors
on those days" for 09-01/08-31. A naive count of DISTINCT TICKERS in `mi_ep_scan_log` with a
day-MAX `gap_pct >= 10` gives 42 and 52 for the same two days — an apparent ~10x miss. That
framing mattered: a thin tape would have explained the null the trigger fired on, and the
scan-log count made the tape look ~10x thinner than it was — exactly the kind of wrong number
that argues for reverting a flip the operator already ruled should stay ("don't revert").

WHY IT NUMBERS DIFFERENT THINGS (traced against prod, read-only SELECTs — see the block above
`_LATTICE_SUPPLY_GAP_PCT` in health_checks.py for the durable version of this):

1. The naive 42/52 never applies the monitor's own $5 prior-close / 50,000-share prior-volume
   floors. Applying them — using `mi_ep_scan_log`'s OWN `prev_close`/`prev_day_volume` columns,
   no cross-table join needed — drops 42 -> 6 and 52 -> 8. Most of the "10x" was un-floored
   penny/micro names (GPRO prev_close $0.88, HKPD $0.33, RDHL $0.66, ...) that were never in
   this trigger's universe.
2. The remaining gap is DEFINITIONAL. `mi_ep_scan_log.gap_pct` is computed in ep_detector.py as
   `(current_price - prev_close) / prev_close * 100` and a fresh row is written on EVERY SCAN
   TICK (dozens per ticker per day) — so a ticker's day-MAX `gap_pct` is its PEAK live-price
   reading vs the prior close at whatever tick caught it, not the settled opening print.
   `mi_daily_closes.open_price` (what the monitor's supply query actually uses) IS the settled
   opening print. The two diverge in both directions: PRLD peaked at a scan-tick reading of
   +12.3% but its actual open was BELOW the prior close (-0.9%); CRK peaked at +10.5% on a tick
   but opened at +9.6% — over the line on a tick that never became the print.

Of the 6 (09-01) / 8 (08-31) that pass the floors, only the ones whose SETTLED OPEN actually
gapped >= 10% are WETO/YEXT/PXS/GDXD (4) and WETO/MOVE/SAIC (3) — reproducing the monitor's
alert exactly. GDXD never appears in the scan log's 42 at all: the two ticker sets are not
nested either direction, so "the scan log is a superset, just noisier" is not a safe shortcut.

VERDICT: the monitor's arithmetic (mi_daily_closes, settled open, floors applied) was already
correct and reproduces exactly — nothing computational changed. The fix is WORDING ONLY: the
operator-facing message said "stocks gapping X%+ past the universe floors", which reads as
"stocks that moved X%+ at some point" — the exact (wrong) reading that produced the 42/52
comparison in the first place. It now says "opened X%+ above the prior close" and spells out
the floor values inline.

All ticker-level numbers below are real prod values captured once via read-only SELECT against
`mi_daily_closes` / `mi_ep_scan_log` on 2026-08-31 and 2026-09-01 (frozen here, not re-queried).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from agents.market_intelligence import health_checks as hc

_D31 = date(2026, 8, 31)
_D01 = date(2026, 9, 1)

# ── step 0: the naive, un-floored scan-log count (what produced the "42 and 52") ──────────
_NAIVE_SCANLOG_COUNT = {_D31: 52, _D01: 42}

# ── step 1: mi_ep_scan_log day-MAX gap_pct >= 10, floor-eligible-only, with the scan log's
# OWN prev_close / prev_day_volume (real prod values). {date: {ticker: (prev_close, prev_vol)}}
_SCANLOG_FLOOR_PASSERS = {
    _D01: {
        "WETO": (5.48, 42_204_632), "YEXT": (6.77, 1_314_412), "FRVO": (15.38, 4_506_105),
        "PXS": (5.36, 726_450), "PRLD": (5.6, 737_667), "CRK": (14.43, 1_604_822),
    },
    _D31: {
        "WETO": (5.72, 2_333_301), "MOVE": (11.49, 58_568), "ARTL": (5.9643, 266_706),
        "HCWC": (8.4455, 62_203), "TITN": (17.86, 352_960), "SAIC": (125.96, 849_499),
        "GPRK": (9.83, 371_134), "RFAI": (52.05, 56_016),
    },
}

# Two real 09-01 names from the naive 42 that the floors REJECT, one on each arm — proves the
# floor filter is doing real work, not just re-affirming a pre-selected list. GPRO fails on
# price ($0.88 < $5), MLEC fails on volume (31,631 < 50,000 shares).
_SCANLOG_FLOOR_REJECTS_D01 = {"GPRO": (0.8762, 220_002_853), "MLEC": (6.8, 31_631)}

# The scan log's day-MAX gap_pct itself (peak live-price-vs-prior-close reading at whatever
# scan tick caught it) for the 09-01 floor-passers — real prod values, this IS what made all
# six of them clear the monitor's 10% floor on the scan-log side in the first place.
_SCANLOG_DAY_MAX_GAP_D01 = {
    "WETO": 51.82, "YEXT": 16.1, "FRVO": 15.86, "PXS": 15.49, "PRLD": 12.32, "CRK": 10.46,
}

# ── step 2: the SETTLED OPEN vs prior close, from mi_daily_closes, for the SAME tickers plus
# GDXD (a true opening gapper on 09-01 the scan log's 42 never flagged at all — real prod
# values). {date: {ticker: (open_price, prev_close, prev_volume)}}
_DAILY_CLOSES_OPEN = {
    _D01: {
        "WETO": (7.685, 5.48, 41_386_359), "YEXT": (7.66, 6.77, 1_307_872),
        "FRVO": (16.47, 15.38, 4_506_411), "PXS": (5.93, 5.36, 547_985),
        "PRLD": (5.55, 5.6, 737_027), "CRK": (15.82, 14.43, 1_602_056),
        "GDXD": (19.0, 17.2, 3_698_493),
    },
    _D31: {
        "WETO": (7.21, 5.72, 1_599_818), "MOVE": (15.09, 11.49, 58_183),
        "ARTL": (5.95, 5.9643, 266_706), "HCWC": (8.16, 8.4455, 62_203),
        "TITN": (19.5, 17.86, 352_958), "SAIC": (140.39, 125.96, 848_452),
        "GPRK": (10.26, 9.83, 353_041), "RFAI": (54.63, 52.05, 55_399),
    },
}

_FLOOR_MIN_CLOSE = hc._LATTICE_SUPPLY_MIN_PREV_CLOSE
_FLOOR_MIN_VOLUME = hc._LATTICE_SUPPLY_MIN_PREV_VOLUME
_GAP_PCT = hc._LATTICE_SUPPLY_GAP_PCT


def _opening_gap_pct(open_price: float, prev_close: float) -> float:
    return (open_price - prev_close) / prev_close * 100.0


def test_scanlog_floor_filter_explains_most_of_the_10x():
    """MUTATION TARGET: comparing the monitor's floored supply figure against an UN-FLOORED
    scan-log ticker count (the mistake that produced '42 and 52' in the first place). Applying
    the SAME $5/50k floors the monitor uses — via the scan log's own prev_close/prev_day_volume
    columns — collapses the naive counts to exactly 6 and 8, which is most of the ~10x. Also
    proves the filter REJECTS real names, on both arms (GPRO on price, MLEC on volume) —
    without this the passing-6 set could be an unfiltered tautology."""
    assert _NAIVE_SCANLOG_COUNT == {_D01: 42, _D31: 52}
    assert len(_SCANLOG_FLOOR_PASSERS[_D01]) == 6
    assert len(_SCANLOG_FLOOR_PASSERS[_D31]) == 8
    for t, (pc, pv) in _SCANLOG_FLOOR_PASSERS[_D01].items():
        assert pc >= _FLOOR_MIN_CLOSE and pv >= _FLOOR_MIN_VOLUME, f"{t} should pass both floors"
    gpro_pc, gpro_pv = _SCANLOG_FLOOR_REJECTS_D01["GPRO"]
    mlec_pc, mlec_pv = _SCANLOG_FLOOR_REJECTS_D01["MLEC"]
    assert gpro_pc < _FLOOR_MIN_CLOSE   # rejected on PRICE ($0.88)
    assert gpro_pv >= _FLOOR_MIN_VOLUME  # (volume alone would have passed it)
    assert mlec_pc >= _FLOOR_MIN_CLOSE   # rejected on VOLUME (31,631 shares)
    assert mlec_pv < _FLOOR_MIN_VOLUME


def test_scan_tick_peak_diverges_from_the_settled_open_prld_and_crk():
    """PRLD and CRK are the money examples: both cleared the monitor's 10% floor on SOME
    scan tick during the day (real day-MAX `gap_pct` readings from `mi_ep_scan_log`, captured
    in `_SCANLOG_DAY_MAX_GAP_D01`), but neither ACTUALLY OPENED 10%+ above the prior close.
    MUTATION TARGET: treating 'day-max scan-tick gap_pct >= threshold' as equivalent to
    'opened >= threshold' — the exact conflation that made the scan log's count look like a
    truer answer than the monitor's settled-open count. Asserting only the daily-closes side
    (as a prior version of this test did) cannot catch that conflation; both sides of the
    divergence must be pinned."""
    # both cleared the floor on a scan tick during the day...
    assert _SCANLOG_DAY_MAX_GAP_D01["PRLD"] >= _GAP_PCT
    assert _SCANLOG_DAY_MAX_GAP_D01["CRK"] >= _GAP_PCT

    prld_open, prld_prev, _ = _DAILY_CLOSES_OPEN[_D01]["PRLD"]
    crk_open, crk_prev, _ = _DAILY_CLOSES_OPEN[_D01]["CRK"]
    prld_gap = _opening_gap_pct(prld_open, prld_prev)
    crk_gap = _opening_gap_pct(crk_open, crk_prev)
    # ...but PRLD's settled open was actually BELOW the prior close...
    assert prld_gap < 0, f"PRLD opening gap should be negative, got {prld_gap:.2f}%"
    # ...and CRK's settled open, while still positive, never reached the floor.
    assert 0 < crk_gap < _GAP_PCT, f"CRK opening gap should be under {_GAP_PCT}%, got {crk_gap:.2f}%"


def test_reconciled_supply_matches_the_alerted_4_and_3():
    """The bridge, end to end: of the floor-passing scan-log tickers, only the ones whose
    SETTLED OPEN (mi_daily_closes) actually gapped >= 10% survive — and that count is exactly
    what the monitor alerted (4 on 09-01, 3 on 08-31). MUTATION TARGET: hardcoding {4, 3}
    without deriving them from the per-ticker open-vs-prior-close arithmetic, or silently
    dropping GDXD (present in the daily-closes-derived set, ABSENT from the scan log's 42 —
    proof the two ticker sets are not nested in either direction)."""
    reconciled = {}
    tickers_used = {}
    for d, opens in _DAILY_CLOSES_OPEN.items():
        winners = {t for t, (op, pc, pv) in opens.items()
                   if pc >= _FLOOR_MIN_CLOSE and pv >= _FLOOR_MIN_VOLUME
                   and _opening_gap_pct(op, pc) >= _GAP_PCT}
        reconciled[d] = len(winners)
        tickers_used[d] = winners

    assert reconciled == {_D01: 4, _D31: 3}
    assert tickers_used[_D01] == {"WETO", "YEXT", "PXS", "GDXD"}
    assert tickers_used[_D31] == {"WETO", "MOVE", "SAIC"}
    # GDXD proves the scan-log-floor-passers set is not a superset of the true opening gappers.
    assert "GDXD" not in _SCANLOG_FLOOR_PASSERS[_D01]
    assert "GDXD" in tickers_used[_D01]


@pytest.mark.asyncio
async def test_lattice_supply_by_date_reproduces_prod_on_both_days():
    """Pins the ACTUAL code path (`_lattice_supply_by_date`), not just the derivation above,
    against the real prod row counts for these two days (~12.4k rows/day, well above the
    measured-day floor). MUTATION TARGET: any change to the SQL's GROUP BY / FILTER clauses,
    or to `_LATTICE_SUPPLY_MIN_UNIVERSE_ROWS`, that would misclassify either day as unmeasured
    or land the count on the wrong date."""
    class _Conn:
        async def fetch(self, sql, *args):
            return [
                {"trade_date": _D31, "rows_with_open": 12_432, "supply": 3},
                {"trade_date": _D01, "rows_with_open": 12_377, "supply": 4},
            ]

    got = await hc._lattice_supply_by_date(_Conn(), _D31, _D01)
    assert got == {_D31: 3, _D01: 4}


def test_alert_wording_says_opened_above_prior_close_not_bare_gapping():
    """MUTATION TARGET: reverting either operator-facing string back to 'stocks gapping X%+
    past the universe floors' — the wording that let a day-max scan-tick reading be misread as
    an opening-gap count and produced the original 42-vs-4 mismatch. The message must name the
    SETTLED OPEN explicitly and spell out the floor values so a future reader cannot substitute
    `mi_ep_scan_log`'s per-tick gap_pct for this measure again."""
    import inspect
    src = inspect.getsource(hc.run_catalyst_lattice_monitor)
    assert "OPENED" in src
    assert "prior close $5+" in src and "prior-day volume 50k+ shares" in src
    assert "stocks gapping" not in src and "stocks that gapped" not in src
