"""#210 2026-10-10 — item-by-item side-by-side of OUR stored corpus vs TradingView's
`tv_items_we_missed`, for the two readable rows with TradingView coverage (ACN 10-01,
PENG 10-07). Reads q1_read.out (captured once); never touches prod.

For every item: source/provider, published time in ET, whether it was published AFTER
our extraction time (so it could not have been in our corpus at grade time), and the
best fuzzy title match on the other side (token Jaccard after the same normalisation
tv_news_shadow.normalize_title applies, plus a numeric-token overlap).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
OUT = sys.argv[1] if len(sys.argv) > 1 else "q1_read.out"

_NORM = re.compile(r"[^a-z0-9\s]")
_WS = re.compile(r"\s+")
STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "is", "at", "by", "as",
        "with", "its", "it", "from", "this", "that", "are", "be", "or", "vs", "after",
        "stock", "stocks", "shares", "inc", "corp", "ltd", "plc", "co", "nyse", "nasdaq"}


def norm(t: str) -> str:
    return _WS.sub(" ", _NORM.sub(" ", t.lower())).strip()


def toks(t: str) -> set:
    return {w for w in norm(t).split() if w not in STOP and len(w) > 1}


def jacc(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def section(text: str, start: str, end: str) -> list[str]:
    lines = text.splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(start))
    j = next(k for k, l in enumerate(lines) if l.startswith(end) and k > i)
    return lines[i + 1:j]


def parse_tsv(lines: list[str]) -> list[dict]:
    rows = [l for l in lines if l and not l.startswith("(") and not l.startswith("###")]
    hdr = rows[0].split("\t")
    out = []
    for r in rows[1:]:
        cells = r.split("\t")
        if len(cells) != len(hdr):
            # psql -A prints embedded newlines raw; our JSON columns have none, but pplx may.
            continue
        out.append(dict(zip(hdr, cells)))
    return out


def et(dt_str_or_epoch) -> datetime | None:
    if dt_str_or_epoch in (None, "", "null"):
        return None
    if isinstance(dt_str_or_epoch, (int, float)):
        return datetime.fromtimestamp(dt_str_or_epoch, tz=ET)
    s = str(dt_str_or_epoch)
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(ET)


text = open(OUT, encoding="utf-8").read()
q3 = parse_tsv(section(text, "### Q3", "### Q4"))
q4 = parse_tsv(section(text, "### Q4", "### Q5"))

missed_by_key = {(r["ticker"], r["alert_date"]): json.loads(r["missed"]) for r in q4}

for r in q3:
    key = (r["ticker"], r["alert_date"])
    extracted_et = datetime.fromisoformat(r["extracted_et"]).replace(tzinfo=ET)
    ours = []
    for src, col, tkey in (("polygon", "polygon", "published_utc"),
                           ("alpaca", "alpaca", "created_at"),
                           ("fmp", "fmp", "published")):
        raw = r.get(col) or ""
        if raw in ("", "null"):
            continue
        items = json.loads(raw)
        for it in items:
            t = it.get("title") or ""
            when = et(it.get(tkey) or it.get("published_utc") or it.get("created_at")
                      or it.get("published") or it.get("date"))
            ours.append({"src": src, "title": t, "when": when,
                         "provider": it.get("source") or it.get("publisher") or it.get("author") or ""})
    tv = missed_by_key[key]
    for it in tv:
        it["when"] = et(it["published"])

    print("=" * 110)
    print(f"{key[0]} {key[1]}  extracted_at={extracted_et:%Y-%m-%d %H:%M ET}  "
          f"ours={len(ours)} items  tv_missed={len(tv)} items  pplx_len={len(r.get('pplx') or '')}")
    print("-" * 110)
    print("OUR CORPUS (as stored at grade time):")
    for o in sorted(ours, key=lambda x: x["when"] or datetime.min.replace(tzinfo=ET)):
        w = f"{o['when']:%m-%d %H:%M}" if o["when"] else "??"
        print(f"  [{o['src']:7}] {w} ET  {o['provider'][:14]:14} | {o['title'][:88]}")
    print("-" * 110)
    print("TV ITEMS WE 'MISSED' (same-day rule) — after_our_extraction? / best match on our side:")
    n_after = 0
    n_match = 0
    for it in sorted(tv, key=lambda x: x["when"]):
        after = it["when"] > extracted_et
        n_after += after
        tt = toks(it["title"])
        best = max(ours, key=lambda o: jacc(tt, toks(o["title"])), default=None)
        bj = jacc(tt, toks(best["title"])) if best else 0.0
        nums_tv = {w for w in tt if any(c.isdigit() for c in w)}
        nums_best = {w for w in toks(best["title"]) if any(c.isdigit() for c in w)} if best else set()
        num_overlap = len(nums_tv & nums_best)
        flag = "AFTER " if after else "before"
        hit = bj >= 0.34 or (num_overlap >= 2)
        n_match += hit
        print(f"  {it['when']:%m-%d %H:%M} ET {flag} {it['provider'][:12]:12} j={bj:.2f} "
              f"{'MATCH' if hit else '     '} | {it['title'][:70]}")
        if best and bj > 0:
            print(f"        ~ ours [{best['src']}]: {best['title'][:80]}")
    print("-" * 110)
    print(f"SUMMARY {key[0]}: tv_missed={len(tv)}; published AFTER our extraction={n_after}; "
          f"before-or-at={len(tv) - n_after}; fuzzy story match to something we held={n_match}")
