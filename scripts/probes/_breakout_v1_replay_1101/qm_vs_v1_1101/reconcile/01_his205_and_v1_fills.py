#!/usr/bin/env python3
"""Reconcile step 1 (2026-11-01): v1's gate vector on the night before EVERY one of Qullamaggie's 205 replayed buys,
plus entry facts for every v1 fill in the same window, so each "what v1 misses" pattern can be counted three ways:
his 28 big winners, his whole 205 (winners vs losers), and v1's own fills (winners vs losers).

Read-only, $0, local files, no network/DB. Store A only (pre_v2 daily, 2016-01-04..2022-06-30): nothing dated
2025-01-01 or later is read; every v1 frame is cut to E < 2025-01-01 and then to his window 2020-01-27..2022-06-14.
Recipe = build/01_build.py (the live `breakout_v1.v1_gates`, the night's strength cross-section), parity-checked
against the frozen list files (era A to 2022-03-31, era B from 2022-04-01).

Writes his205_nights.tsv and v1_fills_window.tsv here."""
import os, sys
from collections import Counter
import numpy as np, pandas as pd

HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101/qm_vs_v1_1101/reconcile"
SCR = "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/qmvs/reconcile"
os.environ["BV1_SCRATCH"] = SCR
PROBE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101"
sys.path.insert(0, PROBE); sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
import v1_replay as R  # noqa
from agents.market_intelligence import breakout_v1 as bv  # noqa
from agents.market_intelligence import consolidation_breakout as cb  # noqa
from scripts.probes._cb_backtest import runner  # noqa

QM = "/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024"
W_LO, W_HI = "2020-01-27", "2022-06-14"


def iso(d):
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


t = pd.read_csv(f"{QM}/replay/trades.tsv.gz", sep="\t")
w = t[(t.arm == "d3_p33_tspd") & (t.in_window == True) & (t.entry_status == "filled")].copy()
assert len(w) == 205, len(w)
ent = pd.read_csv(f"{QM}/entries.tsv", sep="\t").set_index("eid")
for c in ("pivot", "adr20", "q1_2022_hole", "sym"):
    w["e_" + c] = w.eid.map(ent[c])

l98 = pd.concat([pd.read_csv(f"{PROBE}/out/list_era{e}.tsv.gz", sep="\t", dtype={"ticker": str}) for e in "AB"])
l90 = pd.concat([pd.read_csv(f"{PROBE}/template_grid_1101/list90/list_era{e}.tsv.gz", sep="\t", dtype={"ticker": str}) for e in "AB"])
l98 = l98[l98.scan_date < "2025-01-01"]; l90 = l90[l90.scan_date < "2025-01-01"]
in98 = set(zip(l98.ticker, l98.scan_date)); in90 = set(zip(l90.ticker, l90.scan_date))

S = R.load_store("A"); D = S.D; cal = D.cal; cal_iso = [iso(d) for d in cal]; pos = {d: i for i, d in enumerate(cal_iso)}
facts = [R.ticker_facts(S, k) for k in range(len(D.tickers))]
row_tid = np.repeat(np.arange(len(D.tickers), dtype=np.int64), (D.stop - D.start).astype(np.int64))
order = np.argsort(D.ci, kind="stable")
rows_at = R._RowsAt(order, D.ci[order], row_tid)
cache = {}


def bars_of(tk):
    k = D.tid[tk]
    if k not in cache:
        b, ci = runner.bars_for(D, k)
        cache[k] = (b, np.asarray(ci, dtype=np.int64))
    return cache[k]


def bar_i(tk, d_iso):
    b, ci = bars_of(tk)
    j = np.where(ci == pos[d_iso])[0]
    return int(j[0]) if j.size else None


rs_night = {}


def rs_of(d_iso, tk):
    if d_iso not in rs_night:
        members, _ = R.night_members(S, facts, pos[d_iso], rows_at)
        rb, _, _, _ = cb.cross_section_one_date([m["r21"] for m in members], [m["r63"] for m in members],
                                                [m["r126"] for m in members], [None] * len(members))
        rs_night[d_iso] = {m["ticker"]: x for m, x in zip(members, rb)}
    return rs_night[d_iso].get(tk)


def night_facts(tk, e_iso):
    """v1 gates on night D (the session before E) + E-day facts from the daily bars."""
    out = {}
    if tk not in D.tid or e_iso not in pos:
        out["note"] = "not_in_store"; return out
    ie = bar_i(tk, e_iso)
    d_iso = cal_iso[pos[e_iso] - 1]
    li = bar_i(tk, d_iso)
    if ie is None or li is None or ie != li + 1:
        out["note"] = "no_bar_or_hole"; return out
    b, cidx = bars_of(tk)
    f = facts[D.tid[tk]]
    rb = rs_of(d_iso, tk)
    g = bv.v1_gates(b, li, rs_best=rb, raw_close=float(f["raw"][li]), cidx=cidx)
    adm, _ = bv.security_admitted(tk, S.types.get(tk), S.etv_names.get(tk))
    failed = list(g["failed"])
    out.update(D=d_iso, rs_best=rb, failed=",".join(failed), first_failed=failed[0] if failed else "",
               ok98=int(g["ok"] and adm), in98=int((tk, d_iso) in in98), in90=int((tk, d_iso) in in90),
               ok90=int(adm and rb is not None and rb >= 90 and all(x == "rs" for x in failed)))
    if g["gates"]["history"]["pass"]:
        G = g["gates"]
        h, l, c, v = b.h, b.l, b.c, b.v
        adr = g["adr20"]
        rngD = (h[li] - l[li]) / c[li]
        out.update(level=g["level"], v50=g["vol50"], vol_x_E=float(v[ie]) / g["vol50"] if g["vol50"] else np.nan,
                   adr20=adr, rangeD_adr=rngD / adr if adr else np.nan,
                   upD=float(c[li] / c[li - 1] - 1), hiD=float(h[li]),
                   level_vs_hiD=float(g["level"] / h[li] - 1),
                   wide_up_D=int(adr is not None and rngD > adr and c[li] > c[li - 1] and c[li] >= l[li] + 0.5 * (h[li] - l[li])),
                   tight=G["tightening"]["value"]["ratio"], surf=G["surf"]["value"]["best"],
                   base_len=G["prior_move"]["value"]["base_len"], prior_move=g["prior_move"],
                   hl=int(G["higher_lows"]["pass"]), surf_ok=int(G["surf"]["pass"]), tight_ok=int(G["tightening"]["pass"]),
                   brk_ok=int(G["breakdown"]["pass"]), pm_ok=int(G["prior_move"]["pass"]), uni_ok=int(G["universe"]["pass"]),
                   hi126_gap=float(c[li] / h[max(0, li - 125):li + 1].max() - 1))
    return out


# ---- his 205
rows = []
for r in w.itertuples():
    nf = night_facts(r.ticker, r.E)
    rec = {"eid": r.eid, "ticker": r.ticker, "E": r.E, "setup": r.setup, "era": r.era, "q1_2022_hole": r.e_q1_2022_hole,
           "R": r.realized_r, "fill": r.fill, "stop": r.stop, "pivot": r.e_pivot,
           "stop_pct": (r.fill - r.stop) / r.fill}
    rec.update(nf)
    if "level" in nf and r.e_pivot == r.e_pivot:
        rec["level_vs_pivot"] = nf["level"] / r.e_pivot - 1
        rec["fill_vs_level"] = r.fill / nf["level"] - 1
    rows.append(rec)
h = pd.DataFrame(rows)
par = Counter()
for x in h.itertuples():
    if isinstance(getattr(x, "D", None), str):
        par[("98", x.ok98, x.in98)] += 1; par[("90", x.ok90, x.in90)] += 1
print("his205 nights evaluated", int(h.D.notna().sum()), "notes", h.note.value_counts(dropna=True).to_dict() if "note" in h else {})
print("parity (list, my call, in file)", dict(par))
h.to_csv(f"{HERE}/his205_nights.tsv", sep="\t", index=False, float_format="%.6g")

# ---- v1 fills in his window (guard book = one position per stock, every listed day walked, no slot limit)
tr = pd.read_csv(f"{PROBE}/out/trades.tsv.gz", sep="\t", low_memory=False)
tr = tr[(tr.E < "2025-01-01") & (tr.E >= W_LO) & (tr.E <= W_HI) & (tr.filled == True)]
tr = tr[(tr.adm_guard == True) & (tr.mature == True)]
gr = pd.read_csv(f"{PROBE}/template_grid_1101/out/trades_grid.tsv.gz", sep="\t")
gr = gr[gr.E < "2025-01-01"]
gC = gr[gr.rule == "C"].set_index("key")
vrows = []
for r in tr.itertuples():
    nf = night_facts(r.ticker, r.E)
    rec = {"key": r.key, "ticker": r.ticker, "E": r.E, "R_A": r.r_2c, "exit_kind": r.exit_kind, "events": r.events,
           "fill": r.fill, "stop": r.stop, "list_level": r.level, "adm_cap": r.adm_cap,
           "R_C": float(gC.loc[r.key].r_2c) if r.key in gC.index else np.nan}
    rec.update({k: v for k, v in nf.items() if k in ("D", "rs_best", "vol_x_E", "adr20", "rangeD_adr", "upD", "hiD",
                                                    "level_vs_hiD", "wide_up_D", "level", "note", "in98", "base_len")})
    if "level" in nf:
        rec["fill_vs_level"] = r.fill / nf["level"] - 1
        rec["fill_vs_hiD"] = r.fill / nf["hiD"] - 1
    ev = str(r.events)
    rec["third_then_cost_day0"] = int('[0, "partial_r"' in ev and '"day0_stop"' in ev and '[0, "day0_stop"' in ev)
    vrows.append(rec)
v = pd.DataFrame(vrows)
print("v1 fills in window (guard book, mature):", len(v), "in98 parity", v.in98.value_counts(dropna=False).to_dict())
v.to_csv(f"{HERE}/v1_fills_window.tsv", sep="\t", index=False, float_format="%.6g")
