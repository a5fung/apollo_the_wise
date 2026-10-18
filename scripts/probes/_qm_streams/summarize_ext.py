#!/usr/bin/env python3
"""#702 P4b extension - one-page EXT/summary_ext.txt from the step outputs ($0: pandas only). The HELD vision step is priced from
shared.llm_models.pricing_for via summarize.price_per_frame (a table lookup; nothing is called)."""
import argparse
import csv
import datetime as dt
import os
import random
import sys
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import summarize  # noqa: E402
import extract_hits_ext as xe  # noqa: E402
import ext_match  # noqa: E402

RECALL = ["TSLA", "ZM", "PTON", "NVDA", "AMD", "ROKU", "SQ", "ETSY", "NIO", "MDGL"]
HAND_SEED, HAND_N = 1018, 30


def num(s):
    return pd.to_numeric(s, errors="coerce")


def era_of(d):
    if d < "2021-08-01":
        return "1 before 2021-08 (Alpaca)"
    if d < "2022-03-28":
        return "2 2021-08..2022-03-27 (Alpaca)"
    return "3 2022-03-28 on (production watch rows)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/Users/alvinfung/apollo_data/cb702/qm_streams")
    ap.add_argument("--ext", default="/Users/alvinfung/apollo_data/cb702/qm_streams/ext_2016_2022")
    a = ap.parse_args()
    O, E = a.out, a.ext
    rd = lambda p, **k: pd.read_csv(p, sep="\t", keep_default_na=False, low_memory=False, **k)  # noqa: E731
    sm = rd(f"{E}/stream_moments_ext.tsv")
    ky = rd(f"{E}/kyna_notes_ext.tsv")
    lab = rd(f"{E}/labelled_candidates_ext.tsv")
    g = rd(f"{E}/symbol_guard.tsv")
    vs = rd(f"{O}/video_status.tsv", dtype={"upload_date": str})
    fp_sm = rd(f"{O}/stream_moments.tsv")
    fp_lab = rd(f"{O}/labelled_candidates.tsv")
    for c in ("c0", "chart_kw", "near_chart", "elig", "literal_flag", "strength"):
        sm[c] = num(sm[c]).fillna(0)
        if c in ky.columns:
            ky[c] = num(ky[c]).fillna(0)
    for c in ("c0", "chart_kw", "near_chart", "strength"):
        fp_sm[c] = num(fp_sm[c]).fillna(0)
    sm["era"] = sm.upload_date.map(era_of)
    sm["labelled"] = ((sm.c0 == 1) & (sm.chart_kw == 1)).astype(int)
    sm["source"] = "stream"
    sm["clean"] = (ext_match.clean_cut(sm) & (sm.labelled == 1)).astype(int)
    lab["hq"] = num(lab.hq).fillna(0)
    lab["literal_flag"] = num(lab.literal_flag).fillna(0)
    ls = lab[lab.source == "stream"]
    lk = lab[lab.source == "kyna"]
    L = []
    P = L.append
    P("#702 P4b EXTENSION - stream labels 2016-2022 on free Alpaca daily bars: summary ($0: no model call, no network, no prod)")
    P("=" * 110)
    okv = vs[vs.status == "ok"].copy()
    okv["era"] = okv.upload_date.map(lambda d: era_of(f"{d[:4]}-{d[4:6]}-{d[6:8]}"))
    P(f"BARS         Alpaca SIP daily 2016-01-04..2022-06-30: 10,958,104 rows / 9,971 symbols read; 0 duplicate (ticker,date) rows; "
      f"{int(rd(f'{E}/alp_build_stats.tsv', header=None).set_index(0).loc['zero_volume_rows_dropped', 1]):,} forward-filled zero-volume rows dropped "
      f"(a dormant symbol keeps printing its last close; Polygon has no row for a no-trade day either)")
    P("")
    P("COUNTS BY ERA  (moments = re-extracted with the recall fixes + precision rules; labelled = a C0 base in the 20 sessions before the talk AND a chart word;")
    P("                clean cut = labelled + chart word at the mention + a trusted name: spoken ticker (tier A), hand-reviewed allowlisted name, or a read-through company alias)")
    P(f"  {'era':<42}{'videos':>7}{'moments':>9}{'tier A':>8}{'eligible':>9}{'C0 base':>9}{'labelled':>9}{'clean':>7}")
    for e, grp in sorted(sm.groupby("era")):
        nv = int((okv.era == e).sum())
        el = int((grp.elig == 1).sum()) if e[0] != "3" else None
        P(f"  {e:<42}{nv:>7}{len(grp):>9}{int((grp.tier == 'A').sum()):>8}{(str(el) if el is not None else 'n/a'):>9}{int(grp.c0.sum()):>9}{int(grp.labelled.sum()):>9}{int(grp.clean.sum()):>7}")
    P(f"  {'ALL stream moments':<42}{int(len(okv)):>7}{len(sm):>9}{int((sm.tier == 'A').sum()):>8}{'':>9}{int(sm.c0.sum()):>9}{int(sm.labelled.sum()):>9}{int(sm.clean.sum()):>7}")
    P(f"  first pass (for comparison): 19,235 moments, 35 stream labelled, 12 clean (tier A only); Kyna rows now: {len(lk)} labelled (first pass 11)")
    P(f"  LABELLED TOTAL {len(lab)} = stream {len(ls)} + Kyna {len(lk)}; CLEAN CUT {int(lab.hq.sum())} = stream {int(ls.hq.sum())} + Kyna {int(lk.hq.sum())}; "
      f"distinct tickers in labelled {lab.ticker.nunique()}, distinct stock-bases (ticker + pole date) {lab.drop_duplicates(['ticker', 'w_pole_date']).shape[0]}")
    P("")
    alp = sm[sm.bars_source == "alpaca_split_c0only"]
    P("ELIGIBILITY (Alpaca-era moments, reported APART from 'no base'): a moment is eligible when >= 1 night in its 28-day window passes the universe (CS/ADRC or")
    P("  unknown type, raw close >= $5, 20-session median dollar volume >= $10M, >= 130 bars), the identity-break rule and 130 CONSECUTIVE sessions")
    el = alp[alp.elig == 1]
    P(f"  moments {len(alp):,}: eligible {len(el):,} ({len(el) / max(len(alp), 1):.0%}) -> C0 base {int(el.c0.sum()):,} | no base {len(el) - int(el.c0.sum()):,}")
    rs = alp[alp.elig != 1].elig_reason.value_counts()
    P("  NOT eligible " + f"{int((alp.elig != 1).sum()):,}: " + ", ".join(f"{k} {v}" for k, v in rs.items()) +
      "  (history_lt130 = <130 consecutive sessions; before ~2016-07 would be ineligible by construction - no talk is that early: the oldest video is 2017)")
    P("  sectype = ETFs / funds / non-common (small_pulls + SIC, as the runner resolves it); no_alpaca_series = a symbol Polygon has but Alpaca does not list")
    P("")
    nb = g.breaks != ""
    P("IDENTITY GUARD (per symbol, 9,944 symbols with traded bars)")
    P(f"  symbols with a break {int(nb.sum())} = hole (> 30 sessions with no trade; two issuers / long halt) {int((g['flags'].str.contains('hole')).sum())}, "
      f"jump (> 70% close move with no volume event, or a same-day factor change) {int((g['flags'].str.contains('jump')).sum())}; exclusion is PER NIGHT:")
    P("  a night is ineligible when a break falls inside the 130 bars it needs (NIO's pre-2018 junk, AA's 2016 Arconic split, DNB's 2019-20 gap are clean after the break).")
    P(f"  Polygon-overlap check (2021-09-27..2022-06-30, median gap > 2%): {int((g['flags'].str.contains('overlap')).sum())} symbols = constant-scale {int((g['flags'].str.contains('overlap_constant')).sum())} "
      f"(same series, different split factor) + polygon_reuse {int((g['flags'].str.contains('overlap_polygon')).sum())} (Alpaca continuous, the POLYGON side held another issuer: META, BNY) + "
      f"alpaca_break {int((g['flags'].str.contains('overlap_alpaca')).sum())}")
    lit_sym = int(((g.n_holes.astype(int) > 0) | (g.n_move70_nosplit.astype(int) > 0) | g['flags'].str.contains('overlap')).sum())
    P(f"  LITERAL rule from the brief (any hole > 30, any > 70% move with no split, any overlap gap, whole symbol excluded): {lit_sym} symbols. It would drop "
      f"{int((ls.literal_flag == 1).sum())} of {len(ls)} stream labelled and {int(((ls.literal_flag == 1) & (ls.hq == 1)).sum())} of {int(ls.hq.sum())} clean-cut ones "
      f"({ls[ls.literal_flag == 1].ticker.nunique()} tickers, e.g. {', '.join(ls[ls.literal_flag == 1].ticker.value_counts().head(6).index)}) - real EP-then-base names (NIO, GME, MDGL's 2018 pop). Not applied.")
    ib = int((alp.elig_reason == "identity_break").sum())
    P(f"  moments made ineligible by a break in their window: {ib}. Known cost: GME's Jan-2021 squeeze trips the jump test (its prior 20 sessions already had squeeze volume) - a few GME nights lost; noted, not tuned.")
    P("  Alpaca symbol history: FB 2020-06-01 closes 231.91 (Facebook, 1,620 bars 2016-01-04..2022-06-08, then nothing - the ProShares ETF now on FB is outside the window);")
    P("  META carries the IDENTICAL series (1,620 of 1,620 shared closes equal) and runs on to 2022-06-30. More: BNY = BNY Mellon's history (37.70 on 2020-06-01, 58.08 on 2021-12-31)")
    P("  while Polygon's BNY is a ~$14.78 muni trust (symbol reused); SQ is not an Alpaca symbol at all - Block sits under XYZ (161.51 on 2021-12-31 = Polygon SQ), resolved by a data-derived")
    P("  rename map (552 old->new symbols, matched on closes, nothing hand-listed); DNB prints 144.95 for 351 zero-volume sessions (2019-02-08..2020-06-30) then the 2020-07-01 re-IPO at 25.35 = a hole break.")
    P("  Limit: a reused symbol whose old issuer left BEFORE 2021-09-27 cannot be cross-checked against Polygon; only the hole / jump tests see it.")
    P("")
    P("CHECKS RUN (all in the repo scripts, $0)")
    P("  equivalence : extract_hits_ext.py --legacy reproduces extract_hits.py's stream_moments_raw.tsv exactly (19,235 moments, 0 differing cells), so the loop copy is faithful")
    for ln in open(f"{E}/parity.txt").read().splitlines():
        P("  " + ln.strip())
    P("")
    hr = rd(f"{E}/hand_read_ext.tsv")
    h1 = rd(f"{E}/hand_read_ext_round1.tsv")
    c2, c1 = Counter(hr.verdict), Counter(h1.verdict)
    nn = num(hr.near_chart) >= 1
    c2n, c2f = Counter(hr[nn].verdict), Counter(hr[~nn].verdict)
    # the sample must still be the sample the final labelled set yields
    ta = sm[(sm.labelled == 1) & (sm.tier == "A")].reset_index(drop=True)
    random.seed(HAND_SEED)
    pick = ta.iloc[sorted(random.sample(range(len(ta)), HAND_N))]
    same = list(zip(pick.video, pick.ts, pick.ticker)) == list(zip(hr.video, hr.ts, hr.ticker))
    P(f"PRECISION (hand-read, fixed seed {HAND_SEED}, {HAND_N} random tier-A labelled stream moments, +-30 s of caption; evidence: hand_read_ext.tsv)")
    P("  clear = what he says about the BASE is about this ticker | partial = this ticker but loosely (group statement, base as a price level, or two tickers in one breath) |")
    P("  wrong = the chart word is another stock's / an old trade / a unit, or the ticker token is not the stock")
    P(f"  FINAL read of the {len(ta):,} tier-A labelled set: clear {c2.get('clear', 0)}, partial {c2.get('partial', 0)}, wrong {c2.get('wrong', 0)} of {len(hr)}"
      f"  ->  {c2.get('clear', 0) / len(hr):.0%} clear, {c2.get('wrong', 0) / len(hr):.0%} wrong")
    P(f"  chart word AT the mention (the clean cut): clear {c2n.get('clear', 0)}, partial {c2n.get('partial', 0)}, wrong {c2n.get('wrong', 0)} of {int(nn.sum())};"
      f"  chart word only somewhere in the +-30 s window: clear {c2f.get('clear', 0)}, partial {c2f.get('partial', 0)}, wrong {c2f.get('wrong', 0)} of {int((~nn).sum())}")
    P(f"  earlier read BEFORE the cruise-line fix (same seed, 1,317-moment set): clear {c1.get('clear', 0)}, partial {c1.get('partial', 0)}, wrong {c1.get('wrong', 0)} of 30 - 4 of the 10 wrong were 'cruise line(s)'; fixed, then re-sampled and re-read.")
    P("  Remaining wrong: the chart word belongs to a NEIGHBOURING stock (9 of 10; 8 of them named just before) or the ticker is an ordinary word (MINI). Use the clean cut, not the whole labelled set.")
    if not same:
        P("  !! WARNING: the sampled rows no longer match hand_read_ext.tsv - the labelled set changed after the read; re-read before trusting these numbers.")
    hn = rd(f"{E}/hand_read_names.tsv")
    cn = Counter(hn.verdict)
    tn = sm[(sm.labelled == 1) & (sm.tier == "N") & (sm.clean == 1)].reset_index(drop=True)
    random.seed(HAND_SEED + 1)
    pick_n = tn.iloc[sorted(random.sample(range(len(tn)), len(hn)))]
    same_n = list(zip(pick_n.video, pick_n.ts, pick_n.ticker)) == list(zip(hn.video, hn.ts, hn.ticker))
    P(f"  NAME-BASED clean cut (allowlisted + read-through company names, tier N, {len(tn)} moments; seed {HAND_SEED + 1}, {len(hn)} read; hand_read_names.tsv): "
      f"clear {cn.get('clear', 0)}, partial {cn.get('partial', 0)}, wrong {cn.get('wrong', 0)} of {len(hn)}")
    if not same_n:
        P("  !! WARNING: the name-sample rows no longer match hand_read_names.tsv - re-read before trusting.")
    P("")
    P("RECALL (moments / with a chart word / labelled / clean cut;  first pass in brackets: moments / labelled)")
    P(f"  {'ticker':<7}{'moments':>8}{'chart wd':>9}{'labelled':>9}{'clean':>7}   first pass")
    for t in RECALL:
        x = sm[sm.ticker == t]
        f1 = fp_sm[fp_sm.ticker == t]
        fl = fp_lab[(fp_lab.ticker == t) & (fp_lab.source == "stream")]
        P(f"  {t:<7}{len(x):>8}{int((x.chart_kw == 1).sum()):>9}{int(x.labelled.sum()):>9}{int(x.clean.sum()):>7}   ({len(f1)} / {len(fl)})")
    ah = [ln.split("\t") for ln in open(f"{E}/ext_extract_diag.txt").read().split("allowlisted name")[1].split("\n\n")[0].splitlines()[1:] if ln.strip()]
    n_allow = sum(int(x[2]) for x in ah)
    n_rej = sum(len(v) for v in xe.ALIAS_REVIEW.values())
    ac = rd(f"{E}/alias_candidates.tsv")
    dropped_ac = ac[ac.dropped_by != "kept"]
    P(f"  recall fixes: alias_candidates.tsv ranks the first words of LIQUID companies by caption videos ({len(ac)} candidates, {len(dropped_ac)} dropped by the first-pass rule); the top 100 ({dropped_ac.videos.iloc[0]} -> {dropped_ac.videos.iloc[99]} videos) are all")
    P(f"  decided in code (extract_hits_ext.ALLOW_* / ALIAS_REVIEW, {n_rej} rejected words with a reason), KWIC-checked for the plausible ~50; {len(xe.ALLOW_UNI)} single names + {len(xe.ALLOW_BI)} two-word names allowlisted")
    P(f"  (8 from the top 100; 6 more from ranks 101-200; 'square' and 'facebook' are historical names no current-name file holds; 'nioh' = the captions' spelling of NIO, 159 tokens vs 319 for 'nio').")
    P(f"  {n_allow} allowlisted-name moments kept after the chart-word-at-the-mention rule and the precision rules ('square' -> SQ trades on XYZ's bars via the rename map).")
    P("")
    P("HELD STEP 3 (vision read of the chart frame at the moment - NOT RUN). Price = sonnet-5-5 from shared.llm_models.pricing_for(), 1 image ~1.6k tok + 450 prompt + 450 out")
    kimgs_all = int(num(lk.n_images).fillna(0).clip(upper=3).sum()) if "n_images" in lk.columns else 0
    kimgs_hq = int(num(lk[lk.hq == 1].n_images).fillna(0).clip(upper=3).sum()) if "n_images" in lk.columns else 0
    cf, pr, src = summarize.price_per_frame()
    for label, ns, nk, nimg in (("WHOLE labelled set", len(ls), len(lk), kimgs_all), ("CLEAN CUT", int(ls.hq.sum()), int(lk.hq.sum()), kimgs_hq)):
        tot = ns + nimg
        P(f"  {label:<20}: {ns:>5} stream frames (a short video segment fetched at the timestamp) + {nimg:>3} Kyna images already posted ({nk} rows) = {tot:>5} frames x ${cf:.4f} = ${tot * cf:,.2f}")
    sb = ls.drop_duplicates(["ticker", "w_pole_date"]).shape[0]
    P(f"  one frame per distinct stock-base would be {sb} stream frames = ${sb * cf:,.2f}.  ({src}: ${pr['input']}/${pr['output']} per Mtok.)")
    P("")
    P("TOP 40 LABELLED (clean cut first, then strength; max 2 per ticker).  ticker | talk date | video@time | kw | base state | base_len | quote")
    P("     features of the matching night: depth / tighten ratio / trendline slope % / interior touches / retrace / trigger-bar range in ADR / higher lows")
    top = lab.copy()
    top["strength"] = num(top.strength).fillna(0)
    top = top.sort_values(["hq", "strength"], ascending=[False, False])
    top["rank_t"] = top.groupby("ticker").cumcount()
    top = top[top.rank_t < 2].head(40)

    def f(v, nd=2):
        try:
            return f"{float(v):.{nd}f}"
        except (TypeError, ValueError):
            return "-"
    for _, r in top.iterrows():
        q = str(r.quote1)[:120].replace("\n", " ")
        P(f"  {r.ticker:<5} {r.ref_date} {str(r['where'])[:26]:<26} [{r.kw_list[:34]}] {r.status_at_ref} L={r.w_base_len} | {q}")
        P(f"         depth {f(r.w_base_depth)} tight {f(r.w_tightening_ratio)} tl_slope {f(r.w_tl_slope_pct, 3)} tl_touch {r.w_tl_interior_touches} retr {f(r.w_retrace)} "
          f"trig {f(r.w_trigger_bar_range_adr)} hi_lows {r.w_higher_lows}  [{r.bars_source}{', clean cut' if r.hq == 1 else ''}]")
    P("")
    P("NOT DONE / LIMITS")
    P("  - Alpaca's asset list omits many delisted names (ABMD, ABC, TWTR, ATVI, SGEN, NLSN...): a spoken ticker with no Alpaca series cannot be matched before 2022-03-28 (see ext_extract_diag.txt).")
    P("  - A symbol later reused by a new issuer (SPWR, ...) can show the new issuer's short history in the old era: moments there fail the window or history tests.")
    P("  - Talks on or after 2022-03-28 still use the production watch rows (Polygon bars) - unchanged first-pass path; their eligibility is not itemised.")
    P("  - Breakout existence uses the same K levels (k5 / k10 / full / trendline) and next-session test as the runner's candidates (identical on 100% of 2,015 checked nights); first entry day only, no trade outcome read.")
    P("  - Inherited first-pass bug, NOT touched (that path is held intact): `match_bars.match_one` keys breakouts by pole date but candidates.tsv uses a drift-robust chain id, so for talks on or after")
    P("    2022-03-28 a base whose pole drifted one session can read 'no breakout' (97 of 483 both-C0 cases read none on the first-pass path while the Alpaca path finds a breakout;")
    P("    the two inspected, MAR and LAND, were exactly this key mismatch - the rest are unverified). The Alpaca path does not have it.")
    P("  - Company-name matching: names from the Nasdaq files stay current-only; the hand-reviewed allowlist adds the dictionary-word names (and 'facebook', 'square', 'nioh').")
    P("  - Vision frames, trade outcomes and RS / group / phase are out of scope (held / null): every Alpaca-era row is 'C0-only, Alpaca bars'.")
    open(f"{E}/summary_ext.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
