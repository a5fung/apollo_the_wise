"""#655(a) replay, $0, offline: reads cap_rows_30d.jsonl (captured ONCE by capture.sh) and applies the
proposed keep rule to every Pass-2 sector-cap row.

RULE: a theme the cap would move into its group's top theme is KEPT when at least 3 of its members were
judged by the co-movement test (path == "tape": price history + a target basket of >= 3 members with
>= 30 overlapping sessions) and none passed, and none already sits in the top theme. Anything else keeps
today's path.

Pre-set bar (fixed before the run): keep the three named churners on their churn nights AND keep no theme
any of whose members passed.
"""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
MIN_JUDGED = 3

rows = [json.loads(ln.rstrip("\n").replace("\\\\", "\\")) for ln in open(HERE / "cap_rows_30d.jsonl")]
cap = [r for r in rows if r["event_type"] in ("theme_sector_cap_absorbed", "theme_sector_cap_not_absorbed")]
biotech = [r for r in rows if r["event_type"] == "theme_sector_cap_dropped"]

per_night = defaultdict(list)
violations = []
for r in cap:
    d = json.loads(r["detail"])
    members = d.get("members") or {}
    judged = [tk for tk, v in members.items() if v.get("path") == "tape"]
    passed = [tk for tk, v in members.items() if v.get("verdict") == "admit"]
    unjudged = [tk for tk, v in members.items() if v.get("path") == "unjudgeable"]
    guard = [tk for tk, v in members.items() if v.get("path") in ("cooldown", "exclusion")]
    already = d.get("already_in_target") or []
    keep = len(judged) >= MIN_JUDGED and not passed and not already
    if keep and passed:
        violations.append(d["source"])
    why = ("KEEP" if keep else
           "absorbed (a member passed / already in top)" if (passed or already) else
           f"drop as today ({len(judged)} judged < {MIN_JUDGED})")
    per_night[r["et"][:10]].append((d["source"], d["target"], len(members), len(judged), len(passed),
                                    len(unjudged), len(guard), why))

print(f"Pass-2 cap rows: {len(cap)} (absorbed/not_absorbed) over {len(per_night)} nights; "
      f"biotech per-family drops (not this path): {len(biotech)}")
print(f"first cap row {min(per_night)}  last {max(per_night)}")
kept_total = 0
for night in sorted(per_night):
    print(f"\n== {night}")
    for src, tgt, n, j, p, u, g, why in per_night[night]:
        kept_total += why == "KEEP"
        print(f"  {why:<44} members={n:<2} judged={j:<2} passed={p} unjudgeable={u} guard={g}  "
              f"'{src[:60]}' -> '{tgt[:40]}'")
print(f"\nKEPT under the rule: {kept_total} of {len(cap)}")
print(f"kept themes with any passing member (must be 0): {len(violations)}")
