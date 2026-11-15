#!/usr/bin/env python3
"""#717 pick model LIVE PORT — parity of the live list code against the research score, and the test fixture
(2026-11-14; offline, $0, read-only, ERA A ONLY — list nights 2017-01 .. 2022-03-31; nothing deployed, no rule changed).

WHAT IT CHECKS. For sampled era-A watch nights it runs the LIVE code path on the frozen era-A bar store, shaped the way
the nightly job shapes it (`breakout_v1_list._run`): the pool's cross-section (`night_cross_section`), every listable
member through `evaluate_members` on its last-200-session bars with the pick-model inputs on its last-300-session bars,
then `rank_all`. It compares, per night:
  POPULATION  the names the live code ranks inside (passing + removed only by a context check) == the research capture's
              list rows for that night (`bv1_pick_model_1113/list_eraA_4pct.parquet`, the 4% list of 2026-11-13);
  SCORE       the live `pick_score` of every such name vs the research score recomputed here exactly as
              `_717_pick_model_1113/02_fit_test.py::load` + `_717_rank2_1114/01_rank2.py` do (within-night
              rank(pct=True).fillna(0.5), X @ coef), and vs the stored `PM` column of
              `bv1_rank2_1114/pool3_ranked.parquet` on that file's rows (bridge: the two must agree).
A night "matches" when the population is identical and every score agrees to 1e-6.
  INPUTS      on a night that does not match: which names' RAW inputs differ from the capture's, per input (the EMA21
              distance is compared at 1e-6 relative — the live EMA is seeded at the first of 200 loaded bars, the
              research's at the ticker's first bar, a ~1e-8 difference that moves no rank unless two names tie that
              closely), and how far the ORDER moved: the day's top 5 / top 20 listed names by each score, and the
              rank correlation.

THE SEAL: bars = cb702_pre_v2 (2016-01-04 .. 2022-06-30; `P.setup()` asserts < 2025). `cb702/` is NOT opened.

Stages
  check [--nights N]   sample N nights (seed 717, half with E <= 2020-12-31, half after), print the parity per night
  scan_test [--want K] `check`'s sample held no exactly-matching night with a breakout day after 2020-12-31 (every one
                       carries a reused ticker symbol — see 01_check.out's reading), so this walks those nights from
                       the smallest list up (at most --tries) and stops at K exact matches, for the fixture only. It is
                       a SEARCH for matching nights, not a sample: its hit rate is not a parity rate.
  fixture              write tests/fixtures/bv1_pick_model_parity/ from matching nights of `check` + `scan_test`
                       (>= 200 pool3 rows; whole nights; both eras)

    python3 scripts/probes/_717_pick_live_1114/01_parity.py check --nights 40 > scripts/probes/_717_pick_live_1114/01_check.out
    python3 scripts/probes/_717_pick_live_1114/01_parity.py scan_test > scripts/probes/_717_pick_live_1114/01_scan_test.out
    python3 scripts/probes/_717_pick_live_1114/01_parity.py fixture > scripts/probes/_717_pick_live_1114/01_fixture.out
"""
import argparse, importlib.util, json, os, sys
from collections import Counter

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
spec = importlib.util.spec_from_file_location("p01", os.path.join(HERE, "..", "_717_precision_1112", "01_precision.py"))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
bv, cb, R, runner, G = P.bv, P.cb, P.R, P.runner, P.G
from agents.market_intelligence import breakout_v1_list as bl          # noqa: E402
from agents.market_intelligence import breakout_v1_pick_model as pm    # noqa: E402

CAPTURE = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"
POOL3 = "/Users/alvinfung/apollo_data/bv1_rank2_1114/pool3_ranked.parquet"
SIC = "/Users/alvinfung/apollo_data/cb702_pre_v2/cb702_sic.psv"
COEF = os.path.join(HERE, "..", "_717_pick_model_1113", "coef.json")
FIXDIR = os.path.join(REPO, "tests", "fixtures", "bv1_pick_model_parity")
PICKED = os.path.join(HERE, "01_check_nights.json")
SCANNED = os.path.join(HERE, "01_scan_test_nights.json")
SEED, TOL, FIT_LAST = 717, 1e-6, "2020-12-31"
VOL_KEEP = 60                # sessions of volume the fixture stores (the list path reads the last 50)
PCT = [f for f in pm.FEATURES if f != "first_base"]


def research_scores(cap_n: pd.DataFrame, co: dict) -> pd.Series:
    """The research score of every list row of ONE night — 02_fit_test.py::load's transform, 01_rank2.py's product."""
    d = cap_n.copy()
    d["dist_level"] = (d.level / d.close - 1) / d.adr20
    X = [np.ones(len(d))]
    for f in co["features"]:
        X.append((d.bases_before == 0).astype(float) if f == "first_base" else d[f].rank(pct=True).fillna(0.5))
    return pd.Series(np.c_[tuple(X)] @ np.r_[co["intercept"], co["coef"]], index=d.ticker.to_numpy())


def live_night(S, facts, rows_at, sic2, ci):
    """The live code on night ci -> (rows ranked by `rank_all`, the context-removed names, members, groups, series)."""
    D = S.D
    members, _ = R.night_members(S, facts, ci, rows_at)
    groups = [sic2.get(m["ticker"]) for m in members]
    rs_best, xs, _ = bl.night_cross_section(members, groups)
    live_members, long = [], {}
    for m in members:
        if not m["listable"]:
            live_members.append(dict(m, security_type=m["st"], listable=False, history=False, bars=None, cidx=None))
            continue
        bars, cidx = runner.bars_for(D, m["k"])
        Di = m["i"] - facts[m["k"]]["a"]
        lo_s = int(np.searchsorted(cidx, ci - bl.HISTORY_SESSIONS + 1))          # the job's `start` = cal[n - 200]
        lo_l = int(np.searchsorted(cidx, ci - pm.HISTORY_SESSIONS + 1))          # its `long_start` = cal[n - 300]
        sb, sc = bars.slice(lo_s, Di + 1), np.asarray(cidx[lo_s:Di + 1], dtype=np.int64)
        long[m["ticker"]] = bars.slice(lo_l, Di + 1)
        live_members.append({"ticker": m["ticker"], "security_type": m["st"], "listable": True,
                             "history": bv.history_ok(len(sb) - 1, sc), "bars": sb, "cidx": sc,
                             "r21": m["r21"], "r63": m["r63"], "r126": m["r126"]})
    pick = {"xs": xs, "long": long, "extra": []}
    removed = {}
    rows, fails, n_eval = bl.evaluate_members(live_members, rs_best, D.cal[ci], removed, pick)
    summary = bl.rank_all(rows, pick["extra"], bl.RANKING_PICK_MODEL)
    # the context-removed names in the order `evaluate_members` appended their inputs to pick["extra"]
    ctx = {t for v in removed.values() for t in v}
    pick["extra_tickers"] = [m["ticker"] for m in live_members if m["ticker"] in ctx]
    assert len(pick["extra_tickers"]) == len(pick["extra"])
    pick["gap_facts"] = {}
    for m in live_members:                      # per ranked name: a symbol break on record? bars inside the last 300 sessions?
        if m.get("bars") is not None and (m["ticker"] in ctx or m["ticker"] in {r["ticker"] for r in rows}):
            _b, c_all = runner.bars_for(D, D.tid[m["ticker"]])
            c_to = np.asarray(c_all[:int(np.searchsorted(c_all, ci)) + 1], dtype=np.int64)
            pick["gap_facts"][m["ticker"]] = {"symbol_break": m["ticker"] in S.breaks, "bars_to_d": int(len(c_to)),
                                              "bars_in_300": int((c_to > ci - pm.HISTORY_SESSIONS).sum())}
    return rows, removed, pick, members, groups, live_members, summary


def compare(ci, cap_n, pool_n, co, rows, removed, pick):
    removed_names = sorted({t for v in removed.values() for t in v})
    live_pop = {r["ticker"] for r in rows} | set(removed_names)
    cap_pop = set(cap_n.ticker)
    ref = research_scores(cap_n, co)
    bridge = float(np.abs(ref.reindex(pool_n.ticker).to_numpy() - pool_n.PM.to_numpy()).max()) if len(pool_n) else 0.0
    by = {r["ticker"]: r["pick_score"] for r in rows}
    common = [t for t in by if t in ref.index]
    unscored = [t for t in common if by[t] is None]
    diffs = np.array([abs(by[t] - ref[t]) for t in common if by[t] is not None]) if common else np.array([])
    pool_live = [t for t in pool_n.ticker if t in by and by[t] is not None]
    # raw-input differences vs the capture, per input, over the listed + context-removed names
    cn = cap_n.set_index("ticker")
    cn = cn.assign(dist_level=(cn.level / cn.close - 1) / cn.adr20, first_base=(cn.bases_before == 0).astype(float))
    live_in = {r["ticker"]: r["pick_inputs"] for r in rows}
    live_in.update(dict(zip(pick["extra_tickers"], pick["extra"])))          # the context-removed names rank too
    inp_diff, names_diff = Counter(), set()
    for t, x in live_in.items():
        if t not in cn.index:
            continue
        for f in pm.FEATURES:
            a_, b_ = x.get(f), cn.at[t, f]
            if a_ is None and pd.isna(b_):
                continue
            tol = 1e-6 if f == "vs_ema21_adr" else 1e-9
            if a_ is None or pd.isna(b_) or abs(a_ - b_) > tol * max(1.0, abs(b_)):
                inp_diff[f] += 1; names_diff.add(t)
    sc = pd.DataFrame({"live": pd.Series({t: by[t] for t in common if by[t] is not None}), "ref": ref}).dropna()
    top = lambda col, k: set(sc.sort_values(col, ascending=False).index[:k])
    order = {"top5_same": len(top("live", 5) & top("ref", 5)), "top20_same": len(top("live", 20) & top("ref", 20)),
             "spearman": float(sc.live.rank().corr(sc.ref.rank())) if len(sc) > 2 else float("nan")}
    return {"ci": int(ci), "cap_n": len(cap_pop), "live_pop_n": len(live_pop), "listed": len(rows), "context_removed": len(removed_names),
            "only_capture": sorted(cap_pop - live_pop), "only_live": sorted(live_pop - cap_pop), "unscored": unscored,
            "max_diff": float(diffs.max()) if diffs.size else float("nan"), "bridge_pool3": bridge,
            "pool3_rows": len(pool_n), "pool3_scored_live": len(pool_live),
            "input_diffs": dict(inp_diff), "names_with_input_diff": sorted(names_diff), **order,
            "diff_name_facts": {t: pick["gap_facts"].get(t) for t in sorted(names_diff)},
            "match": cap_pop == live_pop and not unscored and bool(diffs.size) and float(diffs.max()) <= TOL and bridge <= TOL}


def setup_all():
    S, nights = P.setup()
    assert S.D.cal[-1] < R.SEAL
    sic = pd.read_csv(SIC, sep="|", header=None, dtype=str, keep_default_na=False)
    sic2 = {t: s for t, s in ((t, cb.sic2(c)) for t, c in zip(sic[0], sic[3])) if s is not None}
    cap, pool = pd.read_parquet(CAPTURE), pd.read_parquet(POOL3)
    co = json.load(open(COEF))["models"]["primary"]
    assert tuple(co["features"]) == pm.FEATURES and co["intercept"] == pm.INTERCEPT and tuple(co["coef"]) == pm.COEF
    return S, G["facts"], G["rows_at"], sic2, cap, pool, co


def stage_check(a):
    S, facts, rows_at, sic2, cap, pool, co = setup_all()
    cal = S.D.cal
    nights = np.array(sorted(cap.ci.unique()))
    assert cal[int(nights.max())].isoformat() <= "2022-03-31"
    E = np.array([cal[c + 1].isoformat() for c in nights])
    rng = np.random.default_rng(SEED)
    pickn = sorted(set(rng.choice(nights[E <= FIT_LAST], a.nights // 2, replace=False).tolist())
                   | set(rng.choice(nights[E > FIT_LAST], a.nights - a.nights // 2, replace=False).tolist()))
    print(f"CHECK — {len(pickn)} era-A watch nights (seed {SEED}; {a.nights // 2} with the breakout day <= {FIT_LAST}, the rest after), "
          f"tolerance {TOL:g}")
    out, why = [], Counter()
    for ci in pickn:
        rows, removed, pick, *_ = live_night(S, facts, rows_at, sic2, ci)
        r = compare(ci, cap[cap.ci == ci], pool[pool.ci == ci], co, rows, removed, pick)
        r["D"] = cal[ci].isoformat()
        out.append(r)
        print(f"  {r['D']}  capture {r['cap_n']:>4d} | live population {r['live_pop_n']:>4d} (listed {r['listed']:>4d} + context-removed {r['context_removed']:>3d}) "
              f"| max |live - research| {r['max_diff']:.2e} | pool3 rows {r['pool3_rows']:>3d} (bridge {r['bridge_pool3']:.1e}) | "
              f"{'MATCH' if r['match'] else 'DIFF'}"
              + (f" only-capture {r['only_capture'][:6]}" if r["only_capture"] else "") + (f" only-live {r['only_live'][:6]}" if r["only_live"] else "")
              + (f" unscored {r['unscored'][:6]}" if r["unscored"] else "")
              + (f" | inputs differ on {len(r['names_with_input_diff'])} name(s) {r['names_with_input_diff'][:5]} {r['input_diffs']}; "
                 f"top 5 same {r['top5_same']}/5, top 20 same {r['top20_same']}/20, rank corr {r['spearman']:.4f}" if not r["match"] else ""), flush=True)
    n_ok = sum(r["match"] for r in out)
    rows_ok = sum(r["cap_n"] for r in out if r["match"])
    pop_ok = [r for r in out if not r["only_capture"] and not r["only_live"]]
    print(f"\nRESULT: {n_ok} of {len(out)} nights match (identical population and every score within {TOL:g}); "
          f"{rows_ok:,} list rows on the matching nights, {sum(r['pool3_rows'] for r in out if r['match']):,} of them pool3 rows.")
    print(f"  identical population on {len(pop_ok)} nights; on those the largest |live - research| = "
          f"{max((r['max_diff'] for r in pop_ok), default=float('nan')):.2e}")
    bad = [r for r in out if not r["match"]]
    print(f"  nights that differ: {len(bad)}; names only in the capture {sum(len(r['only_capture']) for r in bad)}, only live {sum(len(r['only_live']) for r in bad)}, "
          f"unscored live {sum(len(r['unscored']) for r in bad)}")
    facts = {}
    for r in out:
        facts.update(r["diff_name_facts"])
    brk = sorted(t for t, f in facts.items() if f and f["symbol_break"])
    short = sorted(t for t, f in facts.items() if f and not f["symbol_break"] and f["bars_in_300"] < min(f["bars_to_d"], pm.YEAR))
    other = sorted(set(facts) - set(brk) - set(short))
    print(f"  names whose raw inputs differ from the capture on ANY sampled night (listed or context-removed): {len(facts)} — "
          f"{len(brk)} with a symbol break on record (the ticker was reused / relisted) {brk}; "
          f"{len(short)} without one but with fewer of their last 252 bars inside the last 300 sessions (missing sessions) {short}; other {other}")
    unexplained = [r["D"] for r in bad if not r["names_with_input_diff"] and not r["only_capture"] and not r["only_live"]]
    print(f"  differing nights with NO name whose inputs differ and an identical population (unexplained): {unexplained}")
    if bad:
        print(f"  on the differing nights: names whose raw inputs differ from the capture {sum(len(r['names_with_input_diff']) for r in bad)} of "
              f"{sum(r['cap_n'] for r in bad):,} list rows; by input {dict(sum((Counter(r['input_diffs']) for r in bad), Counter()))}; "
              f"top 5 identical on {sum(r['top5_same'] == 5 for r in bad)} of {len(bad)} nights (mean {np.mean([r['top5_same'] for r in bad]):.2f}/5), "
              f"top 20 mean {np.mean([r['top20_same'] for r in bad]):.2f}/20, rank correlation min {min(r['spearman'] for r in bad):.4f}")
    json.dump(out, open(PICKED, "w"), indent=1)


def stage_scan_test(a):
    S, facts, rows_at, sic2, cap, pool, co = setup_all()
    cal = S.D.cal
    sizes = cap.groupby("ci").size()
    cand = [int(c) for c in sizes.sort_values(kind="stable").index if cal[int(c) + 1].isoformat() > FIT_LAST
            and (pool.ci == c).sum() >= a.min_pool][:a.tries]
    print(f"SCAN — breakout days after {FIT_LAST}, smallest list first, at least {a.min_pool} pool3 rows; stop at {a.want} exact matches (max {len(cand)} nights). A search, not a sample.")
    out = []
    for ci in cand:
        rows, removed, pick, *_ = live_night(S, facts, rows_at, sic2, ci)
        r = compare(ci, cap[cap.ci == ci], pool[pool.ci == ci], co, rows, removed, pick)
        r["D"] = cal[ci].isoformat()
        out.append(r)
        print(f"  {r['D']}  capture {r['cap_n']:>4d} | pool3 rows {r['pool3_rows']:>3d} | max |live - research| {r['max_diff']:.2e} | {'MATCH' if r['match'] else 'DIFF'}"
              + (f" {r['names_with_input_diff'][:5]} only-capture {r['only_capture'][:3]}" if not r["match"] else ""), flush=True)
        if sum(x["match"] for x in out) >= a.want:
            break
    print(f"\n{sum(x['match'] for x in out)} exact matches in {len(out)} nights walked")
    json.dump(out, open(SCANNED, "w"), indent=1)


def stage_fixture(a):
    picked = json.load(open(PICKED)) + (json.load(open(SCANNED)) if os.path.exists(SCANNED) else [])
    S, facts, rows_at, sic2, cap, pool, co = setup_all()
    cal = S.D.cal
    ok = [r for r in picked if r["match"] and r["pool3_rows"] > 0]
    # the fewest names for >= MIN_ROWS pool3 rows, at least one night from each side of the fit/test split
    ok.sort(key=lambda r: -r["pool3_rows"] / r["cap_n"])
    chosen, have = [], 0
    for side in (True, False):
        c = next(r for r in ok if (cal[r["ci"] + 1].isoformat() <= FIT_LAST) == side)
        chosen.append(c); have += c["pool3_rows"]
    for r in ok:
        if have >= a.min_rows:
            break
        if r not in chosen:
            chosen.append(r); have += r["pool3_rows"]
    assert have >= a.min_rows, have
    os.makedirs(FIXDIR, exist_ok=True)
    # bars.psv.gz: one line per bar of every list name's LONG window (the last 300 sessions): night | ticker | the
    # session's offset from the night (0 = D) | high | low | close | volume. The list path never reads the OPEN, and
    # reads VOLUME over the last 50 sessions only (`bv.VOL_WINDOW_50`, the 20-session dollar volume): the open is not
    # stored (the test's loader sets it to the close) and the volume is stored for the last VOL_KEEP sessions (0 before).
    pool_rows, exp_rows, bar_rows, meta, cals = [], [], [], [], {}
    for r in sorted(chosen, key=lambda r: r["ci"]):
        ci = r["ci"]
        rows, removed, pick, members, groups, live_members, summary = live_night(S, facts, rows_at, sic2, ci)
        chk = compare(ci, cap[cap.ci == ci], pool[pool.ci == ci], co, rows, removed, pick)
        assert chk["match"], chk
        ref = research_scores(cap[cap.ci == ci], co)
        pool_t = set(pool[pool.ci == ci].ticker)
        ctx = {t for v in removed.values() for t in v}
        cals[str(ci)] = [cal[k].isoformat() for k in range(ci - pm.HISTORY_SESSIONS + 1, ci + 1)]
        for m, g_ in zip(members, groups):
            pool_rows.append((ci, m["ticker"], repr(m["r21"]) if m["r21"] is not None else "", repr(m["r63"]),
                              repr(m["r126"]) if m["r126"] is not None else "", g_ or ""))
        by = {x["ticker"]: x for x in rows}
        for t in sorted(ref.index):
            long = pick["long"][t]
            n_long = len(long)
            b_all, c_all = runner.bars_for(S.D, S.D.tid[t])
            hi = int(np.searchsorted(c_all, ci)) + 1
            assert int(c_all[hi - 1]) == ci
            rel = (np.asarray(c_all[hi - n_long:hi], dtype=np.int64) - ci).tolist()
            for j in range(n_long):
                bar_rows.append((ci, t, rel[j], repr(float(long.h[j])), repr(float(long.l[j])), repr(float(long.c[j])),
                                 repr(float(long.v[j])) if j >= n_long - VOL_KEEP else ""))
            x = by.get(t)
            exp_rows.append((ci, cal[ci].isoformat(), t, repr(float(ref[t])), int(t in pool_t), int(t in ctx), n_long,
                             "" if x is None else x["rank_pick_model"]))
        meta.append({"ci": ci, "D": cal[ci].isoformat(), "E": cal[ci + 1].isoformat(), "list_rows": int(len(ref)), "pool3_rows": len(pool_t),
                     "context_removed": len(ctx), "pool_members": len(members)})
    kw = dict(sep="|", index=False, compression={"method": "gzip", "mtime": 0})
    pd.DataFrame(bar_rows, columns=["ci", "ticker", "rel", "h", "l", "c", "v"]).to_csv(os.path.join(FIXDIR, "bars.psv.gz"), **kw)
    pd.DataFrame(pool_rows, columns=["ci", "ticker", "r21", "r63", "r126", "sic2"]).to_csv(os.path.join(FIXDIR, "pool.psv.gz"), **kw)
    pd.DataFrame(exp_rows, columns=["ci", "D", "ticker", "research_score", "in_pool3", "context_removed", "n_long_bars", "live_rank_pick_model"]).to_csv(
        os.path.join(FIXDIR, "expected.tsv"), sep="\t", index=False)
    json.dump({"built_by": "scripts/probes/_717_pick_live_1114/01_parity.py fixture", "era": "A (list nights <= 2022-03-31; bars < 2022-07)",
               "seed": SEED, "tolerance": TOL, "history_sessions": bl.HISTORY_SESSIONS, "long_sessions": pm.HISTORY_SESSIONS, "vol_keep": VOL_KEEP,
               "selection": "nights where the live code reproduces the research exactly (see 01_check.out: 15 of 40 sampled nights; the rest "
                            "differ only through reused ticker symbols) — chosen for the most pool3 rows per list name, both sides of 2020-12-31",
               "nights": meta, "pool3_rows": sum(m["pool3_rows"] for m in meta), "list_rows": sum(m["list_rows"] for m in meta),
               "calendar": cals},
              open(os.path.join(FIXDIR, "meta.json"), "w"), indent=1)
    print("FIXTURE:", json.dumps(meta, indent=1))
    print(f"total pool3 rows {sum(m['pool3_rows'] for m in meta)}, list rows {sum(m['list_rows'] for m in meta)}; sizes: "
          + ", ".join(f"{f} {os.path.getsize(os.path.join(FIXDIR, f)) / 1e3:.0f} KB" for f in sorted(os.listdir(FIXDIR))))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("stage", choices=["check", "scan_test", "fixture"])
    ap.add_argument("--nights", type=int, default=40); ap.add_argument("--min-rows", type=int, default=220)
    ap.add_argument("--want", type=int, default=2); ap.add_argument("--tries", type=int, default=60); ap.add_argument("--min-pool", type=int, default=15)
    a = ap.parse_args()
    {"check": stage_check, "scan_test": stage_scan_test, "fixture": stage_fixture}[a.stage](a)
