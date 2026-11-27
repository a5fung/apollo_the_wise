"""R4 stage-1 list pass (blind). Calls the live chain: v1_replay.load_store / ticker_facts / night_members (the pinned copy of
scan_members), cb.cross_section_one_date, bv.v1_gates, bvl.rank_all. One v1_gates call per (night, pool member with rs>=35, listable,
86-session history). Captures every row with set(failed) <= CONTEXT_GATES (ok rows = the live list; ctx-only rows = the pick model's
extra population + the 11-13 bridge set), once, to apollo_data/cb702/r4_pool_era{A,B}.parquet.
usage: r4_pool.py A|B [--smoke N] [--workers W]"""
import sys, time, argparse
import numpy as np
import pandas as pd
from datetime import date
from multiprocessing import get_context
import r4_common as C
import v1_replay as R
from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import breakout_v1_list as bvl
from agents.market_intelligence import breakout_v1_pick_model as pm
from agents.market_intelligence import consolidation_breakout as cb
from scripts.probes._cb_backtest import runner

assert str(R.SCRATCH) == str(C.SCR), (R.SCRATCH, C.SCR)
G = {}
CTX = bv.CONTEXT_GATES
GATES = tuple(bv.GATES) + tuple(CTX)
COLS = ["ci", "ticker", "Di", "rs_best", "ctxmask", "ok", "has_e", "hE", "oE", "level", "level_src", "level5", "adr20", "close",
        "prior_move", "base_len", "depth_adr", "dollar_vol20", "vs_ema21_adr", "raw_close", "raw_src", "ll_bars", "ll_scored",
        "ret126_none", "sma50_nan", "rs_1m", "rs_3m", "rs_6m", "group_strength", "runup6m", "spread10_adr", "d52", "since_low",
        "bases_before", "order_score", "pick_score", "n_pool", "n_rows_night"]


def nz(x):
    return np.nan if x is None else float(x)


def nights_of(S, era):
    cal = S.D.cal
    E_FIRST, E_LAST = date(2017, 1, 3), date(2024, 12, 31)
    out = []
    for ci, d in enumerate(cal):
        if ci + 1 >= len(cal):
            continue
        e = cal[ci + 1]
        if era == "A":
            if d > date(2022, 3, 31) or e < E_FIRST:
                continue
        else:
            if d < date(2022, 4, 1) or e > E_LAST:
                continue
        assert e < C.SEAL
        out.append(ci)
    return out


def work(chunk):
    S, facts, rows_at, sic2 = G["S"], G["facts"], G["rows_at"], G["sic2"]
    D = S.D
    cache, rows = {}, []
    for ci in chunk:
        members, _ = R.night_members(S, facts, ci, rows_at)
        r21, r63, r126 = ([m[k] for m in members] for k in ("r21", "r63", "r126"))
        groups = [sic2.get(m["ticker"]) for m in members]
        rs_best, _, grp, _ = cb.cross_section_one_date(r21, r63, r126, groups)
        p21, p63, p126 = (cb.percentile_ranks(list(r)) for r in (r21, r63, r126))
        okrows, extras, tonight = [], [], []
        for j, (m, rb) in enumerate(zip(members, rs_best)):
            if rb is None or rb < bv.RS_MIN or not m["listable"] or not m["history"]:
                continue
            k = m["k"]
            if k not in cache:
                cache[k] = runner.bars_for(D, k)
            bars, cidx = cache[k]
            Di = m["i"] - facts[k]["a"]
            g = bv.v1_gates(bars, Di, rs_best=rb, raw_close=m["raw_close"], cidx=cidx)
            failed = set(g["failed"])
            if not failed <= set(CTX):
                continue
            oi = bv.order_inputs(bars, Di, g["adr20"])
            facts_pm = pm.base_facts(bars.h, bars.l, bars.c, Di)
            xs = {"rs_1m": p21[j], "rs_3m": p63[j], "rs_6m": p126[j], "group_strength": grp[j]}
            pin = pm.pick_inputs(g, oi, facts=facts_pm, xs=xs)
            has_e = Di + 1 < len(bars) and int(cidx[Di + 1]) == ci + 1
            hE, oE = (float(bars.h[Di + 1]), float(bars.o[Di + 1])) if has_e else (np.nan, np.nan)
            gg = g["gates"]
            llv = gg["lower_line"]["value"]
            f52 = facts_pm if facts_pm is not None else (None, None, None)
            ctxmask = sum(1 << i for i, kk in enumerate(CTX) if kk in failed)
            row = {"ci": ci, "ticker": m["ticker"], "Di": Di, "rs_best": float(rb), "ctxmask": ctxmask, "ok": bool(g["ok"]),
                   "has_e": bool(has_e), "hE": hE, "oE": oE, "level": nz(g["level"]),
                   "level_src": {"five_day": 0, "range": 1, "settled_after_wick": 2}[g["level_source"]], "level5": nz(g["level5"]),
                   "adr20": nz(g["adr20"]), "close": nz(g["close"]), "prior_move": nz(g["prior_move"]),
                   "base_len": nz(gg["prior_move"]["value"]["base_len"]), "depth_adr": nz(gg["base_depth"]["value"]["depth_adr"]),
                   "dollar_vol20": nz(gg["universe"]["value"]["dollar_vol20"]),
                   "vs_ema21_adr": nz(gg["ema21"]["value"]["vs_ema21_adr"]), "raw_close": float(m["raw_close"]),
                   "raw_src": int(S.raw_src[m["i"]]), "ll_bars": int(llv["bars"]), "ll_scored": llv["status"] == "scored",
                   "ret126_none": gg["downtrend_6m"]["value"]["ret126"] is None,
                   "sma50_nan": gg["sma50_falling_under"]["value"]["sma50"] is None,
                   "rs_1m": nz(p21[j]), "rs_3m": nz(p63[j]), "rs_6m": nz(p126[j]), "group_strength": nz(grp[j]),
                   "runup6m": nz(oi["runup6m"]), "spread10_adr": nz(oi["spread10_adr"]), "d52": nz(f52[0]),
                   "since_low": nz(f52[1]), "bases_before": nz(f52[2]), "order_score": np.nan, "pick_score": np.nan}
            tonight.append(row)
            if g["ok"]:
                okrows.append({"ticker": m["ticker"], "runup6m_adr": oi["runup6m_adr"], "spread10_adr": oi["spread10_adr"],
                               "pick_inputs": pin, "dollar_vol20": bv._f(gg["universe"]["value"]["dollar_vol20"]), "_row": row})
            else:
                extras.append(pin)
        if okrows:
            bvl.rank_all(okrows, extra_inputs=extras)
            for r in okrows:
                r["_row"]["order_score"] = nz(r.get("order_score"))
                r["_row"]["pick_score"] = nz(r.get("pick_score"))
        for row in tonight:
            row["n_pool"] = len(members)
            row["n_rows_night"] = len(tonight)
        rows.extend(tonight)
    return rows


def setup(era):
    S = R.load_store(era)
    assert S.D.cal[-1] < C.SEAL, S.D.cal[-1]
    t = time.time()
    facts = [R.ticker_facts(S, k) for k in range(len(S.D.tickers))]
    print(f"facts {time.time() - t:.0f}s", flush=True)
    D = S.D
    row_tid = np.repeat(np.arange(len(D.tickers), dtype=np.int64), (D.stop - D.start).astype(np.int64))
    order = np.argsort(D.ci, kind="stable")
    sic = pd.read_csv(C.SIC[era], sep="|", header=None, dtype=str, keep_default_na=False)
    sic2 = {t: s for t, s in ((t, cb.sic2(c)) for t, c in zip(sic[0], sic[3])) if s is not None}
    G.update(S=S, facts=facts, rows_at=R._RowsAt(order, D.ci[order], row_tid), sic2=sic2)
    return S


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("era")
    ap.add_argument("--smoke", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    C.assert_pins()
    S = setup(a.era)
    nights = nights_of(S, a.era)
    cal = S.D.cal
    print(f"era {a.era}: {len(nights)} nights {cal[nights[0]]} .. {cal[nights[-1]]}; bar store {S.name} last bar {cal[-1]}", flush=True)
    if a.smoke:
        nights = nights[len(nights) // 2: len(nights) // 2 + a.smoke]
    t = time.time()
    chunks = [nights[i::a.workers * 4] for i in range(a.workers * 4)]
    with get_context("fork").Pool(a.workers) as pool:
        parts = pool.map(work, chunks)
    df = pd.DataFrame([r for p in parts for r in p]).sort_values(["ci", "ticker"]).reset_index(drop=True)
    df["D"] = [cal[c].isoformat() for c in df.ci]
    df["E"] = [cal[c + 1].isoformat() for c in df.ci]
    print(f"rows {len(df):,}, ok {int(df.ok.sum()):,}, nights {df.ci.nunique()}, {time.time() - t:.0f}s", flush=True)
    if a.smoke:
        print(df.head(3).T)
        df.to_parquet(C.OUTD / f"smoke_{a.era}.parquet")
    else:
        assert df.D.max() < C.SEAL.isoformat()
        df.to_parquet(C.BIG / f"r4_pool_era{a.era}.parquet", index=False)
        (C.BIG / f"r4_pool_era{a.era}.cal.txt").write_text("\n".join(d.isoformat() for d in cal))
        print("written", flush=True)
