#!/usr/bin/env python3
"""Qullamaggie's 269 dated breakout buys (holdings_1024/entries.tsv, setup in {breakout, both}, 2017-2023) vs breakout v1's
list rules on the night before each buy (D). His trades ARE the setup: every v1 rule that keeps one of them off the list is a
detector defect. Per-gate miss table (any fail, and the ONLY failing gate), plus listed-on-D and listed-in-D-4..D.
Read-only, $0, local stores, nothing dated 2025+ (era B = the sealed < 2025 copy). Recipe = qm_vs_v1_1101/build/01_build.py."""
import os, sys
from collections import Counter
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("BV1_SCRATCH", "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/qmbo1102")
PROBE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_v1_replay_1101"
sys.path.insert(0, PROBE); sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
import v1_replay as R  # noqa
from agents.market_intelligence import breakout_v1 as bv  # noqa
from agents.market_intelligence import consolidation_breakout as cb  # noqa
from scripts.probes._cb_backtest import runner  # noqa

QM = "/Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024"
ent = pd.read_csv(f"{QM}/entries.tsv", sep="\t")
buys = ent[ent.setup.isin(["breakout", "both"])].copy()
assert len(buys) == 269, len(buys)
out, LOG = [], []
def log(s): print(s, flush=True); LOG.append(str(s))

for era in ("A", "B"):
    sub = buys[buys.era == era]
    S = R.load_store(era); D = S.D
    cal_iso = [d.isoformat() for d in D.cal]; pos = {d: i for i, d in enumerate(cal_iso)}
    facts = {}
    row_tid = np.repeat(np.arange(len(D.tickers), dtype=np.int64), (D.stop - D.start).astype(np.int64))
    order = np.argsort(D.ci, kind="stable")
    rows_at = R._RowsAt(order, D.ci[order], row_tid)
    allfacts = [R.ticker_facts(S, k) for k in range(len(D.tickers))]
    rs_cache = {}
    for r in sub.itertuples():
        tk = r.sym_a if isinstance(r.sym_a, str) and r.sym_a in D.tid else r.sym
        rec = {"eid": r.eid, "sym": r.sym, "ticker": tk, "E": r.E, "era": era}
        if tk not in D.tid or r.E not in pos:
            rec["note"] = "not_in_store"; out.append(rec); continue
        k = D.tid[tk]
        b, ci = runner.bars_for(D, k); ci = np.asarray(ci, dtype=np.int64)
        for lag in range(0, 5):                        # nights D-lag, D = the session before E
            cn = pos[r.E] - 1 - lag
            j = np.where(ci == cn)[0]
            if not j.size:
                continue
            li = int(j[0])
            if cn not in rs_cache:
                members, _ = R.night_members(S, allfacts, cn, rows_at)
                rsb, _, _, _ = cb.cross_section_one_date([m["r21"] for m in members], [m["r63"] for m in members],
                                                         [m["r126"] for m in members], [None] * len(members))
                rs_cache[cn] = {m["ticker"]: x for m, x in zip(members, rsb)}
            rb = rs_cache[cn].get(tk)
            f = allfacts[k]
            adm, why = bv.security_admitted(tk, S.types.get(tk), S.etv_names.get(tk))
            g = bv.v1_gates(b, li, rs_best=rb, raw_close=float(f["raw"][li]), cidx=ci)
            failed = list(g["failed"]) + ([] if adm else ["security_type"])
            if lag == 0:
                G = g["gates"]
                rec.update(D=cal_iso[cn], rs_best=rb, listed_D=int(not failed), failed=",".join(failed),
                           adr20=g.get("adr20"), prior_move=g.get("prior_move"), pole_date=g.get("pole_date"),
                           level=g.get("level"), raw_close=float(f["raw"][li]))
                for name in bv.GATES:
                    if name in G:
                        rec["v_" + name] = str(G[name].get("value"))[:160]
            if not failed:
                rec["listed_within_5"] = 1
        rec.setdefault("listed_within_5", 0)
        out.append(rec)
    del S, D, allfacts

df = pd.DataFrame(out)
df.to_csv(f"{HERE}/qm_breakouts_v1_gates.tsv.gz", sep="\t", index=False)
ok = df[df.get("note").isna()] if "note" in df else df
log(f"Qullamaggie's dated breakout buys: {len(df)}; in the stores {len(ok)}; not in store {len(df) - len(ok)}")
log(f"on v1's list the night before (D): {int(ok.listed_D.sum())} ({ok.listed_D.mean():.0%}); within the 5 nights before: {int(ok.listed_within_5.sum())} ({ok.listed_within_5.mean():.0%})")
anyf, onlyf = Counter(), Counter()
for fs in ok.failed.fillna(""):
    xs = [x for x in fs.split(",") if x]
    for x in xs: anyf[x] += 1
    if len(xs) == 1: onlyf[xs[0]] += 1
log("\nrule | his buys it blocks (any) | his buys blocked by this rule ALONE")
for name in list(bv.GATES) + ["security_type"]:
    log(f"  {name:14s} {anyf.get(name, 0):4d} ({anyf.get(name, 0) / len(ok):.0%})   alone {onlyf.get(name, 0):4d}")
nf = Counter(len([x for x in fs.split(',') if x]) for fs in ok.failed.fillna(""))
log(f"\nnumber of rules failing per buy: {dict(sorted(nf.items()))}")
open(f"{HERE}/01_gate_misses.txt", "w").write("\n".join(LOG) + "\n")
