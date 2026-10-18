#!/usr/bin/env python3
"""#702 P4b step 3b - parse the saved Kyna Kosling post HTML into kyna_notes.tsv ($0: html.parser + regex).

Per (post, ticker): the stream date, how the ticker was recognised (cashtag / parenthesis / bare capitals / name),
the text around every mention, the nearby IMAGE URLs and alt text (URLs only - no image is downloaded), and the same
keyword flags as the transcripts. Step 2 (match_bars.py) adds the watch-row match.

usage: parse_kyna.py --out OUT --closes daily_closes_all.csv.gz
"""
import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import sys
from collections import defaultdict
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qmlib  # noqa: E402
from extract_hits import ACRONYM_IGNORE, build_aliases, load_names  # noqa: E402

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                      "october", "november", "december"], 1)}
DATE_RE = re.compile(r"(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4})", re.I)
# capitalised words in the notes that are acronyms / market vocabulary, never a ticker on their own
CAPS_STOP = set("""EP EPS ADR ATR ATH SMA EMA MA IPO CEO CFO CTO ETF ETFS USA US UK EU FED GDP CPI PPI PE PS VS RS RSI ORH PM AM
NYSE NASDAQ SEC PR AI THE AND FOR NOT BUT YOU ARE CAN ALL ONE NEW TOP HOD LOD OK TL DR LOL OMG FOMO YTD QOQ YOY TTM FCF AH PRE
OTC SPAC FAQ USD EUR PDF URL CAGR EBITDA GAAP ESG ATM ITM OTM LLC INC LTD PLC NOTE UPDATE PLUS FIVE FOUR SIX STAR ADRS TAM IV HV
DIY MM AP YT""".split())


class Blocks(HTMLParser):
    """body_html -> ordered blocks: ('h', level, text) / ('t', text) / ('img', url, alt)."""
    BLOCK = {"p", "li", "blockquote", "figcaption", "h1", "h2", "h3", "h4", "h5", "h6", "div", "ul", "ol", "br", "td", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.buf, self.hlevel = [], [], None

    def flush(self):
        txt = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if txt:
            self.blocks.append(("h", self.hlevel, txt) if self.hlevel else ("t", txt))
        self.buf, self.hlevel = [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.BLOCK:
            self.flush()
            if re.fullmatch(r"h[1-6]", tag):
                self.hlevel = int(tag[1])
        elif tag == "img":
            self.flush()
            src, alt = a.get("src", ""), a.get("alt", "") or ""
            da = a.get("data-attrs")
            if da:
                try:
                    j = json.loads(html.unescape(da))
                    src = j.get("src") or src
                    alt = j.get("alt") or alt
                except Exception:
                    pass
            self.blocks.append(("img", src, alt))

    def handle_endtag(self, tag):
        if tag in self.BLOCK:
            self.flush()

    def handle_data(self, data):
        self.buf.append(data)

    def close(self):
        super().close()
        self.flush()


def stream_dates(raw_dir):
    """slug -> stream date from the index headings (authoritative), e.g. '18 May 2023'."""
    p = os.path.join(raw_dir, "qullamaggie-stream-notes.html")
    s = open(p, encoding="utf-8").read()
    m = re.search(r'<script type="application/json" id="preloads-json"[^>]*>(.*?)</script>', s, re.S)
    body = json.loads(m.group(1))["post"]["body_html"]
    out = {}
    for mm in re.finditer(r'<h4><a href="([^"]+)">([^<]+)</a></h4>', body):
        slug = re.search(r"/p/([a-z0-9\-]+)", html.unescape(mm.group(1)))
        dm = DATE_RE.search(mm.group(2))
        if slug and dm:
            out[slug.group(1)] = dt.date(int(dm.group(3)), MONTHS[dm.group(2).lower()], int(dm.group(1))).isoformat()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--closes", required=True)
    a = ap.parse_args()
    raw_dir = os.path.join(a.out, "kyna_raw")
    sdates = stream_dates(raw_dir)
    uni = qmlib.load_universe(a.closes, os.path.join(a.out, "universe_dates.pkl"))
    all_t = set(uni)
    bars_min = min(int(v[0]) for v in uni.values())
    dict_words = set(w.strip().lower() for w in open("/usr/share/dict/words", encoding="utf-8", errors="replace"))
    names = load_names(a.out)
    aliases = build_aliases(names, dict_words, set())
    rows = []
    for fn in sorted(os.listdir(raw_dir)):
        slug = fn[:-5]
        if slug == "qullamaggie-stream-notes":
            continue
        s = open(os.path.join(raw_dir, fn), encoding="utf-8").read()
        m = re.search(r'<script type="application/json" id="preloads-json"[^>]*>(.*?)</script>', s, re.S)
        if not m:
            continue
        post = json.loads(m.group(1)).get("post") or {}
        bh = post.get("body_html") or ""
        if post.get("audience") not in (None, "everyone") or not bh:
            print(slug, "PAYWALLED / empty - skipped", flush=True)
            continue
        sdate = sdates.get(slug, "")
        if not sdate:
            dm = DATE_RE.search(post.get("title") or "")
            if dm and "stream notes" in (post.get("title") or "").lower():
                sdate = dt.date(int(dm.group(3)), MONTHS[dm.group(2).lower()], int(dm.group(1))).isoformat()
        pub = (post.get("post_date") or "")[:10]
        bp = Blocks()
        bp.feed(bh)
        bp.close()
        blocks = bp.blocks
        if sdate and dt.date.fromisoformat(sdate).toordinal() + 60 >= bars_min:
            cand = qmlib.tickers_in_window(uni, dt.date.fromisoformat(sdate).toordinal(), 60)
            bars_win = 1 if cand else 0
        else:
            cand, bars_win = all_t, 0
        section = ""
        found = defaultdict(lambda: dict(via=set(), ctx=[], imgs=[], alts=[], n=0, sections=set()))
        for bi, b in enumerate(blocks):
            if b[0] == "h":
                section = b[2]
            if b[0] == "img":
                continue
            text = b[-1]
            hits = []
            for mm in re.finditer(r"\$([A-Z]{1,5})\b", text):
                hits.append((mm.group(1), "cashtag"))
            for mm in re.finditer(r"\(([A-Z]{1,5})\)", text):
                hits.append((mm.group(1), "paren"))
            if b[0] == "h" or len(text) <= 12:        # a bare ticker line in a list: 'APLD'
                if re.fullmatch(r"[A-Z]{2,5}", text.strip()):
                    hits.append((text.strip(), "bare-line"))
            for mm in re.finditer(r"\b([A-Z]{3,5})\b", text):
                hits.append((mm.group(1), "bare"))
            low = text.lower()
            for al, ts in aliases.items():
                if al in low and re.search(r"\b" + re.escape(al) + r"\b", low):
                    tk = sorted([x for x in ts if x in cand], key=lambda x: (len(x), x))
                    if tk:
                        hits.append((tk[0], "name"))
            seen = set()
            for tk, via in hits:
                if (tk, via) in seen:
                    continue
                seen.add((tk, via))
                if tk not in cand or tk in CAPS_STOP or tk.lower() in ACRONYM_IGNORE and via not in ("cashtag", "paren", "name"):
                    continue
                if via == "bare" and tk.lower() in dict_words and tk not in ("AAPL",):
                    continue                           # a capitalised English word, not a ticker
                f = found[tk]
                f["via"].add(via)
                f["n"] += 1
                f["sections"].add(section)
                listlike = bool(re.fullmatch(r"[A-Z]{2,5}", text.strip()))   # a bare watch-list line: no discussion, no chart
                ctx = text if (len(text) > 40 or listlike) else text + " | " + " ".join(x[-1] for x in blocks[bi + 1:bi + 4] if x[0] != "img")
                f["ctx"].append(ctx[:600])
                f["listonly"] = f.get("listonly", True) and listlike
                if not listlike:
                    for x in blocks[max(0, bi - 1):bi + 6]:
                        if x[0] == "img" and x[1] not in f["imgs"]:
                            f["imgs"].append(x[1])
                            f["alts"].append(x[2])
        for tk, f in found.items():
            ctx = " || ".join(dict.fromkeys(f["ctx"]))[:3000]
            fl = qmlib.kw_flags(ctx.lower())
            chart = any(fl[x] for x in qmlib.CHART_KW)
            strong = {"cashtag", "paren", "bare-line"} & f["via"]
            rows.append(dict(source="kyna", listonly=int(f.get("listonly", False)), slug=slug, stream_date=sdate, published=pub, ticker=tk, via="+".join(sorted(f["via"])),
                             tier="A" if strong else "N", mentions=f["n"], bars_window=bars_win, chart_kw=int(chart),
                             strength=round(qmlib.kw_strength(fl) * (1.0 if strong else 0.7), 2),
                             n_images=len(f["imgs"]), image_urls=" ".join(f["imgs"][:6]), image_alts=" || ".join(x for x in f["alts"][:6] if x),
                             sections=" | ".join(sorted(x for x in f["sections"] if x))[:300],
                             **{f"kw_{k}": v for k, v in fl.items()}, context=ctx))
        print(slug, sdate or "(undated)", "blocks", len(blocks), "imgs", sum(1 for b in blocks if b[0] == "img"),
              "tickers", len(found), flush=True)
    cols = list(rows[0].keys())
    with open(os.path.join(a.out, "kyna_notes_raw.tsv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        wr.writeheader()
        for r in rows:
            wr.writerow(r)
    print(len(rows), "post-ticker rows -> kyna_notes_raw.tsv", flush=True)


if __name__ == "__main__":
    main()
