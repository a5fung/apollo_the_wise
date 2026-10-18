#!/usr/bin/env python3
"""#702 P4b vision step: score frame reads against the REAL daily bars ($0) - the answer key the 10-18 batch 1 lacked.

A reported hand-drawn line is VERIFIED when, between its two end points, the bars behave like that line: >= 2 bars touch it
(a top line: |high - L| <= 2.5% of L; a bottom line: the low) and <= 10% of closes cross it by more than 3%. Prices are
compared AS SHOWN ON THE SCREEN THAT DAY: split-adjusted bars x (raw / split-adjusted) on the screen date, so a split after
the stream does not read as a misread. Also checks each end point (a bar high / low within 3% inside +-5 sessions).

    python vision_score.py --reads reads.json --out score.tsv
`reads.json` = [{"variant": ..., "group": ..., "frames": [<frame read>, ...]}, ...]  (the free re-test's output)
"""
import argparse
import csv
import datetime as dt
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

QM = "/Users/alvinfung/apollo_data/cb702/qm_streams"
CB = "/Users/alvinfung/apollo_data/cb702"
TOUCH = 0.025
CROSS = 0.03
CROSS_MAX_SHARE = 0.10
ANCHOR = 0.03
ANCHOR_SESSIONS = 5


def load_bars(tickers):
    cols = "ticker,date,open,high,low,close,volume,vwap,trade_count".split(",")
    split = pd.concat([pd.read_csv(f, header=None, names=cols, usecols=[0, 1, 3, 4, 5])
                       for f in glob.glob(f"{QM}/alpaca_all_2016_2022/split/*.csv.gz")])
    split = split[split.ticker.isin(tickers)]
    raw = pd.concat([pd.read_csv(f, header=None, names=cols, usecols=[0, 1, 5])
                     for f in glob.glob(f"{QM}/alpaca_all_2016_2022/raw/*.csv.gz")])
    raw = raw[raw.ticker.isin(tickers)].rename(columns={"close": "raw_close"})
    a = split.merge(raw, on=["ticker", "date"], how="left")
    a["ratio"] = a.raw_close / a.close                      # product of the splits AFTER that date (as of the fetch)
    p = pd.read_csv(f"{CB}/daily_closes_all.csv.gz", header=None, names=["ticker", "date", "o", "high", "low", "close", "v"],
                    usecols=[0, 1, 3, 4, 5])
    p = p[p.ticker.isin(tickers) & (p.date > "2022-06-30")]
    spl = {}
    for ln in open(f"{CB}/cb702_splits.psv"):
        t, d, x, y = ln.strip().split("|")[:4]
        if t in tickers:
            spl.setdefault(t, []).append((d, float(y) / float(x)))
    return a, p, spl


def series_asof(t, screen, a, p, spl):
    """(dates, high, low, close) as the chart showed them on `screen` (YYYY-MM-DD)."""
    if screen <= "2022-06-30":
        g = a[a.ticker == t].sort_values("date")
        if g.empty:
            return None
        s = g[g.date <= screen]
        r = float(s.ratio.iloc[-1]) if len(s) else float(g.ratio.iloc[0])
        return g.date.to_numpy(), g.high.to_numpy() * r, g.low.to_numpy() * r, g.close.to_numpy() * r
    g = p[p.ticker == t].sort_values("date")
    if g.empty:
        return None
    f = 1.0
    for d, ratio in spl.get(t, []):
        if d > screen:
            f *= ratio
    return g.date.to_numpy(), g.high.to_numpy() * f, g.low.to_numpy() * f, g.close.to_numpy() * f


def ordinal(s):
    try:
        return dt.date.fromisoformat(s[:10]).toordinal()
    except Exception:
        return None


def check_line(ln, ser):
    role = ln["role"]
    if role not in ("top", "bottom", "level"):
        return dict(status="not_scored")
    d1, d2 = ordinal(ln["start_date"]), ordinal(ln["end_date"])
    p1, p2 = ln["start_price"], ln["end_price"]
    if d1 is None or d2 is None or not (p1 > 0 and p2 > 0):
        return dict(status="unreadable_coords")
    if d1 > d2:
        d1, d2, p1, p2 = d2, d1, p2, p1
    dates, hi, lo, cl = ser
    od = np.array([dt.date.fromisoformat(x).toordinal() for x in dates])
    m = (od >= d1) & (od <= d2)
    if m.sum() < 3:
        return dict(status="no_bars_in_span", n=int(m.sum()))
    L = p1 + (p2 - p1) * (od[m] - d1) / max(1, d2 - d1)
    h, l, c = hi[m], lo[m], cl[m]
    # crossings count only up to the LAST touch: a line acts as support / resistance while price keeps touching it; a
    # breakout through it after that (the trade he draws it for) is not a misread
    if role == "top":
        tm = np.abs(h - L) / L <= TOUCH; xm = c > L * (1 + CROSS)
    elif role == "bottom":
        tm = np.abs(l - L) / L <= TOUCH; xm = c < L * (1 - CROSS)
    else:  # a level: price respects it from either side; touches by high OR low
        tm = (np.abs(h - L) / L <= TOUCH) | (np.abs(l - L) / L <= TOUCH)
        xm = (c > L * (1 + CROSS)) if (c > L * (1 + CROSS)).mean() < (c < L * (1 - CROSS)).mean() else (c < L * (1 - CROSS))
    touch = int(tm.sum())
    last = int(np.nonzero(tm)[0][-1]) if touch else len(L) - 1
    cross = float(xm[: last + 1].mean())
    # end-point anchor: a bar within +-5 sessions whose high (top) / low (bottom) is within 3% of the stated price
    def anchor(dd, pp):
        k = int(np.argmin(np.abs(od - dd)))
        w = slice(max(0, k - ANCHOR_SESSIONS), k + ANCHOR_SESSIONS + 1)
        ref = hi[w] if role == "top" else lo[w] if role == "bottom" else np.r_[hi[w], lo[w]]
        return bool((np.abs(ref - pp) / pp <= ANCHOR).any())
    ok = touch >= 2 and cross <= CROSS_MAX_SHARE
    return dict(status="verified" if ok else "not_verified", touches=touch, cross_share=round(cross, 3),
                start_anchor=anchor(d1, p1), end_anchor=anchor(d2, p2), n=int(m.sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reads", required=True)
    ap.add_argument("--manifest", default=f"{QM}/vision/batch1_manifest.tsv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    runs = json.load(open(a.reads))
    vs = {r["id"]: r["upload_date"] for r in csv.DictReader(open(f"{QM}/video_status.tsv"), delimiter="\t")}
    man = {r["frame_id"]: r for r in csv.DictReader(open(a.manifest), delimiter="\t")}
    rename = {r["polygon_ticker"]: r["alpaca_symbol"] for r in csv.DictReader(open(f"{QM}/ext_2016_2022/rename_map.tsv"), delimiter="\t")}
    tick = {f["ticker_on_screen"] for run in runs for f in run["frames"]}
    A, P, S = load_bars(tick | {rename[t] for t in tick if t in rename})
    rows = []
    for run in runs:
        for f in run["frames"]:
            up = vs.get(man.get(f["frame_id"], {}).get("vid", ""), "")
            screen = f["screen_date"] if ordinal(f["screen_date"]) else (f"{up[:4]}-{up[4:6]}-{up[6:8]}" if len(up) == 8 else "")
            ser = series_asof(f["ticker_on_screen"], screen, A, P, S) if screen else None
            if ser is None and screen and f["ticker_on_screen"] in rename:      # SQ -> XYZ, DWAC -> DJT (data-derived map)
                ser = series_asof(rename[f["ticker_on_screen"]], screen, A, P, S)
            for i, ln in enumerate(f["daily_lines"]):
                res = check_line(ln, ser) if ser is not None else dict(status="no_bars_for_ticker")
                rows.append(dict(variant=run["variant"], group=run["group"], frame_id=f["frame_id"],
                                 ticker=f["ticker_on_screen"], screen=screen, line=i, **{k: ln[k] for k in ln}, **res))
            if not f["daily_lines"]:
                rows.append(dict(variant=run["variant"], group=run["group"], frame_id=f["frame_id"],
                                 ticker=f["ticker_on_screen"], screen=screen, line=-1, status="no_lines_reported"))
    df = pd.DataFrame(rows)
    df.to_csv(a.out, sep="\t", index=False)
    sc = df[df.status.isin(["verified", "not_verified"])]
    print("lines reported per variant:")
    print(df[df.line >= 0].groupby("variant").size().to_string())
    print("\nscored lines (top / bottom / level with bars) - verified share:")
    print(sc.groupby("variant").status.apply(lambda s: f"{(s == 'verified').sum()}/{len(s)}").to_string())
    print("\nstatus counts:")
    print(df.groupby(["variant", "status"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    sys.exit(main())
