"""Breakout v1 — the PICK MODEL orders the nightly list; the older rankings stay as stored backups (2026-11-14).

OPERATOR-SIGNED 2026-11-14: "pick model, let's continue to eval and keep all the old models we have as backup".

What is pinned here:
  * THE FROZEN MODEL — `breakout_v1_pick_model`'s constants equal `scripts/probes/_717_pick_model_1113/coef.json`
    ("primary"); nothing in the live code refits it.
  * PARITY (the WOULD-FAIL-IF) — on three WHOLE era-A watch nights rebuilt from bars
    (`tests/fixtures/bv1_pick_model_parity/`, built by `scripts/probes/_717_pick_live_1114/01_parity.py`; the research's
    613 list rows = 502 names listed under today's rules + 111 only a context check removes; 229 of the 502 are rows
    of the research's ranked pool `bv1_rank2_1114/pool3_ranked.parquet`), the LIVE functions
    (`scan_members`, `night_cross_section`, `evaluate_members`, `rank_all`) reproduce the research score of every list
    row to 1e-6, on the research's own population. A wrong feature, a wrong fill, the wrong rank population or a
    shortened 52-week window each break it (shown below, not assumed).
  * THE BACKUPS — the order score is byte-for-byte what the code before this change produced for the same inputs
    (a golden generated from commit a1062a86); all three scores and ranks are stored on every row; ONE switch
    (`mi_safeguard_state('breakout_v1_ranking', 'global')`) picks which sets `list_rank`, the pick model by default.
  * the rules of the order: a missing input ranks last, ties by ticker, under every ranking.

ERA A ONLY (list nights <= 2022-03-31): no 2025-2026 research row is read here or by the fixture's builder.
"""
from __future__ import annotations

import asyncio
import csv
import gzip
import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import breakout_v1_list as bl
from agents.market_intelligence import breakout_v1_pick_model as pm
from agents.market_intelligence import consolidation_breakout as cb

REPO = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "bv1_pick_model_parity"
GOLDEN = Path(__file__).parent / "fixtures" / "bv1_order_score_golden.json"
TOL = 1e-6


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The frozen model
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_constants_are_the_fitted_primary_model_never_a_refit():
    co = json.load(open(REPO / pm.PROVENANCE["coef_file"]))
    m = co["models"][pm.PROVENANCE["model"]]
    assert tuple(m["features"]) == pm.FEATURES and len(pm.FEATURES) == 16
    assert m["intercept"] == pm.INTERCEPT and tuple(m["coef"]) == pm.COEF             # bit-for-bit, not approximately
    assert co["lambda"] == pm.PROVENANCE["l2_lambda"] and co["fit_rows"] == pm.PROVENANCE["fit_rows"]
    assert co["fit_positives"] == pm.PROVENANCE["fit_positives"] and co["registration"] == pm.PROVENANCE["registration"]
    assert pm.RAW_FEATURES == ("first_base",) and len(pm.PCT_FEATURES) == 15
    assert pm.HALF_FILL == {"rs_1m", "rs_3m", "rs_6m", "group_strength"}
    # scoring never changes the model: the constants are the same objects after a night is ranked
    before = (pm.INTERCEPT, pm.COEF, pm.FEATURES)
    bl.rank_all(_three_names(), [_inputs()], "pick_model")
    assert (pm.INTERCEPT, pm.COEF, pm.FEATURES) == before


def test_score_from_features_is_the_plain_linear_form_with_the_research_fill():
    f = {k: 0.25 for k in pm.FEATURES}
    assert pm.score_from_features(f) == pytest.approx(pm.INTERCEPT + 0.25 * sum(pm.COEF), abs=1e-12)
    # a blank cross-section rank reads 0.5 (the research's fillna); a blank bar-derived input leaves the name unscored
    g = dict(f, rs_6m=None, group_strength=None)
    want = pm.INTERCEPT + sum(c * (0.5 if k in ("rs_6m", "group_strength") else 0.25) for k, c in zip(pm.FEATURES, pm.COEF))
    assert pm.score_from_features(g) == pytest.approx(want, abs=1e-12)
    for k in pm.FEATURES:
        if k not in pm.HALF_FILL:
            assert pm.score_from_features(dict(f, **{k: None})) is None, k


def test_base_facts_52_week_window_major_low_and_completed_bases():
    # 300 bars: a low at bar 100, then a staircase of new highs — three gaps of >= 10 bars between new-high days
    n = 300
    h = np.full(n, 10.0); l = np.full(n, 9.0); c = np.full(n, 9.5)
    l[100] = 5.0
    for k, px in ((120, 11.0), (140, 12.0), (160, 13.0), (165, 14.0)):
        h[k] = px
    d52, since_low, bases = pm.base_facts(h, l, c, n - 1)
    assert d52 == 9.5 / 14.0 and since_low == n - 1 - 100
    # new-high days since the low (bar 100): 100 itself, 120, 140, 160, 165 -> gaps 20, 20, 20, 5 -> three completed bases
    assert bases == 3
    # the window is the LAST 252 bars: a higher high / lower low older than that is not seen
    h2, l2 = h.copy(), l.copy()
    h2[10], l2[10] = 99.0, 1.0
    assert pm.base_facts(h2, l2, c, n - 1) == (d52, since_low, bases)
    h2[n - pm.YEAR], l2[n - pm.YEAR] = 99.0, 1.0                                  # the oldest bar inside the window
    assert pm.base_facts(h2, l2, c, n - 1)[0] == 9.5 / 99.0 and pm.base_facts(h2, l2, c, n - 1)[1] == pm.YEAR - 1
    # fewer than 252 bars: the window is what exists
    assert pm.base_facts(h[:150], l[:150], c[:150], 149) == (9.5 / 12.0, 49, 2)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# PARITY against the research, whole nights from bars (the WOULD-FAIL-IF)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _f(x):
    return float(x) if x != "" else None


@pytest.fixture(scope="module")
def nights():
    meta = json.load(open(FIX / "meta.json"))
    assert meta["history_sessions"] == bl.HISTORY_SESSIONS and meta["long_sessions"] == pm.HISTORY_SESSIONS
    assert max(n["D"] for n in meta["nights"]) <= "2022-03-31"                       # ERA A only
    out = {int(n["ci"]): {"meta": n, "cal": [date.fromisoformat(d) for d in meta["calendar"][str(n["ci"])]],
                          "bars": {}, "pool": [], "expected": {}} for n in meta["nights"]}
    with gzip.open(FIX / "bars.psv.gz", "rt") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            out[int(r["ci"])]["bars"].setdefault(r["ticker"], []).append(
                (int(r["rel"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"]) if r["v"] else 0.0))
    with gzip.open(FIX / "pool.psv.gz", "rt") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            out[int(r["ci"])]["pool"].append({"ticker": r["ticker"], "r21": _f(r["r21"]), "r63": _f(r["r63"]),
                                              "r126": _f(r["r126"]), "group": r["sic2"] or None})
    for r in csv.DictReader(open(FIX / "expected.tsv"), delimiter="\t"):
        out[int(r["ci"])]["expected"][r["ticker"]] = {"score": float(r["research_score"]), "in_pool3": r["in_pool3"] == "1",
                                                      "context_removed": r["context_removed"] == "1",
                                                      "n_long": int(r["n_long_bars"])}
    return out


def _run_live(night, ci, *, long_sessions=None, with_context_names=True, groups=True):
    """The nightly job's own steps on one fixture night -> (rows ranked by `rank_all`, the removed dict, the pick dict).
    The fixture stores each list name's last 300 sessions; the job's short window is the last 200 of them."""
    cal = night["cal"]                                           # the last 300 session dates; cal[-1] = D
    n_long = long_sessions or pm.HISTORY_SESSIONS
    series, long = {}, {}
    for t, recs in night["bars"].items():
        def bars_from(rs):
            hh, ll, cc, vv = (np.array([x[k] for x in rs]) for k in (1, 2, 3, 4))
            # the OPEN is not stored: the list path never reads it (the loader uses the close)
            return cb.daily_bars_from_arrays([cal[len(cal) - 1 + x[0]] for x in rs], cc, hh, ll, cc, vv)
        short = [x for x in recs if x[0] > -bl.HISTORY_SESSIONS]
        series[t] = (bars_from(short), np.array([ci + x[0] for x in short], dtype=np.int64))
        long[t] = bars_from([x for x in recs if x[0] > -n_long])
    sm = bl.scan_members(series, today_ci=ci, types={t: ("CS", None) for t in series}, unapplied=set())
    members = sm["members"]
    assert {m["ticker"] for m in members} == set(series)         # every list name is a pool member, from its own bars
    pool = night["pool"]
    by_pool = {p["ticker"]: p for p in pool}
    for m in members:                                            # the pool file's returns ARE the bars' returns
        p = by_pool[m["ticker"]]
        assert (m["r21"], m["r63"], m["r126"]) == (p["r21"], p["r63"], p["r126"]), m["ticker"]
    rs_best, xs, n_groups = bl.night_cross_section(pool, [p["group"] if groups else None for p in pool])
    rb = dict(zip((p["ticker"] for p in pool), rs_best))
    pick = {"xs": xs, "long": long, "extra": []}
    removed = {}
    rows, fails, n_eval = bl.evaluate_members(members, [rb[m["ticker"]] for m in members], cal[-1], removed, pick)
    extra = pick["extra"] if with_context_names else []
    summary = bl.rank_all(rows, extra, bl.RANKING_PICK_MODEL)
    return rows, removed, pick, summary


def test_the_live_score_reproduces_the_research_on_whole_nights_from_bars(nights):
    """PARITY. WOULD FAIL IF the port were wrong: any of the 16 inputs, the within-night rank, the 0.5 fill, the
    population the rank is taken in, or the frozen coefficients."""
    n_rows = n_pool3 = n_ctx = 0
    worst = 0.0
    seen = {"rs_6m_blank": 0, "group_blank": 0, "under_252_bars": 0}
    for ci, night in nights.items():
        rows, removed, pick, summary = _run_live(night, ci)
        exp = night["expected"]
        ctx = {t for v in removed.values() for t in v}
        # the POPULATION the ranks are taken in = the research's list for the night (passing + context-removed)
        assert {r["ticker"] for r in rows} | ctx == set(exp), ci
        assert ctx == {t for t, e in exp.items() if e["context_removed"]} and ctx
        assert len(pick["extra"]) == len(ctx) and summary["population_n"] == len(exp)
        assert summary["ranked_by"] == "pick_model" and summary["fallback"] is None
        for r in rows:
            e = exp[r["ticker"]]
            assert r["pick_score"] is not None, r["ticker"]
            worst = max(worst, abs(r["pick_score"] - e["score"]))
            n_rows += 1
            n_pool3 += e["in_pool3"]
            seen["rs_6m_blank"] += r["pick_inputs"]["rs_6m"] is None
            seen["group_blank"] += r["pick_inputs"]["group_strength"] is None
            seen["under_252_bars"] += e["n_long"] < pm.YEAR
        n_ctx += len(ctx)
        # the stored order: rank 1 = the highest score, the rows sorted by it, ties by ticker
        assert [r["list_rank"] for r in rows] == list(range(1, len(rows) + 1))
        assert all(r["list_rank"] == r["rank_pick_model"] and r["ranked_by"] == "pick_model" for r in rows)
        key = [(-r["pick_score"], r["ticker"]) for r in rows]
        assert key == sorted(key)
    assert worst <= TOL, worst
    assert worst < 1e-12                                              # in fact float-exact up to summation order
    assert n_pool3 >= 200 and n_rows >= 400, (n_pool3, n_rows)        # >= 200 rows of the research's ranked pool
    assert len(nights) == 3 and n_ctx > 0
    assert {min(n["meta"]["E"] for n in nights.values()) <= "2020-12-31", max(n["meta"]["E"] for n in nights.values()) > "2020-12-31"} == {True}
    assert all(v > 0 for v in seen.values()), seen                    # the 0.5 fills and short histories are exercised


def test_the_parity_check_discriminates_a_wrong_population_window_or_group_source_fails_it(nights):
    """The check above is not satisfied by a broken port: each of these plausible mistakes moves the scores by far
    more than the tolerance (what the BROKEN system would read)."""
    ci = min(nights)
    night = nights[ci]
    exp = night["expected"]

    def worst(**kw):
        rows, *_ = _run_live(night, ci, **kw)
        return max(abs(r["pick_score"] - exp[r["ticker"]]["score"]) for r in rows)
    assert worst() <= TOL
    assert worst(with_context_names=False) > 1e-3        # ranks taken inside the gated list only (re-percentiled)
    assert worst(long_sessions=bl.HISTORY_SESSIONS) > 1e-3   # the 52-week facts read off the 200-session load
    assert worst(groups=False) > 1e-3                    # the industry-group strength dropped (every name at 0.5)


def test_a_wrong_coefficient_fails_parity(nights, monkeypatch):
    ci = min(nights)
    coef = list(pm.COEF)
    coef[pm.FEATURES.index("dollar_vol20")] += 0.01
    monkeypatch.setattr(pm, "COEF", tuple(coef))
    rows, *_ = _run_live(nights[ci], ci)
    assert max(abs(r["pick_score"] - nights[ci]["expected"][r["ticker"]]["score"]) for r in rows) > 1e-3


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The three rankings, the switch, and the rules of the order
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _inputs(**over):
    base = {"rs_1m": 50.0, "rs_3m": 50.0, "rs_6m": 50.0, "prior_move": 0.5, "runup6m": 1.0, "depth_adr": 4.0,
            "base_len": 20, "spread10_adr": 2.0, "adr20": 0.05, "dollar_vol20": 1e7, "dist_52w": 0.9, "dist_level": 0.5,
            "vs_ema21_adr": 0.5, "since_low": 100, "first_base": 0.0, "group_strength": 50.0}
    base.update(over)
    return base


def _row(ticker, *, runup=10.0, spread=2.0, dv=1e7, **over):
    pin = _inputs(dollar_vol20=dv, **over)
    return {"ticker": ticker, "level": 10.0, "rs_best": 90.0, "runup6m_adr": runup, "spread10_adr": spread,
            "pick_inputs": pin, "dollar_vol20": pin["dollar_vol20"]}


def _three_names():
    # AAA: the biggest run-up and the tightest closes (order score 1st) but the smallest dollar volume
    # BBB: the middle on everything
    # CCC: the largest dollar volume (and so the pick model's 1st: its weight is by far the largest) but order score last
    return [_row("BBB", runup=20.0, spread=2.0, dv=2e7), _row("CCC", runup=10.0, spread=3.0, dv=9e7),
            _row("AAA", runup=30.0, spread=1.0, dv=1e7)]


@pytest.mark.parametrize("ranking,want", [("pick_model", ["CCC", "BBB", "AAA"]), ("order_score", ["AAA", "BBB", "CCC"]),
                                          ("dollar_volume", ["CCC", "BBB", "AAA"])])
def test_the_switch_value_sets_list_rank_and_every_ranking_is_stored_on_every_row(ranking, want):
    rows = _three_names()
    summary = bl.rank_all(rows, [], ranking)
    assert [r["ticker"] for r in rows] == want and [r["list_rank"] for r in rows] == [1, 2, 3]
    by = {r["ticker"]: r for r in rows}
    for r in rows:                                                   # all three scores + ranks, whichever is selected
        assert r["ranked_by"] == ranking and r["list_rank"] == r["rank_" + ranking]
        assert r["order_score"] is not None and r["pick_score"] is not None and r["dollar_vol20"] is not None
    assert [by[t]["rank_order_score"] for t in ("AAA", "BBB", "CCC")] == [1, 2, 3]
    assert [by[t]["rank_dollar_volume"] for t in ("CCC", "BBB", "AAA")] == [1, 2, 3]
    assert [by[t]["rank_pick_model"] for t in ("CCC", "BBB", "AAA")] == [1, 2, 3]
    assert summary["selected"] == summary["ranked_by"] == ranking and summary["fallback"] is None
    assert summary["scored"] == {"pick_model": 3, "order_score": 3, "dollar_volume": 3}
    assert set(summary["scores"]) == {"AAA", "BBB", "CCC"} and all(len(v) == 3 for v in summary["scores"].values())
    assert summary["top10"]["order_score"] == ["AAA", "BBB", "CCC"] and summary["top10"]["dollar_volume"] == ["CCC", "BBB", "AAA"]


def test_the_audit_copy_of_the_scores_is_capped_so_a_busy_night_fits_the_audit_row_budget():
    """A 1,300-name night (era A's largest list) must not overflow mi_audit_log's 32,000-char detail: the audit row
    carries the first 300 names' scores by list rank and counts the rest; every ROW still carries all three."""
    from agents.market_intelligence import db
    rows = [_row(f"T{k:04d}", runup=float(k % 97), spread=1.0 + (k % 13) / 10, dv=1e7 + k * 12345.678) for k in range(1300)]
    s = bl.rank_all(rows, [_inputs() for _ in range(300)], "pick_model")
    assert len(s["scores"]) == bl.AUDIT_SCORES_MAX and s["scores_omitted"] == 1000
    assert list(s["scores"]) == [r["ticker"] for r in rows[:bl.AUDIT_SCORES_MAX]]          # the best-ranked names
    assert len(json.dumps(s)) < db._AUDIT_DETAIL_MAX // 2
    assert all(r["pick_score"] is not None and r["rank_order_score"] and r["rank_dollar_volume"] for r in rows)


def test_the_default_ranking_is_the_pick_model_and_an_unknown_one_is_refused():
    assert bl.DEFAULT_RANKING == "pick_model" and bl.RANKINGS == ("pick_model", "order_score", "dollar_volume")
    rows = _three_names()
    bl.rank_all(rows)
    assert {r["ranked_by"] for r in rows} == {"pick_model"}
    with pytest.raises(ValueError):
        bl.rank_all(_three_names(), [], "rs_best")


def test_a_name_missing_an_input_has_no_score_and_ranks_last_under_that_ranking_only():
    rows = [_row("AAA", dv=9e7), _row("BBB", dv=5e7, since_low=None), _row("CCC", dv=1e7)]
    rows[2]["runup6m_adr"] = None                                    # CCC: no order score
    bl.rank_all(rows, [], "pick_model")
    by = {r["ticker"]: r for r in rows}
    assert by["BBB"]["pick_score"] is None and by["BBB"]["rank_pick_model"] == 3      # missing a bar-derived input
    assert [r["ticker"] for r in rows] == ["AAA", "CCC", "BBB"]
    assert by["CCC"]["order_score"] is None and by["CCC"]["rank_order_score"] == 3    # the same rule as before
    assert by["BBB"]["rank_dollar_volume"] == 2                                        # its other rankings are intact
    # a blank cross-section input is NOT a missing input: it reads 0.5 (the research's fill) and the name is scored
    rows = [_row("AAA"), _row("BBB", rs_6m=None, group_strength=None)]
    bl.rank_all(rows, [], "pick_model")
    assert all(r["pick_score"] is not None for r in rows)
    # no dollar volume -> last under dollar volume
    rows = [_row("AAA", dv=1e7), _row("BBB", dv=9e7)]
    rows[1]["dollar_vol20"] = None; rows[1]["pick_inputs"]["dollar_vol20"] = None
    bl.rank_all(rows, [], "dollar_volume")
    assert [r["ticker"] for r in rows] == ["AAA", "BBB"]


def test_ties_break_by_ticker_under_every_ranking():
    for ranking in bl.RANKINGS:
        rows = [_row("ZZZ"), _row("MMM"), _row("AAA")]              # identical inputs -> identical scores
        bl.rank_all(rows, [], ranking)
        assert [r["ticker"] for r in rows] == ["AAA", "MMM", "ZZZ"], ranking
        assert len({r[bl.RANKING_SCORE_COL[ranking]] for r in rows}) == 1
    # several unscored names: after every scored name, by ticker
    rows = [_row("ZZZ", since_low=None), _row("BBB"), _row("CCC", since_low=None)]
    bl.rank_all(rows, [], "pick_model")
    assert [r["ticker"] for r in rows] == ["BBB", "CCC", "ZZZ"]


def test_the_context_removed_names_shape_the_ranks_but_are_never_listed():
    rows = [_row("AAA", dv=3e7), _row("BBB", dv=1e7)]
    alone = [r["pick_score"] for r in (bl.rank_all(rows, [], "pick_model"), rows)[1]]
    rows2 = [_row("AAA", dv=3e7), _row("BBB", dv=1e7)]
    s = bl.rank_all(rows2, [_inputs(dollar_vol20=2e7), _inputs(dollar_vol20=9e7)], "pick_model")
    assert [r["ticker"] for r in rows2] == ["AAA", "BBB"] and len(rows2) == 2          # the two extras are not rows
    assert s["population_n"] == 4 and s["context_removed_in_population"] == 2
    assert [r["pick_score"] for r in rows2] != alone                                   # but they moved the ranks
    assert bl.pick_scores([]) == []


def test_if_the_selected_ranking_scores_no_name_the_order_score_sets_the_order_and_says_so():
    rows = [{"ticker": t, "level": 1.0, "rs_best": 50.0, "runup6m_adr": float(k), "spread10_adr": 1.0}
            for k, t in enumerate(("AAA", "BBB", "CCC"))]            # no pick inputs at all
    s = bl.rank_all(rows, [], "pick_model")
    assert s["selected"] == "pick_model" and s["ranked_by"] == "order_score" and "scored no name" in s["fallback"]
    assert [r["ticker"] for r in rows] == ["CCC", "BBB", "AAA"] and {r["ranked_by"] for r in rows} == {"order_score"}
    assert bl.rank_all([], [], "pick_model")["fallback"] is None     # an empty night is not a fallback


def test_the_order_score_is_byte_for_byte_what_the_code_before_the_change_produced():
    """The backup must be the SAME ranking, not a lookalike: a golden from `rank_rows` at commit a1062a86 (the last
    commit before the pick model), compared by the float's exact hex — through `rank_rows` and through `rank_all`."""
    g = json.load(open(GOLDEN))
    assert "a1062a86" in g["generated_from"] and len(g["inputs"]) == 260
    assert sum(e[1] is None for e in g["expected"]) == 14            # the golden carries unscored names
    assert len({e[1] for e in g["expected"]}) < 246                  # ... and ties

    def as_expected(rows, rank_col):
        return [[r["ticker"], None if r["order_score"] is None else r["order_score"].hex(), r[rank_col]]
                for r in sorted(rows, key=lambda r: r[rank_col])]
    assert as_expected(bl.rank_rows([dict(r) for r in g["inputs"]]), "list_rank") == g["expected"]
    for ranking in bl.RANKINGS:                                      # whichever ranking is selected, the backup is intact
        rows = [dict(r) for r in g["inputs"]]
        bl.rank_all(rows, [], ranking)
        assert as_expected(rows, "rank_order_score") == g["expected"], ranking
    rows = [dict(r) for r in g["inputs"]]
    bl.rank_all(rows, [], "order_score")                             # the switch set back = the old list order exactly
    assert [[r["ticker"], r["list_rank"]] for r in rows] == [[e[0], e[2]] for e in g["expected"]]


# ── the switch read ──────────────────────────────────────────────────────────────────────────────
def _switch(monkeypatch, *, row="absent", exc=None, fail_first=0):
    calls = {"n": 0}

    async def state_f(safeguard, account_mode, timeout=None):
        assert (safeguard, account_mode) == ("breakout_v1_ranking", "global")
        assert timeout == bl.RANKING_READ_TIMEOUT_S                    # bounded: a hung read cannot eat the job's budget
        calls["n"] += 1
        if exc and (not fail_first or calls["n"] <= fail_first):
            raise exc
        return None if row == "absent" else {"state": row}
    monkeypatch.setattr(bl, "get_safeguard_state", state_f)
    monkeypatch.setattr(bl, "RANKING_READ_PAUSE_S", 0.0)
    return asyncio.run(bl.get_ranking()) + (calls["n"],)


def test_the_switch_reads_the_database_row_and_nothing_else_no_row_is_the_pick_model(monkeypatch):
    assert _switch(monkeypatch) == ("pick_model", "default", None, 1)                 # no row: the pick model
    for v in bl.RANKINGS:
        assert _switch(monkeypatch, row=v) == (v, "db", None, 1)
        assert _switch(monkeypatch, row=f"  {v.upper()} ") == (v, "db", None, 1)
    # ONE source (review 2026-11-14 finding 7): an env var the acting-rules view cannot see must not move the order
    monkeypatch.setenv("BREAKOUT_V1_RANKING", "dollar_volume")
    assert _switch(monkeypatch)[:2] == ("pick_model", "default")
    assert _switch(monkeypatch, row="order_score")[:2] == ("order_score", "db")
    assert not hasattr(bl, "RANKING_SWITCH_ENV")
    # an unknown value never stops the list: the pick model, and the reason is carried to the audit row
    r, src, note, _n = _switch(monkeypatch, row="on")
    assert (r, src) == ("pick_model", "default") and "unknown switch state 'on'" in note


def test_a_transient_switch_read_failure_is_retried_so_a_backup_choice_is_not_undone_for_a_night(monkeypatch):
    """Review 2026-11-14 finding 6. WOULD FAIL IF one failed read fell straight to the default: the row says
    `order_score`, the first read (or the first two) raises — the night must still be ranked by the order score."""
    for k in (1, bl.RANKING_READ_TRIES - 1):
        assert _switch(monkeypatch, row="order_score", exc=RuntimeError("blip"), fail_first=k) == ("order_score", "db", None, k + 1)
    # every try failing: the pick model, noted — and it tried exactly RANKING_READ_TRIES times
    r, src, note, n = _switch(monkeypatch, row="order_score", exc=RuntimeError("db down"))
    assert (r, src, n) == ("pick_model", "default", bl.RANKING_READ_TRIES) and "switch read failed" in note


def test_the_acting_rules_view_names_the_ranking_that_is_acting_with_or_without_a_row():
    """Review 2026-11-14 finding 7 / the disclosed "off (no row)": no row means the PICK MODEL acts, and the view's
    ENTRY section must say so; a row shows its value."""
    from scripts import live_rules as lr
    res = lr.Resolver({}, {}, lr.ProdState(reachable=True))
    line = [l for l in lr.build_entry_section(res) if "breakout_v1_ranking" in l]
    assert len(line) == 1 and "global=pick_model [no mi_safeguard_state row — code default]" in line[0]
    res.prod.toggles = [{"safeguard": "breakout_v1_ranking", "account_mode": "global", "state": "order_score",
                         "last_transition_at": "2026-11-16 17:00:00+00"}]
    line = [l for l in lr.build_entry_section(res) if "breakout_v1_ranking" in l]
    assert "global=order_score [mi_safeguard_state (set 2026-11-16)]" in line[0]


def test_the_switch_is_a_database_row_the_acting_rules_view_discovers():
    """`scripts/live_rules.py` (the OPEN ritual's acting-rules check) finds every `mi_safeguard_state` switch by
    scanning for its registration: the ranking switch must be one of them, so a flipped row shows up there."""
    from scripts.live_rules import discover_runtime_toggles
    t = discover_runtime_toggles()
    assert bl.RANKING_SWITCH in t and t[bl.RANKING_SWITCH].style == "state"
    assert t[bl.RANKING_SWITCH].where.startswith("agents/market_intelligence/breakout_v1_list.py")


def test_the_entry_list_read_returns_the_names_in_list_rank_order():
    """The entry job's ONE list read orders by `list_rank` — the column the selected ranking sets. (That the slots
    then follow `list_rank` against a contradicting order score is exercised in
    tests/test_breakout_v1_entry.py::test_the_slot_goes_by_list_rank_even_when_the_order_score_says_the_opposite.)"""
    from agents.market_intelligence import db
    seen = {}

    class Conn:
        async def fetch(self, sql, *a):
            seen["sql"] = " ".join(sql.split())
            return [{"ticker": "BBB", "list_rank": 1}, {"ticker": "AAA", "list_rank": 2}]

    class Pool:
        def acquire(self):
            class Ctx:
                async def __aenter__(s):
                    return Conn()

                async def __aexit__(s, *e):
                    return False
            return Ctx()

    async def run():
        orig = db.get_pool

        async def fake_pool():
            return Pool()
        db.get_pool = fake_pool
        try:
            return await db.bv1_get_list(date(2026, 11, 16))
        finally:
            db.get_pool = orig
    rows = asyncio.run(run())
    assert [r["ticker"] for r in rows] == ["BBB", "AAA"]
    assert seen["sql"].endswith("FROM mi_breakout_v1_list WHERE scan_date = $1 ORDER BY list_rank")


def test_the_message_names_the_ranking_that_set_the_order():
    today = date(2026, 11, 16)
    for ranking, label, cell in (("pick_model", "the pick model", None), ("order_score", "the order score", None),
                                 ("dollar_volume", "dollar volume", "90M")):
        rows = _three_names()
        bl.rank_all(rows, [], ranking)
        msg = bl.format_list_message(today, rows)
        assert f"the top 3 by {label})" in msg and "|" not in msg.split("```")[1]
        first = msg.split("```")[1].strip().splitlines()[1].split()
        assert first[1] == rows[0]["ticker"]
        if cell:
            assert first[3] == cell
        else:
            assert float(first[3]) == pytest.approx(rows[0][bl.RANKING_SCORE_COL[ranking]], abs=0.006)
    # rows ranked before the change (no `ranked_by`) still read as the order score
    old = bl.rank_rows([{"ticker": "AAA", "level": 1.0, "rs_best": 50.0, "runup6m_adr": 1.0, "spread10_adr": 1.0}])
    assert "by the order score)" in bl.format_list_message(today, old)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The nightly job end to end (in-memory fakes of its reads / writes; no database, no network)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _job(monkeypatch, **fake_attrs):
    from test_breakout_v1_list import TODAY, Fakes
    f = Fakes(monkeypatch)
    for k, v in fake_attrs.items():
        setattr(f, k, v)
    out = asyncio.run(bl.run_breakout_v1_list(TODAY))
    return f, out, f.lists[TODAY]


def test_the_job_stores_all_three_rankings_per_row_and_in_the_audit_row_with_the_pick_model_setting_the_order(monkeypatch):
    from agents.market_intelligence import db
    f, out, rows = _job(monkeypatch)
    r = rows[0]
    assert r["ticker"] == "ZCSH" and r["ranked_by"] == "pick_model" and r["list_rank"] == r["rank_pick_model"] == 1
    assert r["rank_order_score"] == 1 and r["rank_dollar_volume"] == 1
    assert r["order_score"] == 1.0 and r["pick_score"] is not None and r["dollar_vol20"] >= bv.MIN_DOLLAR_VOL
    assert r["dollar_vol20"] == r["gates"]["gates"]["universe"]["value"]["dollar_vol20"]
    # the 16 raw inputs ride in the row's gates JSON (jsonb-safe)
    pin = r["gates"]["pick_inputs"]
    assert set(pin) == set(pm.FEATURES) and pin["group_strength"] is None            # no industry code cached -> blank
    assert pin["rs_3m"] is not None and pin["dist_52w"] is not None and pin["first_base"] in (0.0, 1.0)
    json.dumps(r["gates"], allow_nan=False)
    assert all(c in r for c in db.BV1_LIST_COLS)                                      # every stored column has a value
    rk = out["ranking"]
    assert rk["selected"] == rk["ranked_by"] == "pick_model" and rk["source"] == "default" and rk["fallback"] is None
    assert rk["switch"] == "breakout_v1_ranking" and rk["note"] is None and rk["sic_error"] is None
    assert rk["scores"] == {"ZCSH": [1.0, round(r["pick_score"], 4), int(round(r["dollar_vol20"]))]} and rk["scores_omitted"] == 0
    assert rk["top10"] == {k: ["ZCSH"] for k in bl.RANKINGS} and rk["scored"] == {k: 1 for k in bl.RANKINGS}
    assert rk["listed_with_52w_facts"] == 1 and rk["listed_with_group_strength"] == 0 and rk["pool_with_industry_code"] == 0
    assert rk["model"]["coef_file"].endswith("coef.json")
    ev = [a for a in f.audit if a[0] == "breakout_v1_list_run"]
    assert len(ev) == 1 and ev[0][2]["ranking"] == rk                                 # the audit row carries it
    assert "by the pick model)" in f.sent[0]


@pytest.mark.parametrize("state", ["order_score", "dollar_volume"])
def test_the_database_switch_puts_a_backup_ranking_back_in_charge_with_no_code_change(monkeypatch, state):
    f, out, rows = _job(monkeypatch, ranking_state=state)
    assert {r["ranked_by"] for r in rows} == {state} and out["ranking"]["source"] == "db"
    assert out["ranking"]["selected"] == state and all(r["list_rank"] == r["rank_" + state] for r in rows)
    assert rows[0]["pick_score"] is not None                                          # the pick model is still computed
    assert f"by {bl.RANKING_LABEL[state]})" in f.sent[0]


def test_a_bad_switch_value_or_a_failed_read_never_stops_the_list_and_is_noted(monkeypatch):
    f, out, rows = _job(monkeypatch, ranking_state="banana")
    assert rows and out["ranking"]["selected"] == "pick_model" and "banana" in out["ranking"]["note"]
    f, out, rows = _job(monkeypatch, ranking_exc=RuntimeError("db down"))
    assert rows and out["ranking"]["selected"] == "pick_model" and "switch read failed" in out["ranking"]["note"]
    # the industry-code read failing blanks ONE input (it reads 0.5) — the list is written and the reason recorded
    f, out, rows = _job(monkeypatch, sic_exc=RuntimeError("sic table missing"))
    assert rows and rows[0]["pick_score"] is not None and "sic table missing" in out["ranking"]["sic_error"]
    assert out["error"] is None and out["message"] == "sent"


def test_the_longer_bar_load_feeds_only_the_pick_model_every_older_value_is_unchanged(nights, monkeypatch):
    """The job now loads 300 sessions (the 52-week facts need 252 bars). The pool, the gates, the level, the volume bar
    and the order score must read exactly the 200-session rows they read before: run one fixture night through the
    whole job twice — the long load at 300 and at 200 — and every pre-existing stored value is identical."""
    from test_breakout_v1_list import Fakes
    ci = min(nights)
    night = nights[ci]
    cal = night["cal"]
    bar_rows = [(t, cal[len(cal) - 1 + x[0]], x[3], x[1], x[2], x[3], x[4]) for t, recs in sorted(night["bars"].items()) for x in recs]
    types = {t: ("CS", None) for t in night["bars"]}

    def run(long_sessions):
        monkeypatch.setattr(pm, "HISTORY_SESSIONS", long_sessions)
        f = Fakes(monkeypatch, cal=cal, rows=bar_rows, types=types)
        out = asyncio.run(bl.run_breakout_v1_list(cal[-1]))
        return out, {r["ticker"]: r for r in f.lists[cal[-1]]}
    out300, r300 = run(300)
    out200, r200 = run(200)
    assert len(r300) > 50 and set(r300) == set(r200)
    old_cols = ("level", "vol_bar", "adr20", "rs_best", "close", "security_type", "order_score", "runup6m_adr",
                "spread10_adr", "rank_order_score", "dollar_vol20", "rank_dollar_volume")
    for t in r300:
        a, b = r300[t], r200[t]
        assert {k: a[k] for k in old_cols} == {k: b[k] for k in old_cols}, t
        ga, gb = ({k: v for k, v in x["gates"].items() if k != "pick_inputs"} for x in (a, b))
        assert ga == gb, t
    for k in ("universe_n", "listable_n", "evaluated", "passing", "gate_fails", "context_removed", "counts"):
        assert out300[k] == out200[k], k
    # ... while the 52-week facts DO read the longer load (so the pick model's order differs when it is cut to 200)
    moved = [t for t in r300 if r300[t]["gates"]["pick_inputs"]["since_low"] != r200[t]["gates"]["pick_inputs"]["since_low"]]
    assert moved and any(r300[t]["rank_pick_model"] != r200[t]["rank_pick_model"] for t in r300)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Review 2026-11-14 (second round): the audit row fits, the pick model cannot stop the list, a bad old bar
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _busy_night_detail(n: int) -> dict:
    """The WHOLE audit detail of an `n`-name night with real-shaped tickers: `_new_out` filled the way `_run` fills it
    (the ticker list, the fund lists and the context-removed lists at their caps, the `ranking` block)."""
    import random
    import string
    rng = random.Random(717)
    tick = sorted({"".join(rng.choice(string.ascii_uppercase) for _ in range(rng.choice((3, 4, 4, 4, 5)))) for _ in range(3 * n)})[:n]
    rows = [_row(t, runup=float(k % 97), spread=1.0 + (k % 13) / 10, dv=1e7 + k * 12345.678) for k, t in enumerate(tick)]
    out = bl._new_out(date(2021, 2, 10))
    out["ranking"] = bl.rank_all(rows, [_inputs() for _ in range(300)], "pick_model")
    out["ranking"].update(source="default", note=None, switch=bl.RANKING_SWITCH, sic_error=None, pool_with_industry_code=2000,
                          industry_groups=55, listed_with_group_strength=900, listed_with_52w_facts=n, long_error=None,
                          short_bar_facts_n=bl.SHORT_FALLBACK_LIST_MAX, short_bar_facts=tick[:bl.SHORT_FALLBACK_LIST_MAX],
                          model=pm.PROVENANCE)
    out.update(prefilter_tickers=4000, universe_n=3000, listable_n=2800, evaluated=2700, passing=n, written=n,
               counts={f"admitted_{k}": 1000 + k for k in range(12)}, gate_fails={f"gate_{k}": 1000 + k for k in range(22)},
               context_removed_n={k: 400 for k in ("a", "b", "c")},
               context_removed={k: tick[:bl.CONTEXT_REMOVED_LIST_MAX] for k in ("a", "b", "c")},
               fund_kept_tickers=tick[:bl.FUND_EXCLUDED_LIST_MAX],
               fund_excluded_tickers={k: tick[:bl.FUND_EXCLUDED_LIST_MAX] for k in ("fund_leveraged", "fund_no_name", "fund_multi")},
               tickers=[r["ticker"] for r in rows], message="suppressed_paper_off", wall_s=61.2)
    return out


def test_the_whole_audit_row_fits_the_budget_on_the_busiest_night_and_stays_queryable_json():
    """Review 2026-11-14 finding 3: the earlier cap test measured only the `ranking` block. The WHOLE detail of a
    1,353-name night (era A's largest list) and of a night twice that must come out of `fit_audit_detail` under
    mi_audit_log's budget, so `db` never wraps it as a `_head` string and `detail->'ranking'` stays a JSON object.
    WOULD FAIL IF nothing were shed: the unfitted 2,700-name detail is over the budget (asserted)."""
    from agents.market_intelligence import db
    from agents.market_intelligence.consolidation_breakout_shadow import _json_safe
    normal = _json_safe(_busy_night_detail(250))
    assert bl.fit_audit_detail(json.loads(json.dumps(normal))) == normal            # an ordinary night: untouched
    for n in (1353, 2700, 6000):
        raw = _json_safe(_busy_night_detail(n))
        fitted = bl.fit_audit_detail(json.loads(json.dumps(raw)))
        text = json.dumps(fitted)
        assert len(text) <= db._AUDIT_DETAIL_MAX - bl.AUDIT_HEADROOM, (n, len(text))
        stored = json.loads(db._fit_audit_detail(text)) if hasattr(db, "_fit_audit_detail") else fitted
        assert "_truncated" not in stored and isinstance(stored["ranking"], dict)
        assert stored["ranking"]["top10"] == raw["ranking"]["top10"] and stored["ranking"]["ranked_by"] == "pick_model"
        if n >= 2700:
            assert len(json.dumps(raw)) > db._AUDIT_DETAIL_MAX                       # the unfitted row WOULD overflow
            assert fitted["audit_shed"][0] == "ranking.scores" and fitted["ranking"]["scores"] == {}
            assert fitted["ranking"]["scores_omitted"] == n                          # every name's copy is counted gone
        if "tickers" in fitted.get("audit_shed", []):
            assert fitted["tickers"] == [] and fitted["tickers_omitted"] == n


def test_a_pick_model_failure_never_stops_the_list_the_order_score_sets_the_order_and_the_row_says_why(nights, monkeypatch):
    """Review 2026-11-14 finding 4. WOULD FAIL IF the new code were unguarded inside the job: each of the pick
    model's own steps raising — the scoring, the cross-section percentiles, the long bar series, the long splits read —
    must still leave tonight's list WRITTEN (the order score and dollar volume need none of that code)."""
    def boom(*a, **k):
        raise RuntimeError("numpy changed")
    # (1) the scoring raises -> no pick score, the order score sets the order, said in the audit row
    monkeypatch.setattr(bl, "pick_scores", boom)
    f, out, rows = _job(monkeypatch)
    rk = out["ranking"]
    assert rows and out["error"] is None and out["written"] == len(rows)
    assert rk["ranked_by"] == "order_score" and rk["selected"] == "pick_model" and "scored no name" in rk["fallback"]
    assert "numpy changed" in rk["pick_error"] and all(r["pick_score"] is None and r["list_rank"] == r["rank_order_score"] for r in rows)
    assert all(r["dollar_vol20"] is not None for r in rows) and rk["scored"]["dollar_volume"] == len(rows)
    monkeypatch.undo()
    # (2) the cross-section's percentile step raises -> rs_best (the gates) still computed, the list written
    #     (`cb.cross_section_one_date` makes the first 3 `percentile_ranks` calls itself — the old path; the pick
    #     model's own 3 come after)
    real = bl.cb.percentile_ranks
    seen = {"n": 0}

    def later_calls_fail(v):
        seen["n"] += 1
        if seen["n"] > 3:
            raise RuntimeError("numpy changed")
        return real(v)
    monkeypatch.setattr(bl.cb, "percentile_ranks", later_calls_fail)
    f, out, rows = _job(monkeypatch)
    assert seen["n"] == 4
    assert rows and out["error"] is None and out["ranking"]["ranked_by"] == "order_score" and out["ranking"]["fallback"]
    assert out["ranking"]["xs_error"] and rows[0]["pick_score"] is None      # never scored on neutral 0.5 strength ranks
    # ... and the dollar-volume backup is untouched by it (stored, ranked, and still selectable that night)
    assert rows[0]["dollar_vol20"] >= bv.MIN_DOLLAR_VOL and out["ranking"]["scored"]["dollar_volume"] == 1
    assert rows[0]["gates"]["pick_inputs"] == {}
    monkeypatch.undo()
    seen["n"] = 0
    monkeypatch.setattr(bl.cb, "percentile_ranks", later_calls_fail)
    f, out, rows = _job(monkeypatch, ranking_state="dollar_volume")
    assert out["ranking"]["ranked_by"] == "dollar_volume" and out["ranking"]["fallback"] is None and out["ranking"]["xs_error"]
    monkeypatch.undo()
    assert bl.cb.percentile_ranks is real
    # (3) the LONG series build raises (the second build_series call) -> the list written, the pick model still scores
    #     off the 200-session bars, and the audit row names the cause and counts the names
    n = {"calls": 0}
    real_bs = bl.build_series

    def second_fails(rows_, ci):
        n["calls"] += 1
        if n["calls"] == 2:
            raise MemoryError("long series")
        return real_bs(rows_, ci)
    monkeypatch.setattr(bl, "build_series", second_fails)
    f, out, rows = _job(monkeypatch)
    rk = out["ranking"]
    assert rows and out["error"] is None and "long series" in rk["long_error"]
    assert rk["ranked_by"] == "pick_model" and rows[0]["pick_score"] is not None
    assert rk["short_bar_facts_n"] >= len(rows) and rows[0]["ticker"] in rk["short_bar_facts"]
    monkeypatch.undo()
    # (4) the long-window splits read raises (the second get_unapplied_splits call; needs a market longer than 200
    #     sessions, so a fixture night) -> the list written, the cause named
    n["calls"] = 0
    from test_breakout_v1_list import Fakes
    night = nights[min(nights)]
    cal = night["cal"]
    bar_rows = [(t, cal[len(cal) - 1 + x[0]], x[3], x[1], x[2], x[3], x[4]) for t, recs in sorted(night["bars"].items()) for x in recs]
    f = Fakes(monkeypatch, cal=cal, rows=bar_rows, types={t: ("CS", None) for t in night["bars"]})
    real_sp = bl.get_unapplied_splits

    async def second_split_read_fails(*a, **k):
        n["calls"] += 1
        if n["calls"] == 2:
            raise RuntimeError("splits table")
        return await real_sp(*a, **k)
    monkeypatch.setattr(bl, "get_unapplied_splits", second_split_read_fails)
    out = asyncio.run(bl.run_breakout_v1_list(cal[-1]))
    assert n["calls"] == 2 and len(f.lists[cal[-1]]) > 50 and out["error"] is None
    assert "splits table" in out["ranking"]["long_error"] and out["ranking"]["ranked_by"] == "pick_model"


def _gate_stub(monkeypatch):
    """`evaluate_members` on one synthetic passing name without real gates: returns (member, pick-less gate result)."""
    g = {"ok": True, "failed": [], "level": 10.0, "vol_bar": 1e6, "adr20": 4.0, "close": 9.9, "gates": {}}
    monkeypatch.setattr(bl.bv, "v1_gates", lambda bars, D, rs_best, cidx: dict(g))
    monkeypatch.setattr(bl.bv, "order_inputs", lambda bars, D, adr: {"runup6m_adr": 5.0, "spread10_adr": 1.0})
    seen = {}

    def facts(h, l, c, D):
        seen["n"] = D + 1
        return (0.9, 7, 0)
    monkeypatch.setattr(bl.pm, "base_facts", facts)
    monkeypatch.setattr(bl.pm, "pick_inputs", lambda g_, oi, facts, xs: {"dist_52w": None if facts is None else facts[0]})
    return seen


class _Bars:
    def __init__(self, n):
        self.h = self.l = self.c = np.ones(n)

    def __len__(self):
        return len(self.c)


def test_a_name_dropped_from_the_long_series_reads_its_52_week_facts_off_the_short_bars_and_is_named(monkeypatch):
    """Review 2026-11-14 finding 5: one NULL / non-finite bar 201-300 sessions back drops the WHOLE ticker from the
    long series (`build_series`), and an unapplied split in that window is taken out of it too. WOULD FAIL IF such a
    name got no facts (it was unscored and ranked last, with no trace): it reads its facts off the 200-session bars
    the gates read and is named in `pick["short_fallback"]`. A name WITH long bars reads the long bars, and with no
    long series supplied at all nothing falls back (the old 'no long bars -> no facts')."""
    seen = _gate_stub(monkeypatch)
    short = _Bars(200)
    members = [{"ticker": "AAA", "security_type": "CS", "listable": True, "history": True, "bars": short, "cidx": None}]
    pick = {"xs": {}, "long": {"ZZZ": _Bars(300)}, "extra": []}                    # a long series WITHOUT AAA
    rows, _f, _n = bl.evaluate_members(members, [90.0], date(2026, 11, 16), {}, pick)
    assert rows[0]["pick_inputs"]["dist_52w"] == 0.9 and seen["n"] == 200 and pick["short_fallback"] == ["AAA"]
    pick = {"xs": {}, "long": {"AAA": _Bars(300)}, "extra": []}                    # the long bars exist: they are read
    rows, _f, _n = bl.evaluate_members(members, [90.0], date(2026, 11, 16), {}, pick)
    assert seen["n"] == 300 and "short_fallback" not in pick
    pick = {"xs": {}, "extra": []}                                                 # no long series at all: no fallback
    rows, _f, _n = bl.evaluate_members(members, [90.0], date(2026, 11, 16), {}, pick)
    assert rows[0]["pick_inputs"]["dist_52w"] is None and "short_fallback" not in pick


def test_the_job_scores_a_name_whose_older_bars_carry_one_bad_bar_and_the_audit_row_names_it(nights, monkeypatch):
    """Finding 5 end to end, on a fixture night through the whole job: one listed name gets a NULL close 250 sessions
    back. Its 200-session series is clean, so it is listed exactly as before; the long series drops it — it must STILL
    get a pick score (it had none and ranked last), every other name's row is unchanged, and the audit row names it."""
    from test_breakout_v1_list import Fakes
    ci = min(nights)
    night = nights[ci]
    cal = night["cal"]
    bar_rows = [(t, cal[len(cal) - 1 + x[0]], x[3], x[1], x[2], x[3], x[4]) for t, recs in sorted(night["bars"].items()) for x in recs]
    types = {t: ("CS", None) for t in night["bars"]}

    def run(rows_):
        f = Fakes(monkeypatch, cal=cal, rows=rows_, types=types)
        out = asyncio.run(bl.run_breakout_v1_list(cal[-1]))
        return out, {r["ticker"]: r for r in f.lists[cal[-1]]}
    out0, base = run(bar_rows)
    assert out0["ranking"]["short_bar_facts_n"] == 0 and out0["ranking"]["long_error"] is None
    bad_day = cal[-250]
    victim = next(t for t in sorted(base, key=lambda t: base[t]["list_rank"])
                  if sum(1 for x in night["bars"][t]) >= 290 and base[t]["gates"]["pick_inputs"]["since_low"] < 150)
    hurt = [(r[0], r[1], r[2], r[3], r[4], None, r[6]) if (r[0] == victim and r[1] == bad_day) else r for r in bar_rows]
    assert hurt != bar_rows
    out1, got = run(hurt)
    assert set(got) == set(base) and got[victim]["pick_score"] is not None
    assert got[victim]["gates"]["pick_inputs"]["dist_52w"] is not None
    assert got[victim]["rank_pick_model"] < len(got)                                  # scored: not parked last
    rk = out1["ranking"]
    assert rk["short_bar_facts"] == [victim] and rk["short_bar_facts_n"] == 1 and rk["long_error"] is None
    assert rk["ranked_by"] == "pick_model" and rk["listed_with_52w_facts"] == out0["ranking"]["listed_with_52w_facts"]
    old_cols = ("level", "vol_bar", "adr20", "rs_best", "close", "order_score", "rank_order_score", "dollar_vol20")
    assert all({k: got[t][k] for k in old_cols} == {k: base[t][k] for k in old_cols} for t in base)


# ── review 2026-11-14 (the fix round's own review) ──────────────────────────────────────────────────────────────────
def test_unscored_names_follow_the_order_score_not_the_alphabet():
    """1 of 4 names scored: the rest must keep the order score's order behind it, never A-Z (a partial pick failure)."""
    rows = [_row("AAA", runup=10.0, since_low=None), _row("ZZZ", runup=40.0, since_low=None),
            _row("MMM", runup=20.0, since_low=None), _row("BBB", runup=5.0)]
    bl.rank_all(rows, [], "pick_model")
    assert [r["ticker"] for r in rows] == ["BBB", "ZZZ", "MMM", "AAA"]


def test_an_industry_group_failure_does_not_stop_the_list(monkeypatch):
    """The group step feeds only the pick model: it raising must still return rs_best (the gates) and no pick inputs."""
    pool = [{"ticker": f"T{k}", "r21": 0.01 * k, "r63": 0.02 * k, "r126": 0.03 * k} for k in range(30)]
    real = bl.cb.cross_section_one_date

    def groups_break(r21, r63, r126, groups):
        if any(g is not None for g in groups):
            raise RuntimeError("group median failed")
        return real(r21, r63, r126, groups)
    monkeypatch.setattr(bl.cb, "cross_section_one_date", groups_break)
    rs_best, xs, _ = bl.night_cross_section(pool, ["28"] * 30)
    assert xs is None and rs_best == real([p["r21"] for p in pool], [p["r63"] for p in pool],
                                          [p["r126"] for p in pool], [None] * 30)[0]


def test_the_execution_copy_of_the_ranking_table_matches_the_list_module():
    """breakout_v1_entry keeps literals (execution imports no list code); a renamed or added ranking must update both."""
    from agents.market_intelligence.broker import breakout_v1_entry as be
    assert {k: v[0] for k, v in be.RANKED_BY_SCORE.items()} == dict(bl.RANKING_SCORE_COL)


def test_a_degraded_ranking_night_has_one_plain_alert_and_a_normal_night_none():
    from datetime import date
    d = date(2026, 11, 16)
    assert bl.ranking_alert_message(d, {"selected": "pick_model", "fallback": None}) is None
    m = bl.ranking_alert_message(d, {"selected": "pick_model", "fallback": "x", "pick_error": "ValueError: nan"})
    assert "scored no stock" in m and "order score" in m and "ValueError" in m and "2026-11-16" in m
    assert "1-year price history" in bl.ranking_alert_message(d, {"long_error": "Timeout"})


def test_the_job_sends_the_alert_when_the_pick_model_falls_back(monkeypatch):
    monkeypatch.setattr(bl, "pick_scores", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("numpy changed")))
    f, out, rows = _job(monkeypatch)
    assert out["ranking"]["fallback"] and out["ranking_alert"] == "sent"
    assert any("ranking degraded" in m and "numpy changed" in m for m in f.sent)


def test_a_normal_night_sends_no_ranking_alert(monkeypatch):
    f, out, rows = _job(monkeypatch)
    assert "ranking_alert" not in out and not any("ranking degraded" in m for m in f.sent)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Grades (his approval 2026-11-15): A+/A/B/C from the pick score, frozen cutoffs; a label, orders nothing
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_grade_cutoffs_are_the_frozen_numbers_and_the_boundaries_are_inclusive():
    assert bl.GRADE_CUTOFFS == (("A+", -3.4942), ("A", -4.1845), ("B", -4.8715))
    eps = 1e-9
    for g, cut, below in (("A+", -3.4942, "A"), ("A", -4.1845, "B"), ("B", -4.8715, "C")):
        assert bl.grade_for(cut) == g                      # exactly on the cutoff takes the grade
        assert bl.grade_for(cut - eps) == below            # just under falls to the next
    assert bl.grade_for(0.0) == "A+" and bl.grade_for(-11.0) == "C"
    assert bl.grade_for(None) is None


def test_the_job_stamps_a_grade_on_every_row_and_the_audit_counts_sum_to_the_list(monkeypatch):
    from agents.market_intelligence import db
    f, out, rows = _job(monkeypatch)
    assert "grade" in db.BV1_LIST_COLS and "grade" not in db.BV1_LIST_SELECT_SQL
    assert all(r["grade"] == bl.grade_for(r["pick_score"]) for r in rows)
    g = out["ranking"]["grades"]
    assert sum(g.values()) == len(rows) and set(g) == {"A+", "A", "B", "C", "none"}
    assert g["none"] == sum(1 for r in rows if r["pick_score"] is None)


def test_the_message_shows_each_names_grade_and_a_dash_when_there_is_none():
    rows = _three_names()
    bl.rank_all(rows, [], "pick_model")
    rows[0]["grade"], rows[1]["grade"], rows[2]["grade"] = "A+", "B", None
    body = bl.format_list_message(date(2026, 11, 16), rows).split("```")[1].strip().splitlines()
    assert "GR" in body[0].split()
    assert [ln.split()[4] for ln in body[1:]] == ["A+", "B", "-"]
