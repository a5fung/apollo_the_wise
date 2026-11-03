"""Breakout v1 (B1) — the ported arithmetic still matches the reference it came from, on the pieces the 2026-11-02
rebuild KEPT; and the operator's live examples read as recorded under the rebuilt rules.

HISTORY. The first acceptance bar (docs/design/breakout_v1_build_spec_2026-10-29.md B1) was the 2020-08-10 review's
"V3 + RSbest" classification — HIT 10 | LATE 2 | EARLY 1 | MISS 11, 12 of his 24 dated good setups caught — on the
v1 gates higher-lows / surf / tightening / breakdown / RS >= 98. His spec sign-off of 2026-11-02
(`docs/analysis/cb_rebuild_from_qm_trades_2026-11-02.md`, "signd off") REMOVED those gates (his CODX / PENN charts
showed the definitions misread his pattern) and replaced the bar with the SCORECARD — Qullamaggie's own 269 dated
breakout buys (`tests/test_breakout_v2_stage1.py`). The 12-of-24 classification reproduces at main `456d4ff1` and
earlier (the commit before the rebuild), not on HEAD — the same note the SSoT carries for the frozen replays.

WHAT STAYS PINNED HERE. The fixture (`tests/fixtures/breakout_v1_parity/`, built ONCE by
`scripts/probes/_breakout_v1_build/build_parity_fixture.py` from the reference code itself) carries the reference's
own per-night gate vector on every evaluated night of his 23 names; the axes the rebuilt list still computes — the
universe floors, the prior-move VALUE (read at the reference's 0.30), the level (last-5 high) and the 50-day volume
(kept as `vol50` telemetry) — must match it night by night. A mismatch is a defect in the port, never a reason to move a
threshold.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import consolidation_breakout as cb

FIX = Path(__file__).parent / "fixtures" / "breakout_v1_parity"

# v1_check_variant_rs.txt, "V3 + RSbest" column — transcribed by hand from the committed text (not from the fixture).
# Kept as the fixture's KEY LIST (the 28 setups it was built for); the classification itself is retired (docstring).
RS_TXT = {
    "CELH-1": "HIT", "CELH-3": "HIT", "CODX-1": "HIT", "CVNA-1": "MISS", "CWH-2": "MISS", "LVGO-4": "HIT",
    "NVAX": "MISS", "OPK-2": "HIT", "OSTK-2": "LATE+2", "PLUG": "MISS", "SRNE-2": "LATE+1", "PRTS": "HIT",
    "DFS": "MISS", "QUMU": "MISS(8/10)", "ARCT": "HIT", "HL": "HIT", "IBIO-1": "HIT", "OPK-1": "MISS",
    "OPK-3": "MISS", "PENN-2": "HIT", "PENN-3": "EARLY-31", "RUN": "MISS", "TTOO": "MISS(8/10)", "NAIL": "MISS(8/10)",
    "CLSK": "HIT", "INO-3": "MISS", "INO-4": "HIT", "TRVN": "MISS"}


@pytest.fixture(scope="module")
def fixture():
    meta = json.loads(gzip.open(FIX / "meta.json.gz", "rt").read())
    cal = {d: i for i, d in enumerate(meta["sessions"])}
    rows = defaultdict(list)
    with gzip.open(FIX / "bars.csv.gz", "rt") as f:
        for r in csv.DictReader(f):
            rows[r["t"]].append(r)
    series = {}
    for t, rr in rows.items():
        bars = cb.daily_bars_from_arrays([date.fromisoformat(r["date"]) for r in rr],
                                         *[[float(r[k]) for r in rr] for k in ("o", "h", "l", "c", "v")])
        rc = np.array([float(r["rc"]) if r["rc"] else np.nan for r in rr])
        cidx = np.array([cal.get(r["date"], -10 ** 6) for r in rr])
        series[t] = (bars, rc, cidx)
    return meta, series


@pytest.fixture(scope="module")
def scan(fixture):
    """Every evaluated night of every ticker, as the reference evaluates them: E in the window and the data guard
    (bars D-85..E consecutive sessions)."""
    meta, series = fixture
    lo, hi = meta["win_lo"], meta["win_hi"]
    out = {}
    for t, (bars, rc, cidx) in series.items():
        n = len(bars)
        nights = []
        for D in range(bv.DEEP, n - 1):
            E = D + 1
            if not (lo <= bars.dates[E].isoformat() <= hi):
                continue
            if cidx[E] - cidx[D - bv.DEEP] != bv.DEEP + 1:
                continue
            dd = bars.dates[D].isoformat()
            g = bv.v1_gates(bars, D, rs_best=meta["rs_best"][t].get(dd), raw_close=float(rc[D]), cidx=cidx)
            trig = bv.breakout_triggered({"h": float(bars.h[E]), "v": float(bars.v[E])}, g)
            nights.append((D, dd, g, trig))
        out[t] = nights
    return out


def test_the_fixture_is_compact_and_complete(fixture):
    meta, series = fixture
    size = sum(p.stat().st_size for p in FIX.iterdir())
    assert size < 3_000_000, size
    assert {s["key"] for s in meta["setups"]} == set(RS_TXT)
    assert sum(1 for s in meta["setups"] if s["group"] == "prim") == 24
    assert set(series) == {s["t"] for s in meta["setups"]}
    for t, (bars, _, _) in series.items():          # the reference's span, both ends (warm-up and MISS(8/10) depend on it)
        assert bars.dates[0] >= date(2019, 1, 2) and bars.dates[-1] <= date(2020, 8, 10)


# the reference axes the rebuilt list no longer computes (removed 2026-11-02 on his spec sign-off)
REMOVED_AXES = frozenset({"higher_lows", "surf", "tightening"})


def test_every_night_matches_the_reference_on_the_axes_the_rebuild_kept(fixture, scan):
    """Axis by axis, on every evaluated night of his 23 names: the universe floors ($2 / $5M), the prior-move VALUE at
    the reference's own 0.30 line (`cb.PRIOR_MOVE_MIN`; the list's gate now reads 0.3214), the level (last-5 high,
    strict) and the reference's 50-day volume bar (`vol50` telemetry; the list's bar is now the 10-day)."""
    meta, series = fixture
    order = meta["ref_gate_order"]
    assert REMOVED_AXES < set(order)                     # the reference still names them; they are skipped, not lost
    assert sorted(k for k in order if k not in REMOVED_AXES) == ["level_k5", "prior_move", "universe_loose", "volume"]
    seen, bad = 0, []
    for t, nights in scan.items():
        bars = series[t][0]
        for D, dd, g, trig in nights:
            G = g["gates"]
            mine = {"universe_loose": G["universe"]["pass"],
                    "prior_move": g["prior_move"] is not None and g["prior_move"] >= cb.PRIOR_MOVE_MIN,
                    "level_k5": trig["level_pass"],
                    "volume": float(bars.v[D + 1]) >= bv.VOL_X * g["vol50"]}
            ref = meta["ref_gates"][f"{t}|{dd}"]
            seen += 1
            diff = {k: (ref[i], "1" if mine[k] else "0") for i, k in enumerate(order)
                    if k in mine and ref[i] != ("1" if mine[k] else "0")}
            if diff:
                bad.append((t, dd, diff))
    assert seen == len(meta["ref_gates"]) == 2879
    assert not bad, bad[:10]


# ── the operator's two live examples (mi_daily_closes pulls committed under scripts/probes/) ────────────────────
def _example(ticker: str):
    rr = [r for r in csv.DictReader(open(FIX / "operator_examples_bars.csv")) if r["ticker"] == ticker]
    return cb.daily_bars_from_arrays([date.fromisoformat(r["date"]) for r in rr],
                                     *[[float(r[k]) for r in rr] for k in ("o", "h", "l", "c", "v")])


def _at(bars, iso):
    return next(i for i, d in enumerate(bars.dates) if d.isoformat() == iso)


def test_odd_0908_is_still_rejected_now_by_the_ema21_and_50_day_rules():
    """His 'there's no setup on Sept 8' (2026-10-29; the breakdown check he ruled in that day was REMOVED in the
    2026-11-02 rebuild): the rebuilt rules still reject it — the close 13.02 sits 1.11 daily ranges under the 21-day EMA
    (the line is -0.6335) and under the 50-day SMA 14.94 — and every other rebuilt rule passes."""
    b = _example("ODD")
    g = bv.v1_gates(b, _at(b, "2026-09-08"), rs_best=99.0)
    assert g["failed"] == ["ema21", "sma50"]
    assert round(g["gates"]["ema21"]["value"]["vs_ema21_adr"], 2) == -1.11
    assert round(g["gates"]["sma50"]["value"]["sma50"], 2) == 14.94 and round(g["close"], 2) == 13.03


def test_odd_1009_his_better_date_is_listed_now_and_still_misses_on_volume():
    """v1_gates_odd_1009.txt: setup at the 10-08 close; strength 96.6 failed the old 98 and passes the rebuilt 35, so
    ODD is ON the rebuilt list that night (prior move +71%). E = 10-09 clears the level 20.68 but its volume 767,079 is
    under the rebuilt bar too — 1.2x the last 10 sessions = 883,641 (the old 50-day bar was 1,460,436)."""
    b = _example("ODD")
    D = _at(b, "2026-10-08")
    g = bv.v1_gates(b, D, rs_best=96.6)
    assert g["ok"] is True and g["failed"] == []
    assert round(g["prior_move"], 2) == 0.71
    assert round(g["level"], 2) == 20.68 and round(g["vol_bar"]) == 883_641 and round(1.2 * g["vol50"]) == 1_460_436
    t = bv.breakout_triggered({"h": float(b.h[D + 1]), "v": float(b.v[D + 1])}, g)
    assert t["level_pass"] is True and t["volume_pass"] is False and t["fired"] is False


def test_zcsh_1028_passes_every_rebuilt_rule():
    """v1_gates_at_1028.txt: prior +337% (pole 09-23 at 43.91, 25-session base), level 35.13; under the rebuilt rules
    the base is 5.50 daily ranges deep (band 1.51-8.98), the close 0.64 ranges ABOVE the 21-day EMA and above the
    50-day; the volume bar is 1.2x the last 10 sessions = 1,556,012 shares (the old 50-day bar 1,922,869)."""
    b = _example("ZCSH")
    g = bv.v1_gates(b, _at(b, "2026-10-28"), rs_best=99.0)
    assert g["ok"] is True and g["failed"] == []
    assert round(g["prior_move"], 2) == 3.37 and g["pole_date"] == "2026-09-23"
    assert g["gates"]["prior_move"]["value"]["base_len"] == 25
    assert round(g["gates"]["base_depth"]["value"]["depth_adr"], 2) == 5.50
    assert round(g["gates"]["ema21"]["value"]["vs_ema21_adr"], 2) == 0.64
    assert round(g["level"], 2) == 35.13 and round(g["vol_bar"]) == 1_556_012 and round(1.2 * g["vol50"]) == 1_922_869


def test_history_gate_short_and_holed_series():
    b = _example("ZCSH")
    g = bv.v1_gates(b, bv.DEEP - 1, rs_best=99.0)
    assert g["ok"] is False and g["failed"] == ["history"] and g["gates"]["sma50"]["pass"] is None
    D = len(b) - 1
    cidx = np.arange(len(b))
    cidx[D - 30:] += 1                                  # one missing session inside the 86-bar window
    assert bv.v1_gates(b, D, rs_best=99.0, cidx=cidx)["failed"] == ["history"]
    assert "history" not in bv.v1_gates(b, D, rs_best=99.0, cidx=np.arange(len(b)))["failed"]


def test_rs_gate_reads_none_as_a_fail():
    b = _example("ZCSH")
    g = bv.v1_gates(b, _at(b, "2026-10-28"), rs_best=None)
    assert g["failed"] == ["rs"]
    assert bv.v1_gates(b, _at(b, "2026-10-28"), rs_best=35.0)["ok"] is True        # >= 35 inclusive (the rebuilt line)
    assert bv.v1_gates(b, _at(b, "2026-10-28"), rs_best=34.9)["failed"] == ["rs"]


def test_breakout_triggered_is_strict_on_level_inclusive_on_volume():
    g = {"ok": True, "level": 10.0, "vol_bar": 1000.0}
    assert bv.breakout_triggered({"h": 10.0, "v": 5000}, g)["level_pass"] is False
    assert bv.breakout_triggered({"high": 10.01, "volume": 1000}, g)["fired"] is True
    assert bv.breakout_triggered({"h": 10.01, "v": 999.9}, g)["fired"] is False
    assert bv.breakout_triggered({"h": 11, "v": 2000}, dict(g, ok=False))["fired"] is False


def test_the_list_row_is_json_safe():
    b = _example("ZCSH")
    g = bv.v1_gates(b, _at(b, "2026-10-28"), rs_best=99.0)
    json.dumps(g, allow_nan=False)
