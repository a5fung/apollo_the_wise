#!/usr/bin/env python3
"""#702 P4b step 2 - match every stream / Kyna hit to our Consolidation Breakout watch rows ($0: pandas only).

For each hit with bars: was the ticker on a C0 watch row in the ~20 sessions (<= 28 calendar days) up to and including the
reference date (video upload date / Kyna stream date)?  Records the matching watch night(s), the base length / pole date /
character features of the LAST matching night, and whether a breakout candidate followed (candidates.tsv: existence and the
first entry date only - no trade outcome is read).  Watch nights exist from 2022-03-28 only; earlier references are flagged
pre_watch_era (C0 cannot be assessed, not 'no base').

Outputs (OUT): stream_moments.tsv (all hits + match), kyna_notes.tsv (all Kyna rows + match), labelled_candidates.tsv
(C0 base AND a chart keyword, both sources, ranked by keyword strength), summary.txt.
"""
import argparse
import csv
import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WATCH_START = dt.date(2022, 3, 28)
WIN_DAYS = 28
FEAT = ["base_len", "pole_date", "pole_sessions", "prior_move", "base_depth", "retrace", "tightening_ratio", "tl_slope_pct",
        "tl_interior_touches", "trigger_bar_range_adr", "inside_day", "higher_lows", "range_recent5", "pivot_full", "split"]


def load_watch(path):
    cols = ["ticker", "watch_date"] + FEAT
    w = pd.read_csv(path, sep="\t", usecols=cols)
    w["wd"] = pd.to_datetime(w["watch_date"]).map(dt.datetime.toordinal)
    w["base_id"] = w["ticker"] + "|" + w["pole_date"].astype(str)
    return w.sort_values(["ticker", "wd"])


def load_cands(path):
    c = pd.read_csv(path, sep="\t", usecols=["ticker", "D", "E", "K", "base_id"])
    c["dd"] = pd.to_datetime(c["D"]).map(dt.datetime.toordinal)
    c["ed"] = pd.to_datetime(c["E"]).map(dt.datetime.toordinal)
    return c.sort_values(["base_id", "dd"])


def match_one(wg, cg, ref):
    """wg: watch rows of the ticker (sorted); cg: candidates by base_id dict; ref: date."""
    r = ref.toordinal()
    out = dict(c0=0, n_watch_nights=0, first_watch="", last_watch="", c0_after10=0, breakout_followed=0, first_E="", days_ref_to_E="",
               n_K_variants="", status_at_ref="")
    for f in FEAT:
        out["w_" + f] = ""
    if wg is None or ref < WATCH_START:
        out["watch_era"] = "pre_watch_era" if ref < WATCH_START else "no_ticker_rows"
        return out
    out["watch_era"] = "partial_window" if ref - dt.timedelta(days=WIN_DAYS) < WATCH_START else "full_window"
    inw = wg[(wg["wd"] >= r - WIN_DAYS) & (wg["wd"] <= r)]
    out["c0_after10"] = int(((wg["wd"] > r) & (wg["wd"] <= r + 10)).any())
    if inw.empty:
        return out
    last = inw.iloc[-1]
    out.update(c0=1, n_watch_nights=len(inw), first_watch=dt.date.fromordinal(int(inw.iloc[0]["wd"])).isoformat(),
               last_watch=dt.date.fromordinal(int(last["wd"])).isoformat())
    for f in FEAT:
        v = last[f]
        out["w_" + f] = "" if pd.isna(v) else (round(v, 4) if isinstance(v, float) else v)
    cg_b = cg.get(last["base_id"])
    if cg_b is not None:
        after = cg_b[cg_b["dd"] >= int(last["wd"])]
        if len(after):
            fe = int(after["ed"].min())
            out.update(breakout_followed=1, first_E=dt.date.fromordinal(fe).isoformat(), days_ref_to_E=fe - r,
                       n_K_variants=int(after[after["ed"] == fe]["K"].nunique()))
    # where the base stood on the day he talked: on watch that very day / already broken out / watch lapsed with no breakout
    if out["breakout_followed"] and out["days_ref_to_E"] <= 0:
        out["status_at_ref"] = "broke_out_before_ref"
    elif int(last["wd"]) >= r - 4:
        out["status_at_ref"] = "in_base_at_ref"
    else:
        out["status_at_ref"] = "base_lapsed_before_ref"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cb", default="/Users/alvinfung/apollo_data/cb702/out")
    a = ap.parse_args()
    out = a.out
    w = load_watch(os.path.join(a.cb, "watch.tsv.gz"))
    wmap = {t: g for t, g in w.groupby("ticker")}
    c = load_cands(os.path.join(a.cb, "candidates.tsv"))
    cmap = {b: g for b, g in c.groupby("base_id")}
    print(f"watch rows {len(w)}, candidates {len(c)}", flush=True)

    sm = pd.read_csv(os.path.join(out, "stream_moments_raw.tsv"), sep="\t")
    ky = pd.read_csv(os.path.join(out, "kyna_notes_raw.tsv"), sep="\t")

    def apply(df, datecol):
        recs = []
        for _, r in df.iterrows():
            d = r[datecol]
            if r["bars_window"] != 1 or not isinstance(d, str) or not d:
                m = dict(c0=0, n_watch_nights=0, first_watch="", last_watch="", c0_after10=0, breakout_followed=0, first_E="",
                         days_ref_to_E="", n_K_variants="", status_at_ref="", watch_era="no_bars" if r["bars_window"] != 1 else "undated")
                for f in FEAT:
                    m["w_" + f] = ""
            else:
                m = match_one(wmap.get(r["ticker"]), cmap, dt.date.fromisoformat(d))
            recs.append(m)
        return pd.concat([df.reset_index(drop=True), pd.DataFrame(recs)], axis=1)

    sm = apply(sm, "upload_date")
    sm["source"] = "stream"
    ky = apply(ky, "stream_date")
    sm = sm.sort_values(["c0", "strength"], ascending=[False, False])
    ky = ky.sort_values(["c0", "strength"], ascending=[False, False])
    sm.to_csv(os.path.join(out, "stream_moments.tsv"), sep="\t", index=False)
    ky.to_csv(os.path.join(out, "kyna_notes.tsv"), sep="\t", index=False)

    # labelled candidates: a C0 base AND a chart keyword (list-only Kyna lines excluded: no discussion)
    ls = sm[(sm.c0 == 1) & (sm.chart_kw == 1)].copy()
    lk = ky[(ky.c0 == 1) & (ky.chart_kw == 1) & (ky.listonly == 0)].copy()
    ls["ref_date"], lk["ref_date"] = ls["upload_date"], lk["stream_date"]
    ls["where"] = ls["video"] + " @" + ls["ts"]
    lk["where"] = lk["slug"]
    ls["quote1"] = ls["quote"]
    lk["quote1"] = lk["context"].str.slice(0, 240)
    kwcols = [c for c in sm.columns if c.startswith("kw_")]
    lab = pd.concat([ls, lk], ignore_index=True)
    lab["kw_list"] = lab[kwcols].apply(lambda r: ",".join(k[3:] for k in kwcols if r[k] == 1), axis=1)
    lab = lab.sort_values("strength", ascending=False)
    keep = ["source", "ticker", "ref_date", "where", "tier", "via", "strength", "kw_list", "mentions", "n_chart_kw", "near_chart", "n_images", "image_urls",
            "watch_era", "status_at_ref", "n_watch_nights", "first_watch", "last_watch", "w_base_len", "w_pole_date", "w_prior_move", "w_base_depth",
            "w_tightening_ratio", "w_tl_slope_pct", "w_tl_interior_touches", "w_trigger_bar_range_adr", "w_inside_day", "w_retrace",
            "w_higher_lows", "breakout_followed", "first_E", "days_ref_to_E", "title", "quote1"]
    for k in keep:
        if k not in lab.columns:
            lab[k] = ""
    lab[keep].to_csv(os.path.join(out, "labelled_candidates.tsv"), sep="\t", index=False)
    print("stream moments", len(sm), "kyna rows", len(ky), "labelled", len(lab), flush=True)


if __name__ == "__main__":
    main()
