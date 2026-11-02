#!/usr/bin/env python3
"""Stage 0 checks 2 and 3 (+ the parity that makes them trustworthy). Reads s0_rowfeat.parquet (s0_features.py).
PARITY first: the re-implemented list must reproduce 18_sma50_rule.txt; the era-A bar features must equal the parent's
cached parquets; the era-A buy test and order score must reproduce 36_trigger_vol10.txt and 33_rank_topn.txt.
CHECK 2: the same measures on era B (nights 2022-04-01 .. 2024-12-30, the sealed < 2025 store), then 2017-2024 combined.
CHECK 3: each day's names firing the daily buy test (NEW volume bar), ranked by 33's order score computed over the night's
whole list; Qullamaggie's buys that fire and sit in their day's top 5 / top 10. No returns read."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import s0_lib as L  # noqa
LOG = []
def say(s=""): print(s, flush=True); LOG.append(str(s))

g = L.load()
F, Q, NEW, eraB = g["F"], g["Q"], g["NEW"], g["eraB"]
eraA = ~eraB
RF = pd.read_parquet(f"{HERE}/s0_rowfeat.parquet")
assert RF.index.is_unique and set(RF.index) == set(F.index[NEW])
X = RF.reindex(F.index)
say("=" * 100)
say("PARITY (stage 0 re-implementation vs the parent folder's printed numbers)")
n = NEW.groupby(F.scan_date).sum(); kept = NEW.loc[Q.row].values
say(f"  list (rules 1-7): Qullamaggie's buys on the list {int(kept.sum())}/269 | big winners {int(kept[Q.big.values].sum())}/{int(Q.big.sum())} | "
    f"names a night median {n.median():.0f} mean {n.mean():.0f} p90 {n.quantile(.9):.0f}   [18_sma50_rule.txt PLAIN LINE: 263/269, 26/26, 249/330/609]")
say(f"  thresholds: base depth {g['th']['LRN']:.4f}..{g['th']['depth_hi']:.4f} daily ranges, run-up >= {g['th']['prior_move']:.4f}, "
    f"close vs EMA21 >= {g['th']['vs21']:.4f} daily ranges, close >= 50-day SMA")
mv = pd.read_parquet(f"{L.OUTDIR}/move126_eraA.parquet").set_index("idx").move126
tt = pd.read_parquet(f"{L.OUTDIR}/tight_recent_eraA.parquet").set_index("idx").c10
tv = pd.read_parquet(f"{L.OUTDIR}/trigger_v10_eraA.parquet").set_index("idx")
ia = RF.index[RF.era == "A"]
def maxdiff(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    both = np.isfinite(a) & np.isfinite(b)
    return float(np.nanmax(np.abs(a[both] - b[both]))) if both.any() else 0.0, int((np.isfinite(a) != np.isfinite(b)).sum())
say(f"  era-A bar features vs the parent's caches on {len(ia):,} list rows: move126 max diff {maxdiff(RF.move126[ia], mv.reindex(ia))}, "
    f"c10 {maxdiff(RF.c10[ia], tt.reindex(ia))}, x10 {maxdiff(RF.x10[ia], tv.x10.reindex(ia))}, x50 {maxdiff(RF.x50[ia], tv.x50.reindex(ia))} "
    f"(max |diff|, NaN-pattern mismatches); up equal {bool((RF.up[ia].values == tv.up.reindex(ia).values).all())}, "
    f"E_bar equal {bool((RF.E_bar[ia].fillna('none').values == tv.E_bar.reindex(ia).fillna('none').values).all())}; cache rows = list rows {len(tv) == len(ia)}")

hole_ok = (X.E_bar == F.E)                                      # a hole after D is not a trigger (34/36)
FIRE = {"OLD": NEW & hole_ok & X.up.fillna(False).astype(bool) & (X.x50 >= 1.2),
        "NEW": NEW & hole_ok & X.up.fillna(False).astype(bool) & (X.x10 >= 1.2)}
nights = {"A": F.scan_date[eraA].unique(), "B": F.scan_date[eraB].unique(), "all": F.scan_date.unique()}
emask = {"A": eraA, "B": eraB, "all": pd.Series(True, index=F.index)}
qmask = {"A": Q.D < L.ERA_B_D_FIRST, "B": Q.D >= L.ERA_B_D_FIRST, "all": pd.Series(True, index=Q.index)}
def per_night(m, era):
    return m[emask[era]].groupby(F.scan_date[emask[era]]).sum().reindex(nights[era], fill_value=0)

# the order score (33): percentiles over the night's whole list
CUR = NEW & X.move126.notna()
A = F[CUR].assign(mr=lambda x: X.move126[x.index] / x.adr20, c10=lambda x: X.c10[x.index])
A["p_run"] = A.groupby("scan_date").mr.rank(pct=True)
A["p_tight"] = A.groupby("scan_date").c10.rank(pct=True, ascending=False)
A["score"] = (A.p_run + A.p_tight) / 2
A["rank_list"] = A.score.groupby(A.scan_date).rank(ascending=False, method="first")
Lb = L.labels(F, Q)

def order_line(era):
    s = A.score[emask[era].reindex(A.index).values]
    rk = A.rank_list.reindex(s.index)
    yy, nn = [i for i in Lb[Lb.yes].i if i in s.index], [i for i in Lb[~Lb.yes].i if i in s.index]
    auc = np.mean([[1.0 if s[u] > s[v] else (0.5 if s[u] == s[v] else 0.0) for v in nn] for u in yy]) if yy and nn else float("nan")
    q = Q[qmask[era].values & NEW.loc[Q.row].values]
    qr = rk.reindex(q.row).dropna(); br = rk.reindex(q.row[q.big]).dropna()
    return (f"his yes above his no {auc:.2f} (yes {len(yy)}, no {len(nn)} on the list) | Qullamaggie's buys in their night's top 10: {int((qr <= 10).sum())}, "
            f"top 20: {int((qr <= 20).sum())}, top 30: {int((qr <= 30).sum())}, top 50: {int((qr <= 50).sum())} of {len(qr)} | "
            f"big winners top 20: {int((br <= 20).sum())}, top 50: {int((br <= 50).sum())} of {len(br)}")

def buy_line(era, name):
    m = FIRE[name]; per = per_night(m, era)
    q = Q[qmask[era].values & NEW.loc[Q.row].values]
    hit = m.loc[q.row].values
    return per, q, hit, (f"breakouts a day: median {per.median():.0f}, mean {per.mean():.1f}, 90th pct {per.quantile(.9):.0f} | "
                         f"Qullamaggie's buys firing on his day {int(hit.sum())}/{len(q)} | big {int(hit[q.big.values].sum())}/{int(q.big.sum())}")

say(f"  era-A buy test, volume >= 1.2x the 50-day (OLD): {buy_line('A', 'OLD')[3]}   [36: median 20, mean 31.2 | 116/245 | 15/26]")
say(f"  era-A buy test, volume >= 1.2x the last 10 days (NEW): {buy_line('A', 'NEW')[3]}   [36: median 24, mean 38.1 | 145/245 | 21/26]")
say(f"  era-A order score: {order_line('A')}   [33: 0.70 (48, 35) | 30, 48, 61, 88 of 245 | 6, 8 of 26]")
say(f"  era-A list median {per_night(NEW, 'A').median():.0f} names a night   [33: 221]")

say("\n" + "=" * 100)
say("CHECK 2 — 2022-2024 (era B: nights 2022-04-01 .. 2024-12-30, the sealed < 2025 store), then 2017-2024 combined")
for era, title in (("A", "era A (nights 2016-12-30 .. 2022-03-31)"), ("B", "era B (nights 2022-04-01 .. 2024-12-30)"),
                   ("all", "COMBINED 2017-2024")):
    lst = per_night(NEW, era)
    q = Q[qmask[era].values]
    onl = NEW.loc[q.row].values
    say(f"\n{title}: {len(nights[era])} nights")
    say(f"  list: names a night median {lst.median():.0f}, mean {lst.mean():.0f}, 90th pct {lst.quantile(.9):.0f} | "
        f"Qullamaggie's buys on the list {int(onl.sum())}/{len(q)} | big winners on the list {int(onl[q.big.values].sum())}/{int(q.big.sum())}")
    for name, lab in (("NEW", "volume >= 1.2x the last 10 days (his ruling)"), ("OLD", "volume >= 1.2x the 50-day (v1 today)")):
        per, qq, hit, line = buy_line(era, name)
        say(f"  buy test {lab}: {line} | days with more than 5 firing {int((per > 5).sum())} ({(per > 5).mean():.0%}), with 0: {int((per == 0).sum())}")
    say(f"  order score: {order_line(era)}" + ("  (none of his 95 labels is an era-B night)" if era == "B" else ""))

k0 = int((pd.Series(nights["A"]) >= "2021-09-27").sum())          # store B's sessions before its first night (its bars start 2021-09-27)
nb = sorted(nights["B"]); short = [d for j, d in enumerate(nb) if k0 + j < 126 + 63]
say(f"\n  era-B history note: the sealed era-B store starts 2021-09-27 ({k0} sessions before the first era-B night), so the 6-month move "
    f"(126 sessions, each high against the lowest low of the 64 sessions before it) has a shortened low look-back on the first {len(short)} era-B nights "
    f"(to {short[-1] if short else '-'}); the 10-close spread and the 10/50-session volume averages are complete")
say("\n  era-B buys one by one (D >= 2022-04-01):")
qb = Q[qmask["B"].values]
for r in qb.sort_values("E").itertuples():
    i = r.row
    say(f"    {r.sym:5s} buy {r.E}  on list {'yes' if NEW[i] else 'NO '} | fires NEW {'yes' if FIRE['NEW'][i] else 'no '} OLD {'yes' if FIRE['OLD'][i] else 'no '} | "
        f"high vs 5-day high {'above' if X.up[i] == True else 'not above'}, volume {X.x10[i]:.2f}x 10-day, {X.x50[i]:.2f}x 50-day | "
        f"6-month move {X.move126[i]:.0%} = {X.move126[i] / F.adr20[i]:.1f} daily ranges, last-10-close spread {X.c10[i]:.1f} ranges | "
        f"order rank {A.rank_list.get(i, np.nan):.0f} of {int(per_night(NEW, 'B')[r.D])}")

say("\n" + "=" * 100)
say("CHECK 3 — each day's names firing the daily buy test (NEW bar), ranked by the order score over the night's whole list")
Fn = F[FIRE["NEW"]].assign(score=A.score.reindex(F.index[FIRE["NEW"]]).values)
n_nan = int(Fn.score.isna().sum())
Fn["rank_fired"] = Fn.score.fillna(-np.inf).groupby(Fn.scan_date).rank(ascending=False, method="first")
Fn["n_fired"] = Fn.groupby("scan_date").score.transform("size")
say(f"  firing name-days {len(Fn):,}; with no order score (fewer than 10/20 bars): {n_nan} (ranked last)")
for era, title in (("A", "era A 2017-22"), ("B", "era B 2022-24"), ("all", "ALL 2017-2024")):
    q = Q[qmask[era].values & NEW.loc[Q.row].values]           # his buys on the list
    qf = q[FIRE["NEW"].loc[q.row].values]
    rk = Fn.rank_fired.reindex(qf.row)
    big = qf.big.values
    per = per_night(FIRE["NEW"], era)
    say(f"  {title}: his buys that fire {len(qf)} of {len(q)} on the list -> in their day's top 5: {int((rk <= 5).sum())}, top 10: {int((rk <= 10).sum())} | "
        f"big winners firing {int(big.sum())} of {int(q.big.sum())} -> top 5: {int((rk[big] <= 5).sum())}, top 10: {int((rk[big] <= 10).sum())} | "
        f"days with more than 5 firing: {int((per > 5).sum())} of {len(per)} ({(per > 5).mean():.0%}); median {per.median():.0f} firing a day")
qf = Q[FIRE["NEW"].loc[Q.row].values].copy()
qf["rank_fired"] = Fn.rank_fired.reindex(qf.row).values; qf["n_fired"] = Fn.n_fired.reindex(qf.row).values
qf["rank_list"] = A.rank_list.reindex(qf.row).values
qf[["eid", "sym", "ticker", "D", "E", "big", "rank_fired", "n_fired", "rank_list"]].sort_values("E").to_csv(f"{HERE}/s0_check3_ranks.tsv", sep="\t", index=False)
say("  big winners that fire: " + ", ".join(f"{r.sym} {r.E} #{r.rank_fired:.0f} of {r.n_fired:.0f}" for r in qf[qf.big].sort_values("E").itertuples()))
say(f"  his firing buys' rank among the day's firing names: median {qf.rank_fired.median():.0f}, quartiles {qf.rank_fired.quantile(.25):.0f}-{qf.rank_fired.quantile(.75):.0f}; "
    f"their day's firing count median {qf.n_fired.median():.0f}")
open(f"{HERE}/s0_check23.txt", "w").write("\n".join(LOG) + "\n")
