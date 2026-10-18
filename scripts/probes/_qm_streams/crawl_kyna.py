#!/usr/bin/env python3
"""#702 P4b step 3 (Kyna Kosling's Qullamaggie stream notes) - FETCH only ($0, public pages).

Reads the index https://tradingresourcehub.substack.com/p/qullamaggie-stream-notes, lists every /p/<slug>
post it links (hrefs + embedded post cards), fetches each with >= 3 s between requests, honours robots.txt
(checked with urllib.robotparser for OUR user agent), stops at a paywall (records it, does not work around it).
Raw HTML is saved under OUT/kyna_raw/ so parsing (parse_kyna.py) can be iterated without re-fetching.
Honest user agent - NOT a browser string and NOT one of the AI-crawler names the site's robots.txt disallows.

usage: crawl_kyna.py --out OUT
"""
import argparse
import html
import json
import os
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser

BASE = "https://tradingresourcehub.substack.com"
INDEX = BASE + "/p/qullamaggie-stream-notes"
UA = "apollo-research-script/1.0 (personal research reader; low rate; no AI training)"
GAP = 3.5


def get(url, last=[0.0]):
    wait = GAP - (time.time() - last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        body, code = "", e.code
    last[0] = time.time()
    return code, body


def preload(page):
    m = re.search(r'<script type="application/json" id="preloads-json"[^>]*>(.*?)</script>', page, re.S)
    return json.loads(m.group(1)) if m else {}


def slugs_from(body_html):
    out = []
    for m in re.finditer(r'(?:href="|canonical_url&quot;:&quot;)([^"&]+(?:&amp;[^"&]*)*)', body_html):
        u = html.unescape(m.group(1))
        mm = re.search(r"tradingresourcehub(?:\.substack\.com)?/p/([a-z0-9\-]+)", u) or re.search(r"/pub/tradingresourcehub/p/([a-z0-9\-]+)", u)
        if mm and mm.group(1) not in out:
            out.append(mm.group(1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    raw = os.path.join(a.out, "kyna_raw")
    os.makedirs(raw, exist_ok=True)
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(BASE + "/robots.txt")
    rcode, rtxt = get(BASE + "/robots.txt")
    open(os.path.join(a.out, "kyna_robots.txt"), "w", encoding="utf-8").write(rtxt)
    rp.parse(rtxt.splitlines())
    print("robots: index allowed =", rp.can_fetch(UA, INDEX), flush=True)
    if not rp.can_fetch(UA, INDEX):
        raise SystemExit("robots.txt disallows the index for our UA - stopping")
    meta = []
    code, page = get(INDEX)
    open(os.path.join(raw, "qullamaggie-stream-notes.html"), "w", encoding="utf-8").write(page)
    d = preload(page)
    body = d.get("post", {}).get("body_html", "")
    slugs = [s for s in slugs_from(body) if s != "qullamaggie-stream-notes"]
    print(f"index http {code}, {len(slugs)} linked posts", flush=True)
    meta.append({"slug": "qullamaggie-stream-notes", "http": code, "audience": d.get("post", {}).get("audience"), "paywalled": 0})
    for s in slugs:
        url = f"{BASE}/p/{s}"
        if not rp.can_fetch(UA, url):
            meta.append({"slug": s, "http": None, "note": "robots disallow"})
            print(s, "robots disallow", flush=True)
            continue
        code, page = get(url)
        open(os.path.join(raw, s + ".html"), "w", encoding="utf-8").write(page)
        dd = preload(page)
        p = dd.get("post", {}) or {}
        bh = p.get("body_html") or ""
        paywalled = int(p.get("audience") not in (None, "everyone") or "paywall" in page[:200000].lower() and "This post is for paid subscribers" in page)
        meta.append({"slug": s, "http": code, "audience": p.get("audience"), "post_date": p.get("post_date"), "title": p.get("title"),
                     "wordcount": p.get("wordcount"), "body_chars": len(bh), "paywalled": paywalled})
        print(s, code, p.get("audience"), p.get("post_date"), "body", len(bh), "PAYWALL" if paywalled else "", flush=True)
    json.dump(meta, open(os.path.join(a.out, "kyna_crawl_meta.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
