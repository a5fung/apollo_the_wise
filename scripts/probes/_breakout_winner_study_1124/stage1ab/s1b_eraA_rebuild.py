"""Stage 1b: era-A list rebuild at the pinned sha (bridge set = set(failed) <= CONTEXT_GATES) + bridge to the 11-13 capture.
Reads only cb702_pre_v2 (bars 2016-01-04 .. 2022-06-30, asserted). Calls the live gates; re-codes nothing."""
import importlib.util, json, os, sys, time
from datetime import date
from multiprocessing import get_context
from common import *
assert_prereg()
import numpy as np, pandas as pd
import v1_replay as R                                   # own scratch folder set first (common.py)
spec = importlib.util.spec_from_file_location("p01", str(REPO / "scripts/probes/_717_precision_1112/01_precision.py"))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
bv, cb, runner, G = P.bv, P.cb, P.runner, P.G
B13 = importlib.util.spec_from_file_location("b13", str(REPO / "scripts/probes/_717_pick_model_1113/01_build.py"))
B = importlib.util.module_from_spec(B13); B13.loader.exec_module(B)       # base_facts, COLS (imported, never run)
OUTP = DATA / "cb702" / "bws1124_eraA_list_ctx.parquet"
CAP = DATA / "bv1_pick_model_1113" / "list_eraA_4pct.parquet"
COLS = B.COLS + ["failed", "fired_live"]
CTX = set(bv.CONTEXT_GATES)


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
            if not set(g["failed"]) <= CTX:                  # the live `context_only` test + the rows with no failed gate
                continue
            has_e = Di + 1 < len(bars) and int(cidx[Di + 1]) == ci + 1
            hE, lE, oE, vE = ((float(x[Di + 1]) for x in (bars.h, bars.l, bars.o, bars.v)) if has_e else (np.nan,) * 4)
            oi = bv.order_inputs(bars, Di, g["adr20"])
            gg = g["gates"]
            d52, since_low, nb = B.base_facts(bars.h, bars.l, bars.c, Di)
            nan = lambda x: np.nan if x is None else float(x)
            bt = bv.breakout_triggered({"h": hE, "v": vE}, g) if has_e else {"level_pass": False, "fired": False}
            rows.append((ci, m["ticker"], float(rb), has_e,
                         bool(bt["level_pass"]),            # the BREAK: high(E) > level (the bridge set's rows are not all `ok`)
                         g["level"], g["adr20"], g["close"], hE, lE, oE,
                         nan(p21[j]), nan(p63[j]), nan(p126[j]), g["prior_move"], nan(oi["runup6m"]), nan(oi["runup6m_adr"]),
                         gg["base_depth"]["value"]["depth_adr"], gg["prior_move"]["value"]["base_len"], nan(oi["spread10_adr"]),
                         gg["universe"]["value"]["dollar_vol20"], d52, gg["ema21"]["value"]["vs_ema21_adr"], since_low, nb,
                         nan(grp[j]), groups[j] is not None, Di + 1, ",".join(g["failed"]), bool(bt["fired"])))
    return rows


def main():
    assert bv.ADR_MIN == 0.04, bv.ADR_MIN
    S, nights = P.setup()
    assert S.D.cal[-1] < date(2022, 7, 1), S.D.cal[-1]       # era A bars end 2022-06-30; nothing sealed exists in this store
    sic = pd.read_csv(DATA / "cb702_pre_v2" / "cb702_sic.psv", sep="|", header=None, dtype=str, keep_default_na=False)
    G["sic2"] = {t: s for t, s in ((t, cb.sic2(c)) for t, c in zip(sic[0], sic[3])) if s is not None}
    t = time.time()
    chunks = [nights[i::8 * 4] for i in range(8 * 4)]
    with get_context("fork").Pool(8) as pool:
        parts = pool.map(work, chunks)
    df = pd.DataFrame([r for p in parts for r in p], columns=COLS).sort_values(["ci", "ticker"]).reset_index(drop=True)
    cal = S.D.cal
    assert not OUTP.exists(), "captured once"
    df.to_parquet(OUTP, index=False)
    (OUTP.with_suffix(".cal.txt")).write_text("\n".join(d.isoformat() for d in cal))
    print(f"build: {len(nights)} nights {cal[nights[0]]} .. {cal[nights[-1]]}, {len(df):,} bridge rows, {int(df.fire.sum()):,} fires in {time.time() - t:.0f}s -> {OUTP}", flush=True)


if __name__ == "__main__":
    main()
