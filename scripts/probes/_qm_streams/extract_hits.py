#!/usr/bin/env python3
"""#702 P4b step 1b - ticker extraction from the stream auto-captions ($0: regex + pandas only).

For every video with a caption file: parse the VTT, find spoken tickers (words like 'mdgs', 'qpts', 'crs'; spelled
letters 'a m d'; Nasdaq-directory company names), validate each against the tickers that had bars within +-60 days of
the upload date, apply the collision stoplist, cluster mentions into moments and write OUT/stream_moments_raw.tsv.
Step 2 (match_bars.py) adds the Consolidation Breakout watch-row match.

Collision tiers (token, in the window's ticker set):
  A  not an English word, not a stream filler          -> kept
  B  an English word (/usr/share/dict/words), not a very common stream word -> kept only with a chart word in the window
  C  a very common stream word (document frequency >= DF_HARD of the caption videos, or the manual list)
                                                       -> kept only if the caption is ALL-CAPS AND a chart word is in the window
usage: extract_hits.py --out OUT --videos qm_videos.txt --closes daily_closes_all.csv.gz
"""
import argparse
import bisect
import csv
import datetime as dt
import math
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qmlib  # noqa: E402

DF_HARD = 0.25            # a ticker-shaped token in >= 25% of caption videos is a stream word, not a ticker
CLUSTER_GAP = 45.0        # mentions of one ticker within 45 s are one moment
WIN = 30.0
MAX_SPAN = 90.0
ACRONYM_IGNORE = set("""ep eps pr adr atr ath atl sma ema ma ipo ceo cfo cto etf etfs usa us uk eu fed gdp cpi ppi pe ps vs rs rsi
orh pm am ny nyc cnbc tv sec usd eur gbp jpy""".split())
MANUAL_STOP = set("""uh um gonna wanna gotta kinda yeah yep okay ok hmm mhm huh nah ya oh ah eh er so and the you
that this what with have are was for not but all can its dont didnt thats youre theyre isnt wasnt cant wont
one two three four five six seven eight nine ten big new old low high up down out off over now any
""".split())
NAME_STRIP = re.compile(r"\b(common stock|ordinary shares?|class [a-z]|american depositary (?:shares?|receipts?)|common shares?|"
                        r"inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|technologies|technology|"
                        r"international|llc|lp|n\.?v|s\.?a|trust|therapeutics|pharmaceuticals?|the|and)\b\.?")


def load_names(out):
    """Nasdaq-Trader symbol directories (free public files) -> alias -> {tickers}."""
    names = {}
    for fn, symi, namei, testi, etfi in (("nasdaqlisted.txt", 0, 1, 3, 6), ("otherlisted.txt", 0, 1, 6, 4)):
        p = os.path.join(out, fn)
        if not os.path.exists(p):
            continue
        for row in csv.reader(open(p, encoding="utf-8", errors="replace"), delimiter="|"):
            if len(row) <= max(symi, namei, testi, etfi) or row[0] in ("Symbol", "ACT Symbol") or row[0].startswith("File Creation"):
                continue
            if row[testi] == "Y" or row[etfi] == "Y":
                continue
            nm = row[namei].split(" - ")[0]
            if re.search(r"\b(warrants?|units?|rights?|preferred|notes?|depositary shares)\b", nm.lower()) and "common" not in nm.lower():
                continue
            names[row[symi].strip()] = nm
    return names


def build_aliases(names, dict_words, stop_words):
    core_by_alias = defaultdict(set)
    tick_by_alias = defaultdict(set)
    for t, nm in names.items():
        core = NAME_STRIP.sub(" ", nm.lower())
        core = re.sub(r"[^a-z ]", " ", core)
        toks = core.split()
        if not toks:
            continue
        cands = []

        def isdict(x):
            return x in dict_words or (x.endswith("s") and x[:-1] in dict_words)

        if len(toks[0]) >= 5 and not isdict(toks[0]) and toks[0] not in stop_words:
            cands.append(toks[0])
        if len(toks) >= 2 and len(toks[0]) >= 3 and len(toks[1]) >= 3 and not (isdict(toks[0]) and isdict(toks[1])) \
                and toks[0] not in stop_words and toks[1] not in stop_words:
            cands.append(toks[0] + " " + toks[1])
        for a in cands:
            core_by_alias[a].add(" ".join(toks[:2]))
            tick_by_alias[a].add(t)
    out = {}
    for a, ts in tick_by_alias.items():
        if len(core_by_alias[a]) == 1 or all(c.split()[0] == a.split()[0] for c in core_by_alias[a]) and " " not in a:
            out[a] = ts
    return out


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--videos", required=True)
    ap.add_argument("--closes", required=True)
    return ap.parse_args()


def main():
    a = parse_args()
    out = a.out
    log = {}
    for ln in open(os.path.join(out, "fetch_log.tsv"), encoding="utf-8"):
        p = ln.rstrip("\n").split("\t")
        if len(p) >= 5 and p[2] in ("ok", "nocaps", "fail"):
            if p[2] == "ok" or p[1] not in log or p[2] == "fail":
                log[p[1]] = (p[2], p[3], p[4], p[5] if len(p) > 5 else "")
    vids = []
    for ln in open(a.videos, encoding="utf-8"):
        if ln.strip():
            i, sec, title = ln.rstrip("\n").split("|", 2)
            vids.append((i, int(sec), title))
    uni = qmlib.load_universe(a.closes, os.path.join(out, "universe_dates.pkl"))
    bars_min = min(int(v[0]) for v in uni.values())
    bars_max = max(int(v[-1]) for v in uni.values())
    all_t = set(uni)
    dict_words = set(w.strip().lower() for w in open("/usr/share/dict/words", encoding="utf-8", errors="replace"))

    # 1. parse every caption file
    vt = {}
    info = {}
    for i, sec, title in vids:
        st, date, track, note = log.get(i, ("missing", "", "", ""))
        path = os.path.join(out, "subs", f"{i}.{track or 'en-orig'}.vtt")
        info[i] = dict(id=i, seconds=sec, title=title, status=st, upload_date=date, track=track, words=0, note=note[:140])
        if st == "ok" and os.path.exists(path):
            raw = qmlib.parse_vtt(path)
            toks = []
            for t, w in raw:
                lw = re.sub(r"[^A-Za-z0-9&.]", "", w.replace("’", "'")).strip(".")
                if not lw:
                    continue
                low = re.sub(r"'s$", "", w.lower().replace("’", "'"))
                low = re.sub(r"[^a-z0-9&.]", "", low).strip(".")
                caps = int(len(lw) >= 2 and lw.isupper() and lw.isalpha())
                if low:
                    toks.append((t, low, caps))
            vt[i] = toks
            info[i]["words"] = len(toks)
    cap_videos = [i for i in vt if vt[i]]
    print(f"{len(vids)} videos listed; {len(cap_videos)} with a caption file", flush=True)

    # 2. document frequency of every token (stream words)
    df = Counter()
    for i in cap_videos:
        df.update(set(t for _, t, _ in vt[i]))
    ndoc = max(1, len(cap_videos))
    stop_words = set(w for w, c in df.items() if c / ndoc >= DF_HARD) | MANUAL_STOP

    names = load_names(out)
    aliases = build_aliases(names, dict_words, stop_words)
    print(f"{len(names)} names, {len(aliases)} usable aliases; {len(stop_words)} stop words (df>={DF_HARD})", flush=True)

    # 3. per-video extraction
    rows = []
    for i in cap_videos:
        inf = info[i]
        d = inf["upload_date"]
        dord = dt.date(int(d[:4]), int(d[4:6]), int(d[6:8])).toordinal() if len(d) == 8 else None
        if dord is not None and dord + 60 >= bars_min:
            wset = qmlib.tickers_in_window(uni, dord, 60)
            bars_win = 1 if wset else 0
        else:
            wset, bars_win = set(), 0
        cand = wset if bars_win else all_t
        toks = vt[i]
        n = len(toks)
        ment = []                     # (t, ticker, via, caps)
        k = 0
        while k < n:
            t, w, caps = toks[k]
            # (a) spelled letters 'a m d'
            if len(w) == 1 and w.isalpha():
                j = k
                while j + 1 < n and len(toks[j + 1][1]) == 1 and toks[j + 1][1].isalpha() and toks[j + 1][0] - toks[j][0] <= 2.5 and j - k < 4:
                    j += 1
                if j > k:
                    sp = "".join(x[1] for x in toks[k:j + 1])
                    if sp.upper() in cand and 2 <= len(sp) <= 5 and len(set(sp)) >= 2 and set(sp) - {"a", "i"}:
                        ment.append((t, sp.upper(), "spelled", 1))
                    k = j + 1
                    continue
            # (b) ticker-shaped word
            if 2 <= len(w) <= 5 and w.isalpha() and w.upper() in cand:
                ment.append((t, w.upper(), "word", caps))
            elif w.isalpha() and len(w) >= 3:
                # (c) company-name alias, 1-gram then 2-gram
                if w in aliases:
                    ts = [x for x in aliases[w] if x in cand]
                    if ts:
                        ment.append((t, sorted(ts, key=lambda x: (len(x), x))[0], "name", 1))
                elif k + 1 < n:
                    bg = w + " " + toks[k + 1][1]
                    if bg in aliases:
                        ts = [x for x in aliases[bg] if x in cand]
                        if ts:
                            ment.append((t, sorted(ts, key=lambda x: (len(x), x))[0], "name", 1))
            k += 1
        # moments
        by_t = defaultdict(list)
        for m in ment:
            by_t[m[1]].append(m)
        times = [x[0] for x in toks]
        for tk, ms in by_t.items():
            ms.sort()
            clusters = [[ms[0]]]
            for m in ms[1:]:
                if m[0] - clusters[-1][-1][0] <= CLUSTER_GAP and m[0] - clusters[-1][0][0] <= 180:
                    clusters[-1].append(m)
                else:
                    clusters.append([m])
            for cl in clusters:
                t1, t2 = cl[0][0], cl[-1][0]
                w0, w1 = t1 - WIN, min(t2, t1 + MAX_SPAN) + WIN
                lo = bisect.bisect_left(times, w0)
                hi = bisect.bisect_right(times, w1)
                wtxt = " ".join(x[1] for x in toks[lo:hi])
                fl = qmlib.kw_flags(wtxt)
                chart = any(fl[x] for x in qmlib.CHART_KW)
                via = Counter(m[2] for m in cl).most_common(1)[0][0]
                caps_any = int(any(m[3] for m in cl))
                low = tk.lower()
                if low in ACRONYM_IGNORE and via != "name":
                    continue
                if via == "name":
                    tier = "N"
                elif low in stop_words:
                    tier = "C"
                elif len(low) == 2 or low in dict_words or (low.endswith("s") and low[:-1] in dict_words) or (low.endswith("es") and low[:-2] in dict_words):
                    tier = "B"                    # 2-letter tokens are abbreviations as often as tickers: soft like English words
                else:
                    tier = "A"
                if tier == "B" and not chart:
                    continue
                if tier == "C" and not (caps_any and chart):
                    continue
                if via == "spelled" and low in stop_words and not chart:
                    continue
                # near window flags (+-10 s of the first mention)
                nlo = bisect.bisect_left(times, t1 - 10)
                nhi = bisect.bisect_right(times, t1 + 15)
                ntxt = " ".join(x[1] for x in toks[nlo:nhi])
                nfl = qmlib.kw_flags(ntxt)
                strength = qmlib.kw_strength(fl) + 2 * sum(qmlib.KW_WEIGHT[x] for x in qmlib.CHART_KW if nfl[x]) + math.log2(len(cl) + 1)
                strength *= {"A": 1.0, "N": 0.7, "B": 0.8, "C": 0.6}[tier]
                # 1-line quote: +-10 s around the chart keyword nearest the first mention, else the mention
                tq = t1
                best = None
                for mm in qmlib.KW_RE["trendline"], qmlib.KW_RE["base"], qmlib.KW_RE["flag"], qmlib.KW_RE["tight"], qmlib.KW_RE["tightening"], qmlib.KW_RE["wedge"], qmlib.KW_RE["triangle"], qmlib.KW_RE["wick"], qmlib.KW_RE["draw"]:
                    m = mm.search(ntxt)
                    if m:
                        best = m
                        break
                qlo = bisect.bisect_left(times, tq - 9)
                qhi = bisect.bisect_right(times, tq + 14)
                quote = " ".join(x[1] for x in toks[qlo:qhi])[:240]
                rows.append(dict(video=i, upload_date=f"{d[:4]}-{d[4:6]}-{d[6:8]}", t=round(t1, 1), t_end=round(t2, 1),
                                 ts=f"{int(t1//3600):d}:{int(t1%3600//60):02d}:{int(t1%60):02d}", ticker=tk, via=via, tier=tier,
                                 caps=caps_any, mentions=len(cl), bars_window=bars_win,
                                 strength=round(strength, 2), chart_kw=int(chart), n_chart_kw=sum(fl[x] for x in qmlib.CHART_KW),
                                 near_chart=sum(nfl[x] for x in qmlib.CHART_KW),
                                 **{f"kw_{k}": v for k, v in fl.items()}, quote=quote, window=wtxt[:1600], title=inf["title"]))
        inf["hits"] = sum(1 for r in rows if r["video"] == i)
    cols = list(rows[0].keys()) if rows else []
    with open(os.path.join(out, "stream_moments_raw.tsv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        wr.writeheader()
        for r in rows:
            wr.writerow(r)
    with open(os.path.join(out, "video_status.tsv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["id", "seconds", "title", "status", "upload_date", "track", "words", "hits", "note"], delimiter="\t", extrasaction="ignore")
        wr.writeheader()
        for i in info:
            info[i].setdefault("hits", 0)
            wr.writerow(info[i])
    # diagnostics: the most common stream-vocabulary tokens that are also tickers
    with open(os.path.join(out, "stoplist_diag.tsv"), "w", encoding="utf-8") as f:
        f.write("token\tdoc_freq\tin_dict\thard_stop\tin_any_bars\n")
        for w, c in df.most_common(4000):
            if 2 <= len(w) <= 5 and w.isalpha() and w.upper() in all_t:
                f.write(f"{w}\t{c/ndoc:.3f}\t{int(w in dict_words)}\t{int(w in stop_words)}\t1\n")
    print(f"{len(rows)} moments -> stream_moments_raw.tsv", flush=True)


if __name__ == "__main__":
    main()
