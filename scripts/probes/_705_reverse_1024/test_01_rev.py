#!/usr/bin/env python3
"""Tests for 01_rev.py — synthetic fixtures for every stage's mechanics and every guard. No real outcome is used: every bar, minute, frame and
caption here is made up. Run: python3 -m pytest scripts/probes/_705_reverse_1024/test_01_rev.py -q"""
import importlib.util
import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("rev01", os.path.join(HERE, "01_rev.py"))
rev = importlib.util.module_from_spec(spec)
sys.modules["rev01"] = rev
spec.loader.exec_module(rev)
cb, rp = rev.cb, rev.rp


# ═════════════════════════════════════════════════════════════════════════════════════════════ fixtures
def sessions(n: int, start: str = "2020-01-02") -> list:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def daily(n: int = 300, base: float = 50.0, seed: int = 1, start: str = "2019-01-02", trend: float = 0.0005):
    rng = np.random.default_rng(seed)
    r = rng.normal(trend, 0.02, n)
    c = base * np.cumprod(1 + r)
    o = c * (1 + rng.normal(0, 0.005, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.01, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.01, n)))
    v = np.full(n, 2_000_000.0)
    dates = sessions(n, start)
    return cb.daily_bars_from_arrays(dates, o, h, l, c, v), np.arange(n, dtype=np.int32)


def minutes(path, start_minute: int = 0):
    """path = list of (o, h, l, c) per minute from `start_minute`."""
    m = list(range(start_minute, start_minute + len(path)))
    o, h, l, c = (list(x) for x in zip(*path))
    return cb.minute_bars_from_lists(m, o, h, l, c, [1000.0] * len(m))


def mk_buy(**kw) -> "rev.Buy":
    base = dict(eid=1, sym="AAA", sym_a="AAA", has_bars=True, ever_candidate=True, setup="undated", E="2020-03-02", D="2020-02-28", era="A", ticker="AAA",
                pivot=None, adr20=None, base_id="", retrigger=0, undated_reason="no_event_in_window", first_frame="f1", prev_full_frame="f0", lo="2020-03-02",
                hi="2020-03-02", window_len=1, inverted=False, initial=False, flicker=False, exit_lo="2020-03-05", exit_hi="2020-03-05", still_held=False, decides=False)
    base.update(kw)
    b = rev.Buy(**base)
    b.dated = b.setup in ("breakout", "EP", "both")
    b.noev = b.setup == "undated" and b.undated_reason == "no_event_in_window"
    b.year = int(b.E[:4])
    return b


def mk_rec(bars, cidx, e: int, b=None, mb=None, fill=None, fill_minute=None, stop=None, adr20=0.04):
    b = b or mk_buy(E=bars.dates[e].isoformat(), lo=bars.dates[e].isoformat(), hi=bars.dates[e].isoformat())
    r = rev.Rec(b=b, bars=bars, cidx=cidx, e=e, adr20=adr20, mb=mb, minutes_state="ok" if mb is not None else "missing")
    r.qqq_c = np.asarray(bars.c, dtype=float) * 3.0
    r.fill, r.fill_minute, r.stop = fill, fill_minute, stop
    return r


def smas_of_rec(r):
    return {10: rev.sma_series(r.bars, 10), 20: rev.sma_series(r.bars, 20), 50: rev.sma_series(r.bars, 50)}


# ═════════════════════════════════════════════════════════════════════════════════════════════ guards and parsing
def test_forbidden_dirs_not_in_files():
    for p in rev.FILES.values():
        assert not any(p.startswith(d) for d in rev.FORBIDDEN_DIRS)


def test_bar_guard_is_per_record_membership_not_a_date():
    """H1: the guard bounds each record by ITS OWN horizon — unbounded inside the stage's fit set (a dated 2021 trade in the EXIT fit), the buy
    day only outside it; an undated check-window buy is refused whatever the set says; the check (None) reads everything."""
    d21 = mk_buy(eid=9, setup="breakout", E="2021-02-01", lo="2021-02-01", hi="2021-02-01", decides=True)
    u21 = mk_buy(eid=10, E="2021-02-01", lo="2021-02-01", hi="2021-02-01")
    u20 = mk_buy(eid=11, E="2020-06-01", lo="2020-06-01", hi="2020-06-01")
    g = rev.BarGuard({9, 11})
    assert g.horizon(d21) is None and g.horizon(u20) is None and g.horizon(u21) == 0
    g.forward(d21, 5, "x")                                     # the old DATE guard (limit 2020-12-31) raised here: the exit fit stopped on its first dated 2021 trade
    g.forward(u20, 120, "x")
    with pytest.raises(rev.GuardStop):
        g.forward(u21, 1, "x")
    with pytest.raises(rev.GuardStop):
        rev.BarGuard({10}).forward(u21, 1, "x")                # the belt: an undated 2021-22 buy is never fit material, even when listed
    with pytest.raises(rev.GuardStop):
        rev.BarGuard(set()).forward(u20, 1, "x")               # outside the fit set: the buy day only
    rev.BarGuard(set()).forward(u20, 0, "x")
    rev.BarGuard(None).forward(u21, 50, "x")                   # the check


def test_marker_and_chosen_lines(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("# title\nprose with `CHOSEN ENTER: …`, `CHOSEN STOP: …` inline mention\n- **CHOSEN SELECT:** F1>=0.1 & F8>=0.2\nCHOSEN ENTER: L2\n"
                   "CHOSEN STOP: S3-T\nCHOSEN EXIT: list: X3 ; X7>=2\nthe freeze marker <!-- FREEZE --> mentioned inline\n<!-- FREEZE -->\n## Freeze record\n- doc_body: abc\n")
    ch = rev.chosen_lines(str(doc))
    assert ch == {"select": ["F1>=0.1 & F8>=0.2"], "enter": ["L2"], "stop": ["S3-T"], "exit": ["list: X3 ; X7>=2"]}
    raw = doc.read_bytes()
    assert len(rev.marker_spans(raw)) == 1
    body_sha = rev.doc_body_sha(str(doc))
    doc.write_text(doc.read_text() + "\n- more pins under the marker\n")
    assert rev.doc_body_sha(str(doc)) == body_sha            # text below the marker never changes the body hash
    doc.write_text(doc.read_text().replace("CHOSEN ENTER: L2", "CHOSEN ENTER: L3"))
    assert rev.doc_body_sha(str(doc)) != body_sha            # an edit above it does
    two = tmp_path / "two.md"
    two.write_text("a\n<!-- FREEZE -->\nb\n<!-- FREEZE -->\n")
    assert rev.chosen_lines(str(two)) == {}
    assert rev.freeze_missing(str(two), {"x": "1"}) == ["x"]


def test_ledger_catches_a_changed_printout(tmp_path, monkeypatch):
    monkeypatch.setattr(rev, "LEDGER", str(tmp_path / "ledger.tsv"))
    p = tmp_path / "out.txt"
    p.write_text("one\n")
    rev.ledger_append("select-fit", str(p))
    assert rev.ledger_verify() == []
    p.write_text("two\n")
    assert any("changed" in x for x in rev.ledger_verify())
    p.unlink()
    assert any("missing" in x for x in rev.ledger_verify())


def test_stage_outputs_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(rev, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(rev, "STOPPED", str(tmp_path / "S.txt"))
    monkeypatch.setattr(rev, "P_CHECK", str(tmp_path / "check.txt"))
    monkeypatch.setattr(rev, "P_FIT", {s: str(tmp_path / f"{s}.txt") for s in rev.STAGES})
    (tmp_path / "dryrun_clocks.tsv").write_text("x")
    assert rev.stage_outputs("select") == [] and rev.any_stage_output() == []
    (tmp_path / "select_fit_buys.tsv").write_text("x")
    assert rev.stage_outputs("select") and rev.stage_outputs("enter") == []
    assert rev.any_stage_output()


def test_binom_ci_matches_the_doc():
    p, hw = rev.binom_ci(32, 64)
    assert p == 0.5 and round(100 * hw) == 12
    assert round(100 * rev.binom_ci(22, 44)[1]) == 15


# ═════════════════════════════════════════════════════════════════════════════════════════════ the population layer
def test_clock_derivation_in_session_vs_pre_market():
    sn = pd.DataFrame([dict(frame_id="f0", date="2020-03-02", ctx="in", clock="10:05"), dict(frame_id="f1", date="2020-03-02", ctx="in", clock="10:40"),
                       dict(frame_id="p0", date="2020-03-02", ctx="pre", clock="07:30"), dict(frame_id="c0", date="2020-03-01", ctx="closed", clock="17:00"),
                       dict(frame_id="e0", date="2020-03-02", ctx="in", clock="09:33")])
    b = mk_buy(first_frame="f1", prev_full_frame="f0")
    rev.derive_clocks([b], sn)
    assert (b.first_clock, b.flat_clock, b.in_bracket, b.pre_flat_bracket) == ("10:40", "10:05", True, False)
    assert rev.bracket_width(b) == 35
    b2 = mk_buy(first_frame="f1", prev_full_frame="p0")
    rev.derive_clocks([b2], sn)
    assert (b2.flat_clock, b2.in_bracket, b2.pre_flat_bracket) == ("07:30", False, True)
    b3 = mk_buy(first_frame="f1", prev_full_frame="c0")      # the flat frame on another day: no flat clock
    rev.derive_clocks([b3], sn)
    assert b3.flat_clock == "" and not b3.in_bracket
    b4 = mk_buy(first_frame="e0", prev_full_frame="p0")
    rev.derive_clocks([b4], sn)
    assert b4.held_before_0935
    b5 = mk_buy(first_frame="f1", prev_full_frame="f0", initial=True)
    rev.derive_clocks([b5], sn)
    assert b5.first_clock == ""


def test_clock_misreads():
    sn = pd.DataFrame([dict(frame_id=f"g{i}", vid="v", date="2019-10-01", et_time=t, stream_ts=str(s)) for i, (t, s) in enumerate(
        [("2019-10-01T10:00-04:00", 1000), ("2019-10-01T10:10-04:00", 1600), ("2019-10-01T10:20-04:00", 2200), ("2019-10-01T13:00-04:00", 2800), ("", 3000)])])
    mis = rev.clock_misreads(sn)
    assert set(mis) == {"g3"} and mis["g3"][0] == "2019-10-01"


def test_type_gate():
    small = {"SPY": ("ETF", "ARCX"), "AAPL": ("CS", "XNAS"), "LAZR": ("ETF", "ARCX")}
    sic = {"TSM": ("3674", "SEMI", "ADRC", "2026-10-16"), "XYZ": ("", "", "", "")}
    assert rev.type_of("SPY", small, sic) == ("ETF", "mi", False)
    assert rev.type_of("AAPL", small, sic) == ("CS", "mi", True)
    assert rev.type_of("TSM", small, sic) == ("ADRC", "sic", True)
    assert rev.type_of("NOPE", small, sic) == ("", "none", True)             # no type row: admitted (the U rule as it stands), flagged
    assert rev.type_of("LAZR", small, sic) == ("CS", "override", True)


def test_gate_steps_order_and_counts():
    bs = [mk_buy(eid=i) for i in range(6)]
    bs[0].type_ok = False; bs[0].inverted = True                 # removed by the type gate (counted once, there)
    bs[1].inverted = True
    bs[2].same_day_rebuy = True
    bs[3].inverted = True; bs[3].same_day_rebuy = True           # inverted removes it before the same-day step sees it
    used, n_t, n_i, n_s, t_out = rev.gate_steps(bs)
    assert (n_t, n_i, n_s, len(used)) == (1, 2, 1, 2) and [b.eid for b in used] == [4, 5]


def test_rebuy_definition():
    a = mk_buy(eid=1, sym="X", lo="2020-02-03", exit_hi="2020-02-10")
    b = mk_buy(eid=2, sym="X", lo="2020-02-24", exit_hi="2020-03-01")       # 14 days after -> re-buy
    c = mk_buy(eid=3, sym="X", lo="2020-03-20", exit_hi="2020-03-25")       # 19 days -> not
    d = mk_buy(eid=4, sym="Y", lo="2020-03-20", exit_hi="")
    i0 = mk_buy(eid=0, sym="Y", lo="2020-03-10", exit_hi="2020-03-18", initial=True)
    assert rev.mark_rebuys([a, b, c, d, i0]) == 1
    assert b.rebuy and not a.rebuy and not c.rebuy and not d.rebuy          # the previous entry of Y is INITIAL: no re-buy


def test_events_outside_priority():
    cal = [d.isoformat() for d in sessions(60, "2020-01-02")]
    CI = {d: i for i, d in enumerate(cal)}
    EV = {"tl": {("A", "P"): {cal[22]}, ("A", "Q"): {cal[12]}, ("A", "S"): {cal[32]}}, "other": {("A", "Q"): {cal[20]}}, "ep": {}}
    mk = lambda eid, sym: mk_buy(eid=eid, sym=sym, sym_a=sym, E=cal[20], lo=cal[20], hi=cal[20])   # noqa: E731
    bs = [mk(1, "P"), mk(2, "Q"), mk(3, "S"), mk(4, "T")]
    rev.index_calendar(bs, cal)
    c = rev.classify_events_outside(bs, EV, CI)
    assert bs[0].event_class == "after_1_5" and bs[0].fwd_event_1_5
    assert bs[1].event_class == "other_level" and bs[1].other_level_inside     # the other level inside the window outranks the 6-20 before
    assert bs[2].event_class == "none"                                          # 12 sessions AFTER is beyond 5: none
    assert bs[3].event_class == "none" and c["none"] == 2
    with pytest.raises(rev.GuardStop):
        rev.classify_events_outside([mk(5, "P")], {"tl": {("A", "P"): {cal[20]}}, "other": {}, "ep": {}}, CI)


def test_dated_paths():
    cal = [d.isoformat() for d in sessions(200, "2020-01-02")]
    d = mk_buy(eid=1, sym="X", setup="breakout", E=cal[10], lo=cal[10], hi=cal[10], decides=True)
    u1 = mk_buy(eid=2, sym="X", E=cal[100], lo=cal[100], hi=cal[100])
    u2 = mk_buy(eid=3, sym="X", E=cal[140], lo=cal[140], hi=cal[140])
    u3 = mk_buy(eid=4, sym="Y", E=cal[100], lo=cal[100], hi=cal[100])
    rev.index_calendar([d, u1, u2, u3], cal)
    rev.mark_dated_paths([u1, u2, u3], [d])
    assert u1.in_dated_path and not u2.in_dated_path and not u3.in_dated_path


# ═════════════════════════════════════════════════════════════════════════════════════════════ SELECT
def test_pool_floor_is_split_invariant():
    """H2: the $10M test reads the export's close x the export's volume (one adjusted basis); the raw close serves the $5 test only. Scaling the
    raw close (a later split) must not move the dollar-volume verdict."""
    bars, cidx = daily(200, base=20.0)
    raw = np.asarray(bars.c) * 1.0
    bars2 = cb.daily_bars_from_arrays(bars.dates, bars.o, bars.h, bars.l, bars.c, np.full(200, 100.0))
    holed = cidx.copy(); holed[140:] += 1
    # the ONE floor (the fit's and the dry run's path, M7); re-check N6: the second copy `pool_floor_for` is deleted
    assert not hasattr(rev, "pool_floor_for")
    T = rev.ticker_feature_table(bars, cidx, raw, {})
    assert rev.floor_reason_from_table(T, 150) == ""
    assert rev.floor_reason_from_table(rev.ticker_feature_table(bars, cidx, raw * 0.1, {}), 150) == "raw_close_lt_5"
    assert rev.floor_reason_from_table(rev.ticker_feature_table(bars, cidx, raw * 15.0, {}), 150) == ""
    assert rev.floor_reason_from_table(rev.ticker_feature_table(bars2, cidx, raw, {}), 150) == "dollar_vol_lt_10M"
    assert rev.floor_reason_from_table(rev.ticker_feature_table(bars2, cidx, raw * 1000.0, {}), 150) == "dollar_vol_lt_10M"   # the raw close never enters the $10M test
    assert rev.floor_reason_from_table(rev.ticker_feature_table(bars, holed, raw, {}), 150) == "history_lt_130"              # a hole inside the 130 sessions
    assert rev.floor_reason_from_table(T, 100) == "history_lt_130"
    assert rev.floor_reason_from_table(rev.ticker_feature_table(bars, holed, raw, {}), 139) == "no_bar_on_prior_session"   # bar 140 is not the next session
    assert rev.floor_reason_from_table(T, 199) == "no_bar_on_prior_session"                                              # no bar after the last one


def test_select_features_on_a_hand_series():
    n = 300
    c = np.full(n, 10.0); c[-1] = 11.0                       # the prior session closes at a 20- and 50-day high
    o, h, l = c.copy(), c + 0.2, c - 0.2
    h[-1], l[-1] = 11.5, 10.5
    v = np.full(n, 1e6); v[-1] = 3e6
    bars = cb.daily_bars_from_arrays(sessions(n), o, h, l, c, v)
    cidx = np.arange(n, dtype=np.int32)
    T = rev.ticker_feature_table(bars, cidx, None, {i: "up" for i in range(n)})
    p = n - 1
    adr = T["adr"][p]
    assert adr > 0 and T["F1"][p] > 0 and T["F2"][p] > 0          # above the max high of the 20 / 50 sessions before
    assert T["F3"][p] == 0                                        # the 252-session high is the prior session itself
    assert abs(T["F8"][p] - 0.1) < 1e-12 and abs(T["F9"][p] - 0.1) < 1e-12
    assert abs(T["F11"][p] - 3.0) < 1e-12                          # volume vs the 20 before it
    assert abs(T["F13"][p] - 0.5) < 1e-12                          # close mid-range
    assert T["F17"][p] == "up" and T["contig130"][p] and not T["next_is_bar"][p]
    assert np.isnan(T["F14"][p])                                   # no bar after the last one: F14 undefined
    assert abs(T["F14"][p - 1] - (o[p] - c[p - 1]) / (c[p - 1] * T["adr"][p - 1])) < 1e-12


def test_conj_search_counts_match_brute_force_and_set_choice():
    rng = np.random.default_rng(0)
    K, n_pool, n_buys = 7, 500, 40
    P = rng.random((K, n_pool)) < 0.5
    B = rng.random((K, n_buys)) < 0.5
    conds = [rev.Cond(f"F{i + 1}", ">=", 0.0) for i in range(K)]
    cs = rev.ConjSearch(conds, rev.pack_bits(P), n_pool)
    pc = cs.pool_counts()
    bc = cs.counts(rev.pack_bits(B))
    assert len(pc) == K + K * (K - 1) // 2 + K * (K - 1) * (K - 2) // 6
    for i in range(len(pc)):
        ids = [x for x in (cs.a[i], cs.b[i], cs.c[i]) if x >= 0]
        assert pc[i] == np.all(P[ids], axis=0).sum() and bc[i] == np.all(B[ids], axis=0).sum()
    # a planted condition: buys all satisfy F3, the pool rarely does -> chosen as a single
    P2 = rng.random((K, n_pool)) < 0.5
    P2[2] = rng.random(n_pool) < 0.1
    B2 = rng.random((K, n_buys)) < 0.5
    B2[2] = True
    cs2 = rev.ConjSearch(conds, rev.pack_bits(P2), n_pool)
    res = rev.choose_condition_set(cs2, cs2.pool_counts(), rev.pack_bits(B2), n_buys, cs2.P, cap=0.2, max_conj=1)
    assert res["texts"] == ["F3>=0"] and res["recall"] == 1.0 and res["pool_rate"] <= 0.2
    # the cap binds: with cap 0.05 nothing qualifies but a conjunction
    res2 = rev.choose_condition_set(cs2, cs2.pool_counts(), rev.pack_bits(B2), n_buys, cs2.P, cap=0.05, max_conj=1)
    pc2 = cs2.pool_counts() / n_pool
    assert (pc2 <= 0.05).any(), "the fixture must leave at least one conjunction under the cap"
    assert res2["ids"] and res2["pool_rate"] <= 0.05 and res2["recall"] == max(cs2.counts(rev.pack_bits(B2))[pc2 <= 0.05]) / n_buys
    assert all(cs2.size()[i] > 1 for i in res2["ids"]) or pc2[res2["ids"][0]] <= 0.05


def test_choose_condition_set_adds_a_second_conjunction_only_with_ten_points():
    rng = np.random.default_rng(3)
    K, n_pool, n_buys = 5, 400, 50
    P = rng.random((K, n_pool)) < 0.12
    B = np.zeros((K, n_buys), dtype=bool)
    B[0, :30] = True                      # conjunction A covers 60%
    B[1, 30:45] = True                    # B adds 30%
    B[2, 45:47] = True                    # C adds 4%: not kept
    conds = [rev.Cond(f"F{i + 1}", ">=", 0.0) for i in range(K)]
    cs = rev.ConjSearch(conds, rev.pack_bits(P), n_pool)
    res = rev.choose_condition_set(cs, cs.pool_counts(), rev.pack_bits(B), n_buys, cs.P, cap=0.3)
    assert res["texts"][:2] == ["F1>=0", "F2>=0"] and len(res["texts"]) == 2 and abs(res["recall"] - 0.9) < 1e-9
    assert res["pool_rate"] <= 0.3


def test_grid_and_set_matches_and_placement():
    pool = pd.DataFrame({k: np.linspace(-1, 1, 101) for k in rev.NUMERIC} | {"F17": ["up"] * 101})
    conds = rev.grid_from_pool(pool)
    assert len(conds) == 16 * 18 + 3
    conj = [rev.Cond("F1", ">=", 0.5), rev.Cond("F17", "==", "up")]
    m = rev.set_matches([conj], pool)
    assert m.sum() == 26
    assert rev.place_window([False, True, False, True, False]) == (3, False)
    assert rev.place_window([False, False]) == (0, True)


def test_ridge_logistic_and_percentile():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(400, 3))
    y = (X[:, 0] + 0.5 * X[:, 1] + rng.normal(0, 0.3, 400) > 0).astype(float)
    w, b, mu, sd = rev.ridge_logistic(X, y)
    assert w[0] > w[1] > 0 and abs(w[2]) < 0.5
    assert rev.pick_percentile(10.0, np.array([1.0, 2.0, 3.0])) == 0.0
    assert rev.pick_percentile(0.0, np.array([1.0, 2.0, 3.0])) == 0.75
    assert rev.short_cluster_flag(pd.DataFrame({"F8": [5.0], "F9": [0.0]}), pd.DataFrame({"F8": np.linspace(0, 1, 100), "F9": np.linspace(0, 1, 100)}))
    assert not rev.short_cluster_flag(pd.DataFrame({"F8": [0.5], "F9": [0.5]}), pd.DataFrame({"F8": np.linspace(0, 1, 100), "F9": np.linspace(0, 1, 100)}))


# ═════════════════════════════════════════════════════════════════════════════════════════════ ENTER
def enter_fixture():
    bars, cidx = daily(200, base=50.0, seed=5)
    e = 180
    # a synthetic buy day: open 50, drifts up through 52 at minute 40, 54 at minute 70; prior high 51.5, prior close 50.5
    bars.o[e], bars.c[e - 1], bars.h[e - 1] = 50.0, 50.5, 51.5
    bars.l[e - 1] = 49.0
    path = []
    px = 50.0
    for m in range(0, 120):
        px = 50.0 + 0.05 * m
        path.append((px, px + 0.03, px - 0.03, px + 0.01))
    mb = minutes(path)
    bars.h[e], bars.l[e] = max(x[1] for x in path), min(x[2] for x in path)
    b = mk_buy(E=bars.dates[e].isoformat(), lo=bars.dates[e].isoformat(), hi=bars.dates[e].isoformat(), first_clock="10:40", flat_clock="10:00")
    b.first_clock, b.flat_clock, b.p_ctx, b.in_bracket = "10:40", "10:00", "in", True       # bracket minutes (30, 70]
    return mk_rec(bars, cidx, e, b=b, mb=mb)


def test_enter_levels_and_feasibility():
    r = enter_fixture()
    L = rev.enter_levels(r)
    assert L["L2"] == 51.5 and L["L5"] == 50.5 and L["L4"] == 50.0 and L["L6"] == pytest.approx(50.0 + 0.05 * 59 + 0.03)
    assert L["L1"] == pytest.approx(50.0 + 0.05 * 4 + 0.03)                   # undated: the opening-range high alone
    flat_m, first_m = rev.bracket_minutes(r.b)
    assert (flat_m, first_m) == (30, 70)
    s2 = rev.score_level(r.mb, L["L2"], flat_m, first_m, r.adr20)             # 51.5 crossed at minute 30 (high 51.53 > 51.5)? minute 30 high = 51.53 -> crossed AT the flat minute: not feasible
    assert s2["cross"] == 30 and not s2["feasible"]
    s = rev.score_level(r.mb, 52.0, flat_m, first_m, r.adr20)
    assert s["feasible"] and s["cross"] == 40 and s["verdict"] == "HIT"
    s4 = rev.score_level(r.mb, L["L4"], flat_m, first_m, r.adr20)
    assert s4["cross"] == 0 and not s4["feasible"]                             # L4 never feasible on an in-session bracket
    s5 = rev.score_level(r.mb, L["L5"], flat_m, first_m, r.adr20)
    assert not s5["feasible"]                                                  # the prior close was crossed at the open: not his trigger
    s6 = rev.score_level(r.mb, L["L6"], flat_m, first_m, r.adr20)
    assert s6["cross"] is None or s6["cross"] >= 60
    lo, hi = s["range"]
    tol = rev.BALLPARK_ADR * r.adr20
    bp = rev.score_level(r.mb, hi * (1 + tol * 0.5), flat_m, first_m, r.adr20)
    assert bp["verdict"] == "BALLPARK" and not bp["feasible"]
    miss = rev.score_level(r.mb, hi * (1 + tol * 3), flat_m, first_m, r.adr20)
    assert miss["verdict"] == "MISS"
    # a pre-market flat frame (flat_m negative): L4 and L5 pass by construction -> why those brackets are beside
    s4p = rev.score_level(r.mb, L["L4"], -120, first_m, r.adr20)
    assert s4p["feasible"]


def test_random_level_control_is_seeded_and_from_the_session():
    r = enter_fixture()
    a = rev.random_levels(r.mb, 50, rev.rng_for("rev|minute"))
    b = rev.random_levels(r.mb, 50, rev.rng_for("rev|minute"))
    assert np.array_equal(a, b) and set(np.round(a, 6)) <= set(np.round(np.concatenate((r.mb.c, [r.mb.o[0]])), 6))
    res = rev.enter_score_trade(r, rev.rng_for("rev|minute"))
    assert 0.0 <= res["control"]["feasible_share"] <= 1.0 and set(res) >= set(rev.LEVELS)


def test_enter_summary_choice_and_verdict():
    r = enter_fixture()
    scored = {k: rev.enter_score_trade(r, rev.rng_for("x")) for k in range(3)}
    summ = rev.enter_summary(scored)
    assert summ["n"] == 3 and rev.choose_level(summ) in rev.LEVELS
    # synthetic summaries for the verdict
    def S(n, feas, hit, cf=0.3, chh=0.4):
        d = {"n": n, "control": {"feasible_share": cf, "hit_share": chh}}
        for L in rev.LEVELS:
            d[L] = dict(feasible=0, hit=0, feasible_share=(0.1, 0.1), hit_share=(0.1, 0.1), verdicts={})
        d["L2"] = dict(feasible=int(feas * n), hit=int(hit * n), feasible_share=(feas, 0.1), hit_share=(hit, 0.1), verdicts={})
        return d
    assert rev.enter_verdict(S(64, 0.6, 0.8), "L2")[0] == "PASS"
    assert rev.enter_verdict(S(24, 0.6, 0.8), "L2")[0] == "INCONCLUSIVE"       # fewer than 40 scorable
    assert rev.enter_verdict(S(64, 0.3, 0.8), "L2")[0] == "FAIL"               # no level >= 50% feasible
    assert rev.enter_verdict(S(64, 0.6, 0.5), "L2")[0] == "INCONCLUSIVE"       # hit-or-ballpark below 70


def test_chain_fill_uses_the_level_where_feasible_else_the_registered_fill():
    r = enter_fixture()
    r.levels = rev.enter_levels(r)
    r.levels["L2"] = 52.0
    rev.chain_fill(r, "L2")
    assert r.fill == 52.0 and r.fill_minute == 40 and r.fill_src == "level:L2" and not r.fill_fallback
    rev.chain_fill(r, "L4")
    assert r.fill_src == "open" and r.fill_fallback and r.fill_minute == 0
    rev.chain_fill(r, None)
    assert r.fill_src == "open" and not r.fill_fallback


# ═════════════════════════════════════════════════════════════════════════════════════════════ STOP
def stop_fixture(exit_lo_j=3, exit_hi_j=5):
    bars, cidx = daily(200, base=50.0, seed=7)
    e = 150
    c = np.asarray(bars.c); o = np.asarray(bars.o); h = np.asarray(bars.h); l = np.asarray(bars.l)
    for j in range(0, 8):                                   # a flat path after the buy day: close 50, low 49
        o[e + j], c[e + j], h[e + j], l[e + j] = 50.0, 50.0, 50.6, 49.0
    l[e + 2] = 47.0                                          # session 2 touches 47 (he held with certainty: before exit_lo)
    c[e + 4] = 48.0                                          # session 4 closes at 48 (inside the window: not evidence)
    c[e - 1], l[e - 1] = 49.8, 48.5
    bars = cb.daily_bars_from_arrays(bars.dates, o, h, l, c, bars.v)
    dates = [d.isoformat() for d in bars.dates]
    b = mk_buy(E=dates[e], lo=dates[e], hi=dates[e], exit_lo=dates[e + exit_lo_j], exit_hi=dates[e + exit_hi_j])
    b.Ei, b.lo_i, b.hi_i, b.exit_lo_i, b.exit_hi_i = e, e, e, e + exit_lo_j, e + exit_hi_j
    mb = minutes([(50.0, 50.2, 49.9, 50.1)] * 5 + [(50.1, 50.3, 48.2, 50.0)] + [(50.0, 50.2, 49.9, 50.0)] * 300)   # minute 5 dips to 48.2
    r = mk_rec(bars, cidx, e, b=b, mb=mb, fill=50.0, fill_minute=2, stop=49.0)
    r.stop_levels = {"S1": 49.9, "S2": 49.0, "S3": 48.5, "S4": 50.0 * 0.96, "S5": 51.0, "S6": 47.5, "S7": ("sma", 10), "S8": 50.0 * 0.92, "SMA50": ("sma", 50), "S1_is_S2": False}
    return r


def test_held_through_certainty_rules():
    r = stop_fixture()
    smas = smas_of_rec(r)
    sight = rev.Sightings({})
    # S6 = 47.5: touched on session 2 (< exit_lo = 3) -> certain
    h = rev.held_through(r, "S6", "T", smas, sight)
    assert h["any"] and h["certain"] and h["first_j"] == 2
    # a close below 48.5 happens on session 4 (inside the window) -> traded through, not certain
    h2 = rev.held_through(r, "S3", "C", smas, sight)
    assert h2["any"] and not h2["certain"] and h2["first_j"] == 4
    # S2-T from session 1: the day-0 low is the level by definition; session 2's 47 < 49 -> certain
    h3 = rev.held_through(r, "S2", "T", smas, sight)
    assert h3["any"] and h3["certain"] and h3["first_j"] == 1        # from session 1 (the flat path's low 49 touches it there); day 0 never counts for S2
    # day-0 touch after the fill (minute 5 low 48.2 <= 48.3) with exit_lo later -> certain (he held to exit_lo)
    h4 = rev.held_through(r, 48.3, "T", smas, sight)
    assert h4["first_j"] == 0 and h4["certain"]
    # a same-day exit window (exit_lo = 0): the day-0 touch needs a frame after the touch minute showing him holding
    r0 = stop_fixture(exit_lo_j=0, exit_hi_j=0)
    s_none = rev.Sightings({})
    h5 = rev.held_through(r0, 48.3, "T", smas_of_rec(r0), s_none)
    assert h5["any"] and not h5["certain"]
    s_after = rev.Sightings({(r0.b.E, "AAA"): [(1, "in", "10:30")]})
    assert rev.held_through(r0, 48.3, "T", smas_of_rec(r0), s_after)["certain"]
    s_before = rev.Sightings({(r0.b.E, "AAA"): [(1, "in", "09:33")]})
    assert not rev.held_through(r0, 48.3, "T", smas_of_rec(r0), s_before)["certain"]
    # a close below on exit_lo counts only with a frame after 16:00 that day
    r1 = stop_fixture(exit_lo_j=4, exit_hi_j=5)
    assert not rev.held_through(r1, 48.5, "C", smas_of_rec(r1), rev.Sightings({}))["certain"]
    s_closed = rev.Sightings({(r1.b.exit_lo, "AAA"): [(9, "closed", "17:00")]})
    assert rev.held_through(r1, 48.5, "C", smas_of_rec(r1), s_closed)["certain"]
    # a touch after exit_hi is no evidence at all
    h6 = rev.held_through(r, 10.0, "T", smas, sight)
    assert not h6["any"]
    # the guard: a fit stage may not read a forward bar of a trade outside its fit set
    r.guard = rev.BarGuard(set())                          # the fixture's trade is in no fit set: its horizon is the buy day
    with pytest.raises(rev.GuardStop):
        rev.held_through(r, "S6", "T", smas, sight)
    r.guard = rev.BarGuard({r.b.eid})                      # inside the fit set: unbounded
    assert rev.held_through(r, "S6", "T", smas, sight)["certain"]
    r.guard = None


def test_stop_table_choice_and_verdict():
    recs = [stop_fixture() for _ in range(25)]
    smas_cache = {}
    tab = rev.stop_table(recs, lambda r: rev.smas_for(r, smas_cache), rev.Sightings({}))
    assert tab[("S6", "T")]["any"] == 25 and tab[("S6", "T")]["eligible"] and tab[("S6", "T")]["H_cond"] == 1.0
    assert tab[("S3", "C")]["H_cond"] == 0.0 and tab[("S3", "C")]["eligible"]
    chosen, per = rev.choose_stop(tab)
    # under C every level S1..S6 is closed through on session 4 only (inside the window: traded through, never certain -> H_cond 0, eligible); the
    # tightest of them is S1 (49.9 vs the 50 fill). The old assert `per['C'] == 'S3' and ... or chosen is not None` passed whatever this was (L8).
    assert per["C"] == "S1" and tab[("S1", "C")]["H_cond"] == 0.0 and tab[("S1", "C")]["tight"] == pytest.approx(0.002)
    assert per["T"] is None or per["T"] in rev.STOP_CHOOSABLE
    assert chosen == ("S1", "C") or (chosen is not None and chosen[1] == "T" and tab[chosen]["tight"] < 0.002)
    v, _ = rev.stop_verdict(tab, tab, chosen)
    assert v == "PASS"
    bad = {k: dict(v, H_cond=0.5) for k, v in tab.items()}
    assert rev.stop_verdict(tab, bad, chosen)[0] == "FAIL"
    assert rev.stop_verdict(tab, tab, None)[0] == "INCONCLUSIVE"
    # L1: S8 and the 50-day are controls — never chosen even when they look perfect; a level at or above the fill (width <= 0) is never chosen
    perfect = {k: dict(v, H_cond=0.0, eligible=True, tight=0.001) for k, v in tab.items()}
    perfect[("S8", "T")]["tight"] = 0.0001
    perfect[("SMA50", "T")]["tight"] = 0.00001
    ch2, per2 = rev.choose_stop(perfect)
    assert ch2[0] in rev.STOP_CHOOSABLE and ch2[0] not in rev.STOP_CONTROLS
    above = {k: dict(v, H_cond=0.0, eligible=True, tight=(-0.02 if k[0] == "S5" else 0.03)) for k, v in tab.items()}
    assert rev.choose_stop(above)[0][0] != "S5"
    # re-check N1 (option b, supersedes M2's combining rule): the undated check decides ALONE — the dated 2021-22 table cannot enter the verdict
    # (the EXIT fit walks those trades under the chosen stop before --check); the verdict takes no dated table at all
    import inspect
    assert list(inspect.signature(rev.stop_verdict).parameters) == ["fit_table", "chk_table", "chosen"]
    tabC = {k: dict(v) for k, v in tab.items()}
    tabC[("S4", "C")].update(H_cond=0.0, eligible=True, tight=0.04, any=25, certain=0)        # S4-C: UNREAD on dated 2021-22 by the exits study
    assert rev.stop_verdict(tabC, tabC, ("S4", "C"))[0] == "PASS"
    assert rev.stop_verdict(tabC, tabC, ("S3", "C"))[0] == "PASS"
    badS4 = {k: dict(v) for k, v in tabC.items()}
    badS4[("S4", "C")]["H_cond"] = 0.5
    assert rev.stop_verdict(tabC, badS4, ("S4", "C"))[0] != "PASS"                         # the undated check still blocks on its own


def test_stop_walk_variants():
    r = stop_fixture()
    smas = smas_of_rec(r)
    j, px, kind = rev.stop_walk(r, 48.0, "T", smas, 5)            # session 2's low 47 touches 48 -> exit at 48
    assert (j, px, kind) == (2, 48.0, "stop")
    j, px, kind = rev.stop_walk(r, 46.0, "T", smas, 5)            # never touched -> his exit at the close of 5
    assert (j, kind) == (5, "mark")
    j, px, kind = rev.stop_walk(r, 48.5, "C", smas, 5)            # session 4 closes 48 < 48.5 -> the next open
    assert (j, kind) == (5, "stop_close") and px == float(r.bars.o[r.e + 5])
    j, px, kind = rev.stop_walk(r, 48.3, "T", smas, 5)            # day-0 minute 5 low 48.2 -> day-0 stop
    assert (j, px, kind) == (0, 48.3, "day0_stop")


def test_make_simple_trade_and_simulate():
    r = stop_fixture()
    t = rev.make_simple_trade(r, 5, 52.0, "mark", 0.02, None, 10_000)
    assert t is not None and t.realized_r == pytest.approx((52.0 - 50.0) / (50.0 * 0.02))
    sim = rp.simulate([t], rev.CAP30, list(r.bars.dates), r.e)
    assert sim["final"] > 1.0 and sim["counts"]["entered"] == 1


# ═════════════════════════════════════════════════════════════════════════════════════════════ EXIT
def test_exit_features_and_rules():
    r = stop_fixture()
    smas = smas_of_rec(r)
    X = rev.exit_features(r, 5, smas)
    assert X.shape == (6, 10)
    assert X[2, 4] == 2 and X[4, 2] == 1.0                                     # X5 = sessions held; session 4 is a red close (48 < 50)
    assert X[4, 6] == pytest.approx((48.0 - 50.0) / 1.0)                      # X7 = R at the close (risk 1.0)
    assert X[2, 3] == 0.0 and X[4, 3] == 1.0                                   # X4: close below the prior low (48 < 49)
    assert rev.rule_fire_day(X, (("X3", "==", 1),)) == 4
    assert rev.rule_fire_day(X, (("X5", ">=", 3),)) == 3
    assert rev.rule_fire_day(X, (("X7", ">=", 3.0),)) == 10 ** 6
    rules = rev.all_rules()
    assert len(rules) == 17 + sum(1 for i in range(17) for j in range(i + 1, 17) if not (rev.EXIT_GRID[i][0] == rev.EXIT_GRID[j][0] and rev.EXIT_GRID[i][1] == rev.EXIT_GRID[j][1]))
    # a planted world: 30 trades whose windows sit exactly on the first red close -> the list recovers X3
    Xs, lo, hi = [], [], []
    rng = np.random.default_rng(2)
    for _ in range(30):
        n = 12
        x = np.zeros((n, 10)); x[:, 4] = np.arange(n)
        k = int(rng.integers(2, 9)); x[k, 2] = 1.0; x[k + 1:, 2] = rng.random(n - k - 1) < 0.5
        Xs.append(x); lo.append(k); hi.append(k)
    fires = np.array([[rev.rule_fire_day(X, rr) for X in Xs] for rr in rules])
    lst, hr = rev.fit_decision_list(fires, np.array(lo), np.array(hi), np.ones(30, bool), rules)
    assert hr == 1.0 and lst and all(("X3", "==", 1) in rr for rr in lst[:1])


def test_hazard_likelihood_on_a_hand_world():
    # one trade, 3 sessions, fixed hazards via the intercept only: h = sigmoid(b); window [1, 2] -> P = S(0) - S(2)
    X = np.zeros((3, 1))
    Xs = [np.hstack((X, np.ones((3, 1))))]
    b = 0.3
    h = 1 / (1 + np.exp(-b))
    ll, g = rev.hazard_loglik_grad(np.array([0.0, b]), Xs, np.array([1]), np.array([2]), lam=0.0)
    P = (1 - h) - (1 - h) ** 3
    assert ll == pytest.approx(np.log(P))
    eps = 1e-6
    ll2, _ = rev.hazard_loglik_grad(np.array([0.0, b + eps]), Xs, np.array([1]), np.array([2]), lam=0.0)
    assert g[1] == pytest.approx((ll2 - ll) / eps, rel=1e-3)
    # still held: log S(last)
    ll3, g3 = rev.hazard_loglik_grad(np.array([0.0, b]), Xs, np.array([0]), np.array([-1]), lam=0.0)
    assert ll3 == pytest.approx(3 * np.log(1 - h)) and g3[1] == pytest.approx(-3 * h)
    # the fit recovers a high hazard when every sale is on day 0..1
    rng = np.random.default_rng(4)
    Xr = [rng.normal(size=(6, 2)) for _ in range(40)]
    lo = np.zeros(40, int); hi = np.ones(40, int)
    m = rev.fit_hazard(Xr, lo, hi, lam=1.0)
    assert m["w"][-1] > 0 and np.isfinite(m["loglik"])
    day = rev.hazard_sell_day(Xr[0], m)
    assert 0 <= day <= 1
    # the median day: a constant hazard of 0.2 crosses 0.5 at the 4th session (1 - 0.8^4 = 0.59)
    const = dict(w=np.array([0.0, 0.0, np.log(0.2 / 0.8)]), mu=np.zeros(2), sd=np.ones(2))
    assert rev.hazard_sell_day(np.zeros((10, 2)), const) == 3


def test_hit_rate_recovery_void_and_trivial():
    sell = np.array([3, 5, 10 ** 6, 2])
    lo, hi = np.array([3, 4, 1, 3]), np.array([4, 6, 2, 3])
    assert rev.hit_rate(sell, lo, hi, np.ones(4, bool)) == 0.5
    assert rev.hit_rate(sell, lo, hi, np.array([True, True, False, False])) == 1.0
    assert rev.recovery(1.0, 1.5, 2.0) == (pytest.approx(np.log(1.5) / np.log(2.0)), "")
    assert np.isnan(rev.recovery(1.0, 1.1, 1.2)[0]) and "1.25" in rev.recovery(1.0, 1.1, 1.2)[1]
    assert np.isnan(rev.recovery(1.0, 1.1, 0.9)[0])
    # L7: the buy day = session 1, so "the close of session 3" is offset 2; the first red close is read from session 2 on (offset 1)
    X = np.zeros((6, 10)); X[:, 4] = np.arange(6); X[2, 2] = 1.0
    assert rev.trivial_sell_days(X) == {"close_of_session_3": 2, "first_red_close": 2}
    X0 = np.zeros((6, 10)); X0[0, 2] = 1.0                                                   # a red BUY-DAY close alone never fires
    assert rev.trivial_sell_days(X0)["first_red_close"] == 10 ** 6
    X1 = np.zeros((6, 10)); X1[0, 2] = 1.0; X1[1, 2] = 1.0
    assert rev.trivial_sell_days(X1)["first_red_close"] == 1


def test_exit_walk_stop_then_rule():
    r = stop_fixture()
    smas = smas_of_rec(r)
    # the rule says sell at session 4; the stop at 48.0 is touched on session 2 -> the stop first
    j, px, kind = rev.exit_walk(r, lambda X: 4, 48.0, "T", smas, horizon=8)
    assert (j, px, kind) == (2, 48.0, "stop")
    j, px, kind = rev.exit_walk(r, lambda X: 4, 46.0, "T", smas, horizon=8)
    assert (j, kind) == (4, "sell_close") and px == float(r.bars.c[r.e + 4])
    j, px, kind = rev.exit_walk(r, lambda X: 10 ** 6, 46.0, "T", smas, horizon=6)
    assert (j, kind) == (6, "mark")


# ═════════════════════════════════════════════════════════════════════════════════════════════ WHY
def test_phrase_hits_and_join_rule():
    texts = {"v1": ("so i sold it yesterday and i got stopped out on the other", None, None)}
    txt = texts["v1"][0]
    offs, pos = [], 0
    toks = txt.split(" ")
    for w in toks:
        offs.append(pos); pos += len(w) + 1
    texts["v1"] = (txt, offs, [float(i) for i in range(len(toks))])
    hits = rev.phrase_hits(texts)
    # the alternation is matched left to right without overlap: "i sold it" yields "i sold" (never "sold it" too), "i got stopped out" yields
    # "got stopped" (never "stopped out" too) — the doc's 4,015 is counted exactly so
    assert [h[2] for h in hits] == ["i sold", "got stopped"]
    assert [h[1] for h in hits] == [1.0, 7.0]                               # the time of the word each match starts in
    assert rev.phrase_class("i sold") == "SOLD" and rev.phrase_class("stopped out") == "STOPPED" and rev.phrase_class("took partials") == "PARTIAL"
    cal = [d.isoformat() for d in sessions(30, "2020-03-02")]
    VS = pd.DataFrame({"id": ["v1"], "upload_date": ["20200310"]}).set_index("id")
    MG = {"v1": pd.DataFrame({"ticker": ["AAA", "BBB"], "tf": [2.0, 200.0]})}
    s0 = cal.index("2020-03-10")
    a = mk_buy(eid=1, sym="AAA", exit_lo=cal[s0], exit_hi=cal[s0]); a.exit_lo_i = a.exit_hi_i = s0
    b = mk_buy(eid=2, sym="BBB", exit_lo=cal[s0 + 5], exit_hi=cal[s0 + 6]); b.exit_lo_i, b.exit_hi_i = s0 + 5, s0 + 6
    c = mk_buy(eid=3, sym="AAA", exit_lo=cal[s0 - 1], exit_hi=cal[s0 - 1]); c.exit_lo_i = c.exit_hi_i = s0 - 1   # within [lo - 1, hi + 2]: also qualifies -> ambiguous
    J = rev.caption_joins(hits, VS, MG, {"AAA": [a, c], "BBB": [b]}, cal)
    assert J["hits"] == 2 and J["near"] == 2 and J["qual"] == 2 and J["amb"] == 2 and J["trades"] == {1, 3}
    J2 = rev.caption_joins(hits, VS, MG, {"AAA": [a], "BBB": [b]}, cal)
    assert J2["amb"] == 0 and J2["trades"] == {1} and all(j["eids"] == [1] for j in J2["joins"])


def test_why_sheet_and_precision():
    joins = [dict(video="v1", t=float(10 * i), phrase="i sold", cls=c, upload="20200310", s0=5, ambiguous=False, eids=[1], tickers=["AAA"])
             for i, c in enumerate(["STOPPED"] * 10 + ["SOLD"] * 10 + ["PARTIAL"] * 5)]
    toks = ["w"] * 400
    offs = [2 * i for i in range(400)]
    texts = {"v1": (" ".join(toks), offs, [float(i) for i in range(400)])}
    sn = pd.DataFrame({"vid": ["v1", "v1"], "frame_id": ["g1", "g2"], "folder": ["f", "f"], "stream_ts": ["5", "100"]})
    b = mk_buy(eid=1)
    rows = rev.why_sheet_rows(joins, texts, sn, {1: b})
    assert len(rows) == 20 and pd.Series([r["cls"] for r in rows]).value_counts().to_dict() == {"STOPPED": 8, "SOLD": 8, "PARTIAL": 4}
    rows2 = rev.why_sheet_rows(joins, texts, sn, {1: b})
    assert [r["t_seconds"] for r in rows] == [r["t_seconds"] for r in rows2]       # seeded
    sheet = pd.DataFrame(rows)
    assert np.isnan(rev.why_precision(sheet)[0])
    sheet["verdict"] = ["correct"] * 15 + ["wrong"] * 5
    assert rev.why_precision(sheet) == (0.75, "")


# ═════════════════════════════════════════════════════════════════════════════════════════════ sets and helpers
def test_build_sets_and_trade_days():
    cal = [d.isoformat() for d in sessions(400, "2019-06-03")]
    i20 = cal.index("2020-03-02")
    bs = [mk_buy(eid=1, E=cal[i20], lo=cal[i20], hi=cal[i20], exit_lo=cal[i20 + 2], exit_hi=cal[i20 + 3]),
          mk_buy(eid=2, E=cal[i20], lo=cal[i20], hi=cal[i20], exit_lo=cal[i20], exit_hi=cal[i20], flicker=True),
          mk_buy(eid=3, E=cal[i20], lo=cal[i20], hi=cal[i20 + 2], window_len=3, exit_lo=cal[i20 + 5], exit_hi=cal[i20 + 5]),
          mk_buy(eid=4, sym="SPY", sym_a="SPY", E=cal[i20], lo=cal[i20], hi=cal[i20], exit_lo=cal[i20 + 1], exit_hi=cal[i20 + 1]),
          mk_buy(eid=5, E=cal[i20], lo=cal[i20], hi=cal[i20], exit_lo="", exit_hi="", still_held=True, initial=True)]
    bs[3].type_ok = False
    for b in bs:
        b.type_ok = b.type_ok if b.eid == 4 else True
    rev.index_calendar(bs, cal)
    S = rev.build_sets(bs)
    assert len(S["ni"]) == 4 and len(S["c633"]) == 3 and len(S["ex_nf"]) == 2 and len(S["ex_all"]) == 3 and len(S["multi_nf"]) == 1
    assert len(S["sel_fit"]) == 1 and S["nfit_type"] == 1 and len(S["und_fit"]) == 2 and rev.tdays(S["und_fit"]) == 4 + 1
    assert rev.med_held(S["und_fit"]) == 2.5 and bs[0].exit_window_len() == 2
    assert "sel_fit" in bs[0].sets and "und_fit" in bs[1].sets
    # re-check N3: the other-level buys split by year — the 2021-22 members are read in --check only, the rest at the fit
    cal = [d.isoformat() for d in sessions(700, "2019-06-03")]
    i20, i21 = cal.index("2020-03-02"), cal.index("2021-02-01")
    ol = [mk_buy(eid=11, E=cal[i20], lo=cal[i20], hi=cal[i20]), mk_buy(eid=12, E=cal[i21], lo=cal[i21], hi=cal[i21]),
          mk_buy(eid=13, E=cal[i21], lo=cal[i21], hi=cal[i21 + 2], window_len=3)]
    for b in ol:
        b.type_ok, b.other_level_inside = True, True
    rev.index_calendar(ol, cal)
    S2 = rev.build_sets(ol)
    assert [b.eid for b in S2["other_level_47"]] == [11, 12, 13]
    assert [b.eid for b in S2["other_level_fit"]] == [11] and [b.eid for b in S2["other_level_chk"]] == [12, 13]
    assert "sel_chk" in ol[1].sets and "other_level_chk" in ol[1].sets and "other_level_fit" not in ol[1].sets


def test_hhmm_and_spearman():
    assert rev.hhmm_to_min("09:30") == 0 and rev.hhmm_to_min("10:05") == 35 and rev.hhmm_to_min("07:30") == -120 and rev.hhmm_to_min("") is None
    assert rev.min_to_hhmm(35) == "10:05"
    assert rev.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert rev.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_pack_bits_popcount():
    M = np.zeros((2, 70), dtype=bool)
    M[0, :5] = True; M[1, 64:70] = True
    B = rev.pack_bits(M)
    assert B.shape[1] == 2 and list(rev.popcount_rows(B)) == [5, 6]
    assert rev.popcount_rows(B[0] & B[1]) == 0


# ═════════════════════════════════════════════════════════════════════════════════════════════ smoke tests on a synthetic export (the stage functions end to end)
def synth_daily(n: int = 320, seed: int = 11):
    """A runner `Daily` with four tickers over one calendar: AAA (a stock), BBB (a stock), QQQ, SPY; flat arrays sorted by ticker then date."""
    cal = sessions(n, "2019-01-02")
    tks = ["AAA", "BBB", "QQQ", "SPY"]
    rng = np.random.default_rng(seed)
    o, h, l, c, v, ci = [], [], [], [], [], []
    for k, tk in enumerate(tks):
        base = 20.0 + 10 * k
        r = rng.normal(0.0008, 0.015, n)
        cc = base * np.cumprod(1 + r)
        oo = cc * (1 + rng.normal(0, 0.004, n))
        hh = np.maximum(oo, cc) * (1 + np.abs(rng.normal(0, 0.008, n)))
        ll = np.minimum(oo, cc) * (1 - np.abs(rng.normal(0, 0.008, n)))
        o.append(oo); h.append(hh); l.append(ll); c.append(cc); v.append(np.full(n, 3_000_000.0)); ci.append(np.arange(n, dtype=np.int32))
    start = np.arange(len(tks)) * n
    stop = start + n
    D = rev.R.Daily(tks, start, stop, np.concatenate(ci), np.concatenate(o), np.concatenate(h), np.concatenate(l), np.concatenate(c), np.concatenate(v),
                    cal, {t: k for k, t in enumerate(tks)}, 0, 0)
    return D, [d.isoformat() for d in cal]


def synth_M(D, cal):
    return dict(DA=D, DB=D, Ds={"A": D, "B": D}, cal_u=cal, map_b=None, px=None, guards={"A": {}, "B": {}}, done={}, files={}, sight=rev.Sightings({}), held={})


def test_pool_rows_and_pick_features_on_a_synthetic_export():
    D, cal = synth_daily()
    small = {"AAA": ("CS", "XNAS"), "BBB": ("ETF", "ARCX"), "QQQ": ("ETF", "XNAS"), "SPY": ("ETF", "ARCX")}   # funds are out of the pool
    sic = {}
    qst = rev.qqq_states(D)
    day_cis = [250, 260]
    pool = rev.pool_rows_for_days(D, None, day_cis, qst, small, sic, {cal[260]: {"AAA"}}, cal, "A")
    assert set(pool["ticker"]) == {"AAA"} and len(pool) == 2 and set(pool["day_ci"]) == {250, 260}
    assert pool.loc[pool["day_ci"] == 260, "held"].all() and not pool.loc[pool["day_ci"] == 250, "held"].any()
    assert set(rev.NUMERIC) <= set(pool.columns) and pool["F15"].between(0, 1).all()
    b = mk_buy(E=cal[250], lo=cal[250], hi=cal[250], sym_a="AAA", ticker="AAA")
    CI = {d: i for i, d in enumerate(cal)}
    rev.index_calendar([b], cal)
    M = synth_M(D, cal)
    r = rev.make_rec(b, M, "A", {}, {}, {}, {}, want_minutes=False)
    f = rev.pick_features(r, None, qst, pool[pool["day_ci"] == 250])
    assert f["floor_ok"] and f["F17"] in rev.F17_CATS and 0 <= f["F15"] <= 1
    # the pick's F1..F14 equal the pool row's for the same ticker and day
    row = pool[pool["day_ci"] == 250].iloc[0]
    for k in rev.NUMERIC[:14]:
        assert f[k] == pytest.approx(float(row[k]))
    conds = rev.grid_from_pool(pool)
    assert all(isinstance(cd, rev.Cond) for cd in conds)


def test_accounts_and_families_on_synthetic_trades():
    D, cal = synth_daily()
    CI = {d: i for i, d in enumerate(cal)}
    M = synth_M(D, cal)
    recs = []
    for k, e in enumerate(range(200, 260, 6)):
        b = mk_buy(eid=k, E=cal[e], lo=cal[e], hi=cal[e], sym_a="AAA", ticker="AAA", exit_lo=cal[e + 3], exit_hi=cal[e + 4])
        rev.index_calendar([b], cal)
        r = rev.make_rec(b, M, "A", {}, {}, {}, {}, want_minutes=False)
        r.fill, r.fill_minute, r.fill_src, r.day0 = rev.registered_fill(r)
        r.stop_levels = rev.stop_levels(r, None)
        r.stop, r.stop_src = r.fill * (1 - r.adr20), "ADR20-T"
        r.day0 = rev.day0_for(r, r.fill_minute, r.stop)
        recs.append(r)
    smas_cache = {}
    Xs, lo, hi, scor, keep = rev.exit_rows_for(recs, smas_cache)
    assert keep.all() and all(len(X) == 5 for X in Xs) and scor.all() and list(lo) == [3] * 10 and list(hi) == [4] * 10
    lines = []
    fam = rev.fit_families(lines.append, Xs, lo, hi, scor, "synthetic")
    assert fam["list"] and np.isfinite(fam["hazard"]["loglik"]) and 0 <= fam["list_hit"] <= 1
    chosen_obj = dict(family="list", list=[[list(c) for c in r] for r in fam["list"]],
                      hazard=dict(w=fam["hazard"]["w"].tolist(), mu=fam["hazard"]["mu"].tolist(), sd=fam["hazard"]["sd"].tolist()), stop=None)
    C = dict(cal=cal, CI=CI)
    acc = rev.accounts_for(lines.append, recs, chosen_obj, M, C, (cal[200], cal[300]), smas_cache)
    assert set(acc) == {"chain", "registered"} and acc["chain"]["n"] == 10 and acc["chain"]["ours"] > 0 and acc["chain"]["his"] > 0
    assert any("recovery" in ln for ln in lines)
    # the panel trade sells at the close of exit_hi; the speed trail is the holdings' arm; both size on the chain's stop
    t_h = rev.panel_trade(recs[0], None, len(cal))
    assert t_h.status == "mark" and t_h.sessions_held == 4 and t_h.legs[0][3] == float(recs[0].bars.c[recs[0].e + 4])
    t_o = rev.speed_trail_trade(recs[0], M, {})
    assert t_o is not None and t_o.width == pytest.approx((recs[0].fill - recs[0].stop) / recs[0].fill)
    # the held-through table over the synthetic trades runs on every level and variant
    tab = rev.stop_table(recs, lambda r: rev.smas_for(r, smas_cache), rev.Sightings({}))
    assert set(tab) == {(L, V) for L in rev.STOP_LEVELS + rev.STOP_CONTROLS for V in rev.STOP_VARIANTS}
    assert all(0 <= t["H_cond"] <= 1 or np.isnan(t["H_cond"]) for t in tab.values())
    # the forward guard refuses a fit stage reading the forward bars of a trade outside its fit set
    recs[0].guard = rev.BarGuard(set())
    with pytest.raises(rev.GuardStop):
        rev.exit_rows_for([recs[0]], smas_cache)
    recs[0].guard = None


def test_rec_drop_reason_and_population_guard():
    D, cal = synth_daily()
    M = synth_M(D, cal)
    ok = mk_buy(E=cal[250], lo=cal[250], hi=cal[250], sym_a="AAA", ticker="AAA")
    early = mk_buy(E=cal[30], lo=cal[30], hi=cal[30], sym_a="AAA", ticker="AAA")
    gone = mk_buy(E=cal[250], lo=cal[250], hi=cal[250], sym_a="ZZZ", ticker="ZZZ")
    assert rev.rec_drop_reason(ok, M, "A", {}) is None
    assert rev.rec_drop_reason(early, M, "A", {}) == f"bars_before_E_lt_{rev.REC_MIN_BARS}"
    assert rev.rec_drop_reason(gone, M, "A", {}) == "ticker_not_in_export"
    assert rev.make_rec(early, M, "A", {}, {}, {}, {}, want_minutes=False) is None
    # guard (3): a population claim that disagrees with the doc STOPs a stage before any bar is opened
    quiet = lambda _m: None  # noqa: E731
    cl = rev.Claims(quiet)
    cl("no such anchor in the doc", "x", 2, 3)
    assert cl.bad == [(0, "x", 2, 3)]                       # an anchor the doc no longer carries prints as [L?] and still counts


def test_g8_file_shape(tmp_path):
    rp.write_g8_file(str(tmp_path / "g.tsv"), [("rev", "AAA", "2020-03-02", 4, 0.0)])
    t = pd.read_csv(tmp_path / "g.tsv", sep="\t")
    assert list(t.columns) == ["cell", "attempt", "ticker", "entry_date", "exit_j", "realized_r"] and t.iloc[0]["exit_j"] == 4


# ═════════════════════════════════════════════════════════════════════════════════════════════ the 2026-10-24 check's findings (H1 .. L8)
def test_doc_line_of(tmp_path):
    d = tmp_path / "d.md"
    d.write_text("one\ntwo **anchor** here\nthree\n")
    assert rev.doc_line_of("**anchor**", str(d)) == 2 and rev.doc_line_of("absent", str(d)) == 0
    assert all(rev.doc_line_of(a) > 0 for a, _l, _v in rev.EXPECT), [a for a, _l, _v in rev.EXPECT if rev.doc_line_of(a) == 0]   # every claim's anchor is in the doc


def test_dry_run_complete_gate(tmp_path):
    p = tmp_path / "dry.txt"
    assert not rev.dry_run_complete(str(p))
    p.write_text("# dry\n  [L1] x | doc 1 | mine 2 | MISMATCH\nSTOPPED: the dry run does not reproduce the registration\n")
    assert not rev.dry_run_complete(str(p))                 # L3: a STOPPED dry run is not a dry run
    p.write_text("# dry\n## RESULT: 60 claims, 60 OK, 0 MISMATCH\n\nDRY RUN COMPLETE: every composition count reproduced\n\n")
    assert rev.dry_run_complete(str(p))


def test_fit_set_violation_per_stage():
    cal = [d.isoformat() for d in sessions(800, "2019-01-02")]
    i20, i21 = cal.index("2020-03-02"), cal.index("2021-03-01")
    u20 = mk_buy(eid=1, E=cal[i20], lo=cal[i20], hi=cal[i20], exit_lo=cal[i20 + 2], exit_hi=cal[i20 + 2])
    u21 = mk_buy(eid=2, E=cal[i21], lo=cal[i21], hi=cal[i21], exit_lo=cal[i21 + 2], exit_hi=cal[i21 + 2])
    d21 = mk_buy(eid=3, setup="breakout", E=cal[i21], lo=cal[i21], hi=cal[i21], decides=True, exit_lo=cal[i21 + 2], exit_hi=cal[i21 + 2])
    d21_noexit = mk_buy(eid=4, setup="breakout", E=cal[i21], lo=cal[i21], hi=cal[i21], decides=True, exit_lo="", exit_hi="", still_held=True)
    fl20 = mk_buy(eid=5, E=cal[i20], lo=cal[i20], hi=cal[i20], flicker=True, exit_lo=cal[i20], exit_hi=cal[i20])
    w20 = mk_buy(eid=6, E=cal[i20], lo=cal[i20], hi=cal[i20 + 2], window_len=3, exit_lo=cal[i20 + 5], exit_hi=cal[i20 + 5])
    etf = mk_buy(eid=7, E=cal[i20], lo=cal[i20], hi=cal[i20], exit_lo=cal[i20 + 2], exit_hi=cal[i20 + 2]); etf.type_ok = False
    bs = [u20, u21, d21, d21_noexit, fl20, w20, etf]
    rev.index_calendar(bs, cal)
    for b in (u20, fl20):
        b.in_bracket = True
    assert rev.fit_set_violation("exit", u20) is None and rev.fit_set_violation("exit", d21) is None and rev.fit_set_violation("exit", fl20) is None
    assert rev.fit_set_violation("exit", u21) and rev.fit_set_violation("exit", d21_noexit) and rev.fit_set_violation("exit", w20) and rev.fit_set_violation("exit", etf)
    assert rev.fit_set_violation("select", u20) is None and rev.fit_set_violation("select", fl20) and rev.fit_set_violation("select", d21)
    assert rev.fit_set_violation("enter", u20) is None and rev.fit_set_violation("enter", fl20) and rev.fit_set_violation("enter", w20)
    assert rev.fit_set_violation("stop", u20) is None and rev.fit_set_violation("stop", fl20) is None and rev.fit_set_violation("stop", u21) and rev.fit_set_violation("stop", d21)
    lines = []
    eids = rev.assert_fit_set(lines.append, "exit", [u20, d21, fl20])
    assert eids == {1, 3, 5}
    with pytest.raises(rev.GuardStop):
        rev.assert_fit_set(lines.append, "exit", [u20, u21])


def runner_world(n: int = 800):
    """A synthetic world for the stage runners: two stocks over 2019-01..2022-02, undated 2020 buys of AAA (four before July, four after), one dated 2020
    AAA breakout, one dated 2021 BBB breakout with an in-session bracket (= ENTER's dated check set), one undated 2021 BBB buy (check material)."""
    D, cal = synth_daily(n=n)
    CI = {d: i for i, d in enumerate(cal)}
    buys = []
    for k, d_ in enumerate(("2020-02-03", "2020-03-02", "2020-04-01", "2020-05-01", "2020-07-01", "2020-08-03", "2020-09-01", "2020-10-01")):
        i = CI[d_]
        buys.append(mk_buy(eid=k + 1, sym_a="AAA", ticker="AAA", E=cal[i], lo=cal[i], hi=cal[i], exit_lo=cal[i + 3], exit_hi=cal[i + 4]))
    i = CI["2020-06-01"]
    buys.append(mk_buy(eid=20, sym_a="AAA", ticker="AAA", setup="breakout", decides=True, pivot=None, E=cal[i], lo=cal[i], hi=cal[i], exit_lo=cal[i + 5], exit_hi=cal[i + 6]))
    i = CI["2021-02-01"]
    d21 = mk_buy(eid=21, sym="BBB", sym_a="BBB", ticker="BBB", setup="breakout", decides=True, E=cal[i], lo=cal[i], hi=cal[i], exit_lo=cal[i + 4], exit_hi=cal[i + 5])
    d21.first_clock, d21.flat_clock, d21.p_ctx, d21.in_bracket = "10:40", "10:00", "in", True
    buys.append(d21)
    i = CI["2021-03-01"]
    buys.append(mk_buy(eid=22, sym="BBB", sym_a="BBB", ticker="BBB", E=cal[i], lo=cal[i], hi=cal[i], exit_lo=cal[i + 3], exit_hi=cal[i + 3]))
    rev.index_calendar(buys, cal)
    byeid = {b.eid: b for b in buys}
    S = dict(und_fit=[byeid[k] for k in range(1, 9)], exit_fit_dated=[byeid[20], byeid[21]], ent_chk_dated=[byeid[21]], und_chk=[byeid[22]])
    S["exit_fit"] = S["exit_fit_dated"] + S["und_fit"]
    C = dict(buys=buys, S=S, cal=cal, CI=CI)
    M = synth_M(D, cal)
    return D, cal, C, M, byeid


def test_exit_fit_runner_end_to_end(tmp_path, monkeypatch):
    """H1 / L8: the EXIT fit itself, end to end on the synthetic world — a dated 2021 trade in the fit set runs to CHOSEN EXIT (the old date-keyed guard
    raised on its first forward bar), an undated 2021 trade in the fit set is refused by the fit-set assertion, and a record outside the fit set
    cannot read a forward bar. M4: the dated 2021 bracket (ENTER's dated check set) carries the REGISTERED fill, flagged."""
    D, cal, C, M, byeid = runner_world()
    out = tmp_path / "reverse"
    out.mkdir()
    monkeypatch.setattr(rev, "OUT_DIR", str(out))
    monkeypatch.setattr(rev, "LEDGER", str(tmp_path / "ledger.tsv"))
    monkeypatch.setattr(rev, "load_for_stage", lambda say, C_, a, b: M)
    monkeypatch.setattr(rev, "read_chosen", lambda stage: {"enter": {"object": {"level": "L2"}}, "stop": {"object": {"level": "S3", "variant": "T"}}}[stage])
    monkeypatch.setattr(rev, "g8_run", lambda say, recs, label: None)
    say = rp.Say()
    rc = rev.exit_fit(say, C)
    assert rc == 0
    text = "\n".join(say.lines)
    assert "CHOSEN EXIT:" in text and "fit set composition asserted" in text and "STOPPED" not in text
    tr = pd.read_csv(out / "exit_fit_trades.tsv", sep="\t")
    assert set(tr["eid"]) == {1, 2, 3, 4, 5, 6, 7, 8, 20, 21}                      # the dated 2021 trade IS in the fit (in-sample by registration, §10)
    row21 = tr[tr["eid"] == 21].iloc[0]
    assert bool(row21["fill_checkwin_registered"]) and row21["fill_src"] == "close_proxy"   # M4: never the chosen level on ENTER's dated check bracket
    assert not tr[tr["eid"] == 20].iloc[0]["fill_checkwin_registered"]
    assert (out / "exit_fit_chosen.json").exists() and (tmp_path / "ledger.tsv").exists()
    # the negative: an undated 2021 buy smuggled into the fit set -> the fit-set assertion STOPs before any bar is opened
    C2 = dict(C, S=dict(C["S"], exit_fit=C["S"]["exit_fit"] + [byeid[22]]))
    with pytest.raises(rev.GuardStop, match="outside the registered fit set"):
        rev.exit_fit(rp.Say(), C2)
    # the guard itself: a record outside the fit set cannot read a forward bar; the dated 2021 inside it can
    g = rev.BarGuard({b.eid for b in C["S"]["exit_fit"]})
    r22 = rev.make_rec(byeid[22], M, "A", {}, {}, {}, {}, want_minutes=False, guard=g)
    r21 = rev.make_rec(byeid[21], M, "A", {}, {}, {}, {}, want_minutes=False, guard=g)
    for r in (r21, r22):
        r.fill, r.fill_minute, r.fill_src, r.day0 = rev.registered_fill(r)
        r.stop = r.fill * (1 - r.adr20)
    assert len(rev.exit_rows_for([r21], {})[0]) == 1
    with pytest.raises(rev.GuardStop):
        rev.exit_rows_for([r22], {})


def test_enter_deciding_set_and_no_level_yet():
    """M1: with L1 chosen the undated check brackets decide alone (L1 on dated 2021-22 is a re-read); any other level decides on both. L5: a level that
    does not exist yet at first_clock reads no_level_yet; an EP row's L3 is the prior-20 high, not its pivot (= the prior close = L5)."""
    scored = {1: "d", 2: "u", 3: "u"}
    dec, beside = rev.enter_deciding(scored, {1}, "L1")
    assert dec == {2: "u", 3: "u"} and beside == {1: "d"}
    dec2, beside2 = rev.enter_deciding(scored, {1}, "L2")
    assert dec2 == scored and beside2 == {}
    r = enter_fixture()
    r.b.first_clock, r.b.flat_clock = "09:33", "09:31"       # the frame showed him holding at 09:33: ORH5 (09:35) and the first-hour high do not exist yet
    res = rev.enter_score_trade(r, rev.rng_for("x"))
    assert res["L1"]["verdict"] == "no_level_yet" and not res["L1"]["feasible"] and res["L6"]["verdict"] == "no_level_yet"
    assert res["L2"]["verdict"] in ("HIT", "BALLPARK", "MISS", "no_bracket_minutes")
    summ = rev.enter_summary({1: res})
    assert summ["L1"]["verdicts"]["no_level_yet"] == 1 and summ["n"] == 1
    ep = enter_fixture()
    ep.b.setup, ep.b.dated, ep.b.pivot = "EP", True, 50.5
    L = rev.enter_levels(ep)
    assert L["L3"] == float(np.max(ep.bars.h[ep.p - 19:ep.p + 1])) and L["L3"] != L["L5"]
    bo = enter_fixture()
    bo.b.setup, bo.b.dated, bo.b.pivot = "breakout", True, 51.0
    assert rev.enter_levels(bo)["L3"] == 51.0


def test_apply_chain_registered_eids_and_moving_stop():
    """M4: a protected eid carries the registered fill and the flag. M10: the chosen stop is carried as a level OBJECT (('sma', 10) for S7) while
    r.stop keeps the buy-day price for sizing; exit_walk follows the moving average and stops where the fixed buy-day value would not."""
    r = stop_fixture()
    r.b.in_bracket = True
    r.b.first_clock, r.b.flat_clock = "10:40", "10:00"
    cc = rev.apply_chain([r], "L2", ("S7", "C"), {}, registered_fill_eids={r.b.eid})
    assert r.fill_checkwin_registered and r.fill_src == "open" and cc["fill_checkwin_registered"] == 1 and not r.fill_fallback
    assert r.stop_lvl == ("sma", 10) and r.stop_src.startswith("S7-C") and np.isfinite(r.stop)
    r2 = stop_fixture()
    rev.apply_chain([r2], None, ("S3", "T"), {})
    assert r2.stop_lvl == r2.stop_levels["S3"] and r2.stop == r2.stop_levels["S3"]
    # a rising SMA10: closes climb for 11 sessions after the buy day, then one close dips under the average (still far above the buy-day SMA10)
    bars, cidx = daily(220, base=50.0, seed=9)
    e = 180
    c = np.asarray(bars.c); o = np.asarray(bars.o); h = np.asarray(bars.h); l = np.asarray(bars.l)
    c[e - 15:e] = 45.0; c[e] = 50.0
    for j in range(1, 11):
        c[e + j] = 50.0 + j
    c[e + 11] = 55.0                                            # SMA10 at e+11 = mean(52..60, 55) = 55.9 > 55 -> a close below the moving stop
    c[e + 12:e + 20] = 56.0
    o[e - 15:e + 20] = c[e - 15:e + 20]; h[e - 15:e + 20] = c[e - 15:e + 20] + 0.2; l[e - 15:e + 20] = c[e - 15:e + 20] - 0.2
    bars = cb.daily_bars_from_arrays(bars.dates, o, h, l, c, bars.v)
    r3 = mk_rec(bars, cidx, e, fill=50.0, fill_minute=0, stop=46.0)
    smas = smas_of_rec(r3)
    j, px, kind = rev.exit_walk(r3, lambda X: 10 ** 6, ("sma", 10), "C", smas, horizon=19)
    assert (j, kind) == (12, "stop_close") and px == float(bars.o[e + 12])
    j2, _px, kind2 = rev.exit_walk(r3, lambda X: 10 ** 6, float(smas[10][e]), "C", smas, horizon=19)   # the buy-day VALUE (about 45.5) is never closed under
    assert kind2 == "mark" and j2 == 19


def test_day0_is_recomputed_against_the_chains_stop():
    """Re-check N2: the day-0 stop check is ALWAYS recomputed against the chain's actual stop (registered_fill's undated result is a hard-coded
    'not stopped'; check_stages' second apply_chain changes the stop). An undated buy whose buy-day low sits under the chosen stop: ours (the
    speed trail, reading r.day0) and chosen (exit_walk) both exit on the buy day. A close fill (the dated close-fill proxy) is never a day-0 stop."""
    D, cal = synth_daily()
    M = synth_M(D, cal)
    e = 250
    tid = D.tid["AAA"]
    k = int(D.start[tid]) + e
    D.o[k], D.h[k], D.l[k], D.c[k] = 50.0, 50.5, 49.0, 50.2                   # open 50, low 49 (2% under the open), close 50.2
    D.l[k - 1], D.h[k - 1], D.c[k - 1] = 49.6, 50.4, 50.0                       # the prior session's low 49.6 (S3): under the open, above the buy-day low
    b = mk_buy(eid=1, E=cal[e], lo=cal[e], hi=cal[e], sym_a="AAA", ticker="AAA", exit_lo=cal[e + 3], exit_hi=cal[e + 4])
    rev.index_calendar([b], cal)
    r = rev.make_rec(b, M, "A", {}, {}, {}, {}, want_minutes=False)
    r.adr20 = 0.04                                                               # the registered stop = one ADR20 under the fill: 48.05, never touched
    cache = {}
    rev.apply_chain([r], None, None, cache)                                     # check_stages' FIRST call: the registered stop
    assert r.fill_src == "open" and r.fill_minute == 0 and r.stop == pytest.approx(r.fill * 0.96) and not r.day0["stopped"]
    rev.apply_chain([r], None, ("S3", "T"), cache)                              # the SECOND call, the chosen stop: the buy-day low 49 is under S3 = 49.6
    assert r.stop == pytest.approx(49.6) and r.day0["stopped"] and r.day0["exit_price"] == pytest.approx(49.6)
    smas = rev.smas_for(r, cache)
    j, px, kind = rev.exit_walk(r, lambda X: 10 ** 6, r.stop_lvl, "T", smas)
    assert (j, kind) == (0, "day0_stop") and px == pytest.approx(49.6)          # chosen exits on the buy day
    t_o = rev.speed_trail_trade(r, M, {})
    assert t_o is not None and t_o.status == "stopped_day0" and t_o.sessions_held == 0 and t_o.legs[0][3] == pytest.approx(49.6)   # ours too (before N2: never)
    # one apply_chain alone (the undated registered fill's hard-coded result never survives)
    r1 = rev.make_rec(b, M, "A", {}, {}, {}, {}, want_minutes=False)
    r1.adr20 = 0.04
    rev.apply_chain([r1], None, ("S3", "T"), {})
    assert r1.day0["stopped"]
    # a close fill has nothing left in the day: never a day-0 stop, even under S1 = the day's low (true by equality before N2)
    rd = rev.make_rec(mk_buy(eid=2, setup="breakout", decides=True, E=cal[e], lo=cal[e], hi=cal[e], sym_a="AAA", ticker="AAA", exit_lo=cal[e + 3], exit_hi=cal[e + 4]),
                      M, "A", {}, {}, {}, {}, want_minutes=False)
    rev.index_calendar([rd.b], cal)
    rev.apply_chain([rd], None, None, {})
    assert rd.fill_src == "close_proxy" and rd.fill_minute is None and rd.stop == pytest.approx(49.0) and not rd.day0["stopped"]
    assert not rev.day0_for(rd, None, 49.5)["stopped"]


def test_exit_rows_for_hole_before_window_and_cut_window():
    """M9: a hole BEFORE exit_lo makes the trade still-held at its last bar (hi -1, not scorable), counted; a hole inside the window keeps the rows and
    leaves the hit rate."""
    r = stop_fixture(exit_lo_j=4, exit_hi_j=6)
    holed = r.cidx.copy(); holed[r.e + 2:] += 1                  # the session e+2 is missing: rows stop at j = 1
    r.cidx = holed
    notes = {}
    from collections import Counter
    notes = Counter()
    Xs, lo, hi, scor, keep = rev.exit_rows_for([r], {}, notes)
    assert keep.all() and len(Xs[0]) == 2 and list(hi) == [-1] and not scor[0] and notes["held_to_hole_before_window"] == 1
    ll, _g = rev.hazard_loglik_grad(np.array([0.0] * 10 + [-1.0]), [np.hstack((Xs[0], np.ones((2, 1))))], lo, hi, lam=0.0)
    assert np.isfinite(ll) and ll > -50                          # no -690 term from a window past the data
    r2 = stop_fixture(exit_lo_j=1, exit_hi_j=6)
    holed2 = r2.cidx.copy(); holed2[r2.e + 3:] += 1              # the hole falls inside the window
    r2.cidx = holed2
    notes2 = Counter()
    Xs2, lo2, hi2, scor2, _k = rev.exit_rows_for([r2], {}, notes2)
    assert len(Xs2[0]) == 3 and list(lo2) == [1] and list(hi2) == [2] and not scor2[0] and notes2["window_cut_by_hole"] == 1


def test_break_horizon_cuts_every_account(tmp_path):
    """L2: the chosen and his accounts stop at the identity break the speed trail already stopped at."""
    r = stop_fixture(exit_lo_j=5, exit_hi_j=6)
    assert rev.break_horizon(r, {}) == (min(rev.HORIZON + 1, len(r.bars) - r.e - 1), "")
    brk = {"AAA": np.array([r.bars.dates[r.e + 3].toordinal()], dtype=np.int64)}
    bh, why = rev.break_horizon(r, brk)
    assert (bh, why) == (2, "break")                             # sessions e+1, e+2 remain; the break is the move INTO e+3
    t = rev.panel_trade(r, None, 10_000, max_j=bh, cut_kind="mark_break")
    assert t.sessions_held == 2 and t.status == "mark_break" and t.legs[0][3] == float(r.bars.c[r.e + 2])
    assert rev.panel_trade(r, None, 10_000).sessions_held == 6
    holed = stop_fixture(exit_lo_j=5, exit_hi_j=6)
    hc = holed.cidx.copy(); hc[holed.e + 4:] += 1               # a missing session after e+3: a HOLE cut, not a break
    holed.cidx = hc
    assert rev.break_horizon(holed, brk) == (2, "break") and rev.break_horizon(holed, {}) == (3, "hole")
    r.guard = rev.BarGuard(set())
    with pytest.raises(rev.GuardStop):
        rev.break_horizon(r, brk)


def test_pick_features_pool_empty_and_place_windows():
    """M5 / M6: F15 / F16 are never a default — a day without pool rows reads NaN + pool_empty; placement scores a window session only with that day's
    (light) pool rows, else counts it `session_pool_empty`; light rows carry the returns only."""
    D, cal = synth_daily()
    small = {"AAA": ("CS", "XNAS"), "BBB": ("CS", "XNAS"), "QQQ": ("ETF", "XNAS"), "SPY": ("ETF", "ARCX")}
    qst = rev.qqq_states(D)
    M = synth_M(D, cal)
    b = mk_buy(E=cal[250], lo=cal[250], hi=cal[250], sym_a="AAA", ticker="AAA")
    rev.index_calendar([b], cal)
    r = rev.make_rec(b, M, "A", {}, {}, {}, {}, want_minutes=False)
    f0 = rev.pick_features(r, None, qst, None)
    assert f0["pool_empty"] and np.isnan(f0["F15"]) and np.isnan(f0["F16"])
    light = rev.pool_rows_for_days(D, None, [250, 251, 252], qst, small, {}, {}, cal, "A", light=True)
    assert set(light["ticker"]) == {"AAA", "BBB"} and "F1" not in light.columns and {"ret63", "ret21", "F15", "F16", "held"} <= set(light.columns)
    f1 = rev.pick_features(r, None, qst, light[light["day_ci"] == 250])
    assert not f1["pool_empty"] and 0 <= f1["F15"] <= 1
    full = rev.pool_rows_for_days(D, None, [250], qst, small, {}, {}, cal, "A")
    assert f1["F1"] == pytest.approx(float(full[full["ticker"] == "AAA"].iloc[0]["F1"]))      # the pick's F1 equals its own pool row's
    w = mk_buy(eid=5, E=cal[250], lo=cal[250], hi=cal[252], window_len=3, sym_a="AAA", ticker="AAA")
    rev.index_calendar([w], cal)
    conj = [[rev.Cond("F15", ">=", 0.0)]]                                                     # a condition on the percentile: needs the day's pool
    by_day = {d: g for d, g in light.groupby("day_ci")}
    rows, notes = rev.place_windows([w], M, D, None, qst, by_day, conj, cal)
    assert notes["session_scored"] == 3 and rows[0]["placed"] == cal[252] and not rows[0]["placed_by_default"]
    rows0, notes0 = rev.place_windows([w], M, D, None, qst, {}, conj, cal)
    assert notes0["session_pool_empty"] == 3 and rows0[0]["placed_by_default"] and rows0[0]["placed"] == cal[250]
    assert rev.percentile_with(2.0, np.array([1.0, 3.0])) == 0.5 and rev.percentile_with(5.0, np.array([1.0, 3.0])) == pytest.approx(2.5 / 3)


def test_after_loss_count_reads_the_earlier_entry_with_the_inferred_fill():
    """L6: the after-loss flag reads the earlier entry's exit against ITS chain fill (the registered open fill here: no minutes) — the expected flag is
    computed from the bars in the test, not from the function."""
    D, cal = synth_daily()
    M = synth_M(D, cal)
    a = mk_buy(eid=1, sym_a="AAA", ticker="AAA", E=cal[200], lo=cal[200], hi=cal[200], exit_lo=cal[204], exit_hi=cal[204])
    b = mk_buy(eid=2, sym_a="AAA", ticker="AAA", E=cal[210], lo=cal[210], hi=cal[210], exit_lo=cal[214], exit_hi=cal[214])
    b.rebuy, b.rebuy_prev_eid = True, 1
    rev.index_calendar([a, b], cal)
    C = dict(buys=[a, b])
    rb = rev.make_rec(b, M, "A", {}, {}, {}, {}, want_minutes=False)
    lines = []
    n = rev.after_loss_count(lines.append, [rb], C, M, None, None, "t")
    bars, _c = rev.bars_of(D, "AAA", {})
    expected = int(float(bars.c[204]) < float(bars.o[200]) * (1.0 + cb.ENTRY_SLIPPAGE_PCT))
    assert n == expected and "re-buys 1" in lines[0]
    with pytest.raises(rev.GuardStop):                             # the earlier entry outside the guard's allowed set: its exit bars are refused
        rev.after_loss_count(lines.append, [rb], C, M, None, rev.BarGuard({2}), "t")
    assert rev.after_loss_count(lines.append, [rb], C, M, None, rev.BarGuard({1, 2}), "t") == expected


def test_choose_family_applies_one_held_out_rule():
    """L6: the family choice (fit without 2020-07..12, compare on it, refit) is one function used for the dated-inclusive and the undated-only fits."""
    rng = np.random.default_rng(5)
    Xs, lo, hi, Es = [], [], [], []
    for i in range(24):
        n = 8
        x = np.zeros((n, 10)); x[:, 4] = np.arange(n)
        k = int(rng.integers(2, 6)); x[k, 2] = 1.0
        Xs.append(x); lo.append(k); hi.append(k)
        Es.append("2020-03-02" if i % 2 == 0 else "2020-09-01")
    lines = []
    ch = rev.choose_family(lines.append, Xs, np.array(lo), np.array(hi), np.ones(24, bool), Es, "t")
    assert ch["winner"] in ("list", "hazard") and "held-out hit rates" in " ".join(lines) and ch["full"]["list"]
    obj = rev.family_obj(ch)
    assert set(obj) >= {"family", "list", "hazard", "holdout"}


# ═════════════════════════════════════════════════════════════════════════════════════════════ caches keyed by id() (the 10-24 first SELECT fit crash)
def test_id_keyed_caches_never_serve_another_arrays_entry():
    """A cache entry planted under the id of a NEW bar array but holding a different array (what a reused id looks like) is never served:
    the feature table and the moving averages are rebuilt for the new array (the first SELECT fit crashed on a reused id, 2026-10-24)."""
    b1, c1 = daily(300, seed=1)
    b2, c2 = daily(260, seed=2)
    r2 = mk_rec(b2, c2, 200)
    smas = {(id(b2),): (b1, smas_of_rec(mk_rec(b1, c1, 200)))}
    got = rev.smas_for(r2, smas)
    assert len(got[10]) == len(b2.c) and np.allclose(got[20][-1], np.mean(np.asarray(b2.c, dtype=float)[-20:]))
    qst = {}
    T_other = rev.ticker_feature_table(b1, c1, None, qst)
    tc = {id(b2): (b1, T_other)}
    T = rev.feature_table_for(r2, None, qst, tc)
    assert len(T["F1"]) == len(b2.c) and tc[id(b2)][0] is b2


def test_rank_score_of_one_pick_is_a_scalar():
    """The rank fit scores one pick at a time: a one-row design times the weights is a 1-element array, which numpy 2 refuses to float()
    directly (the second SELECT fit run crashed there, 2026-10-24); the module takes element [0]."""
    df = pd.DataFrame([{**{k: 0.1 * j for j, k in enumerate(rev.NUMERIC)}, "F17": "up"}])
    X = rev.rank_design(df)
    w, mu, sd = np.ones(X.shape[1]), np.zeros(X.shape[1]), np.ones(X.shape[1])
    with pytest.raises(TypeError):
        float(((X - mu) / sd) @ w + 0.5)
    assert float((((X - mu) / sd) @ w + 0.5)[0]) == pytest.approx(float(X.sum()) + 0.5)
