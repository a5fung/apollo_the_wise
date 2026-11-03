from pathlib import Path
HERE = Path(__file__).resolve().parent
src = (HERE / "v_f3.py").read_text()
exec(src.split("# ---------------------------------------------------------------- population checks")[0])
OUT.clear()
pa = {(p["ticker"], p["date"]): p["label"] for p in pairs if p["source"] == "A"}
BW = {"run_incl": False, "shelf_incl": False}
P("[shelf_win=22] pairs whose held differs, literal (60/45) vs builder (61/46) windows:")
for (t, d), lab in pa.items():
    a = f3(t, d, {"shelf_win": 22}); b = f3(t, d, {"shelf_win": 22, **BW})
    if a["held"] != b["held"]:
        P(f"   {t} {d} {lab}: literal held {a['held']} shelf {a['shelf_date']} {a['shelf']} d {a['d1']:+.2f}/{a['d2']:+.2f} S {a['S_date']} | builder held {b['held']} shelf {b['shelf_date']} {b['shelf']} d {b['d1']:+.2f}/{b['d2']:+.2f} S {b['S_date']}")
P("[stated] pairs whose held/into differs literal vs builder windows (all 158):")
nn = 0
for p in pairs:
    a = f3(p["ticker"], p["date"]); b = f3(p["ticker"], p["date"], BW)
    if a["held"] != b["held"] or a["into"] != b["into"]:
        nn += 1; P(f"   {p['ticker']} {p['date']} {p['source']}: held {a['held']}/{b['held']} into {a['into']}/{b['into']}")
P(f"   -> {nn} differ")
P("[KOD] variants under builder windows:")
for nm, v in [("stated", {}), ("run_win=30", {"run_win": 30}), ("shelf_win=22", {"shelf_win": 22}), ("run_win=90", {"run_win": 90}), ("shelf_win=68", {"shelf_win": 68})]:
    o = f3("KOD", "2026-09-28", {**v, **BW, "couple": True})
    P(f"   {nm}: S {o['S_date']} {o['S']} shelf {o['shelf_date']} {o['shelf']} d {o['d1']:+.2f}/{o['d2']:+.2f} held {o['held']} into {o['into']}")
# held_old (11-03 feature) from my own code
def held_old(t, d):
    sl, ia = slice_to(t, d)
    if sl is None or ia < 250: return None
    adr = adr20(sl, ia)
    bh = max(x[2] for x in sl[ia-250:ia-40])
    lows = []
    for i in range(ia-40, ia-2):
        L = sl[i][3]
        if L <= sl[i-1][3] and L <= sl[i-2][3] and L < sl[i+1][3] and L < sl[i+2][3]:
            lows.append(L)
    lows.sort()
    if len(lows) < 2: return None
    return 1 if all((x/bh-1)*100/adr >= -1 for x in lows[:2]) else 0
yv = [held_old(t, d) for (t, d), l in pa.items() if l in YES]; nv = [held_old(t, d) for (t, d), l in pa.items() if l in NO]
yv = [x for x in yv if x is not None]; nv = [x for x in nv if x is not None]
P(f"[held_old] P(yes>no) {auc(yv, nv):.3f} n {len(yv)}/{len(nv)} =1 {sum(yv)}/{sum(nv)}")
(HERE / "extra.txt").write_text("\n".join(OUT) + "\n")
