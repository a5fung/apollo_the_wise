"""Breakout v1 (B1) — the pure rules reproduce the reference that his 12-of-24 result came from.

THE ACCEPTANCE BAR (docs/design/breakout_v1_build_spec_2026-10-29.md B1): `breakout_v1.v1_gates` + `breakout_triggered`,
re-scanning every watch night of his 28 dated setups' tickers (2019-01-02..2020-08-10, the reference's span and data
guard), classify the 24 primary setups exactly as `scripts/probes/_qm_0810_review/v1_check_variant_rs.txt`'s
"V3 + RSbest" column — HIT 10 | LATE 2 | EARLY 1 | MISS 11, 12 of 24 caught — and the 4 secondary ones as its
secondary table. A mismatch is a defect in the port, never a reason to move a threshold.

The fixture (`tests/fixtures/breakout_v1_parity/`, CI has no apollo_data) was built ONCE by
`scripts/probes/_breakout_v1_build/build_parity_fixture.py` from the reference code itself (v1_check + v1_check_variant
imported): the bars, the session calendar, the precomputed rs_best per (ticker, D) over the reference's $2/$5M pool,
and the reference's own per-night gate vector — so a mismatch names the gate and the night, not just a bucket.

WITH the breakdown check (his "yes" 2026-10-29) the measured classification is asserted per row too: it changed NO row
of the 28 (the builder's report; universe-wide it removed 3 of 486 fire-days, 3.71 -> 3.69 names a night).
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

# v1_check_variant_rs.txt, "V3 + RSbest" column — transcribed by hand from the committed text (not from the fixture)
RS_TXT = {
    "CELH-1": "HIT", "CELH-3": "HIT", "CODX-1": "HIT", "CVNA-1": "MISS", "CWH-2": "MISS", "LVGO-4": "HIT",
    "NVAX": "MISS", "OPK-2": "HIT", "OSTK-2": "LATE+2", "PLUG": "MISS", "SRNE-2": "LATE+1", "PRTS": "HIT",
    "DFS": "MISS", "QUMU": "MISS(8/10)", "ARCT": "HIT", "HL": "HIT", "IBIO-1": "HIT", "OPK-1": "MISS",
    "OPK-3": "MISS", "PENN-2": "HIT", "PENN-3": "EARLY-31", "RUN": "MISS", "TTOO": "MISS(8/10)", "NAIL": "MISS(8/10)",
    "CLSK": "HIT", "INO-3": "MISS", "INO-4": "HIT", "TRVN": "MISS"}
# MEASURED at the build (2026-10-29) with the breakdown check added: identical on every row.
WITH_BREAKDOWN = dict(RS_TXT)


def _bucket(c: str) -> str:
    return c.split("(")[0].split("+")[0].split("-")[0]


def _classify(n_bars: int, E: int, F: list, Pstar: int) -> str:
    """v1_check_variant.classify: HIT > LATE+1/+2 > EARLY (after his pole top P, before his day) > MISS;
    MISS(8/10) when his day is the file's last bar (a LATE fire cannot be observed)."""
    if E in F:
        return "HIT"
    for k in (1, 2):
        if E + k in F:
            return f"LATE+{k}"
    early = [f for f in F if Pstar < f < E]
    if early:
        return f"EARLY-{E - max(early)}"
    return "MISS(8/10)" if E == n_bars - 1 else "MISS"


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


def _fires(nights, *, breakdown: bool) -> list:
    out = []
    for D, _, g, trig in nights:
        G = g["gates"]
        shape = all(G[k]["pass"] for k in ("history", "universe", "rs", "prior_move", "higher_lows", "surf",
                                            "tightening")) and trig["level_pass"] and trig["volume_pass"]
        if shape and (not breakdown or G["breakdown"]["pass"]):
            out.append(D + 1)
    return out


def _classifications(fixture, scan, *, breakdown: bool) -> dict:
    meta, series = fixture
    res = {}
    for s in meta["setups"]:
        bars = series[s["t"]][0]
        E = next(i for i, d in enumerate(bars.dates) if d.isoformat() == s["e"])
        Pstar = cb._pole_top(bars.h, bars.c, E - 1 - bv.BASE_MAX, E - 1 - bv.BASE_MIN)
        res[s["key"]] = _classify(len(bars), E, _fires(scan[s["t"]], breakdown=breakdown), Pstar)
    return res


def test_the_fixture_is_compact_and_complete(fixture):
    meta, series = fixture
    size = sum(p.stat().st_size for p in FIX.iterdir())
    assert size < 3_000_000, size
    assert {s["key"] for s in meta["setups"]} == set(RS_TXT)
    assert sum(1 for s in meta["setups"] if s["group"] == "prim") == 24
    assert set(series) == {s["t"] for s in meta["setups"]}
    for t, (bars, _, _) in series.items():          # the reference's span, both ends (warm-up and MISS(8/10) depend on it)
        assert bars.dates[0] >= date(2019, 1, 2) and bars.dates[-1] <= date(2020, 8, 10)


def test_every_night_matches_the_reference_gate_vector(fixture, scan):
    """Gate by gate, on every evaluated night of his 23 names (the reference's V3 axes: universe $2/$5M, prior move,
    higher lows, surf, tightening, level = last-5 high, volume)."""
    meta, _ = fixture
    order = meta["ref_gate_order"]
    seen, bad = 0, []
    for t, nights in scan.items():
        for D, dd, g, trig in nights:
            G = g["gates"]
            mine = {"universe_loose": G["universe"]["pass"], "prior_move": G["prior_move"]["pass"],
                    "higher_lows": G["higher_lows"]["pass"], "surf": G["surf"]["pass"],
                    "tightening": G["tightening"]["pass"], "level_k5": trig["level_pass"],
                    "volume": trig["volume_pass"]}
            bits = "".join("1" if mine[k] else "0" for k in order)
            ref = meta["ref_gates"][f"{t}|{dd}"]
            seen += 1
            if bits != ref:
                bad.append((t, dd, {k: (ref[i], bits[i]) for i, k in enumerate(order) if ref[i] != bits[i]}))
    assert seen == len(meta["ref_gates"]) == 2879
    assert not bad, bad[:10]


def test_v3_rsbest_reproduces_his_12_of_24(fixture, scan):
    got = _classifications(fixture, scan, breakdown=False)
    assert got == RS_TXT
    prim = [s["key"] for s in fixture[0]["setups"] if s["group"] == "prim"]
    tally = defaultdict(int)
    for k in prim:
        tally[_bucket(got[k])] += 1
    assert dict(tally) == {"HIT": 10, "LATE": 2, "EARLY": 1, "MISS": 11}
    assert tally["HIT"] + tally["LATE"] == 12


def test_with_the_breakdown_check_the_measured_result(fixture, scan):
    """v1 as built (the breakdown check in): MEASURED identical to the reference on every one of the 28 rows —
    HIT 10 | LATE 2 | EARLY 1 | MISS 11, 12 of 24 caught. Pinned per row, not just the count."""
    got = _classifications(fixture, scan, breakdown=True)
    assert got == WITH_BREAKDOWN
    assert got == fixture[0]["expected_with_breakdown"]
    changed = {k: (RS_TXT[k], got[k]) for k in RS_TXT if got[k] != RS_TXT[k]}
    assert changed == {}


def test_the_12_caught_fires_pass_the_breakdown_check_at_their_own_watch_night(fixture, scan):
    """v1_breakdown_gate_check.txt: G1 (not below all of the 10/20/50-day) and G2 (no new 10-session low) pass at
    the watch night of every caught fire — the values printed there, re-read here."""
    printed = {"CELH-1": ("2020-06-23", 3.38, 2.87), "OSTK-2": ("2020-06-23", 27.38, 18.84),
               "SRNE-2": ("2020-07-31", 8.55, 6.12), "PENN-2": ("2020-06-23", 31.43, 27.52)}
    meta, series = fixture
    t_of = {s["key"]: s["t"] for s in meta["setups"]}
    for key, (fire_e, close_d, low10) in printed.items():
        night = next(n for n in scan[t_of[key]] if n[0] + 1 == next(
            i for i, d in enumerate(series[t_of[key]][0].dates) if d.isoformat() == fire_e))
        b = night[2]["gates"]["breakdown"]
        assert b["pass"] is True
        assert round(b["value"]["close"], 2) == close_d and round(b["value"]["prior_low10"], 2) == low10


# ── the operator's two live examples (mi_daily_closes pulls committed under scripts/probes/) ────────────────────
def _example(ticker: str):
    rr = [r for r in csv.DictReader(open(FIX / "operator_examples_bars.csv")) if r["ticker"] == ticker]
    return cb.daily_bars_from_arrays([date.fromisoformat(r["date"]) for r in rr],
                                     *[[float(r[k]) for r in rr] for k in ("o", "h", "l", "c", "v")])


def _at(bars, iso):
    return next(i for i, d in enumerate(bars.dates) if d.isoformat() == iso)


def test_odd_0908_is_rejected_by_the_breakdown_check_only_besides_rs():
    """His 'there's no setup on Sept 8': close 13.02 under the 10/20/50-day 14.20/13.53/14.94, low 12.99 under the
    10-session low 13.07 (v1_breakdown_gate_check.txt) — every SHAPE rule passes, the breakdown check fails."""
    b = _example("ODD")
    g = bv.v1_gates(b, _at(b, "2026-09-08"), rs_best=99.0)
    assert g["failed"] == ["breakdown"]
    v = g["gates"]["breakdown"]["value"]
    assert (round(v["sma10"], 2), round(v["sma20"], 2), round(v["sma50"], 2)) == (14.20, 13.53, 14.94)
    assert v["below_all"] is True and v["new_low"] is True and v["low"] == 12.99 and v["prior_low10"] == 13.07


def test_odd_1009_misses_on_volume_as_recorded():
    """v1_gates_odd_1009.txt: setup at the 10-08 close passes every shape rule and the breakdown check (strength
    96.6 fails RS); E = 10-09 clears the level 20.68 but volume 767,079 < 1.2x the 50-day 1,460,436."""
    b = _example("ODD")
    D = _at(b, "2026-10-08")
    g = bv.v1_gates(b, D, rs_best=96.6)
    assert g["failed"] == ["rs"]
    assert round(g["prior_move"], 2) == 0.71 and g["gates"]["surf"]["value"]["best"] == 16
    assert round(g["gates"]["tightening"]["value"]["ratio"], 2) == 0.80
    assert round(g["level"], 2) == 20.68 and round(g["vol_bar"]) == 1_460_436
    t = bv.breakout_triggered({"h": float(b.h[D + 1]), "v": float(b.v[D + 1])}, g)
    assert t["level_pass"] is True and t["volume_pass"] is False and t["fired"] is False


def test_zcsh_1028_passes_every_shape_rule_as_recorded():
    """v1_gates_at_1028.txt: prior +337% (pole 09-23 at 43.91, 25-session base), surf 7, tightening 0.56, level
    35.13, volume bar 1,922,869 shares; universe $34.63 / $41.3M."""
    b = _example("ZCSH")
    g = bv.v1_gates(b, _at(b, "2026-10-28"), rs_best=99.0)
    assert g["ok"] is True and g["failed"] == []
    assert round(g["prior_move"], 2) == 3.37 and g["pole_date"] == "2026-09-23"
    assert g["gates"]["prior_move"]["value"]["base_len"] == 25
    assert g["gates"]["surf"]["value"]["best"] == 7
    assert round(g["gates"]["tightening"]["value"]["ratio"], 2) == 0.56
    assert round(g["level"], 2) == 35.13 and round(g["vol_bar"]) == 1_922_869


def test_history_gate_short_and_holed_series():
    b = _example("ZCSH")
    g = bv.v1_gates(b, bv.DEEP - 1, rs_best=99.0)
    assert g["ok"] is False and g["failed"] == ["history"] and g["gates"]["surf"]["pass"] is None
    D = len(b) - 1
    cidx = np.arange(len(b))
    cidx[D - 30:] += 1                                  # one missing session inside the 86-bar window
    assert bv.v1_gates(b, D, rs_best=99.0, cidx=cidx)["failed"] == ["history"]
    assert "history" not in bv.v1_gates(b, D, rs_best=99.0, cidx=np.arange(len(b)))["failed"]


def test_rs_gate_reads_none_as_a_fail():
    b = _example("ZCSH")
    g = bv.v1_gates(b, _at(b, "2026-10-28"), rs_best=None)
    assert g["failed"] == ["rs"]
    assert bv.v1_gates(b, _at(b, "2026-10-28"), rs_best=98.0)["ok"] is True        # >= 98 inclusive
    assert bv.v1_gates(b, _at(b, "2026-10-28"), rs_best=97.9)["failed"] == ["rs"]


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
