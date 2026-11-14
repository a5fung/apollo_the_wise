"""Breakout v1's three CONTEXT checks (#717, OPERATOR-SIGNED 2026-11-14, "ok, let's build it today").

Owner: `docs/setups/consolidation_breakout.md` (change log 2026-11-14). The checks, at the list night D on bars <= D:
  sma50_falling_under  out when the close is more than 3% under the 50-day SMA AND the 50-day is lower than 10 sessions ago
  downtrend_6m         out when the 50-day is lower than 10 sessions ago AND the 126-session return is negative
  lower_line           out when the re-widening swing V3 > 0.2123 (strict; MU 2021-12-21's own V3) AND the 30-session
                       lower line is flat or falling — scored only with >= 189 bars ("insufficient_history" passes)
These tests pin: the constants; his named cases on the era-A windows the research read (MELI and TDOC out, FIRY and
BLDP kept, MU kept by the strict line); PARITY with the research code itself (`tests/fixtures/bv1_context_reference.py`,
verbatim) on every Qullamaggie series in the scorecard fixtures; that no existing gate moved (a baseline written from
the pre-change module); and the nightly list's record of what the checks removed.
"""
from __future__ import annotations

import csv
import gzip
import importlib.util
import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import breakout_v1_list as bl
from agents.market_intelligence import consolidation_breakout as cb
from tests.fixtures import bv1_context_reference as ref

FX = Path(__file__).parent / "fixtures"
QM = FX / "qm_breakout_scorecard"
REPO = Path(__file__).resolve().parent.parent


def _bars_from(rows, keys="ohlcv"):
    rows = sorted(rows, key=lambda x: x["date"])
    ds = [date.fromisoformat(x["date"]) for x in rows]
    return cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rows] for k in keys])


def _ctx(b, D):
    return bv.context_gates(b, D, adr20=bv.adr20_at((b.h - b.l) / b.c, D))


def _window(b, D, W=200):
    """The research window: the last W bars ending D, NaN-padded on the left (o, h, l, c, v)."""
    out = np.full((5, W), np.nan)
    a = max(0, D - W + 1)
    for j, x in enumerate((b.o, b.h, b.l, b.c, b.v)):
        seg = np.asarray(x[a:D + 1], float)
        out[j, W - len(seg):] = seg
    return out


@pytest.fixture(scope="module")
def cases():
    """{ticker: (DailyBars ending on the list night, D)} — the five era-A windows of the lower-line research."""
    by = defaultdict(list)
    with gzip.open(FX / "bv1_context_cases.psv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            by[r["ticker"]].append(r)
    out = {}
    for t, rr in by.items():
        rr.sort(key=lambda x: int(x["i"]))
        ds = [date(2000, 1, 3) + timedelta(days=int(x["i"])) for x in rr]
        b = cb.daily_bars_from_arrays(ds, *[[float(x[k]) for x in rr] for k in "ohlcv"])
        out[t] = (b, len(b) - 1, rr[0]["D"])
    return out


@pytest.fixture(scope="module")
def qm_all():
    """[(set, eid, DailyBars)] — Qullamaggie's 269 dated buys and 488 widened positions (real split-adjusted bars)."""
    out = []
    for name, tag in (("bars.psv.gz", "dated"), ("bars_undated_widened.psv.gz", "widened")):
        by = defaultdict(list)
        with gzip.open(QM / name, "rt") as f:
            for r in csv.DictReader(f, delimiter="|"):
                by[r["eid"]].append(r)
        out += [(tag, eid, _bars_from(rr)) for eid, rr in by.items()]
    return out


# ── the constants ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_signed_constants():
    assert bv.CONTEXT_GATES == ("sma50_falling_under", "downtrend_6m", "lower_line")
    assert (bv.CTX_SMA_SESSIONS, bv.CTX_SMA_FALL_SESSIONS, bv.CTX_UNDER_SMA50_MAX) == (50, 10, -0.03)
    assert (bv.CTX_RET_SESSIONS, bv.CTX_RET_MIN_BARS, bv.CTX_RET_MAX) == (126, 120, 0.0)
    assert (bv.SWING_K, bv.SWING_LOOK, bv.CHART_SESSIONS, bv.CTX_WINDOW) == (ref.K, ref.LOOK, ref.CHART, 200)
    assert (bv.LOWER_LINE_SESSIONS, bv.LOWER_LINE_MIN_BARS) == (ref.N_LOW, ref.MIN_BARS) == (30, 189)
    assert bv.LOWER_LINE_V3_MIN == 0.2123 and bv.LOWER_LINE_SLOPE_MAX == 0.0
    # the list job's load already covers the deepest look-back (189); it did not change for these checks
    assert bl.HISTORY_SESSIONS == 200 >= bv.LOWER_LINE_MIN_BARS
    # the list's existing gates are untouched (the context gates are a separate tuple, appended after them)
    assert bv.GATES == ("history", "universe", "pinned", "adr", "rs", "prior_move", "base_depth", "ema21")


# ── his named cases (era-A windows, the research's own numbers) ────────────────────────────────────────────────────
@pytest.mark.parametrize("ticker,d,v3,slope,bars,status,out", [
    ("MELI", "2018-09-17", 0.483984, -0.001676, 200, "scored", True),            # his def-no: flat wide box
    ("TDOC", "2020-03-19", 0.244389, -0.036532, 200, "scored", True),            # his def-no: falling lows
    ("FIRY", "2021-01-04", 0.298825, +0.179699, 175, "insufficient_history", False),   # Qullamaggie big winner (E 01-05)
    ("BLDP", "2019-11-11", 0.236679, +0.065578, 200, "scored", False),           # Qullamaggie High buy (E 11-12): rising lows
    ("MU", "2021-12-20", 0.212297, -0.017690, 200, "scored", False),             # High buy (E 12-21): the line itself
])
def test_his_cases_on_the_research_windows(cases, ticker, d, v3, slope, bars, status, out):
    b, D, fd = cases[ticker]
    assert fd == d
    ll = _ctx(b, D)["lower_line"]
    v = ll["value"]
    assert v["v3"] == pytest.approx(v3, abs=5e-7) and v["slope30"] == pytest.approx(slope, abs=5e-7)
    assert v["bars"] == bars and v["status"] == status
    assert ll["pass"] is (not out)


def test_mu_sets_the_line_and_the_strict_greater_keeps_it(cases):
    """The line is MU 2021-12-21's own V3 (0.21229655), the loosest line flagging no must-keep buy with a flat or
    falling lower line; the research's ll.py ran 0.212, which would have flagged MU itself."""
    b, D, _ = cases["MU"]
    v = _ctx(b, D)["lower_line"]["value"]
    assert v["v3"] == pytest.approx(0.21229655, abs=1e-8) and v["slope30"] <= 0
    assert 0.212 < v["v3"] < bv.LOWER_LINE_V3_MIN
    W = _window(b, D)[None]
    V, L, n = ref.measure(W)
    assert bool(ref.flag(V, L, n, line=0.212)[0]) is True and bool(ref.flag(V, L, n, line=bv.LOWER_LINE_V3_MIN)[0]) is False


def test_the_cases_match_the_research_code(cases):
    for t, (b, D, _) in cases.items():
        W = _window(b, D)[None]
        V, L, n = ref.measure(W)
        g = _ctx(b, D)
        v = g["lower_line"]["value"]
        assert (v["v3"], v["slope30"], v["bars"]) == (float(V[0]), float(L[0]), int(n[0])), t
        assert g["lower_line"]["pass"] is (not bool(ref.flag(V, L, n, line=bv.LOWER_LINE_V3_MIN)[0])), t


def test_the_vendored_reference_is_the_probe_code_when_the_probe_dirs_are_present(cases):
    """When the research dirs are checked in, the vendored copy must give the probe modules' own numbers."""
    llp = REPO / "scripts/probes/_717_lowline_1114/ll.py"
    swd = REPO / "scripts/probes/_717_contract_1114/swings"
    if not (llp.exists() and (swd / "sw.py").exists() and (swd / "v3m.py").exists()):
        pytest.skip("the 2026-11-14 probe dirs are not in this checkout")
    import sys
    sys.path.insert(0, str(swd))
    try:
        spec = importlib.util.spec_from_file_location("_ll_probe", llp)
        llm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(llm)
        W = np.stack([_window(b, D) for b, D, _ in cases.values()])
        for x, y in zip(llm.measure(W), ref.measure(W)):
            assert np.array_equal(x, y, equal_nan=True)
    finally:
        sys.path.remove(str(swd))


# ── parity with the research code on every Qullamaggie series (real bars) ──────────────────────────────────────────
def test_parity_with_the_research_code_on_every_scorecard_series(qm_all):
    """Production `context_gates` vs the verbatim research code on the same bars, every 5th night of all 757 series:
    V3, the lower-line slope, the bar count and the 6-month return equal EXACTLY (the same float64 operations), and
    each check's verdict equals the research's (1d, A2 read over 10 sessions, the lower line at the signed line)."""
    n = flagged = 0
    hits = Counter()
    for tag, eid, b in qm_all:
        Ds = list(range(bv.DEEP, len(b), 5))
        if not Ds:
            continue
        WW = np.stack([_window(b, D) for D in Ds])
        V3, LS, NB = ref.measure(WW)
        R = ref.ret126_of(WW)
        rng = (b.h - b.l) / b.c
        for k, D in enumerate(Ds):
            adr = bv.adr20_at(rng, D)
            g = bv.context_gates(b, D, adr20=adr)
            v = g["lower_line"]["value"]
            for got, want in ((v["v3"], V3[k]), (v["slope30"], LS[k]), (g["downtrend_6m"]["value"]["ret126"], R[k])):
                assert (got is None and math.isnan(want)) or got == want, (tag, eid, D, got, want)
            assert v["bars"] == int(NB[k])
            u50, chg = ref.u50_s50chg10(np.asarray(b.c[:D + 1], float), D, adr)
            assert g["sma50_falling_under"]["pass"] is ref.one_d_keeps(u50, chg), (tag, eid, D)
            assert g["downtrend_6m"]["pass"] is ref.a2_10_keeps(chg, R[k]), (tag, eid, D)
            out3 = bool(ref.flag(V3[k:k + 1], LS[k:k + 1], NB[k:k + 1], line=bv.LOWER_LINE_V3_MIN)[0])
            assert g["lower_line"]["pass"] is (not out3), (tag, eid, D)
            for c in bv.CONTEXT_GATES:
                hits[c] += not g[c]["pass"]
            n += 1
    assert n > 25_000
    assert min(hits.values()) > 100            # every check acts on real bars (the comparison is not vacuous)


# ── no existing gate moved ───────────────────────────────────────────────────────────────────────────────────────────
def _same(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            _same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _same(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, (float, int)) and not isinstance(b, bool):
        assert b == pytest.approx(a, rel=1e-9, abs=1e-12), path
    else:
        assert a == b, path


def test_every_existing_gate_is_unchanged_on_qullamaggies_series(qm_all):
    """`bv1_existing_gates_baseline.json.gz` was written from the PRE-CHANGE module (HEAD 2dd3eb98) on his 269 dated
    buys (at D) and 462 widened positions (the night before the window's last session): every existing gate's pass and
    value, the level, the volume bar, ADR20, the range, the 50-day telemetry and the failed list. The new module gives
    the same on all 731, the failed list read with the context gates set aside."""
    with gzip.open(FX / "bv1_existing_gates_baseline.json.gz", "rt") as f:
        base = json.load(f)
    buys = {r["eid"]: r for r in csv.DictReader(open(QM / "buys.tsv"), delimiter="\t")}
    series = {(tag, eid): b for tag, eid, b in qm_all}
    moved = Counter()
    for key, want in base.items():
        tag, eid, D = key.split("|")
        b, D = series[(tag, eid)], int(D)
        if tag == "dated":
            r = buys[eid]
            g = bv.v1_gates(b, D, rs_best=float(r["rs_best"]), raw_close=float(r["raw_close_D"]))
        else:
            g = bv.v1_gates(b, D, rs_best=50.0)
        got = json.loads(json.dumps(g, default=str, allow_nan=False))
        pre = [k for k in got["failed"] if k not in bv.CONTEXT_GATES]
        _same({k: want[k] for k in want if k not in ("failed", "ok")},
              {"gates": {k: got["gates"][k] for k in bv.GATES}, **{k: got.get(k) for k in want if k not in ("gates", "failed", "ok")}},
              key)
        assert pre == want["failed"], key
        moved[(want["ok"], g["ok"])] += 1
    assert len(base) == 731
    assert moved[(False, True)] == 0                     # a context gate only ever REMOVES a name
    assert moved[(True, False)] > 0                      # ... and does remove some


def test_the_context_gates_read_only_bars_up_to_d(cases):
    b, D, _ = cases["TDOC"]
    D2 = D - 6
    want = _ctx(b, D2)
    junk = cb.daily_bars_from_arrays(b.dates, *[np.concatenate([np.asarray(x[:D2 + 1], float), np.full(D - D2, 1e6)])
                                                for x in (b.o, b.h, b.l, b.c, b.v)])
    assert _ctx(junk, D2) == want


def test_a_failed_history_gate_leaves_the_context_gates_unevaluated(cases):
    b, D, _ = cases["MELI"]
    g = bv.v1_gates(b, bv.DEEP - 1, rs_best=99.0)
    assert g["failed"] == ["history"] and all(g["gates"][k] == {"pass": None, "value": None} for k in bv.CONTEXT_GATES)


def test_blank_measures_pass_and_say_why():
    """Under 60 bars the 50-day 10 sessions back is blank, under 120 the 6-month return, under 189 the lower line —
    each passes (the research's NaN-passes), and the value records it."""
    n = 100
    ds = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    c = np.linspace(50.0, 10.0, n)                                  # a long decline: every check would want it out
    b = cb.daily_bars_from_arrays(ds, c, c * 1.02, c * 0.98, c, np.full(n, 1e6))
    g = bv.context_gates(b, 55, adr20=0.04)
    assert g["sma50_falling_under"]["pass"] and g["sma50_falling_under"]["value"]["s50_chg10_adr"] is None
    g = bv.context_gates(b, n - 1, adr20=0.04)
    assert not g["sma50_falling_under"]["pass"]                     # 50-day falling, close far under it
    assert g["downtrend_6m"]["pass"] and g["downtrend_6m"]["value"]["ret126"] is None        # < 120 bars
    assert g["lower_line"]["pass"] and g["lower_line"]["value"]["status"] == "insufficient_history"
    assert bv.context_gates(b, n - 1, adr20=None)["sma50_falling_under"]["pass"]              # no ADR: the change is blank


# ── the nightly list records what the checks removed ─────────────────────────────────────────────────────────────────
def test_the_list_counts_the_checks_and_names_the_names_they_alone_removed():
    """FCX 2021-12-07 (Qullamaggie, his "no") passes every other gate and is taken off by the lower line alone: the
    night's per-gate counts carry it, the passing rows do not, and `removed` names it."""
    buys = {(r["sym"], r["E"]): r for r in csv.DictReader(open(QM / "buys.tsv"), delimiter="\t")}
    r = buys[("FCX", "2021-12-07")]
    by = []
    with gzip.open(QM / "bars.psv.gz", "rt") as f:
        by = [x for x in csv.DictReader(f, delimiter="|") if x["eid"] == r["eid"]]
    b = _bars_from(by)
    D = list(b.dates).index(date.fromisoformat(r["D"]))
    b = cb.daily_bars_from_arrays(b.dates[:D + 1], *[np.asarray(x[:D + 1], float) for x in (b.o, b.h, b.l, b.c, b.v)])
    m = {"ticker": "FCX", "security_type": "CS", "listable": True, "history": True, "bars": b,
         "cidx": np.arange(len(b), dtype=np.int64)}
    removed: dict = {}
    rows, fails, n = bl.evaluate_members([m], [float(r["rs_best"])], date(2021, 12, 6), removed)
    assert rows == [] and n == 1 and fails == Counter({"lower_line": 1}) and removed == {"lower_line": ["FCX"]}
    rows, fails, n = bl.evaluate_members([m], [float(r["rs_best"])], date(2021, 12, 6))      # the old call still works
    assert rows == [] and fails == Counter({"lower_line": 1})
