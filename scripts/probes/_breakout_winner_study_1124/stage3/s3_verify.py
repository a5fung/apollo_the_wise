#!/usr/bin/env python3
"""STAGE 3 - independent recount of the captured discovery outcomes (a second implementation: pandas, DATE-based windows, no shared
code with s3_outcomes.py beyond the file paths). Reads era-A bars for discovery tickers dated <= ci(2020-12-31)+60 only (rows after
that are filtered inside each chunk and never kept), the event rows (level / open / low of E / ADR20), and the captured file."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = Path("/Users/alvinfung/apollo_data")
PRE = DATA / "cb702_pre_v2"
O = pd.read_csv(HERE / "discovery_outcomes.tsv.gz", sep="\t", keep_default_na=False, dtype={"ticker": str, "truncated": str})
assert O.E.max() <= "2020-12-31" and (O.era == "A").all()
cal = [l.strip() for l in open(DATA / "cb702/bws1124_eraA_list_ctx.cal.txt")]
cut = cal[cal.index("2020-12-31") + 60]
EV = pd.read_parquet(DATA / "cb702/bws1124_events_postdrop.parquet", columns=["era", "ci", "ticker", "level", "adr20", "oE", "hE", "lE", "E"])
EV = EV[(EV.era == "A") & (EV.E <= "2020-12-31")]
X = O.merge(EV, on=["era", "ci", "ticker", "E"], how="left", validate="1:1")
need = set(X.ticker)
parts = []
for ch in pd.read_csv(PRE / "daily_closes_all.csv.gz", header=None, names=["t", "d", "o", "h", "l", "c", "v"], dtype={"t": str, "d": str}, keep_default_na=False, chunksize=1_000_000):
    parts.append(ch[ch.t.isin(need) & (ch.d <= cut)][["t", "d", "l", "c"]])
B = pd.concat(parts)
parts = []
for ch in pd.read_csv(PRE / "daily_raw_close.csv.gz", header=None, names=["t", "d", "rc"], dtype={"t": str, "d": str}, keep_default_na=False, chunksize=2_000_000):
    parts.append(ch[ch.t.isin(need) & (ch.d <= cut)])
B = B.merge(pd.concat(parts), on=["t", "d"], how="left")
B["F"] = B.rc / B.c
G = {t: g.set_index("d").sort_index() for t, g in B.groupby("t")}
guard = {}
gt = pd.read_csv(PRE / "symbol_guard.tsv", sep="\t", dtype=str, keep_default_na=False)
for s, b in zip(gt.symbol, gt.breaks):
    if b and s in need:
        guard[s] = sorted(x.split(":")[0] for x in b.split(";"))
bad = {k: 0 for k in ("big", "monster", "failed", "adr_tail", "big_untrunc", "big_e1", "clean", "nbars", "big_fromhigh", "big_w30")}
ntr = 0
for r in X.itertuples(index=False):
    g = G[r.ticker]
    iE = int(r.ci) + 1
    assert cal[iE] == r.E

    def win(W, trunc=True):
        w = g.loc[r.E:cal[iE + W]]
        if trunc:
            gs = [x for x in guard.get(r.ticker, []) if r.E < x <= cal[iE + W]]
            if gs:
                w = w[w.index < gs[0]]
            cc, FF = w.c.to_numpy(), w.F.to_numpy()
            for p in range(1, len(w)):
                if abs(FF[p] / FF[p - 1] - 1) > 0.005 and (cc[p] / cc[p - 1] - 1 >= 0.70 or cc[p] / cc[p - 1] - 1 <= -0.50):
                    w = w.iloc[:p]; break
        return w
    w = win(60); wu = win(60, False); w3 = win(30)
    px = max(r.level, r.oE); mx = w.c.max()
    big = int(mx >= 1.5 * px)
    hit = np.flatnonzero(w.c.to_numpy() >= 1.5 * px)
    clean = int(big and (w.l.to_numpy()[1:hit[0] + 1] >= r.lE).all())
    mine = dict(big=big, monster=int(mx >= 2 * px), failed=int(mx < 1.10 * px), adr_tail=int(mx >= px * (1 + 8 * r.adr20)), big_untrunc=int(wu.c.max() >= 1.5 * px),
                big_e1=int(len(w) > 1 and w.c.iloc[1:].max() >= 1.5 * px), clean=clean, nbars=len(w), big_fromhigh=int(mx >= 1.5 * max(r.level, r.hE)), big_w30=int(w3.c.max() >= 1.5 * px))
    ntr += len(w) != len(wu)
    for k, v in mine.items():
        bad[k] += int(v != getattr(r, k))
ok = not any(bad.values()) and ntr == int((O.truncated != "").sum())
out = f"independent recount of {len(X)} discovery events (date-based windows, pandas parse; latest bar read {B.d.max()} <= {cut}): mismatches per column {bad}; truncated here {ntr} vs captured {int((O.truncated != '').sum())} -> {'EQUAL' if ok else 'DIFFERENT'}"
print(out)
(HERE / "3_verify.txt").write_text(out + "\n")
sys.exit(0 if ok else 3)
