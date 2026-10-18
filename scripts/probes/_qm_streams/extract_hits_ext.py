#!/usr/bin/env python3
"""#702 P4b extension, step 1 - ticker extraction from the stream auto-captions with the recall fixes and precision rules
($0: regex + pandas only; no network, no model call). The first-pass tiers (A / B / C / N and their chart-word rules) are
reproduced unchanged and only ADDED to; `--legacy` switches every addition off so the loop can be diffed against
`extract_hits.py`'s own output (the equivalence check in the summary).

Additions over `extract_hits.py`:
 1a  recall: a hand-reviewed ALLOWLIST of company names that are dictionary words ("tesla", "zoom", "peloton"...). Review of the
     top 100 dropped first words (liquid companies only, ranked by caption video count) is recorded in ALIAS_REVIEW; everything
     not allowed was rejected for a reason (a common word in stream speech: "target", "five", "gap"...). An allowlisted name
     counts only with a chart word at the mention (near_chart), is tier N, and a per-name context rule drops "zoom in".
 1b  validation: a spoken ticker is validated against the symbols with ALPACA bars within +-60 days of the upload date UNION the
     Polygon list (the first pass used Polygon only, so every delisted name before 2021-08 was invisible: WORK = Slack). Renamed
     symbols resolve through the data-derived rename map (SQ -> XYZ).
 3   precision (the first card's hand-read found 16 of 35 wrong):
       - drop a moment when a year word (2015-2023, "last year") or a month name sits within +-10 s of the mention (his "back in
         October 2021" recalls of old trades). "may" / "march" are also verbs, so they count only when a number follows or
         in/of/since/last/early/late/mid/until precedes;
       - "tight" / "tighten*" is not a chart word when "stop" / "stops" is within 3 tokens ("tighten up my stops");
       - "line(s)" is not a chart word after cruise / fuel / bottom / front / assembly / production / pipe ("cruise lines" were 31 % of
         all its uses and 4 of the 10 wrong moments in the first 30-moment hand-read).
usage: extract_hits_ext.py --out QM_DIR --ext EXT_DIR --videos qm_videos.txt [--legacy]
"""
import argparse
import bisect
import csv
import datetime as dt
import math
import os
import pickle
import re
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_hits as eh  # noqa: E402
import qmlib  # noqa: E402

# ---------------------------------------------------------------- the reviewed allowlist (1a)
# word -> (tickers, reject_next, reject_prev). Tickers are what he SAID at the time (SQ, not XYZ; FB, not META).
ALLOW_UNI = {
    "tesla": (["TSLA"], set(), set()),
    "zoom": (["ZM"], {"in", "out", "into", "up", "over", "back"}, set()),          # "let me zoom in" is the verb
    "peloton": (["PTON"], set(), set()),
    "amazon": (["AMZN"], set(), set()),
    "apple": (["AAPL"], set(), set()),
    "ford": (["F"], set(), set()),
    "celsius": (["CELH"], set(), {"degrees", "degree"}),                              # "30 degrees celsius" is the unit
    "lucid": (["LCID"], set(), set()),
    "chewy": (["CHWY"], set(), set()),
    "lemonade": (["LMND"], set(), set()),
    "riot": (["RIOT"], set(), set()),                                                 # a ticker-shaped word in the stop list (tier C
    "plug": (["PLUG"], {"it", "in", "up", "into", "that", "this", "the", "a", "them", "out"}, set()),  # needs CAPS: unreachable)
    "blink": (["BLNK"], set(), set()),
    "macy": (["M"], set(), set()),
    "square": (["SQ"], {"one", "foot", "feet", "mile", "miles", "up", "off"}, set()),
    "facebook": (["FB"], {"marketplace", "friend", "friends", "account", "page", "messenger"}, set()),   # historical name (not in assets.tsv)
    "nioh": (["NIO"], set(), set()),          # the captions' spelling of NIO (159 tokens in 66 videos vs 319 for "nio"); the game never comes up
}
ALLOW_BI = {                                                                           # two-word names whose parts are both dictionary words
    "beyond meat": ["BYND"], "shake shack": ["SHAK"], "general motors": ["GM"], "dollar tree": ["DLTR"],
    "first solar": ["FSLR"], "royal caribbean": ["RCL"], "norwegian cruise": ["NCLH"], "planet fitness": ["PLNT"],
}
# Review record of the top-100 dropped candidates (word: why it is NOT allowlisted). The allowed ones are ALLOW_UNI / ALLOW_BI.
ALIAS_REVIEW = {
    "generic word in stream speech (no company reading)": """the all one bit trade great range nice five high take moving money first four better
        super new open people news support hope six best mid build care happen extended red green line china clean old main top
        life check world star ready gold oil business nine space power ideal fuel pattern energy mega smart sound pop white waste
        solid air forward science future agree preferred service forty tech ultra site liquidity retail stars team system paper
        steel iron clear bank equity blue black sun state smith lucky turning gaming pool choice cars community grand core ball
        fifth gain natural global trip office alpha bio customers finance option selective safe party champion context
        education performance hello jones public east nano post meet honest""".split(),
    "dominant non-company sense in the captions (KWIC-checked)": """target(price target) gap(gap up) dollar(dollar volume) under home
        general capital live lowe(mis-hear of 'low') genius bill box dow(dow jones) monster block strategy toast rocket(rocket
        science) monday(day) shake(shake out) twitter(on twitter) google(verb) interactive(his broker account)
        take(take two) mara roku pdd etsy uber amc snap(already resolve as spoken tickers: tier B)""".split(),
}
# first-pass N-tier aliases that are plain words in stream speech (tightening only)
NAME_IGNORE_EXT = {"marcus", "installed", "camping", "korea", "taiwan", "desktop", "midcap", "campbell",
                   "sykes", "patterson", "solaris", "centerpoint"}      # Tim Sykes, people's names, 'solar'-ish plurals, his broker CenterPoint
# first-pass N-tier alias words (>= 5 caption videos) read through and judged to be the company in stream speech: they join the CLEAN CUT
# when a chart word sits at the mention (ext_match.clean_cut). Not here: intel (the word), and the noise words ignored above.
N_REVIEWED_OK = set("""shopify nvidia fastly draftkings netflix pinterest crowdstrike workhorse twilio livongo tilray palantir microsoft
    carvana airbnb spotify baidu fiverr roblox paypal fuelcell pfizer jumia boeing coinbase zillow gilead gopro robinhood gamestop dexcom
    goldman mcdonald moderna wayfair groupon mongodb sabre walmart amgen netease rivian alcoa fitbit""".split())

YEARS = {str(y) for y in range(2015, 2024)}
MONTHS = {"january", "february", "april", "june", "july", "august", "september", "october", "november", "december"}
MONTH_SOFT = {"may", "march"}
MONTH_PREV = {"in", "of", "since", "last", "early", "late", "mid", "until"}
NUM_RE = re.compile(r"^\d+(st|nd|rd|th)?$")
TIGHT_RE = re.compile(r"^tight(?:er|ly|en|ens|ened|ening)?$")
STOP_WORDS_NEAR = {"stop", "stops"}
# "line" is a chart word (trend line, magic line, yellow line) but in 2020 "cruise line(s)" is 278 of its 895 uses; the other prefixes
# are the same non-chart sense. Found by the 30-moment hand-read: 4 of its 10 wrong moments were "cruise line".
LINE_NONCHART_PREV = {"cruise", "cruises", "fuel", "bottom", "front", "assembly", "production", "pipe"}


def load_tokens(out, ext, vids):
    """{video: (upload_date, [(t, word, caps)])} from the VTT files; cached in EXT/tokens_cache.pkl."""
    cache = os.path.join(ext, "tokens_cache.pkl")
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    log = {}
    for ln in open(os.path.join(out, "fetch_log.tsv"), encoding="utf-8"):
        p = ln.rstrip("\n").split("\t")
        if len(p) >= 5 and p[2] == "ok":
            log[p[1]] = (p[3], p[4])
    vt = {}
    for i, _, _ in vids:
        if i not in log:
            continue
        date, track = log[i]
        path = os.path.join(out, "subs", f"{i}.{track or 'en-orig'}.vtt")
        if not os.path.exists(path):
            continue
        toks = []
        for t, w in qmlib.parse_vtt(path):
            lw = re.sub(r"[^A-Za-z0-9&.]", "", w.replace("’", "'")).strip(".")
            if not lw:
                continue
            low = re.sub(r"'s$", "", w.lower().replace("’", "'"))
            low = re.sub(r"[^a-z0-9&.]", "", low).strip(".")
            caps = int(len(lw) >= 2 and lw.isupper() and lw.isalpha())
            if low:
                toks.append((t, low, caps))
        vt[i] = (date, toks)
    pickle.dump(vt, open(cache, "wb"))
    return vt


def alpaca_universe(ext):
    """{symbol: sorted ordinals} from the traded-bars cache, plus the rename aliases (old symbol -> the new symbol's dates)."""
    import ext_bars
    a = ext_bars.load(ext)
    uni = {}
    for k, t in enumerate(a["tickers"]):
        uni[str(t)] = a["d"][int(a["start"][k]):int(a["stop"][k])]
    ren = {}
    p = os.path.join(ext, "rename_map.tsv")
    if os.path.exists(p):
        for ln in open(p).read().splitlines()[1:]:
            old, new, _ = ln.split("\t")
            if old not in uni and new in uni:
                uni[old] = uni[new]
                ren[old] = new
    return uni, ren


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--ext", required=True)
    ap.add_argument("--videos", required=True)
    ap.add_argument("--legacy", action="store_true", help="switch every addition off (equivalence check vs extract_hits.py)")
    ap.add_argument("--tag", default="")
    return ap.parse_args()


def main():
    a = parse_args()
    out, ext = a.out, a.ext
    legacy = a.legacy
    vids = []
    for ln in open(a.videos, encoding="utf-8"):
        if ln.strip():
            i, sec, title = ln.rstrip("\n").split("|", 2)
            vids.append((i, int(sec), title))
    title_of = {i: t for i, _, t in vids}
    vt = load_tokens(out, ext, vids)
    cap_videos = [i for i in vt if vt[i][1]]
    print(f"{len(vids)} videos listed; {len(cap_videos)} with a caption file", flush=True)

    poly_uni = qmlib.load_universe(None, os.path.join(out, "universe_dates.pkl"))
    all_poly = set(poly_uni)
    alp_uni, ren = alpaca_universe(ext)
    bars_min = min(int(v[0]) for v in poly_uni.values())

    dict_words = set(w.strip().lower() for w in open("/usr/share/dict/words", encoding="utf-8", errors="replace"))

    def dictish(w):
        return w in dict_words or (w.endswith("s") and w[:-1] in dict_words) or (w.endswith("es") and w[:-2] in dict_words)

    df = Counter()
    for i in cap_videos:
        df.update(set(t for _, t, _ in vt[i][1]))
    ndoc = max(1, len(cap_videos))
    stop_words = set(w for w, c in df.items() if (c / ndoc >= eh.DF_HARD and dictish(w)) or c / ndoc >= eh.DF_NONDICT) | eh.MANUAL_STOP
    names = eh.load_names(out)
    if not legacy:
        eh.NAME_IGNORE.update(NAME_IGNORE_EXT)
    aliases = eh.build_aliases(names, dict_words, stop_words)
    print(f"{len(names)} names, {len(aliases)} usable aliases; {len(stop_words)} stop words", flush=True)

    rows = []
    dropped = []
    diag = Counter()
    allow_hits = Counter()
    lost_not_in_alpaca = Counter()
    for i in cap_videos:
        d, toks = vt[i]
        dord = dt.date(int(d[:4]), int(d[4:6]), int(d[6:8])).toordinal() if len(d) == 8 else None
        wset_p = qmlib.tickers_in_window(poly_uni, dord, 60) if (dord is not None and dord + 60 >= bars_min) else set()
        wset_a = qmlib.tickers_in_window(alp_uni, dord, 60) if dord is not None and not legacy else set()
        wset = wset_p | wset_a
        bars_win = 1 if wset else 0
        cand = wset if bars_win else set(all_poly)
        n = len(toks)
        times = [x[0] for x in toks]
        ws = [x[1] for x in toks]
        # tokens that are NOT chart words: tight* with stop/stops within 3 tokens
        mw = list(ws)
        if not legacy:
            for k in range(n):
                if ws[k] in ("line", "lines") and k and ws[k - 1] in LINE_NONCHART_PREV:
                    mw[k] = "_"
                    diag["line_masked_tokens"] += 1
                if TIGHT_RE.match(ws[k]):
                    if any(ws[j] in STOP_WORDS_NEAR for j in range(max(0, k - 3), min(n, k + 4)) if j != k):
                        mw[k] = "_"
                        diag["tight_masked_tokens"] += 1
        ment = []                                         # (t, ticker, via, caps)
        k = 0
        while k < n:
            t, w, caps = toks[k]
            if len(w) == 1 and w.isalpha():
                j = k
                while j + 1 < n and len(toks[j + 1][1]) == 1 and toks[j + 1][1].isalpha() and toks[j + 1][0] - toks[j][0] <= 2.5 and j - k < 4:
                    j += 1
                if j > k:
                    sp = "".join(x[1] for x in toks[k:j + 1])
                    if sp.upper() in cand and 2 <= len(sp) <= 5 and len(set(sp)) >= 2 and set(sp) - {"a", "i"}:
                        ment.append((t, sp.upper(), "spelled", 1, ""))
                    k = j + 1
                    continue
            if not legacy:
                if w in ALLOW_UNI:                         # a reviewed name: handled here ONLY (never the ticker / alias path)
                    tks, rn, rp = ALLOW_UNI[w]
                    nx = ws[k + 1] if k + 1 < n else ""
                    pv = ws[k - 1] if k else ""
                    if nx in rn or pv in rp:
                        diag["allow_context_rejected"] += 1
                    else:
                        tt = [x for x in tks if x in cand]
                        if tt:
                            ment.append((t, tt[0], "name_allow", 1, w))
                    k += 1
                    continue
                if k + 1 < n and (w + " " + ws[k + 1]) in ALLOW_BI:
                    tt = [x for x in ALLOW_BI[w + " " + ws[k + 1]] if x in cand]
                    if tt:
                        ment.append((t, tt[0], "name_allow", 1, w + " " + ws[k + 1]))
                    k += 2
                    continue
            if 2 <= len(w) <= 5 and w.isalpha() and w.upper() in cand:
                ment.append((t, w.upper(), "word", caps, ""))
            elif w.isalpha() and len(w) >= 3:
                if w.upper() in all_poly and 2 <= len(w) <= 5 and not dictish(w) and dord is not None and dord < dt.date(2022, 3, 28).toordinal():
                    lost_not_in_alpaca[w.upper()] += 1
                if w in aliases:
                    ts = [x for x in aliases[w] if x in cand]
                    if ts:
                        ment.append((t, sorted(ts, key=lambda x: (len(x), x))[0], "name", 1, w))
                elif k + 1 < n:
                    bg = w + " " + toks[k + 1][1]
                    if bg in aliases:
                        ts = [x for x in aliases[bg] if x in cand]
                        if ts:
                            ment.append((t, sorted(ts, key=lambda x: (len(x), x))[0], "name", 1, bg))
            k += 1
        by_t = defaultdict(list)
        for m in ment:
            by_t[m[1]].append(m)
        for tk, ms in by_t.items():
            ms.sort()
            clusters = [[ms[0]]]
            for m in ms[1:]:
                if m[0] - clusters[-1][-1][0] <= eh.CLUSTER_GAP and m[0] - clusters[-1][0][0] <= 180:
                    clusters[-1].append(m)
                else:
                    clusters.append([m])
            for cl in clusters:
                t1, t2 = cl[0][0], cl[-1][0]
                w0, w1 = t1 - eh.WIN, min(t2, t1 + eh.MAX_SPAN) + eh.WIN
                lo = bisect.bisect_left(times, w0)
                hi = bisect.bisect_right(times, w1)
                wtxt = " ".join(ws[lo:hi])
                fl = qmlib.kw_flags(" ".join(mw[lo:hi]))
                chart = any(fl[x] for x in qmlib.CHART_KW)
                via = Counter(m[2] for m in cl).most_common(1)[0][0]
                caps_any = int(any(m[3] for m in cl))
                low = tk.lower()
                if low in eh.ACRONYM_IGNORE and via not in ("name", "name_allow"):
                    continue
                allow = int(via == "name_allow")
                name_word = next((m[4] for m in cl if m[2] == via and m[4]), "")
                if via in ("name", "name_allow"):
                    tier = "N"
                elif low in stop_words:
                    tier = "C"
                elif len(low) == 2 or dictish(low):
                    tier = "B"
                else:
                    tier = "A"
                nlo = bisect.bisect_left(times, t1 - 10)
                nhi = bisect.bisect_right(times, t1 + 15)
                ntxt = " ".join(mw[nlo:nhi])
                nfl = qmlib.kw_flags(ntxt)
                near = any(nfl[x] for x in qmlib.CHART_KW)
                if tier == "B" and not near:
                    continue
                if tier == "C" and not (caps_any and near):
                    continue
                if via == "spelled" and low in stop_words and not near:
                    continue
                if allow and not near:
                    diag["allow_no_near_dropped"] += 1
                    continue
                if not legacy:                                 # precision rule: a year / month word at the mention = a recall of an old trade
                    a0 = bisect.bisect_left(times, t1 - 10)
                    a1 = bisect.bisect_right(times, t2 + 10)
                    why = None
                    for q in range(a0, a1):
                        x = ws[q]
                        if x in YEARS:
                            why = "year"
                        elif x == "last" and q + 1 < n and ws[q + 1] == "year":
                            why = "last_year"
                        elif x in MONTHS:
                            why = "month"
                        elif x in MONTH_SOFT:
                            nx = ws[q + 1] if q + 1 < n else ""
                            pv = ws[q - 1] if q else ""
                            if NUM_RE.match(nx) or pv in MONTH_PREV:
                                why = "month"
                        if why:
                            break
                    if why:
                        diag["dropped_" + why] += 1
                        dropped.append((i, f"{int(t1 // 3600)}:{int(t1 % 3600 // 60):02d}:{int(t1 % 60):02d}", tk, tier, via, why, int(chart and near)))
                        continue
                strength = qmlib.kw_strength(fl) + 2 * sum(qmlib.KW_WEIGHT[x] for x in qmlib.CHART_KW if nfl[x]) + math.log2(len(cl) + 1)
                strength *= {"A": 1.0, "N": 0.7, "B": 0.8, "C": 0.6}[tier]
                qlo = bisect.bisect_left(times, t1 - 9)
                qhi = bisect.bisect_right(times, t1 + 14)
                quote = " ".join(ws[qlo:qhi])[:240]
                if allow:
                    allow_hits[(low, tk)] += 1
                rows.append(dict(video=i, upload_date=f"{d[:4]}-{d[4:6]}-{d[6:8]}", t=round(t1, 1), t_end=round(t2, 1),
                                 ts=f"{int(t1 // 3600):d}:{int(t1 % 3600 // 60):02d}:{int(t1 % 60):02d}", ticker=tk, via=via, tier=tier,
                                 caps=caps_any, mentions=len(cl), bars_window=bars_win,
                                 strength=round(strength, 2), chart_kw=int(chart), n_chart_kw=sum(fl[x] for x in qmlib.CHART_KW),
                                 near_chart=sum(nfl[x] for x in qmlib.CHART_KW),
                                 **{f"kw_{kk}": v for kk, v in fl.items()}, quote=quote, window=wtxt[:1600], title=title_of.get(i, ""),
                                 bars_symbol=ren.get(tk, tk), allow=allow, name_word=name_word))
    cols = list(rows[0].keys()) if rows else []
    suffix = "_legacy" if legacy else ""
    path = os.path.join(ext, f"stream_moments_ext_raw{suffix}.tsv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        wr.writeheader()
        for r in rows:
            wr.writerow(r)
    if not legacy:
        with open(os.path.join(ext, "dropped_precision.tsv"), "w", encoding="utf-8") as f:
            f.write("video\tts\tticker\ttier\tvia\treason\tchart_at_mention\n")
            for r in dropped:
                f.write("\t".join(str(x) for x in r) + "\n")
        with open(os.path.join(ext, "ext_extract_diag.txt"), "w", encoding="utf-8") as f:
            for k_, v_ in sorted(diag.items()):
                f.write(f"{k_}\t{v_}\n")
            f.write("\nallowlisted name -> ticker : moments kept (near_chart satisfied, precision rules applied)\n")
            for (w_, t_), c_ in sorted(allow_hits.items(), key=lambda x: -x[1]):
                f.write(f"{w_}\t{t_}\t{c_}\n")
            f.write("\nspoken ticker-shaped words that are Polygon tickers with NO Alpaca series (pre 2022-03-28 videos; coverage gap) top 40\n")
            for t_, c_ in lost_not_in_alpaca.most_common(40):
                f.write(f"{t_}\t{c_}\n")
    print(f"{len(rows)} moments -> {path}; dropped by precision rules {len(dropped)}; diag {dict(diag)}", flush=True)


if __name__ == "__main__":
    main()
