"""#624 backfill — STAGE 2 minute-pull lists: every backfill-window (2024-01-02..2026-09-03) prefilter row, split
round-robin (date order) over three workers so an interrupted pull still covers every year. Outcome-blind."""
import json
import lib624 as L
L.assert_frozen()
samp = json.load(open(L.HERE / "s1_samples.json"))
dec = json.load(open(L.HERE / "s1_decisions.json"))
assert dec["w6_volume_safe"] and not dec["w6_price_widen"] and dec["a1_pass"] and dec["a2_pass"] and not dec["halt_phase1"]
done = set(L.load_minlog([L.HERE / "log_min_s1.txt"]))
keys = sorted({(r["t"], r["d"]) for r in samp["BW"]} - {(t, d.isoformat()) for t, d in done}, key=lambda x: (x[1], x[0]))
for i, tag in enumerate("abc"):
    part = keys[i::3]
    open(L.HERE / f"list_min_s2{tag}.txt", "w").write("\n".join(f"{t}|{d}" for t, d in part) + "\n")
    print(tag, len(part))
print("total", len(keys))
