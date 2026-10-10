"""#655 scope Q-B: theme churn over the last 14 engine nights (2026-09-22 .. 10-09). $0, capture only.
PRE-STATED:
 * on(name, night) = a non-Retired mi_themes row with >= 1 member dated that night (the engine saves every live theme
   nightly — rows per night ~= board).
 * SAME-NAME FLIP = name on at night a, off at the next engine night b, on again at a later night c; b and c inside
   the 14-night window. Counted once per return.
 * NEW-NAME RE-MINT = name X goes off at b (window), and within 7 calendar days after b a name never seen since 06-15
   appears whose first roster has Jaccard >= 0.5 with X's last roster.
 * Cause of the exit = the audit row(s) on night b naming X, by precedence: Pass-2 cap (split: < 3 members at the cap /
   >= 3 judged, none passed = ruling (a)'s case / a member passed = correctly absorbed) > Pass-1.5 absorption >
   empty shell (protect-strip EMPTY_AFTER_STRIP or Step-4 cap drop) > rule B > Arm-B thesis merge > rename (mass flag /
   continuity) > Arm-A dissolve > 5-night Fading retire > merge-pass drop with no row of its own (Pass-1 overlap merge
   or other) > none found.
"""
import json, re
from collections import Counter, defaultdict
from datetime import date, timedelta
from load import load
b = load()
NIGHTS_ALL = sorted({r["d"] for r in b["themes"]})
WIN = [d for d in NIGHTS_ALL if d <= date(2026, 10, 9)][-14:]
PRE = [d for d in NIGHTS_ALL if d < WIN[0]][-1]
SEQ = [PRE] + WIN
on = defaultdict(dict)
for r in b["themes"]:
    if r["stage"] != "Retired" and r["tickers"]:
        on[r["d"]][r["name"]] = r
first_seen = {}
for r in sorted(b["themes"], key=lambda r: (r["d"], r["id"])):
    if r["stage"] != "Retired" and r["tickers"]:
        first_seen.setdefault(r["name"], r)

ev = defaultdict(lambda: defaultdict(list))  # night -> name -> [(cause, extra)]
for e in b["events"]:
    d = date.fromisoformat(e["et"][:10]); s = e["summary"] or ""; det = e["detail"] or ""; t = e["event_type"]
    def add(n, c, x=None): ev[d][n].append((c, x))
    if t in ("theme_sector_cap_not_absorbed", "theme_sector_cap_absorbed"):
        j = json.loads(det); m = j.get("members") or {}
        judged = sum(1 for v in m.values() if v.get("path") == "tape")
        passed = sum(1 for v in m.values() if v.get("verdict") == "admit")
        if passed: k = "cap: a member passed (absorbed)"
        elif len(m) < 3 or judged < 3: k = "cap: < 3 members/judged at the cap"
        else: k = "cap: >= 3 judged, none passed (ruling (a) keeps these)"
        add(j["source"], k, j.get("target"))
    elif t == "theme_sector_cap_dropped":
        m = re.match(r"'(.*)' dropped by sector cap", s); add(m.group(1), "cap: biotech family slot taken")
    elif t == "theme_pass1_5_absorption":
        m = re.search(r"t='(.*?)' t_score", det); add(m.group(1), "Pass-1.5 small-theme absorption", re.search(r"target='(.*?)' target_score", det).group(1))
    elif t == "theme_pass1_protect_strip" and "EMPTY_AFTER_STRIP" in det:
        m = re.search(r"stripped='(.*?)' \d", det); add(m.group(1), "empty shell (re-minted namesake stripped)")
    elif t == "theme_cap_drop":
        for m in re.finditer(r"dropped '(.*?)' size", det): add(m.group(1), "empty shell (re-minted namesake stripped)" if "->0" in det else "below 2 members (Step-4)")
    elif t == "theme_retired_small_fading":
        add(json.loads(det)["theme"], "rule B (small weak Fading)")
    elif t == "theme_thesis_merged":
        m = re.match(r"Arm B: '(.*?)' merged into", s); m and add(m.group(1), "Arm-B thesis merge")
    elif t == "theme_renamed_on_mass_flag":
        m = re.match(r"'(.*?)' renamed to", s); m and add(m.group(1), "rename")
    elif t == "theme_renamed_for_continuity":
        for m in re.finditer(r"'(.*?)' → '(.*?)'", det): add(m.group(1), "rename")
    elif t == "theme_dissolved_flagged_pair":
        m = re.match(r"Arm A dissolve: '(.*?)'", s); m and add(m.group(1), "Arm-A dissolve")
    elif t == "theme_retired":
        m = re.match(r"Retired: (.*)$", s); m and add(m.group(1).strip(), "5-night Fading retire")
    elif t == "theme_auto_retired":
        for m in re.finditer(r"'(.*?)' -> parent=", det): add(m.group(1), "merge-pass drop, no row of its own")
ORDER = ["cap: < 3 members/judged at the cap", "cap: >= 3 judged, none passed (ruling (a) keeps these)", "cap: a member passed (absorbed)",
         "cap: biotech family slot taken", "Pass-1.5 small-theme absorption", "empty shell (re-minted namesake stripped)",
         "below 2 members (Step-4)", "rule B (small weak Fading)", "Arm-B thesis merge", "rename", "Arm-A dissolve",
         "5-night Fading retire", "merge-pass drop, no row of its own"]
def cause(n, d):
    cs = [c for c, _ in ev[d].get(n, [])]
    for o in ORDER:
        if o in cs: return o
    return "none found"

flips = []; exits = []
for i in range(1, len(SEQ)):
    a, bb = SEQ[i - 1], SEQ[i]
    for n in on[a]:
        if n in on[bb]: continue
        ret = next((c for c in SEQ[i + 1:] if n in on[c]), None)
        exits.append((n, bb, cause(n, bb), ret))
        if ret: flips.append((n, bb, cause(n, bb), ret))
# new-name re-mints
remints = []
for n, bb, c, ret in exits:
    if ret and (ret - bb).days <= 7:
        continue
    last = on[[x for x in SEQ if x < bb][-1]][n]["tickers"]
    L = set(last)
    for nn, fr in first_seen.items():
        if nn == n or not (bb <= fr["d"] <= bb + timedelta(days=7)): continue
        F = set(fr["tickers"]); jac = len(L & F) / len(L | F)
        if jac >= 0.5:
            remints.append((n, bb, c, nn, fr["d"], round(jac, 2))); break

print(f"window {WIN[0]}..{WIN[-1]} ({len(WIN)} engine nights); exits {len(exits)}; same-name flips {len(flips)} "
      f"({len({f[0] for f in flips})} names); new-name re-mints within 7 days {len(remints)}")
cf = Counter(c for _, _, c, _ in flips); cr = Counter(c for _, _, c, *_ in remints); ce = Counter(c for _, _, c, _ in exits)
print("\ncause | same-name flips | new-name re-mints | all exits")
for o in ORDER + ["none found"]:
    if ce[o] or cf[o] or cr[o]: print(f"{o} | {cf[o]} | {cr[o]} | {ce[o]}")
print("\n== same-name flips (name | off night | cause | back on)")
for n, bb, c, r in sorted(flips, key=lambda x: (x[2], x[0], x[1])):
    print(f"  {n[:70]} | {bb} | {c} | {r}")
print("\n== new-name re-mints (old | off | cause | new name | first night | jaccard)")
for x in sorted(remints, key=lambda x: (x[2], x[0])):
    print(f"  {x[0][:55]} | {x[1]} | {x[2]} | {x[3][:55]} | {x[4]} | {x[5]}")
# return mechanism for same-name flips
srcs = Counter()
for n, bb, c, r in flips:
    row = on[r][n]
    renamed = any(cc == "rename" for cc, _ in []) 
    srcs[row["source"]] += 1
print("\nsource of the row on the return night:", dict(srcs))
# continuity renames that land on a returning name
cont = Counter()
for e in b["events"]:
    if e["event_type"] == "theme_renamed_for_continuity":
        d = date.fromisoformat(e["et"][:10])
        for m in re.finditer(r"'(.*?)' → '(.*?)'", e["detail"] or ""):
            if any(f[0] == m.group(2) and f[3] == d for f in flips): cont["return made by a continuity rename"] += 1
print(dict(cont))
