#!/usr/bin/env python3
"""#702 re-entry read ($0, local) - pre-registered in docs/analysis/cb_reentry_prereg_2026-10-19.md before any re-entry
outcome was read. Trendline level, ORH5 entry, low-of-day stop, the article exit arm p33_s3_t10 (the only arm the runner
computed on repeat breaks). R1 (decides): after the base's first trade exits, ONE re-entry on the next break strictly after
the exit day. R2 / Rall beside. Discovery decides; 2025-26 is descriptive only.

    python reentry_read.py --data /Users/alvinfung/apollo_data/cb702 --out <file.txt>
"""
import argparse
import sys

import numpy as np
import pandas as pd

ARM, VARIANT, LEVEL = "p33_s3_t10", "orh5", "tl"


def sessions_index(daily_gz, tickers):
    b = pd.read_csv(daily_gz, header=None, names=["ticker", "date", "o", "h", "l", "c", "v"], usecols=[0, 1])
    b = b[b.ticker.isin(tickers)].sort_values(["ticker", "date"])
    return {t: g.date.to_numpy() for t, g in b.groupby("ticker")}


def walk(df, cal, max_re):
    """Apply the rule to one period's trades (one row per break; columns ticker, base, E, realized_r, sessions_held)."""
    out = []
    for (tk, base), g in df.sort_values("E").groupby(["ticker", "base"]):
        days = cal.get(tk)
        open_until, n_re, first = None, 0, True
        for r in g.itertuples():
            if open_until is not None and r.E <= open_until:
                continue                                  # a break while a trade is open (or on its exit day) is skipped
            if not first and n_re >= max_re:
                break
            i = int(np.searchsorted(days, r.E))
            j = min(i + int(r.sessions_held), len(days) - 1)
            open_until = days[j]
            out.append(dict(ticker=tk, base=base, E=r.E, month=r.E[:7], r=r.realized_r, kind="first" if first else "re",
                            C0=r.C0, C1=r.C1, C3=r.C3))
            if not first:
                n_re += 1
            first = False
    return pd.DataFrame(out)


def boot(x, months, n=2000, seed=702):
    rng = np.random.default_rng(seed)
    um = np.unique(months)
    by = {m: x[months == m] for m in um}
    means = []
    for _ in range(n):
        pick = rng.choice(um, size=len(um), replace=True)
        v = np.concatenate([by[m] for m in pick])
        means.append(v.mean() if len(v) else np.nan)
    return np.nanpercentile(means, [2.5, 97.5])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    L = []
    P = L.append
    for f, label in (("trades_discovery.tsv.gz", "2022-24 DISCOVERY - decides"),
                     ("trades_holdout.tsv.gz", "2025-26 - DESCRIPTIVE ONLY (read once for the primary already)")):
        t = pd.read_csv(f"{a.data}/out/{f}", sep="\t",
                        usecols=["ticker", "D", "E", "K", "variant", "arm", "realized_r", "mature", "sessions_held", "C0", "C1",
                                 "C3", "retrigger"], low_memory=False)
        t = t[(t.K == LEVEL) & (t.variant == VARIANT) & (t.arm == ARM) & (t.mature == 1)].copy()
        c = pd.read_csv(f"{a.data}/out/candidates.tsv", sep="\t", usecols=["ticker", "D", "E", "K", "pole_date"],
                        low_memory=False)
        c = c[c.K == LEVEL].drop_duplicates(["ticker", "D", "E"])
        t = t.merge(c[["ticker", "D", "E", "pole_date"]], on=["ticker", "D", "E"], how="left")
        t["base"] = t.pole_date    # the runner's one-trade-per-base key (stamp_retrigger: ticker, pole_date, K); "first" = the
        # base's first FILLED trade (a base whose first break never filled starts at a repeat break)
        cal = sessions_index(f"{a.data}/daily_closes_all.csv.gz", set(t.ticker))
        P(f"\n===== {label}  (tl / ORH5 / low-of-day stop / article exit p33_s3_t10; mature walks) =====")
        P(f"breaks available: {len(t):,} ({int((t.retrigger == 0).sum()):,} first breaks, {int((t.retrigger == 1).sum()):,} repeat breaks)")
        for rule, mx in (("R1 (decides): one re-entry", 1), ("R2 (beside): up to two", 2), ("Rall (beside): every break after each exit", 10 ** 6)):
            d = walk(t, cal, mx)
            for cell in ("C0", "C1", "C3"):
                g = d[d[cell] == 1]
                fi, re_ = g[g.kind == "first"], g[g.kind == "re"]
                if not len(re_):
                    P(f"  {rule:44s} {cell}: no re-entries"); continue
                lo, hi = boot(re_.r.to_numpy(), re_.month.to_numpy())
                per_base_first = fi.groupby(["ticker", "base"]).r.sum()
                per_base_all = g.groupby(["ticker", "base"]).r.sum()
                verdict = ("RE-ENTRY ADDS EDGE" if lo > 0 else "RE-ENTRY LOSES" if hi < 0 else "CAN'T TELL")
                P(f"  {rule:44s} {cell}: first breaks n={len(fi):5d} mean {fi.r.mean():+.3f}R >=5R {(fi.r >= 5).mean():.1%} | "
                  f"re-entries n={len(re_):5d} mean {re_.r.mean():+.3f}R [{lo:+.2f}, {hi:+.2f}] >=5R {(re_.r >= 5).mean():.1%} "
                  f"win {(re_.r > 0).mean():.0%} | per base: first only {per_base_first.mean():+.3f}R vs with re-entries "
                  f"{per_base_all.mean():+.3f}R ({len(g) / len(per_base_all):.2f} trades/base)"
                  + (f"  -> {verdict}" if (cell == "C0" and mx == 1 and "DISCOVERY" in label) else ""))
    open(a.out, "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
