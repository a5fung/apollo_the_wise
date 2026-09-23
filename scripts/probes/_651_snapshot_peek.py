"""Read-only peek at the portfolio-app2 snapshots — do they carry mi_themes history and/or
judge rationales usable for #651 without prod access? Local files only, nothing written."""
import json
import os

_THEMES = "/Users/alvinfung/portfolio-app2/apollo_themes_snapshot.json"
_FUNNEL = "/Users/alvinfung/portfolio-app2/apollo_funnel_snapshot.json"

for fn in (_THEMES, _FUNNEL):
    print("==", fn, os.path.getsize(fn), "bytes")
    d = json.load(open(fn))
    print("  type", type(d).__name__, (list(d.keys())[:12] if isinstance(d, dict) else len(d)))
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, list):
                keys = list(v[0].keys())[:22] if v and isinstance(v[0], dict) else (type(v[0]).__name__ if v else None)
                print("  ", k, "n=", len(v), "keys=", keys)
            else:
                print("  ", k, "=", str(v)[:100])

t = json.load(open(_THEMES))
th = t.get("themes") or t.get("mi_themes") or []
if th:
    ds = sorted({r.get("theme_date") for r in th if r.get("theme_date")})
    print("themes rows", len(th), "dates", ds[0], "->", ds[-1], "distinct names", len({r.get("name") for r in th}))

f = json.load(open(_FUNNEL))
if isinstance(f, dict):
    for k, v in f.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and any("rationale" in kk for kk in v[0]):
            print("funnel list with rationale:", k, len(v))
