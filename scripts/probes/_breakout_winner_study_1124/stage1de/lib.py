"""Shared build code for 1d (era B rebuild + overlap) and 1e. Calls the live gates at the pin; re-codes nothing.
Same row rule as 1b: bridge set = set(failed) <= CONTEXT_GATES. Reads bars <= D, plus E's open/high/low/volume for the break only."""
import importlib.util, time
from datetime import date
from multiprocessing import get_context
from common import *
assert_docs()
import numpy as np, pandas as pd
import v1_replay as R                                   # BEFORE 01_precision (its import resets BV1_SCRATCH; R already holds ours)
spec = importlib.util.spec_from_file_location("p01", str(REPO / "scripts/probes/_717_precision_1112/01_precision.py"))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
bv, cb, runner, G = P.bv, P.cb, P.runner, P.G
B13 = importlib.util.spec_from_file_location("b13", str(REPO / "scripts/probes/_717_pick_model_1113/01_build.py"))
B = importlib.util.module_from_spec(B13); B13.loader.exec_module(B)
CTX = set(bv.CONTEXT_GATES)
GATE_NAMES = ["history", "universe", "pinned", "adr", "rs", "prior_move", "base_depth", "ema21"] + list(bv.CONTEXT_GATES)
BASE_COLS = B.COLS + ["failed", "fired_live"]            # exactly 1b's columns
EXTRA_COLS = ["raw_close", "raw_src", "sectype", "ll_status", "ll_bars", "ret126_blank", "chg10_blank", "first_ci", "last_ci"] + ["gp_" + g for g in GATE_NAMES]
ALL_COLS = BASE_COLS + EXTRA_COLS
CUT_D = date(2025, 1, 1)


def setup_store(era):
    S = R.load_store(era); D = S.D
    assert D.cal[-1] < CUT_D, D.cal[-1]
    facts = [R.ticker_facts(S, k) for k in range(len(D.tickers))]
    row_tid = np.repeat(np.arange(len(D.tickers), dtype=np.int64), (D.stop - D.start).astype(np.int64))
    order = np.argsort(D.ci, kind="stable")
    sicp = (DATA / "cb702_pre_v2" / "cb702_sic.psv") if era == "A" else (DATA / "cb702" / "cb702_sic.psv")
    sic = pd.read_csv(sicp, sep="|", header=None, dtype=str, keep_default_na=False)
    sic2 = {t: s for t, s in ((t, cb.sic2(c)) for t, c in zip(sic[0], sic[3])) if s is not None}
    G.clear()
    G.update(S=S, facts=facts, rows_at=R._RowsAt(order, D.ci[order], row_tid), sic2=sic2, era=era)
    return S


def work(args):
    chunk, keep_all = args
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
            if not keep_all and not set(g["failed"]) <= CTX:
                continue
            has_e = Di + 1 < len(bars) and int(cidx[Di + 1]) == ci + 1
            hE, lE, oE, vE = ((float(x[Di + 1]) for x in (bars.h, bars.l, bars.o, bars.v)) if has_e else (np.nan,) * 4)
            oi = bv.order_inputs(bars, Di, g["adr20"])
            gg = g["gates"]
            d52, since_low, nb = B.base_facts(bars.h, bars.l, bars.c, Di)
            nan = lambda x: np.nan if x is None else float(x)
            bt = bv.breakout_triggered({"h": hE, "v": vE}, g) if has_e else {"level_pass": False, "fired": False}
            llv = gg["lower_line"]["value"]; dtv = gg["downtrend_6m"]["value"]
            a = facts[k]["a"]
            rows.append((ci, m["ticker"], float(rb), has_e, bool(bt["level_pass"]),
                         g["level"], g["adr20"], g["close"], hE, lE, oE,
                         nan(p21[j]), nan(p63[j]), nan(p126[j]), g["prior_move"], nan(oi["runup6m"]), nan(oi["runup6m_adr"]),
                         gg["base_depth"]["value"]["depth_adr"], gg["prior_move"]["value"]["base_len"], nan(oi["spread10_adr"]),
                         gg["universe"]["value"]["dollar_vol20"], d52, gg["ema21"]["value"]["vs_ema21_adr"], since_low, nb,
                         nan(grp[j]), groups[j] is not None, Di + 1, ",".join(g["failed"]), bool(bt["fired"]),
                         float(m["raw_close"]), int(S.raw_src[m["i"]]), m["st"], llv["status"], int(llv["bars"]),
                         dtv["ret126"] is None, dtv["s50_chg10_adr"] is None,
                         int(D.ci[a]), int(D.ci[facts[k]["b"] - 1])) + tuple(bool(gg[x]["pass"]) for x in GATE_NAMES))
    return rows


def run_nights(nights, keep_all, workers=8):
    chunks = [(nights[i::workers * 4], keep_all) for i in range(workers * 4)]
    with get_context("fork").Pool(workers) as pool:
        parts = pool.map(work, chunks)
    return pd.DataFrame([r for p in parts for r in p], columns=ALL_COLS).sort_values(["ci", "ticker"]).reset_index(drop=True)
