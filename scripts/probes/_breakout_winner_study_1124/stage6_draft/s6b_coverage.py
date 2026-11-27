"""Stage 6 DRAFT step b: coverage of the draft flag (OUTCOME-FREE: reads the components table, the stage-1f feature table and the gallery key's
chart ids only - no outcome column of any file)."""
from common6 import *
P = Out("6b_coverage.txt")
P("# STAGE 6 DRAFT (not a freeze) - b. COVERAGE of gallery read #1 'V into the breakout' - outcome-free"); P(assert_all())
F = components()
T = L.load()
F = F.merge(T[["era", "ci", "ticker", "f01", "B4", "f12", "first10"]], on=["era", "ci", "ticker"], how="left", validate="1:1")
K = F[F.kept].reset_index(drop=True); K2 = F[F.kept2411].reset_index(drop=True)
assert len(K) == 11596 and len(K2) == 11607
P(f"thresholds: trough_age <= {gr1.T_MAX_AGE}, drop_adr >= {gr1.DROP_ADR_MIN}, recover >= {gr1.RECOVER_MIN}, at_level <= {gr1.AT_LEVEL_MAX}; window {gr1.WIN}, drop leg {gr1.PRE}")
P(f"NULLs: seed 1124 {int((K.gr1_null != '').sum())} of {len(K)}; seed 2411 {int((K2.gr1_null != '').sum())} of {len(K2)}; reasons {dict(F.gr1_null[F.gr1_null != ''].value_counts()) or 'NONE'}")
def line(nm, d):
    n = len(d); v = int((d.gr1 == 1).sum()); a = int((d.alt1 == 1).sum())
    return f"   {nm:26} n {n:5d} | V {v:4d} = {100 * v / max(n, 1):5.1f}% | not-V {n - v:5d} | ALT-1 (pause allowed) {a:4d} = {100 * a / max(n, 1):5.1f}%"
for nm, d in (("SEED 1124 (kept)", K), ("SEED 2411 (kept2411)", K2)):
    P(f"\n== {nm} - share flagged ==")
    P(line("ALL", d)); P(line("DISCOVERY (2017-20)", d[d.set == "DISC"])); P(line("CHECK (2021-24)", d[d.set == "CHECK"]))
    P(line("CHECK era A (2021-22Q1)", d[(d.set == "CHECK") & (d.era == "A")])); P(line("CHECK era B (2022-24)", d[(d.set == "CHECK") & (d.era == "B")]))
    for (e, y), g in d.groupby(["era", "Ey"]): P(line(f"era {e} {y}", g))
D = K[K.set == "DISC"]; C = K[K.set == "CHECK"]
P("\n== steps of the definition (seed 1124, kept) ==")
s1 = K.trough_age <= gr1.T_MAX_AGE; s2 = s1 & (K.drop_adr >= gr1.DROP_ADR_MIN); s3 = s2 & (K.recover >= gr1.RECOVER_MIN); s4 = s3 & (K.at_level <= gr1.AT_LEVEL_MAX)
for nm, s in (("1 low of 85 sessions made in the last 60", s1), ("2 + drop >= 5 daily ranges", s2), ("3 + level takes back >= half", s3), ("4 + under 10 sessions at the level", s4)):
    P(f"   {nm:42} {int(s.sum()):5d} = {100 * s.mean():5.1f}%   (discovery {100 * s[K.set == 'DISC'].mean():.1f}% / check {100 * s[K.set == 'CHECK'].mean():.1f}%)")
V = K[K.gr1 == 1]
P("   among the flagged: median sessions since the low %.0f, median drop %.1f ranges over %.0f sessions, median recover %.2f, median sessions at the level %.0f, median base_len (f12) %.0f"
  % (V.trough_age.median(), V.drop_adr.median(), V.drop_len.median(), V.recover.median(), V.at_level.median(), V.f12.median()))
P(f"   the low sits INSIDE the list's base (trough_age < base_len) on {100 * (V.trough_age < V.f12).mean():.0f}% of the flagged")
P("\n== two-group minimum of prereg 4.1 (information; a read skips the 5.2 gates): smaller group >= 100 events AND >= 15% ==")
for nm, d in (("discovery", D), ("check", C), ("check era A", C[C.era == "A"]), ("check era B", C[C.era == "B"])):
    v = int((d.gr1 == 1).sum()); P(f"   {nm:12} V {v} of {len(d)} = {100 * v / len(d):.1f}% -> {'meets' if (v >= 100 and v / len(d) >= 0.15) else 'UNDER the 15% line (>= 100 events: ' + ('yes' if v >= 100 else 'no') + ')'}")
P("\n== share flagged by third of daily range (f01) and of distance to the level (B4), thirds within (era, month), seed 1124 ==")
for col in ("f01", "B4"):
    t = L.assign_thirds(K[col].to_numpy(float), [K.era.values, K.month.values], 6)
    P(f"   {col}: " + " | ".join(f"{nm} {100 * (K.gr1[t == q] == 1).mean():.1f}% (n {int((t == q).sum())})" for q, nm in ((0, 'bottom'), (1, 'middle'), (2, 'top'))))
P("   first breaks (after 10 quiet sessions) %.1f%% vs later breaks %.1f%%" % (100 * (K.gr1[K.first10 == True] == 1).mean(), 100 * (K.gr1[K.first10 != True] == 1).mean()))
P("\n== FACE CHECK on the 48 charts of gallery pairs 1-2 (the sheets opened to write the definition; chart id only - no outcome column read) ==")
P("   called a V by eye from the two sheets (shape only; listed before the first components print, written to a file only after it): 01F-01 01F-04 01F-07 01F-08 01F-10 02F-05 02F-06 02F-07 02F-08 02F-09 02F-10 01W-04 01W-08 02W-06 02W-07 02W-09 02W-10")
G = pd.read_csv(ROOT / "stage5_gallery/_key/gallery_A_key.tsv", sep="\t", dtype={"identity": str}, keep_default_na=False, usecols=["chart", "pair", "identity", "D", "E"])
G = G[G.pair <= 2].merge(K, left_on=["identity", "D", "E"], right_on=["ticker", "D", "E"], how="left", validate="1:1")
EYE = set("01F-01 01F-04 01F-07 01F-08 01F-10 02F-05 02F-06 02F-07 02F-08 02F-09 02F-10 01W-04 01W-08 02W-06 02W-07 02W-09 02W-10".split())
P(f"   {'chart':7} {'age':>4} {'drop':>6} {'recov':>6} {'atLvl':>5}  gr1 alt1  eye")
for r in G.itertuples():
    P(f"   {r.chart:7} {r.trough_age:4.0f} {r.drop_adr:6.2f} {r.recover:6.2f} {r.at_level:5.0f}  {int(r.gr1):3d} {int(r.alt1):4d}  {'V' if r.chart in EYE else ''}")
e = G.chart.isin(EYE)
P(f"   eye-V charts flagged: main {int((G.gr1[e] == 1).sum())} of {int(e.sum())}, ALT-1 {int((G.alt1[e] == 1).sum())} of {int(e.sum())}; not-eye-V charts flagged: main {int((G.gr1[~e] == 1).sum())} of {int((~e).sum())}, ALT-1 {int((G.alt1[~e] == 1).sum())} of {int((~e).sum())}")
P("   (the eye list is one reader's, made from two sheets; it shows where the form and the eye part ways - mostly condition 4 and the 5-range bar)")
P.save()
