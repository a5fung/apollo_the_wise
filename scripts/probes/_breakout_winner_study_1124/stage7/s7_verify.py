#!/usr/bin/env python3
"""STAGE 7a recount - a second implementation of the captured check outcomes (pandas, DATE-based windows, no shared code with
s7_outcomes.py beyond file paths). Reads bars only for check tickers and only dates <= each era's last window end (<= 2024-12-31,
asserted); era B from the sealed copy only. Prints mismatch counts only - no outcome rate."""
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = Path("/Users/alvinfung/apollo_data")
PRE = DATA / "cb702_pre_v2"
SEALED = Path("/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/bws1124/pop/cb702_daily_lt2025.csv.gz")
REPO = HERE.parents[3]
CUT = "2024-12-31"
O = pd.read_csv(HERE / "check_outcomes.tsv.gz", sep="\t", keep_default_na=False, dtype={"ticker": str, "truncated": str})
assert O.E.max() <= CUT and len(O) == 6266
EV = pd.read_parquet(DATA / "cb702/bws1124_events_postdrop.parquet", columns=["era", "ci", "ticker", "level", "adr20", "oE", "hE", "lE", "E"])
X = O.merge(EV, on=["era", "ci", "ticker", "E"], how="left", validate="1:1")
bad = {k: 0 for k in ("big", "monster", "failed", "adr_tail", "big_untrunc", "big_e1", "clean", "nbars", "big_fromhigh", "qqq_above50")}
for era, fn, path in (("A", "bws1124_eraA_list_ctx.cal.txt", PRE / "daily_closes_all.csv.gz"), ("B", "bws1124_eraB_list_ctx.cal.txt", SEALED)):
    cal = [l.strip() for l in open(DATA / "cb702" / fn)]
    x = X[X.era == era]
    hi = cal[int(x.ci.max()) + 61]; lo = cal[int(x.ci.min()) - 60]
    assert hi <= CUT
    need = set(x.ticker) | {"QQQ"}
    parts = [ch[ch.t.isin(need) & (ch.d >= lo) & (ch.d <= hi)] for ch in pd.read_csv(path, header=None, names=["t", "d", "o", "h", "l", "c", "v"], dtype={"t": str, "d": str}, keep_default_na=False, chunksize=1_000_000)]
    B = pd.concat(parts)
    assert B.d.max() <= CUT
    if era == "A":
        rc = pd.concat([ch[ch.t.isin(need) & (ch.d >= lo) & (ch.d <= hi)] for ch in pd.read_csv(PRE / "daily_raw_close.csv.gz", header=None, names=["t", "d", "rc"], dtype={"t": str, "d": str}, keep_default_na=False, chunksize=2_000_000)])
        B = B.merge(rc, on=["t", "d"], how="left"); B["F"] = B.rc / B.c
        gt = pd.read_csv(PRE / "symbol_guard.tsv", sep="\t", dtype=str, keep_default_na=False)
        steps = None
    else:
        gt = pd.read_csv(REPO / "scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv", sep="\t", dtype=str, keep_default_na=False)
        sp = pd.read_csv(DATA / "cb702/cb702_splits.psv", sep="|", header=None, dtype=str, usecols=[0, 1], names=["t", "d"])
        sp = sp[sp.d <= CUT]
        steps = {t: set(g.d) for t, g in sp.groupby("t")}
    guard = {s: sorted(z.split(":")[0] for z in b.split(";") if z.split(":")[0] <= CUT) for s, b in zip(gt.symbol, gt.breaks) if b}
    G = {t: g.set_index("d").sort_index() for t, g in B.groupby("t")}
    q = G["QQQ"].c
    for r in x.itertuples(index=False):
        g = G[r.ticker]
        e_d, end_d = cal[int(r.ci) + 1], cal[int(r.ci) + 61]
        wdf = g.loc[e_d:end_d]
        full = wdf
        cut_at = None
        for gd in guard.get(r.ticker, []):
            if cal[int(r.ci) + 2] <= gd <= end_d:
                cut_at = gd; break
        if cut_at is not None:
            wdf = wdf[wdf.index < cut_at]
        prev = g[g.index < e_d].c.iloc[-1]
        cc = np.concatenate([[prev], wdf.c.to_numpy()])
        for p in range(1, len(wdf)):
            d = wdf.index[p]
            st = (d in steps.get(r.ticker, set())) if era == "B" else (abs(wdf.F.iloc[p] / wdf.F.iloc[p - 1] - 1) > 0.005 if np.isfinite(wdf.F.iloc[p]) and np.isfinite(wdf.F.iloc[p - 1]) else False)
            mv = cc[p + 1] / cc[p] - 1
            if st and (mv >= 0.7 or mv <= -0.5):
                wdf = wdf.iloc[:p]; break
        px = max(r.level, r.oE); mx = wdf.c.max()
        hit = wdf.c >= 1.5 * px
        clean = 0
        if hit.any():
            k = int(np.argmax(hit.to_numpy()))
            clean = int(k == 0 or (wdf.l.iloc[1:k + 1] >= r.lE).all())
        e1 = wdf.c.iloc[1:].max() if len(wdf) > 1 else np.nan
        qq = q[q.index <= r.D]
        got = dict(big=int(mx >= 1.5 * px), monster=int(mx >= 2 * px), failed=int(mx < 1.1 * px), adr_tail=int(mx >= px * (1 + 8 * r.adr20)),
                   big_untrunc=int(full.c.max() >= 1.5 * px), big_e1=int(np.isfinite(e1) and e1 >= 1.5 * px), clean=clean, nbars=len(wdf),
                   big_fromhigh=int(mx >= 1.5 * max(r.level, r.hE)), qqq_above50=int(qq.iloc[-1] > qq.iloc[-50:].mean()))
        for k_, v in got.items():
            bad[k_] += int(v != getattr(r, k_))
out = f"independent recount of {len(X)} check events: mismatches {bad} -> {'EQUAL' if not any(bad.values()) else 'DIFFERENT - STOP'}"
print(out)
(HERE / "7a_verify.txt").write_text(out + "\n")
assert not any(bad.values())
