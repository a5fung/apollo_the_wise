#!/usr/bin/env python3
"""How much do the flagged data artifacts touch a published trade population? (companion to price_integrity_check.py)

For each artifact class in <label>_flags.tsv it counts the trades whose HOLD window [E, E + exit_session bars] (and, separately, the
60 bars BEFORE E, which feed the pole/base detection) contain a flagged event, and shows mean R touched vs untouched and the
population headline with the union of strong artifacts removed. Read-only; bars after --cutoff are dropped unread.

  python trade_impact.py --flags OUT/A_flags.tsv --export daily_closes_all.csv.gz --trades trades_pre_exitpb.tsv.gz --label A
"""
import argparse
import sys

import numpy as np
import pandas as pd

SEALED_FROM = "2025-01-01"


def load_bars(path, cutoff, tickers):
    parts = []
    for ch in pd.read_csv(path, header=None, names=["t", "d", "o", "h", "l", "c", "v"], dtype={"t": str, "d": str},
                          keep_default_na=False, na_values=[""], chunksize=2_000_000):
        ch = ch[(ch.d <= cutoff) & ch.t.isin(tickers)]
        parts.append(ch[["t", "d", "v"]])
    return pd.concat(parts).sort_values(["t", "d"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flags", required=True); ap.add_argument("--export", required=True); ap.add_argument("--trades", required=True)
    ap.add_argument("--label", default="X"); ap.add_argument("--cutoff", default="2024-12-31"); ap.add_argument("--pre", type=int, default=60)
    ap.add_argument("--out", default=None)
    ap.add_argument("--kind", choices=["c0", "r1"], default="c0", help="c0 = the published C0 trade list; r1 = a trail-read cell file (first attempts only)")
    ap.add_argument("--cell", default="A20_X3_P0")
    a = ap.parse_args()
    if a.cutoff >= SEALED_FROM:
        sys.exit("cutoff is in the sealed range")
    if a.kind == "c0":
        t = pd.read_csv(a.trades, sep="\t", low_memory=False, usecols=["ticker", "E", "arm", "entry", "K", "C0", "mature", "exit_session", "realized_r", "fill"])
        t = t[(t.arm == "pp") & (t.entry == "orh5") & (t.K == "tl") & (t.C0 == 1) & (t.mature == 1)].reset_index(drop=True)
    else:
        t = pd.read_csv(a.trades, sep="\t", low_memory=False, keep_default_na=False, na_values=[""], usecols=["cell", "attempt", "ticker", "entry_date", "exit_j", "realized_r"])
        t = t[(t.cell == a.cell) & (t.attempt == 0) & t.exit_j.notna()].rename(columns={"entry_date": "E", "exit_j": "exit_session"}).reset_index(drop=True)
        t["fill"] = np.nan
    n0 = len(t)
    print(f"[{a.label}] {a.kind} {a.cell if a.kind == 'r1' else 'published C0'} trades n={n0:,}  distinct tickers={t.ticker.nunique():,}  E range {t.E.min()}..{t.E.max()}  "
          f"mean R {t.realized_r.mean():+.4f}  >=10R per 100 {100 * (t.realized_r >= 10).mean():.3f}  worst {t.realized_r.min():+.1f}")
    after = t.E > a.cutoff
    print(f"  trades entered after the cutoff {a.cutoff} (their bars are sealed): {int(after.sum())}")
    f = pd.read_csv(a.flags, sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str, "date": str})
    bars = load_bars(a.export, a.cutoff, set(t.ticker))
    bt = {k: g for k, g in bars.groupby("t")}
    # per-trade window bounds
    lo_pre, hi_hold, trunc, holes = [], [], [], []
    ds = {k: g.d.to_numpy() for k, g in bt.items()}
    vs = {k: g.v.to_numpy() for k, g in bt.items()}
    cal = np.sort(bars[bars.t == "SPY"].d.unique()) if (bars.t == "SPY").any() else None
    for r in t.itertuples():
        d = ds.get(r.ticker)
        if d is None or r.E > a.cutoff:
            lo_pre.append(None); hi_hold.append(None); trunc.append(True); holes.append(False); continue
        p = int(np.searchsorted(d, r.E))
        q = p + int(r.exit_session)
        trunc.append(q > len(d) - 1)
        q = min(q, len(d) - 1)
        lo_pre.append(d[max(0, p - a.pre)]); hi_hold.append(d[q])
        holes.append(False)
    t["pre_lo"], t["hold_hi"], t["trunc"] = lo_pre, hi_hold, trunc
    print(f"  trades whose hold runs past the last bar kept (truncated or no bars): {int(t.trunc.sum())}")

    def events(mask):
        g = f[mask]
        return {k: np.sort(v.date.to_numpy()) for k, v in g.groupby("ticker")}

    classes = {
        "gap reverted next session": (f.check == "gap") & (f.klass == "reverted_next_session"),
        "gap reverted within 5": (f.check == "gap") & (f.klass == "reverted_within_5"),
        "gap open-only, reverted same day": (f.check == "gap") & (f.klass == "open_gap_reverted_same_day"),
        "gap reverted AND no volume event": (f.check == "gap") & f.klass.isin(["reverted_next_session", "reverted_within_5"]) & (f.v_ratio_20 < 2),
        "gap persistent (all)": (f.check == "gap") & (f.klass == "persistent"),
        "gap persistent DOWN >=25% close-to-close": (f.check == "gap") & (f.klass == "persistent") & (f.rc <= -0.25),
        "gap persistent UP >=25% close-to-close": (f.check == "gap") & (f.klass == "persistent") & (f.rc >= 0.25),
        "adjusted series broken across a vendor/listed adjustment": (f.check == "adj_event"),
        "spin-off candidate, mechanical": (f.check == "spinoff") & (f.klass == "candidate_mechanical"),
        "spin-off candidate, other": (f.check == "spinoff") & (f.klass == "candidate_other"),
        "split-like ratio, volume-confirmed": (f.check == "splitlike") & (f.klass == "volume_confirmed_relevel"),
        "split-like ratio, unconfirmed": (f.check == "splitlike") & (f.klass == "unconfirmed"),
        "wick >= 1.5x with volume": (f.check == "wick"),
        "interior hole >= 5 sessions": (f.check == "calendar"),
    }
    union_names = ["gap reverted AND no volume event", "adjusted series broken across a vendor/listed adjustment",
                   "spin-off candidate, mechanical", "split-like ratio, volume-confirmed"]
    rows, touched_union_hold = [], np.zeros(len(t), bool)
    touched_union_pre = np.zeros(len(t), bool)
    for name, m in classes.items():
        ev = events(m)
        th = np.zeros(len(t), bool); tp = np.zeros(len(t), bool)
        for i, r in enumerate(t.itertuples()):
            e = ev.get(r.ticker)
            if e is None or pd.isna(r.hold_hi):
                continue
            th[i] = ((e >= r.E) & (e <= r.hold_hi)).any()
            tp[i] = ((e >= r.pre_lo) & (e < r.E)).any()
        if name in union_names:
            touched_union_hold |= th; touched_union_pre |= tp
        R = t.realized_r.to_numpy()
        rows.append((name, int(th.sum()), R[th].mean() if th.any() else np.nan, R[~th].mean(), int((R[th] >= 10).sum()),
                     int(tp.sum()), R[tp].mean() if tp.any() else np.nan))
    out = pd.DataFrame(rows, columns=["class", "trades_hold_touched", "meanR_touched", "meanR_untouched", "n_ge10R_touched", "trades_pre60_touched", "meanR_pre_touched"])
    pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 70)
    print(out.round(4).to_string(index=False))
    # duplicates and test symbols and trades on test tickers
    dup = f[f.check == "duplicate"]
    dset = set(dup.ticker) | {x.split("other=")[1].split("|")[0] for x in dup.extra}
    ts = set(f[f.check == "test_symbol"].ticker)
    print(f"  trades on a ticker inside an identical-series pair: {int(t.ticker.isin(dset).sum())}  on an exchange test ticker: {int(t.ticker.isin(ts).sum())}")
    dbl = 0
    for r in dup.itertuples():
        b = r.extra.split("other=")[1].split("|")[0]
        x = t[t.ticker == r.ticker]; y = t[t.ticker == b]
        if len(x) and len(y):
            dbl += len(x.merge(y, on=["E", "realized_r"]))
    print(f"  trades duplicated one-for-one under both symbols (same E, same R): {dbl}")
    big = t.fill >= 1000
    print(f"  trades filled at an adjusted price >= $1000: {int(big.sum())}  mean R {t.realized_r[big].mean():+.4f}")
    R = t.realized_r
    keep = ~(touched_union_hold | touched_union_pre)
    keep_hold = ~touched_union_hold
    print(f"UNION of strong artifacts {union_names}")
    print(f"  touched in the hold: {int(touched_union_hold.sum())}  touched in the 60 bars before E: {int(touched_union_pre.sum())}  either: {int((~keep).sum())}  (of n={n0:,})")
    for nm, k in (("published", np.ones(len(t), bool)), ("hold-clean", keep_hold), ("hold- and pre-clean", keep)):
        print(f"  {nm:22s} n={int(k.sum()):6,}  mean R {R[k].mean():+.4f}  median {R[k].median():+.3f}  >=10R per 100 {100 * (R[k] >= 10).mean():.3f}  >=4R per 100 {100 * (R[k] >= 4).mean():.3f}  worst {R[k].min():+.1f}")
    if a.out:
        out.to_csv(a.out, sep="\t", index=False)


if __name__ == "__main__":
    main()
