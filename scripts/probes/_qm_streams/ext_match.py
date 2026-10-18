#!/usr/bin/env python3
"""#702 P4b extension, step 2 - match every re-extracted stream moment / Kyna row to a C0 base ($0: pandas + numpy only).

 talk date >= 2022-03-28  -> the production watch table (Polygon bars), exactly the first-pass path (`match_bars.match_one`)
 talk date <  2022-03-28  -> C0 on ALPACA split bars (`ext_c0.Evaluator`), one bar source for the whole pre-watch era
Outputs (EXT): stream_moments_ext.tsv, kyna_notes_ext.tsv, labelled_candidates_ext.tsv  (`bars_source` says which path).
"""
import argparse
import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ext_c0  # noqa: E402
import match_bars  # noqa: E402

from extract_hits_ext import N_REVIEWED_OK  # noqa: E402


def clean_cut(df):
    """The high-precision subset: a chart word at the mention AND a name we trust: a spoken ticker (tier A), a hand-reviewed allowlisted
    name, or a first-pass company-name alias that was read through (N_REVIEWED_OK). Kyna rows: written by cashtag / parenthesis (tier A)."""
    near = pd.to_numeric(df["near_chart"], errors="coerce").fillna(0) >= 1
    allow = pd.to_numeric(df.get("allow", 0), errors="coerce").fillna(0) == 1
    trusted = (df["tier"] == "A") | allow | df.get("name_word", pd.Series("", index=df.index)).isin(N_REVIEWED_OK)
    return ((df["source"] == "stream") & near & trusted) | ((df["source"] == "kyna") & (df["tier"] == "A"))


EXTRA = ["bars_source", "bars_symbol", "sym_flags", "n_breaks", "literal_flag", "elig", "elig_reason", "elig_nights", "n_nights_eval"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/Users/alvinfung/apollo_data/cb702/qm_streams")
    ap.add_argument("--ext", default="/Users/alvinfung/apollo_data/cb702/qm_streams/ext_2016_2022")
    ap.add_argument("--cb", default="/Users/alvinfung/apollo_data/cb702/out")
    a = ap.parse_args()
    w = match_bars.load_watch(os.path.join(a.cb, "watch.tsv.gz"))
    wmap = {t: g for t, g in w.groupby("ticker")}
    c = match_bars.load_cands(os.path.join(a.cb, "candidates.tsv"))
    cmap = {b: g for b, g in c.groupby("base_id")}
    ev = ext_c0.Evaluator(a.ext)
    sm = pd.read_csv(os.path.join(a.ext, "stream_moments_ext_raw.tsv"), sep="\t", keep_default_na=False, na_values=[""])
    ky = pd.read_csv(os.path.join(a.out, "kyna_notes_raw.tsv"), sep="\t", keep_default_na=False, na_values=[""])
    cache = {}

    def blank(era):
        m = dict(c0=0, n_watch_nights=0, first_watch="", last_watch="", c0_after10=0, breakout_followed=0, first_E="", days_ref_to_E="",
                 n_K_variants="", status_at_ref="", watch_era=era)
        for f in match_bars.FEAT:
            m["w_" + f] = ""
        for e in EXTRA:
            m[e] = ""
        return m

    def apply(df, datecol):
        recs = []
        for _, r in df.iterrows():
            d = r[datecol]
            if not isinstance(d, str) or not d:
                m = blank("undated")
            else:
                ref = dt.date.fromisoformat(d)
                key = (r["ticker"], d)
                if key in cache:
                    m = dict(cache[key])
                elif ref >= match_bars.WATCH_START:
                    if r["bars_window"] != 1:
                        m = blank("no_bars")
                    else:
                        m = match_bars.match_one(wmap.get(r["ticker"]), cmap, ref)
                        for e in EXTRA:
                            m[e] = ""
                        m["bars_source"], m["bars_symbol"] = "polygon_watch_c0", r["ticker"]
                    cache[key] = dict(m)
                else:
                    m = ev.eval_row(r["ticker"], ref)
                    cache[key] = dict(m)
            recs.append(m)
        return pd.concat([df.reset_index(drop=True), pd.DataFrame(recs).drop(columns=[c_ for c_ in ("bars_symbol",) if c_ in df.columns])], axis=1)

    sm = apply(sm, "upload_date")
    sm["source"] = "stream"
    ky = apply(ky, "stream_date")
    sm = sm.sort_values(["c0", "strength"], ascending=[False, False])
    ky = ky.sort_values(["c0", "strength"], ascending=[False, False])
    sm.to_csv(os.path.join(a.ext, "stream_moments_ext.tsv"), sep="\t", index=False)
    ky.to_csv(os.path.join(a.ext, "kyna_notes_ext.tsv"), sep="\t", index=False)
    print(f"off-calendar bars dropped: {ev.off_calendar}")

    ls = sm[(sm.c0 == 1) & (sm.chart_kw == 1)].copy()
    lk = ky[(ky.c0 == 1) & (ky.chart_kw == 1) & (ky.listonly == 0)].copy()
    ls["ref_date"], lk["ref_date"] = ls["upload_date"], lk["stream_date"]
    ls["where"] = ls["video"] + " @" + ls["ts"]
    lk["where"] = lk["slug"]
    ls["quote1"] = ls["quote"]
    lk["quote1"] = lk["context"].astype(str).str.slice(0, 240)
    kwcols = [k for k in sm.columns if k.startswith("kw_")]
    lab = pd.concat([ls, lk], ignore_index=True)
    lab["kw_list"] = lab[kwcols].apply(lambda r: ",".join(k[3:] for k in kwcols if r[k] == 1), axis=1)
    lab["near_chart"] = pd.to_numeric(lab["near_chart"], errors="coerce").fillna(0)
    lab["hq"] = clean_cut(lab).astype(int)
    lab = lab.sort_values("strength", ascending=False)
    keep = ["source", "ticker", "ref_date", "where", "tier", "hq", "via", "name_word", "strength", "kw_list", "mentions", "n_chart_kw", "near_chart", "n_images", "image_urls",
            "bars_source", "bars_symbol", "sym_flags", "literal_flag", "watch_era", "status_at_ref", "n_watch_nights", "first_watch", "last_watch",
            "w_base_len", "w_pole_date", "w_prior_move", "w_base_depth", "w_tightening_ratio", "w_tl_slope_pct", "w_tl_interior_touches",
            "w_trigger_bar_range_adr", "w_inside_day", "w_retrace", "w_higher_lows", "breakout_followed", "first_E", "days_ref_to_E", "title", "quote1"]
    for k in keep:
        if k not in lab.columns:
            lab[k] = ""
    lab[keep].to_csv(os.path.join(a.ext, "labelled_candidates_ext.tsv"), sep="\t", index=False)
    print("stream moments", len(sm), "kyna rows", len(ky), "labelled", len(lab))


if __name__ == "__main__":
    main()
