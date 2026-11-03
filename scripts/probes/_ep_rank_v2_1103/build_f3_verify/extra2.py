from pathlib import Path
HERE = Path(__file__).resolve().parent
src = (HERE / "comp.py").read_text()
exec(src.split("LIT = {}")[0])
OUT.clear()
zy = [zones(t, d) for (t, d) in yesA]; zn = [zones(t, d) for (t, d) in noA]
P(f"[zones_cleared] A P(yes>no) {auc([x for x in zy if x is not None], [x for x in zn if x is not None]):.3f} n {sum(x is not None for x in zy)}/{sum(x is not None for x in zn)}")
sl, ia = slice_to("KOD", "2026-09-28")
for i in range(ia - 45, ia):
    if sl[i][3] < 30.0 or sl[i][0] in ("2026-09-11", "2026-09-18", "2026-09-24"):
        P(f"[KOD] D-{ia-i} {sl[i][0]} low {sl[i][3]}")
jun = [(x[3], x[0], ia - i) for i, x in enumerate(sl) if "2026-06-01" <= x[0] <= "2026-07-15"]
P(f"[KOD] June-mid July lowest low {min(jun)} (D-offset) · 40-session pivot window starts {sl[ia-40][0]}")
(HERE / "extra2.txt").write_text("\n".join(OUT) + "\n")
