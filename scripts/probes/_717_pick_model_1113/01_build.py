#!/usr/bin/env python3
"""#717 pick model — the CAPTURE (2026-11-13; offline, $0, read-only, ERA A ONLY; registration:
docs/analysis/cb_pick_model_2026-11-13.md §1/§3). One row per LIST name per watch night under the LIVE rules
(`breakout_v1.v1_gates`, ADR floor 4%), the pool and strength rank exactly as `_717_precision_1112/02_picks.py`, plus
the registered features — every one from bars <= D except oE/hE/lE (the day-E open/high/low: hE/lE only decide the
fire and the too-wide skip, never a feature). No Qullamaggie label is read here.

THE SEAL: bars = cb702_pre_v2 (2016-01-04 .. 2022-06-30; `P.setup()` asserts < 2025). `cb702/` is NOT opened.
`cb702_pre_v2/cb702_sic.psv` (industry codes, a 2026-10-16 snapshot, no prices) gives the SIC 2-digit group.

    python3 scripts/probes/_717_pick_model_1113/01_build.py [--workers 8]
"""
import argparse, importlib.util, os, time
from multiprocessing import get_context

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("p01", os.path.join(HERE, "..", "_717_precision_1112", "01_precision.py"))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
bv, cb, R, runner, G = P.bv, P.cb, P.R, P.runner, P.G
CAPTURE = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"   # captured ONCE, outside git
SIC = "/Users/alvinfung/apollo_data/cb702_pre_v2/cb702_sic.psv"
YEAR = 252
COLS = ["ci", "ticker", "rs_best", "has_e", "fire", "level", "adr20", "close", "hE", "lE", "oE",
        "rs_1m", "rs_3m", "rs_6m", "prior_move", "runup6m", "runup6m_adr", "depth_adr", "base_len", "spread10_adr",
        "dollar_vol20", "dist_52w", "vs_ema21_adr", "since_low", "bases_before", "group_strength", "has_sic", "bars_to_d"]


def base_facts(h, l, c, Di):
    """(close / the 252-session high, sessions since the major low, completed earlier bases since it) — bars <= Di."""
    a = max(0, Di - YEAR + 1)
    hw, lw = np.asarray(h[a:Di + 1], float), np.asarray(l[a:Di + 1], float)
    k = int(np.nanargmin(lw))
    hh = hw[k:]
    cm = np.maximum.accumulate(hh)
    idx = np.flatnonzero(np.r_[True, hh[1:] > cm[:-1]])          # "new high since the major low" days
    return float(c[Di] / np.nanmax(hw)), int(len(lw) - 1 - k), int((np.diff(idx) >= bv.BASE_MIN).sum())


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
        for j, (m, rb) in enumerate(zip(members, rs_best)):
            if rb is None or rb < bv.RS_MIN or not m["listable"] or not m["history"]:
                continue
            k = m["k"]
            if k not in cache:
                cache[k] = runner.bars_for(D, k)
            bars, cidx = cache[k]
            Di = m["i"] - facts[k]["a"]
            g = bv.v1_gates(bars, Di, rs_best=rb, raw_close=m["raw_close"], cidx=cidx)
            if not g["ok"]:
                continue
            has_e = Di + 1 < len(bars) and int(cidx[Di + 1]) == ci + 1
            hE, lE, oE, vE = ((float(x[Di + 1]) for x in (bars.h, bars.l, bars.o, bars.v)) if has_e else (np.nan,) * 4)
            oi = bv.order_inputs(bars, Di, g["adr20"])
            gg = g["gates"]
            d52, since_low, nb = base_facts(bars.h, bars.l, bars.c, Di)
            nan = lambda x: np.nan if x is None else float(x)
            rows.append((ci, m["ticker"], float(rb), has_e,
                         bool(has_e and bv.breakout_triggered({"h": hE, "v": vE}, g)["fired"]),
                         g["level"], g["adr20"], g["close"], hE, lE, oE,
                         nan(p21[j]), nan(p63[j]), nan(p126[j]), g["prior_move"], nan(oi["runup6m"]), nan(oi["runup6m_adr"]),
                         gg["base_depth"]["value"]["depth_adr"], gg["prior_move"]["value"]["base_len"], nan(oi["spread10_adr"]),
                         gg["universe"]["value"]["dollar_vol20"], d52, gg["ema21"]["value"]["vs_ema21_adr"], since_low, nb,
                         nan(grp[j]), groups[j] is not None, Di + 1))
    return rows


def main(a):
    assert not os.path.exists(CAPTURE), "captured once — delete by hand to rebuild"
    assert bv.ADR_MIN == 0.04, bv.ADR_MIN
    S, nights = P.setup()
    sic = pd.read_csv(SIC, sep="|", header=None, dtype=str, keep_default_na=False)
    G["sic2"] = {t: s for t, s in ((t, cb.sic2(c)) for t, c in zip(sic[0], sic[3])) if s is not None}
    t = time.time()
    chunks = [nights[i::a.workers * 4] for i in range(a.workers * 4)]
    with get_context("fork").Pool(a.workers) as pool:
        parts = pool.map(work, chunks)
    df = pd.DataFrame([r for p in parts for r in p], columns=COLS).sort_values(["ci", "ticker"])
    df.to_parquet(CAPTURE, index=False)
    cal = S.D.cal
    with open(CAPTURE + ".cal.txt", "w") as fh:
        fh.write("\n".join(d.isoformat() for d in cal))
    print(f"build: {len(nights)} nights {cal[nights[0]]} .. {cal[nights[-1]]}, {len(df):,} list rows, {int(df.fire.sum()):,} fires, "
          f"{len(G['sic2'])} tickers with an industry code, in {time.time() - t:.0f}s -> {CAPTURE}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=8)
    main(ap.parse_args())
