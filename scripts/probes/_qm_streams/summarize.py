#!/usr/bin/env python3
"""#702 P4b - one-page OUT/summary.txt from the step outputs ($0: pandas only). Also prices the HELD vision step from
shared.llm_models.pricing_for (a pure table lookup - nothing is called)."""
import argparse
import datetime as dt
import json
import os
import sys

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def price_per_frame(model="claude-sonnet-5-5", img_tok=1600, prompt_tok=450, out_tok=450):
    try:
        sys.path.insert(0, REPO)
        from shared.llm_models import pricing_for
        p = pricing_for(model)
        src = "pricing_for()"
    except Exception:
        p, src = {"input": 2.0, "output": 10.0}, "table copy (import failed)"
    return (img_tok + prompt_tok) / 1e6 * p["input"] + out_tok / 1e6 * p["output"], p, src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--videos", required=True)
    a = ap.parse_args()
    o = a.out
    vs = pd.read_csv(os.path.join(o, "video_status.tsv"), sep="\t", dtype={"upload_date": str})
    sm = pd.read_csv(os.path.join(o, "stream_moments.tsv"), sep="\t")
    ky = pd.read_csv(os.path.join(o, "kyna_notes.tsv"), sep="\t")
    lab = pd.read_csv(os.path.join(o, "labelled_candidates.tsv"), sep="\t")
    meta = json.load(open(os.path.join(o, "kyna_crawl_meta.json")))
    L = []
    P = L.append
    # fetch timing from the resumable log
    ts = []
    attempts = 0
    for ln in open(os.path.join(o, "fetch_log.tsv"), encoding="utf-8"):
        p = ln.split("\t")
        ts.append(dt.datetime.fromisoformat(p[0]))
        attempts += 1
    wall = (max(ts) - min(ts)).total_seconds() if ts else 0
    n = len(vs)
    ok = int((vs.status == "ok").sum())
    nocaps = int((vs.status == "nocaps").sum())
    fail = int((vs.status == "fail").sum())
    missing = int((vs.status == "missing").sum())
    hrs_all = vs.seconds.sum() / 3600
    hrs_ok = vs[vs.status == "ok"].seconds.sum() / 3600
    P("#702 P4b - Qullamaggie streams + Kyna notes: free mining summary")
    P("=" * 78)
    P(f"TRANSCRIPTS  videos listed {n} ({hrs_all:.0f} h) | captions fetched {ok} ({hrs_ok:.0f} h, {vs.words.sum():,} words) | "
      f"no auto-caption track {nocaps} | failed {fail}" + (f" | NOT ATTEMPTED {missing}" if missing else ""))
    P(f"             fetch wall time {wall/3600:.2f} h over {attempts} log lines (>= 8 s between videos, no cookies, no paid call)")
    vs["yr"] = vs.upload_date.str[:4]
    by = vs.groupby("yr").agg(videos=("id", "size"), ok=("status", lambda s: int((s == "ok").sum())), nocaps=("status", lambda s: int((s == "nocaps").sum())),
                              fail=("status", lambda s: int(s.isin(["fail"]).sum())))
    P("  by upload year:  " + "  ".join(f"{y}: {r.ok}/{r.videos}" for y, r in by.iterrows()))
    fails = vs[vs.status == "fail"]
    for _, r in fails.iterrows():
        P(f"  FAILED {r['id']} {r.upload_date} {r.title[:50]}  <- {r.get('note', '')}")
    ok_in_bars = int(sm[sm.bars_window == 1].video.nunique())
    P("")
    P(f"HITS         stream moments {len(sm):,} in {sm.video.nunique()} videos | with a bars window (video >= 2021-08) {int((sm.bars_window==1).sum()):,} "
      f"| in the watch era (>= 2022-03-28) {int(sm.watch_era.isin(['full_window','partial_window','no_ticker_rows']).sum()):,}")
    P(f"             with a C0 base in the 20 sessions before the video {int(sm.c0.sum()):,} | + a chart word {int(((sm.c0==1)&(sm.chart_kw==1)).sum()):,} "
      f"| distinct tickers in those {sm[(sm.c0==1)&(sm.chart_kw==1)].ticker.nunique()}")
    P(f"KYNA         posts crawled {len(meta)-1} (index + {len(meta)-1}) | paywalled {sum(m.get('paywalled',0) or 0 for m in meta)} | "
      f"dated stream posts {ky[ky.stream_date.notna()].slug.nunique()} | post-ticker rows {len(ky)} ({ky.ticker.nunique()} tickers) | "
      f"image URLs recorded {int(ky.n_images.sum())}")
    P(f"             with a C0 base {int(ky.c0.sum())} | + chart word (not a bare list line) {int(((ky.c0==1)&(ky.chart_kw==1)&(ky.listonly==0)).sum())}")
    P(f"LABELLED     candidates (C0 base AND a chart word): {len(lab)}  = stream {int((lab.source=='stream').sum())} + kyna {int((lab.source=='kyna').sum())}")
    if len(lab):
        P("             base state on the talk day: " + ", ".join(f"{k} {v}" for k, v in lab.status_at_ref.value_counts().items()))
        P("             tier: " + ", ".join(f"{k} {v}" for k, v in lab.tier.value_counts().items()) +
          "  (A = spoken ticker, B = English-word ticker + chart word, C = very common word + caps + chart word, N = company name)")
    P("")
    P("TOP 30 LABELLED CANDIDATES  (ticker | talk date | where | kw | base state | base_len | one-line quote)")
    for _, r in lab.head(30).iterrows():
        q = str(r.quote1)[:150].replace("\n", " ")
        P(f"  {r.ticker:<5} {r.ref_date} {str(r['where'])[:34]:<34} [{r.kw_list}] {r.status_at_ref} L={r.w_base_len} | {q}")
    # the held step 3 estimate
    s1 = lab[lab.source == "stream"]
    two = s1[(s1.get("n_chart_kw", 0) >= 2)]
    near = s1[(s1.get("near_chart", 0) >= 1)]
    inb = s1[s1.status_at_ref.isin(["in_base_at_ref", "broke_out_before_ref"])]
    uniq_vt = s1.drop_duplicates(["where"]).shape[0]
    uniq_base = s1.drop_duplicates(["ticker", "w_pole_date"]).shape[0]
    k = lab[lab.source == "kyna"]
    k_imgs = int(k.n_images.clip(upper=3).sum())
    c_frame, pr, src = price_per_frame()
    P("")
    P("HELD STEP 3 (vision read of the chart at the moment - NOT RUN): frames needed at ~1 frame per moment")
    P(f"  stream moments with a C0 base + chart word: {len(s1)}  (distinct video+time {uniq_vt}; distinct stock-bases {uniq_base})")
    P(f"    tighter cuts: >= 2 distinct chart words {len(two)} | a chart word within -10/+15 s of the mention {len(near)} | base in place or just broken out {len(inb)}")
    P(f"  Kyna rows with a C0 base + chart word: {len(k)} -> up to {k_imgs} images already posted (URLs only; no frame extraction needed)")
    for label, cnt in (("all labelled stream moments", len(s1)), ("near-mention cut", len(near)), ("base-in-place cut", len(inb))):
        P(f"  price @ {label}: {cnt} frames x ${c_frame:.4f} = ${cnt*c_frame:,.2f}   "
          f"(sonnet-5-5 {src}: ${pr['input']}/${pr['output']} per Mtok; 1 image ~1.6k tok + 450 prompt + 450 out)")
    P("  frame source for stream moments = a short video segment fetch at the timestamp (free, but ~800 h of video is NOT downloaded - only")
    P("  the few seconds around each moment); the transcript time is the caption time, +-3 s.")
    open(os.path.join(o, "summary.txt"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
