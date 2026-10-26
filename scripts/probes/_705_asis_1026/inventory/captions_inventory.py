#!/usr/bin/env python3
"""#705 as-is reverse-engineering, inventory 1: how usable are his stream captions as the
step-6 reference ("check the inferred entry/exit points against what he said on stream").

MEASURE ONLY. Reads the local YouTube auto-caption files; no network, no paid call, no data
after 2024-12-31 (captions end 2023-12). Our rule library is NOT used anywhere here.

Stages (each re-runnable):
  extract  parse 495 .vtt -> de-duplicated word streams -> candidate trade statements (counts)
  draw     draw the fixed sample (seed 705) -> caption_sample.tsv (labels blank) + context file
  account  collect account / yearly / monthly result candidates for hand review
  report   read the hand labels -> yields + intervals + coverage -> captions.md

  python captions_inventory.py extract
  python captions_inventory.py draw            # refuses to overwrite a labelled sample
  python captions_inventory.py account
  python captions_inventory.py report
"""
import argparse
import bisect
import collections
import csv
import datetime as dt
import glob
import math
import os
import random
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
STREAMS = "/Users/alvinfung/apollo_data/cb702/qm_streams"
SUBS = os.path.join(STREAMS, "subs")
STATUS = os.path.join(STREAMS, "video_status.tsv")
WORK = os.environ.get("INV_WORK", os.path.join(tempfile.gettempdir(), "cb705_captions_inventory"))
SAMPLE_TSV = os.path.join(HERE, "caption_sample.tsv")
ACCOUNT_TSV = os.path.join(HERE, "account_statements.tsv")
REPORT_MD = os.path.join(HERE, "captions.md")
SEED = 705
N_SAMPLE = 120
SEALED_AFTER = "20241231"  # nothing dated after this is read (captions end 2023-12 anyway)

# ----------------------------------------------------------------------------------------
# 1. parse the captions into a word stream (t_seconds, word), without the rolling repeats
# ----------------------------------------------------------------------------------------
TS = re.compile(r"^(\d+):(\d\d):(\d\d)\.(\d{3}) --> (\d+):(\d\d):(\d\d)\.(\d{3})")
TAGSPLIT = re.compile(r"(<\d+:\d\d:\d\d\.\d{3}>)")
TAGVAL = re.compile(r"<(\d+):(\d\d):(\d\d)\.(\d{3})>")


def _sec(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt(path):
    """YouTube auto-captions roll: every cue repeats the previous line and adds one new line
    (the new line carries per-word <time> tags); a 10 ms cue then re-prints the finished line.
    Keep only the LAST line of each cue that lasts > 50 ms -> each spoken word appears once."""
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    out, i = [], 0
    while i < len(lines):
        m = TS.match(lines[i])
        if not m:
            i += 1
            continue
        st = _sec(*m.groups()[:4])
        en = _sec(*m.groups()[4:])
        j, body = i + 1, []
        while j < len(lines) and lines[j] != "":
            body.append(lines[j])
            j += 1
        i = j
        if en - st <= 0.05:
            continue
        body = [b for b in body if b.strip() != ""]
        if not body:
            continue
        t = st
        for p in TAGSPLIT.split(body[-1]):
            if TAGSPLIT.fullmatch(p):
                t = _sec(*TAGVAL.match(p).groups())
            else:
                for w in re.sub(r"</?c>", "", p).split():
                    out.append((t, w))
    return out


def norm_tok(w):
    w = w.lower().replace("\u2019", "'").replace("\u2018", "'")
    w = re.sub(r"&nbsp;?", " ", w)
    w = re.sub(r"[^a-z0-9'%$.&/\-]", "", w)
    w = w.strip(".,-/")
    return w


class Video:
    __slots__ = ("id", "date", "title", "seconds", "toks", "times", "text", "starts", "dup_of")

    def __init__(self, row):
        self.id = row["id"]
        self.date = row["upload_date"]
        self.title = row["title"]
        self.seconds = int(row["seconds"] or 0)
        self.dup_of = None
        self.toks = []
        self.times = []
        self.text = ""
        self.starts = []

    def load(self):
        words = parse_vtt(os.path.join(SUBS, self.id + ".en-orig.vtt"))
        for t, w in words:
            n = norm_tok(w)
            if n:
                self.toks.append(n)
                self.times.append(t)
        pos, parts = 0, []
        for n in self.toks:
            self.starts.append(pos)
            parts.append(n)
            pos += len(n) + 1
        self.text = " ".join(parts)

    def widx(self, char_off):
        return bisect.bisect_right(self.starts, char_off) - 1


def load_status():
    rows = list(csv.DictReader(open(STATUS), delimiter="\t"))
    return rows


def load_videos():
    """caption videos, with the 10 duplicate uploads (same date + title + length) dropped."""
    rows = load_status()
    ok = [r for r in rows if r["status"] == "ok" and r["upload_date"] <= SEALED_AFTER]
    seen, vids, dups = {}, [], []
    for r in ok:
        key = (r["upload_date"], r["title"], r["seconds"])
        if key in seen:
            dups.append((r["id"], seen[key]))
            continue
        seen[key] = r["id"]
        v = Video(r)
        v.load()
        vids.append(v)
    return rows, ok, vids, dups


# ----------------------------------------------------------------------------------------
# 2. candidate trade statements (regex pass on the normalised caption text)
# ----------------------------------------------------------------------------------------
NUMW = ("one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
        "sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
        "hundred|thousand|million|billion")
NUM = r"(?:\$?\d[\d.,]*|(?:%s)(?:[\s-]+(?:%s|and))*)" % (NUMW, NUMW)
UNIT = r"(?:%|percent|k|thousand|million|x|grand|dollars|bucks)"
ACCNUM = NUM + r"\s*" + UNIT + r"\b"
PERIOD = (r"(?:this\s+year|this\s+month|this\s+week|today|the\s+year|the\s+month|the\s+week|the\s+day|"
          r"year\s+to\s+date|ytd|so\s+far|last\s+year|last\s+month|last\s+week|a\s+year|the\s+quarter|"
          r"this\s+quarter|for\s+the\s+year|on\s+the\s+year|on\s+the\s+month|on\s+the\s+day)")

# kind -> list of regexes.  Order of KIND_PRIORITY is how a cluster of nearby matches is named.
KIND_PRIORITY = ["stopped", "sold_part", "sold", "added", "bought", "buy_now",
                 "profit", "cost_stop", "account"]
PATTERNS = {
    "bought": [
        r"\b(?:i|we|i've|ive)\s+(?:\w+\s+){0,2}?bought\b",
        r"\bbought\s+(?:it|some|more|a\s+(?:little|bit|starter|small|lot)|half|back|this|that|them|these|"
        r"here|too|the|at|in|on|before|after|\d)\b",
    ],
    "buy_now": [
        r"\bi'?m\s+(?:\w+\s+)?(?:buying|long|in\s+(?:it|this|that|here|there|now))\b",
        r"\bi\s+(?:\w+\s+)?(?:got\s+in|went\s+long|entered|started\s+(?:a\s+)?(?:position|buying)|"
        r"took\s+(?:a\s+)?(?:position|starter|shot|stab))\b",
    ],
    "added": [
        r"\b(?:i|we|i've|ive|i'm)\s+(?:\w+\s+){0,2}?(?:added|adding)\b",
        r"\badded\s+(?:more|to\s+(?:it|this|that|my|the|mine)|some|a\s+(?:little|bit))\b",
    ],
    "sold_part": [
        r"\bsold\s+(?:a\s+)?(?:half|third|quarter|little|bit|some|part|partial|portion|two\s+thirds|"
        r"1/3|1/2|one\s+third|most)\b",
        r"\b(?:i|we)\s+(?:\w+\s+)?(?:trimmed|sold\s+off)\b",
        r"\b(?:i|we)\s+(?:\w+\s+)?took\s+(?:some|a\s+little|a\s+bit|half|a\s+third|a\s+partial|partials?)\b",
    ],
    "sold": [
        r"\b(?:i|we|i've|ive)\s+(?:\w+\s+){0,2}?sold\b",
        r"\bsold\s+(?:it|them|the\s+(?:rest|whole|remaining|remainder)|all|everything|out|my|at|into|on|"
        r"before|after|here|there|\d)\b",
        r"\bi'?m\s+out\b",
        r"\bi\s+(?:\w+\s+)?(?:got|was|am)\s+out\b",
        r"\b(?:i|we)\s+(?:\w+\s+)?(?:exited|closed\s+(?:it|my|the|out)|dumped|got\s+rid\s+of)\b",
    ],
    "stopped": [
        r"\bstopped\s+(?:me\s+)?out\b",
        r"\b(?:got|was|been|get|getting|am|i'm|gets)\s+stopped\b",
        r"\bstopped\s+me\b",
    ],
    "profit": [
        r"\b(?:took|taking|take|booked|banked|locking|locked)\s+(?:(?:some|a\s+little|a\s+bit\s+of|partial|"
        r"part|my|the)\s+)?(?:profits?|gains?)\b",
    ],
    "cost_stop": [
        r"\bmy\s+(?:average|avg|cost|entry|buy\s+price|basis|stop|stops|stop\s+loss|initial\s+stop|"
        r"break\s*even)\b",
        r"\b(?:cost\s+basis|average\s+price|average\s+cost|avg\s+price)\b",
    ],
    "account": [
        r"\bmy\s+(?:account|accounts|p\s*(?:and|&|n)\s*l|pnl|profit\s+and\s+loss|performance|returns?|"
        r"portfolio|equity|net\s+worth|results)\b",
        r"\b(?:year\s+to\s+date|ytd)\b",
        r"\b(?:up|down|made|lost|gained)\s+(?:\w+\s+){0,3}?" + ACCNUM + r"(?:\s+\w+){0,8}?\s+(?:in\s+|on\s+|for\s+)?" + PERIOD,
        r"\b" + PERIOD + r"\s+(?:\w+\s+){0,5}?(?:up|down|made|lost|gained)\s+(?:\w+\s+){0,3}?" + ACCNUM,
    ],
}
COMPILED = {k: [re.compile(p) for p in v] for k, v in PATTERNS.items()}
SAME_KIND_GAP = 8      # words: same-kind matches closer than this are one mention
CLUSTER_GAP = 12       # words: matches closer than this (any kind) are one statement
CLUSTER_MAX = 40       # words: a statement cluster never spans more than this


def find_matches(v):
    """-> list of (kind, w_start, w_end, matched_text) with same-kind repeats collapsed."""
    out = []
    for kind, pats in COMPILED.items():
        raw = []
        for p in pats:
            for m in p.finditer(v.text):
                raw.append((v.widx(m.start()), v.widx(max(m.end() - 1, m.start())), m.group(0)))
        raw.sort()
        last_end = -10 ** 9
        for ws, we, txt in raw:
            if ws - last_end < SAME_KIND_GAP:
                last_end = max(last_end, we)
                continue
            out.append((kind, ws, we, txt))
            last_end = we
    out.sort(key=lambda x: (x[1], KIND_PRIORITY.index(x[0])))
    return out


def cluster(v, matches):
    """merge nearby matches (any kind) into one statement; its kind = highest-priority kind."""
    stmts, cur = [], None
    for kind, ws, we, txt in matches:
        if cur and ws - cur["end"] <= CLUSTER_GAP and ws - cur["start"] <= CLUSTER_MAX:
            cur["end"] = max(cur["end"], we)
            cur["kinds"].add(kind)
            cur["texts"].append(txt)
        else:
            cur = {"start": ws, "end": we, "kinds": {kind}, "texts": [txt]}
            stmts.append(cur)
    res = []
    for s in stmts:
        kind = min(s["kinds"], key=KIND_PRIORITY.index)
        res.append({
            "video": v.id, "date": v.date, "title": v.title,
            "t": v.times[s["start"]], "w0": s["start"], "w1": s["end"],
            "kind": kind, "kinds_in_cluster": "+".join(sorted(s["kinds"], key=KIND_PRIORITY.index)),
            "matched": " | ".join(s["texts"])[:160],
            "snippet": " ".join(v.toks[max(0, s["start"] - 12): s["end"] + 13]),
        })
    return res


def hms(t):
    t = int(t)
    return "%d:%02d:%02d" % (t // 3600, (t % 3600) // 60, t % 60)


def extract(verbose=True):
    rows, ok, vids, dups = load_videos()
    mentions = collections.Counter()           # (year, kind) -> same-kind-deduped matches
    stmts = []
    for v in vids:
        ms = find_matches(v)
        for kind, *_ in ms:
            mentions[(v.date[:4], kind)] += 1
        stmts.extend(cluster(v, ms))
    os.makedirs(WORK, exist_ok=True)
    cols = ["video", "date", "title", "t", "w0", "w1", "kind", "kinds_in_cluster", "matched", "snippet"]
    with open(os.path.join(WORK, "statements.tsv"), "w") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for s in stmts:
            w.writerow(s)
    if verbose:
        print("caption files", len(ok), "| unique streams", len(vids), "| duplicates dropped", len(dups))
        by = collections.Counter((s["date"][:4], s["kind"]) for s in stmts)
        print("statements", len(stmts))
        years = sorted({y for y, _ in by})
        print("kind".ljust(11), *[y.rjust(6) for y in years], "total".rjust(7))
        for k in KIND_PRIORITY:
            print(k.ljust(11), *[str(by[(y, k)]).rjust(6) for y in years], str(sum(by[(y, k)] for y in years)).rjust(7))
    return rows, ok, vids, dups, stmts, mentions


# ----------------------------------------------------------------------------------------
# 3. fixed sample (seed 705), stratified by kind (x year, 2020/2021/2022)
# ----------------------------------------------------------------------------------------
FRAME_YEARS = ("2020", "2021", "2022")
SAMPLE_COLS = ["sid", "video", "upload_date", "t_hms", "kind", "stratum", "matched", "snippet",
               "ticker_ident", "ticker", "ticker_inferred", "action", "price_stated", "price_value",
               "price_garbled", "date_pinnable", "his_trade", "usable_strict", "usable_strict_no_inferred",
               "usable_loose", "usable_anydate", "usable_state", "note"]


def read_statements():
    with open(os.path.join(WORK, "statements.tsv")) as f:
        return list(csv.DictReader(f, delimiter="\t"))


def allocate(cells, total):
    """cells: {stratum: N}. Spread `total` as evenly as possible over strata (a stratum never gets more
    than it holds); leftover goes to the strata with the most statements left. Deterministic."""
    alloc = {c: 0 for c in cells}
    left = total
    while left > 0:
        open_c = [c for c in cells if alloc[c] < cells[c]]
        if not open_c:
            break
        base = max(1, left // len(open_c))
        for c in sorted(open_c, key=lambda c: (-(cells[c] - alloc[c]), c)):
            if left == 0:
                break
            give = min(base, cells[c] - alloc[c], left)
            alloc[c] += give
            left -= give
    return alloc


def draw():
    if os.path.exists(SAMPLE_TSV):
        with open(SAMPLE_TSV) as f:
            existing = list(csv.DictReader(f, delimiter="\t"))
        if any(r.get("action", "").strip() for r in existing):
            sys.exit("caption_sample.tsv already carries hand labels - refusing to overwrite (delete it by hand to redraw)")
    if not os.path.exists(os.path.join(WORK, "statements.tsv")):
        extract(verbose=False)
    stmts = [s for s in read_statements() if s["date"][:4] in FRAME_YEARS]
    cells = collections.defaultdict(list)
    for s in stmts:
        cells[(s["kind"], s["date"][:4])].append(s)
    counts = {c: len(v) for c, v in cells.items()}
    alloc = allocate(counts, N_SAMPLE)
    rng = random.Random(SEED)
    picked = []
    for c in sorted(cells):
        pool = sorted(cells[c], key=lambda s: (s["video"], int(s["w0"])))
        picked.extend((c, s) for s in rng.sample(pool, alloc[c]))
    picked.sort(key=lambda cs: (KIND_PRIORITY.index(cs[0][0]), cs[0][1], cs[1]["date"], cs[1]["video"], int(cs[1]["w0"])))
    rows = []
    for i, (c, s) in enumerate(picked, 1):
        rows.append({"sid": "S%03d" % i, "video": s["video"], "upload_date": s["date"], "t_hms": hms(float(s["t"])),
                     "kind": s["kind"], "stratum": "%s|%s" % c, "matched": s["matched"], "snippet": s["snippet"],
                     **{k: "" for k in SAMPLE_COLS[8:]}})
    with open(SAMPLE_TSV, "w") as f:
        w = csv.DictWriter(f, fieldnames=SAMPLE_COLS, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    # context file for hand reading: +-30 s of words around the statement
    _, _, vids, _ = load_videos()
    vmap = {v.id: v for v in vids}
    sm = {s["video"] + ":" + s["w0"]: s for s in stmts}
    with open(os.path.join(WORK, "sample_context.txt"), "w") as f:
        for r, (c, s) in zip(rows, picked):
            v = vmap[s["video"]]
            t0 = float(s["t"])
            f.write("=== %s | %s | %s | %s @%s | kind=%s | matched: %s\n" % (
                r["sid"], r["upload_date"], v.title[:60], v.id, r["t_hms"], r["kind"], r["matched"]))
            f.write(context_text(v, t0, int(s["w0"]), int(s["w1"])) + "\n\n")
    print("sample rows", len(rows), "| allocation per (kind|year):")
    for c in sorted(alloc):
        print("  ", c, counts[c], "->", alloc[c])
    return rows


def context_text(v, t0, w0, w1, pre=30.0, post=30.0):
    lo = bisect.bisect_left(v.times, t0 - pre)
    hi = bisect.bisect_right(v.times, v.times[w1] + post)
    out, last_mark = [], None
    for i in range(lo, hi):
        mark = int(v.times[i] // 10)
        if mark != last_mark:
            out.append("\n[%s]" % hms(v.times[i]))
            last_mark = mark
        tok = v.toks[i]
        if i == w0:
            tok = "<<" + tok
        if i == w1:
            tok = tok + ">>"
        out.append(tok)
    return " ".join(out).replace("\n ", "\n")


# ----------------------------------------------------------------------------------------
# 4. account-level candidates (for hand review)
# ----------------------------------------------------------------------------------------
ACCT = (r"(?:account|accounts|portfolio|p\s*(?:and|&|n)\s*l|pnl|profit\s+and\s+loss|performance|returns?|"
        r"equity|net\s+worth|ytd|year\s+to\s+date|money)")
PER = r"(?:year|month|week|quarter|day|session|decade)"
ACC_PATTERNS = {
    "my_account_number": r"\bmy\s+(?:\w+\s+)?" + ACCT + r"\b(?:\s+\w+){0,14}?\s+" + NUM + r"\s*" + UNIT + r"\b",
    "i_up_down_per_period": (r"\b(?:i'm|i\s+am|i\s+was|i\s+ended|i\s+finished|i\s+made|i\s+lost|i\s+gained|"
                            r"i\s+returned|we\s+made|we're)\s+(?:\w+\s+){0,3}?(?:up|down|made|lost|gained|returned)?\s*"
                            r"(?:\w+\s+){0,2}?" + NUM + r"\s*" + UNIT + r"\b(?:\s+\w+){0,6}?\s+(?:this|last|for\s+the|"
                            r"in\s+the|on\s+the|in|for|over\s+the)\s+" + PER),
    "period_then_i": (r"\b(?:this|last|for\s+the|over\s+the\s+past)\s+" + PER + r"\s+(?:\w+\s+){0,6}?(?:i'm|i\s+am|"
                     r"i\s+was|i\s+made|i\s+lost|i\s+finished|i\s+ended|i\s+returned|i\s+gained|i\s+did|my)\s+"
                     r"(?:\w+\s+){0,5}?" + NUM + r"\s*" + UNIT + r"\b"),
    "doubled_account": (r"\b(?:i|we)\s+(?:\w+\s+){0,2}?(?:doubled|tripled|quadrupled|10x|2x|3x|5x)\s+(?:\w+\s+){0,3}?"
                        r"(?:account|money|portfolio|capital)"),
    "best_worst": (r"\bmy\s+(?:best|worst|biggest)\s+(?:year|month|week|day|loss|win|trade)\b|"
                   r"\b(?:best|worst)\s+(?:year|month)\s+(?:ever|i've\s+had|of\s+my)"),
    "million_profit_loss": (r"\b(?:million|millionaire|hundred\s+thousand|\d+k)\b(?:\s+\w+){0,5}?\s+(?:profit|profits|"
                            r"gain|gains|loss|losses|in\s+my\s+account|account)\b"),
    "ytd": r"\b(?:ytd|year\s+to\s+date)\b",
    "pct_year": (r"\b" + NUM + r"\s*(?:%|percent)\s+(?:\w+\s+){0,3}?(?:for\s+the\s+year|this\s+year|in\s+\d{4}|"
                 r"last\s+year|a\s+year|per\s+year|return|returns|annual)"),
}
ACC_COMPILED = {k: re.compile(v) for k, v in ACC_PATTERNS.items()}
FIRST_PERSON = re.compile(r"\b(?:i|i'm|i've|ive|i'd|my|me|we|we're|our)\b")


def account_candidates():
    """first-person money-result phrases (tight patterns) with >= 1 first-person word in +-12 words;
    same-video hits closer than 25 words are one candidate. Output is for HAND review."""
    _, _, vids, _ = load_videos()
    rows = []
    for v in vids:
        hits = []
        for name, p in ACC_COMPILED.items():
            for m in p.finditer(v.text):
                hits.append((v.widx(m.start()), v.widx(max(m.end() - 1, m.start())), name, m.group(0)))
        hits.sort()
        last = -99
        for ws, we, name, txt in hits:
            if ws - last < 25:
                continue
            win = " ".join(v.toks[max(0, ws - 12): we + 13])
            if not FIRST_PERSON.search(win):
                continue
            last = we
            rows.append((v.date, v.id, hms(v.times[ws]), v.title[:50], name, txt[:70],
                         " ".join(v.toks[max(0, ws - 25): we + 35])))
    rows.sort()
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(WORK, "account_candidates.tsv"), "w") as f:
        f.write("date\tvideo\tt\ttitle\tpattern\tmatched\tcontext\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    print("account candidates", len(rows), "in", len({r[1] for r in rows}), "videos")
    return rows


# ----------------------------------------------------------------------------------------
# 5. report: yields + intervals + coverage + account statements -> captions.md
# ----------------------------------------------------------------------------------------
EVENT = {"buy", "add", "sell_part", "sell_all", "sell_unspec", "stopped"}
STATE = {"holding", "stop_level", "result"}
DATE_STRICT = {"stream_day", "stated_earlier"}
DATE_LOOSE = DATE_STRICT | {"implied_recent", "approx_earlier"}
USABLE_COLS = ["usable_strict", "usable_strict_no_inferred", "usable_loose", "usable_anydate", "usable_state"]

# NYSE full-day closures, hard-coded for 2020-2022 (used only for the coverage table)
HOLIDAYS = {
    "2020-01-01", "2020-01-20", "2020-02-17", "2020-04-10", "2020-05-25", "2020-07-03", "2020-09-07",
    "2020-11-26", "2020-12-25", "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31",
    "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24", "2022-01-17", "2022-02-21", "2022-04-15",
    "2022-05-30", "2022-06-20",
}


def trading_days(year, month):
    d, out = dt.date(year, month, 1), []
    while d.month == month:
        if d.weekday() < 5 and d.isoformat() not in HOLIDAYS:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def flags(r):
    ev = r["ticker_ident"] == "Y" and r["action"] in EVENT and r["his_trade"] == "Y"
    return {
        "usable_strict": ev and r["date_pinnable"] in DATE_STRICT,
        "usable_strict_no_inferred": ev and r["date_pinnable"] in DATE_STRICT and r["ticker_inferred"] != "Y",
        "usable_loose": ev and r["date_pinnable"] in DATE_LOOSE,
        "usable_anydate": ev,
        "usable_state": r["ticker_ident"] == "Y" and r["action"] in STATE and r["his_trade"] == "Y",
    }


def fail_reason(r):
    f = flags(r)
    if f["usable_strict"]:
        return "1 usable now: ticker + action + day"
    if f["usable_anydate"]:
        return "2 ticker + action ok, day not in the words"
    if r["his_trade"] != "Y":
        return "3 not about his own trade (advice, if-then, plan, viewer, someone else)"
    if r["action"] not in EVENT:
        return "4 his position but no buy / sell / stop event (holding, stop level, result, nothing)"
    return "5 event is his, but the ticker is not identifiable"


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def r10(x):
    return "{:,}".format(int(round(x, -1)))


def pct(x, d=0):
    return "n/a" if x != x else ("%." + str(d) + "f%%") % (100 * x)


def strat_estimate(sample, counts, pred, years=None, kinds=None):
    """post-stratified proportion over (kind, year) cells."""
    num = den = 0.0
    for cell, N in counts.items():
        kind, yr = cell
        if (years and yr not in years) or (kinds and kind not in kinds):
            continue
        rows = sample.get(cell, [])
        if not rows:
            continue
        num += N * sum(1 for r in rows if pred(r)) / len(rows)
        den += N
    return (num / den if den else float("nan")), den


def boot_ci(sample, counts, pred, years=None, kinds=None, B=None, seed=None):
    """95% range = estimate +- 1.96 standard errors of the weighted (kind x year) estimate.
    Each cell's variance uses its rate with one hit and one miss added (Agresti-Coull style), so a cell that
    happened to show 0 of 4 or 4 of 4 is not treated as certain; cells read in full add no variance.
    (Name kept from an earlier bootstrap version; B and seed are unused.)"""
    cells = []
    for cell, N in counts.items():
        kind, yr = cell
        if (years and yr not in years) or (kinds and kind not in kinds):
            continue
        rows = sample.get(cell, [])
        if rows:
            cells.append((N, len(rows), sum(1 for r in rows if pred(r))))
    den = float(sum(N for N, _, _ in cells))
    est = sum(N * k / n_ for N, n_, k in cells) / den
    var = 0.0
    for N, n_, k in cells:
        if n_ >= N:
            continue
        pt = (k + 1.0) / (n_ + 2.0)
        var += (N / den) ** 2 * (1 - n_ / float(N)) * pt * (1 - pt) / (n_ + 2.0)
    se = math.sqrt(var)
    return max(0.0, est - 1.96 * se), min(1.0, est + 1.96 * se)


def load_account_rows():
    with open(ACCOUNT_TSV) as f:
        return list(csv.DictReader(f, delimiter="\t"))


def report():
    rows, ok, vids, dups, stmts, mentions = extract(verbose=False)
    with open(SAMPLE_TSV) as f:
        sample_rows = list(csv.DictReader(f, delimiter="\t"))
    unlabeled = [r["sid"] for r in sample_rows if not r["action"].strip()]
    if unlabeled:
        sys.exit("unlabelled sample rows: %s" % unlabeled[:10])
    for r in sample_rows:
        for k, v in flags(r).items():
            r[k] = "Y" if v else "N"
    with open(SAMPLE_TSV, "w") as f:
        w = csv.DictWriter(f, fieldnames=SAMPLE_COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(sample_rows)
    md = render(rows, ok, vids, dups, stmts, mentions, sample_rows)
    with open(REPORT_MD, "w") as f:
        f.write(md)
    print("wrote", REPORT_MD, "and refreshed the usable_* columns in", SAMPLE_TSV)


def render(rows, ok, vids, dups, stmts, mentions, sample_rows):
    L = []
    P = L.append
    # ---------- counts --------------------------------------------------------------------
    years = sorted({s["date"][:4] for s in stmts})
    by = collections.Counter((s["date"][:4], s["kind"]) for s in stmts)
    frame = [s for s in stmts if s["date"][:4] in FRAME_YEARS]
    counts = collections.Counter((s["kind"], s["date"][:4]) for s in frame)
    sample = collections.defaultdict(list)
    for r in sample_rows:
        kind, yr = r["stratum"].split("|")
        r["_kind"], r["_year"] = kind, yr
        r["_f"] = flags(r)
        sample[(kind, yr)].append(r)
    N_frame = len(frame)
    n = len(sample_rows)

    def est(col, years_=None, kinds_=None):
        pred = (lambda r: r["_f"][col]) if col in USABLE_COLS else col
        e, den = strat_estimate(sample, counts, pred, years_, kinds_)
        lo, hi = boot_ci(sample, counts, pred, years_, kinds_)
        return e, lo, hi, den

    trade_kinds = [k for k in KIND_PRIORITY if k != "account"]
    scopes = [("2020-2022 all kinds", None, None), ("2020-2022 trade kinds (no 'account')", None, trade_kinds),
              ("2020", {"2020"}, None), ("2021", {"2021"}, None), ("2022", {"2022"}, None)]
    res = {}
    for name, yrs, kds in scopes:
        for col in USABLE_COLS:
            res[(name, col)] = est(col, yrs, kds)
        res[(name, "price_any")] = est(lambda r: r["_f"]["usable_anydate"] and r["price_stated"] == "Y", yrs, kds)
        res[(name, "price_clean")] = est(lambda r: r["_f"]["usable_anydate"] and r["price_stated"] == "Y" and r["price_garbled"] == "N", yrs, kds)
    allk = ("2020-2022 all kinds",)
    h = lambda col: res[("2020-2022 all kinds", col)]

    # ---------- headline ------------------------------------------------------------------
    P("# #705 inventory 1: how usable are his stream captions as the step-6 reference?")
    P("")
    P("Measure only. No rules, no design. Our rule library is not used anywhere in this page.")
    P("")
    P("## Answer")
    P("")
    e, lo, hi, _ = h("usable_strict")
    ea, loa, hia, _ = h("usable_anydate")
    es, los, his_, _ = h("usable_state")
    P("- **About %s of caption trade statements give a complete, dated trade fact** (named stock + what he did + the day), 95%% range %s to %s. "
      "That is roughly **%s of the %s candidate statements** in 2020-2022 (range %s to %s)." % (
          pct(e), pct(lo), pct(hi), r10(e * N_frame), "{:,}".format(N_frame),
          r10(lo * N_frame), r10(hi * N_frame)))
    P("- **Counting statements whose day is not in the words** (he points at the chart: \"here\", \"this day\") the share is %s (%s to %s): "
      "the stock and the action are clear, the day is only bounded by the stream date. Position-state facts (holding, stop level, stated result) add a further %s." % (
          pct(ea), pct(loa), pct(hia), pct(es)))
    P("- **By year (2020 / 2021 / 2022): %s / %s / %s usable now**; the ranges overlap (see table 2), so no year is measurably better than another." % (
        pct(res[("2020", "usable_strict")][0]), pct(res[("2021", "usable_strict")][0]), pct(res[("2022", "usable_strict")][0])))
    P("- **A price is stated in few of them**: only %s of all statements have a named stock, an action AND a price (%s with a clean number). When he gives a number it is usually a share count or a dollar gain or loss (sample rows S017, S021, S044, S055, S098), not an entry price." % (
        pct(h("price_any")[0]), pct(h("price_clean")[0])))
    P("- **Account-level numbers exist and are rich**: %d statements with a number listed in `account_statements.tsv` (yearly returns 2013-2020, the 2021 year-to-date path, account sizes, best/worst weeks and days). "
      "The 2013-2018 yearly returns are told identically on two days seven months apart (stable); the 2020 figure is not (+710%% to +1000%% depending on how and when he says it)." % len(load_account_rows()))
    P("- **Coverage is dense for 2020-01 to 2021-06** (about %s of trading days have a caption video) **and thin after** (2021-07 to 2022-06 about %s). Details in the coverage table." % (
        "@@COV1@@", "@@COV2@@"))
    P("- **Action: none.** Inventory only; the numbers here set what step 6 can and cannot lean on.")
    P("")

    # ---------- method --------------------------------------------------------------------
    P("## What was done")
    P("")
    P("- Parsed %d caption files (YouTube auto-captions, rolling repeats removed) -> %d unique streams after dropping %d duplicate uploads of the same stream (same date, title, length)." % (len(ok), len(vids), len(dups)))
    P("- Regex pass for first-person trade phrases (patterns in the script). Nearby matches (within 12 words, any kind) are merged into one statement named by its strongest kind. Total: **%s statements** in 2017-2023, **%s in 2020-2022**." % ("{:,}".format(len(stmts)), "{:,}".format(N_frame)))
    P("- Fixed sample (seed %d) of %d statements, stratified by kind x year (the brief said kind; adding year gives about 40 rows per year for the per-year estimate), %d to %d per cell where the cell is that big. 2017-2019 and 2023 are counted in table 1 but not sampled (the positions-list era is 2020-01 to 2022-06). Each read with +-30 s of caption context and hand-labelled by ONE reader (me); no blind second reader (no subagents allowed). A review pass over the rows that drive the headline changed 7 of 120 labels (6 day labels, 1 ticker). Rows: `caption_sample.tsv`." % (SEED, n, min(len(v) for v in sample.values()), max(len(v) for v in sample.values())))
    P("- Weighted estimate = each cell scaled to the number of statements it stands for. 95% range = estimate +- 1.96 standard errors; each cell's variance is computed with one hit and one miss added, so a cell that happened to show 0 of 4 is not treated as certain. Cells hold only 1-5 rows, so the ranges are wide.")
    P("")
    P("**Label meanings (plain):**")
    P("")
    P("- *ticker identifiable*: Y = one company/ticker named in the 30 s either side that the sentence clearly points at (a garbled name I could resolve from the next sentence counts as Y but is flagged *inferred*); amb = garbled or several candidates; N = not named.")
    P("- *his own trade (Y)*: first-person fact about his own position. Not Y: advice to viewers, if-then, plans (\"gonna get stopped out\"), a viewer's trade, insiders, jokes.")
    P("- *action*: buy, add, sell_part, sell_all, sell_unspec (sold, size not said), stopped. Position-state facts are labelled separately: holding, stop_level (\"my stop is ...\"), result (\"lost 180k on two trades\").")
    P("- *day pinned*: stream_day (words show it is today: just, pre-market, at the open, today), stated_earlier (yesterday, Friday, three days ago), implied_recent (live position but no day word), approx_earlier (last week, a month ago), unstated (\"here\", \"this day\" = chart pointing, or nothing).")
    P("- **usable now** = ticker Y + event action + his own + day in {stream_day, stated_earlier}. **usable, day bounded only** = same without the day test. **loose** adds implied_recent and approx_earlier.")
    P("")

    # ---------- table 1 -------------------------------------------------------------------
    P("## 1. Candidate trade statements by kind and upload year (after de-duplication)")
    P("")
    P("Kind = strongest phrase in the merged statement. `stopped` = \"stopped out / got stopped\"; `sold_part` = \"sold half / some / a third\", \"took half\"; `sold` = \"i sold / sold it / i'm out\"; `buy_now` = \"i'm long / i got in / i'm buying\"; `cost_stop` = \"my average / my entry / my stop\"; `profit` = \"took profits\".")
    P("")
    P("| kind | " + " | ".join(years) + " | total | in 2020-22 |")
    P("|---|" + "---:|" * (len(years) + 2))
    for k in KIND_PRIORITY:
        tot = sum(by[(y, k)] for y in years)
        in_f = sum(by[(y, k)] for y in FRAME_YEARS)
        P("| %s | %s | %s | %s |" % (k, " | ".join("{:,}".format(by[(y, k)]) for y in years), "{:,}".format(tot), "{:,}".format(in_f)))
    tots = [sum(by[(y, k)] for k in KIND_PRIORITY) for y in years]
    P("| **all** | %s | **%s** | **%s** |" % (" | ".join("**{:,}**".format(t) for t in tots), "{:,}".format(sum(tots)), "{:,}".format(N_frame)))
    vid_by_year = collections.Counter(v.date[:4] for v in vids)
    P("| unique streams | %s | %s | %s |" % (" | ".join(str(vid_by_year[y]) for y in years), sum(vid_by_year.values()), sum(vid_by_year[y] for y in FRAME_YEARS)))
    P("")
    P("Mentions before merging nearby kinds (the same sentence often hits two kinds, e.g. \"bought ... got stopped\"): " + ", ".join(
        "%s %s" % (k, "{:,}".format(sum(v for (y, kk), v in mentions.items() if kk == k))) for k in KIND_PRIORITY) + ".")
    P("")

    # ---------- table 2: yields -----------------------------------------------------------
    P("## 2. Yield from the hand-read sample (%d statements)" % n)
    P("")
    P("Share of statements that are usable. Range = 95%. \"statements\" = candidate statements, not distinct trades (one trade is often mentioned twice in a minute, e.g. S040/S041/S105 are one BOIL sale and its entry).")
    P("")
    P("| scope | statements in scope | usable now (ticker + action + day said) | ticker + action, any day wording | ticker + action + day said or implied | position-state facts | ticker + action and a price stated |")
    P("|---|---:|---|---|---|---|---|")
    for name, yrs, kds in scopes:
        den = res[(name, "usable_strict")][3]
        cells = []
        for col in ["usable_strict", "usable_anydate", "usable_loose", "usable_state", "price_any"]:
            e_, lo_, hi_, _ = res[(name, col)]
            cells.append("%s (%s-%s)" % (pct(e_), pct(lo_), pct(hi_)))
        P("| %s | %s | %s |" % (name, "{:,}".format(int(den)), " | ".join(cells)))
    P("")
    P("Conservative variant: dropping the %d sampled rows where I resolved a garbled name by inference (flagged `ticker_inferred`) the \"usable now\" share is %s (%s-%s)." % (
        sum(1 for r in sample_rows if r["ticker_inferred"] == "Y"), pct(h("usable_strict_no_inferred")[0]), pct(h("usable_strict_no_inferred")[1]), pct(h("usable_strict_no_inferred")[2])))
    P("")
    P("Expected number of usable statements in the 2020-2022 captions (share x %s statements): usable now ~%s (%s to %s); day bounded only ~%s (%s to %s)." % (
        "{:,}".format(N_frame), r10(e * N_frame), r10(lo * N_frame), r10(hi * N_frame),
        r10(ea * N_frame), r10(loa * N_frame), r10(hia * N_frame)))
    P("")
    n_streams = len({s_["video"] for s_ in frame}) or 1
    n_streams = sum(1 for v in vids if v.date[:4] in FRAME_YEARS)
    P("Per stream (%d streams in 2020-2022): about %.1f usable-now statements and %.1f with ticker + action (any day wording) per stream." % (
        n_streams, e * N_frame / n_streams, ea * N_frame / n_streams))
    P("")
    P("**By kind (raw sample counts, small n: read as direction only):**")
    P("")
    P("| kind | statements 2020-22 | sampled | usable now | ticker + action (any day) | position-state | not his own trade |")
    P("|---|---:|---:|---:|---:|---:|---:|")
    for k in KIND_PRIORITY:
        rs = [r for c, v in sample.items() if c[0] == k for r in v]
        Nk = sum(counts[(k, y)] for y in FRAME_YEARS)
        P("| %s | %s | %d | %d | %d | %d | %d |" % (
            k, "{:,}".format(Nk), len(rs), sum(r["_f"]["usable_strict"] for r in rs), sum(r["_f"]["usable_anydate"] for r in rs),
            sum(r["_f"]["usable_state"] for r in rs), sum(1 for r in rs if r["his_trade"] != "Y")))
    P("")

    # ---------- table 3: why not usable ---------------------------------------------------
    P("## 3. Why a statement is not usable (weighted shares, 2020-2022)")
    P("")
    P("| first failing test | share | sampled rows |")
    P("|---|---:|---:|")
    reasons = sorted({fail_reason(r) for r in sample_rows})
    for rs in reasons:
        e_, _ = strat_estimate(sample, counts, lambda r, rs=rs: fail_reason(r) == rs)
        P("| %s | %s | %d |" % (rs[2:], pct(e_), sum(1 for r in sample_rows if fail_reason(r) == rs)))
    P("")
    dp = collections.Counter(r["date_pinnable"] for r in sample_rows if r["_f"]["usable_anydate"])
    P("Among the %d sampled rows with ticker + his own event: day pinned as %s." % (sum(dp.values()), ", ".join("%s %d" % (k, v) for k, v in dp.most_common())))
    ti = collections.Counter(r["ticker_ident"] for r in sample_rows if r["his_trade"] == "Y" and r["action"] in EVENT)
    P("Among his own event rows the ticker is Y %d / amb %d / N %d." % (ti["Y"], ti["amb"], ti["N"]))
    pr = [r for r in sample_rows if r["_f"]["usable_anydate"]]
    P("Among the %d usable rows (day bounded only or better): price stated %d (garbled %d); a share count or dollar size is stated in a few more." % (
        len(pr), sum(1 for r in pr if r["price_stated"] == "Y"), sum(1 for r in pr if r["price_stated"] == "Y" and r["price_garbled"] == "Y")))
    hm = collections.Counter(r["his_trade"] for r in sample_rows)
    P("His-trade label over all %d rows: %s." % (n, ", ".join("%s %d" % (k, v) for k, v in hm.most_common())))
    P("")
    P("What the misses look like (from reading the rows): the regex fires on advice (\"if you get stopped out ...\"), plans (\"I'm gonna get stopped out\"), jokes and viewers' trades as often as on facts; "
      "tickers are said as nicknames or garbled by the caption (TVIX heard as twix / tweaks / twigs / tricks; GUSH as gosh / cash; TQQQ as tqq / tq), which a per-ticker alias list could recover; "
      "and the day is often \"here\" on a chart he is pointing at.")
    P("")

    # ---------- account statements --------------------------------------------------------
    acc = load_account_rows()
    lev = collections.Counter(r["level"] for r in acc)
    tr = [r for r in acc if r["level"] == "trade"]
    ac = [r for r in acc if r["level"] != "trade"]
    P("## 4. His statements of account, yearly and monthly results")
    P("")
    P("`account_statements.tsv`: **%d statements** (%d account-level, %d single-trade $ results of about $200k or more, %d are video titles). "
      "Found with two regex passes over all %d streams plus a title scan, then read by hand; recall is unknown and some are surely missing (the second pass found about 15 the first missed). "
      "By year of the video: %s." % (
          len(acc), len(ac), len(tr), sum(1 for r in acc if r["source"] == "title"), len(vids),
          ", ".join("%s %d" % (y, c) for y, c in sorted(collections.Counter(r["video_date"][:4] for r in acc).items()))))
    P("")
    P("By level: " + ", ".join("%s %d" % (k, v) for k, v in lev.most_common()) + ".")
    P("")
    P("Quality: " + ", ".join("%s %d" % (k, v) for k, v in collections.Counter(r["quality"] for r in acc).most_common()) + ".")
    P("")
    P("**The yearly return series as he states it (his figures, not verified):**")
    P("")
    P("| year | stated | said on (video date) | repeated? |")
    P("|---|---|---|---|")
    P("| 2011-2012 | losing years, \"blew up about four times\" | 2019-11-01, 2020-06-09 | yes |")
    P("| 2013 | +352% (first winning year; account $16k down to $9.1k) | 2019-11-01, 2020-06-09 | same number twice |")
    P("| 2014 | +646% (also \"10-bagger / ~1000% in under a year\" on a rolling window) | 2019-11-01, 2020-06-09, 2019-10-04, 2020-12-07 (\"best year ~650\") | same number 3x |")
    P("| 2015 | +107% | 2019-11-01, 2020-06-09 | same number twice |")
    P("| 2016 | +217% | 2019-11-01, 2020-06-09 | same number twice |")
    P("| 2017 | +414% (best month Sep 2017 about $200k) | 2019-11-01, 2020-06-09 | same number twice |")
    P("| 2018 | +89% (a $700k Tilray loss) | 2019-11-01, 2020-06-09 | same number twice |")
    P("| 2019 | +52% (\"very unhappy\"); later \"over 100 percent if i remember\" | 2020-06-09 / 2020-07-30 | **conflict** |")
    P("| 2020 | +870% (title + 2021-01-05); +900% (2021-02-11, 02-17); \"almost 1000\" (2021-09-17); \"under 1000\" (2021-01-12); $3.5M start + ~$25M = about +710%; \"800-900%\" (2020-12-22) | 2020-12-09 to 2021-09-17 | **range +710% to +1000%** |")
    P("| 2021 to date | +60% (02-09), ~+90-100% (02-23/24), +100-120% (03-10), +120% (03-12), +130% then +90-100% (03-24), ~+100% with peak +120-130% (05-06), \"barely up 100\" (09-17) | 2021-02 to 2021-09 | full year never stated in captions |")
    P("| 2022 to date | \"not up that much\" (04-13); \"exactly 15 year-to-date\" (04-14, garbled) | 2022-04 | partial |")
    P("")
    P("Seven-year average he quotes (2013-2019) is about 268% a year; the mean of the seven yearly figures above is 268.1, so those figures agree with each other. Account sizes quoted: $16k (2013), about $1M (Dec 2017 after tax, or July 2016 gross), $2.4M then $4M peak (Jul 2019), about $3.3-3.5M (Nov 2019), about $3.3-4M at the start of 2020, about $17.5M (2020-08), about $18-20M peak (Jul 2020), $105M peak (Nov 2021).")
    P("")
    P("**Reliability notes for using these as the \"reproduces his returns\" reference:**")
    P("")
    P("- Fuzzy periods: many numbers are \"on the year\" or \"on the month\" said mid-period; the account base changes with withdrawals (boat, car) and a second smaller IB account is quoted separately (+900% to +1100% in 2020).")
    P("- A few are jokes or look rhetorical (\"20 million in my paper account\", \"almost 200 million dollar account\" in 2021-03 vs a $105M peak he gives later): flagged `sarcasm-risk`.")
    P("- Dollar figures are mostly P&L swings and unrealized (\"main account\"), not closed-trade returns.")
    P("")

    # ---------- coverage ------------------------------------------------------------------
    P("## 5. Coverage by month, 2020-01 to 2022-06")
    P("")
    P("Videos = caption files with duplicates dropped. Trading days = NYSE days (hard-coded holiday list). Days covered = trading days that have at least one caption video uploaded that day (one Saturday upload in the era; 8 \"Late upload\" videos in 2021-03 / 2021-01 carry an earlier stream date in the title, so their upload date is NOT the stream date).")
    P("")
    P("| month | caption videos | trading days | days covered | covered | listed but no caption track | stream hours captioned | caption words |")
    P("|---|---:|---:|---:|---:|---:|---:|---:|")
    status = load_status()
    nocap = collections.Counter(r["upload_date"][:6] for r in status if r["status"] == "nocaps")
    cov_tot = [0, 0]
    seg = {"a": [0, 0], "b": [0, 0]}
    for y in (2020, 2021, 2022):
        for m in range(1, 13):
            if y == 2022 and m > 6:
                break
            key = "%04d%02d" % (y, m)
            vs = [v for v in vids if v.date[:6] == key]
            td = trading_days(y, m)
            dates = {"%s-%s-%s" % (v.date[:4], v.date[4:6], v.date[6:]) for v in vs}
            covered = len(dates & set(td))
            hours = sum(v.seconds for v in vs) / 3600.0
            words = sum(len(v.toks) for v in vs)
            P("| %s-%02d | %d | %d | %d | %s | %d | %.0f | %s |" % (y, m, len(vs), len(td), covered, pct(covered / len(td)), nocap[key], hours, "{:,}".format(words)))
            cov_tot[0] += covered
            cov_tot[1] += len(td)
            g = "a" if key <= "202106" else "b"
            seg[g][0] += covered
            seg[g][1] += len(td)
    P("| **total** | **%d** | **%d** | **%d** | **%s** | **%d** | | |" % (
        sum(1 for v in vids if "202001" <= v.date[:6] <= "202206"), cov_tot[1], cov_tot[0], pct(cov_tot[0] / cov_tot[1]),
        sum(c for k, c in nocap.items() if "202001" <= k <= "202206")))
    P("")
    listed = collections.Counter(r["upload_date"][:6] for r in status if r["upload_date"])
    l_a = sum(c for k, c in listed.items() if "202001" <= k <= "202106")
    l_b = sum(c for k, c in listed.items() if "202107" <= k <= "202206")
    n_b = sum(c for k, c in nocap.items() if "202107" <= k <= "202206")
    outside = collections.Counter(v.date[:4] for v in vids if v.date[:4] not in FRAME_YEARS or v.date[:6] > "202206")
    P("2020-01 to 2021-06: %d of %d trading days covered (%s). 2021-07 to 2022-06: %d of %d (%s). "
      "In that second stretch the channel lists only %d videos in total (against %d in the first 18 months) and %d of them have no caption track at all, so the gap is both fewer streams on the channel and missing tracks. "
      "3 further videos failed on an age gate (no date). Caption videos outside the table: %s." % (
          seg["a"][0], seg["a"][1], pct(seg["a"][0] / seg["a"][1]), seg["b"][0], seg["b"][1], pct(seg["b"][0] / seg["b"][1]),
          l_b, l_a, n_b, ", ".join("%s %d" % (y, c) for y, c in sorted(outside.items()))))
    P("")
    P("## Files")
    P("")
    P("- `captions_inventory.py`: stages `extract`, `draw`, `account`, `report`, plus `show VIDEO H:MM:SS [SECONDS]` to read any caption stretch. Seed %d. Writes only here; scratch in the system temp dir." % SEED)
    P("- `caption_sample.tsv`: the %d sample rows with all labels and the derived `usable_*` columns." % n)
    P("- `account_statements.tsv`: %d account / result statements with video date, time, level, period, number, verbatim caption quote (checked to appear in the caption text), quality flag." % len(acc))
    text = "\n".join(L) + "\n"
    text = text.replace("@@COV1@@", pct(seg["a"][0] / seg["a"][1])).replace("@@COV2@@", pct(seg["b"][0] / seg["b"][1]))
    return text

def show(video, start_hms, seconds=60):
    """print the caption words of one video from start_hms for `seconds` (hand-verification helper)."""
    h = start_hms.split(":")
    t0 = sum(int(x) * m for x, m in zip(reversed(h), (1, 60, 3600)))
    rows = [r for r in load_status() if r["id"] == video]
    v = Video(rows[0])
    v.load()
    lo = bisect.bisect_left(v.times, t0)
    hi = bisect.bisect_right(v.times, t0 + seconds)
    out, last = [], None
    for i in range(lo, hi):
        mark = int(v.times[i] // 10)
        if mark != last:
            out.append("\n[%s]" % hms(v.times[i]))
            last = mark
        out.append(v.toks[i])
    print("%s %s %s" % (v.date, v.id, v.title))
    print(" ".join(out).replace("\n ", "\n"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["extract", "draw", "account", "report", "show"])
    ap.add_argument("args", nargs="*", help="show: VIDEO_ID START(h:mm:ss) [SECONDS]")
    a = ap.parse_args()
    if a.stage == "show":
        show(a.args[0], a.args[1], int(a.args[2]) if len(a.args) > 2 else 60)
        return
    {"extract": extract, "draw": draw, "account": account_candidates, "report": report}[a.stage]()


if __name__ == "__main__":
    main()
