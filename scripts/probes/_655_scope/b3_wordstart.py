"""#655 scope Q-B parked items (1)(2): substring vs word-start keyword matching, on every theme name live in the 14
nights (2026-09-22..10-09). Uses the engine's own lists (theme_engine._SECTOR_KEYWORD_GROUPS, the ecosystem taxonomy
via theme_ecosystems.get_ecosystems — YAML only; dynamic buckets not captured). $0."""
import re
from collections import Counter
from datetime import date
import sys; sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from load import load
from agents.market_intelligence.theme_engine import _SECTOR_KEYWORD_GROUPS, _sector_group
from agents.market_intelligence import theme_ecosystems as te

b = load()
W0 = date(2026, 9, 22)
live = {}
for r in b["themes"]:
    if r["d"] >= W0 and r["stage"] != "Retired" and r["tickers"]:
        live[r["name"]] = r
def ws_group(name):
    low = name.lower()
    for g, kws, mx in _SECTOR_KEYWORD_GROUPS:
        if any(re.search(r"(?<![a-z0-9])" + re.escape(k), low) for k in kws):
            return g, mx
    return None
ch = []
for n in sorted(live):
    a, w = _sector_group(n), ws_group(n)
    if a != w:
        hit = [k for g, kws, _ in _SECTOR_KEYWORD_GROUPS for k in kws if k in n.lower() and not re.search(r"(?<![a-z0-9])" + re.escape(k), n.lower())]
        ch.append((n, a and a[0], w and w[0], hit))
print(f"(2) sector-cap groups: {len(live)} names live in the window; {sum(1 for n in live if _sector_group(n))} fall in a cap group today; "
      f"{len(ch)} change group under word-start matching")
for x in ch: print("   ", x[0][:75], "|", x[1], "->", x[2], "| substring hit", x[3])

ecos = te.get_ecosystems()
def kf_ws(name, desc, tickers):
    name_l, desc_l = (name or "").lower(), (desc or "").lower(); members = {t.upper() for t in tickers}
    best, bs = te.E_UNASSIGNED, 0.0
    for e in ecos:
        code = e.get("e_code")
        if not code or code == te.E_UNASSIGNED: continue
        s = 0.0
        for stem in (e.get("keyword_stems") or []):
            st = str(stem).lower() if stem else ""
            if not st: continue
            pat = r"(?<![a-z0-9])" + re.escape(st)
            if re.search(pat, name_l): s += te._NAME_STEM_WEIGHT
            elif re.search(pat, desc_l): s += te._DESC_STEM_WEIGHT
        s += te._EXEMPLAR_WEIGHT * len(members & {str(x).upper() for x in (e.get("exemplars") or [])})
        if s > bs: best, bs = code, s
    return (te.E_UNASSIGNED, bs) if bs < te._KEYWORD_MIN_SCORE else (best, bs)
methods = {}
for ln in __import__("gzip").open("capture.raw.gz", "rt"):
    m = re.search(r'"theme" : "(.*?)", "e" : "(.*?)", "method" : "(.*?)"', ln)
    if m: methods[m.group(1)] = (m.group(2), m.group(3))
chg_all = []; chg_kw = []
for n, r in live.items():
    a = te.keyword_fallback_ecosystem(n, r.get("desc") or "", r["tickers"], ecos)[0]
    w = kf_ws(n, r.get("desc") or "", r["tickers"])[0]
    if a != w:
        chg_all.append((n, a, w, methods.get(n)))
        if methods.get(n, (None, None))[1] == "keyword": chg_kw.append(n)
kw_live = [n for n in live if methods.get(n, (None, None))[1] == "keyword"]
print(f"\n(1) ecosystem keyword fallback: {len(kw_live)} of the {len(live)} live names were MAPPED by the fallback (method=keyword); "
      f"{len(chg_kw)} of those would map differently under word-start. If every live name went through the fallback, {len(chg_all)} would change.")
for x in chg_all: print("   ", x[0][:70], "|", x[1], "->", x[2], "| stored", x[3])
