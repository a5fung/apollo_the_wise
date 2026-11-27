"""Stage 1b post-processing: bridge the rebuilt era-A rows to the 11-13 capture + the context gates' cut. Reads parquets only."""
import json
from datetime import date
from common import *
import numpy as np, pandas as pd
OUTP = DATA / "cb702" / "bws1124_eraA_list_ctx.parquet"
CAP = DATA / "bv1_pick_model_1113" / "list_eraA_4pct.parquet"
FX = REPO / "tests/fixtures/qm_breakout_scorecard"
CTX = ("sma50_falling_under", "downtrend_6m", "lower_line")
new = pd.read_parquet(OUTP); old = pd.read_parquet(CAP)
cal_new = (OUTP.with_suffix(".cal.txt")).read_text().split(); cal_old = (CAP.with_name(CAP.name + ".cal.txt")).read_text().split()
cal = [date.fromisoformat(s) for s in cal_new]
R = {"cal_equal": cal_new == cal_old}
L = []
def P(s=""):
    print(s); L.append(s)

def summarize(df, name):
    nights = sorted(df.ci.unique()); per = df.groupby("ci").agg(l=("ticker", "size"), f=("fire", "sum")).reindex(nights).fillna(0)
    return dict(name=name, nights=len(nights), rows=len(df), fires=int(df.fire.sum()), listed_median=float(per.l.median()), fires_median=float(per.f.median()),
                first=str(cal[nights[0]]), last=str(cal[nights[-1]]))

# QM buys fired (same join as 03_adr_floor.py): distinct scorecard buys with a fire row whose E is in [lo, hi]
def buys_fired(df):
    last_e = cal[int(df.ci.max()) + 1].isoformat()
    by_t, big_ids, n = {}, set(), 0
    b = pd.read_csv(FX / "buys.tsv", sep="\t", dtype=str, keep_default_na=False)
    w = pd.read_csv(FX / "buys_undated_widened.tsv", sep="\t", dtype=str, keep_default_na=False)
    for bid, t, lo, hi, big in [("d" + r.eid, r.ticker, r.E, r.E, r.big_winner == "1") for r in b.itertuples()] + \
                               [("w" + r.eid, r.ticker, r.lo, r.hi, False) for r in w.itertuples()]:
        if hi <= last_e:
            by_t.setdefault(t, []).append((bid, lo, hi)); n += 1
            if big: big_ids.add(bid)
    f = df[df.fire]
    hit = set()
    for t, ci in zip(f.ticker, f.ci):
        E = cal[ci + 1].isoformat()
        for bid, lo, hi in by_t.get(t, ()):
            if lo <= E <= hi: hit.add(bid)
    return len(hit), len(hit & big_ids), n, len(big_ids)

P("== 1b BRIDGE: rebuilt era A (HEAD, set(failed) <= CONTEXT_GATES) vs the 11-13 capture ==")
P(f"calendar file equal: {R['cal_equal']}")
sn, so = summarize(new, "rebuilt"), summarize(old, "11-13 capture")
for s in (so, sn): P(f"  {s['name']:14s} nights {s['nights']} {s['first']}..{s['last']}  rows {s['rows']:,}  fires(break rows) {s['fires']:,}  listed median {s['listed_median']:.0f}  fires median {s['fires_median']:.0f}")
bn, bo = buys_fired(new), buys_fired(old)
P(f"  QM buys on a break row: rebuilt {bn[0]} ({bn[1]} big) of {bn[2]} era-A buys; capture {bo[0]} ({bo[1]} big)  [expected 375 / 26]")
kn = new[["ci", "ticker"]].apply(tuple, axis=1); ko = old[["ci", "ticker"]].apply(tuple, axis=1)
sk_new, sk_old = set(kn), set(ko)
only_new, only_old = sk_new - sk_old, sk_old - sk_new
P(f"row keys (ci,ticker): in both {len(sk_new & sk_old):,}; only rebuilt {len(only_new):,}; only capture {len(only_old):,}; duplicate keys rebuilt {int(new.duplicated(['ci','ticker']).sum())} capture {int(old.duplicated(['ci','ticker']).sum())}")
m = new.merge(old, on=["ci", "ticker"], suffixes=("_n", "_o"))
cols = [c for c in old.columns if c not in ("ci", "ticker")]
diffs = {}
for c in cols:
    a, b = m[c + "_n"], m[c + "_o"]
    if a.dtype == bool or b.dtype == bool:
        d = (a.astype(bool) != b.astype(bool))
    else:
        a_, b_ = a.astype(float).to_numpy(), b.astype(float).to_numpy()
        d = ~((np.isnan(a_) & np.isnan(b_)) | np.isclose(a_, b_, rtol=1e-9, atol=1e-12, equal_nan=False))
        d = pd.Series(d, index=m.index)
    diffs[c] = int(d.sum())
P(f"column differences on the {len(m):,} shared rows (rtol 1e-9): " + (", ".join(f"{c}={n}" for c, n in diffs.items() if n) or "none"))
fire_flip = int((m.fire_n != m.fire_o).sum())
exact = (len(only_new) == 0 and len(only_old) == 0 and sum(diffs.values()) == 0 and sn["rows"] == so["rows"] and sn["fires"] == so["fires"] and bn[0] == bo[0])
R.update(exact=exact, only_new=len(only_new), only_old=len(only_old), shared=len(m), col_diffs=diffs, fire_flip=fire_flip,
         rebuilt=sn, capture=so, qm_rebuilt=bn, qm_capture=bo)
P(f"BRIDGE {'EXACT' if exact else 'NOT EXACT'}")
# diagnose any difference
if not exact:
    for nm, ks, df in (("only rebuilt", only_new, new), ("only capture", only_old, old)):
        if ks:
            x = df[[k in ks for k in zip(df.ci, df.ticker)]]
            P(f"  {nm}: {len(x)} rows; by year {x.ci.map(lambda c: cal[c + 1].year).value_counts().sort_index().to_dict()}")
            if "failed" in x: P(f"   failed-gate mix: {x.failed.value_counts().head(8).to_dict()}")
            P("   sample: " + "; ".join(f"{t} {cal[c]}" for c, t in list(ks)[:8]))
    for c, n in diffs.items():
        if n:
            a = m[c + "_n"].astype(float) if m[c + "_n"].dtype != bool else m[c + "_n"].astype(float); b = m[c + "_o"].astype(float)
            dd = m[(a != b) & ~(a.isna() & b.isna())]
            P(f"  diff {c}: {n} rows; first 5: " + "; ".join(f"{r.ticker} ci{r.ci} {getattr(r, c + '_n')} vs {getattr(r, c + '_o')}" for r in dd.head(5).itertuples()))

# ── the context gates' cut (HEAD's live list = failed == "" ; bridge set adds the rows only a context gate removes)
P("\n== THE CONTEXT GATES' CUT (HEAD live list = no failed gate; 11-13 list = bridge set) ==")
live = new[new.failed == ""]
assert int(live.fire.sum()) == int(new.fired_live.sum()) and bool((new.fired_live == (new.fire & (new.failed == ""))).all())
sl = summarize(live, "HEAD live list")
P(f"  11-13 list (bridge set): rows {sn['rows']:,}, break rows {sn['fires']:,}, listed median {sn['listed_median']:.0f}/night, break rows median {sn['fires_median']:.0f}/night")
P(f"  HEAD live list         : rows {sl['rows']:,}, break rows {sl['fires']:,}, listed median {sl['listed_median']:.0f}/night, break rows median {sl['fires_median']:.0f}/night")
P(f"  cut by the context gates: rows {sn['rows'] - sl['rows']:,} ({1 - sl['rows'] / sn['rows']:.1%}), break rows {sn['fires'] - sl['fires']:,} ({1 - sl['fires'] / sn['fires']:.1%})")
bl = buys_fired(live)
P(f"  QM buys on a break row: bridge set {bn[0]} -> HEAD live list {bl[0]} ({bl[1]} big of {bl[3]})")
cut = new[new.failed != ""]
for g in CTX:
    any_ = cut[cut.failed.str.contains(g)]
    only = cut[cut.failed == g]
    P(f"  gate {g:22s}: fails on {len(any_):,} rows ({int(any_.fire.sum()):,} break rows); alone {len(only):,} ({int(only.fire.sum()):,})")
P(f"  failed-set mix among cut rows: {cut.failed.value_counts().head(8).to_dict()}")
P("  per break-year (break rows: bridge set -> HEAD live): " + ", ".join(
    f"{y} {int(a)}->{int(b)}" for y, a, b in zip(
        sorted(set(new[new.fire].ci.map(lambda c: cal[c + 1].year))),
        [new[new.fire & (new.ci.map(lambda c: cal[c + 1].year) == y)].shape[0] for y in sorted(set(new[new.fire].ci.map(lambda c: cal[c + 1].year)))],
        [live[live.fire & (live.ci.map(lambda c: cal[c + 1].year) == y)].shape[0] for y in sorted(set(new[new.fire].ci.map(lambda c: cal[c + 1].year)))])))
R["live"] = sl; R["qm_live"] = bl; R["cut_rows"] = sn["rows"] - sl["rows"]; R["cut_break_rows"] = sn["fires"] - sl["fires"]
(HERE / "1b_bridge.txt").write_text("\n".join(L) + "\n")
(HERE / "1b_result.json").write_text(json.dumps(R, indent=1, default=str) + "\n")
