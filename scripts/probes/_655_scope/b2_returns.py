"""#655 scope Q-B: how did each same-name flip come back — birth-gate verdict on the return night (if any) and
whether a continuity rename made the name. $0."""
import json, re
from datetime import date
from load import load
b = load()
flips = []
for ln in open("b1_churn.out"):
    m = re.match(r"  (.*?) \| (\d{4}-\d\d-\d\d) \| (.*?) \| (\d{4}-\d\d-\d\d)$", ln.rstrip())
    if m: flips.append((m.group(1), date.fromisoformat(m.group(2)), m.group(3), date.fromisoformat(m.group(4))))
gate = {}
for e in b["events"]:
    d = date.fromisoformat(e["et"][:10])
    if e["event_type"] == "theme_birth_gate":
        try:
            for v in json.loads(e["detail"]):
                gate.setdefault((d, v.get("name")), []).append((e["summary"][11:30], v["outcome"], v.get("join_target")))
        except Exception:
            pass
cont = {}
for e in b["events"]:
    if e["event_type"] == "theme_renamed_for_continuity":
        d = date.fromisoformat(e["et"][:10])
        for m in re.finditer(r"'(.*?)' → '(.*?)'", e["detail"] or ""):
            cont.setdefault((d, m.group(2)), []).append(m.group(1))
src = {}
for r in b["themes"]:
    src[(r["d"], r["name"])] = r["source"]
for n, off, c, back in flips:
    g = [v for (d, nm), v in gate.items() if d == back and (nm == n or nm in cont.get((back, n), []))]
    print(f"{n[:60]} | off {off} ({c[:30]}) | back {back} src={src.get((back, n))} | continuity-rename from {cont.get((back, n), [])[:1]} | gate {g[:1]}")
