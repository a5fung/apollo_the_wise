"""Read-only, local: group the stored M&A audit rows (fired_rows.psv) by event, source path, publisher.
Population = mna_filter_fired / released / headline_unanswered rows 2026-05-14 .. 2026-10-10."""
import collections, json, re, sys

rows = []
for i, line in enumerate(open(sys.argv[1] if len(sys.argv) > 1 else "fired_rows.psv")):
    if i == 0:
        continue
    p = line.rstrip("\n").split("|", 4)
    if len(p) < 5:
        continue
    d, hhmm, ev, summ, det = p
    obj = {}
    try:
        obj = json.loads(det)
    except Exception:
        for k in ("source", "match_path", "publisher", "title", "published_utc", "matched_keyword"):
            m = re.search(rf"['\"]{k}['\"]: ['\"](.*?)['\"][,}}]", det)
            if m:
                obj[k] = m.group(1)
    rows.append((d, hhmm, ev, summ, obj))

c = collections.Counter()
for d, hhmm, ev, summ, o in rows:
    month = d[:7]
    c[(month, ev, o.get("source", ""), o.get("publisher", ""))] += 1
for k, v in sorted(c.items()):
    print(v, k)
print(len(rows), "rows")
